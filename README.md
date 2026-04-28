# MeshCore Node Manager

A Python desktop application for connecting to and operating **MeshCore**
companion radio nodes over **USB serial**, **TCP/WiFi**, or **Bluetooth BLE**.

---

## Features

| Feature | Detail |
|---|---|
| **3 transports** | USB Serial, TCP/WiFi (port 4403), Bluetooth BLE |
| **BLE scanner** | Scans for nearby devices; MeshCore nodes highlighted green |
| **Contacts tab** | Sortable table with filter, recency colour, RSSI/SNR, battery %, GPS |
| **Channel tab** | Send and receive public LoRa channel broadcasts |
| **Direct tab** | DMs with contact autocomplete and ACK tracking |
| **History tab** | Full message history with RTT, delivery stats, success rate |
| **Radio tab** | Frequency, BW, SF, CR, TX power; live device stats |
| **Ping** | Re-query device to confirm connection alive |
| **Backup / Restore** | JSON snapshot of device info and radio parameters |
| **Export messages** | Save full message history to a plain-text file |
| **Save log** | Save the application log to a file |
| **228-char guard** | Live counter; warning if LoRa frame limit exceeded |
| **Event-bus architecture** | GUI and radio layer fully decoupled |
| **Dark theme** | Catppuccin Mocha palette |

---

## Recommended Firmware

For Heltec WiFi LoRa 32 **V3** and **V4**, use the dt267 low-power fork:

**[github.com/dt267/MeshCore-Low-Power-Firmware-For-Heltec-V3-V4](https://github.com/dt267/MeshCore-Low-Power-Firmware-For-Heltec-V3-V4)**

| Capability | Detail |
|---|---|
| Transports | USB + BLE + TCP/WiFi simultaneously in one binary |
| Hardware | V3, WSL3, V4 (V4.2 / V4.3 auto-detected) |
| Display | OLED vs no-display auto-detected at boot |
| OTA updates | `start ota` in the TerminalCLI channel |
| Battery life | V3 ≈ 7 days, V4 ≈ 3.5 days (2000 mAh, idle) |
| Low-battery cut | Deep sleep at 3.4 V, wake at 3.5 V |

> **V4 requirement:** official MeshCore firmware **v1.15.0+** is required for V4.

> **Serial idle note:** dt267 firmware deactivates the serial port after **30 s
> idle**. Use TCP for persistent desktop connections, or click **📡 Ping** to
> wake a dormant serial link.

---

## Requirements

- Python **3.10+**
- Tkinter — usually bundled; on Debian/Ubuntu: `sudo apt install python3-tk`

```
pip install meshcore bleak
```

| Package | Purpose |
|---|---|
| `meshcore` | MeshCore Python companion library |
| `bleak` | Cross-platform BLE (Windows / macOS / Linux) |

### BLE notes by platform

| OS | Notes |
|---|---|
| Windows 10/11 | Built-in; requires Bluetooth 4.0+ adapter |
| macOS | Python may request Bluetooth permission on first run |
| Linux | Run `bluetoothctl power on`; BlueZ required |

---

## Installation

```bash
git clone https://github.com/2E0LXY/meshcore-node-manager.git
cd meshcore-node-manager
pip install meshcore bleak
python main.py
```

**With a virtual environment (recommended):**

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install meshcore bleak
python main.py
```

---

## Quick Start

1. Flash your Heltec V3/V4 with dt267 firmware
2. `pip install meshcore bleak`
3. `python main.py`
4. Click **🔵 BLE** → **Scan** → double-click your node (green row)
5. **Contacts** tab populates; **Channel** tab shows incoming messages

---

## Connecting

### 🔵 BLE
1. Click **🔵 BLE** in the toolbar
2. Click **🔍 Scan (5 s)** — MeshCore nodes appear in green
3. Double-click a row, or select it and click **✅ Connect**
4. You can also type a MAC address or partial name directly

### 🌐 TCP
1. Click **🌐 TCP**
2. Enter the node's IP address (check your router's DHCP table or the node display)
3. Port defaults to **4403**

### 🔌 Serial (USB)
1. Plug in the node via USB-C data cable
2. Click **🔌 Serial**
3. Enter the port:
   - Windows: `COM3`, `COM4` … (check Device Manager)
   - Linux: `/dev/ttyUSB0` or `/dev/ttyACM0`
   - macOS: `/dev/cu.usbserial-*`
4. Linux permission fix: `sudo usermod -aG dialout $USER` then re-login

---

## Tabs

### 📡 Contacts
All contacts known to the connected node.
- **Filter** box narrows by name or key
- **Column headers** are clickable to sort
- Contacts heard within 10 minutes appear **green**; older contacts are dimmed
- **🔄 Refresh** reloads contacts from the device
- **🗑 Remove** removes selected contacts from the local cache (does not affect the device)

### 💬 Channel
Public LoRa channel broadcast.
- Sent messages in blue, received in green
- Live character counter — maximum **228 characters** per LoRa frame
- Press **Enter** or click **📤 Broadcast** to send

### 📨 Direct
Private direct messages to a specific contact.
- **To:** dropdown is auto-populated with contact names; start typing to filter
- ACK tracking: `pending → sent → delivered` or `timeout`
- Delivery confirmation and RTT appear inline after each sent message
- Press **Enter** or click **📨 Send DM** to send

### 📊 History
Full message history.
- Columns: Dir (↑/↓), Type, Peer, Message, Status, Time, RTT
- Row colours: green = delivered/received, red = timeout, blue = pending
- Stats bar: total, sent, received, delivered, timeout, pending, avg RTT, success %
- **🗑 Clear History** wipes in-memory history only

### 📻 Radio
Radio configuration read from the device at connect time.
- Frequency, bandwidth, spreading factor, coding rate, TX power
- **Live Device Stats** — click **🔄 Refresh** to fetch TX/RX counters
- Write-back is not available (MeshCore Python API limitation); use the device
  button UI or TerminalCLI to change settings

### 📋 Log
Colour-coded application log.

| Colour | Meaning |
|---|---|
| Green | Success (connected, delivered, backup saved) |
| Yellow | Warning (timeout, disconnect issues) |
| Red | Error (connection failed, contact not found) |
| Cyan | Info (message sent, disconnected) |
| Grey | Debug / muted |

---

## Toolbar Reference

| Button | Action |
|---|---|
| 🔌 Serial | Connect via USB serial |
| 🌐 TCP | Connect via TCP/WiFi |
| 🔵 BLE | Open BLE scanner and connect |
| ⏹ Disconnect | Clean disconnect |
| 🔄 Contacts | Reload contact list from device |
| 📡 Ping | Re-query device (useful after serial idle timeout) |
| 💾 Backup | Save device info + radio params to JSON |
| 📂 Load Backup | Load and display a saved JSON backup |
| 📝 Export Msgs | Save message history to plain text |
| ℹ Info | Show raw device info popup |

---

## Firmware Limitations

The MeshCore Python companion API does not expose a writable config tree.
These features are therefore **not available**:

- WiFi, MQTT, LoRa, GPS, display config write-back
- Channel name / uplink / downlink editing
- Node role, region, modem preset
- `setOwner`, `beginSettingsTransaction`

Use the **device button UI** or the **TerminalCLI** channel instead.
Create a channel named `TerminalCLI` on the device, then type commands
in the Channel tab.

**Broadcast:** uses `send_msg(None, text)` — works on dt267 v1.13+ and
meshcomod. If you see "Broadcast failed" in the log, upgrade firmware.

---

## Project Structure

```
meshcore-node-manager/
├── main.py      # Entry point
├── app.py       # AppWindow (Tk), all tabs, dialogs
├── radio.py     # NodeRadio — device connection and messaging
├── events.py    # EventBus — decouples GUI from radio layer
├── config.py    # Theme tokens, defaults, constants
├── helpers.py   # Pure utility functions
├── README.md
└── LICENSE      # MIT
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `meshcore` not found | `pip install meshcore` |
| `bleak` not found | `pip install bleak` |
| BLE scan empty | Check Bluetooth is on; on Linux run `bluetoothctl power on` |
| Serial "Permission denied" (Linux) | `sudo usermod -aG dialout $USER` then re-login |
| Serial drops after ~30 s | dt267 serial idle timeout — click **📡 Ping** or switch to TCP |
| "Contact not found" on DM | Click **🔄 Contacts** to refresh; check spelling |
| "Broadcast failed" | Firmware doesn't support `send_msg(None, text)` — upgrade to dt267 v1.13+ |
| Stats show nothing | Requires dt267 v1.13+ or meshcomod firmware |
| Black screen on V4 after flash | Flash non-merged `.bin` at offset `0x10000` if bootloader already present |

---

## Contributing

```bash
git checkout -b feature/my-feature
# make changes
python3 -m pyflakes *.py   # must be clean
git commit -m "Add my feature"
git push origin feature/my-feature
# open a Pull Request
```

---

## Acknowledgements

- **meshcore-dev** — [MeshCore firmware](https://github.com/meshcore-dev/MeshCore) and [meshcore Python library](https://github.com/meshcore-dev/meshcore_py)
- **dt267** — [Low-power Heltec V3/V4 firmware](https://github.com/dt267/MeshCore-Low-Power-Firmware-For-Heltec-V3-V4)
- **ALLFATHER-BV** — [meshcomod multi-transport firmware](https://github.com/ALLFATHER-BV/meshcomod)

---

## License

MIT — see [LICENSE](LICENSE)
