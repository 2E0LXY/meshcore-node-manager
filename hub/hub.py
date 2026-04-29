#!/usr/bin/env python3
"""
hub.py — MeshCore Bridge Hub
MeshCore Node Manager  |  Original work

A centralised WebSocket relay hub that multiple Node Manager instances
connect to, eliminating the need for any port-forwarding on client machines.
Caddy sits in front and provides TLS (HTTPS/WSS) automatically.

Architecture
------------

  Node Manager A ──┐
  Node Manager B ──┤──► Caddy (TLS) ──► hub.py :9000 (WebSocket relay)
  Node Manager C ──┘                         │
                                              └──► :9001 (Web dashboard)

All clients connect as WebSocket clients to the hub. The hub:
  1. Authenticates each client via the shared secret in the HELLO frame
  2. Relays channel_msg and contact_upd frames between all connected clients
  3. Enforces deduplication and hop-count limits
  4. Serves a live web dashboard on a second port showing:
       - Connected clients (name, IP, connected-for, messages sent/received)
       - Real-time message feed (last 200 frames)
       - Aggregate traffic statistics

Usage
-----
  python hub.py [--ws-port 9000] [--web-port 9001] [--secret mypassword]

  Or with environment variables:
    HUB_SECRET=mypassword  HUB_WS_PORT=9000  HUB_WEB_PORT=9001  python hub.py

  Then configure Caddy (see Caddyfile in this directory).
  Each Node Manager sets a single peer: wss://yourdomain.com/hub

Dependencies
------------
  pip install websockets

No other dependencies. Runs on Python 3.10+.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass, field

try:
    import websockets
    import websockets.server
    import websockets.exceptions
except ImportError:
    print("ERROR: websockets not installed.  Run:  pip install websockets")
    sys.exit(1)

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("hub")

# ── constants ─────────────────────────────────────────────────────────────────
PROTOCOL_VERSION = 1
MAX_BRIDGE_HOPS  = 3
DEDUP_TTL_SECS   = 300
MAX_FRAME_BYTES  = 65_536
FEED_MAXLEN      = 200     # max raw frames kept for dashboard
PING_INTERVAL    = 30      # seconds between hub→client pings


# ── deduplication ─────────────────────────────────────────────────────────────

class DedupeCache:
    def __init__(self, ttl: float = DEDUP_TTL_SECS):
        self._ttl  = ttl
        self._seen: OrderedDict[str, float] = OrderedDict()

    def seen(self, msg_id: str) -> bool:
        now = time.time()
        self._expire(now)
        if msg_id in self._seen:
            return True
        self._seen[msg_id] = now
        return False

    def _expire(self, now: float):
        cutoff = now - self._ttl
        while self._seen:
            k, v = next(iter(self._seen.items()))
            if v < cutoff:
                del self._seen[k]
            else:
                break


# ── client record ─────────────────────────────────────────────────────────────

@dataclass
class Client:
    ws:           object
    addr:         str          # remote IP:port
    node_name:    str = ""
    connected_at: float = field(default_factory=time.time)
    tx:           int = 0      # frames sent TO this client
    rx:           int = 0      # frames received FROM this client
    last_rx:      float = field(default_factory=time.time)

    @property
    def connected_for(self) -> str:
        secs = int(time.time() - self.connected_at)
        h, rem = divmod(secs, 3600)
        m, s   = divmod(rem, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def to_dict(self) -> dict:
        return {
            "node":          self.node_name or self.addr,
            "addr":          self.addr,
            "connected_for": self.connected_for,
            "tx":            self.tx,
            "rx":            self.rx,
            "last_rx":       time.strftime("%H:%M:%S",
                                           time.localtime(self.last_rx)),
        }


# ── hub ───────────────────────────────────────────────────────────────────────

class Hub:
    def __init__(self, secret: str):
        self._secret  = secret
        self._clients: dict[str, Client] = {}   # addr → Client
        self._lock    = asyncio.Lock()
        self._dedup   = DedupeCache()
        self._feed: deque[dict] = deque(maxlen=FEED_MAXLEN)
        self._stats = {
            "total_rx":       0,
            "total_relayed":  0,
            "total_dropped":  0,
            "started_at":     time.time(),
        }

    # ── WebSocket server handler ──────────────────────────────────────────────

    async def handle_client(self, ws) -> None:
        addr = f"{ws.remote_address[0]}:{ws.remote_address[1]}"
        client = Client(ws=ws, addr=addr)
        log.info("New connection from %s", addr)

        # ── handshake ────────────────────────────────────────────────────────
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        except asyncio.TimeoutError:
            log.warning("%s  hello timeout", addr)
            return
        except websockets.exceptions.ConnectionClosed:
            return

        frame = self._parse(raw)
        if not frame or frame.get("type") != "hello":
            log.warning("%s  bad hello frame", addr)
            return

        if self._secret and frame.get("secret") != self._secret:
            log.warning("%s  wrong secret", addr)
            await ws.close(1008, "wrong secret")
            return

        client.node_name = frame.get("payload", {}).get("node", addr)
        log.info("%s  authenticated as [%s]", addr, client.node_name)

        # Send hello back
        hello_back = self._make_frame("hello",
                                      {"node": "hub", "version": PROTOCOL_VERSION})
        await ws.send(hello_back)

        async with self._lock:
            self._clients[addr] = client

        self._feed_append({
            "ts":   time.strftime("%H:%M:%S"),
            "dir":  "←",
            "from": client.node_name,
            "type": "hello",
            "text": f"[{client.node_name}] connected from {addr}",
        })

        # ── session ───────────────────────────────────────────────────────────
        try:
            recv_task = asyncio.create_task(self._recv_loop(client))
            ping_task = asyncio.create_task(self._ping_loop(client))
            _, pending = await asyncio.wait(
                [recv_task, ping_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
        finally:
            async with self._lock:
                self._clients.pop(addr, None)
            log.info("%s  [%s] disconnected", addr, client.node_name)
            self._feed_append({
                "ts":   time.strftime("%H:%M:%S"),
                "dir":  "✗",
                "from": client.node_name,
                "type": "disconnect",
                "text": f"[{client.node_name}] disconnected",
            })

    async def _recv_loop(self, client: Client) -> None:
        async for raw in client.ws:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if len(raw) > MAX_FRAME_BYTES:
                continue

            frame = self._parse(raw)
            if not frame:
                continue

            # Validate secret on every frame
            if self._secret and frame.get("secret") != self._secret:
                continue

            client.rx    += 1
            client.last_rx = time.time()
            self._stats["total_rx"] += 1

            ftype  = frame.get("type", "")
            hops   = int(frame.get("hops", 0))
            msg_id = frame.get("id", "")

            # Log to feed
            payload = frame.get("payload", {})
            feed_text = self._feed_text(ftype, frame, payload)
            self._feed_append({
                "ts":   time.strftime("%H:%M:%S"),
                "dir":  "←",
                "from": client.node_name,
                "type": ftype,
                "text": feed_text,
                "raw":  raw[:300],
            })

            # Drop pings (we handle them in ping_loop)
            if ftype in ("ping", "pong"):
                if ftype == "ping":
                    pong = self._make_frame("pong", {"ts": time.time()})
                    try:
                        await client.ws.send(pong)
                    except Exception:
                        pass
                continue

            # Drop if too many hops
            if hops >= MAX_BRIDGE_HOPS:
                self._stats["total_dropped"] += 1
                continue

            # Dedup
            if self._dedup.seen(msg_id):
                self._stats["total_dropped"] += 1
                continue

            # Relay to all other connected clients
            relay_frame = dict(frame)
            relay_frame["hops"] = hops + 1
            relay_raw = json.dumps(relay_frame)

            await self._broadcast(relay_raw, skip_addr=client.addr)

    async def _ping_loop(self, client: Client) -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                ping = self._make_frame("ping", {"ts": time.time()})
                await client.ws.send(ping)
                client.tx += 1
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception:
                break

    async def _broadcast(self, raw: str, skip_addr: str) -> None:
        async with self._lock:
            targets = {a: c for a, c in self._clients.items()
                       if a != skip_addr}
        for _addr, client in targets.items():
            try:
                await client.ws.send(raw)
                client.tx += 1
                self._stats["total_relayed"] += 1

                # Log outbound to feed
                frame = self._parse(raw)
                if frame:
                    ftype   = frame.get("type", "")
                    payload = frame.get("payload", {})
                    self._feed_append({
                        "ts":   time.strftime("%H:%M:%S"),
                        "dir":  "→",
                        "from": frame.get("origin", "?"),
                        "to":   client.node_name,
                        "type": ftype,
                        "text": self._feed_text(ftype, frame, payload),
                    })
            except Exception:
                pass

    # ── web dashboard ─────────────────────────────────────────────────────────

    async def handle_web(self, ws) -> None:
        """
        Simple JSON streaming endpoint for the dashboard.
        Sends a state snapshot every 2 seconds.
        """
        try:
            while True:
                async with self._lock:
                    clients = [c.to_dict() for c in self._clients.values()]
                uptime = int(time.time() - self._stats["started_at"])
                h, rem = divmod(uptime, 3600)
                m, s   = divmod(rem, 60)
                payload = {
                    "type":    "state",
                    "ts":      time.strftime("%Y-%m-%d %H:%M:%S"),
                    "uptime":  f"{h:02d}:{m:02d}:{s:02d}",
                    "clients": clients,
                    "stats":   dict(self._stats),
                    "feed":    list(self._feed)[-50:],
                }
                await ws.send(json.dumps(payload))
                await asyncio.sleep(2)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as exc:
            log.debug("Dashboard WS error: %s", exc)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _parse(self, raw: str) -> "dict | None":
        try:
            f = json.loads(raw)
            return f if isinstance(f, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    def _make_frame(self, ftype: str, payload: dict) -> str:
        return json.dumps({
            "v":       PROTOCOL_VERSION,
            "id":      str(uuid.uuid4()),
            "origin":  "hub",
            "hops":    0,
            "secret":  self._secret,
            "type":    ftype,
            "payload": payload,
        })

    def _feed_append(self, entry: dict) -> None:
        self._feed.append(entry)

    @staticmethod
    def _feed_text(ftype: str, frame: dict, payload: dict) -> str:
        origin = frame.get("origin", "?")
        if ftype == "channel_msg":
            sender = payload.get("sender", origin)
            text   = payload.get("text", "")
            return f"[{origin}] {sender}: {text[:80]}"
        if ftype == "contact_upd":
            name = payload.get("name", "?")
            rssi = payload.get("rssi", "?")
            lat  = payload.get("lat")
            loc  = f" GPS {lat:.4f},{payload.get('lon',0):.4f}" if lat else ""
            return f"contact [{origin}] {name} RSSI={rssi}{loc}"
        return f"{ftype} from {origin}"


# ── dashboard HTTP/WS handler ─────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MeshCore Bridge Hub</title>
<style>
  :root {
    --bg:      #03060f;
    --bg2:     #060d1a;
    --panel:   #0a1628;
    --border:  #0f2040;
    --text:    #c8e8ff;
    --sub:     #5a8ab0;
    --cyan:    #00f5ff;
    --green:   #39ff8a;
    --yellow:  #ffe040;
    --red:     #ff2060;
    --orange:  #ff8c00;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
  }
  header {
    background: var(--bg2);
    border-bottom: 1px solid var(--cyan);
    padding: 10px 20px;
    display: flex;
    align-items: center;
    gap: 20px;
  }
  header h1 { color: var(--cyan); font-size: 16px; letter-spacing: 2px; }
  .badge {
    padding: 2px 10px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: bold;
  }
  .badge-ok   { background: #0a2a18; color: var(--green); border: 1px solid var(--green); }
  .badge-warn { background: #2a1e00; color: var(--yellow); border: 1px solid var(--yellow); }
  #clock { margin-left: auto; color: var(--sub); font-size: 11px; }

  .grid {
    display: grid;
    grid-template-columns: 340px 1fr;
    grid-template-rows: auto 1fr;
    gap: 8px;
    padding: 8px;
    height: calc(100vh - 48px);
  }

  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 4px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .panel-title {
    padding: 6px 12px;
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    color: var(--sub);
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
  }
  .panel-body { padding: 10px; flex: 1; overflow-y: auto; }

  /* Stats row */
  .stats-grid {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
  }
  .stat-card {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px 14px;
    text-align: center;
  }
  .stat-val { font-size: 22px; font-weight: bold; color: var(--cyan); }
  .stat-lbl { font-size: 10px; color: var(--sub); margin-top: 2px; letter-spacing: 1px; }

  /* Client table */
  table { width: 100%; border-collapse: collapse; }
  th { color: var(--sub); font-size: 10px; text-align: left;
       padding: 4px 8px; border-bottom: 1px solid var(--border); }
  td { padding: 5px 8px; border-bottom: 1px solid var(--border); font-size: 12px; }
  tr:last-child td { border-bottom: none; }
  .dot { display: inline-block; width: 8px; height: 8px;
         border-radius: 50%; background: var(--green);
         box-shadow: 0 0 6px var(--green); margin-right: 6px; }

  /* Feed */
  #feed { font-size: 11px; line-height: 1.7; }
  .feed-row { display: flex; gap: 8px; padding: 2px 0;
              border-bottom: 1px solid #0d1e30; }
  .feed-ts   { color: var(--sub); min-width: 56px; }
  .feed-dir  { min-width: 18px; }
  .feed-dir.in  { color: var(--green); }
  .feed-dir.out { color: var(--cyan); }
  .feed-dir.disc{ color: var(--red); }
  .feed-type { color: var(--orange); min-width: 90px; }
  .feed-text { color: var(--text); overflow: hidden; white-space: nowrap;
               text-overflow: ellipsis; }
  .type-channel_msg { color: var(--green); }
  .type-contact_upd { color: var(--cyan); }
  .type-hello      { color: var(--yellow); }
  .type-disconnect { color: var(--red); }

  #status-dot { width:10px; height:10px; border-radius:50%;
                display:inline-block; background:var(--yellow); margin-right:6px; }
  #status-dot.ok { background:var(--green); box-shadow:0 0 8px var(--green); }
</style>
</head>
<body>
<header>
  <h1>⬡ MESHCORE BRIDGE HUB</h1>
  <span id="conn-badge" class="badge badge-warn">CONNECTING</span>
  <span id="client-badge" class="badge badge-ok">0 CLIENTS</span>
  <span id="clock"></span>
</header>

<div class="grid">
  <!-- Stats row -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-val" id="s-clients">0</div>
      <div class="stat-lbl">CONNECTED</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" id="s-rx">0</div>
      <div class="stat-lbl">FRAMES RX</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" id="s-relayed">0</div>
      <div class="stat-lbl">RELAYED</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" id="s-dropped">0</div>
      <div class="stat-lbl">DROPPED</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" id="s-uptime">00:00:00</div>
      <div class="stat-lbl">UPTIME</div>
    </div>
  </div>

  <!-- Client list -->
  <div class="panel">
    <div class="panel-title">Connected Clients</div>
    <div class="panel-body">
      <table>
        <thead>
          <tr><th>Node</th><th>Address</th><th>Time</th><th>RX</th><th>TX</th><th>Last</th></tr>
        </thead>
        <tbody id="client-table"></tbody>
      </table>
    </div>
  </div>

  <!-- Frame feed -->
  <div class="panel">
    <div class="panel-title">Live Frame Feed</div>
    <div class="panel-body" id="feed-body">
      <div id="feed"></div>
    </div>
  </div>
</div>

<script>
const WS_URL = (location.protocol === 'https:' ? 'wss' : 'ws')
               + '://' + location.host + '/dash';
let ws, reconnectTimer;

function connect() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    document.getElementById('conn-badge').textContent = 'LIVE';
    document.getElementById('conn-badge').className = 'badge badge-ok';
  };
  ws.onclose = () => {
    document.getElementById('conn-badge').textContent = 'RECONNECTING';
    document.getElementById('conn-badge').className = 'badge badge-warn';
    reconnectTimer = setTimeout(connect, 3000);
  };
  ws.onmessage = (evt) => {
    try { update(JSON.parse(evt.data)); } catch(e) {}
  };
}

function update(data) {
  if (data.type !== 'state') return;
  const clients = data.clients || [];
  const stats   = data.stats   || {};

  // Stats
  document.getElementById('s-clients').textContent = clients.length;
  document.getElementById('s-rx').textContent      = stats.total_rx || 0;
  document.getElementById('s-relayed').textContent = stats.total_relayed || 0;
  document.getElementById('s-dropped').textContent = stats.total_dropped || 0;
  document.getElementById('s-uptime').textContent  = data.uptime || '--';
  document.getElementById('client-badge').textContent = clients.length + ' CLIENT' + (clients.length !== 1 ? 'S' : '');

  // Client table
  const tbody = document.getElementById('client-table');
  tbody.innerHTML = clients.map(c =>
    `<tr>
      <td><span class="dot"></span>${esc(c.node)}</td>
      <td>${esc(c.addr)}</td>
      <td>${esc(c.connected_for)}</td>
      <td>${c.rx}</td>
      <td>${c.tx}</td>
      <td>${esc(c.last_rx)}</td>
    </tr>`).join('') || '<tr><td colspan="6" style="color:var(--sub);text-align:center">No clients connected</td></tr>';

  // Feed
  const feed  = document.getElementById('feed');
  const rows  = data.feed || [];
  const scrolledToBottom = feedBody.scrollHeight - feedBody.clientHeight <= feedBody.scrollTop + 10;
  feed.innerHTML = rows.map(r => {
    const dirClass = r.dir === '←' ? 'in' : (r.dir === '→' ? 'out' : 'disc');
    const typeClass = 'type-' + (r.type || '');
    return `<div class="feed-row">
      <span class="feed-ts">${esc(r.ts)}</span>
      <span class="feed-dir ${dirClass}">${esc(r.dir)}</span>
      <span class="feed-type ${typeClass}">${esc(r.type || '')}</span>
      <span class="feed-text">${esc(r.text || '')}</span>
    </div>`;
  }).join('');
  if (scrolledToBottom) feedBody.scrollTop = feedBody.scrollHeight;
}

const feedBody = document.getElementById('feed-body');
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function tick() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toISOString().replace('T',' ').slice(0,19) + ' UTC';
}
setInterval(tick, 1000); tick();
connect();
</script>
</body>
</html>
"""


