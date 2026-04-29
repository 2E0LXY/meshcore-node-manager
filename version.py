"""
version.py — single source of truth for application version
MeshCore Node Manager  |  Original work

Import this anywhere a version string is needed:
    from version import VERSION, VERSION_TUPLE
"""

VERSION_TUPLE = (1, 2, 0)
VERSION       = ".".join(str(x) for x in VERSION_TUPLE)
VERSION_STR   = f"v{VERSION}"

# Semantic version components
MAJOR, MINOR, PATCH = VERSION_TUPLE

# Protocol version for the bridge WebSocket framing (separate from app version)
BRIDGE_PROTOCOL_VERSION = 1
