"""
app.py — AppWindow: main Tkinter application window
MeshCore Node Manager  |  Original work

Architecture
------------
AppWindow owns a NodeRadio and an EventBus.
All state changes flow through the bus — no tab ever calls NodeRadio directly
(except through AppWindow helper methods).
Tabs inherit from TabBase which provides self.radio, self.bus, self.after_tk.
"""

import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import C, LOG_COLOURS, TCP_DEFAULT_PORT
from events import (
    EventBus,
    EV_CONNECTED, EV_DISCONNECTED, EV_CONN_ERROR,
    EV_CONTACTS_UPD,
    EV_MSG_CHANNEL, EV_MSG_DIRECT, EV_MSG_SENT,
    EV_MSG_DELIVERED, EV_MSG_TIMEOUT,
    EV_LOG,
)
from helpers import ts_to_hms, fmt_rtt, safe_str
from radio import NodeRadio


# ════════════════════════════════════════════════════════════════════════════
# TabBase
# ════════════════════════════════════════════════════════════════════════════

class TabBase(ttk.Frame):
    """Common base for all tab widgets."""

    def __init__(self, parent, radio: NodeRadio, bus: EventBus, root: tk.Tk):
        super().__init__(parent)
        self.radio    = radio
        self.bus      = bus
        self._root    = root

    def after_tk(self, fn, *args):
        """Schedule fn(*args) on the Tk main thread."""
        self._root.after(0, lambda: fn(*args))

    def _bg(self, fn, done=None):
        """Run fn() in a daemon thread; call done(result) on Tk thread."""
        def worker():
            result = fn()
            if done:
                self.after_tk(done, result)
        threading.Thread(target=worker, daemon=True).start()


# ════════════════════════════════════════════════════════════════════════════
# Tab: Contacts
# ════════════════════════════════════════════════════════════════════════════

