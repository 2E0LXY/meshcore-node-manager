"""
dashboard.py — NEXUS: Neural EXtended UX System
MeshCore Node Manager  |  Original work

A real-time animated network operations centre (NOC) HUD.
Pure Tkinter canvas — no external dependencies beyond the standard library.

Design language: biopunk neural interface
- Radial radar with rotating sweep arm and contact arcs
- Animated signal-strength rings per contact
- Live RTT sparkline (last 30 deliveries)
- Hourly activity radial sunburst
- Network health orb with breathing glow
- Per-contact reliability bars
- Hop-count topology visualiser
- All elements react to live data every 500 ms
"""

import math
import time
import tkinter as tk

# ─────────────────────────────────────────────────────────────────────────────
# NEXUS colour palette — deep space + bioluminescence
# ─────────────────────────────────────────────────────────────────────────────
N = {
    "void":     "#03060f",   # deepest background
    "deep":     "#060d1a",   # panel backgrounds
    "mid":      "#0a1628",   # mid-layer
    "rim":      "#0f2040",   # borders / grid
    "dim":      "#1a3a5c",   # muted elements
    "faint":    "#243d5a",   # barely visible grid
    "text":     "#c8e8ff",   # primary text
    "sub":      "#5a8ab0",   # secondary text
    "ghost":    "#2a4a6a",   # ghost/inactive

    # Bioluminescent accents
    "cyan":     "#00f5ff",   # primary highlight
    "cyan2":    "#00c8d4",   # secondary cyan
    "teal":     "#00ffcc",   # teal glow
    "green":    "#39ff8a",   # signal good
    "yellow":   "#ffe040",   # signal fair
    "orange":   "#ff8c00",   # signal poor / warn
    "red":      "#ff2060",   # alert / critical
    "magenta":  "#ff00aa",   # special highlight
    "violet":   "#9d4edd",   # decorative

    # Glow variants (semi-transparent via stipple or darker)
    "cyan_dim":   "#003a3d",
    "green_dim":  "#0a2a18",
    "red_dim":    "#3a0015",
}

TWO_PI = 2 * math.pi


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _polar(cx, cy, r, angle_deg):
    a = math.radians(angle_deg - 90)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def _lerp(a, b, t):
    return a + (b - a) * t


def _hex_lerp(c1: str, c2: str, t: float) -> str:
    """Interpolate between two hex colours."""
    def _parse(c):
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    r1, g1, b1 = _parse(c1)
    r2, g2, b2 = _parse(c2)
    r = int(_lerp(r1, r2, t))
    g = int(_lerp(g1, g2, t))
    b = int(_lerp(b1, b2, t))
    return f"#{r:02x}{g:02x}{b:02x}"


def _score_colour(score: float) -> str:
    if score >= 0.75:
        return N["green"]
    if score >= 0.5:
        return N["yellow"]
    if score >= 0.25:
        return N["orange"]
    return N["red"]


# ─────────────────────────────────────────────────────────────────────────────
# Base animated panel — a Canvas widget that redraws itself
# ─────────────────────────────────────────────────────────────────────────────

class _Panel(tk.Canvas):

    REFRESH_MS = 50   # 20 fps base; heavy panels override

    def __init__(self, parent, w, h, **kw):
        super().__init__(parent, width=w, height=h,
                         bg=N["void"], highlightthickness=0, **kw)
        self._w = w
        self._h = h
        self._t = 0.0          # animation time in seconds
        self._running = False
        self.bind("<Destroy>", lambda _: self._stop())

    def start(self):
        self._running = True
        self._loop()

    def _stop(self):
        self._running = False

    def _loop(self):
        if not self._running:
            return
        self._t += self.REFRESH_MS / 1000.0
        self.delete("all")
        self.draw(self._t)
        self.after(self.REFRESH_MS, self._loop)

    def draw(self, t: float):
        """Override in subclasses."""

    # ── drawing primitives ────────────────────────────────────────────────────

    def _arc_ring(self, cx, cy, r, start, extent,
                  colour, width=1, dash_arg=None):
        x0, y0 = cx - r, cy - r
        x1, y1 = cx + r, cy + r
        kw = dict(outline=colour, width=width, style="arc",
                  start=start, extent=extent)
        if dash_arg:
            kw["dash"] = dash_arg
        self.create_arc(x0, y0, x1, y1, **kw)

    def _circle(self, cx, cy, r, fill="", outline="", width=1):
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill=fill, outline=outline, width=width)

    def _dot(self, cx, cy, r, colour):
        self._circle(cx, cy, r, fill=colour, outline="")

    def _glow_dot(self, cx, cy, r, colour, glow_r=None):
        """Draw a dot with a soft halo."""
        gr = glow_r or r * 3
        # Outer glow — dimmer rings
        for i in range(3):
            ratio = (3 - i) / 3
            dim = _hex_lerp(colour, N["void"], 0.6 + ratio * 0.35)
            gr2 = r + (gr - r) * ratio
            self._circle(cx, cy, gr2, outline=dim, width=1)
        self._dot(cx, cy, r, colour)

    def _text(self, x, y, text, colour=None, size=9, anchor="center",
              font="Consolas", bold=False):
        weight = "bold" if bold else "normal"
        self.create_text(x, y, text=text,
                         fill=colour or N["text"],
                         font=(font, size, weight),
                         anchor=anchor)

    def _line(self, points, colour, width=1, dash_pat=None):
        kw = dict(fill=colour, width=width, smooth=False)
        if dash_pat:
            kw["dash"] = dash_pat
        self.create_line(*points, **kw)

    def _polygon(self, points, fill="", outline="", width=1):
        self.create_polygon(*points, fill=fill, outline=outline,
                            width=width, smooth=False)


