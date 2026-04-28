"""
radio.py — NodeRadio: async MeshCore device manager
MeshCore Node Manager  |  Original work

Manages the connection to a MeshCore companion radio node via the
`meshcore` Python library.  All device I/O is async; a background
asyncio event loop runs in a daemon thread.  All public methods are
safe to call from any thread.

Communication with the rest of the application is entirely through the
EventBus — NodeRadio never calls GUI code directly.

MeshCore firmware notes
-----------------------
* The Python companion API does not expose a writable config tree.
  Radio parameters (frequency, SF, BW, power) must be changed via the
  device button UI or the TerminalCLI channel command.
* Broadcast uses send_msg(None, text).  This works on dt267 ≥ v1.13
  and meshcomod firmware.  A TypeError is caught and reported if the
  build does not support it.
* Serial port deactivates after 30 s idle on dt267 firmware; TCP is
  recommended for persistent desktop use.
"""

import asyncio
import gc
import json
import threading
import time
from dataclasses import dataclass, field

from config import ACK_TIMEOUT_SECS, BLE_SCAN_SECONDS, HISTORY_LIMIT
from events import (
    EventBus,
    EV_CONNECTED, EV_DISCONNECTED, EV_CONN_ERROR,
    EV_CONTACTS_UPD,
    EV_MSG_CHANNEL, EV_MSG_DIRECT, EV_MSG_SENT,
    EV_MSG_DELIVERED, EV_MSG_TIMEOUT,
    EV_LOG,
)
from helpers import pubkey_short, normalise_key, ts_to_iso

# ── optional third-party imports ─────────────────────────────────────────────
try:
    from meshcore import MeshCore, EventType
    _MC_OK = True
except ImportError:
    MeshCore = None
    EventType = None
    _MC_OK = False

try:
    from bleak import BleakScanner
    _BLE_OK = True
except ImportError:
    BleakScanner = None
    _BLE_OK = False


# ── data classes ─────────────────────────────────────────────────────────────

@dataclass
class Contact:
    """Normalised representation of a MeshCore contact."""
    key:        str          # pubkey_short string used as unique ID
    name:       str
    last_heard: float | None = None
    snr:        float | None = None
    rssi:       float | None = None
    lat:        float | None = None
    lon:        float | None = None
    battery:    int   | None = None
    raw:        object       = field(default=None, repr=False)


@dataclass
class Message:
    """A single sent or received message."""
    local_id:      int
    direction:     str        # "tx" | "rx"
    kind:          str        # "channel" | "direct"
    peer:          str        # sender name (rx) or dest name (tx)
    text:          str
    ts_sent:       float | None = None
    ts_received:   float | None = None
    ts_delivered:  float | None = None
    rtt:           float | None = None
    status:        str = "unknown"  # sent|pending|delivered|timeout|received — always set explicitly


# ── NodeRadio ─────────────────────────────────────────────────────────────────