class ContactsTab(TabBase):

    def __init__(self, parent, radio, bus, root):
        super().__init__(parent, radio, bus, root)
        self._sort_col = ""
        self._sort_rev = False
        self._build()
        bus.on(EV_CONTACTS_UPD, lambda **_: self.after_tk(self.refresh))
        bus.on(EV_CONNECTED,    lambda **_: self.after_tk(self.refresh))
        bus.on(EV_DISCONNECTED, lambda **_: self.after_tk(self._clear))

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Label(bar, text="Filter:").pack(side="left")
        self._fv = tk.StringVar()
        self._fv.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(bar, textvariable=self._fv, width=24).pack(side="left", padx=4)
        ttk.Button(bar, text="🔄 Refresh",
                   command=lambda: self._bg(self.radio.refresh_contacts,
                                            lambda _: self.refresh())
                   ).pack(side="left", padx=4)
        ttk.Button(bar, text="🗑 Remove",
                   command=self._remove).pack(side="left", padx=4)
        self._count_lbl = ttk.Label(bar, foreground=C["muted"])
        self._count_lbl.pack(side="left", padx=8)

        cols   = ("Name", "Key", "SNR", "RSSI", "Batt %", "Last Heard", "GPS")
        widths = (160, 130, 55, 58, 60, 90, 210)
        self._tree = ttk.Treeview(self, columns=cols, show="headings")
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col,
                               command=lambda c=col: self._sort(c))
            self._tree.column(col, width=w, anchor="w")
        self._tree.tag_configure("fresh", foreground=C["ok"])
        self._tree.tag_configure("stale", foreground=C["muted"])
        sb = ttk.Scrollbar(self, orient="vertical",
                           command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")

    def refresh(self):
        contacts = self.radio.get_contacts()
        filt = self._fv.get().lower()
        self._tree.delete(*self._tree.get_children())
        now = time.time()
        shown = 0
        for c in contacts:
            if filt and filt not in c.name.lower() and filt not in c.key.lower():
                continue
            age = (now - c.last_heard) if c.last_heard else 99999
            tag = "fresh" if age < 600 else "stale"
            gps = (f"{c.lat:.5f}, {c.lon:.5f}"
                   if c.lat is not None and c.lon is not None else "")
            self._tree.insert("", "end", iid=c.key, tags=(tag,),
                              values=(c.name, c.key,
                                      safe_str(c.snr), safe_str(c.rssi),
                                      safe_str(c.battery),
                                      ts_to_hms(c.last_heard), gps))
            shown += 1
        total = len(contacts)
        self._count_lbl.config(
            text=f"{shown} of {total}" if filt else f"{total} contact(s)")

    def _clear(self):
        self._tree.delete(*self._tree.get_children())
        self._count_lbl.config(text="")

    def _sort(self, col):
        rows = [(self._tree.set(k, col), k)
                for k in self._tree.get_children("")]
        rev = (self._sort_col == col and not self._sort_rev)
        rows.sort(reverse=rev)
        for i, (_, k) in enumerate(rows):
            self._tree.move(k, "", i)
        self._sort_col, self._sort_rev = col, rev

    def _remove(self):
        for key in self._tree.selection():
            self.radio.remove_contact(key)
        self.refresh()


# ════════════════════════════════════════════════════════════════════════════
# Tab: Channel
# ════════════════════════════════════════════════════════════════════════════

class ChannelTab(TabBase):

    def __init__(self, parent, radio, bus, root):
        super().__init__(parent, radio, bus, root)
        self._build()
        bus.on(EV_MSG_CHANNEL, lambda **kw: self.after_tk(self._append_rx, kw))
        bus.on(EV_DISCONNECTED, lambda **_: self.after_tk(self._reset))

    def _build(self):
        self._txt = tk.Text(self, bg=C["bg2"], fg=C["fg"],
                            state="disabled", wrap="word",
                            font=("Consolas", 10))
        self._txt.tag_configure("ts",   foreground=C["muted"])
        self._txt.tag_configure("tx",   foreground=C["accent"])
        self._txt.tag_configure("rx",   foreground=C["ok"])
        sb = ttk.Scrollbar(self, orient="vertical", command=self._txt.yview)
        self._txt.configure(yscrollcommand=sb.set)
        self._txt.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y", pady=4)

        bot = ttk.Frame(self)
        bot.pack(side="bottom", fill="x", padx=6, pady=4)
        self._mv = tk.StringVar()
        ent = ttk.Entry(bot, textvariable=self._mv, width=70)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _: self._send())
        self._cc = ttk.Label(bot, text="0 / 228", foreground=C["muted"])
        self._cc.pack(side="left", padx=4)
        self._mv.trace_add("write", lambda *_:
            self._cc.config(text=f"{len(self._mv.get())} / 228"))
        ttk.Button(bot, text="📤 Broadcast",
                   command=self._send).pack(side="left", padx=4)

    def _send(self):
        text = self._mv.get().strip()
        if not text:
            return
        if len(text) > 228:
            messagebox.showwarning("Too long",
                                   "Maximum 228 characters per LoRa frame.")
            return
        lid = self.radio.transmit_channel(text)
        if lid is not None:
            self._write(f"[{ts_to_hms(time.time())}] ", "ts")
            self._write(f"me: {text}\n", "tx")
        self._mv.set("")

    def _append_rx(self, kw):
        self._write(f"[{ts_to_hms(kw['ts'])}] ", "ts")
        self._write(f"{kw['sender']}: {kw['text']}\n", "rx")

    def _write(self, text, tag=""):
        self._txt.configure(state="normal")
        self._txt.insert("end", text, tag)
        self._txt.configure(state="disabled")
        self._txt.see("end")

    def _reset(self):
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.configure(state="disabled")


# ════════════════════════════════════════════════════════════════════════════
# Tab: Direct Messages
# ════════════════════════════════════════════════════════════════════════════

