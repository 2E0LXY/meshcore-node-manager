"""
analytics.py — real-time analytics engine derived from NodeRadio data
MeshCore Node Manager  |  Original work

All functions are pure: they take snapshots from NodeRadio and return
structured dicts suitable for display or plotting.
"""
import math
import time
from collections import defaultdict

from radio import Contact, Message


# ── link quality ──────────────────────────────────────────────────────────────

def rssi_quality(rssi: float | None) -> float:
    """Map RSSI (dBm) to a 0.0–1.0 quality score."""
    if rssi is None:
        return 0.0
    # Typical LoRa range: -140 dBm (dead) to -60 dBm (excellent)
    return max(0.0, min(1.0, (rssi + 140) / 80))


def snr_quality(snr: float | None) -> float:
    """Map SNR (dB) to a 0.0–1.0 quality score."""
    if snr is None:
        return 0.0
    # Typical LoRa range: -20 dB (dead) to +10 dB (excellent)
    return max(0.0, min(1.0, (snr + 20) / 30))


def link_quality(contact: Contact) -> float:
    """
    Combined link quality score 0.0–1.0.
    Weights RSSI 60%, SNR 40%.
    """
    rq = rssi_quality(contact.rssi)
    sq = snr_quality(contact.snr)
    return rq * 0.6 + sq * 0.4


def link_label(score: float) -> str:
    if score >= 0.75:
        return "Excellent"
    if score >= 0.5:
        return "Good"
    if score >= 0.25:
        return "Fair"
    return "Poor"


def link_colour(score: float) -> str:
    """Return a hex colour from red → yellow → green based on score."""
    if score >= 0.75:
        return "#a6e3a1"   # green
    if score >= 0.5:
        return "#f9e2af"   # yellow
    if score >= 0.25:
        return "#fab387"   # orange
    return "#f38ba8"       # red


# ── distance ──────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float,
                 lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two GPS coordinates."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1: float, lon1: float,
                lat2: float, lon2: float) -> float:
    """Bearing in degrees (0 = North) from point 1 to point 2."""
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(math.radians(lat2))
    y = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) -
         math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ── contact analytics ─────────────────────────────────────────────────────────

def contact_age_secs(contact: Contact) -> float | None:
    if contact.last_heard is None:
        return None
    return time.time() - contact.last_heard


def activity_score(contact: Contact) -> float:
    """
    0.0–1.0 recency score: 1.0 = heard just now, 0.0 = not heard in 24 h.
    """
    age = contact_age_secs(contact)
    if age is None:
        return 0.0
    return max(0.0, 1.0 - age / 86400)


def contacts_summary(contacts: list[Contact],
                     own_lat: float | None = None,
                     own_lon: float | None = None) -> list[dict]:
    """
    Returns one dict per contact with all derived analytics fields:
    link_score, link_label, link_colour, activity_score, age_secs,
    distance_km, bearing_deg, battery_ok, overall_score.
    """
    out = []
    for c in contacts:
        lq   = link_quality(c)
        act  = activity_score(c)
        age  = contact_age_secs(c)

        dist = bearing = None
        if (own_lat is not None and own_lon is not None and
                c.lat is not None and c.lon is not None):
            dist    = haversine_km(own_lat, own_lon, c.lat, c.lon)
            bearing = bearing_deg(own_lat, own_lon, c.lat, c.lon)

        batt_ok = (c.battery is None or c.battery >= 20)

        # Overall score: link 50%, activity 35%, battery penalty 15%
        batt_score = 1.0 if c.battery is None else min(1.0, c.battery / 100)
        overall = lq * 0.50 + act * 0.35 + batt_score * 0.15

        out.append({
            "contact":      c,
            "link_score":   lq,
            "link_label":   link_label(lq),
            "link_colour":  link_colour(lq),
            "activity":     act,
            "age_secs":     age,
            "distance_km":  dist,
            "bearing_deg":  bearing,
            "battery_ok":   batt_ok,
            "overall":      overall,
        })

    out.sort(key=lambda x: x["overall"], reverse=True)
    return out


# ── message analytics ─────────────────────────────────────────────────────────

