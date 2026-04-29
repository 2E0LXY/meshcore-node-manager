# MeshCore Node Manager — User Manual

**Version 1.2.0**

---

## What's new

### v1.2.0
- **⟷ Bridge Network** — connect geographically separate MeshCore networks
  over the internet (disabled by default)
- **Hub server** (`hub/hub.py`) — centralised WebSocket relay; no
  port-forwarding needed on client machines; live web dashboard
- **Caddy integration** — automatic TLS/WSS via Let's Encrypt
- Bug fixes: unread counter data race, sweep_timeouts lock, bridge inject
  setting, hub feed spam

### v1.1.0 (internal)
- **⬡ NEXUS analytics dashboard** — animated radar, health orb, RTT
  sparkline, hop topology, signal waterfall and more
- **Analytics engine** — link quality scores, network health, RTT trends,
  hop distribution
- **Contact features** — notes, favourites, CSV export, double-click to DM
- **Desktop notifications and sound alerts**
- **Auto-ping** (Serial keepalive), **auto-reconnect** (TCP)
- **BLE PIN pairing**
- **Session log** — auto-saves to `~/.meshcore_nm/sessions/`
- **Chat-per-contact filter** in Direct tab
- **Message search** in History tab
- **GPS network map** tab
- **Settings tab** — persistent preferences
- **⟷ Bridge tab** status panel

### v1.0.0
- Initial release: Serial, TCP, BLE connections
- Contacts, Channel, Direct, History, Radio, Log tabs
- ACK tracking, backup/restore, message export

---


## Table of Contents