class DirectTab(TabBase):

    def __init__(self, parent, radio, bus, root):
        super().__init__(parent, radio, bus, root)
        self._build()
        bus.on(EV_MSG_DIRECT,    lambda **kw: self.after_tk(self._append_rx, kw))
        bus.on(EV_MSG_DELIVERED, lambda **kw: self.after_tk(
            self._append_note,
            f"✅ Delivered  (RTT {fmt_rtt(kw.get('rtt'))})" if kw.get('rtt')
            else "✅ Delivered"))
        bus.on(EV_MSG_TIMEOUT,   lambda **kw: self.after_tk(
            self._append_note, "⏱ Timeout — no ACK received"))
        bus.on(EV_CONTACTS_UPD,  lambda **_: self.after_tk(self._update_dest_list))
        bus.on(EV_CONNECTED,     lambda **_: self.after_tk(self._update_dest_list))
        bus.on(EV_DISCONNECTED,  lambda **_: self.after_tk(self._reset))

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="To:").pack(side="left")
        self._dv = tk.StringVar()
        self._dcb = ttk.Combobox(top, textvariable=self._dv,
                                  width=22, state="normal")
        self._dcb.pack(side="left", padx=4)
        ttk.Label(top, text="Message:").pack(side="left")
        self._mv = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self._mv, width=44)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _: self._send())
        self._cc = ttk.Label(top, text="", foreground=C["muted"])
        self._cc.pack(side="left", padx=4)
        self._mv.trace_add("write", lambda *_:
            self._cc.config(text=f"{len(self._mv.get())} / 228"))
        ttk.Button(top, text="📨 Send DM",
                   command=self._send).pack(side="left")

        self._txt = tk.Text(self, bg=C["bg2"], fg=C["fg"],
                            state="disabled", wrap="word",
                            font=("Consolas", 10))
        self._txt.tag_configure("ts",    foreground=C["muted"])
        self._txt.tag_configure("tx",    foreground=C["accent"])
        self._txt.tag_configure("rx",    foreground=C["ok"])
        self._txt.tag_configure("note",  foreground=C["muted"],
                                font=("Consolas", 9, "italic"))
        sb = ttk.Scrollbar(self, orient="vertical", command=self._txt.yview)
        self._txt.configure(yscrollcommand=sb.set)
        self._txt.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")

    def _send(self):
        dest = self._dv.get().strip()
        text = self._mv.get().strip()
        if not dest or not text:
            return
        if len(text) > 228:
            messagebox.showwarning("Too long",
                                   "Maximum 228 characters per LoRa frame.")
            return
        lid = self.radio.transmit_direct(dest, text)
        if lid is not None:
            self._write(f"[{ts_to_hms(time.time())}] ", "ts")
            self._write(f"me → {dest}: {text}\n", "tx")
        self._mv.set("")

    def _append_rx(self, kw):
        self._write(f"[{ts_to_hms(kw['ts'])}] ", "ts")
        self._write(f"{kw['sender']}: {kw['text']}\n", "rx")

    def _append_note(self, text):
        self._write(f"  {text}\n", "note")

    def _write(self, text, tag=""):
        self._txt.configure(state="normal")
        self._txt.insert("end", text, tag)
        self._txt.configure(state="disabled")
        self._txt.see("end")

    def _update_dest_list(self):
        self._dcb["values"] = self.radio.get_contact_names()

    def _reset(self):
        self._dcb["values"] = []
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.configure(state="disabled")


# ════════════════════════════════════════════════════════════════════════════
# Tab: Message History
# ════════════════════════════════════════════════════════════════════════════

