"""
app.py — AppWindow: main Tkinter application window
MeshCore Node Manager  |  Original work
"""

import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import C, LOG_COLOURS, TCP_DEFAULT_PORT, SESSION_LOG_DIR, RECONNECT_DELAY
from events import (
    EventBus,
    EV_CONNECTED, EV_DISCONNECTED, EV_RECONNECTING, EV_CONN_ERROR,
    EV_CONTACTS_UPD,
    EV_MSG_CHANNEL, EV_MSG_DIRECT, EV_MSG_SENT,
    EV_MSG_DELIVERED, EV_MSG_TIMEOUT,
    EV_UNREAD_CHANGE, EV_NOTE_UPD, EV_SETTINGS_UPD,
    EV_LOG,
)
from helpers import ts_to_hms, fmt_rtt, safe_str
from notify import desktop_notify, play_alert
from radio import NodeRadio
from settings import Settings


# ════════════════════════════════════════════════════════════════════════════
# TabBase
# ════════════════════════════════════════════════════════════════════════════

class TabBase(ttk.Frame):
    def __init__(self, parent, radio: NodeRadio, bus: EventBus,
                 root: tk.Tk, settings: Settings):
        super().__init__(parent)
        self.radio    = radio
        self.bus      = bus
        self._root    = root
        self.settings = settings

    def after_tk(self, fn, *args):
        self._root.after(0, lambda: fn(*args))

    def _bg(self, fn, done=None):
        def worker():
            result = fn()
            if done:
                self.after_tk(done, result)
        threading.Thread(target=worker, daemon=True).start()


# ════════════════════════════════════════════════════════════════════════════
# Tab: Contacts
# ════════════════════════════════════════════════════════════════════════════

class ContactsTab(TabBase):

    def __init__(self, parent, radio, bus, root, settings):
        super().__init__(parent, radio, bus, root, settings)
        self._sort_col = ""
        self._sort_rev = False
        self._build()
        bus.on(EV_CONTACTS_UPD, lambda **_: self.after_tk(self.refresh))
        bus.on(EV_CONNECTED,    lambda **_: self.after_tk(self.refresh))
        bus.on(EV_DISCONNECTED, lambda **_: self.after_tk(self._clear))
        bus.on(EV_NOTE_UPD,     lambda **_: self.after_tk(self.refresh))

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Label(bar, text="Filter:").pack(side="left")
        self._fv = tk.StringVar()
        self._fv.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(bar, textvariable=self._fv, width=22).pack(side="left", padx=4)
        ttk.Button(bar, text="🔄 Refresh",
                   command=lambda: self._bg(self.radio.refresh_contacts,
                                            lambda _: self.refresh())
                   ).pack(side="left", padx=2)
        ttk.Button(bar, text="⭐ Favourite",
                   command=self._toggle_fav).pack(side="left", padx=2)
        ttk.Button(bar, text="📝 Note",
                   command=self._edit_note).pack(side="left", padx=2)
        ttk.Button(bar, text="🗑 Remove",
                   command=self._remove).pack(side="left", padx=2)
        ttk.Button(bar, text="📄 CSV",
                   command=self._export_csv).pack(side="left", padx=2)
        self._count_lbl = ttk.Label(bar, foreground=C["muted"])
        self._count_lbl.pack(side="left", padx=8)

        cols   = ("★", "Name", "Key", "SNR", "RSSI", "Batt %", "Last Heard", "GPS", "Note")
        widths = (25, 150, 120, 50, 55, 55, 90, 200, 150)
        self._tree = ttk.Treeview(self, columns=cols, show="headings")
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col, command=lambda c=col: self._sort(c))
            self._tree.column(col, width=w, anchor="w")
        self._tree.tag_configure("fresh", foreground=C["ok"])
        self._tree.tag_configure("stale", foreground=C["muted"])
        self._tree.tag_configure("fav",   foreground=C["peach"])
        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", self._on_double_click)

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
            if c.favourite:
                tag = "fav"
            elif age < 600:
                tag = "fresh"
            else:
                tag = "stale"
            gps  = (f"{c.lat:.5f}, {c.lon:.5f}"
                    if c.lat is not None and c.lon is not None else "")
            note = self.radio.get_note(c.key)
            self._tree.insert("", "end", iid=c.key, tags=(tag,),
                              values=("★" if c.favourite else "",
                                      c.name, c.key,
                                      safe_str(c.snr), safe_str(c.rssi),
                                      safe_str(c.battery),
                                      ts_to_hms(c.last_heard), gps, note))
            shown += 1
        total = len(contacts)
        self._count_lbl.config(
            text=f"{shown} of {total}" if filt else f"{total} contact(s)")

    def _clear(self):
        self._tree.delete(*self._tree.get_children())
        self._count_lbl.config(text="")

    def _sort(self, col):
        rows = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        rev  = (self._sort_col == col and not self._sort_rev)
        rows.sort(reverse=rev)
        for i, (_, k) in enumerate(rows):
            self._tree.move(k, "", i)
        self._sort_col, self._sort_rev = col, rev

    def _selected_key(self) -> "str | None":
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _toggle_fav(self):
        key = self._selected_key()
        if key:
            self.radio.toggle_favourite(key)
            self.refresh()

    def _edit_note(self):
        key = self._selected_key()
        if not key:
            return
        current = self.radio.get_note(key)
        dlg = _PromptDialog(self._root, "Contact Note",
                            "Enter note for this contact\n(leave blank to clear):",
                            default=current)
        if dlg.result is not None:
            self.radio.set_note(key, dlg.result)

    def _remove(self):
        for key in self._tree.selection():
            self.radio.remove_contact(key)
        self.refresh()

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All", "*.*")],
            title="Export contacts")
        if path:
            self._bg(lambda: self.radio.export_contacts_csv(path))

    def _on_double_click(self, _event):
        """Double-click a contact → pre-fill the Direct tab."""
        key = self._selected_key()
        if not key:
            return
        vals = self._tree.item(key, "values")
        contact_name = vals[1] if vals else key
        self.bus.emit("_prefill_direct", name=contact_name)


