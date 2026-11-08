# -*- coding: utf-8 -*-
"""Orbiq - grafikus műholdkövető SDR++ Doppler-vezérléssel (Windows)."""
from __future__ import annotations

import datetime as dt
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import core
import skyplot
from core import Engine, SatEntry
import i18n
import storage
from i18n import tl
from viewlogic import DigitLayout, az_name, fmt_dur, fmt_mhz, fmt_signed_hz, fmt_time, map_url, parse_coord, split_coord_pair, sat_order, clashing, fmt_clash, sat_list_rows, rows_to_text

APP_TITLE = "Orbiq – satellite pass follower for SDR++ (Doppler)"

# Színpaletta (sötét téma)
C = dict(bg="#0d1117", panel="#161b22", raised="#21262d", hover="#2d333b", border="#30363d",
         text="#e6edf3", muted="#8b949e", dim="#6e7681", accent="#2f81f7", accent_hi="#4493f8",
         accent_lo="#1f6feb", green="#3fb950", green_bg="#12361f", red="#f85149", amber="#d29922",
         amber_bg="#3a2f0b", blue="#58a6ff", blue_bg="#12315e", good_bg="#102a1b", purple_bg="#2a1b45", red_bg="#3d1a1d", display="#010409")
def build_id() -> str:
    """A futó verzió azonosítója (a zip-ből: commit + dátum; git pull esetén: az aktuális commit) - hibakereséshez."""
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, "version.txt"), encoding="utf-8") as f:
            v = f.read().strip()
        if v and not v.startswith("$Format"):
            return v
    except OSError:
        pass
    try:
        import subprocess
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=base, capture_output=True, text=True, timeout=2)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:                                   # noqa: BLE001
        pass
    return "dev"


FONT = "Segoe UI"


def apply_theme(root) -> None:
    """Egységes sötét megjelenés (ttk 'clam' témára építve)."""
    st = ttk.Style(root)
    for th in ("clam", "vista"):
        if th in st.theme_names():
            st.theme_use(th)
            break
    root.configure(bg=C["bg"])
    root.option_add("*Font", (FONT, 10))
    root.option_add("*Text.selectBackground", C["accent_lo"])
    st.configure(".", background=C["bg"], foreground=C["text"], fieldbackground=C["panel"],
                 bordercolor=C["border"], lightcolor=C["bg"], darkcolor=C["bg"], troughcolor=C["bg"],
                 focuscolor=C["bg"], insertcolor=C["text"], font=(FONT, 10))
    st.configure("TFrame", background=C["bg"])
    st.configure("Bar.TFrame", background=C["panel"])
    st.configure("TLabel", background=C["bg"], foreground=C["text"])
    st.configure("Bar.TLabel", background=C["panel"], foreground=C["muted"], font=("Consolas", 11))
    st.configure("Hint.TLabel", foreground=C["muted"], font=(FONT, 9))
    st.configure("Cap.TLabel", foreground=C["text"], font=(FONT, 10, "bold"))
    st.configure("Title.TLabel", foreground=C["text"], font=(FONT, 15, "bold"))
    st.configure("Sub.TLabel", foreground=C["muted"], font=(FONT, 10))
    st.configure("Head.TLabel", foreground=C["blue"], font=(FONT, 10, "bold"))
    st.configure("Ok.TLabel", foreground=C["green"], font=(FONT, 9))
    st.configure("TLabelframe", background=C["bg"], bordercolor=C["border"], lightcolor=C["border"],
                 darkcolor=C["border"], borderwidth=1, relief="solid")
    st.configure("TLabelframe.Label", background=C["bg"], foreground=C["muted"], font=(FONT, 9, "bold"))
    st.configure("TSeparator", background=C["border"])

    st.configure("TButton", background=C["raised"], foreground=C["text"], bordercolor=C["border"],
                 lightcolor=C["raised"], darkcolor=C["raised"], focuscolor=C["raised"], padding=(12, 6),
                 relief="flat", font=(FONT, 10))
    st.map("TButton", background=[("disabled", C["panel"]), ("pressed", C["border"]), ("active", C["hover"])],
           foreground=[("disabled", C["dim"])], bordercolor=[("active", C["muted"]), ("disabled", C["panel"])],
           lightcolor=[("active", C["hover"])], darkcolor=[("active", C["hover"])])
    for name, pad, fnt in (("Accent.TButton", (12, 6), (FONT, 10, "bold")), ("Big.TButton", (22, 9), (FONT, 11, "bold"))):
        st.configure(name, background=C["accent"], foreground="white", bordercolor=C["accent"],
                     lightcolor=C["accent"], darkcolor=C["accent"], focuscolor=C["accent"], padding=pad,
                     relief="flat", font=fnt)
        st.map(name, background=[("disabled", C["raised"]), ("pressed", C["accent_lo"]), ("active", C["accent_hi"])],
               foreground=[("disabled", C["dim"])], bordercolor=[("active", C["accent_hi"])],
               lightcolor=[("active", C["accent_hi"])], darkcolor=[("active", C["accent_hi"])])

    for name in ("TEntry", "TSpinbox"):
        st.configure(name, fieldbackground=C["panel"], foreground=C["text"], insertcolor=C["text"],
                     bordercolor=C["border"], lightcolor=C["panel"], darkcolor=C["panel"], padding=5,
                     arrowcolor=C["muted"], arrowsize=13)
        st.map(name, bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent"])],
               darkcolor=[("focus", C["accent"])], fieldbackground=[("disabled", C["bg"])],
               foreground=[("disabled", C["dim"])])
    for name, bgc in (("TCheckbutton", C["bg"]), ("TRadiobutton", C["bg"]),
                      ("Bar.TCheckbutton", C["panel"]), ("Bar.TRadiobutton", C["panel"])):
        st.configure(name, background=bgc, foreground=C["text"], indicatorbackground=C["bg"],
                     indicatorforeground="white", upperbordercolor=C["muted"], lowerbordercolor=C["muted"],
                     focuscolor=bgc, padding=(2, 3))
        st.map(name, background=[("active", bgc)], foreground=[("active", C["text"])],
               indicatorcolor=[("selected", C["accent"]), ("!selected", C["bg"])],
               indicatorbackground=[("selected", C["accent"]), ("!selected", C["bg"])])

    st.configure("TCombobox", fieldbackground=C["panel"], background=C["raised"], foreground=C["text"],
                 arrowcolor=C["muted"], bordercolor=C["border"], lightcolor=C["panel"], darkcolor=C["panel"],
                 selectbackground=C["panel"], selectforeground=C["text"], padding=5)
    st.map("TCombobox", fieldbackground=[("readonly", C["panel"]), ("disabled", C["bg"])],
           foreground=[("readonly", C["text"])], selectbackground=[("readonly", C["panel"])],
           selectforeground=[("readonly", C["text"])], bordercolor=[("focus", C["accent"])],
           background=[("active", C["hover"])])
    root.option_add("*TCombobox*Listbox.background", C["panel"])
    root.option_add("*TCombobox*Listbox.foreground", C["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent_lo"])
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    st.configure("TNotebook", background=C["bg"], bordercolor=C["border"], lightcolor=C["bg"],
                 darkcolor=C["bg"], tabmargins=(8, 6, 8, 0))
    st.configure("TNotebook.Tab", background=C["panel"], foreground=C["muted"], padding=(18, 8),
                 bordercolor=C["border"], lightcolor=C["panel"], darkcolor=C["panel"], font=(FONT, 10, "bold"))
    st.map("TNotebook.Tab", background=[("selected", C["bg"]), ("active", C["raised"])],
           foreground=[("selected", C["text"]), ("active", C["text"])],
           lightcolor=[("selected", C["accent"])], darkcolor=[("selected", C["bg"])])

    st.configure("Treeview", background=C["panel"], fieldbackground=C["panel"], foreground=C["text"],
                 bordercolor=C["border"], lightcolor=C["panel"], darkcolor=C["panel"], rowheight=28,
                 borderwidth=0, font=(FONT, 10))
    st.map("Treeview", background=[("selected", C["accent_lo"])], foreground=[("selected", "white")])
    st.configure("Treeview.Heading", background=C["raised"], foreground=C["muted"], bordercolor=C["border"],
                 lightcolor=C["raised"], darkcolor=C["raised"], relief="flat", padding=(6, 7),
                 font=(FONT, 9, "bold"))
    st.map("Treeview.Heading", background=[("active", C["hover"])], foreground=[("active", C["text"])])
    st.configure("Vertical.TScrollbar", background=C["raised"], troughcolor=C["bg"], bordercolor=C["bg"],
                 lightcolor=C["raised"], darkcolor=C["raised"], arrowcolor=C["muted"], arrowsize=13,
                 gripcount=0)
    st.map("Vertical.TScrollbar", background=[("active", C["border"]), ("pressed", C["muted"])])
    st.configure("Horizontal.TScrollbar", background=C["raised"], troughcolor=C["bg"], bordercolor=C["bg"],
                 lightcolor=C["raised"], darkcolor=C["raised"], arrowcolor=C["muted"], arrowsize=13,
                 gripcount=0)
    st.map("Horizontal.TScrollbar", background=[("active", C["border"]), ("pressed", C["muted"])])


def dark_text(parent, **kw) -> tk.Text:
    """Sötét témájú szövegmező."""
    opts = dict(bg=C["panel"], fg=C["text"], insertbackground=C["text"], relief="flat", bd=0,
                highlightthickness=1, highlightbackground=C["border"], highlightcolor=C["border"],
                selectbackground=C["accent_lo"], selectforeground="white")
    opts.update(kw)
    return tk.Text(parent, **opts)


def caption(parent, title: str, hint: str = "") -> ttk.Frame:
    """Kis felirat: félkövér cím + halvány magyarázó sor."""
    f = ttk.Frame(parent)
    ttk.Label(f, text=title, style="Cap.TLabel").pack(anchor="w")
    if hint:
        ttk.Label(f, text=hint, style="Hint.TLabel", justify="left").pack(anchor="w")
    return f


# --------------------------------------------------------------------------
# Háttérszálak a hálózati hívásokhoz (az eredmény a fő szálban érkezik meg)
# --------------------------------------------------------------------------
class BG:
    def __init__(self, root: tk.Misc):
        self.root = root
        self.q: "queue.Queue" = queue.Queue()
        root.after(100, self._poll)

    def run(self, fn, done=None):
        def work():
            try:
                self.q.put((done, fn(), None))
            except Exception as e:           # noqa: BLE001
                self.q.put((done, None, e))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                done, res, err = self.q.get_nowait()
                if done:
                    try:
                        done(res, err)
                    except tk.TclError:
                        pass                 # az ablak közben bezárult
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


# --------------------------------------------------------------------------
# SDR++ stílusú számjegyes frekvenciakijelző
# --------------------------------------------------------------------------
class Tabs(ttk.Frame):
    """Lapos, modern fülsor: csak felirat, a kiválasztott fül alatt vastag kék vonal. A lapokat a `.body`
    keretbe kell létrehozni, majd `add(lap, text=...)`-tal felvenni (mint a ttk.Notebooknál)."""

    def __init__(self, master):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.bar = tk.Frame(self, bg=C["bg"])
        self.bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        tk.Frame(self, height=1, bg=C["border"]).grid(row=1, column=0, sticky="ew")
        self.body = ttk.Frame(self)
        self.body.grid(row=2, column=0, sticky="nsew")
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)
        self._tabs = []          # (lap, felirat, vonal)
        self._cur = None

    def add(self, frame, text=""):
        cell = tk.Frame(self.bar, bg=C["bg"], cursor="hand2")
        cell.pack(side="left", padx=(0, 6))
        lab = tk.Label(cell, text=text, bg=C["bg"], fg=C["muted"], font=(FONT, 11, "bold"), padx=16, pady=8,
                       cursor="hand2")
        lab.pack()
        line = tk.Frame(cell, height=3, bg=C["bg"])
        line.pack(fill="x")
        entry = (frame, lab, line)
        for w in (cell, lab):
            w.bind("<Button-1>", lambda _e, f=frame: self.select(f))
            w.bind("<Enter>", lambda _e, en=entry: self._hover(en, True))
            w.bind("<Leave>", lambda _e, en=entry: self._hover(en, False))
        frame.grid(in_=self.body, row=0, column=0, sticky="nsew")
        self._tabs.append(entry)
        self.select(frame if self._cur is None else self._cur)

    def _hover(self, entry, on):
        frame, lab, line = entry
        if frame is self._cur:
            return
        lab.configure(fg=C["text"] if on else C["muted"])
        line.configure(bg=C["border"] if on else C["bg"])

    def select(self, frame):
        self._cur = frame
        for f, lab, line in self._tabs:
            active = f is frame
            lab.configure(fg=C["text"] if active else C["muted"])
            line.configure(bg=C["accent"] if active else C["bg"])
            if active:
                f.tkraise()