class HistoryTab(TabBase):

    def __init__(self, parent, radio, bus, root):
        super().__init__(parent, radio, bus, root)
        self._build()
        for ev in (EV_MSG_CHANNEL, EV_MSG_DIRECT, EV_MSG_SENT,
                   EV_MSG_DELIVERED, EV_MSG_TIMEOUT):
            bus.on(ev, lambda **_: self.after_tk(self.refresh))
        bus.on(EV_DISCONNECTED, lambda **_: self.after_tk(self.refresh))

    def _build(self):
        self._stats = ttk.Label(self, font=("Consolas", 10))
        self._stats.pack(anchor="nw", padx=10, pady=(8, 2))

        cols   = ("Dir", "Type", "Peer", "Message", "Status", "Time", "RTT")
        widths = (35, 60, 130, 250, 85, 78, 60)
        self._tree = ttk.Treeview(self, columns=cols, show="headings")
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w")
        self._tree.tag_configure("delivered", foreground=C["ok"])
        self._tree.tag_configure("timeout",   foreground=C["err"])
        self._tree.tag_configure("pending",   foreground=C["info"])
        self._tree.tag_configure("received",  foreground=C["ok"])
        sb = ttk.Scrollbar(self, orient="vertical",
                           command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")

        ttk.Button(self, text="🗑 Clear History",
                   command=self._clear).pack(pady=4)

    def refresh(self):
        s = self.radio.message_stats()
        self._stats.config(text=(
            f"Total: {s['total']}  │  ↑ {s['tx']}  ↓ {s['rx']}  │  "
            f"✅ {s['delivered']}  ⏱ {s['timeout']}  ⏳ {s['pending']}  │  "
            f"Avg RTT: {s['avg_rtt']:.1f}s  │  "
            f"Success: {s['success']:.0f}%"
        ))
        self._tree.delete(*self._tree.get_children())
        for m in self.radio.message_history():
            tag = m.status if m.status in (
                "delivered", "timeout", "pending", "received") else ""
            ts  = m.ts_received or m.ts_sent
            self._tree.insert("", "end", tags=(tag,), values=(
                "↑" if m.direction == "tx" else "↓",
                m.kind,
                m.peer,
                m.text[:34],
                m.status,
                ts_to_hms(ts),
                fmt_rtt(m.rtt),
            ))

    def _clear(self):
        self.radio.clear_history()
        self.refresh()


# ════════════════════════════════════════════════════════════════════════════
# Tab: Radio Info
# ════════════════════════════════════════════════════════════════════════════

class RadioTab(TabBase):

    def __init__(self, parent, radio, bus, root):
        super().__init__(parent, radio, bus, root)
        self._param_vars: dict[str, tk.StringVar] = {}
        self._build()
        bus.on(EV_CONNECTED,    lambda **_: self.after_tk(self._refresh_params))
        bus.on(EV_DISCONNECTED, lambda **_: self.after_tk(self._clear_params))

    def _build(self):
        pf = ttk.LabelFrame(self, text=" Radio Parameters (read-only) ")
        pf.pack(fill="x", padx=16, pady=(14, 4))
        for label in ("Frequency (MHz)", "Bandwidth (kHz)",
                      "Spreading Factor", "Coding Rate", "TX Power (dBm)"):
            row = ttk.Frame(pf)
            row.pack(fill="x", padx=12, pady=4)
            ttk.Label(row, text=label, width=22, anchor="w").pack(side="left")
            var = tk.StringVar(value="—")
            self._param_vars[label] = var
            ttk.Label(row, textvariable=var,
                      foreground=C["accent"],
                      font=("Consolas", 10, "bold")).pack(side="left")

        ttk.Label(self,
                  text=("Radio parameters are set via the device button UI\n"
                        "or the TerminalCLI channel.  Write-back is not\n"
                        "available through the MeshCore Python API."),
                  foreground=C["muted"], justify="left"
                  ).pack(anchor="w", padx=16, pady=(2, 8))

        sf = ttk.LabelFrame(self, text=" Live Device Stats ")
        sf.pack(fill="x", padx=16, pady=4)
        self._stats_var = tk.StringVar(value="  Press Refresh to fetch.")
        ttk.Label(sf, textvariable=self._stats_var,
                  font=("Consolas", 9), justify="left"
                  ).pack(anchor="w", padx=10, pady=6)

        ttk.Button(self, text="🔄 Refresh",
                   command=self._do_refresh).pack(pady=8)

    def _refresh_params(self):
        params = self.radio.radio_params()
        for label, var in self._param_vars.items():
            val = params.get(label)
            var.set(str(val) if val is not None else "—")

    def _clear_params(self):
        for var in self._param_vars.values():
            var.set("—")
        self._stats_var.set("  Not connected.")

    def _do_refresh(self):
        self._refresh_params()
        self._stats_var.set("  Fetching…")
        def fetch():
            stats = self.radio.live_stats()
            def update():
                if stats:
                    self._stats_var.set(
                        "\n".join(f"  {k}: {v}" for k, v in stats.items()))
                else:
                    self._stats_var.set(
                        "  No stats returned.\n"
                        "  Requires dt267 v1.13+ or meshcomod firmware.")
            self.after_tk(update)
        threading.Thread(target=fetch, daemon=True).start()


# ════════════════════════════════════════════════════════════════════════════
# Tab: Log
# ════════════════════════════════════════════════════════════════════════════

class LogTab(TabBase):

    def __init__(self, parent, radio, bus, root):
        super().__init__(parent, radio, bus, root)
        self._build()
        bus.on(EV_LOG, lambda **kw: self.after_tk(
            self._append, kw["text"], kw.get("level", "info")))

    def _build(self):
        self._txt = tk.Text(self, bg=C["bg2"], fg=C["fg"],
                            state="disabled", wrap="word",
                            font=("Consolas", 9))
        for level, colour in LOG_COLOURS.items():
            self._txt.tag_configure(level, foreground=colour)
        sb = ttk.Scrollbar(self, orient="vertical", command=self._txt.yview)
        self._txt.configure(yscrollcommand=sb.set)
        self._txt.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")

        bf = ttk.Frame(self)
        bf.pack(side="bottom", fill="x", padx=6, pady=2)
        ttk.Button(bf, text="🗑 Clear",
                   command=self._clear).pack(side="left")
        ttk.Button(bf, text="💾 Save",
                   command=self._save).pack(side="left", padx=6)

    def _append(self, text: str, level: str = "info"):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {text}\n"
        tag  = level if level in LOG_COLOURS else "info"
        self._txt.configure(state="normal")
        self._txt.insert("end", line, tag)
        self._txt.configure(state="disabled")
        self._txt.see("end")

    def _clear(self):
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.configure(state="disabled")

    def _save(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            title="Save log")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(self._txt.get("1.0", "end"))
            except Exception as exc:
                messagebox.showerror("Save failed", str(exc))


# ════════════════════════════════════════════════════════════════════════════
# Dialogs
# ════════════════════════════════════════════════════════════════════════════

class _PromptDialog(tk.Toplevel):
    """Single-field input dialog with dark theme."""

    def __init__(self, parent, title: str, prompt: str,
                 default: str = ""):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.grab_set()
        self.result: str | None = None

        tk.Label(self, text=prompt, bg=C["bg"], fg=C["fg"],
                 padx=16, pady=10, justify="left").pack()
        self._v = tk.StringVar(value=default)
        e = tk.Entry(self, textvariable=self._v, width=36,
                     bg=C["entry"], fg=C["fg"],
                     insertbackground=C["fg"])
        e.pack(padx=16, pady=4)
        e.focus_set()
        e.select_range(0, "end")

        bf = tk.Frame(self, bg=C["bg"])
        bf.pack(pady=8)
        for text, cmd in (("OK", self._ok), ("Cancel", self.destroy)):
            tk.Button(bf, text=text, width=8, command=cmd,
                      bg=C["btn"], fg=C["btn_fg"],
                      relief="flat").pack(side="left", padx=4)
        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())
        self.wait_window()

    def _ok(self):
        self.result = self._v.get()
        self.destroy()