class NodeRadio:
    """
    Connects to a MeshCore companion radio and relays events to the bus.

    Connection states
    -----------------
    idle → connecting → online → idle  (on disconnect)
                    ↘ idle             (on error)
    """

    def __init__(self, bus: EventBus):
        self._bus = bus

        # device state
        self._mc = None
        self._online      = False
        self._conn_type   = ""
        self.node_name    = ""
        self.device_info: dict = {}

        # contacts  { key_str: Contact }
        self._contacts: dict[str, Contact] = {}
        self._ct_lock = threading.Lock()

        # message store
        self._msg_lock  = threading.Lock()
        self._history:  list[Message]      = []
        self._pending:  dict[int, Message] = {}   # local_id → Message
        self._id_ctr    = 0

        # async loop
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread             | None = None
        self._fetch_task = None
        self._sub_token  = None

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def online(self) -> bool:
        return self._online

    @property
    def conn_type(self) -> str:
        return self._conn_type

    # ── loop management ───────────────────────────────────────────────────────

    def _start_loop(self):
        if self._loop and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="mc-radio"
        )
        self._thread.start()
        time.sleep(0.05)   # allow run_forever to settle

    def _submit(self, coro, timeout: float = 20.0):
        """Submit coroutine to the background loop; block until done."""
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("Radio loop not running")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    def _stop_loop(self):
        loop, thread = self._loop, self._thread
        self._loop = self._thread = None
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive():
            thread.join(timeout=3.0)

    # ── connect / disconnect ──────────────────────────────────────────────────

    def connect_serial(self, port: str) -> bool:
        self._conn_type = "Serial"
        return self._connect(lambda: MeshCore.create_serial(port))

    def connect_tcp(self, host: str, port: int = 4403) -> bool:
        self._conn_type = "TCP"
        return self._connect(lambda: MeshCore.create_tcp(host, port))

    def connect_ble(self, address: str) -> bool:
        self._conn_type = "BLE"
        return self._connect(lambda: MeshCore.create_ble(address))

    def _connect(self, factory) -> bool:
        if not _MC_OK:
            self._emit_log("meshcore library missing — pip install meshcore", "err")
            return False
        if self._online:
            self._emit_log("Already connected", "warn")
            return False
        try:
            self._start_loop()
            self._mc = self._submit(factory(), timeout=30.0)
            self._submit(self._setup())
            return True
        except Exception as exc:
            self._bus.emit(EV_CONN_ERROR, message=str(exc))
            self._emit_log(f"Connection failed: {exc}", "err")
            self._stop_loop()
            return False

    async def _setup(self):
        """Post-connect initialisation — runs on the background loop."""
        result = await self._mc.commands.send_device_query()
        if result.type != EventType.ERROR:
            self.device_info = result.payload or {}
        self.node_name = self.device_info.get("name", "unknown")

        await self._load_contacts()

        self._sub_token  = self._mc.subscribe(self._on_mc_event)
        self._fetch_task = self._loop.create_task(self._mc.auto_fetch_msgs(delay=5))

        self._online = True
        self._bus.emit(EV_CONNECTED, conn_type=self._conn_type, node_name=self.node_name)
        self._emit_log(f"Online [{self._conn_type}] — {self.node_name}", "ok")

    def disconnect(self):
        if not self._online and self._loop is None and self._mc is None:
            return
        self._emit_log("Disconnecting…", "info")
        try:
            if self._loop and self._loop.is_running() and self._mc:
                if self._fetch_task:
                    self._loop.call_soon_threadsafe(self._fetch_task.cancel)
                if self._sub_token is not None:
                    try:
                        self._mc.unsubscribe(self._sub_token)
                    except Exception:
                        pass
                try:
                    self._submit(self._mc.disconnect(), timeout=5.0)
                except Exception:
                    pass
        except Exception as exc:
            self._emit_log(f"Disconnect warning: {exc}", "warn")
        finally:
            self._mc = self._fetch_task = self._sub_token = None
            self._online = False
            with self._ct_lock:
                self._contacts.clear()
            with self._msg_lock:
                self._pending.clear()
            self._stop_loop()
            gc.collect()
            self._bus.emit(EV_DISCONNECTED)
            self._emit_log("Offline", "info")

    # ── ping ──────────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Re-query device info to confirm connection is alive."""
        if not self._mc or not self._online:
            return False
        try:
            result = self._submit(self._mc.commands.send_device_query(), timeout=8.0)
            alive = result.type != EventType.ERROR
            if alive:
                self.device_info = result.payload or self.device_info
                self._emit_log("Ping OK", "ok")
            else:
                self._emit_log("Ping: no response", "warn")
            return alive
        except Exception as exc:
            self._emit_log(f"Ping error: {exc}", "err")
            return False

    # ── BLE scan ──────────────────────────────────────────────────────────────

    def scan_ble(self, timeout: float = BLE_SCAN_SECONDS) -> list[dict]:
        """
        Discover nearby BLE devices.  Returns list of dicts:
        {name, address, rssi, is_mc}  MeshCore devices sorted first.
        Safe to call before connecting.
        """
        if not _BLE_OK:
            self._emit_log("bleak not installed — pip install bleak", "err")
            return []
        already = self._loop is not None and self._loop.is_running()
        if not already:
            self._start_loop()
        try:
            return self._submit(self._ble_scan_async(timeout), timeout=timeout + 3)
        except Exception as exc:
            self._emit_log(f"BLE scan error: {exc}", "err")
            return []
        finally:
            if not already and not self._online:
                self._stop_loop()

    async def _ble_scan_async(self, timeout: float) -> list[dict]:
        found = await BleakScanner.discover(timeout=timeout)
        out = []
        for d in found:
            nm = d.name or ""
            out.append({
                "name":    nm or "(unknown)",
                "address": d.address,
                "rssi":    getattr(d, "rssi", "?"),
                "is_mc":   nm.startswith("MeshCore"),
            })
        out.sort(key=lambda x: (not x["is_mc"], x["name"].lower()))
        return out

    # ── contacts ─────────────────────────────────────────────────────────────

    async def _load_contacts(self):
        result = await self._mc.commands.get_contacts()
        if result.type == EventType.ERROR:
            return
        raw = result.payload or {}
        contacts = {}
        for k, v in raw.items():
            c = self._build_contact(k, v)
            contacts[c.key] = c
        with self._ct_lock:
            self._contacts = contacts
        self._bus.emit(EV_CONTACTS_UPD)

    def refresh_contacts(self):
        """Reload contacts from device (blocking, safe for background thread)."""
        if self._online:
            self._submit(self._load_contacts())

    def get_contacts(self) -> list[Contact]:
        """Return a snapshot of all contacts, sorted by name."""
        with self._ct_lock:
            return sorted(self._contacts.values(), key=lambda c: c.name.lower())

    def get_contact_names(self) -> list[str]:
        with self._ct_lock:
            return sorted(c.name for c in self._contacts.values() if c.name)

    def remove_contact(self, key: str) -> bool:
        """Remove a contact from the local cache by key or name."""
        needle = normalise_key(key)
        if not needle:
            return False
        with self._ct_lock:
            for k in list(self._contacts):
                if normalise_key(k) == needle or \
                   normalise_key(self._contacts[k].name) == needle:
                    del self._contacts[k]
                    self._emit_log(f"Removed contact: {key}", "info")
                    return True
        self._emit_log(f"Contact not found: {key}", "warn")
        return False

    def _find_raw_contact(self, name_or_key: str):
        """Return the raw contact object for send_msg, or None."""
        needle = normalise_key(name_or_key)
        with self._ct_lock:
            for c in self._contacts.values():
                if normalise_key(c.key) == needle or \
                   normalise_key(c.name) == needle:
                    return c.raw
        return None

    @staticmethod
    def _build_contact(raw_key, raw_val) -> "Contact":
        key = pubkey_short(raw_key) if isinstance(raw_key, (bytes, bytearray)) \
              else str(raw_key)[:16]
        if isinstance(raw_val, dict):
            name  = raw_val.get("adv_name", raw_val.get("name", key))
            lh    = raw_val.get("last_heard")
            snr   = raw_val.get("last_snr")
            rssi  = raw_val.get("last_rssi")
            lat   = raw_val.get("adv_lat")
            lon   = raw_val.get("adv_lon")
            batt  = raw_val.get("battery")
        else:
            name  = getattr(raw_val, "adv_name", getattr(raw_val, "name", key))
            lh    = getattr(raw_val, "last_heard", None)
            snr   = getattr(raw_val, "last_snr",   None)
            rssi  = getattr(raw_val, "last_rssi",  None)
            lat   = getattr(raw_val, "adv_lat",    None)
            lon   = getattr(raw_val, "adv_lon",    None)
            batt  = getattr(raw_val, "battery",    None)
        return Contact(key=key, name=name, last_heard=lh, snr=snr, rssi=rssi,
                       lat=lat, lon=lon, battery=batt, raw=raw_val)

    # ── radio / device info ───────────────────────────────────────────────────

    def radio_params(self) -> dict:
        d = self.device_info
        return {
            "Frequency (MHz)":   d.get("radio_freq"),
            "Bandwidth (kHz)":   d.get("radio_bw"),
            "Spreading Factor":  d.get("radio_sf"),
            "Coding Rate":       d.get("radio_cr"),
            "TX Power (dBm)":    d.get("tx_power"),
        }

    def live_stats(self) -> dict:
        """Fetch real-time device stats.  Returns {} if unsupported."""
        if not self._mc or not self._online:
            return {}
        try:
            r = self._submit(self._mc.commands.get_stats(), timeout=5.0)
            return r.payload or {} if r.type != EventType.ERROR else {}
        except Exception:
            return {}

    # ── send ─────────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._id_ctr += 1
        return (int(time.time() * 1000) + self._id_ctr) & 0xFFFF_FFFF

    def transmit_channel(self, text: str) -> int | None:
        """Broadcast to public channel.  Returns local_id or None on failure."""
        if not self._online or not text.strip():
            return None
        lid = self._next_id()
        try:
            try:
                self._submit(self._mc.commands.send_msg(None, text))
            except TypeError:
                self._emit_log(
                    "Broadcast failed — firmware may not support send_msg(None, text). "
                    "Upgrade to dt267 v1.13+.", "err")
                return None
            msg = Message(local_id=lid, direction="tx", kind="channel",
                          peer="channel", text=text,
                          ts_sent=time.time(), status="sent")
            with self._msg_lock:
                self._history.append(msg)
            self._bus.emit(EV_MSG_SENT, local_id=lid)
            self._emit_log(f"Broadcast sent id={lid}", "info")
            return lid
        except Exception as exc:
            self._emit_log(f"Broadcast error: {exc}", "err")
            return None

    def transmit_direct(self, dest: str, text: str,
                        ack: bool = True) -> int | None:
        """Send a direct message.  Returns local_id or None on failure."""
        if not self._online or not text.strip() or not dest.strip():
            return None
        raw = self._find_raw_contact(dest)
        if raw is None:
            self._emit_log(f"Contact not found: '{dest}' — refresh contacts?", "err")
            return None
        lid = self._next_id()
        try:
            self._submit(self._mc.commands.send_msg(raw, text))
            msg = Message(local_id=lid, direction="tx", kind="direct",
                          peer=dest, text=text,
                          ts_sent=time.time(),
                          status="pending" if ack else "sent")
            with self._msg_lock:
                self._history.append(msg)
                if ack:
                    self._pending[lid] = msg
            self._bus.emit(EV_MSG_SENT, local_id=lid)
            self._emit_log(f"DM sent id={lid} → {dest}", "info")
            return lid
        except Exception as exc:
            self._emit_log(f"DM error: {exc}", "err")
            return None

    # ── ACK timeout sweep ─────────────────────────────────────────────────────

    def sweep_timeouts(self, timeout: float = ACK_TIMEOUT_SECS) -> int:
        """Expire stale pending ACKs.  Returns count expired.  Call periodically."""
        now     = time.time()
        expired = []
        with self._msg_lock:
            for lid, msg in list(self._pending.items()):
                if msg.ts_sent and now - msg.ts_sent > timeout:
                    expired.append((lid, msg))
        for lid, msg in expired:
            msg.status = "timeout"
            with self._msg_lock:
                self._pending.pop(lid, None)
            self._bus.emit(EV_MSG_TIMEOUT, local_id=lid)
            self._emit_log(f"ACK timeout id={lid}", "warn")
        return len(expired)

    # ── incoming event handler ────────────────────────────────────────────────

    def _on_mc_event(self, event):
        """Called from the background loop by mc.subscribe."""
        if not _MC_OK or EventType is None:
            return
        try:
            et = getattr(event, "type", None)
            pl = getattr(event, "payload", None)
            if et == EventType.CONTACT_MSG_RECV:
                self._rx_direct(pl)
            elif et == EventType.CHANNEL_MSG_RECV:
                self._rx_channel(pl)
            elif et == EventType.MSG_SENT:
                self._advance_pending(pl)
            elif et == EventType.ACK:
                self._confirm_delivery(pl)
        except Exception as exc:
            self._emit_log(f"Event handler error: {exc}", "err")

    def _rx_channel(self, payload):
        sender, text = self._split_payload(payload)
        if not text:
            return
        now = time.time()
        msg = Message(local_id=self._next_id(), direction="rx", kind="channel",
                      peer=sender, text=text, ts_received=now, status="received")
        with self._msg_lock:
            self._history.append(msg)
        self._bus.emit(EV_MSG_CHANNEL, sender=sender, text=text, ts=now)
        self._emit_log(f"Channel [{sender}]: {text}", "info")

    def _rx_direct(self, payload):
        sender, text = self._split_payload(payload)
        if not text:
            return
        now = time.time()
        msg = Message(local_id=self._next_id(), direction="rx", kind="direct",
                      peer=sender, text=text, ts_received=now, status="received")
        with self._msg_lock:
            self._history.append(msg)
        self._bus.emit(EV_MSG_DIRECT, sender=sender, text=text, ts=now)
        self._emit_log(f"DM [{sender}]: {text}", "info")

    def _advance_pending(self, _payload):
        """Device confirmed transmission — advance first PENDING msg to SENT."""
        with self._msg_lock:
            for msg in self._pending.values():
                if msg.status == "pending":
                    msg.status = "sent"
                    break

    def _confirm_delivery(self, _payload):
        """Device received an ACK — confirm delivery for best candidate."""
        now  = time.time()
        best = None
        best_diff = float("inf")
        with self._msg_lock:
            for lid, msg in self._pending.items():
                if msg.ts_sent is None:
                    continue
                diff    = now - msg.ts_sent
                is_sent = msg.status == "sent"
                if diff > ACK_TIMEOUT_SECS + 5:
                    continue
                # Prefer SENT over PENDING; then smallest diff
                if best is None or \
                   (is_sent and self._pending[best].status != "sent") or \
                   (is_sent == (self._pending[best].status == "sent") and diff < best_diff):
                    best, best_diff = lid, diff
        if best is not None:
            self._finalise_delivery(best)

    def _finalise_delivery(self, lid: int):
        with self._msg_lock:
            msg = self._pending.pop(lid, None)
        if msg is None:
            return
        now = time.time()
        msg.ts_delivered = now
        msg.rtt          = now - msg.ts_sent if msg.ts_sent else None
        msg.status       = "delivered"
        self._bus.emit(EV_MSG_DELIVERED, local_id=lid, rtt=msg.rtt)
        self._emit_log(
            f"ACK confirmed id={lid} rtt={msg.rtt:.1f}s" if msg.rtt else
            f"ACK confirmed id={lid}", "ok")

    # ── message store ─────────────────────────────────────────────────────────

    def message_history(self, limit: int = HISTORY_LIMIT) -> list[Message]:
        """Return a thread-safe snapshot, oldest first, capped at limit."""
        with self._msg_lock:
            snap = list(self._history)
        snap.sort(key=lambda m: m.ts_received or m.ts_sent or 0)
        return snap[-limit:]

    def pending_count(self) -> int:
        with self._msg_lock:
            return len(self._pending)

    def message_stats(self) -> dict:
        with self._msg_lock:
            hist = list(self._history)
            pend = len(self._pending)
        tx        = [m for m in hist if m.direction == "tx"]
        delivered = [m for m in tx if m.status == "delivered"]
        timed_out = [m for m in tx if m.status == "timeout"]
        rx        = [m for m in hist if m.direction == "rx"]
        rtts      = [m.rtt for m in delivered if m.rtt]
        return {
            "total":     len(hist),
            "tx":        len(tx),
            "rx":        len(rx),
            "delivered": len(delivered),
            "timeout":   len(timed_out),
            "pending":   pend,
            "avg_rtt":   sum(rtts) / len(rtts) if rtts else 0.0,
            "success":   len(delivered) / len(tx) * 100 if tx else 0.0,
        }

    def clear_history(self):
        with self._msg_lock:
            self._history.clear()
            self._pending.clear()
        self._emit_log("Message history cleared", "info")

    # ── export ────────────────────────────────────────────────────────────────

    def export_messages(self, path: str) -> bool:
        """Write full message history to a plain-text file."""
        try:
            hist = self.message_history(limit=10_000)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("MeshCore Node Manager — Message Export\n")
                fh.write(f"Node: {self.node_name}\n")
                fh.write(f"Exported: {ts_to_iso(time.time())}\n")
                fh.write("─" * 56 + "\n\n")
                for m in hist:
                    ts    = m.ts_received or m.ts_sent
                    arrow = "→" if m.direction == "tx" else "←"
                    line  = (f"[{ts_to_iso(ts)}] {m.kind:7s} "
                             f"{arrow} {m.peer}: {m.text}")
                    if m.status not in ("sent", "received"):
                        line += f"  [{m.status}]"
                    fh.write(line + "\n")
            self._emit_log(f"Exported to {path}", "ok")
            return True
        except Exception as exc:
            self._emit_log(f"Export failed: {exc}", "err")
            return False

    # ── backup / restore ──────────────────────────────────────────────────────

    def save_backup(self, path: str) -> bool:
        try:
            payload = {
                "node_name":    self.node_name,
                "device_info":  self.device_info,
                "radio":        self.radio_params(),
                "saved_at":     ts_to_iso(time.time()),
            }
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            self._emit_log(f"Backup saved to {path}", "ok")
            return True
        except Exception as exc:
            self._emit_log(f"Backup failed: {exc}", "err")
            return False

    def load_backup(self, path: str) -> dict | None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._emit_log(f"Backup loaded from {path}", "ok")
            return data
        except Exception as exc:
            self._emit_log(f"Load backup failed: {exc}", "err")
            return None

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _split_payload(payload) -> tuple[str, str]:
        if isinstance(payload, dict):
            sender = payload.get("sender_prefix", payload.get("sender", "?"))
            text   = payload.get("text", "")
        else:
            sender = "?"
            text   = str(payload) if payload else ""
        return sender, text

    def _emit_log(self, text: str, level: str = "info"):
        self._bus.emit(EV_LOG, text=text, level=level)
