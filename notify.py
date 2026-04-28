"""
notify.py — desktop notifications and sound alerts
MeshCore Node Manager  |  Original work

All functions are safe to call from any thread.
All external dependencies are optional — if unavailable the function
silently does nothing.
"""
import os
import sys
import threading


# ── optional imports ──────────────────────────────────────────────────────────
try:
    from plyer import notification as _plyer_notify
    _PLYER = True
except ImportError:
    _plyer_notify = None
    _PLYER = False


def desktop_notify(title: str, message: str, timeout: int = 5) -> None:
    """
    Show a desktop notification.
    Uses plyer if available (pip install plyer), otherwise falls back to
    a platform-specific method.
    Does nothing if no notification backend is available.
    """
    def _send():
        try:
            if _PLYER:
                _plyer_notify.notify(
                    title=title,
                    message=message,
                    app_name="MeshCore Node Manager",
                    timeout=timeout,
                )
                return
            # Platform fallbacks
            if sys.platform == "win32":
                try:
                    from win10toast import ToastNotifier  # type: ignore
                    ToastNotifier().show_toast(title, message,
                                               duration=timeout, threaded=True)
                    return
                except ImportError:
                    pass
                # ctypes fallback (Windows 10+)
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBeep(0)
                except Exception:
                    pass
            elif sys.platform == "darwin":
                os.system(f"osascript -e 'display notification "
                          f"\"{_esc(message)}\" with title \"{_esc(title)}\"'")
            else:
                # Linux — try notify-send
                os.system(f"notify-send '{_esc(title)}' '{_esc(message)}'")
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def play_alert() -> None:
    """
    Play a short audible alert.
    Uses platform-specific methods; safe to call from any thread.
    """
    def _play():
        try:
            if sys.platform == "win32":
                try:
                    import winsound  # type: ignore[import]  # noqa: F401  # pylint: disable=import-outside-toplevel,import-error
                    winsound.MessageBeep(winsound.MB_OK)  # type: ignore[name-defined]  # pylint: disable=undefined-variable
                except Exception:
                    pass
            elif sys.platform == "darwin":
                os.system("afplay /System/Library/Sounds/Tink.aiff &")
            else:
                # Linux — try paplay, then aplay, then bell
                if os.system("paplay /usr/share/sounds/freedesktop/"
                             "stereo/message.oga 2>/dev/null") != 0:
                    if os.system("aplay /usr/share/sounds/alsa/"
                                 "Front_Center.wav 2>/dev/null") != 0:
                        print("\a", end="", flush=True)
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()


def _esc(s: str) -> str:
    """Escape a string for shell usage in notify-send / osascript."""
    return s.replace("'", "\\'").replace('"', '\\"')[:120]