class ScrollFrame(ttk.Frame):
    """Függőlegesen görgethető tartalom (kis képernyőn sem lóg ki semmi). A tartalom a `.inner` keretbe kerül."""

    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, bg=C["bg"], highlightthickness=0, bd=0, yscrollincrement=20)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.bind_all("<MouseWheel>", self._wheel, add="+")

    def _wheel(self, e):
        try:
            if self.canvas.winfo_viewable() and self.inner.winfo_reqheight() > self.canvas.winfo_height():
                self.canvas.yview_scroll(-3 if e.delta > 0 else 3, "units")
        except tk.TclError:
            pass


class FreqDisplay(tk.Canvas):
    def __init__(self, master, on_delta, editable: bool = True, small: bool = False):
        self.small = small
        self.editable = editable and on_delta is not None
        self.dl = DigitLayout(10, 28, 12, 10) if small else DigitLayout(10, 36, 16, 12)
        super().__init__(master, width=self.dl.width + 46, height=64 if small else 92, bg=C["display"],
                         highlightthickness=1, highlightbackground=C["border"])
        self.on_delta = on_delta
        self.value = 0
        self.active = False
        self.preview = False
        self.hover = None
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda e: self._step(e.x, +1))
        self.bind("<Button-5>", lambda e: self._step(e.x, -1))
        self.redraw()

    def set_state(self, value_hz, active: bool, preview: bool = False):
        v = int(round(value_hz)) if value_hz else 0
        if (v, active, preview) != (self.value, self.active, self.preview):
            self.value, self.active, self.preview = v, active, preview
            self.redraw()

    def _motion(self, e):
        h = self.dl.hit(e.x) if (self.active and self.editable) else None
        if h != self.hover:
            self.hover = h
            self.redraw()

    def _leave(self, _e):
        self.hover = None
        self.redraw()

    def _step(self, x, sign):
        p = self.dl.hit(x)
        if self.editable and self.active and p is not None:
            self.on_delta(sign * 10 ** p)

    def _click(self, e):
        self._step(e.x, +1 if e.y < int(self["height"]) / 2 else -1)

    def _wheel(self, e):
        self._step(e.x, +1 if e.delta > 0 else -1)

    def redraw(self):
        self.delete("all")
        L = self.dl
        h = int(self["height"])
        fs, sfs, tri = (26, 22, 5) if self.small else (36, 30, 7)
        on = "#7cfc9a" if self.active and not self.preview else ("#8fb7a0" if self.active else "#4a5560")
        off = "#2b4a35" if self.active else "#2a3138"
        if not self.editable:
            on = "#e6edf3" if self.active and not self.preview else ("#9aa7b4" if self.active else "#4a5560")
            off = "#3a4552"
        for (x0, x1, p), (ch, dim) in zip(L.cells, L.digits(self.value)):
            xm = (x0 + x1) / 2
            if self.hover == p:
                self.create_rectangle(x0, 4, x1, h - 4, outline="#3b82f6", fill="#14202e")
                self.create_polygon(xm, 6, xm - tri, 6 + tri + 4, xm + tri, 6 + tri + 4, fill="#3b82f6")
                self.create_polygon(xm, h - 6, xm - tri, h - 10 - tri, xm + tri, h - 10 - tri, fill="#3b82f6")
            self.create_text(xm, h / 2, text=ch, fill=off if dim else on, font=("Consolas", fs, "bold"))
        for sx in L.seps:
            self.create_text(sx, h / 2 + fs / 3, text=".", fill=on, font=("Consolas", sfs, "bold"))
        self.create_text(L.width + 18, h / 2 + fs / 3, text="Hz", fill=C["muted"], font=("Segoe UI", 11))