1. [Introduction](#1-introduction)
2. [What is MeshCore and LoRa?](#2-what-is-meshcore-and-lora)
3. [Hardware Setup](#3-hardware-setup)
4. [Software Installation](#4-software-installation)
   - [Windows](#41-windows)
   - [Linux (Debian / Ubuntu)](#42-linux-debian--ubuntu)
   - [Linux (other distributions)](#43-linux-other-distributions)
   - [Running from source (all platforms)](#44-running-from-source-all-platforms)
5. [First Launch](#5-first-launch)
6. [Connecting to Your Node](#6-connecting-to-your-node)
   - [Bluetooth (BLE)](#61-bluetooth-ble)
   - [TCP / WiFi](#62-tcp--wifi)
   - [USB Serial](#63-usb-serial)
7. [Main Window Overview](#7-main-window-overview)
8. [Tabs — Detailed Reference](#8-tabs--detailed-reference)
   - [Contacts Tab](#81-contacts-tab)
   - [Channel Tab](#82-channel-tab)
   - [Direct Tab](#83-direct-tab)
   - [History Tab](#84-history-tab)
   - [Map Tab](#85-map-tab)
   - [Radio Tab](#86-radio-tab)
   - [Settings Tab](#87-settings-tab)
   - [Log Tab](#88-log-tab)
9. [NEXUS Analytics Dashboard](#9-nexus-analytics-dashboard)
   - [Opening NEXUS](#91-opening-nexus)
   - [Neural Radar Panel](#92-neural-radar-panel)
   - [Health Orb Panel](#93-health-orb-panel)
   - [RTT Sparkline Panel](#94-rtt-sparkline-panel)
   - [24-Hour Activity Sunburst](#95-24-hour-activity-sunburst)
   - [Contact Signal Matrix](#96-contact-signal-matrix)
   - [Hop Topology Panel](#97-hop-topology-panel)
   - [Delivery Reliability Matrix](#98-delivery-reliability-matrix)
   - [Signal Waterfall Panel](#99-signal-waterfall-panel)
10. [Toolbar Reference](#10-toolbar-reference)
11. [Keyboard Shortcuts](#11-keyboard-shortcuts)
12. [Settings Reference](#12-settings-reference)
13. [Data Files and Storage](#13-data-files-and-storage)
14. [Firmware Guide](#14-firmware-guide)
    - [Recommended firmware](#141-recommended-firmware)
    - [Flashing Heltec V3](#142-flashing-heltec-v3)
    - [Flashing Heltec V4](#143-flashing-heltec-v4)
    - [OTA firmware updates](#144-ota-firmware-updates)
    - [Firmware limitations](#145-firmware-limitations)
15. [Analytics Explained](#15-analytics-explained)
16. [Troubleshooting](#16-troubleshooting)
17. [Frequently Asked Questions](#17-frequently-asked-questions)
18. [Bridge Network — Detailed Guide](#18-bridge-network--detailed-guide)
    - [How it works](#181-how-it-works)
    - [Peer-to-peer setup](#182-peer-to-peer-setup)
    - [Hub setup (recommended)](#183-hub-setup-recommended)
    - [Hub web dashboard](#184-hub-web-dashboard)
    - [Security](#185-security)
    - [Running the hub as a service](#186-running-the-hub-as-a-service)
19. [Glossary](#19-glossary)

---

## 1. Introduction

MeshCore Node Manager is a desktop application for Windows, macOS and Linux
that lets you communicate over a **LoRa mesh radio network** using hardware
running [MeshCore](https://github.com/meshcore-dev/MeshCore) firmware.

You can connect to a radio node by USB cable, WiFi, or Bluetooth, then:

- Send and receive text messages on the public channel or privately
- See every node on your mesh with signal strength and GPS position
- Track whether your messages were delivered and how long they took
- View your network plotted on a live animated map
- Monitor network health, channel utilisation, and signal trends in real time
- Get desktop and sound alerts when messages arrive

**No cloud, no internet, no subscription required.** All traffic travels
directly over LoRa radio between nodes. Range is typically 2–15 km line of
sight depending on antenna, terrain, and radio settings.

---

## 2. What is MeshCore and LoRa?

**LoRa** (Long Range) is a radio modulation technique designed for low-power,
long-range communication. It operates in the unlicensed ISM band (usually
433 MHz, 868 MHz in Europe, or 915 MHz in the Americas) and can carry short
text messages several kilometres with milliwatt-level power.

**MeshCore** is open-source firmware for LoRa hardware that creates a
self-organising mesh network. Each node can relay messages from other nodes,
automatically extending the network range beyond any single radio's reach.
This is called **mesh routing** or **store and forward**.

**This application** is the desktop companion that talks to your nearest
MeshCore node over USB, WiFi, or Bluetooth. The node then handles all radio
communication on your behalf.

---

## 3. Hardware Setup

### Supported hardware

The recommended hardware is the **Heltec WiFi LoRa 32**, available in
two current generations:

| Model | LoRa chip | Display | USB | WiFi | BLE | Notes |
|---|---|---|---|---|---|---|
| **V3** | SX1262 | 0.96" OLED | USB-C | ✅ | ✅ | Widely available |
| **V4** | SX1262 | 0.96" OLED | USB-C | ✅ | ✅ | Requires firmware ≥ v1.15.0 |

Other LoRa32 variants (WSL3, V4.2, V4.3 with KCT8103L FEM) are also
supported by the recommended firmware.

### What you need

- One or more Heltec V3 or V4 boards
- A USB-C **data** cable (charge-only cables will not work for Serial)
- A computer running Windows 10/11, Linux, or macOS
- The MeshCore Node Manager application (this software)
- The dt267 MeshCore firmware flashed to each board (see §14)

### Antennas

Always connect an antenna before powering on the board. Transmitting without
an antenna can damage the RF front-end. The boards usually ship with a short
wire antenna sufficient for testing. For best range use a proper 868 MHz or
915 MHz antenna matched to your region's frequency.

---

## 4. Software Installation

### 4.1 Windows

1. Go to the [Releases page](https://github.com/2E0LXY/meshcore-node-manager/releases/latest)
2. Download `meshcore-node-manager-windows-x64.exe`
3. Double-click the file to run it

> **Windows Defender warning:** because the executable is not code-signed,
> Windows may show a "Windows protected your PC" dialog. Click
> **More info** → **Run anyway**. This is expected for open-source software
> without a paid code-signing certificate. The source code is fully public at
> the link above.

No installation is required. The `.exe` is fully self-contained — Python and
all libraries are bundled inside.

### 4.2 Linux (Debian / Ubuntu)

Download the `.deb` package and install it:

```bash
# Download
wget https://github.com/2E0LXY/meshcore-node-manager/releases/latest/download/meshcore-node-manager_amd64.deb

# Install
sudo dpkg -i meshcore-node-manager_*_amd64.deb

# Run
meshcore-node-manager
```

The `.deb` installs a desktop entry so the application also appears in your
application launcher under the **Network** or **Ham Radio** category.

To uninstall:
```bash
sudo apt remove meshcore-node-manager
```

### 4.3 Linux (other distributions)

Download the standalone binary:

```bash
wget https://github.com/2E0LXY/meshcore-node-manager/releases/latest/download/meshcore-node-manager-linux-x64
chmod +x meshcore-node-manager-linux-x64
./meshcore-node-manager-linux-x64
```

The binary is self-contained. No Python installation is required.

**Serial port permissions** (one-time setup — applies to all Linux installs):

```bash
sudo usermod -aG dialout $USER
# Log out and back in, or run:
newgrp dialout
```

Without this, the application cannot open USB serial ports.

**Bluetooth on Linux:**

```bash
# Ensure the adapter is powered on
bluetoothctl power on
```

### 4.4 Running from source (all platforms)

If you prefer to run the Python source directly, or if you are on macOS:

**Requirements:** Python 3.10 or later, and Tkinter.

```bash
# macOS — install Tkinter if needed
brew install python-tk

# Debian/Ubuntu — install Tkinter if needed
sudo apt install python3-tk

# Clone
git clone https://github.com/2E0LXY/meshcore-node-manager.git
cd meshcore-node-manager

# Install Python libraries
pip install meshcore bleak

# Optional — desktop notifications
pip install plyer

# Run
python main.py
```

**Virtual environment (recommended):**

```bash
python -m venv venv
source venv/bin/activate          # Linux / macOS
# or: venv\Scripts\activate       # Windows

pip install meshcore bleak websockets plyer
python main.py
```

---

## 5. First Launch

When the application opens you will see:

```
┌────────────────────────────────────────────────────────────────┐
│ 🔌 Serial  🌐 TCP  🔵 BLE  ⏹ Disconnect │ 🔄 Contacts  📡 Ping  │
│ 💾 Backup  📂 Load Backup  📝 Export Msgs │ ⬡ NEXUS  ℹ Info     │
├────────────────────────────────────────────────────────────────┤
│ 📡 Contacts │ 💬 Channel │ 📨 Direct │ 📊 History │ ...         │
│                                                                  │
│                  (connect to a node to begin)                    │
│                                                                  │
├────────────────────────────────────────────────────────────────┤
│ ⚫ Offline                                                       │
└────────────────────────────────────────────────────────────────┘
```

The status bar at the bottom shows **⚫ Offline** until you connect.
If you connected previously, the Log tab shows a hint: *"Last connection: BLE
C2:2B:A1:D5:3E:B6 — click to reconnect"*.

---

## 6. Connecting to Your Node

There are three ways to connect. For persistent desktop use, **TCP is
recommended** because it has no idle timeout. BLE is the most convenient
for casual use. Serial is reliable but requires a physical cable.

### 6.1 Bluetooth (BLE)

**Requirements:** Bluetooth 4.0+ adapter in your computer. The node must be
running firmware with BLE enabled (dt267 provides this).

1. Click **🔵 BLE** in the toolbar
2. Click **🔍 Scan (5 s)** — the dialog scans for 5 seconds
3. MeshCore nodes appear **highlighted in green** at the top of the list
4. **Double-click** your node to connect immediately, or select it and click
   **✅ Connect**
5. You can also type a MAC address or device name prefix directly in the
   address field without scanning

**BLE PIN pairing:**

If your node has a PIN configured (set via the device button UI):

1. Open **⚙ Settings** tab → BLE Security section
2. Enter the PIN in the BLE PIN field and click **💾 Save settings**
3. The PIN is stored and used automatically on every BLE connection

**Troubleshooting BLE:**

- If no devices appear, check that Bluetooth is enabled on your computer
- On Linux, run `bluetoothctl power on` in a terminal first
- Some Linux systems require a first-time OS-level pair:
  `bluetoothctl pair C2:2B:A1:D5:3E:B6`

### 6.2 TCP / WiFi

**Requirements:** Your computer and the node must be on the same WiFi network,
or the node's port must be port-forwarded if connecting remotely.

1. Click **🌐 TCP** in the toolbar
2. Enter the node's **IP address** — find this on your router's DHCP table,
   the node's OLED display, or with `nmap -sn 192.168.1.0/24`
3. Enter the port — default is **4403**. Change only if your node is
   configured differently
4. Click **OK**

**Why TCP is recommended for desktop use:**

The dt267 firmware deactivates the serial port after 30 seconds of idle
traffic. TCP has no such timeout, making it the most reliable transport for
a desktop session that may be idle for long periods. If you are using Serial
and the connection goes quiet, use **📡 Ping** to wake it (see §10).

**Last-used values are remembered.** The host and port from your last TCP
connection are pre-filled next time you click **🌐 TCP**.

### 6.3 USB Serial

**Requirements:** A USB-C data cable. Data cables have more wires than
charge-only cables — if the port is not recognised, try a different cable.

1. Plug the node into your computer with the USB-C cable
2. Click **🔌 Serial** in the toolbar
3. Enter the port name:
   - **Windows:** `COM3`, `COM4`, etc. — check Device Manager → Ports
   - **Linux:** `/dev/ttyUSB0` or `/dev/ttyACM0`
   - **macOS:** `/dev/cu.usbserial-*` (use tab-completion in Terminal)
4. Click **OK**

**Linux permission fix** (do this once, then log out and back in):
```bash
sudo usermod -aG dialout $USER
```

**Serial idle timeout:** the dt267 firmware disconnects serial after 30 s of
no data. Enable **Auto-ping** in Settings (on by default) to prevent this.
Auto-ping sends a silent device query every 20 seconds on Serial connections.

---

## 7. Main Window Overview

Once connected, the status bar changes to:

```
✅ Online [BLE]  │  NODE: MY-NODE-NAME                  ⏳ 2 pending
```

The window has three areas:

**Toolbar** (top): connection buttons, utility actions, and the NEXUS button.

**Notebook tabs** (centre): eight tabs, each covering a different aspect of
your network. Tabs with unread messages show a badge:
`📨 Direct (3)` means 3 unread DMs.

**Status bar** (bottom): connection state, transport type, node name, and
pending ACK count.

---

## 8. Tabs — Detailed Reference

### 8.1 Contacts Tab

Shows every node that your connected node knows about — its own contacts list.

#### Columns

| Column | Description |
|---|---|
| **★** | Gold star if the contact is marked as a favourite |
| **Name** | The contact's advertised name |
| **Key** | First 16 characters of the contact's public key (unique identifier) |
| **SNR** | Signal-to-noise ratio of the last received packet in dB |
| **RSSI** | Received signal strength of the last packet in dBm |
| **Batt %** | Battery percentage reported by the contact's device |
| **Last Heard** | Time of the most recent packet received from this contact |
| **GPS** | Latitude and longitude if the contact broadcasts its position |
| **Note** | Your personal annotation for this contact (stored locally) |

#### Row colours

- **Green** — contact was heard within the last 10 minutes (active)
- **Gold/Peach** — contact is marked as a favourite
- **Dimmed grey** — not heard in the last 10 minutes

#### Sorting

Click any column heading to sort by that column. Click again to reverse the
sort order. The sort is applied immediately and persists until you click a
different column.

#### Filter

Type in the **Filter** box to narrow the list to contacts whose name or key
contains the typed text. The count label (e.g. *3 of 12*) updates live.

#### Buttons

| Button | Action |
|---|---|
| **🔄 Refresh** | Reload the full contact list from the device |
| **⭐ Favourite** | Toggle favourite status for the selected contact |
| **📝 Note** | Open a text dialog to add or edit a note for the selected contact |
| **🗑 Remove** | Remove the selected contact(s) from the local cache |
| **📄 CSV** | Export the full contact list to a CSV file |

> **Note on Remove:** removing a contact only removes it from this application's
> view. The node's own internal contact list is not affected. The contact will
> reappear after the next **🔄 Refresh**.

#### Double-click

Double-clicking a contact name pre-fills the **To:** field in the Direct tab
and switches focus to that tab, ready to send a message.

---

### 8.2 Channel Tab

The public channel is a broadcast — every node within radio range (or within
relay range) receives every channel message. There is no delivery confirmation
for channel messages.

#### Reading messages

- **Blue text** — messages you sent
- **Green text** — messages received from other nodes
- **Grey timestamp** — time of each message
- **·2h** suffix — hop count (e.g. `·2h` = message was relayed by 2 nodes)

#### Sending a message

1. Type your message in the text field at the bottom
2. Press **Enter** or click **📤 Broadcast**
3. The character counter shows how many of the **228-character** limit you
   have used. A warning dialog appears if you try to send more than 228
   characters — LoRa frames cannot carry more than this

> **228-character limit:** LoRa payloads are physically constrained by the
> modulation. Longer messages must be split and sent separately.

#### Notifications

If **Channel notifications** are enabled in Settings (⚙), a desktop
notification and/or sound plays when a channel message arrives. This is
disabled by default (channel traffic can be high on busy networks).

---

### 8.3 Direct Tab

Direct messages (DMs) are private — only the addressed node receives them.
The MeshCore firmware provides ACK (delivery confirmation) for DMs, so you
know whether your message was received.

#### Sending a DM

1. Click the **To:** dropdown and select a contact name, or type a name or
   pubkey prefix directly. The dropdown is pre-populated with all known
   contacts after connecting
2. Type your message in the **Message** field
3. Press **Enter** or click **📨 Send DM**

After sending, inline notes appear below each message:
- **✅ Delivered (RTT 1.4s)** — the destination node confirmed receipt; RTT
  is the round-trip time from send to ACK
- **⏱ Timeout — no ACK received** — 30 seconds passed with no confirmation.
  The node may be out of range, powered off, or running non-MeshCore firmware

#### Message colours

- **Blue** — messages you sent
- **Green** — messages you received
- **Italic grey** — delivery notes (ACK confirmed / timeout)

#### Chat-per-contact filter (View: dropdown)

The **View:** dropdown at the top-left lets you filter the message view to
show only conversations with a specific contact. Select a name to see only
that conversation. Click **🌐 All** to return to the full view.

Switching to a contact view also clears the unread badge for that contact.

#### Notifications

If **DM notifications** are enabled in Settings (⚙ → on by default), a
desktop notification and/or sound plays when a direct message arrives,
even if the application window is minimised.

#### ACK timeout

ACK timeout is fixed at **30 seconds**. If the destination node does not
confirm receipt within 30 seconds, the message is marked as timed out.
Timed-out messages are not automatically retried — send again manually if
needed.

---

### 8.4 History Tab

A complete searchable log of every sent and received message in the current
session.

#### Search and filter bar

| Field | Effect |
|---|---|
| **Search** | Filter to messages whose text contains the typed string (case-insensitive) |
| **Peer** | Filter to messages sent to or received from a specific contact name |
| **Type** | Filter to `all`, `direct` only, or `channel` only |
| **✖ Clear filters** | Reset all filters to show the full history |

#### Columns

| Column | Description |
|---|---|
| **Dir** | ↑ = sent, ↓ = received |
| **Type** | `channel` or `direct` |
| **Peer** | Destination (↑) or sender (↓) |
| **Message** | First 30 characters of the message text |
| **Hops** | Number of relay hops (↓ only, when reported by firmware) |
| **Status** | `pending` / `sent` / `delivered` / `timeout` / `received` |
| **Time** | Timestamp when sent or received |
| **RTT** | Round-trip time in seconds for delivered DMs |

#### Row colours

- **Green** — delivered or received
- **Red** — timeout (no ACK)
- **Blue/cyan** — pending ACK (DM sent, waiting for confirmation)

#### Stats bar

The line above the table shows aggregate statistics for the current session:

```
Total: 47  │  ↑ 12  ↓ 35  │  ✅ 10  ⏱ 1  ⏳ 1  │  Avg RTT: 2.3s  │  Success: 83%
```

- **Total** — all messages in history
- **↑ / ↓** — sent / received counts
- **✅** — delivered DMs
- **⏱** — timed-out DMs
- **⏳** — pending DMs (awaiting ACK)
- **Avg RTT** — average round-trip time across all delivered DMs
- **Success %** — delivered / total sent × 100

#### 🗑 Clear History

Removes all messages from the in-memory history. The current session log file
(if enabled in Settings) is not affected. The device's own message store is
not affected.

---

### 8.5 Map Tab

Plots contacts that broadcast GPS coordinates on a plain canvas map.

#### Reading the map

- **Blue dot** — your own node (centre reference)
- **Green dot** — contact heard within the last 10 minutes
- **Peach/gold dot** — contact marked as a favourite
- **Grey dot** — contact not heard recently
- **Name label** — contact name appears below each dot
- **Grid lines** — faint reference grid

The map uses a simple equirectangular (flat) projection. For small areas
(within ~50 km) this is accurate. The map automatically scales to fit all
contacts with GPS data.

#### Hover tooltip

Move your mouse over any dot to see a tooltip with:
- Full contact name
- GPS coordinates (5 decimal places)
- RSSI and SNR values
- Battery percentage

#### 🔄 Refresh

Reloads the contact list and redraws the map. The map also redraws
automatically when contacts are updated.

> **No GPS?** If contacts do not appear on the map, they are either not
> broadcasting GPS coordinates, or the firmware on those nodes does not
> include GPS support. Only contacts with both latitude and longitude data
> are plotted.

---

### 8.6 Radio Tab

Displays radio configuration parameters read from the device at connect time.

#### Radio Parameters (read-only)

| Field | Description |
|---|---|
| **Frequency (MHz)** | LoRa carrier frequency |
| **Bandwidth (kHz)** | LoRa signal bandwidth — lower = longer range, slower |
| **Spreading Factor** | SF7 to SF12 — higher = longer range, slower, more robust |
| **Coding Rate** | Forward error correction ratio (4/5 to 4/8) |
| **TX Power (dBm)** | Transmit power — V3 max ~22 dBm, V4.2 max ~28 dBm |

> **These values cannot be changed from this application.** The MeshCore
> Python companion API does not expose a writable radio configuration. To
> change radio settings, use:
> - The **device button UI** — navigate the OLED menu
> - The **TerminalCLI channel** — create a channel named exactly `TerminalCLI`
>   on the device, then type commands in the Channel tab

#### Live Device Stats

Click **🔄 Refresh** to fetch real-time counters from the device:

- **tx_packets** — total transmitted packets
- **rx_packets** — total received packets
- **recv_errors** — receive errors (CRC failures, etc.)
- Additional fields depend on firmware version

> Live stats require **dt267 v1.13+** or meshcomod firmware. Older builds
> return no data.

---

### 8.7 Settings Tab

Persistent preferences stored in `~/.meshcore_nm/settings.json`.

#### Notifications

| Setting | Default | Effect |
|---|---|---|
| Desktop notification on incoming DM | **On** | Shows a system notification when a DM arrives |
| Desktop notification on Channel message | Off | Shows a notification for every channel message |
| Sound alert on incoming DM | **On** | Plays a short beep when a DM arrives |
| Sound alert on Channel message | Off | Plays a sound for every channel message |

Desktop notifications use `plyer` if installed (`pip install plyer`).
Without plyer, the application falls back to platform-specific methods
(`osascript` on macOS, `notify-send` on Linux, `win10toast` on Windows).

Sound alerts use:
- **Windows:** `winsound.MessageBeep`
- **macOS:** `afplay /System/Library/Sounds/Tink.aiff`
- **Linux:** `paplay` → `aplay` → terminal bell (tried in order)

#### Connection

| Setting | Default | Effect |
|---|---|---|
| Auto-ping on Serial | **On** | Sends a silent device query every N seconds on Serial connections to prevent the 30-second idle disconnect |
| Ping interval (seconds) | **20** | How often to ping on Serial |
| Auto-reconnect TCP on disconnect | **On** | Automatically re-attempts TCP connection when the connection drops |
| Max reconnect attempts | **10** | Maximum number of reconnect attempts (0 = unlimited) |

#### Session Log

| Setting | Default | Effect |
|---|---|---|
| Auto-save session log on connect | **On** | Creates a timestamped `.txt` log file in `~/.meshcore_nm/sessions/` when you connect |

Click **📂 Open log folder** to open the sessions directory in your file manager.

Session log files are named:
`session_NODENAME_YYYYMMDD_HHMMSS.txt`

#### BLE Security

| Setting | Effect |
|---|---|
| BLE PIN | If your node has a PIN set via its button UI, enter the matching PIN here. It is stored and used automatically on every BLE connection |

The PIN field is masked (shows `*` characters). Leave blank if your node has
no PIN configured.

#### Saving

Click **💾 Save settings** to persist all changes. Settings are also
auto-saved when you change a field and click away. A ✅ Saved confirmation
appears briefly.

---

### 8.8 Log Tab

A colour-coded application event log showing everything that happens.

#### Colours

| Colour | Level | When used |
|---|---|---|
| **Green** | ok | Connected, ACK confirmed, backup saved, ping OK, export done |
| **Yellow** | warn | ACK timeout, disconnect warning, contact not found |
| **Red** | err | Connection failed, send failed, library not installed |
| **Cyan** | info | Message sent, disconnecting, history cleared, reconnecting |
| **Grey** | debug | Internal events, session log path |

#### Buttons

- **🗑 Clear** — wipes the log display. The application continues normally.
- **💾 Save** — opens a file dialog to save the full log to a `.txt` file.
  Useful for bug reports or diagnosing connection problems.

---

## 9. NEXUS Analytics Dashboard

NEXUS (Neural EXtended UX System) is a separate full-window animated
network operations centre that visualises all available data from your mesh
network in real time.

### 9.1 Opening NEXUS

Click the **⬡ NEXUS** button in the toolbar (right side, accent coloured).
NEXUS opens as a separate window and can run alongside the main window.

**Demo mode:** NEXUS works even when no radio is connected. It generates
synthetic data to demonstrate all panels. This is useful for understanding
what each panel shows before going to the field.

The dashboard refreshes all data every **2 seconds** from the live radio
connection.

---

### 9.2 Neural Radar Panel

*Top-left. 360 × 360 px.*

A rotating radar sweep that shows all contacts in polar coordinates.

**Elements:**
- **Rotating cyan sweep arm** — rotates at 36°/second with a fading
  afterglow trail
- **Range rings** — four concentric rings at 25%, 50%, 75%, and 100% of
  the maximum visualised range (20 km)
- **Compass labels** — N, E, S, W around the outer edge
- **Contact blips** — each contact appears as a coloured dot:
  - Position on the radial axis represents **distance** from your node
    (if GPS data is available from both nodes). Without GPS, contacts are
    spread evenly by index
  - Position on the angular axis represents **bearing** from your node
    (if GPS data available), otherwise spread evenly
  - **Colour** represents link quality: green = excellent, yellow = good,
    orange = fair, red = poor
  - **Pulse glow** — when the sweep arm passes over a contact, it pulses
    with a bright halo, simulating a real radar return
  - **Name label** — contact name shown beside the blip
  - **Quality arc** — a short coloured arc segment at the contact's range
    ring shows link quality
- **Own node** — central pulsing cyan dot with a breathing glow
- **Outer decorative ring** — a rotating accent segment follows the sweep arm

---

### 9.3 Health Orb Panel

*Below the radar. 200 × 200 px.*

A single glowing orb that represents the overall health of your mesh network
as a composite score from 0 to 100.

**Score calculation:**
- **40%** — average link quality across all online nodes (RSSI 60% + SNR 40%)
- **35%** — ratio of online nodes (heard in last 10 min) to total known nodes
- **25%** — inverse of packet error rate (from live device stats)

**Status thresholds:**
- **≥ 75** — Network Healthy (green orb)
- **50–74** — Network Degraded (yellow orb)
- **< 50** — Network Critical (red orb)

**Elements:**
- **Breathing outer rings** — intensity and speed pulse with the health score
- **Score ring** — a coloured arc around the orb shows the score as a
  proportional arc (like a clock hand)
- **Central numerals** — the current score 0–100
- **Status text** — "Network Healthy" / "Degraded" / "Critical"
- **Node count** — online / total (e.g. `5/8`)
- **Utilisation and PER** — channel utilisation % and packet error rate %
- **Tick marks** — 36 tick marks around the edge; major ticks at 90° intervals

---

### 9.4 RTT Sparkline Panel

*Centre column, top. Full width × 100 px.*

A rolling line graph of round-trip times for delivered direct messages.

**Elements:**
- **Line** — the last 30 delivered DM RTTs plotted as a time series
- **Filled area** — translucent fill under the line
- **Current value dot** — pulsing cyan dot at the latest data point with
  the RTT value in milliseconds shown beside it
- **Y-axis labels** — minimum (0 ms) and maximum RTT
- **Grid lines** — faint horizontal reference lines at 0%, 50%, 100%
- **Animated scan line** — a faint vertical line scrolls left-to-right
  continuously to indicate the panel is live

If no DMs have been delivered yet, the panel shows **AWAITING DATA**.

---

### 9.5 24-Hour Activity Sunburst

*Top-right. 200 × 200 px.*

A radial chart showing message activity by hour of the day.

**Elements:**
- **24 segments** arranged clockwise from midnight (00:00) at the top
- **Segment length** represents the number of messages in that hour relative
  to the busiest hour
- **Current hour** — highlighted in cyan
- **Colour gradient** — teal to magenta based on activity intensity
- **Animated particle flow** — small particles move along active segments
- **Centre** — total message count for all time in the current session
- **Hour labels** — 00, 06, 12, 18 at the cardinal positions

This chart reveals when your network is most active — useful for identifying
peak usage periods.

---

### 9.6 Contact Signal Matrix

*Centre column, middle. Full width × variable height.*

Animated signal quality bars for up to 8 contacts, sorted by overall score.

**Per-contact row:**
- **Name** — contact name (truncated to 10 characters)
- **Status dot** — green = heard < 60 s ago, yellow = heard < 10 min, grey = older
- **Signal bar** — gradient-filled bar showing link quality percentage.
  The bar subtly breathes (slight amplitude pulse) to indicate it is live
- **Percentage label** — link quality as a percentage
- **Battery indicator** — thin vertical bar on the right edge showing
  battery level; green ≥ 50%, yellow ≥ 20%, red < 20%
- **Overall score orb** — small coloured dot on the far right showing the
  composite score (link + activity + battery)

**Link quality calculation:** RSSI weighted 60%, SNR weighted 40%.
Mapped from the typical LoRa range (RSSI: -140 dBm to -60 dBm,
SNR: -20 dB to +10 dB) to a 0–100% scale.

---

### 9.7 Hop Topology Panel

*Right column, middle. 200 × 200 px.*

Visualises how many hops (relay nodes) received messages have traversed.

**Elements:**
- **Concentric rings** — one ring per observed hop count value. The
  innermost ring represents 0-hop (direct) messages; outer rings represent
  messages relayed by 1, 2, 3+ nodes
- **Ring arc** — a thicker coloured arc on each ring shows the proportion
  of messages at that hop count relative to the busiest hop count
- **Animated particles** — four small dots orbit each active ring,
  flowing in the direction of message travel
- **Labels** — hop count and message count shown beside each ring
  (e.g. `2h:14` = 14 messages relayed by 2 nodes)

A network with only 0-hop messages means all contacts are in direct radio
range. Messages at 2+ hops indicate the mesh is actively relaying across
nodes not in direct range of each other.

---

### 9.8 Delivery Reliability Matrix

*Right column, bottom. 340 × variable height.*

Shows per-contact direct message delivery rates.

**Per-contact row:**
- **Name** — contact name
- **Delivery bar** — animated fill bar showing the delivery rate 0–100%
- **Percentage** — delivery rate
- **Stats** — delivered / sent count and timeout count
  (e.g. `10/12 ✓  2 ✗`)

Contacts with high timeout counts may be on the edge of radio range,
running low battery, or have their node powered down intermittently.

---

### 9.9 Signal Waterfall Panel

*Centre column, top section. Full width × 160 px.*

A rolling heatmap showing signal quality for up to 8 contacts over time.

**How to read it:**
- **Rows** — one row per contact (up to 8)
- **Columns** — time, scrolling right. The rightmost column is the
  most recent reading; leftmost is the oldest (up to 60 readings)
- **Colour** — link quality mapped to a gradient:
  - **Black** — no signal / quality 0%
  - **Dark blue** — poor quality (0–33%)
  - **Cyan** — fair to good quality (33–66%)
  - **Teal/white** — excellent quality (66–100%)
- **Rightmost value** — current link quality % shown in the matching colour
- **Row label** — contact name (truncated to 8 characters)
- **Animated scan line** — scrolling vertical line confirms the display is live

The waterfall reveals signal **stability** over time. A contact with a
consistent colour has a stable link; rapidly changing colours indicate
interference, obstruction, or a moving node.

---

## 10. Toolbar Reference

| Button | Action | Notes |
|---|---|---|
| **🔌 Serial** | Connect via USB serial | Prompts for port; last-used port pre-filled |
| **🌐 TCP** | Connect via WiFi/network | Prompts for host and port; last-used values pre-filled |
| **🔵 BLE** | Connect via Bluetooth | Opens BLE scanner dialog |
| **⏹ Disconnect** | Cleanly disconnect | Cancels auto-reconnect; releases all resources |
| **🔄 Contacts** | Reload contact list | Also refreshes the Map and Direct contact dropdown |
| **📡 Ping** | Re-query the device | Confirms connection is alive; wakes serial after idle timeout |
| **💾 Backup** | Save device info to JSON | Saves device info and radio parameters |
| **📂 Load Backup** | Load a saved backup | Displays the backup contents in a dialog |
| **📝 Export Msgs** | Export message history | Saves all messages to a plain-text file |
| **⬡ NEXUS** | Open analytics dashboard | Opens the NEXUS window (works offline in demo mode) |
| **ℹ Info** | Show raw device info | Displays all fields returned by the device query |

---

## 11. Keyboard Shortcuts

| Key | Location | Action |
|---|---|---|
| `Enter` | Channel send field | Send broadcast |
| `Enter` | Direct message field | Send DM |
| `Enter` | Serial / TCP dialog | Confirm and connect |
| `Enter` | Note / prompt dialog | Confirm |
| `Escape` | Any dialog | Cancel and close |
| `Double-click` | Contacts table row | Pre-fill Direct tab with contact name |
| `Double-click` | BLE scanner row | Select address and connect immediately |

---

## 12. Settings Reference

All settings are stored in `~/.meshcore_nm/settings.json` and loaded at
startup. You can edit this file in a text editor if needed.

| Key | Type | Default | Description |
|---|---|---|---|
| `last_conn_type` | string | `""` | Last used transport type |
| `last_serial_port` | string | `""` | Last serial port entered |
| `last_tcp_host` | string | `""` | Last TCP hostname/IP |
| `last_tcp_port` | int | `4403` | Last TCP port |
| `last_ble_address` | string | `""` | Last BLE address used |
| `last_ble_pin` | string | `""` | BLE PIN (stored in plaintext) |
| `auto_ping_enabled` | bool | `true` | Enable Serial keepalive pings |
| `auto_ping_interval` | int | `20` | Seconds between keepalive pings |
| `auto_reconnect` | bool | `true` | Auto-reconnect TCP on disconnect |
| `reconnect_max` | int | `10` | Max TCP reconnect attempts |
| `notify_dm` | bool | `true` | Desktop notification on DM |
| `notify_channel` | bool | `false` | Desktop notification on channel message |
| `sound_dm` | bool | `true` | Sound alert on DM |
| `sound_channel` | bool | `false` | Sound alert on channel message |
| `session_log` | bool | `true` | Auto-save session log files |
| `window_geometry` | string | `"1160x820"` | Saved window size/position |

---

## 13. Data Files and Storage

All application data is stored in a single directory:

| Platform | Path |
|---|---|
| **Windows** | `C:\Users\YourName\.meshcore_nm\` |
| **Linux / macOS** | `~/.meshcore_nm/` |

#### Files

| File | Contents |
|---|---|
| `settings.json` | All application settings (see §12) |
| `notes.json` | Contact notes keyed by contact public key |
| `favourites.json` | List of contact keys marked as favourites |
| `sessions/` | Directory containing session log files |
| `sessions/session_NODENAME_YYYYMMDD_HHMMSS.txt` | One file per connection session |

#### Session log format

```
MeshCore Node Manager — Session Log
Node: MY-NODE  Transport: BLE
Started: 2026-04-29 09:15:33
────────────────────────────────────────────────────────

[2026-04-29 09:15:41] channel → channel: hello from the field
[2026-04-29 09:16:02] direct  → NODE-B: are you there?  (hops=0)
[2026-04-29 09:16:04] direct  ← NODE-B: yes, reading you  [delivered]

Session ended: 2026-04-29 09:45:12
```

#### Backup file format (JSON)

```json
{
  "node_name": "MY-NODE",
  "device_info": { "name": "MY-NODE", "radio_freq": 868.0, ... },
  "radio": {
    "Frequency (MHz)": 868.0,
    "Bandwidth (kHz)": 125,
    "Spreading Factor": 10,
    "Coding Rate": "4/5",
    "TX Power (dBm)": 22
  },
  "saved_at": "2026-04-29 09:45:00"
}
```

---

## 14. Firmware Guide

### 14.1 Recommended firmware

The **dt267 low-power fork** is the recommended firmware for Heltec V3 and V4:

**[github.com/dt267/MeshCore-Low-Power-Firmware-For-Heltec-V3-V4](https://github.com/dt267/MeshCore-Low-Power-Firmware-For-Heltec-V3-V4)**

Key features relevant to this application:

| Feature | Benefit |
|---|---|
| USB + BLE + TCP/WiFi simultaneously | Connect with any transport without reflashing |
| Single binary — auto-detects display | No need to choose OLED vs no-display build |
| V3, V4, V4.2, V4.3 all supported | One firmware for all hardware variants |
| Auto-ping compatible | Works with the 30-second serial idle timeout |
| Live stats API (`get_stats`) | Powers the Radio tab stats and NEXUS Health Orb |
| dt267 v1.13+ required for broadcast | `send_msg(None, text)` API for channel messages |

Also compatible: **meshcomod** (ALLFATHER-BV) — provides the same
multi-transport capability:
[github.com/ALLFATHER-BV/meshcomod](https://github.com/ALLFATHER-BV/meshcomod)

### 14.2 Flashing Heltec V3

1. Download the latest release from the dt267 firmware repository
2. Find the file `Heltec_v3_companion_radio_usb_tcp.bin` (or `_merged.bin`)
3. Enter flash mode: hold **BOOT** button, press and release **RESET**,
   then release **BOOT**
4. Flash with esptool:
   ```bash
   pip install esptool
   # Merged binary (includes bootloader — flash at 0x0):
   esptool.py --port /dev/ttyUSB0 write_flash 0x0 Heltec_v3_companion_radio_usb_tcp-merged.bin
   # App-only binary (flash at 0x10000 — requires existing bootloader):
   esptool.py --port /dev/ttyUSB0 write_flash 0x10000 Heltec_v3_companion_radio_usb_tcp.bin
   ```
5. Or use the [MeshCore Web Flasher](https://flasher.meshcore.co.uk) in Chrome/Edge

### 14.3 Flashing Heltec V4

**Official MeshCore firmware v1.15.0 or above is required for V4.**

1. Download the V4 binary from the dt267 firmware repository
2. **Easiest method (UF2):** Double-tap the **RESET** button — a USB drive
   called `RAK4631` appears on your computer. Drag the `.uf2` file onto it.
   The node flashes and reboots automatically.
3. **Alternative:** Use esptool as for V3 (use the `heltec_v4_` binary)
4. Or use the MeshCore Web Flasher

> **V4.2 black screen after flashing:** if the OLED stays black after
> flashing the merged binary, try the non-merged `.bin` flashed at offset
> `0x10000` instead. Your device must already have a valid bootloader from
> a previous flash. The merged binary includes its own bootloader which can
> conflict with existing ones.

> **V4.2 poor RX sensitivity:** if you experience high noise floor or poor
> receive sensitivity on a V4.2 board, a hardware modification to bypass the
> external LNA is documented in the firmware repository:
> `Bypass-External-LNA-on-Heltec-V4.md`

### 14.4 OTA firmware updates

With dt267 firmware you can update over WiFi without a USB cable:

1. Connect to your node (BLE or TCP)
2. In the **Channel** tab, create a channel named exactly `TerminalCLI` on
   the device via the button UI
3. Type `start ota` in the Channel send field and press **Enter**
4. The node broadcasts a WiFi access point named **`MeshCore-OTA`**
5. Connect your computer to that WiFi network
6. Open a browser and go to `http://192.168.4.1/update`
7. Upload the new `.bin` firmware file

### 14.5 Firmware limitations

The MeshCore Python companion API (which this application uses) provides a
read-only view of the device. The following **cannot** be done from this
application:

| Feature | How to do it instead |
|---|---|
| Change radio frequency/SF/BW/power | Device button UI → Radio Settings |
| Change node name | Device button UI → Device Name |
| Set WiFi SSID / password | Device button UI → WiFi Settings |
| Configure MQTT | Device button UI → MQTT Settings |
| Edit channel name/uplink/downlink | Device button UI → Channels |
| Set GPS polling interval | Device button UI → GPS Settings |
| Change node role (repeater, etc.) | Device button UI → Node Role |

All of these can also be changed via the **TerminalCLI** channel by typing
commands — refer to the MeshCore documentation for available commands.

---

## 15. Analytics Explained

The analytics engine (`analytics.py`) derives additional intelligence from
raw radio data. Here is exactly how each metric is calculated.

### Link quality score (0.0 – 1.0)

Combines RSSI and SNR using the following mappings and weights:

```
RSSI quality = clamp((RSSI + 140) / 80, 0.0, 1.0)
  where -140 dBm = 0.0 (dead), -60 dBm = 1.0 (excellent)

SNR quality  = clamp((SNR + 20) / 30, 0.0, 1.0)
  where -20 dB = 0.0 (dead), +10 dB = 1.0 (excellent)

Link quality = RSSI_quality × 0.60 + SNR_quality × 0.40
```

| Score | Label | Bar colour |
|---|---|---|
| ≥ 0.75 | Excellent | Green |
| ≥ 0.50 | Good | Yellow |
| ≥ 0.25 | Fair | Orange |
| < 0.25 | Poor | Red |

### Activity score (0.0 – 1.0)

How recently the contact was heard, linearly decaying over 24 hours:

```
Activity = max(0.0, 1.0 − age_in_seconds / 86400)
```

A contact heard 12 hours ago has an activity score of 0.5.

### Overall contact score (0.0 – 1.0)

```
Battery score = battery_percent / 100  (or 1.0 if battery unknown)
Overall = Link × 0.50 + Activity × 0.35 + Battery × 0.15
```

### Network health score (0 – 100)

```
Online fraction = online_node_count / total_node_count
Packet error rate (PER) = rx_errors / (tx_packets + rx_packets)

Health = (avg_link × 0.40 + online_fraction × 0.35 + (1 − PER) × 0.25) × 100
```

### Channel utilisation

Estimated from message rate relative to a conservative LoRa ceiling:

```
Utilisation = min(1.0, messages_per_hour / 300)
```

300 messages/hour is a conservative estimate of the maximum capacity of
LoRa at SF10/125 kHz for short text frames. Real capacity depends on your
actual spreading factor and bandwidth settings.

---

## 16. Troubleshooting

### Connection problems

| Problem | Solution |
|---|---|
| **meshcore not found** | `pip install meshcore` |
| **bleak not found** | `pip install bleak` |
| **BLE scan finds nothing** | Enable Bluetooth on your PC; on Linux: `bluetoothctl power on` |
| **BLE connects but disconnects immediately** | Check PIN — if node has a PIN set, enter it in Settings → BLE Security |
| **Serial "Permission denied" on Linux** | `sudo usermod -aG dialout $USER` then log out and back in |
| **Serial drops after ~30 seconds** | Enable Auto-ping in Settings (on by default); or switch to TCP |
| **TCP connection refused** | Check IP address (try `ping` first); check the node is on WiFi and showing the address on its OLED; default port is 4403 |
| **"Already connected" on retry** | Click ⏹ Disconnect first, then reconnect |
| **Connection error dialog on startup** | Previous session did not disconnect cleanly; dismiss and reconnect |

### Messaging problems

| Problem | Solution |
|---|---|
| **"Contact not found"** | Click 🔄 Contacts to refresh; check the spelling matches exactly |
| **"Broadcast failed — firmware may not support..."** | Upgrade to dt267 v1.13+ |
| **DMs always timeout** | Check the destination node is in RF range; verify it is running MeshCore firmware and is powered on |
| **Message appears in History but not in Channel/Direct tab** | Switch to the relevant tab; the tabs only show messages while they are active |
| **228-character warning on short messages** | You may have invisible characters (e.g. from copy-paste); clear the field and retype |

### Display and application problems

| Problem | Solution |
|---|---|
| **NEXUS opens blank** | Wait 2–3 seconds for the first data refresh; in demo mode data generates automatically |
| **Map shows no nodes** | Contacts are not broadcasting GPS; requires GPS-enabled firmware on remote nodes |
| **Live stats show nothing** | Requires dt267 v1.13+; older firmware does not include the stats API |
| **No desktop notifications** | Install plyer: `pip install plyer`; on Linux also install `libnotify-bin` |
| **No sound alerts** | On Linux install `pulseaudio-utils` (for paplay) or `alsa-utils` (for aplay) |
| **Application window is very small** | Resize manually; the window remembers its size between sessions |

### Hardware problems

| Problem | Solution |
|---|---|
| **OLED blank after flashing V4** | Flash non-merged `.bin` at offset `0x10000` |
| **V4.2 poor receive range** | See firmware repo for LNA bypass hardware mod |
| **Node not appearing as serial device** | Use a data cable, not a charge cable; try a different USB port |
| **Node not connecting over WiFi** | Confirm node shows an IP on its OLED; check router is not isolating WiFi clients |

---

## 17. Frequently Asked Questions

**Q: Does this application work without an internet connection?**

A: Yes, completely. All communication is over LoRa radio between your nodes.
The application and firmware require no internet access whatsoever.

**Q: How many nodes can I manage?**

A: The application connects to one node at a time. That node can see all other
nodes in the mesh. You can see up to 500 contacts in the local cache (the
`HISTORY_LIMIT` setting in `config.py`).

**Q: Can I use this for emergency communications?**

A: The application and firmware are suitable for amateur radio emergency
communications. Check your regional regulations regarding LoRa transmissions.
In the UK, the 868 MHz ISM band requires no licence. Always follow your
national radio regulations.

**Q: My messages are being relayed — what does the hop count mean?**

A: A hop count of 0 means the message came directly from the sender. A hop
count of 2 means the message was relayed by two intermediate nodes before
reaching you. Higher hop counts mean longer relay chains, which increases
latency but extends range.

**Q: Can I run multiple instances of the application?**

A: Yes, but each instance connects to its own node. They share the settings
file and notes/favourites files — changes in one instance will be visible in
the other after restart.

**Q: Why does the Serial connection drop after 30 seconds?**

A: The dt267 firmware deactivates the serial port after 30 seconds of idle
traffic to save power. The Auto-ping feature (enabled by default in Settings)
prevents this by sending a silent device query every 20 seconds. For persistent
desktop use, TCP is recommended as it has no idle timeout.

**Q: How do I update the firmware?**

A: See §14.4 for OTA updates over WiFi (no USB required). Or use the USB
flashing method in §14.2/14.3.

**Q: Can I use other LoRa hardware (RAK, TTGO, etc.)?**

A: MeshCore firmware supports various hardware. This application works with
any MeshCore node that supports the Python companion API. The dt267 firmware
currently targets Heltec V3/V4 only — for other hardware, check the main
MeshCore firmware repository or use the official MeshCore firmware.

**Q: What does "No ACK received" mean?**

A: The destination node did not confirm receipt within 30 seconds. This could
mean: the node is out of RF range; the node is powered off; the node is
running firmware that does not support ACK; or the message was lost in
transit. The message is not automatically retried.

**Q: Is the BLE PIN stored securely?**

A: The PIN is stored in plaintext in `~/.meshcore_nm/settings.json`. On a
shared computer, other users could read it. For sensitive deployments, enter
the PIN manually each time (leave the field in Settings blank) rather than
saving it.

---

## 18. Bridge Network — Detailed Guide

The Bridge Network feature connects geographically separate MeshCore
networks over the internet so that messages and contact telemetry flow
between them automatically — extending the effective mesh range across
any distance.

**Key facts:**
- Disabled by default — must be explicitly enabled in ⚙ Settings
- Channel messages are bridged; **direct messages are never bridged**
- Remote contacts appear with a ⟷ prefix to distinguish them from local ones
- Bridged channel messages show `[ORIGIN-NODE]` to identify their source network

---

### 18.1 How it works

```
Cornwall ──────► Bridge ──────► internet ──────► Bridge ◄────── London
  radio                         (WSS/TLS)                         radio
```

Each Node Manager instance with bridging enabled:
1. Connects as a WebSocket client to either a peer or the hub
2. Listens for channel messages from the local radio
3. Forwards them to all connected peers
4. Receives channel messages from peers and injects them onto the local LoRa channel
5. Periodically broadcasts local contact telemetry (GPS, RSSI, battery) to peers

**Loop prevention:** every bridged message has a UUID that is cached for
5 minutes. A message that arrives back at its origin is silently dropped.
Messages passing through more than 3 bridges are also dropped.

---

### 18.2 Peer-to-peer setup

Use this when you have exactly two locations and one of them has a
publicly reachable IP address (or can port-forward).

**Location A — the server side (needs a public IP or port-forward)**

1. Open ⚙ Settings → Bridge Network
2. Tick **Enable bridge**
3. Tick **Run as bridge server**
4. Set port (default 4404) — open this port in your firewall / router
5. Set a shared secret (e.g. `openssl rand -hex 16`)
6. Click 💾 Save settings

**Location B — the client side**

1. Open ⚙ Settings → Bridge Network
2. Tick **Enable bridge** only
3. In the Peers box enter: `ws://LOCATION_A_IP:4404`
   (or `wss://` if TLS is terminated by a reverse proxy)
4. Enter the same shared secret
5. Click 💾 Save settings

Both instances will connect, exchange a HELLO handshake, and begin relaying.
The **⟷ Bridge** tab confirms the connection and shows the peer name.

---

### 18.3 Hub setup (recommended)

The hub eliminates the need for port-forwarding on any client machine.
All instances connect outward to the hub as WebSocket clients.

**Requirements:**
- A VPS or server with a public IP address
- A domain name pointing to that IP
- Ports 80 and 443 open on the server firewall

**Quick setup (5 minutes):**

```bash
# 1. On your server — clone the repo and set up the hub
git clone https://github.com/2E0LXY/meshcore-node-manager.git
cd meshcore-node-manager/hub
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Install Caddy (Debian/Ubuntu)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# 3. Edit Caddyfile — replace yourdomain.com with your domain
nano Caddyfile

# 4. Start the hub (with a secret)
HUB_SECRET=your-secret-here python hub.py &

# 5. Start Caddy
caddy run --config Caddyfile
```

**Each Node Manager client:**

1. ⚙ Settings → Bridge Network
2. Tick **Enable bridge**
3. Peers box: `wss://yourdomain.com/hub`
4. Shared secret: same value as `HUB_SECRET` on the server
5. 💾 Save settings

The bridge starts automatically on the next radio connection.

**Hub ports (all internal — Caddy proxies them):**

| Port | Purpose |
|---|---|
| 9000 | WebSocket relay — clients connect here via Caddy |
| 9001 | Dashboard HTTP — serves the web UI |
| 9002 | Dashboard WebSocket — live data feed for the web UI |

Only ports 80 and 443 need to be open on the server.

---

### 18.4 Hub web dashboard

The hub serves a live web dashboard at `https://yourdomain.com`.

**Dashboard panels:**

| Panel | Shows |
|---|---|
| **Statistics row** | Connected clients, total frames received, relayed, dropped, uptime |
| **Connected Clients** | Node name, IP address, time connected, frames sent/received, last activity |
| **Live Frame Feed** | Every frame relayed through the hub in real time: timestamp, direction (←/→), frame type, message text |

**Frame types in the feed:**

| Type | Colour | Meaning |
|---|---|---|
| `hello` | Yellow | Client connected or reconnected |
| `channel_msg` | Green | Channel message relayed |
| `contact_upd` | Cyan | Contact telemetry (GPS, RSSI, battery) |
| `disconnect` | Red | Client disconnected |

The dashboard auto-reconnects if the browser loses connection to the hub.

---

### 18.5 Security

The shared secret is required in every WebSocket frame. Clients that send
a wrong or missing secret are disconnected immediately during the HELLO
handshake.

**Recommendations:**

- Generate a strong secret: `openssl rand -hex 32`
- Store it in `/etc/meshcore-hub.env` on the server (not in the command line)
- The dashboard has no login — if you want to restrict access, add Caddy
  `basicauth` to the `/` and `/dash` routes in the Caddyfile:
  ```
  basicauth {
      admin $2a$14$hashedpassword
  }
  ```
  Generate the hash: `caddy hash-password`
- For zero-trust deployments, put the entire hub behind a VPN
  (WireGuard or Tailscale) and remove public exposure

---

### 18.6 Running the hub as a service

To keep the hub running after reboot, install it as a systemd service:

```bash
# Create a dedicated user
sudo useradd -r -s /sbin/nologin -d /opt/meshcore-hub meshcore
sudo mkdir -p /opt/meshcore-hub
sudo cp -r /path/to/repo/hub/. /opt/meshcore-hub/
sudo chown -R meshcore:meshcore /opt/meshcore-hub

# Create the virtual environment
sudo -u meshcore bash -c "cd /opt/meshcore-hub && python3 -m venv venv && venv/bin/pip install -r requirements.txt"

# Set the secret
echo "HUB_SECRET=your-secret-here" | sudo tee /etc/meshcore-hub.env
sudo chmod 600 /etc/meshcore-hub.env

# Install the service
sudo cp /opt/meshcore-hub/hub.service /etc/systemd/system/meshcore-hub.service
sudo systemctl daemon-reload
sudo systemctl enable --now meshcore-hub

# Check it's running
sudo systemctl status meshcore-hub
sudo journalctl -u meshcore-hub -f
```

To update the hub:
```bash
cd /path/to/repo && git pull
sudo cp hub/hub.py /opt/meshcore-hub/
sudo systemctl restart meshcore-hub
```

---


## 19. Glossary

| Term | Definition |
|---|---|
| **ACK** | Acknowledgement — a confirmation from the destination node that it received your direct message |
| **BLE** | Bluetooth Low Energy — the Bluetooth 4.0+ protocol used to connect to the node wirelessly at short range |
| **Broadcast** | A message sent to all nodes in range, with no specific destination and no delivery confirmation |
| **Channel** | The public broadcast channel — all nodes receive all channel messages |
| **Companion radio** | The role of the MeshCore node when connected to a desktop or phone application — it acts as a radio gateway |
| **dBm** | Decibels relative to one milliwatt — the unit of radio signal power. More negative = weaker signal |
| **Direct message (DM)** | A private message sent to a specific named contact, with ACK tracking |
| **dt267** | The author/maintainer of the recommended low-power MeshCore firmware fork for Heltec hardware |
| **Firmware** | The software running on the radio node hardware. This application requires MeshCore firmware |
| **GPS** | Global Positioning System — contacts broadcast their coordinates if their node has GPS capability |
| **Heltec V3 / V4** | Heltec WiFi LoRa 32 V3 and V4 — the recommended hardware for this firmware |
| **Hop** | Each time a message is relayed by an intermediate node en route to the destination, that is one hop |
| **ISM band** | Industrial, Scientific and Medical radio band — unlicensed frequency bands where LoRa operates |
| **Link quality** | A composite score (0–100%) derived from RSSI and SNR indicating how strong and clean the radio link is |
| **LoRa** | Long Range — a radio modulation technique for long-range low-power communication |
| **Mesh network** | A network where every node can relay messages for others, extending range beyond direct radio reach |
| **MeshCore** | The open-source mesh radio firmware this application is designed to work with |
| **NEXUS** | The built-in animated analytics dashboard (Neural EXtended UX System) |
| **Node** | A single MeshCore radio device in the network |
| **OTA** | Over-The-Air — firmware update over WiFi without a USB cable |
| **PER** | Packet Error Rate — proportion of received packets that had errors |
| **Ping** | In this application, a device query sent to confirm the connection is alive |
| **RSSI** | Received Signal Strength Indicator — measures how strong the received radio signal is in dBm |
| **RTT** | Round-Trip Time — the time from sending a DM to receiving the ACK confirmation |
| **Serial** | USB serial connection — the node appears as a COM port or /dev/tty device |
| **SNR** | Signal-to-Noise Ratio — how much stronger the signal is than background noise, in dB |
| **Spreading Factor (SF)** | A LoRa parameter (SF7–SF12) controlling range vs data rate. Higher SF = longer range, slower |
| **TCP** | Transmission Control Protocol — used for the WiFi connection between the app and node |
| **TerminalCLI** | A special channel name that enables command-line control of the node over the radio |
| **TX Power** | Transmit power — how strong the radio signal is when transmitted, in dBm |
| **Bridge** | The software feature that connects separate MeshCore networks over the internet |
| **Hub** | The centralised WebSocket relay server that bridge clients connect to |
| **WSS** | WebSocket Secure — WebSocket protocol over TLS, analogous to HTTPS |
| **Caddy** | A modern web server that handles automatic TLS certificate provisioning |
| **Peer** | Another Node Manager instance connected to the same bridge or hub |
| **NEXUS** | The animated analytics dashboard built into the application |
| **Session log** | An automatic plain-text log file created for each radio connection session |