# ════════════════════════════════════════════════════════════════════════════
# Tab: Channel
# ════════════════════════════════════════════════════════════════════════════

class ChannelTab(TabBase):

    def __init__(self, parent, radio, bus, root, settings):
        super().__init__(parent, radio, bus, root, settings)
        self._build()
        bus.on(EV_MSG_CHANNEL,  lambda **kw: self.after_tk(self._append_rx, kw))
        bus.on(EV_DISCONNECTED, lambda **_: self.after_tk(self._reset))
        bus.on(EV_CONNECTED,    lambda **_: self.after_tk(self._mark_read))

    def _build(self):
        self._txt = tk.Text(self, bg=C["bg2"], fg=C["fg"],
                            state="disabled", wrap="word",
                            font=("Consolas", 10))
        self._txt.tag_configure("ts",   foreground=C["muted"])
        self._txt.tag_configure("tx",   foreground=C["accent"])
        self._txt.tag_configure("rx",   foreground=C["ok"])
        self._txt.tag_configure("hops", foreground=C["muted"],
                                font=("Consolas", 8))
        sb = ttk.Scrollbar(self, orient="vertical", command=self._txt.yview)
        self._txt.configure(yscrollcommand=sb.set)
        self._txt.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y", pady=4)
        self._txt.bind("<FocusIn>", lambda _: self._mark_read())

        bot = ttk.Frame(self)
        bot.pack(side="bottom", fill="x", padx=6, pady=4)
        self._mv = tk.StringVar()
        ent = ttk.Entry(bot, textvariable=self._mv, width=68)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _: self._send())
        self._cc = ttk.Label(bot, text="0 / 228", foreground=C["muted"])
        self._cc.pack(side="left", padx=4)
        self._mv.trace_add("write", lambda *_:
            self._cc.config(text=f"{len(self._mv.get())} / 228"))
        ttk.Button(bot, text="📤 Broadcast", command=self._send).pack(side="left")

    def _mark_read(self):
        self.radio.clear_unread_channel()

    def _send(self):
        text = self._mv.get().strip()
        if not text:
            return
        if len(text) > 228:
            messagebox.showwarning("Too long", "Maximum 228 characters.")
            return
        lid = self.radio.transmit_channel(text)
        if lid is not None:
            self._write(f"[{ts_to_hms(time.time())}] ", "ts")
            self._write(f"me: {text}\n", "tx")
        self._mv.set("")

    def _append_rx(self, kw):
        self._write(f"[{ts_to_hms(kw['ts'])}] ", "ts")
        self._write(f"{kw['sender']}: {kw['text']}", "rx")
        hops = kw.get("hops")
        if hops is not None:
            self._write(f"  ·{hops}h", "hops")
        self._write("\n")
        # Notifications
        if self.settings.get("notify_channel"):
            desktop_notify("MeshCore Channel",
                           f"{kw['sender']}: {kw['text'][:80]}")
        if self.settings.get("sound_channel"):
            play_alert()

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

    def __init__(self, parent, radio, bus, root, settings):
        super().__init__(parent, radio, bus, root, settings)
        self._current_peer: str | None = None   # None = show all
        self._build()
        bus.on(EV_MSG_DIRECT,    lambda **kw: self.after_tk(self._append_rx, kw))
        bus.on(EV_MSG_DELIVERED, lambda **kw: self.after_tk(
            self._append_note,
            f"✅ Delivered  (RTT {fmt_rtt(kw.get('rtt'))})" if kw.get("rtt")
            else "✅ Delivered"))
        bus.on(EV_MSG_TIMEOUT,   lambda **_: self.after_tk(
            self._append_note, "⏱ Timeout — no ACK received"))
        bus.on(EV_CONTACTS_UPD,  lambda **_: self.after_tk(self.update_dest_list))
        bus.on(EV_CONNECTED,     lambda **_: self.after_tk(self.update_dest_list))
        bus.on(EV_DISCONNECTED,  lambda **_: self.after_tk(self._reset))
        bus.on("_prefill_direct", lambda **kw: self.after_tk(
            self._prefill, kw.get("name", "")))

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)

        # Contact filter / chat-per-contact selector
        ttk.Label(top, text="View:").pack(side="left")
        self._pv = tk.StringVar(value="All")
        self._pcb = ttk.Combobox(top, textvariable=self._pv,
                                  width=20, state="normal")
        self._pcb.pack(side="left", padx=4)
        self._pcb.bind("<<ComboboxSelected>>", lambda _: self._switch_peer())
        self._pcb.bind("<Return>", lambda _: self._switch_peer())
        ttk.Button(top, text="👁 Filter", command=self._switch_peer).pack(side="left", padx=2)
        ttk.Button(top, text="🌐 All",    command=self._show_all).pack(side="left", padx=2)

        tk.Frame(top, bg=C["bg"], width=16).pack(side="left")
        ttk.Label(top, text="To:").pack(side="left")
        self._dv = tk.StringVar()
        self._dcb = ttk.Combobox(top, textvariable=self._dv, width=20, state="normal")
        self._dcb.pack(side="left", padx=4)
        ttk.Label(top, text="Msg:").pack(side="left")
        self._mv = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self._mv, width=38)
        ent.pack(side="left", padx=4)
        ent.bind("<Return>", lambda _: self._send())
        self._cc = ttk.Label(top, text="", foreground=C["muted"])
        self._cc.pack(side="left", padx=2)
        self._mv.trace_add("write", lambda *_:
            self._cc.config(text=f"{len(self._mv.get())} / 228"))
        ttk.Button(top, text="📨 Send DM", command=self._send).pack(side="left")

        self._txt = tk.Text(self, bg=C["bg2"], fg=C["fg"],
                            state="disabled", wrap="word",
                            font=("Consolas", 10))
        self._txt.tag_configure("ts",    foreground=C["muted"])
        self._txt.tag_configure("tx",    foreground=C["accent"])
        self._txt.tag_configure("rx",    foreground=C["ok"])
        self._txt.tag_configure("hops",  foreground=C["muted"],
                                font=("Consolas", 8))
        self._txt.tag_configure("note",  foreground=C["muted"],
                                font=("Consolas", 9, "italic"))
        sb = ttk.Scrollbar(self, orient="vertical", command=self._txt.yview)
        self._txt.configure(yscrollcommand=sb.set)
        self._txt.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")
        self._txt.bind("<FocusIn>", lambda _: self._mark_read())

    def _mark_read(self):
        self.radio.clear_unread_direct()

    def _send(self):
        dest = self._dv.get().strip()
        text = self._mv.get().strip()
        if not dest or not text:
            return
        if len(text) > 228:
            messagebox.showwarning("Too long", "Maximum 228 characters.")
            return
        lid = self.radio.transmit_direct(dest, text)
        if lid is not None:
            self._write(f"[{ts_to_hms(time.time())}] ", "ts")
            self._write(f"me → {dest}: {text}\n", "tx")
        self._mv.set("")

    def _append_rx(self, kw):
        peer = kw["sender"]
        # Only display if showing all or matches current filter
        if self._current_peer and peer.lower() != self._current_peer.lower():
            return
        self._write(f"[{ts_to_hms(kw['ts'])}] ", "ts")
        self._write(f"{peer}: {kw['text']}", "rx")
        hops = kw.get("hops")
        if hops is not None:
            self._write(f"  ·{hops}h", "hops")
        self._write("\n")
        # Notifications
        if self.settings.get("notify_dm"):
            desktop_notify(f"MeshCore DM from {peer}", kw["text"][:80])
        if self.settings.get("sound_dm"):
            play_alert()

    def _append_note(self, text):
        self._write(f"  {text}\n", "note")

    def _write(self, text, tag=""):
        self._txt.configure(state="normal")
        self._txt.insert("end", text, tag)
        self._txt.configure(state="disabled")
        self._txt.see("end")

    def update_dest_list(self):
        """Refresh the To: and View: dropdowns with known contact names."""
        names = self.radio.get_contact_names()
        self._dcb["values"] = names
        self._pcb["values"] = ["All"] + names
        names = self.radio.get_contact_names()
        self._dcb["values"] = names
        self._pcb["values"] = ["All"] + names

    def _switch_peer(self):
        val = self._pv.get().strip()
        self._current_peer = None if val in ("", "All") else val
        self._reload_history()

    def _show_all(self):
        self._pv.set("All")
        self._current_peer = None
        self._reload_history()

    def _reload_history(self):
        """Rebuild text widget from history for current peer filter."""
        msgs = self.radio.message_history(
            kind="direct",
            peer=self._current_peer if self._current_peer else None
        )
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        for m in msgs:
            ts = m.ts_received or m.ts_sent
            self._write(f"[{ts_to_hms(ts)}] ", "ts")
            if m.direction == "rx":
                self._write(f"{m.peer}: {m.text}", "rx")
                if m.hops is not None:
                    self._write(f"  ·{m.hops}h", "hops")
                self._write("\n")
            else:
                self._write(f"me → {m.peer}: {m.text}\n", "tx")
        self._txt.configure(state="disabled")
        self._txt.see("end")

    def _reset(self):
        self._dcb["values"] = []
        self._pcb["values"] = ["All"]
        self._current_peer  = None
        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.configure(state="disabled")

    def _prefill(self, name: str):
        """Called when a contact is double-clicked in the Contacts tab."""
        self._dv.set(name)


