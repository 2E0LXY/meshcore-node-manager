"""
helpers.py — pure utility functions with no UI or device dependencies
MeshCore Node Manager  |  Original work
"""
import datetime


def ts_to_hms(epoch: float | None) -> str:
    """Convert a UNIX timestamp to HH:MM:SS, or '—' if None/zero."""
    if not epoch:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(epoch).strftime("%H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return "—"


def ts_to_iso(epoch: float | None) -> str:
    """Convert a UNIX timestamp to ISO-8601 date-time string."""
    if not epoch:
        return "—"
    try:
        return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return "—"


def pubkey_short(raw) -> str:
    """
    Return a short hex string from a raw public-key value.
    Accepts bytes, bytearray, or str; always returns at most 16 chars.
    """
    if raw is None:
        return "?"
    if isinstance(raw, (bytes, bytearray)):
        try:
            return raw.hex()[:16]
        except Exception:
            return "?"
    return str(raw)[:16]


def safe_str(value, fallback: str = "—") -> str:
    """Return str(value) unless value is None/empty, then return fallback."""
    if value is None:
        return fallback
    s = str(value).strip()
    return s if s else fallback


def fmt_rtt(seconds: float | None) -> str:
    if seconds is None:
        return ""
    return f"{seconds:.1f}s"


def normalise_key(raw) -> str | None:
    """Normalise a contact key to a comparable lowercase string."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return s if s else None
