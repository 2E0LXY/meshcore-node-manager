"""
config.py — application-wide settings and theme tokens
MeshCore Node Manager  |  Original work
"""
import os

# ── MeshCore transport defaults ───────────────────────────────────────────────
TCP_DEFAULT_PORT    = 4403
SERIAL_BAUD         = 115200        # informational; meshcore library handles baud
BLE_SCAN_SECONDS    = 5.0
ACK_TIMEOUT_SECS    = 30
HISTORY_LIMIT       = 500
LORA_MAX_CHARS      = 228           # practical LoRa payload limit for text frames

# ── auto-ping / reconnect ─────────────────────────────────────────────────────
AUTO_PING_INTERVAL  = 20            # seconds between keepalive pings on Serial
RECONNECT_DELAY     = 5             # seconds before auto-reconnect attempt
RECONNECT_MAX       = 10            # maximum reconnect attempts (0 = unlimited)

# ── session / persistence ─────────────────────────────────────────────────────
APP_DIR             = os.path.join(os.path.expanduser("~"), ".meshcore_nm")
SETTINGS_FILE       = os.path.join(APP_DIR, "settings.json")
NOTES_FILE          = os.path.join(APP_DIR, "notes.json")
SESSION_LOG_DIR     = os.path.join(APP_DIR, "sessions")

# Ensure directories exist at import time
os.makedirs(APP_DIR,         exist_ok=True)
os.makedirs(SESSION_LOG_DIR, exist_ok=True)

# ── Catppuccin Mocha palette (public domain colour scheme) ───────────────────
TH = {
    "base":     "#1e1e2e",
    "mantle":   "#181825",
    "crust":    "#11111b",
    "surface0": "#313244",
    "surface1": "#45475a",
    "overlay0": "#6c7086",
    "text":     "#cdd6f4",
    "subtext":  "#a6adc8",
    "blue":     "#89b4fa",
    "green":    "#a6e3a1",
    "yellow":   "#f9e2af",
    "red":      "#f38ba8",
    "teal":     "#89dceb",
    "mauve":    "#cba6f7",
    "peach":    "#fab387",
}

# ── semantic aliases ──────────────────────────────────────────────────────────
C = {
    "bg":         TH["base"],
    "bg2":        TH["mantle"],
    "panel":      TH["crust"],
    "border":     TH["surface0"],
    "muted":      TH["overlay0"],
    "fg":         TH["text"],
    "fg2":        TH["subtext"],
    "accent":     TH["blue"],
    "ok":         TH["green"],
    "warn":       TH["yellow"],
    "err":        TH["red"],
    "info":       TH["teal"],
    "mauve":      TH["mauve"],
    "peach":      TH["peach"],
    "btn":        TH["surface0"],
    "btn_fg":     TH["text"],
    "entry":      TH["surface0"],
}

# ── log level → colour ────────────────────────────────────────────────────────
LOG_COLOURS = {
    "ok":    C["ok"],
    "warn":  C["warn"],
    "err":   C["err"],
    "info":  C["info"],
    "debug": C["muted"],
}