class _BLEDialog(tk.Toplevel):
    """BLE device scanner dialog."""

    def __init__(self, parent, radio: NodeRadio):
        super().__init__(parent)
        self.title("Connect via Bluetooth (BLE)")
        self.geometry("560x460")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self.grab_set()
        self.result: str | None = None
        self._radio = radio
        self._build()
        self.wait_window()

    def _build(self):
        top = tk.Frame(self, bg=C["bg"])
        top.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(top, text="Address / Name:", bg=C["bg"],
                 fg=C["fg"]).pack(side="left")
        self._av = tk.StringVar()
        tk.Entry(top, textvariable=self._av, bg=C["entry"],
                 fg=C["fg"], insertbackground=C["fg"],
                 width=28).pack(side="left", padx=6)
        tk.Button(top, text="🔍 Scan (5 s)", command=self._scan,
                  bg=C["btn"], fg=C["btn_fg"],
                  activebackground=C["accent"],
                  relief="flat", padx=8, cursor="hand2").pack(side="left")

        self._sv = tk.StringVar(
            value="Press Scan to discover devices, or type an address above.")
        tk.Label(self, textvariable=self._sv, bg=C["bg"], fg=C["info"],
                 anchor="w", wraplength=530).pack(fill="x", padx=10, pady=2)

        cols   = ("Name", "Address", "RSSI", "MeshCore?")
        widths = (200, 160, 55, 80)
        self._tree = ttk.Treeview(self, columns=cols,
                                   show="headings", height=12)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w")
        self._tree.tag_configure("mc",    foreground=C["ok"])
        self._tree.tag_configure("other", foreground=C["fg"])
        sb = ttk.Scrollbar(self, orient="vertical",
                           command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True,
                        padx=(10, 0), pady=4)
        sb.pack(side="left", fill="y", pady=4)
        self._tree.bind("<Double-1>",
                        lambda _: self._pick())
        self._tree.bind("<<TreeviewSelect>>", self._on_sel)

        bf = tk.Frame(self, bg=C["bg"])
        bf.pack(side="bottom", fill="x", padx=10, pady=8)
        tk.Button(bf, text="✅ Connect", command=self._ok,
                  bg=C["accent"], fg=C["bg"],
                  relief="flat", padx=12,
                  cursor="hand2").pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", command=self.destroy,
                  bg=C["btn"], fg=C["btn_fg"],
                  relief="flat", padx=12,
                  cursor="hand2").pack(side="left", padx=4)
        tk.Label(bf, text="Double-click to connect instantly.",
                 bg=C["bg"], fg=C["muted"]).pack(side="right")
        self.bind("<Escape>", lambda _: self.destroy())

    def _scan(self):
        self._sv.set("⏳ Scanning for 5 seconds…")
        self._tree.delete(*self._tree.get_children())
        self.update()
        def worker():
            devices = self._radio.scan_ble()
            self.after(0, lambda: self._populate(devices))
        threading.Thread(target=worker, daemon=True).start()

    def _populate(self, devices):
        self._tree.delete(*self._tree.get_children())
        if not devices:
            self._sv.set("No BLE devices found. Check Bluetooth is enabled.")
            return
        mc_n = sum(1 for d in devices if d["is_mc"])
        self._sv.set(
            f"Found {len(devices)} device(s) — {mc_n} MeshCore (green). "
            "Double-click to connect.")
        for d in devices:
            tag = "mc" if d["is_mc"] else "other"
            self._tree.insert("", "end", iid=d["address"], tags=(tag,),
                              values=(d["name"], d["address"], d["rssi"],
                                      "✅ Yes" if d["is_mc"] else "No"))

    def _on_sel(self, _=None):
        sel = self._tree.selection()
        if sel:
            self._av.set(self._tree.item(sel[0], "values")[1])

    def _pick(self):
        self._on_sel()
        self._ok()

    def _ok(self):
        addr = self._av.get().strip()
        if addr:
            self.result = addr
            self.destroy()


