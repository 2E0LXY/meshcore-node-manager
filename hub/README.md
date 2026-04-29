# MeshCore Bridge Hub

A centralised WebSocket relay hub that multiple Node Manager instances
connect to — no port-forwarding required on any client machine.
Caddy provides automatic HTTPS/WSS via Let's Encrypt.

## Quick setup (5 minutes)

### 1. Get a server

Any VPS with a public IP and a domain name pointing to it.
Minimum: 1 vCPU, 512 MB RAM, Debian 12 / Ubuntu 22.04.
Recommended providers: Hetzner (€4/month), DigitalOcean, Vultr.

### 2. Install

```bash
# On the server
git clone https://github.com/2E0LXY/meshcore-node-manager.git
cd meshcore-node-manager/hub

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Install Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy
```

### 4. Configure

Edit `Caddyfile` — replace `yourdomain.com` with your actual domain:
```
yourdomain.com {
    ...
}
```

### 5. Start the hub

```bash
# Terminal 1 — start the hub
HUB_SECRET=your-secret-here python hub.py

# Terminal 2 — start Caddy
caddy run --config Caddyfile
```

Or run both as systemd services (see `hub.service`).

### 6. Connect Node Manager clients

In each Node Manager instance:
1. ⚙ Settings → Bridge Network
2. Tick **Enable bridge**
3. In the Peers box enter: `wss://yourdomain.com/hub`
4. Enter your shared secret
5. Save settings

### 7. View the dashboard

Open `https://yourdomain.com` in any browser. No login required
(add Caddy `basicauth` if you want access control).

## Ports

| Port | Purpose | Exposure |
|---|---|---|
| 9000 | WebSocket relay | Internal only (Caddy proxies) |
| 9001 | Dashboard HTTP | Internal only (Caddy proxies) |
| 9002 | Dashboard WebSocket | Internal only (Caddy proxies) |
| 80   | HTTP (Caddy, ACME challenge) | Public |
| 443  | HTTPS/WSS (Caddy, TLS) | Public |

Only ports 80 and 443 need to be open on the firewall.

## Running as a systemd service

```bash
# Create a dedicated user
sudo useradd -r -s /sbin/nologin -d /opt/meshcore-hub meshcore
sudo mkdir -p /opt/meshcore-hub
sudo cp -r . /opt/meshcore-hub/
sudo chown -R meshcore:meshcore /opt/meshcore-hub

# Set the secret
echo "HUB_SECRET=your-secret-here" | sudo tee /etc/meshcore-hub.env
sudo chmod 600 /etc/meshcore-hub.env

# Enable and start
sudo cp hub.service /etc/systemd/system/meshcore-hub.service
sudo systemctl daemon-reload
sudo systemctl enable --now meshcore-hub

# Check status
sudo systemctl status meshcore-hub
sudo journalctl -u meshcore-hub -f
```

## Dashboard

The dashboard at `https://yourdomain.com` shows:

- **Connected clients** — node name, IP address, time connected, frames sent/received
- **Live frame feed** — every message relayed through the hub in real time
- **Statistics** — total frames received, relayed, dropped; uptime

The dashboard auto-reconnects if the connection drops.

## Security

The shared secret provides basic access control. For production deployments:

- Use a strong random secret: `openssl rand -hex 32`
- Add IP allowlisting in the Caddyfile if clients have fixed IPs
- Consider putting the hub behind a VPN (WireGuard/Tailscale) for zero-trust access

## Command-line options

```
python hub.py --help

  --ws-port   WebSocket relay port    (default: 9000, env: HUB_WS_PORT)
  --web-port  Dashboard HTTP port     (default: 9001, env: HUB_WEB_PORT)
  --secret    Shared secret           (default: none, env: HUB_SECRET)
```
