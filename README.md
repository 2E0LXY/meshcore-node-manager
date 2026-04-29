# MeshCore Node Manager

A desktop app for **Windows, macOS and Linux** that lets you send and receive
text messages across a **LoRa mesh radio network** using MeshCore-flashed
hardware such as the Heltec WiFi LoRa 32 V3 / V4.

Connect your radio node by **USB cable**, **WiFi**, or **Bluetooth**, then:

- Chat on the public channel or send private direct messages with delivery confirmation
- See every node on your mesh — signal strength, GPS position, battery level
- Track message delivery, round-trip times, and network statistics
- View node locations plotted on a live map
- Get desktop and sound alerts when messages arrive

**No cloud. No internet required.** All traffic travels over LoRa radio.
Range is typically **2–15 km line of sight** depending on hardware and antenna.

> **Licence:** MIT — see [LICENSE](LICENSE)
> **Python:** 3.10 or later required

---

## Table of Contents

1. [Features](#features)
2. [Architecture overview](#architecture-overview)
3. [Recommended firmware](#recommended-firmware)
4. [Requirements](#requirements)
5. [Installation](#installation)
6. [Quick start](#quick-start)
7. [Connecting to a node](#connecting-to-a-node)
8. [Tabs in detail](#tabs-in-detail)
9. [Toolbar reference](#toolbar-reference)
10. [Keyboard shortcuts](#keyboard-shortcuts)
11. [Firmware limitations](#firmware-limitations)
12. [Troubleshooting](#troubleshooting)
13. [Project structure](#project-structure)
14. [Contributing](#contributing)
15. [Licence and legal notice](#licence-and-legal-notice)

---

## Features

| Category | Feature |
|---|---|
| **Connections** | USB serial, TCP/WiFi (port 4403), Bluetooth BLE |
| **BLE scanner** | Scans 5 seconds; MeshCore nodes highlighted green; double-click to connect |
| **📡 Contacts tab** | Live table, filter, click-to-sort columns, recency colour, SNR/RSSI, battery %, GPS |
| **💬 Channel tab** | Send and receive public LoRa broadcast messages |
| **📨 Direct tab** | DMs with contact autocomplete dropdown, ACK tracking, inline delivery notes |
| **📊 History tab** | Full message log, per-row colour by status, RTT, aggregate stats |
| **📻 Radio tab** | Frequency, BW, SF, CR, TX power; live device stats (firmware-dependent) |
| **📋 Log tab** | Colour-coded application log; save to file |
| **228-char guard** | Live character counter on both send fields; warning if LoRa limit exceeded |
| **Ping** | Re-query device to confirm connection is alive (useful after serial idle timeout) |
| **Backup** | Save device info + radio params to JSON |
| **Load backup** | Load and display a saved JSON backup |
| **Export messages** | Save full message history to a timestamped plain-text file |
| **Auto-reconnect** | Periodic ACK timeout sweep; status bar shows pending count |
| **Dark theme** | Catppuccin Mocha palette throughout |
| **Clean shutdown** | Graceful disconnect and loop teardown on window close |
| **⟷ Bridge tab** | Connect geographically separate networks over the internet |
| **⬡ NEXUS dashboard** | Animated real-time analytics HUD — radar, health orb, RTT sparkline, hop topology, signal waterfall |
| **⚙ Settings tab** | Persistent preferences: notifications, auto-ping, auto-reconnect, BLE PIN, bridge, session log |
| **Session log** | Auto-saves every session to `~/.meshcore_nm/sessions/` |
| **Contact notes** | Per-contact private annotations stored locally |
| **Contact favourites** | Star contacts; float to top; persisted between sessions |
| **Contact CSV export** | Export full contact list with notes to CSV |
| **Desktop notifications** | System alerts and sound on incoming DM or channel message |
| **Auto-ping (Serial)** | Prevents dt267 30-second idle disconnect |
| **Auto-reconnect (TCP)** | Reconnects automatically when TCP drops |
| **BLE PIN pairing** | Secure BLE connection with shared PIN |

---

## Architecture overview

```
main.py
  └── AppWindow (app.py)              Tkinter root window
        ├── NodeRadio (radio.py)      All device I/O, async loop in daemon thread
        ├── Bridge (bridge.py)        Internet bridge — WebSocket relay (off by default)
        ├── EventBus (events.py)      Pub/sub decoupling layer
        ├── Analytics (analytics.py)  Derived metrics (link quality, RTT, health score)
        └── Tabs (app.py)
              ├── ContactsTab         Contacts list with notes, favourites, CSV export
              ├── ChannelTab          Broadcast chat
              ├── DirectTab           DM chat + ACK + chat-per-contact filter
              ├── HistoryTab          Searchable message log + stats
              ├── MapTab              GPS network map
              ├── RadioTab            Radio params + live device stats
              ├── BridgeTab           Bridge status and peer list
              ├── SettingsTab         Persistent settings
              └── LogTab              Application log

hub/hub.py                            Centralised relay hub (run on a server)
  ├── WebSocket relay (:9000)         All clients connect here — no port-forward needed
  ├── Dashboard HTTP  (:9001)         Live web UI showing connected clients + feed
  └── Dashboard WS    (:9002)         Real-time data stream for the dashboard

hub/Caddyfile                         Caddy reverse proxy — automatic TLS/WSS
```

**Design principles**

- `NodeRadio` never calls GUI code directly. All device events flow outward
  through `EventBus.emit()`.
- All tabs subscribe to bus events and update themselves via `after_tk()`,
  which marshals every UI update onto the Tkinter main thread.
- `NodeRadio` runs a background `asyncio` event loop in a daemon thread.
  All device I/O is async; all public methods are thread-safe.
- Shared state (`_contacts`, `_history`, `_pending`) is protected by
  `threading.Lock` objects so the GUI thread and the async loop never race.

---

## Recommended firmware

For **Heltec WiFi LoRa 32 V3** and **V4**, use the dt267 low-power fork:

**[https://github.com/dt267/MeshCore-Low-Power-Firmware-For-Heltec-V3-V4](https://github.com/dt267/MeshCore-Low-Power-Firmware-For-Heltec-V3-V4)**

| Capability | Detail |
|---|---|
| Transports | USB serial + BLE + TCP/WiFi simultaneously in one binary |
| Hardware | V3, WSL3, V4 (V4.2 / V4.3 with KCT8103L FEM, auto-detected) |
| Display | OLED vs no-display auto-detected at boot — no separate build needed |
| OTA updates | Send `start ota` in the `TerminalCLI` channel |
| Low-battery protection | Deep sleep at 3.4 V; wake at 3.5 V |
| Adaptive RX gain | Tracks ambient noise floor |
| GPS power management | On only during fix acquisition (V4.2) |
| Battery life (idle) | V3 ≈ 7 days; V4 ≈ 3.5 days on 2 000 mAh |

> **V4 requirement:** official MeshCore firmware **v1.15.0+** is required for
> the V4 hardware generation.

> **Serial idle note:** the dt267 firmware deactivates the serial port after
> **30 seconds of idle**. Use TCP for a persistent desktop connection, or
> click **📡 Ping** to wake a dormant serial link.

> **V4.2 RX sensitivity:** if you notice poor receive sensitivity or a high
> noise floor on V4.2, a hardware mod to bypass the external LNA is
> documented in the firmware repository (`Bypass-External-LNA-on-Heltec-V4.md`).

Also compatible with **meshcomod** (ALLFATHER-BV) which provides the same
USB + BLE + TCP multi-transport support:
[https://github.com/ALLFATHER-BV/meshcomod](https://github.com/ALLFATHER-BV/meshcomod)

---

## Requirements

- **Python 3.10 or later** (uses `X | Y` union type syntax)
- **Tkinter** — included in most Python desktop installs
  - Debian / Ubuntu: `sudo apt install python3-tk`
  - macOS Homebrew: `brew install python-tk`
  - Windows: included in the official Python installer

```bash
pip install meshcore bleak websockets

# Optional — desktop notifications
pip install plyer
```

| Package | Purpose | Min version |
|---|---|---|
| `meshcore` | Official MeshCore Python companion library | latest |
| `bleak` | Cross-platform Bluetooth Low Energy | 0.21+ |
| `websockets` | Bridge and hub networking | 13.0+ |

### BLE platform notes

| OS | Notes |
|---|---|
| **Windows 10 / 11** | Works out of the box; requires a Bluetooth 4.0+ adapter |
| **macOS** | Works; Python may request Bluetooth permission on first run |
| **Linux** | Requires BlueZ; run `bluetoothctl power on` before scanning |

---

## Installation

### Option A — clone from GitHub

```bash
git clone https://github.com/2E0LXY/meshcore-node-manager.git
cd meshcore-node-manager
pip install meshcore bleak
python main.py
```

### Option B — virtual environment (recommended)

```bash
git clone https://github.com/2E0LXY/meshcore-node-manager.git
cd meshcore-node-manager

# Create and activate
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install meshcore bleak
python main.py
```

### Option C — Windows one-liner (in the repo directory)

```bat
python -m venv venv && venv\Scripts\activate && pip install meshcore bleak && python main.py
```

---

## Quick start

1. Flash your Heltec V3 / V4 with dt267 firmware (see
   [recommended firmware](#recommended-firmware))
2. `pip install meshcore bleak`
3. `python main.py`
4. Click **🔵 BLE** → **🔍 Scan (5 s)** → double-click your node (green row)
5. The **📡 Contacts** tab populates; the **💬 Channel** tab shows live traffic

---

## Connecting to a node

### 🔵 BLE (Bluetooth)

1. Click **🔵 BLE** in the toolbar
2. Click **🔍 Scan (5 s)** — MeshCore nodes appear in **green** at the top
3. **Double-click** a row to connect instantly, or select a row and click
   **✅ Connect**
4. You can also type a MAC address or partial device name directly in the
   address field and click **✅ Connect** without scanning

**Tips:**
- If no devices appear, confirm Bluetooth is enabled on your computer and
  the node is powered on
- On Linux, run `bluetoothctl power on` before scanning

### 🌐 TCP / WiFi

1. Click **🌐 TCP**
2. Enter the node's **IP address** (check your router's DHCP table or the
   node's OLED display)
3. Port defaults to **4403** — change only if your node is configured
   differently

TCP is the most reliable transport for desktop use: it has no idle timeout
and works over a LAN or port-forwarded internet connection.

### 🔌 Serial (USB)

1. Connect the node with a **USB-C data cable** (not a charge-only cable)
2. Click **🔌 Serial**
3. Enter the COM port:
   - Windows: `COM3`, `COM4` … (check Device Manager → Ports)
   - Linux: `/dev/ttyUSB0` or `/dev/ttyACM0`
   - macOS: `/dev/cu.usbserial-*`
4. Press Enter or click OK

**Linux permission fix** (one-time):
```bash
sudo usermod -aG dialout $USER
# then log out and back in
```

**Serial idle timeout:** the dt267 firmware disconnects serial after 30 s
idle. Click **📡 Ping** to re-establish, or switch to TCP for persistent
sessions.

---

## Tabs in detail

### 📡 Contacts

Displays all contacts known to the connected node, sorted by name.

| Column | Description |
|---|---|
| Name | Advertised name of the contact |
| Key | First 16 hex characters of the public key (unique ID) |
| SNR | Signal-to-noise ratio of the last received packet (dB) |
| RSSI | Received signal strength of the last packet (dBm) |
| Batt % | Battery level if the contact device reports it |
| Last Heard | Time of the last received packet from this contact |
| GPS | Latitude / longitude if the contact broadcasts position |

**Row colours:**
- **Green** — contact was heard within the last 10 minutes
- **Dimmed** — older than 10 minutes or never heard

**Filter:** type in the filter box to search by name or key; the count label
updates live.

**Sort:** click any column heading to sort ascending; click again to reverse.

**🔄 Refresh:** reloads the full contact list from the device.

**🗑 Remove:** removes the selected contact(s) from the **local cache only**.
The device's own contact list is not affected; contacts reappear on the next
Refresh.

---

### 💬 Channel

Broadcast messages on the public LoRa channel. All nodes within RF range
receive these messages.

- **Sent** messages appear in **blue**
- **Received** messages appear in **green**
- **Live character counter** — LoRa maximum is **228 characters** per frame;
  a warning dialog appears if you try to send more
- Press **Enter** or click **📤 Broadcast** to send

> **No ACK for broadcasts** — the MeshCore protocol does not provide delivery
> confirmation for channel messages. Use Direct messages if you need ACK.

> **Broadcast API note:** the `send_msg(None, text)` call used for broadcasting
> is supported on dt267 v1.13+ and meshcomod firmware. If you see
> *"Broadcast failed"* in the Log tab, upgrade your firmware.

---

### 📨 Direct

Private direct messages to a specific contact with delivery tracking.

- The **To:** dropdown auto-populates with known contact names after
  connecting; start typing to filter the list
- You can also type a pubkey prefix directly if the contact does not appear
  by name
- Press **Enter** or click **📨 Send DM** to send
- **Live character counter** — same 228-character limit as Channel
- After each sent DM, an inline note appears when:
  - **✅ Delivered (RTT x.xs)** — ACK received with round-trip time
  - **⏱ Timeout — no ACK received** — 30 seconds elapsed with no response

**ACK tracking works when:**
- The destination node is within LoRa RF range
- The destination is running MeshCore companion firmware
- The message type is direct (not a broadcast)

**Received** DMs appear in **green**; sent messages appear in **blue**.

---

### 📊 History

Full record of all sent and received messages.

| Column | Description |
|---|---|
| Dir | ↑ = sent, ↓ = received |
| Type | `channel` or `direct` |
| Peer | Destination (↑) or sender (↓) |
| Message | First 34 characters of the message text |
| Status | `pending` / `sent` / `delivered` / `timeout` / `received` |
| Time | Timestamp when sent or received |
| RTT | Round-trip time in seconds for delivered DMs |

**Row colours:**
- **Green** — delivered or received
- **Red** — timeout
- **Blue/cyan** — pending ACK

**Stats bar** at the top shows:
- Total messages, sent (↑), received (↓)
- Delivered, timeout, pending counts
- Average RTT across all delivered DMs
- Success percentage (delivered / total sent × 100)

**🗑 Clear History** removes all messages from the in-memory store only.
It does not affect the device.

---

### 📻 Radio

Radio configuration read from the device at connect time, plus live
device statistics.

**Radio Parameters (read-only):**

| Field | Description |
|---|---|
| Frequency (MHz) | LoRa carrier frequency |
| Bandwidth (kHz) | LoRa signal bandwidth |
| Spreading Factor | SF7 – SF12 |
| Coding Rate | LoRa forward error correction ratio |
| TX Power (dBm) | Transmit power level |

**Live Device Stats:** click **🔄 Refresh** to fetch real-time counters
(TX packets, RX packets, error counts, etc.) from the device.

> **Write-back not available.** The MeshCore Python companion API does not
> expose a writable configuration tree. To change radio parameters, use:
> - The **device button UI** (navigate the OLED menu)
> - The **TerminalCLI channel**: create a channel named `TerminalCLI` on the
>   device, then type commands in the Channel tab
>
> Live stats require dt267 v1.13+ or meshcomod firmware with stats support.

---

### 📋 Log

Colour-coded application log showing every event.

| Colour | Level | Examples |
|---|---|---|
| **Green** | `ok` | Connected, ACK confirmed, backup saved, ping OK |
| **Yellow** | `warn` | ACK timeout, disconnect warning, contact not found |
| **Red** | `err` | Connection failed, send failed, library missing |
| **Cyan** | `info` | Message sent, disconnecting, history cleared |
| **Grey** | `debug` | Verbose internal events |

**🗑 Clear** wipes the log display (application continues running normally).

**💾 Save** opens a file dialog and saves the full log to a `.txt` file.

---

## Bridge Network

Connect geographically separate MeshCore networks over the internet so that
channel messages and contact telemetry flow between them automatically.
**Disabled by default.**

### ⟷ Bridge tab

Shows whether the bridge is running and lists all currently connected peers.
Remote contacts appear prefixed with ⟷ in the Contacts and Map tabs.
Bridged channel messages are prefixed with `[ORIGIN-NODE]`.

Direct messages (DMs) are **never bridged** — they remain private.

### Setting up peer-to-peer (two locations)

See the full guide in [§ Bridge Network](#bridge-network) of the
[User Manual](docs/USER_MANUAL.md).

### Setting up with the hub (recommended — no port-forwarding)

See **[hub/README.md](hub/README.md)** for the 5-minute server setup guide.

Once the hub is running at `wss://yourdomain.com/hub`, each Node Manager
instance just needs:

1. ⚙ Settings → Bridge Network → tick **Enable bridge**
2. Peers box: `wss://yourdomain.com/hub`
3. Enter shared secret → 💾 Save

---

## Toolbar reference

| Button | Action |
|---|---|
| **🔌 Serial** | Open serial port dialog; connect via USB |
| **🌐 TCP** | Open TCP dialog (host + port); connect via WiFi |
| **🔵 BLE** | Open BLE scanner; connect via Bluetooth |
| **⏹ Disconnect** | Graceful disconnect; releases all resources |
| **🔄 Contacts** | Reload full contact list from device |
| **📡 Ping** | Re-query device info to confirm the connection is alive |
| **💾 Backup** | Save device info + radio params to a JSON file |
| **📂 Load Backup** | Open a JSON backup and display its contents |
| **📝 Export Msgs** | Save full message history to a plain-text file |
| **⬡ NEXUS** | Open the animated analytics dashboard |
| **ℹ Info** | Show the raw device info payload in a popup |

---

## Keyboard shortcuts

| Key | Context | Action |
|---|---|---|
| `Enter` | Channel send field | Send broadcast |
| `Enter` | Direct message field | Send DM |
| `Enter` | Any dialog (Serial, TCP) | Confirm / OK |
| `Escape` | Any dialog | Cancel / close |
| `Double-click` | BLE device list | Select and connect immediately |

---

## Firmware limitations

The MeshCore Python companion API exposes a subset of device functionality.
The following are **not available** through this application:

| Feature | Reason |
|---|---|
| WiFi / MQTT / LoRa config write-back | No writable config tree in API |
| Channel name / uplink / downlink edit | Not exposed by API |
| Node role, region, modem preset | Not exposed by API |
| `setOwner` (rename the node) | Not exposed by API |
| GPS configuration | Not exposed by API |

**Workaround for all of the above:** use the device button UI (OLED menu)
or the `TerminalCLI` channel. Create a channel named exactly `TerminalCLI`
on the device, then type commands in the **💬 Channel** tab.

**Broadcast API:** `send_msg(None, text)` is the broadcast call used by this
application. It works on dt267 v1.13+ and meshcomod firmware. If you see
*"Broadcast failed"* in the Log tab, upgrade your firmware to dt267 v1.13+.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: meshcore` | `pip install meshcore` |
| `ModuleNotFoundError: bleak` | `pip install bleak` |
| BLE scan finds no devices | Confirm Bluetooth is enabled; on Linux run `bluetoothctl power on` |
| BLE scan finds device but connection fails | Some adapters require a prior OS-level pair; use `bluetoothctl pair <addr>` on Linux |
| Serial "Permission denied" on Linux | `sudo usermod -aG dialout $USER` then log out and back in |
| Serial disconnects after ~30 s | dt267 serial idle timeout; click **📡 Ping** or switch to TCP |
| "Contact not found" when sending DM | Click **🔄 Contacts** to refresh; check name spelling (case-insensitive) |
| "Broadcast failed — firmware may not support…" | Upgrade to dt267 v1.13+ or meshcomod |
| Live stats show no data | Requires dt267 v1.13+ or meshcomod with stats support |
| Black screen on V4 after flashing | Flash the non-merged `.bin` at offset `0x10000` if the device already has a valid bootloader |
| App hangs when clicking Serial or TCP | Ensure Python 3.10+; if on Windows try running as administrator once to rule out COM port permissions |
| History tab doesn't update after sending | Ensure `EV_MSG_SENT` is received — check the Log tab for any send errors |

---

## Project structure

```
meshcore-node-manager/
├── main.py          Entry point
├── app.py           AppWindow — 9 tabs, dialogs, toolbar, bridge wiring
├── radio.py         NodeRadio — device connection, contacts, messaging, ACK
├── bridge.py        Bridge — internet relay between multiple Node Managers
├── analytics.py     Analytics engine — link quality, RTT, health scores
├── dashboard.py     NEXUS HUD — animated canvas analytics dashboard
├── events.py        EventBus — pub/sub decoupling
├── config.py        Constants and Catppuccin Mocha theme tokens
├── helpers.py       Pure utility functions
├── settings.py      Persistent settings (~/.meshcore_nm/settings.json)
├── notify.py        Desktop notifications and sound alerts
├── docs/
│   └── USER_MANUAL.md    Full user manual
├── hub/
│   ├── hub.py            Centralised bridge relay hub
│   ├── Caddyfile         Caddy reverse proxy config (automatic TLS)
│   ├── hub.service       systemd service file
│   ├── requirements.txt  Hub dependencies
│   └── README.md         Hub setup guide
├── .github/
│   └── workflows/
│       └── build-release.yml   CI/CD — builds EXE + .deb on every version tag
├── README.md        This file
└── LICENSE          MIT licence
```

### Module responsibilities

**`main.py`** (8 lines) — creates `AppWindow` and calls `mainloop()`.

**`config.py`** — all tuneable constants in one place:
- `TCP_DEFAULT_PORT = 4403`
- `ACK_TIMEOUT_SECS = 30`
- `HISTORY_LIMIT = 500`
- `LORA_MAX_CHARS = 228`
- Full Catppuccin Mocha colour palette (`TH` dict) and semantic aliases (`C` dict)
- Log level → colour mapping (`LOG_COLOURS` dict)

**`helpers.py`** — six pure functions with no side effects:
- `ts_to_hms(epoch)` — UNIX timestamp → `"HH:MM:SS"` or `"—"`
- `ts_to_iso(epoch)` — UNIX timestamp → `"YYYY-MM-DD HH:MM:SS"` or `"—"`
- `pubkey_short(raw)` — bytes/str → first 16 hex chars
- `safe_str(value)` — None-safe string conversion with fallback
- `fmt_rtt(seconds)` — float → `"1.4s"` or `""`
- `normalise_key(raw)` — lowercase stripped string for case-insensitive matching

**`events.py`** — `EventBus` class with `on()`, `off()`, `emit()`, `clear()`.
Ten well-known event constants (`EV_CONNECTED`, `EV_MSG_DIRECT`, etc.).
The bus is the only communication channel between `NodeRadio` and the GUI.

**`radio.py`** — `NodeRadio` class. `Contact` and `Message` dataclasses.
Public methods: `connect_serial()`, `connect_tcp()`, `connect_ble()`,
`disconnect()`, `ping()`, `scan_ble()`, `refresh_contacts()`,
`get_contacts()`, `get_contact_names()`, `remove_contact()`,
`transmit_channel()`, `transmit_direct()`, `sweep_timeouts()`,
`message_history()`, `message_stats()`, `clear_history()`,
`export_messages()`, `save_backup()`, `load_backup()`, `live_stats()`,
`radio_params()`.

**`app.py`** — `AppWindow` (Tk root), `TabBase`, six tab classes, two dialogs
(`_PromptDialog`, `_BLEDialog`). No business logic; only layout and event
wiring.

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run the quality checks — all three must be clean before submitting:
   ```bash
   python3 -m py_compile config.py helpers.py events.py settings.py \
       notify.py radio.py bridge.py app.py main.py analytics.py dashboard.py
   python3 -m pyflakes   config.py helpers.py events.py settings.py \
       notify.py radio.py bridge.py app.py main.py analytics.py dashboard.py
   python3 -m pylint     config.py helpers.py events.py settings.py \
       notify.py radio.py bridge.py app.py main.py analytics.py dashboard.py \
       --disable=C,R,W0718 --score=no
   ```
5. Commit: `git commit -m "Add my feature"`
6. Push and open a Pull Request: `git push origin feature/my-feature`

---

## Licence and legal notice

### This project

```
MIT License

Copyright (c) 2026 MeshCore Node Manager Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Originality statement

This project is an **original, independent work**. It was written from
scratch with no copying or derivation from any prior codebase.

In particular, it is **not** a port, fork, modification, or derivative of
[Meshtastic-Ultimate-Center-ACH](https://github.com/Piccolino1965/Meshtastic-Ultimate-Center-ACH)
by Giovanni Popolizio, which is published under a custom all-rights-reserved
licence that prohibits redistribution and sharing in any form. That licence
was carefully reviewed and is fully respected: no code, structure, logic, or
creative expression from that project has been used here.

The shared domain — a Python/Tkinter desktop app for managing a LoRa mesh
radio node — naturally leads to common technical vocabulary
(`connect_serial`, `connect_tcp`, `_build_toolbar`) and similar functional
requirements (contacts list, channel messaging, DM with ACK). These
overlaps fall under the legal doctrine of *scènes à faire*: elements that
are standard, stock, or necessary to a given domain are not protectable by
copyright. All shared identifiers were independently arrived at; none were
copied.

The architecture of this project — `EventBus`, `NodeRadio`, `TabBase`,
typed `Contact` / `Message` dataclasses, and the pub/sub event flow — has
no equivalent in the referenced project and represents original creative
choices.

### Third-party acknowledgements

| Project | Licence | URL |
|---|---|---|
| **meshcore** Python library | See repo | https://github.com/meshcore-dev/meshcore_py |
| **MeshCore firmware** | See repo | https://github.com/meshcore-dev/MeshCore |
| **dt267 low-power firmware** | See repo | https://github.com/dt267/MeshCore-Low-Power-Firmware-For-Heltec-V3-V4 |
| **meshcomod firmware** | See repo | https://github.com/ALLFATHER-BV/meshcomod |
| **bleak** (BLE library) | MIT | https://github.com/hbldh/bleak |
| **Catppuccin Mocha** (colour palette) | MIT | https://github.com/catppuccin/catppuccin |
| **websockets** (bridge / hub) | BSD-3 | https://github.com/python-websockets/websockets |
| **plyer** (notifications, optional) | MIT | https://github.com/kivy/plyer |