# ════════════════════════════════════════════════════════════════════════════
# AppWindow — main window
# ════════════════════════════════════════════════════════════════════════════

class AppWindow(tk.Tk):

    APP_TITLE = "MeshCore Node Manager"

    def __init__(self):
        super().__init__()
        self.title(self.APP_TITLE)
        self.geometry("1160x820")
        self.minsize(900, 600)
        self.configure(bg=C["bg"])

        self._bus   = EventBus(error_handler=self._bus_error)
        self._radio = NodeRadio(self._bus)

        self._apply_style()
        self._build_toolbar()
        self._build_notebook()
        self._build_statusbar()
        self._wire_bus()
        self._tick()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── style ────────────────────────────────────────────────────────────────

    def _apply_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure(".", background=C["bg"], foreground=C["fg"],
                     fieldbackground=C["entry"],
                     bordercolor=C["border"])
        s.configure("TNotebook",       background=C["bg"])
        s.configure("TNotebook.Tab",   background=C["btn"],
                     foreground=C["fg"], padding=[9, 4])
        s.map("TNotebook.Tab",
              background=[("selected", C["accent"])],
              foreground=[("selected", C["bg"])])
        for w in ("TFrame", "TLabel", "TCheckbutton", "TLabelframe",
                  "TLabelframe.Label"):
            s.configure(w, background=C["bg"], foreground=C["fg"])
        s.configure("TButton",   background=C["btn"], foreground=C["btn_fg"])
        s.configure("TEntry",    fieldbackground=C["entry"], foreground=C["fg"])
        s.configure("TCombobox", fieldbackground=C["entry"], foreground=C["fg"],
                     selectbackground=C["accent"])
        s.configure("TSeparator", background=C["border"])
        s.configure("Treeview",   background=C["panel"],
                     fieldbackground=C["panel"],
                     foreground=C["fg"], rowheight=22)
        s.configure("Treeview.Heading",
                     background=C["btn"], foreground=C["fg"])

    # ── toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=C["bg2"], pady=4)
        bar.pack(side="top", fill="x")

        def btn(label, cmd, accent=False):
            b = tk.Button(bar, text=label, command=cmd,
                          bg=C["accent"] if accent else C["btn"],
                          fg=C["bg"]     if accent else C["btn_fg"],
                          activebackground=C["accent"],
                          relief="flat", padx=10, pady=3, cursor="hand2")
            b.pack(side="left", padx=3)
            return b

        def gap():
            tk.Frame(bar, bg=C["bg2"], width=12).pack(side="left")

        btn("🔌 Serial",       self._do_serial)
        btn("🌐 TCP",          self._do_tcp)
        btn("🔵 BLE",          self._do_ble)
        btn("⏹ Disconnect",    self._do_disconnect)
        gap()
        btn("🔄 Contacts",     self._do_refresh)
        btn("📡 Ping",         self._do_ping)
        gap()
        btn("💾 Backup",       self._do_backup)
        btn("📂 Load Backup",  self._do_load_backup)
        btn("📝 Export Msgs",  self._do_export)
        tk.Frame(bar, bg=C["bg2"]).pack(side="left", expand=True, fill="x")
        btn("ℹ Info",          self._do_info)

    # ── notebook ──────────────────────────────────────────────────────────────

    def _build_notebook(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6, pady=4)
        tab_defs = [
            (ContactsTab, "📡 Contacts"),
            (ChannelTab,  "💬 Channel"),
            (DirectTab,   "📨 Direct"),
            (HistoryTab,  "📊 History"),
            (RadioTab,    "📻 Radio"),
            (LogTab,      "📋 Log"),
        ]
        self._tabs = {}
        for cls, label in tab_defs:
            widget = cls(nb, self._radio, self._bus, self)
            nb.add(widget, text=label)
            self._tabs[label] = widget

    # ── status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=C["bg2"], pady=2)
        bar.pack(side="bottom", fill="x")
        self._status_v = tk.StringVar(value="⚫ Offline")
        tk.Label(bar, textvariable=self._status_v,
                 bg=C["bg2"], fg=C["info"],
                 anchor="w").pack(side="left", padx=8)
        self._pending_v = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._pending_v,
                 bg=C["bg2"], fg=C["muted"],
                 anchor="e").pack(side="right", padx=8)

    def _update_statusbar(self):
        if self._radio.online:
            ct = self._radio.conn_type
            nm = self._radio.node_name
            self._status_v.set(f"✅ Online [{ct}]  │  {nm}")
        else:
            self._status_v.set("⚫ Offline")
        p = self._radio.pending_count()
        self._pending_v.set(f"⏳ {p} pending" if p else "")

    # ── bus wiring ────────────────────────────────────────────────────────────

    def _wire_bus(self):
        self._bus.on(EV_CONNECTED,  lambda **_: self.after(0, self._update_statusbar))
        self._bus.on(EV_DISCONNECTED, lambda **_: self.after(0, self._update_statusbar))
        self._bus.on(EV_CONN_ERROR,
                     lambda **kw: self.after(0, lambda: messagebox.showerror(
                         "Connection failed", kw.get("message", "Unknown error"))))

    # ── toolbar actions ───────────────────────────────────────────────────────

    def _do_serial(self):
        dlg = _PromptDialog(self, "Serial Port",
                            "Enter port (e.g. COM3 or /dev/ttyUSB0):")
        if dlg.result:
            self._bg_connect(lambda: self._radio.connect_serial(dlg.result.strip()))

    def _do_tcp(self):
        host_dlg = _PromptDialog(self, "TCP Host", "Enter IP address or hostname:")
        if not host_dlg.result:
            return
        port_dlg = _PromptDialog(self, "TCP Port",
                                  f"Port (default {TCP_DEFAULT_PORT}):",
                                  default=str(TCP_DEFAULT_PORT))
        port = int(port_dlg.result) \
               if port_dlg.result and port_dlg.result.isdigit() \
               else TCP_DEFAULT_PORT
        self._bg_connect(
            lambda: self._radio.connect_tcp(host_dlg.result.strip(), port))

    def _do_ble(self):
        dlg = _BLEDialog(self, self._radio)
        if dlg.result:
            self._bg_connect(lambda: self._radio.connect_ble(dlg.result))

    def _bg_connect(self, fn):
        self._status_v.set("⏳ Connecting…")
        threading.Thread(target=fn, daemon=True).start()

    def _do_disconnect(self):
        threading.Thread(target=self._radio.disconnect, daemon=True).start()

    def _do_refresh(self):
        if not self._radio.online:
            messagebox.showwarning("Offline", "Connect first.")
            return
        def run():
            self._radio.refresh_contacts()
            self.after(0, self._tabs["📡 Contacts"].refresh)
        threading.Thread(target=run, daemon=True).start()

    def _do_ping(self):
        if not self._radio.online:
            messagebox.showwarning("Offline", "Connect first.")
            return
        threading.Thread(target=self._radio.ping, daemon=True).start()

    def _do_backup(self):
        if not self._radio.online:
            messagebox.showwarning("Offline", "Connect first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            title="Save backup")
        if path:
            threading.Thread(
                target=lambda: self._radio.save_backup(path),
                daemon=True).start()

    def _do_load_backup(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            title="Load backup")
        if path:
            data = self._radio.load_backup(path)
            if data:
                info = {**data.get("device_info", {}),
                        **data.get("radio", {})}
                lines = "\n".join(f"  {k}: {v}" for k, v in info.items())
                messagebox.showinfo(
                    f"Backup — {data.get('node_name','?')}",
                    f"Saved: {data.get('saved_at','?')}\n\n{lines}")

    def _do_export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            title="Export messages")
        if path:
            threading.Thread(
                target=lambda: self._radio.export_messages(path),
                daemon=True).start()

    def _do_info(self):
        info = self._radio.device_info
        if not info:
            messagebox.showinfo("Device Info",
                                "Not connected or no data available.")
            return
        lines = "\n".join(f"  {k}: {v}" for k, v in info.items())
        messagebox.showinfo(
            f"Device — {self._radio.node_name}", lines or "(empty)")

    # ── periodic tick ─────────────────────────────────────────────────────────

    def _tick(self):
        if self._radio.online:
            self._radio.sweep_timeouts()
        self._update_statusbar()
        self.after(5000, self._tick)

    # ── close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        if self._radio.online:
            self._radio.disconnect()
        self.destroy()

    def _bus_error(self, event: str, exc: Exception):
        self._bus.emit(EV_LOG, text=f"Bus error [{event}]: {exc}", level="err")
