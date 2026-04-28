"""
events.py — lightweight in-process event bus
MeshCore Node Manager  |  Original work
"""
import threading
from collections import defaultdict


class EventBus:
    """
    Thread-safe publish/subscribe bus.
    Handlers are called in the order registered.
    Exceptions are swallowed and routed to an optional error_handler.
    """

    def __init__(self, error_handler=None):
        self._listeners: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
        self._error_handler = error_handler

    def on(self, event: str, fn) -> None:
        with self._lock:
            self._listeners[event].append(fn)

    def off(self, event: str, fn) -> None:
        with self._lock:
            try:
                self._listeners[event].remove(fn)
            except ValueError:
                pass

    def emit(self, event: str, **kwargs) -> None:
        with self._lock:
            handlers = list(self._listeners[event])
        for fn in handlers:
            try:
                fn(**kwargs)
            except Exception as exc:
                if self._error_handler:
                    try:
                        self._error_handler(event, exc)
                    except Exception:
                        pass

    def clear(self, event: str | None = None) -> None:
        with self._lock:
            if event:
                self._listeners.pop(event, None)
            else:
                self._listeners.clear()


# ── well-known event names ────────────────────────────────────────────────────
EV_CONNECTED      = "connected"       # kwargs: conn_type, node_name
EV_DISCONNECTED   = "disconnected"    # kwargs: (none)
EV_RECONNECTING   = "reconnecting"    # kwargs: attempt (int)
EV_CONN_ERROR     = "conn_error"      # kwargs: message
EV_CONTACTS_UPD   = "contacts_upd"   # kwargs: (none)
EV_MSG_CHANNEL    = "msg_channel"     # kwargs: sender, text, ts
EV_MSG_DIRECT     = "msg_direct"      # kwargs: sender, text, ts
EV_MSG_SENT       = "msg_sent"        # kwargs: local_id
EV_MSG_DELIVERED  = "msg_delivered"   # kwargs: local_id, rtt
EV_MSG_TIMEOUT    = "msg_timeout"     # kwargs: local_id
EV_UNREAD_CHANGE  = "unread_change"   # kwargs: direct (int), channel (int)
EV_NOTE_UPD       = "note_upd"        # kwargs: key (str)
EV_SETTINGS_UPD   = "settings_upd"   # kwargs: (none)
EV_LOG            = "log"             # kwargs: text, level