# ─────────────────────────────────────────────────────────────────────────────
# Panel 1 — NEURAL RADAR
# Rotating sweep arm, contact arcs coloured by link quality,
# range rings, bearing indicators, breathing glow on contact dots
# ─────────────────────────────────────────────────────────────────────────────

class RadarPanel(_Panel):

    REFRESH_MS = 40   # 25 fps for smooth rotation

    def __init__(self, parent, size=360):
        super().__init__(parent, size, size)
        self._size   = size
        self._cx     = size // 2
        self._cy     = size // 2
        self._r      = size // 2 - 20
        self._contacts_data = []   # list of dicts from analytics
        self._sweep_speed   = 36   # degrees per second

    def set_data(self, contacts_data: list):
        self._contacts_data = contacts_data

    def draw(self, t: float):
        cx, cy, r = self._cx, self._cy, self._r

        # ── Background grid rings ─────────────────────────────────────────
        for frac in (0.25, 0.5, 0.75, 1.0):
            ri = int(r * frac)
            self._arc_ring(cx, cy, ri, 0, 359, N["rim"], width=1)

        # ── Compass spokes ────────────────────────────────────────────────
        for deg in range(0, 360, 30):
            x1, y1 = _polar(cx, cy, r * 0.08, deg)
            x2, y2 = _polar(cx, cy, r,         deg)
            col = N["dim"] if deg % 90 != 0 else N["faint"]
            self._line([x1, y1, x2, y2], col, width=1,
                       dash_pat=(4, 6) if deg % 90 != 0 else None)

        # Compass labels
        for deg, lbl in ((0,"N"),(90,"E"),(180,"S"),(270,"W")):
            lx, ly = _polar(cx, cy, r + 12, deg)
            self._text(lx, ly, lbl, N["sub"], size=8)

        # ── Sweep arm ─────────────────────────────────────────────────────
        sweep_deg = (t * self._sweep_speed) % 360

        # Afterglow trail (fading arc behind sweep)
        for back in range(0, 80, 4):
            alpha = 1.0 - back / 80
            dim   = _hex_lerp(N["cyan2"], N["void"], 0.85 + alpha * 0.1)
            trail_deg = (sweep_deg - back) % 360
            self._arc_ring(cx, cy, r - 2, trail_deg - 2, 6,
                           dim, width=max(1, int(3 * alpha)))

        # Main sweep line
        sx, sy = _polar(cx, cy, r - 2, sweep_deg)
        self._line([cx, cy, sx, sy], N["cyan"], width=2)

        # ── Contact blips ─────────────────────────────────────────────────
        if not self._contacts_data:
            self._text(cx, cy + r // 2, "NO CONTACTS", N["ghost"], size=8)
        else:
            for i, cd in enumerate(self._contacts_data[:12]):
                # Spread contacts around the ring by index
                angle = (i / max(len(self._contacts_data), 1)) * 360
                # Use distance_km to set radial position if available
                dist = cd.get("distance_km")
                if dist is not None:
                    # Max visualised range: 20 km
                    radial_frac = min(1.0, dist / 20)
                else:
                    radial_frac = 0.4 + (i % 3) * 0.2

                br = r * radial_frac
                bx, by = _polar(cx, cy, br, angle)

                # Pulse: contact glows when the sweep passes over it
                sweep_diff = abs(((sweep_deg - angle + 180) % 360) - 180)
                pulse = max(0.0, 1.0 - sweep_diff / 25)

                colour = cd["link_colour"]
                dot_r  = 4 + int(pulse * 5)

                if pulse > 0.1:
                    glow_c = _hex_lerp(colour, N["cyan"], pulse * 0.5)
                    self._glow_dot(bx, by, dot_r + 2, glow_c, glow_r=dot_r + 12)
                self._glow_dot(bx, by, dot_r, colour, glow_r=dot_r + 6)

                # Name label
                name = cd["contact"].name[:8]
                lx = bx + (10 if bx >= cx else -10)
                anchor = "w" if bx >= cx else "e"
                self._text(lx, by - 8, name, N["sub"], size=7, anchor=anchor)

                # Link quality arc segment
                arc_r = br + 8
                self._arc_ring(cx, cy, arc_r, angle - 6, 12,
                               colour, width=2)

        # ── Centre node ───────────────────────────────────────────────────
        pulse_r = 6 + math.sin(t * 3) * 2
        self._glow_dot(cx, cy, int(pulse_r), N["cyan"], glow_r=18)
        self._text(cx, cy + 18, "NODE", N["cyan2"], size=7, bold=True)

        # ── Decorative outer ring ─────────────────────────────────────────
        self._arc_ring(cx, cy, r + 6, sweep_deg - 5, 20, N["cyan"], width=1)
        self._arc_ring(cx, cy, r + 10, 0, 359, N["rim"], width=1,
                       dash_arg=(3, 9))


# ─────────────────────────────────────────────────────────────────────────────
# Panel 2 — HEALTH ORB
# Breathing glowing sphere, network health score, status text
# ─────────────────────────────────────────────────────────────────────────────

class HealthOrb(_Panel):

    REFRESH_MS = 60

    def __init__(self, parent, size=200):
        super().__init__(parent, size, size)
        self._size   = size
        self._cx     = size // 2
        self._cy     = size // 2
        self._health = {"score": 0, "status_text": "OFFLINE",
                        "status_colour": N["ghost"],
                        "online_nodes": 0, "total_nodes": 0,
                        "avg_link": 0.0, "avg_battery": None,
                        "per_hour": 0, "channel_util": 0.0,
                        "packet_error_rate": 0.0}

    def set_data(self, health: dict):
        self._health = health

    def draw(self, t: float):
        cx, cy = self._cx, self._cy
        h = self._health
        score  = h["score"] / 100
        colour = h["status_colour"]

        # Outer breathing rings
        for ring in range(5, 0, -1):
            phase  = t * 1.2 + ring * 0.4
            breath = math.sin(phase) * 0.5 + 0.5
            ro     = 80 + ring * 8 + breath * 4
            alpha  = (1.0 - ring / 6) * score * 0.7
            dim    = _hex_lerp(colour, N["void"], 1.0 - alpha)
            self._arc_ring(cx, cy, int(ro), 0, 359, dim, width=1)

        # Core glow layers
        for layer in range(4, 0, -1):
            r   = 30 + layer * 10
            dim = _hex_lerp(colour, N["void"], 1.0 - score * (layer / 4) * 0.8)
            self._circle(cx, cy, r, fill=dim, outline="")

        # Score ring
        extent = int(score * 359)
        if extent > 0:
            self._arc_ring(cx, cy, 68, 90, -extent, colour, width=3)
        self._arc_ring(cx, cy, 68, 90, -(360 - extent), N["rim"], width=1)

        # Score text
        self._text(cx, cy - 6, str(h["score"]), colour, size=22, bold=True)
        self._text(cx, cy + 16, "HEALTH", N["sub"], size=8, bold=True)

        # Status text
        self._text(cx, cy + 36, h["status_text"], colour, size=8, bold=True)

        # Nodes online
        nn = f"{h['online_nodes']}/{h['total_nodes']}"
        self._text(cx, cy + 52, f"NODES  {nn}", N["sub"], size=8)

        # Stats row
        util = f"{h['channel_util'] * 100:.0f}%"
        per  = f"{h['packet_error_rate'] * 100:.1f}%"
        self._text(cx, cy + 66, f"UTIL {util}   PER {per}", N["ghost"], size=7)

        # Decorative tick marks
        for i in range(36):
            deg = i * 10
            r1  = 75 if i % 9 == 0 else (73 if i % 3 == 0 else 71)
            r2  = 80
            x1, y1 = _polar(cx, cy, r1, deg)
            x2, y2 = _polar(cx, cy, r2, deg)
            col = colour if i % 9 == 0 else N["rim"]
            self._line([x1, y1, x2, y2], col, width=1)


# ─────────────────────────────────────────────────────────────────────────────
# Panel 3 — RTT SPARKLINE
# Live rolling round-trip time graph with glow trail
# ─────────────────────────────────────────────────────────────────────────────

class RTTSparkline(_Panel):

    REFRESH_MS = 100
    POINTS = 30

    def __init__(self, parent, w=380, h=100):
        super().__init__(parent, w, h)
        self._w2 = w
        self._h2 = h
        self._series: list[tuple[float, float]] = []

    def set_data(self, rtt_series: list[tuple[float, float]]):
        self._series = rtt_series[-self.POINTS:]

    def draw(self, t: float):
        w, h = self._w2, self._h2
        pad  = 30
        dw   = w - pad * 2
        dh   = h - pad * 2

        # Title
        self._text(pad, 10, "ROUND-TRIP TIME", N["sub"], size=8,
                   anchor="w", bold=True)
        self._text(w - pad, 10, "ms", N["ghost"], size=8, anchor="e")

        # Grid
        for row in (0, 0.5, 1.0):
            y = pad + dh - int(row * dh)
            self._line([pad, y, w - pad, y], N["faint"], dash_pat=(2, 8))

        if not self._series:
            self._text(w // 2, h // 2, "AWAITING DATA", N["ghost"], size=9)
            return

        rtts   = [r for _, r in self._series]
        max_r  = max(rtts + [1.0])
        min_r  = 0.0
        span   = max_r - min_r or 1.0

        # Y-axis labels
        self._text(pad - 4, pad + dh, f"{min_r:.0f}", N["ghost"],
                   size=7, anchor="e")
        self._text(pad - 4, pad, f"{max_r*1000:.0f}", N["ghost"],
                   size=7, anchor="e")

        # Build point list
        pts = []
        for i, (_, r) in enumerate(self._series):
            x = pad + int(i / max(len(self._series) - 1, 1) * dw)
            y = pad + dh - int((r - min_r) / span * dh)
            pts.append((x, y))

        # Filled area under curve
        fill_pts = [pad, pad + dh]
        for x, y in pts:
            fill_pts += [x, y]
        fill_pts += [pts[-1][0], pad + dh]
        self._polygon(fill_pts, fill=N["cyan_dim"], outline="")

        # Line + glow
        if len(pts) >= 2:
            flat = [c for pt in pts for c in pt]
            self._line(flat, N["cyan2"], width=1)
            self._line(flat, N["cyan"],  width=2)

        # Current value dot
        lx, ly = pts[-1]
        self._glow_dot(lx, ly, 4, N["cyan"], glow_r=12)
        cur_val = self._series[-1][1] * 1000
        self._text(lx + 8, ly - 8, f"{cur_val:.0f}ms",
                   N["cyan"], size=8, anchor="w")

        # Scan line animation
        scan_x = pad + int(((t * 30) % dw))
        self._line([scan_x, pad, scan_x, pad + dh],
                   N["cyan_dim"], width=1, dash_pat=(2, 4))


# ─────────────────────────────────────────────────────────────────────────────
# Panel 4 — ACTIVITY SUNBURST
# 24-hour radial activity ring
# ─────────────────────────────────────────────────────────────────────────────

class ActivitySunburst(_Panel):

    REFRESH_MS = 100

    def __init__(self, parent, size=200):
        super().__init__(parent, size, size)
        self._size   = size
        self._cx     = size // 2
        self._cy     = size // 2
        self._hours  = [0] * 24

    def set_data(self, hourly: list[int]):
        self._hours = hourly

    def draw(self, t: float):
        cx, cy = self._cx, self._cy
        max_v = max(list(self._hours) + [1])
        r_min = 28
        r_max = 72

        # Title
        self._text(cx, 10, "24H ACTIVITY", N["sub"], size=8, bold=True)

        # Hour segments
        seg = 360 / 24
        import datetime
        current_h = datetime.datetime.now().hour
        for h in range(24):
            val    = self._hours[h] / max_v
            r_bar  = r_min + int(val * (r_max - r_min))
            angle  = h * seg - 90        # 0h at top
            pulse  = 1.0 + (0.12 * math.sin(t * 2 + h * 0.5))

            # Colour by time of day + intensity
            if val == 0:
                col = N["rim"]
            elif h == current_h:
                col = N["cyan"]
            else:
                col = _hex_lerp(N["teal"], N["magenta"], val)

            # Draw bar as thick arc segment
            self._arc_ring(cx, cy, int(r_bar * pulse),
                           angle, seg - 1, col, width=3)

            # Tick at r_min
            tx, ty = _polar(cx, cy, r_min - 4, angle + seg / 2)
            if h % 6 == 0:
                self._text(tx, ty, f"{h:02d}", N["ghost"], size=6)

        # Inner ring
        self._arc_ring(cx, cy, r_min - 1, 0, 359, N["rim"], width=1)

        # Centre
        msgs = sum(self._hours)
        self._text(cx, cy - 5, str(msgs), N["teal"], size=13, bold=True)
        self._text(cx, cy + 9, "MSGS", N["ghost"], size=7)

        # Current hour marker
        ca = current_h * seg - 90
        hx1, hy1 = _polar(cx, cy, r_min - 8, ca + seg / 2)
        hx2, hy2 = _polar(cx, cy, r_max + 8, ca + seg / 2)
        self._line([hx1, hy1, hx2, hy2], N["cyan"], width=1,
                   dash_pat=(2, 4))


# ─────────────────────────────────────────────────────────────────────────────
# Panel 5 — CONTACT SIGNAL BARS
# Animated per-contact signal quality bars with breathing glow
# ─────────────────────────────────────────────────────────────────────────────

class ContactBars(_Panel):

    REFRESH_MS = 80

    def __init__(self, parent, w=340, h=280):
        super().__init__(parent, w, h)
        self._w2 = w
        self._h2 = h
        self._contacts_data = []

    def set_data(self, contacts_data: list):
        self._contacts_data = contacts_data[:8]

    def draw(self, t: float):
        w, h = self._w2, self._h2
        self._text(10, 10, "CONTACT SIGNAL MATRIX", N["sub"],
                   size=8, anchor="w", bold=True)

        if not self._contacts_data:
            self._text(w // 2, h // 2, "NO CONTACTS", N["ghost"], size=9)
            return

        row_h = (h - 30) / max(len(self._contacts_data), 1)
        bar_w = w - 130

        for i, cd in enumerate(self._contacts_data):
            y  = 26 + i * row_h + row_h / 2
            c  = cd["contact"]
            lq = cd["link_score"]
            ov = cd["overall"]
            lq  = cd["link_score"]
            col = cd["link_colour"]

            # Pulse per contact
            pulse = 0.92 + 0.08 * math.sin(t * 2 + i * 1.1)

            # Name
            name = c.name[:10]
            self._text(10, y, name, N["text"], size=8, anchor="w")

            # Status dot
            age = cd["age_secs"]
            if age is not None and age < 60:
                dot_col = N["green"]
            elif age is not None and age < 600:
                dot_col = N["yellow"]
            else:
                dot_col = N["ghost"]
            self._glow_dot(92, y, 4, dot_col, glow_r=8)

            # Signal bar background
            bx = 102
            bw = int(bar_w * 0.55)
            bh = max(6, int(row_h * 0.38))
            self.create_rectangle(bx, y - bh // 2,
                                  bx + bw, y + bh // 2,
                                  fill=N["deep"], outline=N["rim"])

            # Fill
            fill_w = int(bw * lq * pulse)
            if fill_w > 2:
                # Gradient-ish: two overlapping rects
                self.create_rectangle(bx, y - bh // 2,
                                      bx + fill_w, y + bh // 2,
                                      fill=_hex_lerp(col, N["void"], 0.3),
                                      outline="")
                self.create_rectangle(bx, y - bh // 2 + 1,
                                      bx + fill_w, y,
                                      fill=col, outline="")

            # Percentage
            pct = f"{int(lq * 100)}%"
            self._text(bx + bw + 6, y, pct, col, size=8, anchor="w")

            # Battery indicator
            if c.battery is not None:
                batt_x = w - 28
                batt_col = N["green"] if c.battery >= 50 else (
                    N["yellow"] if c.battery >= 20 else N["red"])
                batt_h = int((row_h - 6) * c.battery / 100)
                self.create_rectangle(batt_x, y + row_h / 2 - 3 - batt_h,
                                      batt_x + 8, y + row_h / 2 - 3,
                                      fill=batt_col, outline=N["rim"])
                self.create_rectangle(batt_x, y - row_h / 2 + 3,
                                      batt_x + 8, y + row_h / 2 - 3,
                                      fill="", outline=N["rim"])

            # Overall score orb (right edge)
            ox = w - 16
            overall_col = _score_colour(ov)
            self._glow_dot(ox, y, 5, overall_col, glow_r=9)

            # Separator
            if i < len(self._contacts_data) - 1:
                self._line([10, y + row_h / 2, w - 10, y + row_h / 2],
                           N["faint"], dash_pat=(3, 9))


# ─────────────────────────────────────────────────────────────────────────────
# Panel 6 — HOP TOPOLOGY
# Visualises hop count distribution as concentric rings with flowing particles
# ─────────────────────────────────────────────────────────────────────────────

class HopTopology(_Panel):

    REFRESH_MS = 50

    def __init__(self, parent, size=200):
        super().__init__(parent, size, size)
        self._size  = size
        self._cx    = size // 2
        self._cy    = size // 2
        self._hops  = {}   # {hop_count: msg_count}

    def set_data(self, hop_dist: dict):
        self._hops = hop_dist

    def draw(self, t: float):
        cx, cy = self._cx, self._cy
        self._text(cx, 10, "HOP TOPOLOGY", N["sub"], size=8,
                   anchor="center", bold=True)

        if not self._hops:
            self._text(cx, cy, "NO HOP DATA", N["ghost"], size=8)
            return

        max_count = max(self._hops.values(), default=1)
        rings = sorted(self._hops.items())   # [(hops, count), ...]
        n_rings = max(len(rings), 1)

        for i, (hops, count) in enumerate(rings):
            r       = 20 + i * 20
            frac    = count / max_count
            colour  = _hex_lerp(N["teal"], N["magenta"], i / max(n_rings - 1, 1))

            # Ring
            self._arc_ring(cx, cy, r, 0, 359, colour, width=1)

            # Filled arc showing relative count
            extent = int(frac * 355) + 1
            self._arc_ring(cx, cy, r, 90, -extent, colour, width=3)

            # Animated particles flowing along ring
            for p in range(4):
                phase    = (t * 60 + p * 90 + hops * 30) % 360
                px, py   = _polar(cx, cy, r, phase)
                pulse    = 0.5 + 0.5 * math.sin(t * 4 + p)
                dot_col  = _hex_lerp(colour, N["cyan"], pulse * 0.6)
                self._glow_dot(int(px), int(py), 3, dot_col, glow_r=7)

            # Label
            lx, ly = _polar(cx, cy, r + 10, -60)
            self._text(int(lx), int(ly),
                       f"{hops}h:{count}", colour, size=7)

        # Centre node
        pulse_r = 5 + math.sin(t * 2) * 2
        self._glow_dot(cx, cy, int(pulse_r), N["cyan"], glow_r=14)


# ─────────────────────────────────────────────────────────────────────────────
# Panel 7 — RELIABILITY MATRIX
# Per-contact delivery reliability as a radial segment chart
# ─────────────────────────────────────────────────────────────────────────────

class ReliabilityMatrix(_Panel):

    REFRESH_MS = 120

    def __init__(self, parent, w=340, h=200):
        super().__init__(parent, w, h)
        self._w2 = w
        self._h2 = h
        self._reliability = {}   # {peer: {sent, delivered, timeout, rate}}

    def set_data(self, reliability: dict):
        self._reliability = reliability

    def draw(self, t: float):
        w, h = self._w2, self._h2
        self._text(10, 10, "DELIVERY RELIABILITY", N["sub"],
                   size=8, anchor="w", bold=True)

        if not self._reliability:
            self._text(w // 2, h // 2, "NO DM DATA", N["ghost"], size=9)
            return

        items  = list(self._reliability.items())[:7]
        row_h  = (h - 28) / max(len(items), 1)

        for i, (peer, data) in enumerate(items):
            y    = 26 + i * row_h + row_h / 2
            rate = data["rate"]
            col  = _score_colour(rate)
            pulse = 0.94 + 0.06 * math.sin(t * 1.8 + i)

            # Peer name
            self._text(10, y, peer[:10], N["text"], size=8, anchor="w")

            # Bar
            bx = 96
            bw = w - 180
            bh = max(5, int(row_h * 0.38))
            self.create_rectangle(bx, y - bh // 2, bx + bw, y + bh // 2,
                                  fill=N["deep"], outline=N["rim"])
            fill_w = int(bw * rate * pulse)
            if fill_w > 2:
                self.create_rectangle(bx, y - bh // 2,
                                      bx + fill_w, y + bh // 2,
                                      fill=_hex_lerp(col, N["void"], 0.25),
                                      outline="")
                self.create_rectangle(bx, y - bh // 2 + 1,
                                      bx + fill_w, y,
                                      fill=col, outline="")

            # Stats
            pct  = f"{rate * 100:.0f}%"
            info = f"{data['delivered']}/{data['sent']} ✓  {data['timeout']} ✗"
            self._text(bx + bw + 6, y - 5,  pct,  col,      size=8, anchor="w")
            self._text(bx + bw + 6, y + 5,  info, N["ghost"], size=7, anchor="w")

            if i < len(items) - 1:
                self._line([10, y + row_h / 2, w - 10, y + row_h / 2],
                           N["faint"], dash_pat=(3, 9))


# ─────────────────────────────────────────────────────────────────────────────
# Panel 8 — SIGNAL HISTORY WATERFALL
# Rolling heatmap: time (x) vs contact (y), colour = RSSI
# ─────────────────────────────────────────────────────────────────────────────

class SignalWaterfall(_Panel):

    REFRESH_MS = 200
    COLS = 60   # time columns

    def __init__(self, parent, w=380, h=160):
        super().__init__(parent, w, h)
        self._w2 = w
        self._h2 = h
        # { contact_name: deque of (rssi_quality, ts) }
        self._history: dict[str, list] = {}

    def push(self, name: str, rssi_q: float):
        if name not in self._history:
            self._history[name] = []
        self._history[name].append(rssi_q)
        if len(self._history[name]) > self.COLS:
            self._history[name].pop(0)

    def set_data(self, contacts_data: list):
        """Called on each data update; appends current RSSI quality."""
        for cd in contacts_data[:8]:
            self.push(cd["contact"].name, cd["link_score"])

    def draw(self, t: float):
        w, h = self._w2, self._h2
        self._text(10, 10, "SIGNAL WATERFALL", N["sub"],
                   size=8, anchor="w", bold=True)

        if not self._history:
            self._text(w // 2, h // 2, "AWAITING DATA", N["ghost"], size=9)
            return

        names = list(self._history.keys())[:8]
        n     = len(names)
        row_h = max(1, (h - 26) // n)
        col_w = max(1, (w - 80) // self.COLS)

        for ri, name in enumerate(names):
            series = self._history[name]
            ry     = 24 + ri * row_h

            # Row label
            self._text(10, ry + row_h // 2, name[:8], N["sub"],
                       size=7, anchor="w")

            # Waterfall cells
            for ci, val in enumerate(series):
                cx = 72 + ci * col_w
                # Colour: black → deep blue → cyan → white
                if val <= 0:
                    col = N["void"]
                elif val < 0.33:
                    col = _hex_lerp(N["void"], N["dim"], val * 3)
                elif val < 0.66:
                    col = _hex_lerp(N["dim"], N["cyan2"], (val - 0.33) * 3)
                else:
                    col = _hex_lerp(N["cyan2"], N["teal"], (val - 0.66) * 3)
                self.create_rectangle(cx, ry, cx + col_w - 1,
                                      ry + row_h - 1,
                                      fill=col, outline="")

            # Latest value indicator
            if series:
                lv   = series[-1]
                lc   = _score_colour(lv)
                lx   = 72 + len(series) * col_w + 4
                self._text(lx, ry + row_h // 2,
                           f"{int(lv * 100)}%", lc, size=7, anchor="w")

        # Time axis
        self._line([72, h - 8, w - 10, h - 8], N["rim"])
        self._text(72,     h - 4, "OLDEST", N["ghost"], size=6, anchor="w")
        self._text(w - 10, h - 4, "NOW",    N["ghost"], size=6, anchor="e")

        # Scan line
        scan_x = 72 + int(((t * 20) % ((w - 82))))
        self._line([scan_x, 22, scan_x, h - 10],
                   N["cyan_dim"], width=1, dash_pat=(1, 6))


# ─────────────────────────────────────────────────────────────────────────────
# NEXUS Dashboard Window
# ─────────────────────────────────────────────────────────────────────────────

class NexusDashboard(tk.Toplevel):
    """
    The NEXUS HUD — full-window animated network operations centre.
    Can be launched from AppWindow or standalone.
    Receives live data via update_data().
    """

    TITLE = "⬡ NEXUS — NETWORK OPERATIONS CENTRE"

    def __init__(self, parent=None, radio=None):
        super().__init__(parent)
        self.title(self.TITLE)
        self.configure(bg=N["void"])
        self.geometry("1400x860")
        self.minsize(1100, 700)

        self._radio = radio
        self._panels: list[_Panel] = []
        self._data_refresh_ms = 2000

        self._build()
        self._start_all()
        self._schedule_data()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Top bar ───────────────────────────────────────────────────────
        top = tk.Frame(self, bg=N["deep"], pady=3)
        top.pack(side="top", fill="x")

        self._title_var = tk.StringVar(value=self.TITLE)
        tk.Label(top, textvariable=self._title_var,
                 bg=N["deep"], fg=N["cyan"],
                 font=("Consolas", 11, "bold")).pack(side="left", padx=14)

        self._clock_var = tk.StringVar()
        tk.Label(top, textvariable=self._clock_var,
                 bg=N["deep"], fg=N["sub"],
                 font=("Consolas", 9)).pack(side="right", padx=14)
        self._tick_clock()

        self._node_var = tk.StringVar(value="NODE: OFFLINE")
        tk.Label(top, textvariable=self._node_var,
                 bg=N["deep"], fg=N["teal"],
                 font=("Consolas", 9)).pack(side="right", padx=20)

        # Separator
        tk.Frame(self, bg=N["cyan"], height=1).pack(fill="x")

        # ── Main grid ─────────────────────────────────────────────────────
        body = tk.Frame(self, bg=N["void"])
        body.pack(fill="both", expand=True, padx=4, pady=4)

        # Column weights
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=0)
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        # ── Left column ───────────────────────────────────────────────────
        left = tk.Frame(body, bg=N["void"])
        left.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 4))

        self._radar   = RadarPanel(left, size=360)
        self._radar.pack(pady=(0, 4))
        self._panels.append(self._radar)

        self._health_orb = HealthOrb(left, size=200)
        self._health_orb.pack()
        self._panels.append(self._health_orb)

        # ── Centre column ─────────────────────────────────────────────────
        centre = tk.Frame(body, bg=N["void"])
        centre.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=4)
        centre.rowconfigure(0, weight=0)
        centre.rowconfigure(1, weight=1)
        centre.rowconfigure(2, weight=0)
        centre.columnconfigure(0, weight=1)

        self._waterfall = SignalWaterfall(centre, w=0, h=160)
        self._waterfall.pack(fill="x", expand=False, pady=(0, 4))
        self._panels.append(self._waterfall)

        self._contact_bars = ContactBars(centre, w=0, h=0)
        self._contact_bars.pack(fill="both", expand=True, pady=4)
        self._panels.append(self._contact_bars)

        self._rtt_spark = RTTSparkline(centre, w=0, h=100)
        self._rtt_spark.pack(fill="x", expand=False, pady=(4, 0))
        self._panels.append(self._rtt_spark)

        # ── Right column ──────────────────────────────────────────────────
        right = tk.Frame(body, bg=N["void"])
        right.grid(row=0, column=2, rowspan=2, sticky="ns", padx=(4, 0))

        self._sunburst = ActivitySunburst(right, size=200)
        self._sunburst.pack(pady=(0, 4))
        self._panels.append(self._sunburst)

        self._hop_topo = HopTopology(right, size=200)
        self._hop_topo.pack(pady=4)
        self._panels.append(self._hop_topo)

        self._reliability = ReliabilityMatrix(right, w=340, h=0)
        self._reliability.pack(fill="both", expand=True, pady=(4, 0))
        self._panels.append(self._reliability)

        # ── Bottom status strip ───────────────────────────────────────────
        tk.Frame(self, bg=N["cyan"], height=1).pack(fill="x")
        bot = tk.Frame(self, bg=N["deep"], pady=2)
        bot.pack(side="bottom", fill="x")
        self._status_var = tk.StringVar(value="◉  NEXUS INITIALISING")
        tk.Label(bot, textvariable=self._status_var,
                 bg=N["deep"], fg=N["sub"],
                 font=("Consolas", 8)).pack(side="left", padx=10)
        tk.Label(bot, text="MeshCore Node Manager  ·  NEXUS v1.0",
                 bg=N["deep"], fg=N["ghost"],
                 font=("Consolas", 8)).pack(side="right", padx=10)

    def _start_all(self):
        for p in self._panels:
            p.start()

    def _tick_clock(self):
        self._clock_var.set(time.strftime("⬡ %Y-%m-%d  %H:%M:%S"))
        self.after(1000, self._tick_clock)

    # ── data pipeline ─────────────────────────────────────────────────────────

    def _schedule_data(self):
        self._refresh_data()
        self.after(self._data_refresh_ms, self._schedule_data)

    def _refresh_data(self):
        if self._radio is None:
            self._status_var.set("◉  NO RADIO — DEMO MODE")
            self._inject_demo_data()
            return

        try:
            from analytics import (
                contacts_summary, network_health,
                rtt_series, hourly_activity,
                hop_distribution, per_contact_reliability,
            )

            contacts = self._radio.get_contacts()
            messages = self._radio.message_history()
            stats    = self._radio.live_stats()

            # Own GPS (from device_info if available)
            own_lat = self._radio.device_info.get("lat")
            own_lon = self._radio.device_info.get("lon")

            cd   = contacts_summary(contacts, own_lat, own_lon)
            hlth = network_health(contacts, messages, stats)
            rtts = rtt_series(messages)
            hrly = hourly_activity(messages)
            hops = hop_distribution(messages)
            rely = per_contact_reliability(messages)

            self._radar.set_data(cd)
            self._health_orb.set_data(hlth)
            self._contact_bars.set_data(cd)
            self._waterfall.set_data(cd)
            self._rtt_spark.set_data(rtts)
            self._sunburst.set_data(hrly)
            self._hop_topo.set_data(hops)
            self._reliability.set_data(rely)

            nn = self._radio.node_name or "?"
            self._node_var.set(f"NODE: {nn.upper()}")
            self._status_var.set(
                f"◉  LIVE  │  "
                f"{hlth['online_nodes']}/{hlth['total_nodes']} NODES  │  "
                f"{hlth['per_hour']:.0f} MSG/H  │  "
                f"NET HEALTH {hlth['score']}")
        except Exception as exc:
            self._status_var.set(f"⚠  DATA ERROR: {exc}")

    def _inject_demo_data(self):
        """Feed synthetic data when no radio is connected — for UI preview."""
        import random
        from analytics import (
            contacts_summary, network_health,
            rtt_series, hourly_activity,
            hop_distribution, per_contact_reliability,
        )
        from radio import Contact, Message

        now = time.time()
        rng = random.Random(int(now / 10))  # changes every 10 s

        demo_contacts = [
            Contact(key=f"key{i:04x}", name=f"NODE-{chr(65+i)}",
                    last_heard=now - rng.uniform(0, 900),
                    rssi=rng.uniform(-120, -65),
                    snr=rng.uniform(-10, 10),
                    lat=51.5 + rng.uniform(-0.1, 0.1) if i < 5 else None,
                    lon=-0.1 + rng.uniform(-0.1, 0.1) if i < 5 else None,
                    battery=rng.randint(10, 100),
                    favourite=(i == 0))
            for i in range(8)
        ]

        demo_messages = []
        for j in range(60):
            ts    = now - rng.uniform(0, 86400)
            direc = rng.choice(["tx", "rx"])
            kind  = rng.choice(["direct", "channel"])
            peer  = rng.choice([c.name for c in demo_contacts])
            rtt_v = rng.uniform(0.3, 8.0) if direc == "tx" else None
            st    = rng.choice(["delivered", "timeout"]) if direc == "tx" else "received"
            hops  = rng.randint(0, 4) if direc == "rx" else None
            demo_messages.append(Message(
                local_id=j, direction=direc, kind=kind, peer=peer,
                text="demo", ts_sent=ts if direc == "tx" else None,
                ts_received=ts if direc == "rx" else None,
                ts_delivered=ts + rtt_v if rtt_v else None,
                rtt=rtt_v, hops=hops, status=st,
            ))

        cd   = contacts_summary(demo_contacts)
        hlth = network_health(demo_contacts, demo_messages, {})
        rtts = rtt_series(demo_messages)
        hrly = hourly_activity(demo_messages)
        hops = hop_distribution(demo_messages)
        rely = per_contact_reliability(demo_messages)

        self._radar.set_data(cd)
        self._health_orb.set_data(hlth)
        self._contact_bars.set_data(cd)
        self._waterfall.set_data(cd)
        self._rtt_spark.set_data(rtts)
        self._sunburst.set_data(hrly)
        self._hop_topo.set_data(hops)
        self._reliability.set_data(rely)

        self._node_var.set("NODE: DEMO")

    def _on_close(self):
        for p in self._panels:
            p._running = False  # pylint: disable=protected-access
        self.destroy()


# ── standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    dash = NexusDashboard(root, radio=None)
    root.mainloop()