# ════════════════════════════════════════════════════════════════════════════
# Tab: Message History
# ════════════════════════════════════════════════════════════════════════════

class HistoryTab(TabBase):

    def __init__(self, parent, radio, bus, root, settings):
        super().__init__(parent, radio, bus, root, settings)
        self._build()
        for ev in (EV_MSG_CHANNEL, EV_MSG_DIRECT, EV_MSG_SENT,
                   EV_MSG_DELIVERED, EV_MSG_TIMEOUT):
            bus.on(ev, lambda **_: self.after_tk(self.refresh))
        bus.on(EV_DISCONNECTED, lambda **_: self.after_tk(self.refresh))

    def _build(self):
        self._stats = ttk.Label(self, font=("Consolas", 10))
        self._stats.pack(anchor="nw", padx=10, pady=(8, 2))

        # Search bar
        sbar = ttk.Frame(self)
        sbar.pack(fill="x", padx=6, pady=2)
        ttk.Label(sbar, text="Search:").pack(side="left")
        self._sv = tk.StringVar()
        self._sv.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(sbar, textvariable=self._sv, width=28).pack(side="left", padx=4)
        ttk.Label(sbar, text="Peer:").pack(side="left")
        self._pv = tk.StringVar()
        self._pv.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(sbar, textvariable=self._pv, width=18).pack(side="left", padx=4)
        ttk.Label(sbar, text="Type:").pack(side="left")
        self._tv = tk.StringVar(value="all")
        cb = ttk.Combobox(sbar, textvariable=self._tv, width=9, state="readonly",
                          values=["all", "direct", "channel"])
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        ttk.Button(sbar, text="✖ Clear filters",
                   command=self._clear_filters).pack(side="left", padx=4)

        cols   = ("Dir", "Type", "Peer", "Message", "Hops", "Status", "Time", "RTT")
        widths = (35, 60, 120, 230, 45, 80, 78, 60)
        self._tree = ttk.Treeview(self, columns=cols, show="headings")
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w")
        self._tree.tag_configure("delivered", foreground=C["ok"])
        self._tree.tag_configure("timeout",   foreground=C["err"])
        self._tree.tag_configure("pending",   foreground=C["info"])
        self._tree.tag_configure("received",  foreground=C["ok"])
        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        sb.pack(side="right", fill="y")
        ttk.Button(self, text="🗑 Clear History", command=self._clear).pack(pady=4)

    def refresh(self):
        s = self.radio.message_stats()
        self._stats.config(text=(
            f"Total: {s['total']}  │  ↑ {s['tx']}  ↓ {s['rx']}  │  "
            f"✅ {s['delivered']}  ⏱ {s['timeout']}  ⏳ {s['pending']}  │  "
            f"Avg RTT: {s['avg_rtt']:.1f}s  │  Success: {s['success']:.0f}%"
        ))
        kind   = self._tv.get() if self._tv.get() != "all" else None
        peer   = self._pv.get().strip() or None
        search = self._sv.get().strip() or None
        self._tree.delete(*self._tree.get_children())
        for m in self.radio.message_history(kind=kind, peer=peer, search=search):
            tag = m.status if m.status in (
                "delivered", "timeout", "pending", "received") else ""
            ts  = m.ts_received or m.ts_sent
            self._tree.insert("", "end", tags=(tag,), values=(
                "↑" if m.direction == "tx" else "↓",
                m.kind,
                m.peer,
                m.text[:30],
                str(m.hops) if m.hops is not None else "",
                m.status,
                ts_to_hms(ts),
                fmt_rtt(m.rtt),
            ))

    def _clear_filters(self):
        self._sv.set("")
        self._pv.set("")
        self._tv.set("all")
        self.refresh()

    def _clear(self):
        self.radio.clear_history()
        self.refresh()


