"""
settings.py — persistent application settings
MeshCore Node Manager  |  Original work

Stores and loads settings from ~/.meshcore_nm/settings.json.
Provides typed defaults and safe load/save.
"""
import json
import os
from config import SETTINGS_FILE


_DEFAULTS: dict = {
    # last connection
    "last_conn_type":  "",        # "Serial" | "TCP" | "BLE"
    "last_serial_port": "",
    "last_tcp_host":   "",
    "last_tcp_port":   4403,
    "last_ble_address": "",
    "last_ble_pin":    "",

    # behaviour
    "auto_ping_enabled":   True,
    "auto_ping_interval":  20,    # seconds (Serial keepalive)
    "auto_reconnect":      True,  # TCP only
    "reconnect_max":       10,

    # notifications
    "notify_dm":       True,      # desktop notification on incoming DM
    "notify_channel":  False,     # desktop notification on channel msg
    "sound_dm":        True,      # audible alert on incoming DM
    "sound_channel":   False,

    # session log
    "session_log":     True,      # auto-save each session to file

    # UI
    "window_geometry": "1160x820",
}


class Settings:
    """
    Simple key-value settings store backed by JSON.
    Thread-safe for read; write always from the GUI thread.
    """

    def __init__(self):
        self._data: dict = dict(_DEFAULTS)
        self.load()

    def get(self, key: str, fallback=None):
        return self._data.get(key, _DEFAULTS.get(key, fallback))

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def load(self) -> bool:
        if not os.path.exists(SETTINGS_FILE):
            return False
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            # Only load known keys; ignore unknown (forward-compat)
            for k in _DEFAULTS:
                if k in saved:
                    self._data[k] = saved[k]
            return True
        except Exception:
            return False

    def save(self) -> bool:
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
            return True
        except Exception:
            return False

    def as_dict(self) -> dict:
        return dict(self._data)
