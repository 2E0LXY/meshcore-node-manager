"""
events.py — lightweight in-process event bus
MeshCore Node Manager  |  Original work

Usage:
    bus = EventBus()
    bus.on("msg_rx", handler)
    bus.emit("msg_rx", payload={"text": "hello"})
"""
import threading
from collections import defaultdict


class EventBus:
    """
    Thread-safe publish/subscribe bus.
    Handlers are called in the order they were registered.
    Exceptions in handlers are swallowed and reported via an optional
    error_handler(event_name, exc) callable.
    """

    def __init__(self, error_handler=None):
        self._listeners: dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
        self._error_handler = error_handler

    def on(self, event: str, fn) -> None:
        """Register fn as a listener for event."""
        with self._lock:
            self._listeners[event].append(fn)

    def off(self, event: str, fn) -> None:
        """Remove a previously registered listener."""
        with self._lock:
            try:
                self._listeners[event].remove(fn)
            except ValueError:
                pass

    def emit(self, event: str, **kwargs) -> None:
        """Call all listeners for event with the given keyword arguments."""
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
        """Remove all listeners for event, or all listeners if event is None."""
        with self._lock:
            if event:
                self._listeners.pop(event, None)
            else:
                self._listeners.clear()


# ── well-known event names ────────────────────────────────────────────────────
EV_CONNECTED      = "connected"       # kwargs: conn_type, node_name
EV_DISCONNECTED   = "disconnected"    # kwargs: (none)
EV_CONN_ERROR     = "conn_error"      # kwargs: message
EV_CONTACTS_UPD   = "contacts_upd"   # kwargs: (none)
EV_MSG_CHANNEL    = "msg_channel"     # kwargs: sender, text, ts
EV_MSG_DIRECT     = "msg_direct"      # kwargs: sender, text, ts
EV_MSG_SENT       = "msg_sent"        # kwargs: local_id
EV_MSG_DELIVERED  = "msg_delivered"   # kwargs: local_id, rtt
EV_MSG_TIMEOUT    = "msg_timeout"     # kwargs: local_id
EV_LOG            = "log"             # kwargs: text, level