# ════════════════════════════════════════════════════════════════════════════
# Tab: Radio Info
# ════════════════════════════════════════════════════════════════════════════

class RadioTab(TabBase):

    def __init__(self, parent, radio, bus, root, settings):
        super().__init__(parent, radio, bus, root, settings)
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
            ttk.Label(row, textvariable=var, foreground=C["accent"],
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
        ttk.Button(self, text="🔄 Refresh", command=self._do_refresh).pack(pady=8)

    def refresh_params(self):
        """Public wrapper — called by AppWindow after connect."""
        self._refresh_params()

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
# Tab: Network Map
# ════════════════════════════════════════════════════════════════════════════

class MapTab(TabBase):
    """
    Simple canvas-based network map.
    Plots contacts that have GPS coordinates as dots on a plain background.
    No external mapping library required.
    """

    PAD    = 30     # canvas border padding in pixels
    RADIUS = 6      # dot radius

    def __init__(self, parent, radio, bus, root, settings):
        super().__init__(parent, radio, bus, root, settings)
        self._dot_info: list[tuple] = []
        self._build()
        bus.on(EV_CONTACTS_UPD, lambda **_: self.after_tk(self.refresh))
        bus.on(EV_CONNECTED,    lambda **_: self.after_tk(self.refresh))
        bus.on(EV_DISCONNECTED, lambda **_: self.after_tk(self._clear))

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Button(bar, text="🔄 Refresh", command=self.refresh).pack(side="left")
        self._lbl = ttk.Label(bar, foreground=C["muted"])
        self._lbl.pack(side="left", padx=8)

        self._canvas = tk.Canvas(self, bg=C["panel"], highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self._canvas.bind("<Configure>", lambda _: self.refresh())
        self._canvas.bind("<Motion>", self._on_hover)

        self._tooltip = tk.Label(self._canvas, bg=C["btn"], fg=C["fg"],
                                  font=("Consolas", 9), padx=4, pady=2,
                                  relief="flat")

    def refresh(self):
        self._canvas.delete("all")
        self._dot_info = []
        contacts = [c for c in self.radio.get_contacts()
                    if c.lat is not None and c.lon is not None]

        if not contacts:
            w = self._canvas.winfo_width()
            h = self._canvas.winfo_height()
            self._canvas.create_text(
                max(w // 2, 100), max(h // 2, 50),
                text="No contacts with GPS data",
                fill=C["muted"], font=("Consolas", 11))
            self._lbl.config(text="0 contacts with GPS")
            return

        lats = [c.lat for c in contacts]
        lons = [c.lon for c in contacts]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Add slight margin so dots aren't clipped
        lat_span = max(max_lat - min_lat, 0.001)
        lon_span = max(max_lon - min_lon, 0.001)

        cw = max(self._canvas.winfo_width(),  200)
        ch = max(self._canvas.winfo_height(), 200)
        draw_w = cw - 2 * self.PAD
        draw_h = ch - 2 * self.PAD

        # Grid lines
        for i in range(5):
            x = self.PAD + draw_w * i // 4
            y = self.PAD + draw_h * i // 4
            self._canvas.create_line(x, self.PAD, x, ch - self.PAD,
                                     fill=C["border"], dash=(2, 6))
            self._canvas.create_line(self.PAD, y, cw - self.PAD, y,
                                     fill=C["border"], dash=(2, 6))

        # Own node marker
        self._canvas.create_oval(
            cw // 2 - self.RADIUS - 2, ch // 2 - self.RADIUS - 2,
            cw // 2 + self.RADIUS + 2, ch // 2 + self.RADIUS + 2,
            fill=C["accent"], outline="", tags="own")
        self._canvas.create_text(cw // 2, ch // 2 + self.RADIUS + 10,
                                  text=self.radio.node_name or "me",
                                  fill=C["accent"], font=("Consolas", 8))

        for c in contacts:
            # Map lat/lon to canvas coords
            # lon → x (east = right), lat → y (north = up → lower y)
            norm_x = (c.lon - min_lon) / lon_span
            norm_y = 1.0 - (c.lat - min_lat) / lat_span
            cx = int(self.PAD + norm_x * draw_w)
            cy = int(self.PAD + norm_y * draw_h)

            now = time.time()
            age = (now - c.last_heard) if c.last_heard else 99999
            colour = C["ok"] if age < 600 else (C["peach"] if c.favourite else C["muted"])
            if c.favourite:
                colour = C["peach"]

            r = self.RADIUS
            self._canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                     fill=colour, outline="", tags=f"dot_{c.key}")
            self._canvas.create_text(cx, cy + r + 8,
                                     text=c.name[:12],
                                     fill=colour, font=("Consolas", 8),
                                     tags=f"lbl_{c.key}")
            self._dot_info.append((cx, cy, c.name, c.key))

        self._lbl.config(text=f"{len(contacts)} contact(s) with GPS")

    def _on_hover(self, event):
        """Show tooltip near a dot when the mouse is close."""
        self._tooltip.place_forget()
        for cx, cy, _name, key in self._dot_info:
            dist = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
            if dist <= self.RADIUS + 4:
                c_list = [c for c in self.radio.get_contacts() if c.key == key]
                if c_list:
                    c = c_list[0]
                    tip = (f"{c.name}  ({c.lat:.4f}, {c.lon:.4f})\n"
                           f"RSSI {safe_str(c.rssi)}  SNR {safe_str(c.snr)}"
                           f"  Batt {safe_str(c.battery)}%")
                    self._tooltip.config(text=tip)
                    self._tooltip.place(x=event.x + 10, y=event.y + 10)
                break

    def _clear(self):
        self._canvas.delete("all")
        self._dot_info = []
        self._lbl.config(text="")


# ════════════════════════════════════════════════════════════════════════════
# Tab: Settings
# ════════════════════════════════════════════════════════════════════════════

class SettingsTab(TabBase):

    def __init__(self, parent, radio, bus, root, settings):
        super().__init__(parent, radio, bus, root, settings)
        self._vars: dict[str, tk.Variable] = {}
        self._build()

    def _build(self):
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=16, pady=10)

        def section(title):
            f = ttk.LabelFrame(outer, text=f" {title} ")
            f.pack(fill="x", pady=6)
            return f

        def check(parent, key, label):
            var = tk.BooleanVar(value=self.settings.get(key, False))
            self._vars[key] = var
            ttk.Checkbutton(parent, text=label, variable=var,
                            command=self._save).pack(anchor="w", padx=10, pady=2)

        def entry_row(parent, key, label, width=16):
            row = ttk.Frame(parent)
            row.pack(fill="x", padx=10, pady=3)
            ttk.Label(row, text=label, width=28, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            self._vars[key] = var
            e = ttk.Entry(row, textvariable=var, width=width)
            e.pack(side="left")
            e.bind("<FocusOut>", lambda _: self._save())
            e.bind("<Return>",   lambda _: self._save())

        # ── Notifications ──────────────────────────────────────────────────
        nf = section("Notifications")
        check(nf, "notify_dm",      "Desktop notification on incoming DM")
        check(nf, "notify_channel", "Desktop notification on Channel message")
        check(nf, "sound_dm",       "Sound alert on incoming DM")
        check(nf, "sound_channel",  "Sound alert on Channel message")
        ttk.Label(nf, text="  (install plyer for cross-platform notifications: pip install plyer)",
                  foreground=C["muted"], font=("", 8)).pack(anchor="w", padx=10)

        # ── Connection behaviour ───────────────────────────────────────────
        cf = section("Connection")
        check(cf, "auto_ping_enabled", "Auto-ping on Serial (prevents 30 s idle disconnect)")
        entry_row(cf, "auto_ping_interval", "Ping interval (seconds):", width=6)
        check(cf, "auto_reconnect", "Auto-reconnect TCP on disconnect")
        entry_row(cf, "reconnect_max", "Max reconnect attempts (0 = unlimited):", width=6)

        # ── Session log ────────────────────────────────────────────────────
        sf = section("Session Log")
        check(sf, "session_log", "Auto-save session log to file on connect")
        row2 = ttk.Frame(sf)
        row2.pack(fill="x", padx=10, pady=3)
        ttk.Label(row2, text="Log directory:").pack(side="left")
        ttk.Label(row2, text=SESSION_LOG_DIR, foreground=C["info"]).pack(side="left", padx=6)
        ttk.Button(sf, text="📂 Open log folder", command=self._open_log_folder).pack(
            anchor="w", padx=10, pady=4)

        # ── BLE PIN ────────────────────────────────────────────────────────
        bf = section("BLE Security")
        entry_row(bf, "last_ble_pin", "BLE PIN (leave blank for no PIN):", width=10)
        ttk.Label(bf,
                  text=("  Set a PIN on the device via the button UI first,\n"
                        "  then enter the matching PIN here before connecting."),
                  foreground=C["muted"], font=("", 8)).pack(anchor="w", padx=10)

        ttk.Button(outer, text="💾 Save settings", command=self._save).pack(pady=8)
        self._status = ttk.Label(outer, foreground=C["ok"])
        self._status.pack()

    def _save(self):
        for key, var in self._vars.items():
            raw = var.get()
            # Coerce int fields
            if key in ("auto_ping_interval", "reconnect_max", "last_tcp_port"):
                try:
                    raw = int(raw)
                except (ValueError, TypeError):
                    raw = self.settings.get(key)
            self.settings.set(key, raw)
        if self.settings.save():
            self._status.config(text="✅ Saved")
            self.after_tk(lambda: self._status.config(text=""), 2000)
            self.bus.emit(EV_SETTINGS_UPD)
        else:
            self._status.config(text="❌ Save failed")

    def _open_log_folder(self):
        import subprocess, sys
        try:
            if sys.platform == "win32":
                os.startfile(SESSION_LOG_DIR)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", SESSION_LOG_DIR])
            else:
                subprocess.Popen(["xdg-open", SESSION_LOG_DIR])
        except Exception:
            messagebox.showinfo("Log folder", SESSION_LOG_DIR)


# ════════════════════════════════════════════════════════════════════════════
# Tab: Log
# ════════════════════════════════════════════════════════════════════════════

class LogTab(TabBase):

    def __init__(self, parent, radio, bus, root, settings):
        super().__init__(parent, radio, bus, root, settings)
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
        ttk.Button(bf, text="🗑 Clear", command=self._clear).pack(side="left")
        ttk.Button(bf, text="💾 Save",  command=self._save).pack(side="left", padx=6)

    def _append(self, text: str, level: str = "info"):
        ts   = time.strftime("%H:%M:%S")
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
    def __init__(self, parent, title: str, prompt: str, default: str = ""):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.grab_set()
        self.result: "str | None" = None
        tk.Label(self, text=prompt, bg=C["bg"], fg=C["fg"],
                 padx=16, pady=10, justify="left").pack()
        self._v = tk.StringVar(value=default)
        e = tk.Entry(self, textvariable=self._v, width=36,
                     bg=C["entry"], fg=C["fg"], insertbackground=C["fg"])
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
    def __init__(self, parent, radio: NodeRadio, settings: Settings):
        super().__init__(parent)
        self.title("Connect via Bluetooth (BLE)")
        self.geometry("560x480")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self.grab_set()
        self.result:    "str | None" = None
        self.result_pin: str         = ""
        self._radio    = radio
        self._settings = settings
        self._build()
        self.wait_window()

    def _build(self):
        top = tk.Frame(self, bg=C["bg"])
        top.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(top, text="Address / Name:", bg=C["bg"], fg=C["fg"]).pack(side="left")
        self._av = tk.StringVar(value=self._settings.get("last_ble_address", ""))
        tk.Entry(top, textvariable=self._av, bg=C["entry"], fg=C["fg"],
                 insertbackground=C["fg"], width=26).pack(side="left", padx=6)
        tk.Button(top, text="🔍 Scan (5 s)", command=self._scan,
                  bg=C["btn"], fg=C["btn_fg"], activebackground=C["accent"],
                  relief="flat", padx=8, cursor="hand2").pack(side="left")

        # PIN row
        pin_row = tk.Frame(self, bg=C["bg"])
        pin_row.pack(fill="x", padx=10, pady=2)
        tk.Label(pin_row, text="BLE PIN (optional):", bg=C["bg"],
                 fg=C["fg"]).pack(side="left")
        self._pv = tk.StringVar(value=self._settings.get("last_ble_pin", ""))
        tk.Entry(pin_row, textvariable=self._pv, bg=C["entry"], fg=C["fg"],
                 insertbackground=C["fg"], width=12, show="*").pack(side="left", padx=6)
        tk.Label(pin_row, text="(leave blank for no PIN)",
                 bg=C["bg"], fg=C["muted"], font=("", 8)).pack(side="left")

        self._sv = tk.StringVar(
            value="Press Scan to discover devices, or type an address above.")
        tk.Label(self, textvariable=self._sv, bg=C["bg"], fg=C["info"],
                 anchor="w", wraplength=530).pack(fill="x", padx=10, pady=2)

        cols   = ("Name", "Address", "RSSI", "MeshCore?")
        widths = (200, 160, 55, 80)
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w")
        self._tree.tag_configure("mc",    foreground=C["ok"])
        self._tree.tag_configure("other", foreground=C["fg"])
        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
        sb.pack(side="left", fill="y", pady=4)
        self._tree.bind("<Double-1>",         lambda _: self._pick())
        self._tree.bind("<<TreeviewSelect>>",  self._on_sel)

        bf = tk.Frame(self, bg=C["bg"])
        bf.pack(side="bottom", fill="x", padx=10, pady=8)
        tk.Button(bf, text="✅ Connect", command=self._ok,
                  bg=C["accent"], fg=C["bg"], relief="flat",
                  padx=12, cursor="hand2").pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", command=self.destroy,
                  bg=C["btn"], fg=C["btn_fg"], relief="flat",
                  padx=12, cursor="hand2").pack(side="left", padx=4)
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
            self.result     = addr
            self.result_pin = self._pv.get().strip()
            # Persist last address and PIN
            self._settings.set("last_ble_address", addr)
            self._settings.set("last_ble_pin", self.result_pin)
            self._settings.save()
            self.destroy()


# ════════════════════════════════════════════════════════════════════════════
# AppWindow
# ════════════════════════════════════════════════════════════════════════════

class AppWindow(tk.Tk):

    APP_TITLE = "MeshCore Node Manager"

    def __init__(self):
        super().__init__()
        self._settings = Settings()
        self.title(self.APP_TITLE)
        geom = self._settings.get("window_geometry", "1160x820")
        self.geometry(geom)
        self.minsize(900, 600)
        self.configure(bg=C["bg"])

        self._bus   = EventBus(error_handler=self._bus_error)
        self._radio = NodeRadio(self._bus)
        self._radio.settings = self._settings

        # reconnect state
        self._reconnect_pending  = False
        self._reconnect_due_time = 0.0

        self._apply_style()
        self._build_toolbar()
        self._build_notebook()
        self._build_statusbar()
        self._wire_bus()
        self._tick()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-restore last connection hint in log
        last = self._settings.get("last_conn_type", "")
        if last:
            host = self._settings.get("last_tcp_host", "")
            port = self._settings.get("last_tcp_port", TCP_DEFAULT_PORT)
            addr = self._settings.get("last_ble_address", "")
            sp   = self._settings.get("last_serial_port", "")
            hints = {"TCP": f"TCP {host}:{port}", "BLE": f"BLE {addr}",
                     "Serial": f"Serial {sp}"}
            hint = hints.get(last, last)
            self._bus.emit(EV_LOG,
                           text=f"Last connection: {hint} — click to reconnect",
                           level="info")

    # ── style ────────────────────────────────────────────────────────────────

    def _apply_style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure(".", background=C["bg"], foreground=C["fg"],
                     fieldbackground=C["entry"], bordercolor=C["border"])
        s.configure("TNotebook",       background=C["bg"])
        s.configure("TNotebook.Tab",   background=C["btn"],
                     foreground=C["fg"], padding=[9, 4])
        s.map("TNotebook.Tab",
              background=[("selected", C["accent"])],
              foreground=[("selected", C["bg"])])
        for w in ("TFrame", "TLabel", "TCheckbutton",
                  "TLabelframe", "TLabelframe.Label"):
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

        btn("🔌 Serial",      self._do_serial)
        btn("🌐 TCP",         self._do_tcp)
        btn("🔵 BLE",         self._do_ble)
        btn("⏹ Disconnect",   self._do_disconnect)
        gap()
        btn("🔄 Contacts",    self._do_refresh)
        btn("📡 Ping",        self._do_ping)
        gap()
        btn("💾 Backup",      self._do_backup)
        btn("📂 Load Backup", self._do_load_backup)
        btn("📝 Export Msgs", self._do_export)
        tk.Frame(bar, bg=C["bg2"]).pack(side="left", expand=True, fill="x")
        btn("ℹ Info",         self._do_info)

    # ── notebook ──────────────────────────────────────────────────────────────

    def _build_notebook(self):
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=6, pady=4)
        self._tab_labels = {}
        tab_defs = [
            (ContactsTab, "📡 Contacts"),
            (ChannelTab,  "💬 Channel"),
            (DirectTab,   "📨 Direct"),
            (HistoryTab,  "📊 History"),
            (MapTab,      "🗺 Map"),
            (RadioTab,    "📻 Radio"),
            (SettingsTab, "⚙ Settings"),
            (LogTab,      "📋 Log"),
        ]
        self._tabs = {}
        for cls, label in tab_defs:
            widget = cls(self._nb, self._radio, self._bus, self, self._settings)
            self._nb.add(widget, text=label)
            self._tabs[label] = widget
            self._tab_labels[label] = label

        # Clear unread when user switches to that tab
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, _event=None):
        idx  = self._nb.index("current")
        name = self._nb.tab(idx, "text")
        # Strip any unread badge
        base = name.split(" (")[0]
        if "Direct" in base:
            self._radio.clear_unread_direct()
        elif "Channel" in base:
            self._radio.clear_unread_channel()

    def _update_tab_badge(self, direct: int, channel: int):
        for label, widget in self._tabs.items():
            base = label.split(" (")[0]
            if "Direct" in base:
                new = f"{base} ({direct})" if direct else base
                self._nb.tab(widget, text=new)
            elif "Channel" in base:
                new = f"{base} ({channel})" if channel else base
                self._nb.tab(widget, text=new)

    # ── status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=C["bg2"], pady=2)
        bar.pack(side="bottom", fill="x")
        self._status_v = tk.StringVar(value="⚫ Offline")
        tk.Label(bar, textvariable=self._status_v,
                 bg=C["bg2"], fg=C["info"], anchor="w").pack(side="left", padx=8)
        self._pending_v = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._pending_v,
                 bg=C["bg2"], fg=C["muted"], anchor="e").pack(side="right", padx=8)

    def _update_statusbar(self):
        if self._radio.online:
            ct = self._radio.conn_type
            nm = self._radio.node_name
            self._status_v.set(f"✅ Online [{ct}]  │  {nm}")
        elif self._reconnect_pending:
            self._status_v.set(f"🔄 Reconnecting [{self._radio.conn_type}]…")
        else:
            self._status_v.set("⚫ Offline")
        p = self._radio.pending_count()
        self._pending_v.set(f"⏳ {p} pending" if p else "")

    # ── bus wiring ────────────────────────────────────────────────────────────

    def _wire_bus(self):
        self._bus.on(EV_CONNECTED,
                     lambda **_: self.after(0, self._on_connected))
        self._bus.on(EV_DISCONNECTED,
                     lambda **_: self.after(0, self._on_disconnected))
        self._bus.on(EV_RECONNECTING,
                     lambda **kw: self.after(0, self._update_statusbar))
        self._bus.on(EV_CONN_ERROR,
                     lambda **kw: self.after(0, lambda: messagebox.showerror(
                         "Connection failed", kw.get("message", "Unknown error"))))
        self._bus.on(EV_UNREAD_CHANGE,
                     lambda **kw: self.after(0, lambda: self._update_tab_badge(
                         kw.get("direct", 0), kw.get("channel", 0))))
        self._bus.on(EV_SETTINGS_UPD,
                     lambda **_: self.after(0, self._update_statusbar))

    def _on_connected(self):
        self._reconnect_pending = False
        self._update_statusbar()
        self._tabs["📡 Contacts"].refresh()
        self._tabs["📻 Radio"].refresh_params()

    def _on_disconnected(self):
        self._update_statusbar()
        if (self._settings.get("auto_reconnect", True) and
                self._radio.conn_type == "TCP" and
                self._radio.has_conn_factory):
            self._reconnect_pending  = True
            self._reconnect_due_time = time.time() + RECONNECT_DELAY

    # ── toolbar actions ───────────────────────────────────────────────────────

    def _do_serial(self):
        default = self._settings.get("last_serial_port", "")
        dlg = _PromptDialog(self, "Serial Port",
                            "Enter port (e.g. COM3 or /dev/ttyUSB0):",
                            default=default)
        if dlg.result:
            port = dlg.result.strip()
            self._settings.set("last_serial_port", port)
            self._settings.set("last_conn_type", "Serial")
            self._settings.save()
            self._status_v.set("⏳ Connecting [Serial]…")
            self._bg_connect(lambda: self._radio.connect_serial(port))

    def _do_tcp(self):
        host_dlg = _PromptDialog(self, "TCP Host", "Enter IP address or hostname:",
                                  default=self._settings.get("last_tcp_host", ""))
        if not host_dlg.result:
            return
        port_dlg = _PromptDialog(self, "TCP Port",
                                  f"Port (default {TCP_DEFAULT_PORT}):",
                                  default=str(self._settings.get(
                                      "last_tcp_port", TCP_DEFAULT_PORT)))
        port = int(port_dlg.result) \
               if port_dlg.result and port_dlg.result.isdigit() \
               else TCP_DEFAULT_PORT
        host = host_dlg.result.strip()
        self._settings.set("last_tcp_host",  host)
        self._settings.set("last_tcp_port",  port)
        self._settings.set("last_conn_type", "TCP")
        self._settings.save()
        self._status_v.set("⏳ Connecting [TCP]…")
        self._bg_connect(lambda: self._radio.connect_tcp(host, port))

    def _do_ble(self):
        dlg = _BLEDialog(self, self._radio, self._settings)
        if dlg.result:
            self._settings.set("last_conn_type", "BLE")
            self._settings.save()
            self._status_v.set("⏳ Connecting [BLE]…")
            pin = dlg.result_pin
            self._bg_connect(lambda: self._radio.connect_ble(dlg.result, pin=pin))

    def _bg_connect(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _do_disconnect(self):
        self._reconnect_pending = False
        self._radio.clear_conn_factory()
        threading.Thread(target=self._radio.disconnect, daemon=True).start()

    def _do_refresh(self):
        if not self._radio.online:
            messagebox.showwarning("Offline", "Connect first.")
            return
        def run():
            self._radio.refresh_contacts()
            self.after(0, self._tabs["📡 Contacts"].refresh)
            self.after(0, self._tabs["📨 Direct"].update_dest_list)
            self.after(0, self._tabs["🗺 Map"].refresh)
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
            threading.Thread(target=lambda: self._radio.save_backup(path),
                             daemon=True).start()

    def _do_load_backup(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            title="Load backup")
        if path:
            data = self._radio.load_backup(path)
            if data:
                info  = {**data.get("device_info", {}), **data.get("radio", {})}
                lines = "\n".join(f"  {k}: {v}" for k, v in info.items())
                messagebox.showinfo(f"Backup — {data.get('node_name','?')}",
                                    f"Saved: {data.get('saved_at','?')}\n\n{lines}")

    def _do_export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            title="Export messages")
        if path:
            threading.Thread(target=lambda: self._radio.export_messages(path),
                             daemon=True).start()

    def _do_nexus(self):
        """Launch the NEXUS animated analytics dashboard."""
        from dashboard import NexusDashboard
        NexusDashboard(self, radio=self._radio)

    def _do_info(self):
        info = self._radio.device_info
        if not info:
            messagebox.showinfo("Device Info", "Not connected or no data available.")
            return
        lines = "\n".join(f"  {k}: {v}" for k, v in info.items())
        messagebox.showinfo(f"Device — {self._radio.node_name}", lines or "(empty)")

    # ── periodic tick ─────────────────────────────────────────────────────────

    def _tick(self):
        try:
            if self._radio.online:
                self._radio.sweep_timeouts()
            elif (self._reconnect_pending and
                  time.time() >= self._reconnect_due_time):
                self._reconnect_due_time = time.time() + RECONNECT_DELAY
                threading.Thread(target=self._radio.try_reconnect,
                                 daemon=True).start()
            self._update_statusbar()
        except Exception:
            pass
        self.after(5000, self._tick)

    # ── close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        try:
            self._settings.set("window_geometry", self.geometry())
            self._settings.save()
        except Exception:
            pass
        if self._radio.online:
            self._radio.disconnect()
        self.destroy()

    def _bus_error(self, event: str, exc: Exception):
        self._bus.emit(EV_LOG, text=f"Bus error [{event}]: {exc}", level="err")