def message_rate(messages: list[Message],
                 window_secs: float = 3600) -> float:
    """Messages received/sent in the last window_secs (default 1 hour)."""
    cutoff = time.time() - window_secs
    return sum(1 for m in messages
               if (m.ts_received or m.ts_sent or 0) >= cutoff)


def hourly_activity(messages: list[Message]) -> list[int]:
    """
    Returns a list of 24 ints — message count per hour of the day (0–23).
    Useful for a heatmap / radial activity chart.
    """
    buckets = [0] * 24
    for m in messages:
        ts = m.ts_received or m.ts_sent
        if ts:
            import datetime
            h = datetime.datetime.fromtimestamp(ts).hour
            buckets[h] += 1
    return buckets


def rtt_series(messages: list[Message]) -> list[tuple[float, float]]:
    """
    Returns [(timestamp, rtt_secs), ...] for delivered DMs only.
    Suitable for an RTT trend sparkline.
    """
    return [
        (m.ts_delivered, m.rtt)
        for m in messages
        if m.status == "delivered" and m.rtt is not None
           and m.ts_delivered is not None
    ]


def per_contact_reliability(messages: list[Message]) -> dict[str, dict]:
    """
    Returns { peer_name: { sent, delivered, timeout, rate } }
    for all direct messages.
    """
    data: dict[str, dict] = defaultdict(
        lambda: {"sent": 0, "delivered": 0, "timeout": 0})
    for m in messages:
        if m.kind != "direct" or m.direction != "tx":
            continue
        data[m.peer]["sent"] += 1
        if m.status == "delivered":
            data[m.peer]["delivered"] += 1
        elif m.status == "timeout":
            data[m.peer]["timeout"] += 1
    result = {}
    for peer, d in data.items():
        rate = d["delivered"] / d["sent"] if d["sent"] else 0.0
        result[peer] = {**d, "rate": rate}
    return result


def hop_distribution(messages: list[Message]) -> dict[int, int]:
    """
    Returns { hop_count: message_count } for received messages with hop data.
    """
    dist: dict[int, int] = defaultdict(int)
    for m in messages:
        if m.direction == "rx" and m.hops is not None:
            dist[m.hops] += 1
    return dict(sorted(dist.items()))


def network_health(contacts: list[Contact],
                   messages: list[Message],
                   stats: dict) -> dict:
    """
    Returns a single network health dict:
    score (0–100), online_nodes, avg_link, avg_battery, per_hour,
    packet_error_rate, channel_utilisation, status_text, status_colour.
    """
    now = time.time()
    online = [c for c in contacts
              if c.last_heard and now - c.last_heard < 600]
    avg_link = (sum(link_quality(c) for c in online) / len(online)
                if online else 0.0)
    batts = [c.battery for c in contacts if c.battery is not None]
    avg_batt = sum(batts) / len(batts) if batts else None

    per_hour = message_rate(messages, 3600)

    # Packet error rate from live stats
    rx_errors = stats.get("recv_errors", stats.get("rx_errors", 0)) or 0
    tx_total  = stats.get("tx_packets", stats.get("sent_packets", 0)) or 0
    rx_total  = stats.get("rx_packets", stats.get("recv_packets", 0)) or 0
    total_pkts = (tx_total + rx_total) or 1
    per = rx_errors / total_pkts

    # Channel utilisation: rough estimate from message rate
    # LoRa at SF10/125kHz can carry ~4-6 short frames/minute
    max_rate = 300  # msgs/hour conservative ceiling
    util = min(1.0, per_hour / max_rate)

    # Composite score
    node_score = min(1.0, len(online) / max(len(contacts), 1))
    score = int((avg_link * 0.4 + node_score * 0.35 +
                 (1.0 - per) * 0.25) * 100)

    if score >= 75:
        status_text   = "Network Healthy"
        status_colour = "#a6e3a1"
    elif score >= 50:
        status_text   = "Network Degraded"
        status_colour = "#f9e2af"
    else:
        status_text   = "Network Critical"
        status_colour = "#f38ba8"

    return {
        "score":          score,
        "online_nodes":   len(online),
        "total_nodes":    len(contacts),
        "avg_link":       avg_link,
        "avg_battery":    avg_batt,
        "per_hour":       per_hour,
        "packet_error_rate": per,
        "channel_util":   util,
        "status_text":    status_text,
        "status_colour":  status_colour,
    }
