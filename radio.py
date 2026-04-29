"""
radio.py — NodeRadio: async MeshCore device manager
MeshCore Node Manager  |  Original work

All device I/O is async; a background asyncio event loop runs in a daemon
thread.  All public methods are safe to call from any thread.

Communication with the rest of the application is entirely through the
EventBus — NodeRadio never calls GUI code directly.

MeshCore firmware notes
-----------------------
* The Python companion API does not expose a writable config tree.
  Radio parameters (frequency, SF, BW, power) must be changed via the
  device button UI or the TerminalCLI channel command.
* Broadcast uses send_msg(None, text).  Supported on dt267 >= v1.13 and
  meshcomod.  A TypeError is caught and reported if unsupported.
* Serial port deactivates after 30 s idle on dt267 firmware; TCP is
  recommended for persistent desktop use.
* BLE PIN pairing: use connect_ble(addr, pin="123456") for secure pairing.
  Set a PIN first with set_ble_pin(123456) then subsequent connections pass
  the matching pin= argument.
* Auto-reconnect is available for TCP connections.
"""

import asyncio
import csv
import gc
import json
import os
import threading
import time
from dataclasses import dataclass, field

from config import (
    ACK_TIMEOUT_SECS, BLE_SCAN_SECONDS, HISTORY_LIMIT,
    NOTES_FILE, SESSION_LOG_DIR,
    AUTO_PING_INTERVAL, RECONNECT_MAX,
)
from events import (
    EventBus,
    EV_CONNECTED, EV_DISCONNECTED, EV_RECONNECTING, EV_CONN_ERROR,
    EV_CONTACTS_UPD,
    EV_MSG_CHANNEL, EV_MSG_DIRECT, EV_MSG_SENT,
    EV_MSG_DELIVERED, EV_MSG_TIMEOUT,
    EV_UNREAD_CHANGE, EV_NOTE_UPD,
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
    key:        str
    name:       str
    last_heard: float | None = None
    snr:        float | None = None
    rssi:       float | None = None
    lat:        float | None = None
    lon:        float | None = None
    battery:    int   | None = None
    favourite:  bool         = False
    raw:        object       = field(default=None, repr=False)


@dataclass
class Message:
    """A single sent or received message."""
    local_id:      int
    direction:     str        # "tx" | "rx"
    kind:          str        # "channel" | "direct"
    peer:          str
    text:          str
    ts_sent:       float | None = None
    ts_received:   float | None = None
    ts_delivered:  float | None = None
    rtt:           float | None = None
    hops:          int   | None = None    # hop count from packet metadata
    status:        str = "unknown"        # always set explicitly at construction


# ── NodeRadio ─────────────────────────────────────────────────────────────────

class NodeRadio:
    """
    Connects to a MeshCore companion radio and relays events through the bus.
    """

    def __init__(self, bus: EventBus):
        self._bus = bus

        # device state
        self._mc              = None
        self._online          = False
        self._conn_type       = ""
        self._conn_factory    = None   # stored for auto-reconnect
        self._reconnect_count = 0
        self.node_name        = ""
        self.device_info: dict = {}

        # contacts
        self._contacts: dict[str, Contact] = {}
        self._ct_lock = threading.Lock()

        # contact notes  { key: str }
        self._notes: dict[str, str] = {}
        self._load_notes()

        # contact favourites set
        self._favourites: set[str] = set()
        self._load_favourites()

        # message store
        self._msg_lock  = threading.Lock()
        self._history:  list[Message]      = []
        self._pending:  dict[int, Message] = {}
        self._id_ctr    = 0

        # unread counters
        self._unread_direct  = 0
        self._unread_channel = 0

        # session log file handle
        self._session_fh = None

        # async loop
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread             | None = None
        self._fetch_task    = None
        self._ping_task     = None
        self._sub_token     = None

        # settings references (set by AppWindow after construction)
        self.settings = None

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def online(self) -> bool:
        return self._online

    @property
    def conn_type(self) -> str:
        return self._conn_type

    @property
    def has_conn_factory(self) -> bool:
        """True if a reconnect factory is stored (i.e. was previously connected)."""
        return self._conn_factory is not None

    def clear_conn_factory(self) -> None:
        """Clear stored connection factory (prevents auto-reconnect)."""
        self._conn_factory = None

    def upsert_contact(self, contact: "Contact") -> None:
        """
        Insert or update a contact in the local cache.
        Used by the bridge to add remote contacts.
        """
        with self._ct_lock:
            self._contacts[contact.key] = contact

    @property
    def unread_direct(self) -> int:
        return self._unread_direct

    @property
    def unread_channel(self) -> int:
        return self._unread_channel

    # ── loop management ───────────────────────────────────────────────────────

    def _start_loop(self):
        if self._loop and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="mc-radio"
        )
        self._thread.start()
        time.sleep(0.05)

    def _submit(self, coro, timeout: float = 20.0):
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
        self._conn_type    = "Serial"
        self._conn_factory = lambda: MeshCore.create_serial(port)
        return self._connect(self._conn_factory)

    def connect_tcp(self, host: str, port: int = 4403) -> bool:
        self._conn_type    = "TCP"
        self._conn_factory = lambda: MeshCore.create_tcp(host, port)
        return self._connect(self._conn_factory)

    def connect_ble(self, address: str, pin: str = "") -> bool:
        """
        Connect via BLE.  If pin is provided, uses PIN-authenticated pairing.
        """
        self._conn_type = "BLE"
        if pin:
            self._conn_factory = lambda: MeshCore.create_ble(address, pin=pin)
        else:
            self._conn_factory = lambda: MeshCore.create_ble(address)
        return self._connect(self._conn_factory)

    def set_ble_pin(self, pin: int) -> bool:
        """Set BLE PIN on the currently connected device."""
        if not self._mc or not self._online:
            return False
        try:
            self._submit(self._mc.commands.set_devicepin(pin), timeout=10.0)
            self._emit_log(f"BLE PIN set to {pin}", "ok")
            return True
        except Exception as exc:
            self._emit_log(f"BLE PIN set failed: {exc}", "err")
            return False

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
        result = await self._mc.commands.send_device_query()
        if result.type != EventType.ERROR:
            self.device_info = result.payload or {}
        self.node_name = self.device_info.get("name", "unknown")

        await self._load_contacts()

        self._sub_token  = self._mc.subscribe(self._on_mc_event)
        self._fetch_task = self._loop.create_task(self._mc.auto_fetch_msgs(delay=5))

        # Auto-ping task (Serial keepalive)
        self._ping_task = self._loop.create_task(self._auto_ping_loop())

        self._online          = True
        self._reconnect_count = 0
        self._start_session_log()
        self._bus.emit(EV_CONNECTED, conn_type=self._conn_type,
                       node_name=self.node_name)
        self._emit_log(f"Online [{self._conn_type}] — {self.node_name}", "ok")

    async def _auto_ping_loop(self):
        """
        Periodically pings the device to prevent serial idle disconnect.
        Only active on Serial connections.
        """
        while self._online:
            interval = AUTO_PING_INTERVAL
            if self.settings:
                interval = self.settings.get("auto_ping_interval", AUTO_PING_INTERVAL)
                if not self.settings.get("auto_ping_enabled", True):
                    await asyncio.sleep(5)
                    continue
            if self._conn_type == "Serial" and self._mc:
                try:
                    await self._mc.commands.send_device_query()
                except Exception:
                    pass
            await asyncio.sleep(interval)

    def disconnect(self, _reconnecting: bool = False):
        if not self._online and self._loop is None and self._mc is None:
            return
        if not _reconnecting:
            self._emit_log("Disconnecting…", "info")
        try:
            if self._loop and self._loop.is_running() and self._mc:
                for task in (self._fetch_task, self._ping_task):
                    if task:
                        self._loop.call_soon_threadsafe(task.cancel)
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
            self._mc = self._fetch_task = self._ping_task = self._sub_token = None
            self._online = False
            with self._ct_lock:
                self._contacts.clear()
            with self._msg_lock:
                self._pending.clear()
            self._close_session_log()
            if not _reconnecting:
                self._conn_factory = None
                self._stop_loop()
                gc.collect()
                self._bus.emit(EV_DISCONNECTED)
                self._emit_log("Offline", "info")

    def try_reconnect(self) -> None:
        """
        Attempt to reconnect using the stored factory.
        Called by AppWindow's periodic tick when auto-reconnect is enabled.
        """
        if self._online or self._conn_factory is None:
            return
        max_a = RECONNECT_MAX
        if self.settings:
            max_a = self.settings.get("reconnect_max", RECONNECT_MAX)
        if max_a > 0 and self._reconnect_count >= max_a:
            return
        self._reconnect_count += 1
        self._emit_log(f"Reconnect attempt {self._reconnect_count}…", "warn")
        self._bus.emit(EV_RECONNECTING, attempt=self._reconnect_count)
        self._connect(self._conn_factory)

    # ── ping ──────────────────────────────────────────────────────────────────

    def ping(self) -> bool:
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
        if not _BLE_OK:
            self._emit_log("bleak not installed — pip install bleak", "err")
            return []
        already = self._loop is not None and self._loop.is_running()
        if not already:
            self._start_loop()
        try:
            return self._submit(self._scan_ble_async(timeout), timeout=timeout + 3)
        except Exception as exc:
            self._emit_log(f"BLE scan error: {exc}", "err")
            return []
        finally:
            if not already and not self._online:
                self._stop_loop()

    async def _scan_ble_async(self, timeout: float) -> list[dict]:
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
            # Restore persisted favourite state
            c.favourite = c.key in self._favourites
            contacts[c.key] = c
        with self._ct_lock:
            self._contacts = contacts
        self._bus.emit(EV_CONTACTS_UPD)

    def refresh_contacts(self):
        if self._online:
            self._submit(self._load_contacts())

    def get_contacts(self) -> list[Contact]:
        """
        Return contacts sorted: favourites first, then by name.
        """
        with self._ct_lock:
            return sorted(
                self._contacts.values(),
                key=lambda c: (not c.favourite, c.name.lower())
            )

    def get_contact_names(self) -> list[str]:
        with self._ct_lock:
            return sorted(c.name for c in self._contacts.values() if c.name)

    def remove_contact(self, key: str) -> bool:
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

    def toggle_favourite(self, key: str) -> bool:
        """Toggle favourite state for a contact. Returns new state."""
        with self._ct_lock:
            c = self._contacts.get(key)
            if c is None:
                return False
            c.favourite = not c.favourite
            if c.favourite:
                self._favourites.add(key)
            else:
                self._favourites.discard(key)
        self._save_favourites()
        return c.favourite

    def _find_raw_contact(self, name_or_key: str):
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
            name = raw_val.get("adv_name", raw_val.get("name", key))
            lh   = raw_val.get("last_heard")
            snr  = raw_val.get("last_snr")
            rssi = raw_val.get("last_rssi")
            lat  = raw_val.get("adv_lat")
            lon  = raw_val.get("adv_lon")
            batt = raw_val.get("battery")
        else:
            name = getattr(raw_val, "adv_name", getattr(raw_val, "name", key))
            lh   = getattr(raw_val, "last_heard", None)
            snr  = getattr(raw_val, "last_snr",   None)
            rssi = getattr(raw_val, "last_rssi",  None)
            lat  = getattr(raw_val, "adv_lat",    None)
            lon  = getattr(raw_val, "adv_lon",    None)
            batt = getattr(raw_val, "battery",    None)
        return Contact(key=key, name=name, last_heard=lh, snr=snr, rssi=rssi,
                       lat=lat, lon=lon, battery=batt, raw=raw_val)

    def export_contacts_csv(self, path: str) -> bool:
        """Export contact list to CSV."""
        try:
            contacts = self.get_contacts()
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(["Name", "Key", "SNR", "RSSI", "Battery%",
                                 "LastHeard", "Lat", "Lon", "Favourite", "Note"])
                for c in contacts:
                    writer.writerow([
                        c.name, c.key,
                        c.snr if c.snr is not None else "",
                        c.rssi if c.rssi is not None else "",
                        c.battery if c.battery is not None else "",
                        ts_to_iso(c.last_heard),
                        c.lat if c.lat is not None else "",
                        c.lon if c.lon is not None else "",
                        "Yes" if c.favourite else "No",
                        self._notes.get(c.key, ""),
                    ])
            self._emit_log(f"Contacts exported to {path}", "ok")
            return True
        except Exception as exc:
            self._emit_log(f"CSV export failed: {exc}", "err")
            return False

    # ── contact notes ─────────────────────────────────────────────────────────

    def get_note(self, key: str) -> str:
        return self._notes.get(key, "")

    def set_note(self, key: str, text: str) -> None:
        if text.strip():
            self._notes[key] = text.strip()
        else:
            self._notes.pop(key, None)
        self._save_notes()
        self._bus.emit(EV_NOTE_UPD, key=key)

    def _load_notes(self):
        if os.path.exists(NOTES_FILE):
            try:
                with open(NOTES_FILE, "r", encoding="utf-8") as fh:
                    self._notes = json.load(fh)
            except Exception:
                self._notes = {}

    def _save_notes(self):
        try:
            with open(NOTES_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._notes, fh, indent=2)
        except Exception:
            pass

    # ── favourites persistence ────────────────────────────────────────────────

    def _favourites_path(self) -> str:
        from config import APP_DIR
        return os.path.join(APP_DIR, "favourites.json")

    def _load_favourites(self):
        p = self._favourites_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    self._favourites = set(json.load(fh))
            except Exception:
                self._favourites = set()

    def _save_favourites(self):
        try:
            with open(self._favourites_path(), "w", encoding="utf-8") as fh:
                json.dump(list(self._favourites), fh)
        except Exception:
            pass

    # ── radio / device info ───────────────────────────────────────────────────

    def radio_params(self) -> dict:
        d = self.device_info
        return {
            "Frequency (MHz)":  d.get("radio_freq"),
            "Bandwidth (kHz)":  d.get("radio_bw"),
            "Spreading Factor": d.get("radio_sf"),
            "Coding Rate":      d.get("radio_cr"),
            "TX Power (dBm)":   d.get("tx_power"),
        }

    def live_stats(self) -> dict:
        if not self._mc or not self._online:
            return {}
        try:
            r = self._submit(self._mc.commands.get_stats(), timeout=5.0)
            if r.type != EventType.ERROR:
                return r.payload or {}
            return {}
        except Exception:
            return {}

    # ── send ─────────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._id_ctr += 1
        return (int(time.time() * 1000) + self._id_ctr) & 0xFFFF_FFFF

    def transmit_channel(self, text: str) -> "int | None":
        if not self._online or not self._mc or not text.strip():
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
            self._session_write(msg)
            self._bus.emit(EV_MSG_SENT, local_id=lid)
            self._emit_log(f"Broadcast sent id={lid}", "info")
            return lid
        except Exception as exc:
            self._emit_log(f"Broadcast error: {exc}", "err")
            return None

    def transmit_direct(self, dest: str, text: str,
                        ack: bool = True) -> "int | None":
        if not self._online or not self._mc or not text.strip() or not dest.strip():
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
            self._session_write(msg)
            self._bus.emit(EV_MSG_SENT, local_id=lid)
            self._emit_log(f"DM sent id={lid} → {dest}", "info")
            return lid
        except Exception as exc:
            self._emit_log(f"DM error: {exc}", "err")
            return None

    # ── ACK timeout sweep ─────────────────────────────────────────────────────

    def sweep_timeouts(self, timeout: float = ACK_TIMEOUT_SECS) -> int:
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
        sender, text, hops = self._split_payload(payload)
        if not text:
            return
        now = time.time()
        msg = Message(local_id=self._next_id(), direction="rx", kind="channel",
                      peer=sender, text=text, ts_received=now,
                      hops=hops, status="received")
        with self._msg_lock:
            self._history.append(msg)
            self._unread_channel += 1
        self._session_write(msg)
        self._bus.emit(EV_MSG_CHANNEL, sender=sender, text=text, ts=now, hops=hops)
        self._bus.emit(EV_UNREAD_CHANGE,
                       direct=self._unread_direct,
                       channel=self._unread_channel)
        self._emit_log(f"Channel [{sender}]: {text}", "info")

    def _rx_direct(self, payload):
        sender, text, hops = self._split_payload(payload)
        if not text:
            return
        now = time.time()
        msg = Message(local_id=self._next_id(), direction="rx", kind="direct",
                      peer=sender, text=text, ts_received=now,
                      hops=hops, status="received")
        with self._msg_lock:
            self._history.append(msg)
            self._unread_direct += 1
        self._session_write(msg)
        self._bus.emit(EV_MSG_DIRECT, sender=sender, text=text, ts=now, hops=hops)
        self._bus.emit(EV_UNREAD_CHANGE,
                       direct=self._unread_direct,
                       channel=self._unread_channel)
        self._emit_log(f"DM [{sender}]: {text}", "info")

    def _advance_pending(self, _payload):
        with self._msg_lock:
            for msg in self._pending.values():
                if msg.status == "pending":
                    msg.status = "sent"
                    break

    def _confirm_delivery(self, _payload):
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
        now          = time.time()
        msg.ts_delivered = now
        msg.rtt          = now - msg.ts_sent if msg.ts_sent else None
        msg.status       = "delivered"
        self._bus.emit(EV_MSG_DELIVERED, local_id=lid, rtt=msg.rtt)
        self._emit_log(
            f"ACK confirmed id={lid} rtt={msg.rtt:.1f}s" if msg.rtt else
            f"ACK confirmed id={lid}", "ok")

    # ── unread management ─────────────────────────────────────────────────────

    def clear_unread_direct(self) -> None:
        self._unread_direct = 0
        self._bus.emit(EV_UNREAD_CHANGE,
                       direct=0, channel=self._unread_channel)

    def clear_unread_channel(self) -> None:
        self._unread_channel = 0
        self._bus.emit(EV_UNREAD_CHANGE,
                       direct=self._unread_direct, channel=0)

    # ── message store ─────────────────────────────────────────────────────────

    def message_history(self, limit: int = HISTORY_LIMIT,
                        kind: str | None = None,
                        peer: str | None = None,
                        search: str | None = None) -> list[Message]:
        """
        Return a snapshot, oldest first, with optional filtering.
        kind:   "channel" | "direct" | None (all)
        peer:   filter by sender/dest name (case-insensitive)
        search: full-text search on message text (case-insensitive)
        """
        with self._msg_lock:
            snap = list(self._history)
        snap.sort(key=lambda m: (
            m.ts_received if m.ts_received is not None
            else (m.ts_sent if m.ts_sent is not None else 0)
        ))
        if kind:
            snap = [m for m in snap if m.kind == kind]
        if peer:
            needle = peer.lower()
            snap = [m for m in snap if needle in m.peer.lower()]
        if search:
            needle = search.lower()
            snap = [m for m in snap if needle in m.text.lower()]
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

    # ── session log ───────────────────────────────────────────────────────────

    def _start_session_log(self):
        enabled = True
        if self.settings:
            enabled = self.settings.get("session_log", True)
        if not enabled:
            return
        try:
            # Sanitise node_name BEFORE strftime to prevent % format codes
            safe_name = "".join(
                c if c.isalnum() or c in "._- " else "_"
                for c in self.node_name)
            fname = time.strftime(f"session_{safe_name}_%Y%m%d_%H%M%S.txt")
            path = os.path.join(SESSION_LOG_DIR, fname)
            self._session_fh = open(path, "w", encoding="utf-8")
            self._session_fh.write(
                f"MeshCore Node Manager — Session Log\n"
                f"Node: {self.node_name}  Transport: {self._conn_type}\n"
                f"Started: {ts_to_iso(time.time())}\n"
                + "─" * 56 + "\n\n"
            )
            self._session_fh.flush()
            self._emit_log(f"Session log: {fname}", "info")
        except Exception as exc:
            self._emit_log(f"Session log failed to open: {exc}", "warn")
            self._session_fh = None

    def _session_write(self, msg: Message):
        if self._session_fh is None:
            return
        try:
            ts    = msg.ts_received or msg.ts_sent
            arrow = "→" if msg.direction == "tx" else "←"
            line  = f"[{ts_to_iso(ts)}] {msg.kind:7s} {arrow} {msg.peer}: {msg.text}"
            if msg.hops is not None:
                line += f"  (hops={msg.hops})"
            self._session_fh.write(line + "\n")
            self._session_fh.flush()
        except Exception:
            pass

    def _close_session_log(self):
        if self._session_fh:
            try:
                self._session_fh.write(
                    f"\nSession ended: {ts_to_iso(time.time())}\n")
                self._session_fh.close()
            except Exception:
                pass
            self._session_fh = None

    # ── export ────────────────────────────────────────────────────────────────

    def export_messages(self, path: str) -> bool:
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
                    if m.hops is not None:
                        line += f"  (hops={m.hops})"
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
                "node_name":   self.node_name,
                "device_info": self.device_info,
                "radio":       self.radio_params(),
                "saved_at":    ts_to_iso(time.time()),
            }
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            self._emit_log(f"Backup saved to {path}", "ok")
            return True
        except Exception as exc:
            self._emit_log(f"Backup failed: {exc}", "err")
            return False

    def load_backup(self, path: str) -> "dict | None":
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
    def _split_payload(payload) -> "tuple[str, str, int | None]":
        """Return (sender, text, hops) from a received event payload."""
        if isinstance(payload, dict):
            sender = payload.get("sender_prefix", payload.get("sender", "?"))
            text   = payload.get("text", "")
            hops   = payload.get("hops")
        else:
            sender = "?"
            text   = str(payload) if payload else ""
            hops   = None
        return sender, text, hops

    def _emit_log(self, text: str, level: str = "info"):
        self._bus.emit(EV_LOG, text=text, level=level)
