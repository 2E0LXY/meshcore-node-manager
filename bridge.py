"""
bridge.py — MeshCore Network Bridge
MeshCore Node Manager  |  Original work

Connects multiple geographically separate MeshCore networks over the internet,
creating a software-defined long-distance relay. Each instance with bridging
enabled shares channel messages and contact telemetry with connected peers.

DISABLED BY DEFAULT — must be explicitly enabled in Settings.

Architecture
------------
Each bridge instance can run as a WebSocket server, client, or both.
  Server: listens for incoming peer connections on a configurable port
  Client: connects outward to a list of peer addresses

All bridged frames are newline-delimited JSON with the following fields:
  {
    "v":      1,                    # protocol version
    "id":     "<uuid>",             # unique message ID (dedup)
    "origin": "<node_name>",        # originating node name
    "hops":   0,                    # bridge hop count (dropped at >= MAX_HOPS)
    "secret": "<shared_secret>",    # optional shared secret
    "type":   "channel_msg",        # frame type (see FrameType)
    "payload": { ... }              # type-specific payload
  }

Frame types
-----------
  channel_msg:   { sender, text, ts }
  contact_upd:   { name, key, rssi, snr, lat, lon, battery, last_heard }
  ping:          { ts }
  pong:          { ts }

Loop prevention
---------------
  - Every message has a UUID; seen IDs are cached for 5 minutes
  - Bridge hop count: messages with hops >= MAX_BRIDGE_HOPS (3) are dropped
  - A bridge never re-injects a message whose origin matches its own node name

Security note
-------------
  The shared secret is a basic gatekeeper, not cryptographic authentication.
  For sensitive deployments run the bridge inside a VPN (WireGuard, Tailscale).
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from collections import OrderedDict
from enum import Enum

try:
    import websockets
    import websockets.server
    import websockets.exceptions
    _WS_OK = True
except ImportError:
    websockets = None
    _WS_OK = False

from version import BRIDGE_PROTOCOL_VERSION
from events import (
    EventBus,
    EV_MSG_CHANNEL,
    EV_CONTACTS_UPD,
    EV_LOG, EV_BRIDGE_STATUS,
)

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────
BRIDGE_DEFAULT_PORT  = 4404
PROTOCOL_VERSION     = BRIDGE_PROTOCOL_VERSION
MAX_BRIDGE_HOPS      = 3
DEDUP_TTL_SECS       = 300      # 5 minutes
PING_INTERVAL_SECS   = 30
RECONNECT_DELAY_SECS = 15
MAX_FRAME_BYTES      = 65_536   # 64 KB max incoming frame


class FrameType(str, Enum):
    CHANNEL_MSG  = "channel_msg"
    CONTACT_UPD  = "contact_upd"
    PING         = "ping"
    PONG         = "pong"
    HELLO        = "hello"


# ── deduplication cache ───────────────────────────────────────────────────────

class _DedupeCache:
    """
    TTL-expiring set of seen message IDs.
    Insertion order maintained so we can efficiently expire old entries.
    """

    def __init__(self, ttl: float = DEDUP_TTL_SECS):
        self._ttl  = ttl
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def seen(self, msg_id: str) -> bool:
        """Return True if msg_id was already seen; also records if not."""
        now = time.time()
        with self._lock:
            self._expire(now)
            if msg_id in self._seen:
                return True
            self._seen[msg_id] = now
            return False

    def _expire(self, now: float):
        cutoff = now - self._ttl
        while self._seen:
            oldest_id, oldest_ts = next(iter(self._seen.items()))
            if oldest_ts < cutoff:
                del self._seen[oldest_id]
            else:
                break


# ── frame helpers ─────────────────────────────────────────────────────────────

def _make_frame(ftype: FrameType, payload: dict,
                origin: str, secret: str, hops: int = 0) -> str:
    frame = {
        "v":       PROTOCOL_VERSION,
        "id":      str(uuid.uuid4()),
        "origin":  origin,
        "hops":    hops,
        "secret":  secret,
        "type":    ftype.value,
        "payload": payload,
    }
    return json.dumps(frame)


def _parse_frame(raw: str) -> "dict | None":
    try:
        frame = json.loads(raw)
        if frame.get("v") != PROTOCOL_VERSION:
            return None
        if "id" not in frame or "type" not in frame:
            return None
        return frame
    except (json.JSONDecodeError, AttributeError):
        return None


# ── Bridge ────────────────────────────────────────────────────────────────────

class Bridge:
    """
    The bridge engine.  One instance per AppWindow.
    Controls a background asyncio loop that runs WebSocket server and
    client connections concurrently.

    Public API (all thread-safe):
      start()          — enable bridge (called when settings enable it)
      stop()           — disable bridge
      set_radio(radio) — attach the NodeRadio instance
      is_running       — property

    Internal flow:
      Incoming LoRa message → local bus → _on_local_* → broadcast to peers
      Incoming WS frame     → validate/dedup → bus.emit → NodeRadio.transmit_channel
    """

    def __init__(self, bus: EventBus, settings):
        self._bus      = bus
        self._settings = settings
        self._radio    = None          # set by AppWindow after radio connect

        self._loop:   asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None          = None

        # Active WebSocket connections: { peer_addr: websocket }
        self._peers: dict[str, object] = {}
        self._peers_lock = threading.Lock()

        # Deduplication
        self._dedup = _DedupeCache()

        # Server task and client tasks
        self._server_task = None
        self._client_tasks: dict[str, object] = {}

        self._running = False

        # Subscribe to local radio events — wired in start()
        self._local_handlers_registered = False

    # ── lifecycle ─────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def set_radio(self, radio) -> None:
        self._radio = radio

    def start(self) -> None:
        if not _WS_OK:
            self._log("websockets library missing — pip install websockets", "err")
            return
        if self._running:
            return
        self._running = True
        self._start_loop()
        self._register_local_handlers()
        self._log("Bridge started", "ok")

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._unregister_local_handlers()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4.0)
        self._loop = self._thread = None
        self._peers.clear()
        self._client_tasks.clear()
        self._server_task = None
        self._log("Bridge stopped", "info")

    def peer_count(self) -> int:
        with self._peers_lock:
            return len(self._peers)

    def peer_list(self) -> list[str]:
        with self._peers_lock:
            return list(self._peers.keys())

    # ── background loop ───────────────────────────────────────────────────────

    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="bridge-loop"
        )
        self._thread.start()
        time.sleep(0.05)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self):
        """Root coroutine — launches server and/or client tasks."""
        tasks = []

        if self._settings.get("bridge_server_enabled", False):
            tasks.append(asyncio.create_task(self._run_server()))

        peers = self._settings.get("bridge_peers", [])
        for peer_uri in peers:
            tasks.append(asyncio.create_task(self._run_client(peer_uri)))

        if not tasks:
            self._log("Bridge enabled but no server/peers configured", "warn")
            return

        try:
            await asyncio.gather(*tasks)
        except Exception as exc:
            self._log(f"Bridge loop error: {exc}", "err")

    # ── WebSocket server ──────────────────────────────────────────────────────

    async def _run_server(self):
        port   = self._settings.get("bridge_port", BRIDGE_DEFAULT_PORT)
        secret = self._settings.get("bridge_secret", "")
        self._log(f"Bridge server listening on port {port}", "ok")

        try:
            async with websockets.server.serve(  # pylint: disable=no-member
                lambda ws: self._handle_peer(ws, secret, _is_server_side=True),
                host="0.0.0.0",
                port=port,
                max_size=MAX_FRAME_BYTES,
            ):
                await asyncio.Future()   # run until cancelled
        except OSError as exc:
            self._log(f"Bridge server failed to bind port {port}: {exc}", "err")
        except Exception as exc:
            self._log(f"Bridge server error: {exc}", "err")

    # ── WebSocket client ──────────────────────────────────────────────────────

    async def _run_client(self, uri: str):
        secret = self._settings.get("bridge_secret", "")
        while self._running:
            try:
                self._log(f"Bridge connecting to {uri}…", "info")
                async with websockets.connect(
                    uri,
                    max_size=MAX_FRAME_BYTES,
                    open_timeout=10,
                ) as ws:
                    self._log(f"Bridge connected to {uri}", "ok")
                    await self._handle_peer(ws, secret,
                                            _is_server_side=False,
                                            peer_label=uri)
            except websockets.exceptions.InvalidURI:
                self._log(f"Bridge: invalid URI '{uri}' — check format (ws://host:port)", "err")
                return   # Don't retry on config errors
            except (ConnectionRefusedError, OSError) as exc:
                self._log(f"Bridge: cannot reach {uri}: {exc}", "warn")
            except websockets.exceptions.ConnectionClosed:
                self._log(f"Bridge: {uri} disconnected", "warn")
            except Exception as exc:
                self._log(f"Bridge: {uri} error: {exc}", "warn")

            if self._running:
                self._log(f"Bridge: retrying {uri} in {RECONNECT_DELAY_SECS}s…", "info")
                await asyncio.sleep(RECONNECT_DELAY_SECS)

    # ── peer session ──────────────────────────────────────────────────────────

    async def _handle_peer(self, ws, secret: str,
                           _is_server_side: bool = False,
                           peer_label: str | None = None):
        """
        Manages a single peer WebSocket connection.
        Runs the hello handshake, then the recv/ping loops concurrently.
        """
        addr = peer_label or str(ws.remote_address)

        # Handshake: send HELLO, wait for HELLO back
        node_name = self._radio.node_name if self._radio else "unknown"
        hello = _make_frame(FrameType.HELLO,
                            {"node": node_name},
                            origin=node_name, secret=secret)
        await ws.send(hello)

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        except asyncio.TimeoutError:
            self._log(f"Bridge: {addr} hello timeout", "warn")
            return

        frame = _parse_frame(raw)
        if not frame or frame["type"] != FrameType.HELLO:
            self._log(f"Bridge: {addr} bad hello — disconnecting", "warn")
            return

        if secret and frame.get("secret") != secret:
            self._log(f"Bridge: {addr} wrong secret — disconnecting", "warn")
            return

        peer_node = frame.get("payload", {}).get("node", addr)
        display   = f"{peer_node}@{addr}"
        self._log(f"Bridge: peer connected [{display}]", "ok")

        with self._peers_lock:
            self._peers[display] = ws
        self._emit_bridge_status()

        try:
            recv_task = asyncio.create_task(
                self._recv_loop(ws, display, secret))
            ping_task = asyncio.create_task(
                self._ping_loop(ws, display, secret))
            _, pending = await asyncio.wait(
                [recv_task, ping_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
        finally:
            with self._peers_lock:
                self._peers.pop(display, None)
            self._emit_bridge_status()
            self._log(f"Bridge: peer disconnected [{display}]", "warn")

    async def _recv_loop(self, ws, display: str, secret: str):
        async for raw in ws:
            if not self._running:
                break
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if len(raw) > MAX_FRAME_BYTES:
                continue
            frame = _parse_frame(raw)
            if frame is None:
                continue
            if secret and frame.get("secret") != secret:
                continue
            await self._process_incoming(frame, source_display=display)

    async def _ping_loop(self, ws, _display: str, secret: str):
        node_name = self._radio.node_name if self._radio else "unknown"
        while self._running:
            await asyncio.sleep(PING_INTERVAL_SECS)
            try:
                ping = _make_frame(FrameType.PING,
                                   {"ts": time.time()},
                                   origin=node_name, secret=secret)
                await ws.send(ping)
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception:
                break

    # ── incoming frame processing ─────────────────────────────────────────────

    async def _process_incoming(self, frame: dict,
                                source_display: str) -> None:
        """Validate, deduplicate, and dispatch an incoming bridged frame."""
        ftype   = frame.get("type")
        msg_id  = frame.get("id", "")
        origin  = frame.get("origin", "")
        hops    = int(frame.get("hops", 0))
        payload = frame.get("payload", {})

        # Drop pings/pongs silently
        if ftype in (FrameType.PING, FrameType.PONG):
            return

        # Drop if too many hops
        if hops >= MAX_BRIDGE_HOPS:
            return

        # Deduplicate
        if self._dedup.seen(msg_id):
            return

        # Never re-inject messages that originated here
        own_name = self._radio.node_name if self._radio else ""
        if origin == own_name:
            return

        # Forward to other connected peers (mesh relay)
        await self._relay_to_peers(frame, skip_display=source_display)

        # Inject into local network
        if ftype == FrameType.CHANNEL_MSG:
            await self._inject_channel(payload, origin)
        elif ftype == FrameType.CONTACT_UPD:
            await self._inject_contact(payload)

    async def _relay_to_peers(self, frame: dict,
                               skip_display: str) -> None:
        """Forward a frame to all connected peers except the one it came from."""
        relay_frame = dict(frame)
        relay_frame["hops"] = int(relay_frame.get("hops", 0)) + 1
        raw = json.dumps(relay_frame)

        with self._peers_lock:
            targets = {k: v for k, v in self._peers.items()
                       if k != skip_display}

        for _peer, ws in targets.items():
            try:
                await ws.send(raw)
            except Exception:
                pass

    async def _inject_channel(self, payload: dict, origin: str) -> None:
        """Emit a channel message from a remote node onto the local bus."""
        sender = payload.get("sender", origin)
        text   = payload.get("text", "")
        ts     = float(payload.get("ts", time.time()))
        if not text:
            return
        # Prefix so users can tell it's from a remote network
        prefixed = f"[{origin}] {text}"
        self._bus.emit(EV_MSG_CHANNEL,
                       sender=f"⟷{sender}",
                       text=prefixed,
                       ts=ts,
                       hops=None)
        self._log(f"Bridge RX channel [{origin}] {sender}: {text[:40]}", "debug")

        # Inject onto local LoRa channel only if the setting permits it
        inject = self._settings.get("bridge_inject_radio", True)
        if inject and self._radio and self._radio.online:
            try:
                self._radio.transmit_channel(f"[{origin}] {sender}: {text}")
            except Exception:
                pass

    async def _inject_contact(self, payload: dict) -> None:
        """
        Update or insert a remote contact into the local radio's contact cache.
        This allows bridged GPS/telemetry to appear on the local Map tab.
        """
        if not self._radio:
            return
        from radio import Contact
        name = payload.get("name", "")
        key  = payload.get("key", name[:16] if name else "bridge")
        if not name:
            return

        c = Contact(
            key       = f"bridge:{key[:12]}",
            name      = f"⟷{name}",
            last_heard= float(payload.get("last_heard", time.time())),
            rssi      = payload.get("rssi"),
            snr       = payload.get("snr"),
            lat       = payload.get("lat"),
            lon       = payload.get("lon"),
            battery   = payload.get("battery"),
        )
        self._radio.upsert_contact(c)
        self._bus.emit(EV_CONTACTS_UPD)

    # ── local → bridge outbox ─────────────────────────────────────────────────

    def _register_local_handlers(self):
        if self._local_handlers_registered:
            return
        self._bus.on(EV_MSG_CHANNEL, self._on_local_channel)
        self._local_handlers_registered = True

    def _unregister_local_handlers(self):
        if not self._local_handlers_registered:
            return
        self._bus.off(EV_MSG_CHANNEL, self._on_local_channel)
        self._local_handlers_registered = False

    def _on_local_channel(self, **kw) -> None:
        """Called when a channel message arrives on the local radio."""
        if not self._running:
            return
        # Don't bridge messages that came from another bridge instance
        sender = kw.get("sender", "")
        if sender.startswith("⟷"):
            return
        payload = {
            "sender": sender,
            "text":   kw.get("text", ""),
            "ts":     kw.get("ts", time.time()),
        }
        self._broadcast_async(FrameType.CHANNEL_MSG, payload)

    def broadcast_contact(self, contact) -> None:
        """
        Called by AppWindow periodically to broadcast local contact telemetry.
        Only fires if bridge is running and contact has data worth sharing.
        """
        if not self._running:
            return
        if not any([contact.rssi, contact.snr, contact.lat,
                    contact.battery, contact.last_heard]):
            return
        payload = {
            "name":       contact.name,
            "key":        contact.key,
            "rssi":       contact.rssi,
            "snr":        contact.snr,
            "lat":        contact.lat,
            "lon":        contact.lon,
            "battery":    contact.battery,
            "last_heard": contact.last_heard,
        }
        self._broadcast_async(FrameType.CONTACT_UPD, payload)

    def _broadcast_async(self, ftype: FrameType, payload: dict) -> None:
        """
        Submit a broadcast to the background loop without blocking.
        Safe to call from any thread including the bridge loop itself.
        """
        if not self._loop or not self._loop.is_running():
            return
        secret    = self._settings.get("bridge_secret", "")
        node_name = self._radio.node_name if self._radio else "unknown"
        raw       = _make_frame(ftype, payload,
                                origin=node_name, secret=secret)
        # Register the UUID so we don't echo back our own messages
        frame = json.loads(raw)
        self._dedup.seen(frame["id"])
        # run_coroutine_threadsafe is non-blocking: it enqueues and returns.
        # Safe even when called from the bridge loop thread itself because
        # the submitted coroutine runs after the current call chain completes.
        asyncio.run_coroutine_threadsafe(
            self._send_to_all(raw), self._loop)

    async def _send_to_all(self, raw: str) -> None:
        with self._peers_lock:
            targets = dict(self._peers)
        for _peer, ws in targets.items():
            try:
                await ws.send(raw)
            except Exception:
                pass

    # ── helpers ───────────────────────────────────────────────────────────────

    def _emit_bridge_status(self):
        n = self.peer_count()
        self._bus.emit(EV_BRIDGE_STATUS,
                       peers=self.peer_list(),
                       running=self._running)
        self._bus.emit(EV_LOG,
                       text=f"Bridge peers: {n} connected",
                       level="ok" if n else "info")

    def _log(self, text: str, level: str = "info"):
        self._bus.emit(EV_LOG, text=f"[Bridge] {text}", level=level)