async def handle_http(reader, writer) -> None:
    """Minimal HTTP server for the dashboard HTML page."""
    try:
        data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        request_line = data.decode("utf-8", errors="replace").splitlines()[0]
        path = request_line.split()[1] if len(request_line.split()) > 1 else "/"
        if path == "/" or path == "/index.html":
            body = DASHBOARD_HTML.encode("utf-8")
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"Connection: close\r\n"
                b"Cache-Control: no-cache\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
        else:
            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


# ── main ──────────────────────────────────────────────────────────────────────

async def _main(ws_port: int, web_port: int, secret: str) -> None:
    hub = Hub(secret=secret)
    log.info("Hub starting")
    log.info("  WebSocket relay  ws://0.0.0.0:%d", ws_port)
    log.info("  Dashboard        http://0.0.0.0:%d", web_port)
    if secret:
        log.info("  Shared secret    set (*** hidden ***)")
    else:
        log.warning("  Shared secret    NOT SET — any client can connect")

    # WebSocket relay server
    relay_server = websockets.server.serve(  # pylint: disable=no-member
        hub.handle_client,
        host="0.0.0.0",
        port=ws_port,
        max_size=MAX_FRAME_BYTES,
    )

    # Dashboard WebSocket server (path /dash)
    dash_server = websockets.server.serve(  # pylint: disable=no-member
        hub.handle_web,
        host="0.0.0.0",
        port=web_port + 1,    # internal; Caddy proxies /dash → this port
        max_size=1024,
    )

    # Dashboard HTTP server (serves HTML page)
    http_server = await asyncio.start_server(
        handle_http, "0.0.0.0", web_port
    )

    log.info("Hub ready.  Press Ctrl+C to stop.")
    async with relay_server, dash_server, http_server:
        await asyncio.Future()  # run forever


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MeshCore Bridge Hub — centralised WebSocket relay")
    parser.add_argument("--ws-port",  type=int,
                        default=int(os.environ.get("HUB_WS_PORT",  "9000")),
                        help="WebSocket relay port (default 9000)")
    parser.add_argument("--web-port", type=int,
                        default=int(os.environ.get("HUB_WEB_PORT", "9001")),
                        help="Dashboard HTTP port (default 9001)")
    parser.add_argument("--secret",
                        default=os.environ.get("HUB_SECRET", ""),
                        help="Shared secret (env: HUB_SECRET)")
    args = parser.parse_args()

    try:
        asyncio.run(_main(args.ws_port, args.web_port, args.secret))
    except KeyboardInterrupt:
        log.info("Hub stopped.")


if __name__ == "__main__":
    main()