# --------------------------------------------------------------------------
# Műhold hozzáadása / szerkesztése
# --------------------------------------------------------------------------
class SatDialog(tk.Toplevel):
    def __init__(self, app: "App", norad: int | None = None):
        super().__init__(app)
        self.app = app
        self.edit = norad is not None
        self.title(tl("dialog.muhold_szerkesztese_frekvencia") if self.edit else tl("dialog.muhold_keresese_norad_id"))
        self.configure(bg=C["bg"])
        self.transient(app)
        self.grab_set()
        self.resizable(True, True)
        self.fetched = None
        self.tx = []
        self.sat = app.engine.sats.get(norad) if self.edit else None

        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(3, weight=1)

        ttk.Label(f, text=tl("dialog.norad_id")).grid(row=0, column=0, sticky="w")
        self.v_norad = tk.StringVar(value=str(norad) if self.edit else "")
        e = ttk.Entry(f, textvariable=self.v_norad, width=12, state="disabled" if self.edit else "normal")
        e.grid(row=0, column=1, sticky="w", padx=6)
        self.btn_search = ttk.Button(f, text=tl("dialog.kereses") if not self.edit else tl("dialog.frissites_a_satnogs_rol"),
                                     style="Accent.TButton", command=self.search)
        self.btn_search.grid(row=0, column=2, padx=4)
        if not self.edit:
            e.focus_set()
            self.bind("<Return>", lambda _e: self.search())

        self.v_info = tk.StringVar(value=tl("dialog.add_meg_a_norad")
                                   if not self.edit else "")
        ttk.Label(f, textvariable=self.v_info, style="Sub.TLabel").grid(row=1, column=0, columnspan=3,
                                                                    sticky="w", pady=(8, 4))
        ttk.Label(f, text=tl("dialog.elerheto_frekvenciak_satnogs_a")).grid(
            row=2, column=0, columnspan=3, sticky="w")

        cols = ("desc", "freq", "mode", "baud", "state")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse", height=9)
        for c, t, w in (("desc", tl("dialog.leiras"), 260), ("freq", tl("dialog.frekvencia_mhz"), 120), ("mode", tl("dialog.mod"), 80),
                        ("baud", "Baud", 70), ("state", tl("dialog.allapot"), 80)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w" if c == "desc" else "center")
        self.tree.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=4)
        self.tree.tag_configure("dead", foreground=C["dim"])
        self.tree.bind("<<TreeviewSelect>>", self.on_pick)

        opt = ttk.LabelFrame(f, text=tl("dialog.beallitasok"), padding=8)
        opt.grid(row=4, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(opt, text=tl("dialog.kovetett_frekvencia_mhz")).grid(row=0, column=0, sticky="w")
        self.v_freq = tk.StringVar(value=f"{self.sat.freq_hz / 1e6:.6f}" if self.sat and self.sat.freq_hz else "")
        ttk.Entry(opt, textvariable=self.v_freq, width=16).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(opt, text=tl("dialog.a_listabol_kivalasztva_kitolto"),
                  style="Hint.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(opt, text=tl("dialog.min_elevacioja")).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.v_minel = tk.StringVar(value="" if not self.sat or self.sat.min_elev is None else f"{self.sat.min_elev:g}")
        ttk.Entry(opt, textvariable=self.v_minel, width=8).grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        ttk.Label(opt, text=tl("dialog.uresen_hagyva_a_beallitasok"),
                  style="Hint.TLabel").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.v_en = tk.BooleanVar(value=self.sat.enabled if self.sat else True)
        self.v_rec = tk.BooleanVar(value=self.sat.record if self.sat else True)
        ttk.Checkbutton(opt, text=tl("dialog.kovetes_engedelyezve"), variable=self.v_en).grid(row=2, column=0, columnspan=2,
                                                                                    sticky="w", pady=(6, 0))
        ttk.Checkbutton(opt, text=tl("dialog.felvetel_inditasa_leallitasa_a"), variable=self.v_rec).grid(
            row=2, column=2, sticky="w", pady=(6, 0))

        bt = ttk.Frame(f)
        bt.grid(row=5, column=0, columnspan=3, sticky="e", pady=(6, 0))
        self.btn_save = ttk.Button(bt, text=tl("dialog.mentes"), style="Accent.TButton", command=self.save, state="normal" if self.edit else "disabled")
        self.btn_save.pack(side="left", padx=8)
        ttk.Button(bt, text=tl("dialog.megse"), command=self.destroy).pack(side="left")

        if self.edit:
            self.tx = list(self.sat.transmitters)
            self.fill_tx()
            self.v_info.set(tl("dialog.name_a_mentett_frekvencialista", name=self.sat.name))
        self.geometry("760x560")

    def fill_tx(self):
        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(self.tx):
            f = fmt_mhz(t["downlink_hz"], 6)
            if t.get("downlink_high_hz"):
                f += f" – {fmt_mhz(t['downlink_high_hz'], 6)}"
            self.tree.insert("", "end", iid=str(i), tags=() if t.get("alive") else ("dead",),
                             values=(t.get("description") or t.get("type") or "—", f, t.get("mode", ""),
                                     t.get("baud") or "", tl("dialog.aktiv") if t.get("alive") else tl("dialog.inaktiv")))

    def on_pick(self, _e=None):
        sel = self.tree.selection()
        if sel:
            t = self.tx[int(sel[0])]
            self.v_freq.set(f"{t['downlink_hz'] / 1e6:.6f}")

    def search(self):
        try:
            norad = int(self.v_norad.get().strip())
        except ValueError:
            messagebox.showerror(tl("dialog.hibas_azonosito"), tl("dialog.a_norad_id_csak"), parent=self)
            return
        if not self.edit and norad in self.app.engine.sats:
            messagebox.showinfo(tl("dialog.mar_koveted"), tl("dialog.ez_a_muhold_mar"), parent=self)
            return
        self.btn_search.state(["disabled"])
        self.v_info.set(tl("dialog.kereses_folyamatban_celestrak_"))

        def work():
            name, l1, l2 = core.fetch_tle(norad)
            info = core.fetch_sat_info(norad)
            try:
                tx, txerr = core.fetch_transmitters(norad), None
            except Exception as e:           # noqa: BLE001
                tx, txerr = [], str(e)
            return {"norad": norad, "name": info.get("name") or name, "l1": l1, "l2": l2,
                    "tx": tx, "txerr": txerr, "status": info.get("status", "")}

        self.app.bg.run(work, self.on_found)

    def on_found(self, res, err):
        self.btn_search.state(["!disabled"])
        if err:
            self.v_info.set("")
            messagebox.showerror(tl("dialog.nem_talalhato"), str(err), parent=self)
            return
        self.fetched = res
        self.tx = res["tx"]
        self.fill_tx()
        msg = tl("dialog.talalat_name_norad_norad", name=res['name'], norad=res['norad'])
        if res["status"]:
            msg += tl("dialog.allapot_status", status=res['status'])
        if res["txerr"]:
            msg += tl("dialog.a_frekvencialistat_nem_sikerul", txerr=res['txerr'])
        elif not res["tx"]:
            msg += tl("dialog.a_satnogs_adatbazisban_nincs")
        self.v_info.set(msg)
        if self.tx and not self.v_freq.get():
            alive = [i for i, t in enumerate(self.tx) if t.get("alive")]
            i = alive[0] if alive else 0
            self.tree.selection_set(str(i))
        self.btn_save.state(["!disabled"])

    def save(self):
        try:
            f_hz = float(self.v_freq.get().replace(",", ".")) * 1e6
            if f_hz < 1e6:
                raise ValueError
        except ValueError:
            messagebox.showerror(tl("dialog.hibas_frekvencia"), tl("dialog.adj_meg_egy_frekvenciat"), parent=self)
            return
        me = self.v_minel.get().strip().replace(",", ".")
        try:
            min_el = float(me) if me else None
            if min_el is not None and not (0 <= min_el < 90):
                raise ValueError
        except ValueError:
            messagebox.showerror(tl("dialog.hibas_elevacios_ertek"), tl("dialog.a_minimum_elevacio_0"), parent=self)
            return
        desc, mode = tl("dialog.kezi"), ""
        sel = self.tree.selection()
        if sel and abs(self.tx[int(sel[0])]["downlink_hz"] - f_hz) < 1:
            t = self.tx[int(sel[0])]
            desc, mode = t.get("description") or t.get("type") or "", t.get("mode", "")
        eng = self.app.engine
        if self.edit:
            changed = abs(f_hz - self.sat.freq_hz) >= 1
            kw = dict(freq_hz=f_hz, min_elev=min_el, enabled=self.v_en.get(), record=self.v_rec.get(),
                      transmitters=self.tx)
            if changed:
                kw.update(freq_desc=desc, mode=mode, offset_hz=0.0)
            elif sel and abs(self.tx[int(sel[0])]["downlink_hz"] - f_hz) < 1:
                kw.update(freq_desc=desc, mode=mode)        # ugyanaz a frekvencia, de a listából kiválasztott adó adatait elmentjük
            eng.update_sat(self.sat.norad, **kw)
        else:
            r = self.fetched
            eng.add_sat(SatEntry(norad=r["norad"], name=r["name"], enabled=self.v_en.get(),
                                 record=self.v_rec.get(), min_elev=min_el, freq_hz=f_hz, freq_desc=desc, mode=mode,
                                 tle1=r["l1"], tle2=r["l2"], tle_fetched=time.time(), transmitters=self.tx))
            self.app.select_sat(r["norad"])
        self.app.request_passes(force=True)
        self.destroy()


# --------------------------------------------------------------------------
# Főablak
# --------------------------------------------------------------------------
def _asset(name: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", name)


class App(tk.Tk):
    def _set_icon(self):
        """Az ablak és a tálca ikonja (a logó); ha a fájl nincs meg, marad az alapértelmezett."""
        try:
            ico = _asset("logo.ico")
            if os.name == "nt" and os.path.exists(ico):
                self.iconbitmap(default=ico)
            png = _asset("logo.png")
            if os.path.exists(png):
                self._icon_img = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_img)
        except Exception:                            # noqa: BLE001 - az ikon sosem akadályozhatja az indulást
            pass

    def __init__(self, engine: Engine):
        super().__init__()
        self.engine = engine
        self.title(f"{APP_TITLE}  [{build_id()}]")
        self._set_icon()
        self.geometry("1320x860")
        self.minsize(1120, 740)
        self._fullscreen = False
        self.bind("<F11>", self.toggle_fullscreen)
        if engine.cfg.get("ui", {}).get("maximized", True):
            try:
                self.state("zoomed")          # Windows: maximalizált ablak
            except tk.TclError:
                pass
        self.bg = BG(self)
        self.selected: int | None = None
        self.freq_target: int | None = None
        self.pass_data = (None, [], 0.0)       # (norad, [Pass], mikor számoltuk)
        self.next_pass = {}                    # norad -> {"key", "pass" (a következő megfelelő áthaladás), "ts"}
        self._jump = None
        self._tle_busy = False
        self._clash_rows = {}
        self._filled_n = None
        self._nxt_sig = None
        self._row_cache = {}                   # iid -> (értékek, címkék): csak a megváltozott sorokat frissítjük
        self._cfg_cache = {}                   # widget -> utoljára beállított értékek
        self.all_passes = {}
        self.allp_busy = False
        self.pass_key = None
        self.pass_busy = False
        self._log_marker = None
        self._restored = False
        self.sel_pass = None                   # (norad, Pass) - a kijelölt áthaladás
        self.sel_track = []
        self.sel_info = None                   # a rajzolónak átadott adatok a kijelölt áthaladásról
        self._sky_sig = None
        self._sky_painter = None

        apply_theme(self)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_topbar()
        nb = Tabs(self)
        nb.grid(row=2, column=0, sticky="nsew")
        t1, t4, t2, t3 = ttk.Frame(nb.body), ttk.Frame(nb.body), ttk.Frame(nb.body), ttk.Frame(nb.body)
        nb.add(t1, text=tl("app.kovetes"))
        nb.add(t4, text=tl("list.tab"))
        nb.add(t2, text=tl("app.beallitasok"))
        nb.add(t3, text=tl("app.sugo"))
        self._build_main(t1)
        self._build_sats(t4)
        self._build_settings(t2)
        self._build_help(t3)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if not engine.location_ok():
            nb.select(t2)
            self.after(400, lambda: messagebox.showinfo(
                tl("app.elso_inditas"), tl("app.eloszor_add_meg_az"), parent=self))

        if storage.last_load_info:                # a beállításfájl sérült volt: tájékoztatás a visszaállításról
            src = storage.last_load_info[1]
            storage.last_load_info = None
            engine.log.append((time.time(), tl("msg.recovered", src=src)))
            self.after(600, lambda: messagebox.showwarning(tl("msg.title_backup"), tl("msg.recovered", src=src),
                                                           parent=self))
        self.bg.run(engine.measure_ntp, self._ntp_done)
        self.after(3000, self.auto_tle)
        self._fast_snap = None
        self.after(250, self.refresh)
        self.after(300, self._fast_tick)

    # ---- felső sáv -----------------------------------------------------
    def _build_topbar(self):
        P = C["panel"]
        bar = ttk.Frame(self, style="Bar.TFrame", padding=(14, 10))
        bar.grid(row=0, column=0, sticky="ew")
        tk.Frame(self, height=1, bg=C["border"]).grid(row=1, column=0, sticky="ew")
        self.btn_track = tk.Button(bar, text="", font=(FONT, 11, "bold"), width=24, bd=0, relief="flat",
                                   pady=12, command=self.toggle_tracking, cursor="hand2")
        self.btn_track.pack(side="left")
        self.v_mode = tk.StringVar(value=self.engine.mode)
        mf = ttk.Frame(bar, style="Bar.TFrame")
        mf.pack(side="left", padx=(20, 0))
        for text, val in ((tl("topbar.kijelolt_muholdat_koveti"), "selected"),
                          (tl("topbar.automatikus_valtas_elevacios_s"), "auto"),
                          (tl("topbar.csak_a_kijelolt_athaladasokat"), "passes")):
            ttk.Radiobutton(mf, text=text, value=val, variable=self.v_mode, style="Bar.TRadiobutton",
                            command=self.on_mode).pack(anchor="w")
        info = ttk.Frame(bar, style="Bar.TFrame")
        info.pack(side="left", padx=(28, 0))
        self.lbl_rig = tk.Label(info, text="", font=(FONT, 10, "bold"), bg=P, fg=C["muted"])
        self.lbl_rig.pack(anchor="w")
        sub = ttk.Frame(info, style="Bar.TFrame")
        sub.pack(anchor="w", pady=(4, 0))
        self.lbl_rec = tk.Label(sub, text="", font=(FONT, 10, "bold"), bg=P, fg=C["red"])
        self.lbl_rec.pack(side="left")
        self.lbl_warn = tk.Label(sub, text="", font=(FONT, 10, "bold"), bg=P, fg=C["amber"])
        self.lbl_warn.pack(side="left")
        self.lbl_next = tk.Label(sub, text="", font=(FONT, 10, "bold"), bg=P, fg=C["blue"])
        self.lbl_next.pack(side="left")
        clock = tk.Frame(bar, bg=P)
        clock.pack(side="right", padx=(0, 4))
        loc = tk.Frame(clock, bg=P)
        loc.pack(side="left")
        self.cap_local = tk.Label(loc, text="", font=(FONT, 8, "bold"), bg=P, fg=C["muted"], anchor="e")
        self.cap_local.pack(anchor="e")
        self.lbl_local = tk.Label(loc, text="--:--:--", font=("Consolas", 22, "bold"), bg=P, fg=C["text"], anchor="e")
        self.lbl_local.pack(anchor="e")
        tk.Frame(clock, bg=C["border"], width=1).pack(side="left", fill="y", padx=16, pady=4)
        utc = tk.Frame(clock, bg=P)
        utc.pack(side="left")
        self.cap_utc = tk.Label(utc, text="UTC", font=(FONT, 8, "bold"), bg=P, fg=C["muted"], anchor="e")
        self.cap_utc.pack(anchor="e")
        self.lbl_utc = tk.Label(utc, text="--:--:--", font=("Consolas", 22, "bold"), bg=P, fg=C["blue"], anchor="e")
        self.lbl_utc.pack(anchor="e")

    def on_mode(self):
        m = self.v_mode.get()
        self.engine.set_mode(m)
        if m == "selected" and self.selected is not None:
            self.engine.set_pinned(self.selected)

    def toggle_tracking(self):
        self.engine.set_tracking(not self.engine.tracking_on)

    # ---- fő fül ----------------------------------------------------------
    def _build_main(self, parent):
        parent.columnconfigure(0, weight=3)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(0, weight=1)
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        right = ttk.Frame(parent)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        left.rowconfigure(2, weight=1)

        # frekvenciakijelző
        fb = ttk.LabelFrame(left, text=tl("main.frekvencia"), padding=12)
        fb.grid(row=0, column=0, sticky="ew")
        caption(fb, tl("main.veteli_frekvencia"), tl("main.doppler_korrigalt_csak_kijelzo")).grid(
            row=0, column=0, sticky="w", padx=(0, 16))
        self.freq = FreqDisplay(fb, None, editable=False)
        self.freq.grid(row=0, column=1, sticky="w")
        caption(fb, tl("main.alapfrekvencia"), tl("main.doppler_nelkul_itt_allithato")).grid(
            row=1, column=0, sticky="w", padx=(0, 16), pady=(12, 0))
        self.base_freq = FreqDisplay(fb, self.on_digit, small=True)
        self.base_freq.grid(row=1, column=1, sticky="w", pady=(12, 0))
        self.v_sat = tk.StringVar(value=tl("main.nincs_kovetett_muhold"))
        self.v_dop = tk.StringVar(value="")
        self.v_pos = tk.StringVar(value="")
        ttk.Label(fb, textvariable=self.v_sat, style="Title.TLabel").grid(row=2, column=0, columnspan=2,
                                                                          sticky="w", pady=(14, 2))
        ttk.Label(fb, textvariable=self.v_dop, style="Sub.TLabel").grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(fb, textvariable=self.v_pos, style="Sub.TLabel").grid(row=4, column=0, columnspan=2, sticky="w")

        # követett műholdak
        sb = ttk.LabelFrame(left, text=tl("main.kovetett_muholdak"), padding=8)
        sb.grid(row=1, column=0, sticky="nsew", pady=10)
        sb.columnconfigure(0, weight=1)
        sb.rowconfigure(0, weight=1)
        cols = ("act", "name", "norad", "freq", "minel", "el", "next", "maxel", "status", "clash")
        self.tree = ttk.Treeview(sb, columns=cols, show="headings", selectmode="browse", height=6)
        for c, t, w, a, st in (("act", tl("main.be"), 36, "center", False), ("name", tl("main.nev"), 110, "w", False),
                               ("norad", "NORAD", 62, "center", False),
                               ("freq", tl("main.frekvencia_mhz"), 105, "center", False),
                               ("minel", tl("main.min_el"), 58, "center", False),
                               ("el", tl("main.elev_most"), 68, "center", False),
                               ("next", tl("main.kovetkezo_athaladas"), 230, "w", False),
                               ("maxel", tl("main.max_el"), 62, "center", False),
                               ("status", tl("main.allapot"), 240, "w", False),
                               ("clash", tl("main.clash_short"), 470, "w", True)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=st, minwidth=470 if c == "clash" else 40)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sc = ttk.Scrollbar(sb, orient="vertical", command=self.tree.yview)
        sc.grid(row=0, column=1, sticky="ns")
        hsc = ttk.Scrollbar(sb, orient="horizontal", command=self.tree.xview)
        hsc.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=sc.set, xscrollcommand=hsc.set)
        self.tree.tag_configure("tracked", background=C["green_bg"], foreground="#7ee787")
        self.tree.tag_configure("visible", background=C["amber_bg"], foreground="#e3b341")
        self.tree.tag_configure("clash", background=C["purple_bg"], foreground="#d2a8ff")
        self.tree.tag_configure("off", foreground=C["dim"])
        self.tree.bind("<Button-1>", self.on_tree_click, add="+")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda _e: self.edit_sat())
        bt = ttk.Frame(sb)
        bt.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        for text, cmd, sty in ((tl("main.muhold_hozzaadasa"), self.add_sat, "Accent.TButton"),
                               (tl("main.szerkesztes_frekvencia"), self.edit_sat, "TButton"),
                               (tl("main.kovetes_be_ki"), self.toggle_sat, "TButton"), (tl("main.torles"), self.delete_sat, "TButton"),
                               (tl("main.tle_frissitese"), self.refresh_tle, "TButton"),
                               (tl("main.tle_all"), self.refresh_all_tle, "TButton"),
                               (tl("main.reset_choices"), self.reset_choices, "TButton")):
            ttk.Button(bt, text=text, command=cmd, style=sty).pack(side="left", padx=(0, 6))

        # áthaladások
        pb = ttk.LabelFrame(left, text=tl("main.athaladasok_a_kovetkezo_24"), padding=8)
        pb.grid(row=2, column=0, sticky="nsew")
        pb.columnconfigure(0, weight=1)
        pb.rowconfigure(1, weight=1)
        self.v_passhdr = tk.StringVar(value=tl("main.valassz_ki_egy_muholdat"))
        ttk.Label(pb, textvariable=self.v_passhdr, style="Head.TLabel").grid(row=0, column=0, columnspan=2,
                                                                              sticky="w", pady=(0, 6))
        pc = ("aos", "los", "dur", "maxel", "follow", "clash", "sched")
        self.ptree = ttk.Treeview(pb, columns=pc, show="headings", selectmode="browse", height=6)
        for c, t, w in (("aos", tl("main.kezdes_aos"), 130), ("los", tl("main.vege_los"), 130), ("dur", tl("main.idotartam"), 80),
                        ("maxel", tl("main.max_elevacio"), 95), ("follow", tl("main.kovetjuk"), 130), ("clash", tl("main.clash"), 470), ("sched", tl("main.utemezes"), 100)):
            self.ptree.heading(c, text=t)
            self.ptree.column(c, width=w, anchor="center", stretch=(c == "clash"), minwidth=470 if c == "clash" else 60)
        self.ptree.grid(row=1, column=0, sticky="nsew")
        ps = ttk.Scrollbar(pb, orient="vertical", command=self.ptree.yview)
        ps.grid(row=1, column=1, sticky="ns")
        phs = ttk.Scrollbar(pb, orient="horizontal", command=self.ptree.xview)
        phs.grid(row=2, column=0, sticky="ew")
        self.ptree.configure(yscrollcommand=ps.set, xscrollcommand=phs.set)
        self.ptree.tag_configure("good", background=C["good_bg"])
        self.ptree.tag_configure("low", foreground=C["dim"])
        self.ptree.tag_configure("clash", background=C["purple_bg"], foreground="#d2a8ff")
        self.ptree.tag_configure("skipped", background=C["red_bg"], foreground="#ff9b94")
        # a felső listában is mutatott következő megfelelő áthaladás: a sor saját háttere marad, a szöveg kék
        self.ptree.tag_configure("good_next", background=C["good_bg"], foreground="#4493f8", font=(FONT, 10, "bold"))
        self.ptree.tag_configure("clash_next", background=C["purple_bg"], foreground="#4493f8", font=(FONT, 10, "bold"))
        self.ptree.tag_configure("sched", background=C["blue_bg"], foreground="#a5d6ff")
        self.ptree.bind("<<TreeviewSelect>>", self.on_pass_select)
        self.ptree.bind("<Button-1>", self.on_ptree_click, add="+")
        self.ptree.bind("<Motion>", self.on_ptree_motion, add="+")
        pbt = ttk.Frame(pb)
        pbt.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(pbt, text=tl("main.csak_ezt_az_athaladast"), style="Accent.TButton",
                   command=self.toggle_pass_sched).pack(side="left", padx=(0, 6))
        ttk.Button(pbt, text=tl("main.skip_pass"), command=self.toggle_pass_skip).pack(side="left", padx=(0, 6))
        ttk.Button(pbt, text=tl("main.utemezes_torlese"), command=self.clear_schedule).pack(side="left", padx=(0, 6))
        ttk.Button(pbt, text=tl("main.utvonal_elrejtese"), command=self.clear_pass).pack(side="left")

        # égbolt-kör + napló
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=1)
        skb = ttk.LabelFrame(right, text=tl("main.egbolt_eppen_zajlo_athaladasok"), padding=6)
        skb.grid(row=0, column=0, sticky="nsew")
        skb.columnconfigure(0, weight=1)
        skb.rowconfigure(0, weight=1)
        self.sky = tk.Canvas(skb, width=420, height=420, bg="#10161c", highlightthickness=1,
                             highlightbackground=C["border"])
        self.sky.grid(row=0, column=0, sticky="nsew")
        self.v_passinfo = tk.StringVar(value=self.PASS_HINT)
        ttk.Label(skb, textvariable=self.v_passinfo, justify="left", wraplength=480, style="Hint.TLabel").grid(
            row=1, column=0, sticky="ew", pady=(6, 0))
        lb = ttk.LabelFrame(right, text=tl("main.naplo"), padding=6)
        lb.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        lb.columnconfigure(0, weight=1)
        lb.rowconfigure(0, weight=1)
        self.log = dark_text(lb, height=8, wrap="word", state="disabled", font=("Consolas", 9), fg=C["muted"], padx=8, pady=6)
        self.log.grid(row=0, column=0, sticky="nsew")
        ls = ttk.Scrollbar(lb, orient="vertical", command=self.log.yview)
        ls.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=ls.set)

    # ---- beállítások fül -------------------------------------------------
    def _build_settings(self, parent):
        cfg = self.engine.cfg
        v = self.v = {}

        def sv(key, val):
            v[key] = tk.StringVar(value=str(val))
            return v[key]

        sf = ScrollFrame(parent)
        sf.pack(fill="both", expand=True)
        outer = ttk.Frame(sf.inner, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)

        # SDR++ / rigctl
        rb = ttk.LabelFrame(outer, text=tl("settings.sdr_kapcsolat_rigctl"), padding=14)
        rb.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        r = cfg["rig"]
        ttk.Label(rb, text=tl("settings.host_ip_cim")).grid(row=0, column=0, sticky="w")
        ttk.Entry(rb, textvariable=sv("host", r["host"]), width=22).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(rb, text=tl("settings.port")).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(rb, textvariable=sv("port", r["port"]), width=8).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(rb, text=tl("settings.frissites_ms_11000")).grid(row=2, column=0, sticky="w")
        ttk.Spinbox(rb, from_=1, to=1000, increment=10, textvariable=sv("interval", r["interval_ms"]),
                    width=8).grid(row=2, column=1, sticky="w", padx=6)
        v["rec_en"] = tk.BooleanVar(value=bool(r["recorder_enabled"]))
        ttk.Checkbutton(rb, text=tl("settings.felvetel_vezerlese_aos_los"), variable=v["rec_en"]).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Label(rb, text=tl("settings.aos_parancs_felvetel_indul")).grid(row=4, column=0, sticky="w")
        ttk.Entry(rb, textvariable=sv("aos", r["aos_cmd"]), width=14).grid(row=4, column=1, sticky="w", padx=6)
        ttk.Label(rb, text=tl("settings.los_parancs_felvetel_all")).grid(row=5, column=0, sticky="w", pady=3)
        ttk.Entry(rb, textvariable=sv("los", r["los_cmd"]), width=14).grid(row=5, column=1, sticky="w", padx=6)
        self.v_rigtest = tk.StringVar()
        ttk.Button(rb, text=tl("settings.kapcsolat_tesztelese"), command=self.test_rig).grid(row=6, column=0, sticky="w",
                                                                                pady=(8, 0))
        ttk.Label(rb, textvariable=self.v_rigtest, wraplength=330).grid(row=6, column=1, sticky="w", padx=6,
                                                                       pady=(8, 0))

        # követési szabályok
        kb = ttk.LabelFrame(outer, text=tl("settings.kovetesi_szabalyok"), padding=14)
        kb.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))
        t = cfg["tracking"]
        ttk.Label(kb, text=tl("settings.minimum_elevacio_ez_alatt")).grid(row=0, column=0, sticky="w")
        ttk.Entry(kb, textvariable=sv("minel", t["min_elev"]), width=7).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(kb, text=tl("settings.valtasi_kuszob_a_masik")
                  ).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(kb, textvariable=sv("margin", t["switch_margin"]), width=7).grid(row=1, column=1, sticky="w",
                                                                                   padx=6)
        ttk.Label(kb, text=tl("settings.legkisebb_kovetesi_ido_valtas")).grid(row=2, column=0, sticky="w")
        ttk.Entry(kb, textvariable=sv("dwell", t["min_dwell"]), width=7).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Label(kb, text=tl("settings.pass_margin")).grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(kb, textvariable=sv("pmargin", t.get("pass_margin", 3.0)), width=7).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Label(kb, justify="left", style="Hint.TLabel", wraplength=420,
                  text=tl("settings.hogyan_dont_ha_egyszerre")
                  ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # állomás helyzete
        pb = ttk.LabelFrame(outer, text=tl("settings.allomas_helyzete_pontos_koordi"), padding=14)
        pb.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        s = cfg["station"]
        ttk.Label(pb, text=tl("settings.szelesseg_e")).grid(row=0, column=0, sticky="w")
        e_lat = ttk.Entry(pb, textvariable=sv("lat", s["lat"]), width=14)
        e_lat.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(pb, text=tl("settings.hosszusag_k")).grid(row=1, column=0, sticky="w", pady=3)
        e_lon = ttk.Entry(pb, textvariable=sv("lon", s["lon"]), width=14)
        e_lon.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(pb, text=tl("settings.magassag_m_tengerszint")).grid(row=2, column=0, sticky="w")
        e_alt = ttk.Entry(pb, textvariable=sv("alt", s["alt_m"]), width=14)
        e_alt.grid(row=2, column=1, sticky="w", padx=6)
        for e_ in (e_lat, e_lon):                 # Google Térképről másolt „lat, lon” beillesztése, egységes 6 tizedes
            e_.bind("<<Paste>>", self._paste_coord)
            e_.bind("<FocusOut>", self._tidy_coords, add="+")
        e_alt.bind("<FocusOut>", self._tidy_coords, add="+")
        ttk.Button(pb, text=tl("settings.lekeres_a_windows_helyszolgalt"), command=self.loc_windows).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 2))
        gf = ttk.Frame(pb)
        gf.grid(row=4, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Button(gf, text=tl("settings.beolvasas_usb_gps_bol"), command=self.loc_gps).pack(side="left")
        ttk.Label(gf, text=tl("settings.port_2")).pack(side="left")
        ttk.Entry(gf, textvariable=sv("gps_port", s["gps_port"]), width=7).pack(side="left")
        ttk.Label(gf, text=tl("settings.baud")).pack(side="left")
        ttk.Entry(gf, textvariable=sv("gps_baud", s["gps_baud"]), width=6).pack(side="left")
        lf = ttk.Frame(pb)
        lf.grid(row=5, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(lf, text=tl("settings.lokatorbol_kozelites")).pack(side="left")
        ttk.Entry(lf, textvariable=sv("grid", ""), width=9).pack(side="left", padx=4)
        ttk.Button(lf, text=tl("settings.atszamit"), command=self.loc_grid).pack(side="left")
        ttk.Button(pb, text=tl("settings.megmutatom_a_google_terkepen"), style="Accent.TButton",
                   command=self.show_on_map).grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 2))
        self.v_locmsg = tk.StringVar()
        ttk.Label(pb, textvariable=self.v_locmsg, wraplength=420, style="Ok.TLabel").grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # idő
        tb = ttk.LabelFrame(outer, text=tl("settings.pontos_ido"), padding=14)
        tb.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))
        v["corr"] = tk.BooleanVar(value=bool(cfg["time"]["use_correction"]))
        ttk.Checkbutton(tb, text=tl("settings.belso_idokorrekcio_hasznalata_"), variable=v["corr"]).grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.v_ntp = tk.StringVar(value=tl("settings.ora_elteres_meres"))
        ttk.Label(tb, textvariable=self.v_ntp, style="Head.TLabel").grid(row=1, column=0, columnspan=2,
                                                                                    sticky="w", pady=6)
        ttk.Button(tb, text=tl("settings.elteres_merese"), command=lambda: self.bg.run(self.engine.measure_ntp,
                                                                          self._ntp_done)).grid(row=2, column=0,
                                                                                               sticky="w")
        ttk.Button(tb, text=tl("settings.windows_ora_szinkronizalasa_re"),
                   command=self.win_sync).grid(row=2, column=1, sticky="w", padx=8)

        # megjelenés
        ub = ttk.LabelFrame(outer, text=tl("settings.megjelenes"), padding=14)
        ub.grid(row=2, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        v["maximized"] = tk.BooleanVar(value=bool(cfg.get("ui", {}).get("maximized", True)))
        ttk.Checkbutton(ub, text=tl("settings.indulaskor_teljes_kepernyore_n"),
                        variable=v["maximized"]).grid(row=0, column=0, sticky="w")
        ttk.Label(ub, text=tl("settings.tipp_az_f11_billentyu"), style="Hint.TLabel", wraplength=420, justify="left").grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        langs = i18n.available()                                  # {kód: a nyelv saját neve}
        self._lang_by_name = {name: code for code, name in langs.items()}
        cur = i18n.current()
        v["language"] = tk.StringVar(value=langs.get(cur, cur))
        lf = ttk.Frame(ub)
        lf.grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(lf, text=tl("settings.language_label")).pack(side="left")
        ttk.Combobox(lf, textvariable=v["language"], values=list(self._lang_by_name), state="readonly",
                     width=16).pack(side="left", padx=8)
        ttk.Label(lf, text=tl("settings.language_hint"), style="Hint.TLabel").pack(side="left")

        # adatok és biztonsági mentés
        db = ttk.LabelFrame(outer, text=tl("settings.data_title"), padding=14)
        db.grid(row=2, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))
        self.v_datainfo = tk.StringVar()
        ttk.Label(db, textvariable=self.v_datainfo, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(db, text=tl("settings.data_hint"), style="Hint.TLabel", wraplength=420, justify="left").grid(
            row=1, column=0, sticky="w", pady=(4, 8))
        bf = ttk.Frame(db)
        bf.grid(row=2, column=0, sticky="w")
        for i, (text, cmd, sty) in enumerate(((tl("settings.btn_backup"), self.backup_now, "Accent.TButton"),
                                              (tl("settings.btn_export"), self.export_data, "TButton"),
                                              (tl("settings.btn_restore"), self.restore_data, "TButton"),
                                              (tl("settings.btn_open"), self.open_data_dir, "TButton"))):
            ttk.Button(bf, text=text, command=cmd, style=sty).grid(row=i // 2, column=i % 2, sticky="ew",
                                                                      padx=(0, 8), pady=(0, 6))
        self._refresh_datainfo()

        ttk.Button(outer, text=tl("settings.alkalmaz_es_mentes"), style="Big.TButton", command=self.apply_settings).grid(
            row=3, column=0, columnspan=2, sticky="e", pady=4)

    # ---- „Műholdak” fül: a hozzáadott műholdak nagy, áttekinthető listája ----------------
    SAT_HEADS = ("main.be", "list.h_name", "list.h_norad", "list.h_freq", "list.h_mode", "list.h_minel", "list.h_rec",
                 "list.h_next", "list.h_maxel", "list.h_state", "list.h_tle")
    SAT_WIDTHS = (46, 170, 80, 130, 80, 120, 80, 220, 90, 80, 150)

    def _build_sats(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        box = ttk.LabelFrame(parent, text=tl("list.title"), padding=10)
        box.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        self.v_satcount = tk.StringVar()
        ttk.Label(box, textvariable=self.v_satcount, style="Head.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        cols = [f"c{i}" for i in range(len(self.SAT_HEADS))]
        self.stree = ttk.Treeview(box, columns=cols, show="headings", selectmode="browse")
        for i, (k, w) in enumerate(zip(self.SAT_HEADS, self.SAT_WIDTHS)):
            self.stree.heading(f"c{i}", text=tl(k))
            self.stree.column(f"c{i}", width=w, anchor="w" if i == 1 else "center", stretch=(i == 1), minwidth=40)
        self.stree.grid(row=1, column=0, sticky="nsew")
        sc = ttk.Scrollbar(box, orient="vertical", command=self.stree.yview)
        sc.grid(row=1, column=1, sticky="ns")
        self.stree.configure(yscrollcommand=sc.set)
        self.stree.tag_configure("off", foreground=C["dim"])
        self.stree.tag_configure("tracked", background=C["green_bg"], foreground="#7ee787")
        self.stree.tag_configure("rec", background=C["red_bg"], foreground="#ff9b94")
        self.stree.bind("<Button-1>", self.on_stree_click, add="+")
        self.stree.bind("<Double-1>", self.on_stree_double)
        bt = ttk.Frame(box)
        bt.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(bt, text=tl("list.copy"), command=self.copy_satlist).pack(side="left", padx=(0, 6))
        ttk.Button(bt, text=tl("list.save"), command=self.save_satlist).pack(side="left", padx=(0, 6))
        self.v_satmsg = tk.StringVar()
        ttk.Label(box, textvariable=self.v_satmsg, style="Hint.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(box, text=tl("list.hint"), style="Hint.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._sat_rows = []
        self._srow_cache = {}

    def _sat_items(self):
        """[(SatEntry, min_el, következő_megfelelő_áthaladás)] a főlistával azonos sorrendben."""
        e = self.engine
        items = []
        for iid in self.tree.get_children():
            s = e.sats.get(int(iid))
            if s:
                c = self.next_pass.get(s.norad)
                items.append((s, e.eff_min_elev(s), c["pass"] if c and s.enabled else None))
        return items

    def _update_satstab(self, snap):
        items = self._sat_items()
        rec_global = bool(self.engine.cfg["rig"].get("recorder_enabled"))
        rec_n = snap["current"] if snap.get("recording") else None
        rows = sat_list_rows(items, rec_global, rec_n)
        self._sat_rows = rows
        have = set(self.stree.get_children())
        keep = set()
        for pos, ((s, _mn, _p), r) in enumerate(zip(items, rows)):
            iid = str(s.norad)
            keep.add(iid)
            info = snap["sats"].get(s.norad, {})
            tag = "off" if not s.enabled else ("rec" if s.norad == rec_n else ("tracked" if info.get("code") == "tracked" else ""))
            vals = ["✓" if s.enabled else "", r[0], r[1], r[2], r[3], r[4], r[5], r[7], r[8], r[6], r[9]]
            tags = (tag,) if tag else ()
            if iid not in have:
                self.stree.insert("", "end", iid=iid, values=vals, tags=tags)
            elif self._srow_cache.get(iid) != (vals, tags):
                self.stree.item(iid, values=vals, tags=tags)
            self._srow_cache[iid] = (vals, tags)
            if iid in have and self.stree.index(iid) != pos:
                self.stree.move(iid, "", pos)
        for iid in have - keep:
            self.stree.delete(iid)
            self._srow_cache.pop(iid, None)
        self.v_satcount.set(tl("list.count", n=len(items), on=sum(1 for it in items if it[0].enabled)))

    def on_stree_click(self, e):
        try:
            col = self.stree.identify_column(e.x)
            if self.stree.identify_region(e.x, e.y) != "cell" or col not in ("#1", "#7"):
                return
            iid = self.stree.identify_row(e.y)
            s = self.engine.sats.get(int(iid)) if iid else None
        except (ValueError, tk.TclError):
            return
        if s:                                   # ✓ oszlop: ki/be; AOS/LOS oszlop: küldés ki/be
            if col == "#1":
                self.engine.update_sat(s.norad, enabled=not s.enabled)
            else:
                self.engine.update_sat(s.norad, record=not s.record)
            return "break"

    def on_stree_double(self, e):
        try:
            iid = self.stree.identify_row(e.y)
            if iid and self.stree.identify_column(e.x) not in ("#1", "#7"):
                self.select_sat(int(iid))
                SatDialog(self, int(iid))
        except (ValueError, tk.TclError):
            pass

    def _satlist_text(self, sep):
        return rows_to_text([tl(k) for k in ("list.h_name", "list.h_norad", "list.h_freq", "list.h_mode", "list.h_minel",
                                             "list.h_rec", "list.h_state", "list.h_next", "list.h_maxel", "list.h_tle")], self._sat_rows, sep)

    def copy_satlist(self):
        self.clipboard_clear()
        self.clipboard_append(self._satlist_text("\t"))
        self.v_satmsg.set(tl("list.copied"))

    def save_satlist(self):
        dest = filedialog.asksaveasfilename(parent=self, title=tl("list.save"), defaultextension=".csv",
                                            initialfile=f"orbiq_satellites_{dt.date.today():%Y%m%d}.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not dest:
            return
        try:
            with open(dest, "w", encoding="utf-8-sig", newline="") as fh:       # BOM: az Excel is jól olvassa az ékezeteket
                fh.write(self._satlist_text(";"))
        except OSError as ex:
            messagebox.showerror(tl("msg.title_error"), str(ex), parent=self)
            return
        self.v_satmsg.set(tl("list.saved", path=dest))

    def _build_help(self, parent):
        txt = dark_text(parent, wrap="word", font=("Segoe UI", 10), padx=18, pady=16, spacing1=2, spacing3=2)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", (
            tl("help.sdr_beallitasa_egyszer_kell")))
        txt.configure(state="disabled")

    # ---- műveletek ---------------------------------------------------------
    def select_sat(self, norad: int):
        self.selected = norad
        iid = str(norad)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)

    def on_select(self, _e=None):
        sel = self.tree.selection()
        self.selected = int(sel[0]) if sel else None
        self._filled_n = None          # a műhold (újra) kijelölésekor a tábla a következő megfelelő áthaladáshoz görget
        if self.sel_pass is not None and self.sel_pass[0] != self.selected:
            self.clear_pass()
        if self.selected is not None and self.engine.mode == "selected":
            self.engine.set_pinned(self.selected)      # a kijelölt műholdat kezdi követni
        self.request_passes(force=True)

    def add_sat(self):
        if not self.engine.location_ok():
            messagebox.showwarning(tl("app.helyzet_hianyzik"), tl("app.elobb_add_meg_az"))
            return
        SatDialog(self)

    def edit_sat(self):
        if self.selected is None:
            messagebox.showinfo(tl("app.szerkesztes"), tl("app.elobb_jelolj_ki_egy"))
            return
        SatDialog(self, self.selected)

    def on_tree_click(self, e):
        """A „Be” oszlop ✓ jelére kattintva közvetlenül ki/be kapcsolható a műhold."""
        try:
            if self.tree.identify_region(e.x, e.y) != "cell" or self.tree.identify_column(e.x) != "#1":
                return
            iid = self.tree.identify_row(e.y)
            s = self.engine.sats.get(int(iid)) if iid else None
        except (ValueError, tk.TclError):
            return
        if s:
            self.engine.update_sat(s.norad, enabled=not s.enabled)
            return "break"

    def toggle_sat(self):
        s = self.engine.sats.get(self.selected) if self.selected is not None else None
        if s:
            self.engine.update_sat(s.norad, enabled=not s.enabled)

    def delete_sat(self):
        s = self.engine.sats.get(self.selected) if self.selected is not None else None
        if s and messagebox.askyesno(tl("app.torles"), tl("app.biztosan_torlod_name_norad", name=s.name, norad=s.norad)):
            self.engine.remove_sat(s.norad)
            self.selected = None
            self.pass_data = (None, [], 0.0)

    def refresh_tle(self):
        """A kijelölt műhold TLE-jének frissítése; az eredmény a naplóban látszik."""
        s = self.engine.sats.get(self.selected) if self.selected is not None else None
        if not s:
            messagebox.showinfo(tl("app.tle_frissitese"), tl("app.elobb_jelolj_ki_egy_2"))
            return
        e = self.engine

        def done(r, err):
            if err:
                e.log.append((e.now(), tl("log.tle_one_fail", name=s.name or s.norad, err=err)))
                messagebox.showerror(tl("app.tle_hiba"), str(err))
            else:
                e.log.append((e.now(), tl("log.tle_one_ok", name=s.name or s.norad, age=self._tle_age_days(s.norad))))
                self.request_passes(force=True)
        self.bg.run(lambda: e.refresh_tle(s.norad), done)

    def _tle_age_days(self, norad):
        m = self.engine.models.get(norad)
        return f"{(self.engine.now() - m.epoch_ts) / 86400:.1f}" if m is not None else "?"

    def refresh_all_tle(self):
        """Az összes műhold TLE-jének frissítése egy gombnyomásra; az összegzés a naplóban."""
        if self._tle_busy:
            return
        e = self.engine
        nums = list(e.sats)
        if not nums:
            return
        self._tle_busy = True
        e.log.append((e.now(), tl("log.tle_all_start", n=len(nums))))

        def work():
            ok, bad = 0, []
            for n in nums:
                try:
                    e.refresh_tle(n)
                    ok += 1
                except Exception as ex:          # noqa: BLE001
                    s = e.sats.get(n)
                    bad.append(f"{(s.name if s else '') or n}")
                time.sleep(0.5)
            return ok, bad

        def done(r, err):
            self._tle_busy = False
            if err or r is None:
                e.log.append((e.now(), tl("log.tle_one_fail", name="*", err=err)))
                return
            ok, bad = r
            e.log.append((e.now(), tl("log.tle_all_done", ok=ok, n=len(nums)) +
                          ((" – " + tl("log.tle_all_failed", names=", ".join(bad))) if bad else "")))
            self.request_passes(force=True)
        self.bg.run(work, done)

    def auto_tle(self):
        old = [s.norad for s in self.engine.sats.values() if time.time() - s.tle_fetched > 12 * 3600]

        def work():
            for n in old:
                try:
                    self.engine.refresh_tle(n)
                except Exception as e:       # noqa: BLE001
                    self.engine.log.append((self.engine.now(), tl("app.tle_frissites_sikertelen_n", n=n, e=e)))
                time.sleep(1.0)
        if old:
            self.bg.run(work, lambda r, e: self.request_passes(force=True))
        self.after(6 * 3600 * 1000, self.auto_tle)

    def _freq_target(self):
        n = self.freq_target
        return n if n is not None and n in self.engine.sats else None

    def on_digit(self, delta):
        """Az alapfrekvencia számjegyeinek állítása (a Doppler-kijelzőt nem érinti)."""
        n = self._freq_target()
        if n is not None:
            self.engine.adjust_base(n, delta)
            self.base_freq.set_state(self.base_freq.value + delta, True)

    # ---- áthaladások -------------------------------------------------------
    def request_passes(self, force=False):
        n = self.selected
        if n is None or n not in self.engine.sats or self.pass_busy:
            return
        e = self.engine
        key = (n, e.sats[n].tle_fetched, e.cfg["station"]["lat"], e.cfg["station"]["lon"], int(e.now() // 600))
        if not force and key == self.pass_key:
            return
        self.pass_key = key
        hit = e.cached_passes(n, 24.0)
        if hit is not None:                  # a közös gyorsítótárból azonnal
            self.pass_data = (n, hit, e.now())
            self.fill_passes()
            return
        self.pass_busy = True

        def done(res, err):
            self.pass_busy = False
            if err:
                self.v_passhdr.set(tl("app.nem_szamolhato_athaladas_err", err=err))
                return
            self.pass_data = (n, res, e.now())
            self.fill_passes()
            if self.selected != n:
                self.request_passes(force=True)

        self.bg.run(lambda: e.compute_passes(n, 24.0), done)

    def fill_passes(self):
        n, passes, _t = self.pass_data
        prev_n, self._filled_n = self._filled_n, n
        nx0 = self.next_pass.get(n)
        self._nxt_sig = nx0["pass"].los if nx0 and nx0["pass"] is not None else None
        try:
            y0 = self.ptree.yview()[0]            # a görgetés helyének megtartásához (újratöltés előtt)
        except (tk.TclError, AttributeError, IndexError):
            y0 = None
        self.ptree.delete(*self.ptree.get_children())
        s = self.engine.sats.get(n)
        if not s:
            return
        mn = self.engine.eff_min_elev(s)
        mn_ok = self.engine.peak_threshold(s)
        today = dt.date.today()
        now_ = self.engine.now()
        others, name2n = {}, {}      # a többi bekapcsolt műhold megfelelő áthaladásai
        self._clash_rows = {}        # sor -> [(norad, név, max_el, aos, los)] a kattintható ütközés-mezőhöz
        for m, (nm, sp) in self._others_spans().items():
            if m != n:
                others[nm] = sp
                name2n[nm] = m
        nx = self.next_pass.get(n)
        nxt_los = nx["pass"].los if nx and nx["pass"] is not None else None     # a felső listában mutatott „következő megfelelő”
        next_idx = None
        for i, p in enumerate(passes):
            is_next = nxt_los is not None and abs(p.los - nxt_los) < 20
            if is_next:
                next_idx = i
            d = dt.datetime.fromtimestamp(p.aos).date() != today
            skipped = self.engine.is_skipped(n, p.los)
            ok = p.max_el >= mn_ok and not skipped
            sch = self.engine.is_scheduled(n, p.los)
            names = clashing(p.aos, p.los, others) if ok else []
            if names:
                self._clash_rows[str(i)] = [(name2n[it[0]],) + tuple(it) for it in names]
            self.ptree.insert("", "end", iid=str(i), tags=(("sched" if sch else ("skipped" if skipped else ("clash" if names else ("good" if ok else "low")))) + ("_next" if is_next and not sch and not skipped else ""),), values=(
                ("▶ " if is_next else "") + (tl("app.mar_fent") if p.started else fmt_time(p.aos, d)), fmt_time(p.los, d), fmt_dur(p.los - p.aos),
                f"{p.max_el:.1f}°", tl("app.igen") if ok else (tl("app.skipped") if skipped else tl("app.low_pass", min=f"{mn_ok:g}")),
                fmt_clash(names, p.max_el), tl("app.kovetve_lesz") if sch else ""))
        if self.sel_pass is not None and self.sel_pass[0] == n:       # a kijelölt áthaladás maradjon kijelölve
            for i, p in enumerate(passes):
                if abs(p.los - self.sel_pass[1].los) < 20:
                    self.ptree.selection_set(str(i))
                    break
            else:
                self.clear_pass()
        try:
            if n != prev_n:                  # másik műhold: a következő megfelelő áthaladáshoz görgetünk, hogy ne maradjon rejtve
                if next_idx is not None:
                    self.ptree.see(str(next_idx))
                else:
                    self.ptree.yview_moveto(0)
            elif y0 is not None:             # ugyanaz a műhold: marad ott, ahol a felhasználó görgetett
                self.ptree.yview_moveto(y0)
        except (tk.TclError, AttributeError):
            pass
        if self._jump is not None and self._jump[0] == n:             # ugrás egy ütköző áthaladásra
            for i, p in enumerate(passes):
                if abs(p.los - self._jump[1]) < 120:
                    self.ptree.selection_set(str(i))
                    self.ptree.see(str(i))
                    self.on_pass_select()          # azonnal (nem az esemény-sorra várva): így a későbbi újratöltés is megtartja
                    break
            self._jump = None

    def _clash_hit(self, e):
        """Az ütközés-szöveg sorának azonosítója, ha a kattintás TÉNYLEG a felirat fölött van (nem csak a cellában)."""
        try:
            if self.ptree.identify_region(e.x, e.y) != "cell" or self.ptree.identify_column(e.x) != "#6":
                return None
            iid = self.ptree.identify_row(e.y)
            if iid not in self._clash_rows:
                return None
            bb = self.ptree.bbox(iid, "clash")
            if not bb:
                return None
            txt = self.ptree.set(iid, "clash")
            try:
                import tkinter.font as tkfont
                fnt = tkfont.nametofont(ttk.Style().lookup("Treeview", "font") or "TkDefaultFont")
                tw = fnt.measure(txt)
            except Exception:                       # noqa: BLE001
                tw = 7 * len(txt)
            cx = bb[0] + bb[2] / 2                   # a szöveg a cella közepén áll
            return iid if abs(e.x - cx) <= tw / 2 + 8 else None
        except tk.TclError:
            return None

    def _check_ptable(self):
        """Az áthaladás-tábla frissen tartása: a lejárt áthaladás sora eltűnik, a ▶ jelölés átlép a következőre."""
        n, passes, t = self.pass_data
        if n is None or n != self.selected:
            return
        now = self.engine.now()
        if any(p.los < now - 1 for p in passes):
            self.pass_data = (n, [p for p in passes if p.los >= now - 1], t)     # új lista (a közös gyorsítótárat nem módosítjuk)
            self.fill_passes()
            return
        nx = self.next_pass.get(n)
        if (nx["pass"].los if nx and nx["pass"] is not None else None) != self._nxt_sig:
            self.fill_passes()

    def on_ptree_motion(self, e):
        try:
            self.ptree.configure(cursor="hand2" if self._clash_hit(e) else "")
        except tk.TclError:
            pass

    def on_ptree_click(self, e):
        """Az „Egyszerre vele” mezőre kattintva odaugrik az ütköző műholdra és annak áthaladására."""
        iid = self._clash_hit(e)
        items = self._clash_rows.get(iid) if iid else None
        if not items:
            return
        if len(items) == 1:
            self.jump_to_pass(items[0][0], items[0][4])
            return "break"
        menu = tk.Menu(self, tearoff=0, bg=C["raised"], fg=C["text"], activebackground=C["accent"], activeforeground="white",
                       bd=0, relief="flat")
        for n, name, m, a, b in items:
            menu.add_command(label=f"{name}   {m:.1f}°   {fmt_time(a)}–{fmt_time(b)}",
                             command=lambda n=n, b=b: self.jump_to_pass(n, b))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()
        return "break"

    def jump_to_pass(self, norad, los):
        """Kijelöli a műholdat a listában, és a táblázatban az adott (LOS-idejű) áthaladását."""
        if norad not in self.engine.sats:
            return
        self._jump = (norad, los)
        self.clear_pass()
        self.select_sat(norad)
        if self.tree.exists(str(norad)):
            self.tree.see(str(norad))
        self.request_passes(force=True)

    def toggle_pass_sched(self):
        if self.sel_pass is None:
            messagebox.showinfo(tl("app.athaladas_kovetese"), tl("app.elobb_kattints_egy_athaladasra"))
            return
        n, p = self.sel_pass
        s = self.engine.sats.get(n)
        if not s:
            return
        e = self.engine
        if e.is_scheduled(n, p.los):
            e.remove_pass(n, p.los)
        else:
            e.add_pass(n, s.name, min(p.aos, e.now()) if p.started else p.aos, p.los, p.tmax, p.max_el)
            if e.mode != "passes":
                e.set_mode("passes")
                self.v_mode.set("passes")
        self.fill_passes()

    def toggle_pass_skip(self):
        if self.sel_pass is None:
            messagebox.showinfo(tl("app.athaladas_kovetese"), tl("app.elobb_kattints_egy_athaladasra"))
            return
        n, p = self.sel_pass
        self.engine.toggle_skip(n, p.los)
        self.next_pass.pop(n, None)            # a „következő áthaladás” újraszámolása
        self.fill_passes()

    def reset_choices(self):
        if not messagebox.askyesno(tl("app.reset_title"), tl("app.reset_ask")):
            return
        self.engine.reset_choices()
        self.next_pass.clear()
        self.all_passes.clear()
        self.fill_passes()

    def clear_schedule(self):
        self.engine.clear_schedule()
        self.fill_passes()

    @property
    def PASS_HINT(self) -> str:
        return tl("app.kattints_egy_athaladasra_a")

    def clear_pass(self):
        self.sel_pass = None
        self.sel_track = []
        self.sel_info = None
        self.v_passinfo.set(self.PASS_HINT)
        sel = self.ptree.selection()
        if sel:
            self.ptree.selection_remove(*sel)

    def on_pass_select(self, _e=None):
        sel = self.ptree.selection()
        n, passes, _t = self.pass_data
        if not sel or n is None or n != self.selected:
            return
        try:
            p = passes[int(sel[0])]
        except (ValueError, IndexError):
            return
        e = self.engine
        s, m = e.sats.get(n), e.models.get(n)
        if not s or m is None:
            return
        self.sel_pass = (n, p)
        self.sel_track = core.pass_track(m, e.observer, p.aos, p.los)
        mn = e.eff_min_elev(s)
        a0, a1 = self.sel_track[0][1], self.sel_track[-1][1]
        am = core.observe(m, e.observer, p.tmax).az
        clash = []                               # ugyanaz az adat, mint a táblában: (norad, név, max_el, aos, los)
        for m2, nm2, mx2, a2, l2 in self._clash_rows.get(sel[0], []):
            m2_model = e.models.get(m2)
            if m2_model is None:
                continue
            tr2 = [x for x in core.pass_track(m2_model, e.observer, max(a2, p.aos), min(l2, p.los)) if x[2] > 0]
            if len(tr2) >= 2:
                clash.append({"name": nm2, "track": tr2, "max_el": mx2})
        self.sel_info = {"name": s.name, "p": p, "mn": mn, "track": self.sel_track, "max_az": am, "clash": clash}
        good = [t for t, _az, el in self.sel_track if el >= mn]
        if good:
            foll = tl("app.kovetheto_mn_g_folott", mn=mn, fmt_time=fmt_time(good[0]), fmt_time2=fmt_time(good[-1]), fmt_dur=fmt_dur(good[-1] - good[0]))
        else:
            foll = tl("app.nem_eri_el_a", mn=mn)
        start = tl("app.mar_fent_van") if p.started else tl("app.kezdes_fmt_time", fmt_time=fmt_time(p.aos, True))
        self.v_passinfo.set(
            tl("app.name_kijelolt_athaladas_start", name=s.name, start=start, az_name=az_name(a0), a0=a0, max_el=p.max_el, fmt_time=fmt_time(p.tmax), az_name2=az_name(am), am=am, fmt_time2=fmt_time(p.los, True), az_name3=az_name(a1), a1=a1, fmt_dur=fmt_dur(p.los - p.aos), foll=foll))

    def _update_passhdr(self):
        n, passes, _t = self.pass_data
        s = self.engine.sats.get(n) if n is not None else None
        if not s or n != self.selected:
            if self.selected is None:
                self.v_passhdr.set(tl("app.valassz_ki_egy_muholdat"))
            return
        now = self.engine.now()
        model = self.engine.models.get(n)
        age = ""
        if model is not None:
            days = (now - model.epoch_ts) / 86400
            age = tl("app.tle_age_old" if days > 7 else "app.tle_age", days=f"{days:.1f}")
        thr = self.engine.peak_threshold(s)
        nxt = next((p for p in passes if p.los > now and p.max_el >= thr and not self.engine.is_skipped(n, p.los)), None)
        if nxt is None:
            txt = tl("app.name_nincs_athaladas_a", name=s.name) if not any(p.los > now for p in passes) else tl("app.no_suitable_pass", name=s.name)
        elif nxt.aos <= now:
            txt = tl("app.name_most_lathato_los", name=s.name, fmt_dur=fmt_dur(nxt.los - now), max_el=nxt.max_el)
        else:
            txt = tl("app.name_kovetkezo_athaladas_fmt", name=s.name, fmt_dur=fmt_dur(nxt.aos - now), fmt_time=fmt_time(nxt.aos), max_el=nxt.max_el)
        self.v_passhdr.set(txt + age)

    # ---- beállítások műveletei ---------------------------------------------
    def _paste_coord(self, _e=None):
        """Ha a vágólapon „szélesség, hosszúság” pár van (pl. Google Térképről), mindkét mezőt kitölti."""
        try:
            pair = split_coord_pair(self.clipboard_get())
            if pair:
                la, lo = parse_coord(pair[0]), parse_coord(pair[1])
                if -90 <= la <= 90 and -180 <= lo <= 180:
                    self.v["lat"].set(f"{la:.6f}")
                    self.v["lon"].set(f"{lo:.6f}")
                    self.v_locmsg.set(tl("app.coord_pasted"))
                    return "break"
        except (tk.TclError, ValueError):
            pass
        return None

    def _tidy_coords(self, _e=None):
        """Mezőelhagyáskor egységes alak: 6 tizedes a koordinátáknál, 1 tizedes a magasságnál (értelmezhetetlent nem bántja)."""
        for key, fmt in (("lat", "{:.6f}"), ("lon", "{:.6f}")):
            try:
                self.v[key].set(fmt.format(parse_coord(self.v[key].get())))
            except ValueError:
                pass
        try:
            self.v["alt"].set(f"{float(self.v['alt'].get().replace(',', '.')):.1f}")
        except ValueError:
            pass

    def apply_settings(self):
        v = self.v
        try:
            lat = parse_coord(v["lat"].get())
            lon = parse_coord(v["lon"].get())
            alt = float(v["alt"].get().replace(",", ".") or 0)
            port = int(v["port"].get())
            iv = int(float(v["interval"].get()))
            minel = float(v["minel"].get().replace(",", "."))
            margin = float(v["margin"].get().replace(",", "."))
            dwell = float(v["dwell"].get().replace(",", "."))
            pmargin = float(v["pmargin"].get().replace(",", "."))
            baud = int(v["gps_baud"].get())
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(tl("app.a_szelesseg_90_90"))
            if not (1 <= iv <= 1000):
                raise ValueError(tl("app.a_frissitesi_ido_1"))
            if not (0 <= minel < 90) or margin < 0 or dwell < 0 or not (0 <= pmargin < 45):
                raise ValueError(tl("app.hibas_elevacio_kuszob_ido"))
            if not v["host"].get().strip():
                raise ValueError(tl("app.a_host_nem_lehet"))
        except ValueError as e:
            messagebox.showerror(tl("app.hibas_beallitas"), str(e) or tl("app.szamot_kell_megadni"))
            return
        self.engine.apply_settings(
            rig=dict(host=v["host"].get().strip(), port=port, interval_ms=iv, recorder_enabled=v["rec_en"].get(),
                     aos_cmd=v["aos"].get().strip(), los_cmd=v["los"].get().strip()),
            tracking=dict(min_elev=minel, switch_margin=margin, min_dwell=dwell, pass_margin=pmargin),
            station=dict(lat=lat, lon=lon, alt_m=alt, gps_port=v["gps_port"].get().strip(), gps_baud=baud),
            time_=dict(use_correction=v["corr"].get()),
            ui=dict(maximized=bool(v["maximized"].get()),
                    language=self._lang_by_name.get(v["language"].get(), i18n.current())))
        self.request_passes(force=True)
        self.v_locmsg.set(tl("app.mentve"))

    def test_rig(self):
        try:
            host, port = self.v["host"].get().strip(), int(self.v["port"].get())
        except ValueError:
            self.v_rigtest.set(tl("app.hibas_port"))
            return
        self.v_rigtest.set(tl("app.kapcsolodas"))

        def work():
            rig = self.engine.rig
            if rig.connected and (host, port) == (rig.host, rig.port):
                # a program saját kapcsolata él - azon kérdezünk (az SDR++ egyszerre egy klienst szolgál ki)
                return rig.get_freq(), rig.last_error, True
            c = core.RigctlClient()
            c.configure(host, port)
            f = c.get_freq(force=True)
            err = c.last_error
            c.close()
            return f, err, False

        def done(res, err):
            if err:
                self.v_rigtest.set(str(err))
            elif res[0] is None and res[2]:
                self.v_rigtest.set(tl("app.a_kapcsolat_el_de"))
            elif res[0] is None:
                self.v_rigtest.set(tl("app.rig_test_fail", detail=res[1] or tl("app.nincs_ervenyes_valasz")))
            else:
                self.v_rigtest.set(tl("app.kapcsolodva_az_sdr_frekvenciaj", p=res[0] / 1e6))
        self.bg.run(work, done)

    def _set_loc(self, d, src):
        self.v["lat"].set(f"{d['lat']:.6f}")
        self.v["lon"].set(f"{d['lon']:.6f}")
        if d.get("alt_m") is not None:
            self.v["alt"].set(f"{d['alt_m']:.0f}")
        extra = tl("app.pontossag_acc_m_0f", acc_m=d['acc_m']) if d.get("acc_m") else ""
        self.v_locmsg.set(tl("app.src_lat_6f_lon", src=src, lat=d['lat'], lon=d['lon'], extra=extra))

    def loc_windows(self):
        self.v_locmsg.set(tl("app.helyzet_lekerese_a_windowstol"))
        self.bg.run(core.windows_location, lambda r, e: self.v_locmsg.set(str(e)) if e
                    else self._set_loc(r, "Windows"))

    def loc_gps(self):
        try:
            port, baud = self.v["gps_port"].get().strip(), int(self.v["gps_baud"].get())
        except ValueError:
            self.v_locmsg.set(tl("app.hibas_baud_ertek"))
            return
        self.v_locmsg.set(tl("app.gps_beolvasasa_max_25"))
        self.bg.run(lambda: core.nmea_location(port, baud), lambda r, e: self.v_locmsg.set(str(e)) if e
                    else self._set_loc(r, "GPS"))

    def show_on_map(self):
        """A mezőkbe írt (még nem mentett) koordináta megnyitása a Google Térképen."""
        try:
            lat = parse_coord(self.v["lat"].get())
            lon = parse_coord(self.v["lon"].get())
            url = map_url(lat, lon)
        except ValueError:
            messagebox.showerror(tl("app.hibas_koordinata"), tl("app.a_szelesseg_90_90_2"), parent=self)
            return
        webbrowser.open(url)
        self.v_locmsg.set(tl("app.megnyitva_a_bongeszoben_lat", lat=lat, lon=lon))

    def loc_grid(self):
        try:
            la, lo = core.grid_to_latlon(self.v["grid"].get())
        except Exception as e:               # noqa: BLE001
            self.v_locmsg.set(str(e))
            return
        self._set_loc({"lat": la, "lon": lo}, tl("app.lokator_csak_kozelites_a"))

    def _ntp_done(self, res, err):
        self.v_ntp.set(tl("app.ora_elteres_res_pozitiv", res=res) if not err else tl("app.ntp_error", err=err))

    def win_sync(self):
        if sys.platform != "win32":
            messagebox.showinfo(tl("app.idoszinkron"), tl("app.ez_a_gomb_csak"))
            return
        if messagebox.askyesno(tl("app.windows_ora_szinkronizalasa"),
                               tl("app.a_windows_engedelyt_uac")):
            core.windows_time_sync()
            self.v_ntp.set(tl("app.szinkron_elinditva_1020_mp"))

    # ---- frissítő ciklus -----------------------------------------------------
    def refresh(self):
        t0 = time.perf_counter()
        parts = {}
        try:
            snap = self.engine.snap
            if snap:
                for name, fn, args in (
                        ("topbar", self._update_topbar, (snap,)), ("allpasses", self.request_all_passes, ()),
                        ("next", self._refresh_next, ()), ("tree", self._update_tree, (snap,)),
                        ("sats", self._update_satstab, (snap,)), ("freq", self._update_freq, (snap,)),
                        ("passhdr", self._update_passhdr, ()), ("ptable", self._check_ptable, ()),
                        ("passes", self.request_passes, ()), ("sky", self._draw_sky, (snap,)),
                        ("log", self._update_log, ())):
                    t1 = time.perf_counter()
                    fn(*args)
                    parts[name] = time.perf_counter() - t1
        except Exception as e:               # noqa: BLE001
            self.engine.log.append((time.time(), tl("app.feluleti_hiba_e_r", e=e)))
        total = time.perf_counter() - t0
        now = time.time()
        # Mozgóátlag: az indításkori egyszeri lassúság (betűtípus-, képtár-betöltés) nem számít, csak a tartós lassúság.
        ema = getattr(self, "_ema", None)
        if ema is None:
            ema = self._ema = {"total": 0.0}
        for k, v in (("total", total), *parts.items()):
            ema[k] = ema.get(k, 0.0) * 0.9 + v * 0.1
        if ema["total"] > 0.08 and now - getattr(self, "_slow_log_t", 0) > 120:      # tartósan lassú felületfrissítés -> napló
            self._slow_log_t = now
            top = sorted(((k, v) for k, v in ema.items() if k != "total"), key=lambda kv: -kv[1])[:3]
            self.engine.log.append((now, tl("app.slow_ui", ms=int(ema["total"] * 1000),
                                            top=", ".join(f"{k} {int(v * 1000)} ms" for k, v in top))))
        self.after(250, self.refresh)

    def _fast_tick(self):
        """Gyors (kb. 30 Hz) frissítés csak a nagy frekvenciakijelzőnek, hogy ugyanolyan gyorsan járjon, mint az SDR++."""
        try:
            snap = self.engine.snap
            if snap and snap is not self._fast_snap:
                self._fast_snap = snap
                live = snap.get("live")
                cur = snap.get("current")
                if cur is not None and live and cur in self.engine.sats:
                    self.freq.set_state(live["freq"], True)
        except Exception:               # noqa: BLE001
            pass
        self.after(33, self._fast_tick)

    def _cfg(self, w, **kw):
        """widget.configure, de csak ha tényleg változott valami (a felesleges beállítás újrarajzolást okoz)."""
        if self._cfg_cache.get(w) != kw:
            self._cfg_cache[w] = dict(kw)
            w.configure(**kw)

    def _update_topbar(self, snap):
        on = snap["tracking_on"]
        self._cfg(self.btn_track, text=tl("app.kovetes_bekapcsolva") if on else tl("app.kovetes_kikapcsolva"),
                                 bg="#238636" if on else C["raised"], fg="white" if on else C["muted"],
                                 activebackground="#2ea043" if on else C["hover"], activeforeground="white")
        r = self.engine.cfg["rig"]
        if snap["rig_connected"]:
            self._cfg(self.lbl_rig, text=tl("app.sdr_kapcsolodva_host_port", host=r['host'], port=r['port']), fg=C["green"])
        else:
            self._cfg(self.lbl_rig, text=tl("app.rig_disconnected", host=r['host'], port=r['port']), fg=C["red"])
        self._cfg(self.lbl_rec, text=tl("app.felvetel") if snap["recording"] else "")
        self._cfg(self.lbl_warn, text="" if snap["location_ok"] else tl("app.allitsd_be_a_helyzetedet"))
        nxt_txt = ""
        if self.engine.mode == "passes":
            nx = self.engine.next_scheduled(snap["t"])
            if nx is None:
                nxt_txt = tl("app.nincs_utemezett_athaladas")
            elif nx["aos"] <= snap["t"]:
                nxt_txt = tl("app.utemezett_athaladas_zajlik_nam", name=nx['name'])
            else:
                nxt_txt = tl("app.kovetkezo_utemezett_name_fmt", name=nx['name'], fmt_time=fmt_time(nx['aos']), fmt_dur=fmt_dur(nx['aos'] - snap['t']))
        self._cfg(self.lbl_next, text=nxt_txt)
        now = snap["t"]
        u = dt.datetime.fromtimestamp(now, dt.timezone.utc)
        lt = dt.datetime.fromtimestamp(now)
        self._cfg(self.lbl_local, text=f"{lt:%H:%M:%S}")
        self._cfg(self.lbl_utc, text=f"{u:%H:%M:%S}")
        self._cfg(self.cap_local, text=tl("app.clock_local", date=f"{lt:%Y.%m.%d.}"))
        self._cfg(self.cap_utc, text=tl("app.clock_utc", date=f"{u:%Y.%m.%d.}") if u.date() != lt.date() else "UTC")

    def _next_key(self, s):
        st = self.engine.cfg["station"]
        return (s.tle_fetched, st["lat"], st["lon"], st["alt_m"])

    def request_all_passes(self):
        """Az összes bekapcsolt műhold 24 órás áthaladásai háttérszálon (a motor közös gyorsítótárába számol).
        Ebből adódik a „következő áthaladás” oszlop, az ütközések jelzése és a kijelölt műhold táblázata is."""
        if self.allp_busy:
            return
        e = self.engine
        now = e.now()
        stale = [n for n, s in list(e.sats.items())
                 if s.enabled and n in e.models and (n not in self.all_passes
                 or self.all_passes[n]["key"] != self._next_key(s) or now - self.all_passes[n]["ts"] > 590)]
        for n in [n for n in self.all_passes if n not in e.sats]:
            del self.all_passes[n]
        if not stale:
            return
        self.allp_busy = True
        keys = {n: self._next_key(e.sats[n]) for n in stale}

        def work():
            out = {}
            for n in stale:                      # műholdanként, hogy a felület közben is kapjon időt
                out[n] = e.compute_passes(n, 24.0)
                time.sleep(0.01)
            return out

        def done(res, err):
            self.allp_busy = False
            t_now = e.now()
            for n in stale:
                self.all_passes[n] = {"key": keys[n], "ts": t_now, "passes": (res or {}).get(n, [])}
            if self.pass_data[0] is not None:
                self.fill_passes()

        self.bg.run(work, done)

    def _refresh_next(self):
        """A következő megfelelő áthaladás műholdanként - a már kiszámolt listákból, gyorsan (nincs újraszámolás)."""
        e = self.engine
        now = e.now()
        out = {}
        for n, c in self.all_passes.items():
            s = e.sats.get(n)
            if s is None or not s.enabled:
                continue
            thr = e.peak_threshold(s)
            out[n] = {"pass": next((p for p in c["passes"] if p.los > now and p.max_el >= thr
                                    and not e.is_skipped(n, p.los)), None)}
        self.next_pass = out

    def _next_texts(self, n, now):
        c = self.next_pass.get(n)
        p = c["pass"] if c else None
        if p is None:
            return "—", "—"
        if p.aos <= now:
            return tl("app.next_ongoing", los=fmt_time(p.los)), f"{p.max_el:.1f}°"
        other_day = dt.datetime.fromtimestamp(p.aos).date() != dt.date.today()
        return tl("app.next_future", time=fmt_time(p.aos, other_day), eta=fmt_dur(p.aos - now)), f"{p.max_el:.1f}°"

    def _others_spans(self):
        """{norad: (név, [(aos, los, max_el), ...])} a bekapcsolt műholdak megfelelő (elég magas, nem kihagyott) áthaladásairól."""
        e = self.engine
        now = e.now()
        out = {}
        for m, c in self.all_passes.items():
            sm = e.sats.get(m)
            if sm is None or not sm.enabled:
                continue
            thr = e.peak_threshold(sm)
            spans = [(q.aos, q.los, q.max_el) for q in c["passes"]
                     if q.los > now and q.max_el >= thr and not e.is_skipped(m, q.los)]
            if spans:
                out[m] = (sm.name or str(m), spans)
        return out

    def _update_tree(self, snap):
        sats = snap["sats"]
        now = snap["t"]
        have = set(self.tree.get_children())
        allspans = self._others_spans()
        for n, info in sats.items():
            s = self.engine.sats.get(n)
            if not s:
                continue
            tag = "off" if not info["enabled"] else ("tracked" if info.get("code") == "tracked" else
                                                     ("visible" if info.get("code") == "visible" else ""))
            status = info["status"]
            clash_txt = ""
            own = self.next_pass.get(n)
            why = {"visible_low": "app.up_low", "visible_weak": "app.up_weak", "visible_skipped": "app.up_skipped"}.get(info.get("code"))
            if why and info["enabled"]:          # fent van, de nem követjük: mondjuk meg miért, és mikor jön a következő megfelelő
                nxt = ""
                if own and own["pass"] is not None and own["pass"].aos > now:
                    nxt = tl("app.up_next", time=fmt_time(own["pass"].aos))
                status = tl(why) + nxt
            if info["enabled"] and own and own["pass"] is not None:
                # a saját következő áthaladásunkat az összes többi műhold ÖSSZES megfelelő áthaladásához mérjük
                # (ugyanaz a szabály, mint az alsó táblázatban)
                items = clashing(own["pass"].aos, own["pass"].los, {nm: sp for m, (nm, sp) in allspans.items() if m != n})
                if items:
                    clash_txt = fmt_clash(items, own["pass"].max_el)
                    if tag == "":
                        tag = "clash"
            vals = ("✓" if info["enabled"] else "", info["name"], n, fmt_mhz(s.freq_hz),
                    tl("app.glob") if s.min_elev is None else f"{s.min_elev:g}°",
                    "—" if info["el"] is None else f"{info['el']:.1f}°",
                    *(self._next_texts(n, now) if info["enabled"] else ("—", "—")), status, clash_txt)
            iid = str(n)
            tags = (tag,) if tag else ()
            if iid in have:
                if self._row_cache.get(iid) != (vals, tags):          # a változatlan sort nem írjuk újra (nincs felesleges újrarajzolás)
                    self.tree.item(iid, values=vals, tags=tags)
            else:
                self.tree.insert("", "end", iid=iid, values=vals, tags=tags)
            self._row_cache[iid] = (vals, tags)
        for iid in have - {str(n) for n in sats}:
            self.tree.delete(iid)
            self._row_cache.pop(iid, None)
        for n in [n for n in self.next_pass if n not in self.engine.sats]:
            del self.next_pass[n]
        rows = []
        for n, info in sats.items():
            c = self.next_pass.get(n)
            rows.append((n, info["enabled"], c["pass"].aos if c and c["pass"] is not None else None, info["name"]))
        order = [str(n) for n in sat_order(rows) if self.tree.exists(str(n))]
        if list(self.tree.get_children()) != order:       # csak ha változott a sorrend (nincs villogás)
            for i, iid in enumerate(order):
                self.tree.move(iid, "", i)
        p = self.engine.pinned
        if not self._restored and p is not None and self.tree.exists(str(p)):
            self._restored = True
            self.select_sat(p)

    def _update_freq(self, snap):
        live, cur = snap["live"], snap["current"]
        e = self.engine
        if cur is not None and live and cur in e.sats:
            s = e.sats[cur]
            self.freq_target = cur
            self.freq.set_state(live["freq"], True)
            self.v_sat.set(f"{s.name} ({cur})  –  {s.freq_desc or tl('app.manual_freq')} {s.mode}".strip())
            self.base_freq.set_state(s.freq_hz, True)
            self.v_dop.set(tl("app.doppler_eltolodas_fmt_signed", fmt_signed_hz=fmt_signed_hz(live['shift'])))
            self.v_pos.set(tl("app.azimut_az_1f_elevacio", az=live['az'], el=live['el'], rng=live['rng'], rr=live['rr']))
            return
        n = self.selected
        s = e.sats.get(n) if n is not None else None
        if s and s.freq_hz:
            info = snap["sats"].get(n, {})
            shift = core.doppler_shift_hz(s.freq_hz, info["rr"]) if info.get("rr") is not None else 0.0
            self.freq_target = n
            self.freq.set_state(s.freq_hz + shift + s.offset_hz, True, preview=True)
            self.v_sat.set(tl("app.nincs_kovetve_elonezet_name", name=s.name, n=n))
            self.base_freq.set_state(s.freq_hz, True)
            self.v_dop.set(tl("app.doppler_now", shift=fmt_signed_hz(shift)))
            self.v_pos.set("" if info.get("el") is None else
                           tl("app.azimut_az_1f_elevacio_2", az=info['az'], el=info['el'], rng=info['rng']))
        else:
            self.freq_target = None
            self.freq.set_state(0, False)
            self.base_freq.set_state(0, False)
            self.v_sat.set(tl("app.nincs_kovetett_muhold"))
            self.v_dop.set("")
            self.v_pos.set("")

    def _draw_sky(self, snap):
        c = self.sky
        w, h = max(c.winfo_width(), 200), max(c.winfo_height(), 200)
        g_min = float(self.engine.cfg["tracking"]["min_elev"])
        ref = self.engine.sats.get(self.selected) if self.selected is not None else None
        if ref is None and snap["current"] is not None:
            ref = self.engine.sats.get(snap["current"])
        if ref is not None:                          # a szaggatott kör a kiválasztott (vagy követett) műhold minimuma
            g_min = float(self.engine.eff_min_elev(ref))
        sig = (snap["sats"], self.sel_info, w, h, g_min, snap["current"])
        old = self._sky_sig
        if old is not None and old[0] is sig[0] and old[1] is sig[1] and old[2:] == sig[2:]:
            return                                   # nem változott semmi - nem rajzoljuk újra
        now = time.perf_counter()
        # Ha csak a műholdak mozdultak el (másodpercenként újraszámolt pozíciók), elég másodpercenként rajzolni:
        # a rajzolás drága (3x felbontás + átméretezés), és a felület szálán fut.
        if (old is not None and old[1] is sig[1] and old[2:] == sig[2:]
                and now - getattr(self, "_sky_t", 0.0) < 1.0):
            return
        self._sky_t = now
        self._sky_sig = sig
        c.delete("all")
        P = skyplot.make_painter(c, w, h, "#10161c")
        skyplot.draw_sky(P, w, h, snap, g_min, self.sel_info)
        P.flush()
        self._sky_painter = P                        # a kép referenciáját meg kell tartani

    def _update_log(self):
        items = list(self.engine.log)
        marker = (len(items), items[-1] if items else None)
        if marker == self._log_marker:
            return
        self._log_marker = marker
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        for ts, msg in items[-80:]:
            self.log.insert("end", f"{fmt_time(ts)}  {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---- adatok: mentés / visszaállítás ----------------------------------------
    def _refresh_datainfo(self):
        bk = storage.list_backups(core.config_path())
        last = (dt.datetime.fromtimestamp(bk[0][1]).strftime("%Y.%m.%d %H:%M") if bk else tl("settings.data_none"))
        self.v_datainfo.set(tl("settings.data_info", path=storage.data_dir(), n=len(bk), last=last))

    def _flush(self):
        """A memóriában lévő állapot kiírása a fájlba (mentés/export előtt)."""
        with self.engine.lock:
            self.engine.save()

    def backup_now(self):
        try:
            self._flush()
            dest = storage.make_backup(core.config_path(), "manual")
        except OSError as e:
            messagebox.showerror(tl("msg.title_error"), str(e), parent=self)
            return
        self._refresh_datainfo()
        messagebox.showinfo(tl("msg.title_backup"), tl("msg.backup_done", path=dest), parent=self)

    def export_data(self):
        dest = filedialog.asksaveasfilename(parent=self, title=tl("settings.btn_export"), defaultextension=".json",
                                            initialfile=f"orbiq_backup_{dt.date.today():%Y%m%d}.json",
                                            filetypes=[("Orbiq JSON", "*.json")])
        if not dest:
            return
        try:
            self._flush()
            storage.export_to(dest, core.config_path())
        except OSError as e:
            messagebox.showerror(tl("msg.title_error"), str(e), parent=self)
            return
        messagebox.showinfo(tl("msg.title_backup"), tl("msg.export_done", path=dest), parent=self)

    def restore_data(self):
        bdir = storage.backups_dir()
        src = filedialog.askopenfilename(parent=self, title=tl("settings.btn_restore"),
                                         initialdir=bdir if os.path.isdir(bdir) else storage.data_dir(),
                                         filetypes=[("Orbiq JSON", "*.json"), ("*", "*.*")])
        if not src:
            return
        try:
            storage.check_file(src)
        except ValueError as e:
            messagebox.showerror(tl("msg.title_error"), str(e), parent=self)
            return
        if not messagebox.askyesno(tl("msg.title_restore"), tl("msg.restore_confirm", path=src), parent=self):
            return
        eng = self.engine
        try:
            self._flush()                         # a jelenlegi állapotról legyen mentés a visszaállítás előtt
            eng.autosave = False                  # bezáráskor ne írja felül a visszaállított adatot
            storage.import_from(src, core.config_path())
        except (OSError, ValueError) as e:
            eng.autosave = True
            messagebox.showerror(tl("msg.title_error"), str(e), parent=self)
            return
        messagebox.showinfo(tl("msg.title_restore"), tl("msg.restore_done"), parent=self)
        self.on_close()

    def open_data_dir(self):
        d = storage.data_dir()
        opener = getattr(os, "startfile", None)       # csak Windowson létezik
        if opener:
            opener(d)
        else:
            messagebox.showinfo(tl("settings.btn_open"), d, parent=self)

    def toggle_fullscreen(self, _e=None):
        self._fullscreen = not self._fullscreen
        self.attributes("-fullscreen", self._fullscreen)

    def on_close(self):
        self.engine.stop()
        self.engine.join(2.0)
        self.destroy()


def _taskbar_identity():
    """Windows: saját alkalmazás-azonosító, hogy a tálca az Orbiq ikonját mutassa (ne a Python-ét)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Orbiq.SatelliteTracker")
    except Exception:                                # noqa: BLE001 - nem kritikus
        pass


def main():
    _taskbar_identity()
    cfg = core.load_config()
    i18n.init(cfg.get("ui", {}).get("language"))
    try:
        storage.auto_backup(core.config_path())   # indításkor: automatikus mentés, ha az utolsó 6 óránál régebbi
    except OSError:
        pass
    engine = Engine(cfg)
    engine.start()
    App(engine).mainloop()


if __name__ == "__main__":
    main()
