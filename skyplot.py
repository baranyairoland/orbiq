# -*- coding: utf-8 -*-
"""Égbolt-kör rajzolása.

Pillow esetén antialiasolt (3x felbontásban rajzol, majd lekicsinyít), egyébként egyszerű Tk-rajzolás.
A feliratokat mindig a Tk rajzolja (így élesek és ClearType-simák).
"""
from __future__ import annotations

import math

from i18n import tl
from viewlogic import fmt_time, polar_xy

try:
    from PIL import Image, ImageDraw
    HAVE_PIL = True
except Exception:            # noqa: BLE001
    HAVE_PIL = False

SAT_COLORS = ["#f2c14e", "#4cc9f0", "#f28482", "#90be6d", "#c77dff", "#ff9f1c", "#2ec4b6", "#e76f51"]


def _have_imagetk() -> bool:
    try:
        from PIL import ImageTk  # noqa: F401
        return True
    except Exception:        # noqa: BLE001
        return False


class TkPainter:
    """Tartalék: sima Tk-vászon rajzolás (nincs élsimítás)."""

    def __init__(self, canvas, w, h, bg):
        self.c = canvas
        canvas.configure(bg=bg)

    def circle(self, cx, cy, r, outline=None, fill=None, width=1):
        self.c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=outline or "", fill=fill or "", width=width)

    def dashed_circle(self, cx, cy, r, color, width=1):
        self.c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=width, dash=(4, 4))

    def line(self, pts, color, width=1, round_caps=False):
        if len(pts) >= 2:
            self.c.create_line(*[v for p in pts for v in p], fill=color, width=width, capstyle="round",
                               joinstyle="round")

    def polygon(self, pts, fill, outline=None):
        self.c.create_polygon(*[v for p in pts for v in p], fill=fill, outline=outline or "")

    def text(self, x, y, text, fill, size=9, bold=False, anchor="center"):
        self.c.create_text(x, y, text=text, fill=fill, anchor=anchor,
                           font=("Segoe UI", size, "bold" if bold else "normal"))

    def restore_static(self, key):
        return False

    def save_static(self, key):
        pass

    def flush(self):
        pass


class SkyPainter:
    """Antialiasolt rajzoló: Pillow, SS-szeres felbontásban, majd lekicsinyítve."""

    def __init__(self, canvas, w, h, bg, ss=3):
        self.c, self.w, self.h, self.ss = canvas, w, h, ss
        self.img = Image.new("RGB", (w * ss, h * ss), bg)
        self.d = ImageDraw.Draw(self.img)
        self.texts = []
        self.photo = None

    def _w(self, width):
        return max(1, int(round(width * self.ss)))

    def circle(self, cx, cy, r, outline=None, fill=None, width=1):
        s = self.ss
        self.d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], outline=outline, fill=fill,
                       width=self._w(width))

    def dashed_circle(self, cx, cy, r, color, width=1, dash=6.0, gap=5.0):
        s = self.ss
        n = max(8, int(2 * math.pi * r / (dash + gap)))
        step = 360.0 / n
        arc = step * dash / (dash + gap)
        box = [(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s]
        for i in range(n):
            self.d.arc(box, i * step, i * step + arc, fill=color, width=self._w(width))

    def line(self, pts, color, width=1, round_caps=False):
        if len(pts) < 2:
            return
        s = self.ss
        P = [(x * s, y * s) for x, y in pts]
        w = self._w(width)
        self.d.line(P, fill=color, width=w, joint="curve")
        if round_caps:
            r = w / 2.0
            for x, y in (P[0], P[-1]):
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=color)

    def polygon(self, pts, fill, outline=None):
        s = self.ss
        P = [(x * s, y * s) for x, y in pts]
        self.d.polygon(P, fill=fill)
        if outline:
            self.d.line(P + [P[0]], fill=outline, width=self._w(1.3), joint="curve")

    def text(self, x, y, text, fill, size=9, bold=False, anchor="center"):
        self.texts.append((x, y, text, fill, size, bold, anchor))

    _static = {}                # (kulcs -> (kép, feliratok)): az állandó háttér (körök, irányok) egyszer készül el

    def restore_static(self, key):
        got = SkyPainter._static.get(key)
        if got is None:
            return False
        self.img = got[0].copy()
        self.d = ImageDraw.Draw(self.img)
        self.texts = list(got[1])
        return True

    def save_static(self, key):
        SkyPainter._static.clear()
        SkyPainter._static[key] = (self.img.copy(), list(self.texts))

    def image(self):
        return self.img.reduce(self.ss)         # dobozszűrős lekicsinyítés: gyors és élsimított (a LANCZOS ~20x lassabb volt)

    def flush(self):
        from PIL import ImageTk
        self.photo = ImageTk.PhotoImage(self.image())
        self.c.create_image(0, 0, anchor="nw", image=self.photo)
        for x, y, text, fill, size, bold, anchor in self.texts:
            self.c.create_text(x, y, text=text, fill=fill, anchor=anchor,
                               font=("Segoe UI", size, "bold" if bold else "normal"))


def make_painter(canvas, w, h, bg):
    if HAVE_PIL and _have_imagetk():
        return SkyPainter(canvas, w, h, bg)
    return TkPainter(canvas, w, h, bg)


def _label(P, cx, xy, text, color, size=9, bold=False):
    left = xy[0] < cx
    P.text(xy[0] + (9 if left else -9), xy[1], text, color, size, bold, "w" if left else "e")


CLASH_RED = "#ff5a52"


def draw_clashes(P, cx, cy, R, sel):
    """Az egyszerre zajló (ütköző) műholdak pályája pirossal, a közös időszakra vágva."""
    for c in sel.get("clash") or []:
        pts = [polar_xy(az, el, cx, cy, R) for _t, az, el in c["track"]]
        P.line(pts, CLASH_RED, 3.0, round_caps=True)
        top = max(c["track"], key=lambda x: x[2])
        xy = polar_xy(top[1], top[2], cx, cy, R)
        P.circle(xy[0], xy[1], 3.5, outline="white", fill=CLASH_RED, width=1)
        _label(P, cx, xy, f"{c['name']} {c['max_el']:.0f}°", "#ff9d94", 8, True)


def draw_selected_pass(P, cx, cy, R, sel):
    track = sel["track"]
    if len(track) < 2:
        return
    draw_clashes(P, cx, cy, R, sel)
    p, mn = sel["p"], sel["mn"]
    pts = [(t, polar_xy(az, el, cx, cy, R), el) for t, az, el in track]
    runs, cur = [], None
    for (_t1, a, e1), (_t2, b, e2) in zip(pts, pts[1:]):
        good = min(e1, e2) >= mn
        if cur is not None and cur[0] == good:
            cur[1].append(b)
        else:
            cur = [good, [a, b]]
            runs.append(cur)
    for good, ps in sorted(runs, key=lambda r: r[0]):          # előbb a szürke, rá a zöld
        P.line(ps, "#37e29a" if good else "#6b7c8c", 4.5 if good else 3.5, round_caps=True)
    last_min = None
    for t, xy, _el in pts:                                      # percjelek, kétpercenként felirattal
        mi = int(t // 60)
        if last_min is not None and mi != last_min:
            P.circle(xy[0], xy[1], 3.2, outline="#cbd5df", fill="#0b1015", width=1.2)
            near = min(abs(mi * 60 - p.aos), abs(mi * 60 - p.los), abs(mi * 60 - p.tmax)) < 100
            if mi % 2 == 0 and not near:
                _label(P, cx, xy, fmt_time(mi * 60)[:5], "#9fb0bf", 8)
        last_min = mi
    x0, y0 = pts[0][1]
    x1, y1 = pts[-1][1]
    P.circle(x0, y0, 6, outline="white", fill="#2ecc71", width=1.5)
    _label(P, cx, (x0, y0), tl("sky.already_up") if p.started else tl("sky.aos", time=fmt_time(p.aos)), "#7dffb0", 9, True)
    P.circle(x1, y1, 6, outline="white", fill="#e74c3c", width=1.5)
    _label(P, cx, (x1, y1), tl("sky.los", time=fmt_time(p.los)), "#ff9d94", 9, True)
    # legmagasabb pont: elevációja a kiszámolt maximum, azimutja a mentett érték
    xm, ym = polar_xy(sel["max_az"], p.max_el, cx, cy, R)
    P.polygon([(xm, ym - 8), (xm + 8, ym), (xm, ym + 8), (xm - 8, ym)], "#ffd166", "white")
    _label(P, cx, (xm, ym), tl("sky.max", el=f"{p.max_el:.1f}", time=fmt_time(p.tmax)), "#ffe39b", 9, True)


def draw_sky(P, w, h, snap, g_min, sel):
    cx, cy = w / 2.0, h / 2.0
    R = max(10.0, min(w, h) / 2.0 - 26)
    grid, txt = "#2a3640", "#7f93a3"
    skey = (w, h, round(g_min, 3), tl("compass.n"))
    if not P.restore_static(skey):
        for el in (0, 30, 60):
            r = R * (90 - el) / 90.0
            P.circle(cx, cy, r, outline=grid, width=1.3)
            if el:
                P.text(cx + 4, cy - r + 8, f"{el}°", txt, 8, anchor="w")
        for az, lab in ((0, tl("compass.n")), (90, tl("compass.e")), (180, tl("compass.s")), (270, tl("compass.w"))):
            x, y = polar_xy(az, 0, cx, cy, R)
            P.line([(cx, cy), (x, y)], grid, 1.3)
            lx, ly = polar_xy(az, -7, cx, cy, R + 4)
            P.text(lx, ly, lab, "#c9d4dc", 10, True)
        P.dashed_circle(cx, cy, R * (90 - g_min) / 90.0, "#b8860b", 1.5)
        P.save_static(skey)
    order = sorted(snap["sats"])
    for n in order:
        info = snap["sats"][n]
        tr = snap["tracks"].get(n)
        if tr and info["enabled"] and len(tr["pts"]) >= 2:
            col = SAT_COLORS[order.index(n) % len(SAT_COLORS)]
            P.line([polar_xy(a, e, cx, cy, R) for a, e in tr["pts"]], col, 2.6 if n == snap["current"] else 1.6)
    if sel:
        draw_selected_pass(P, cx, cy, R, sel)
    for n in order:
        info = snap["sats"][n]
        if not info["enabled"] or info["el"] is None or info["el"] <= 0:
            continue
        col = SAT_COLORS[order.index(n) % len(SAT_COLORS)]
        x, y = polar_xy(info["az"], info["el"], cx, cy, R)
        if n == snap["current"]:
            P.circle(x, y, 9, outline="#ff3b30", width=2)
        P.circle(x, y, 5, fill=col)
        P.text(x + 10, y - 8, f"{info['name']} {info['el']:.0f}°", col, 9, True, "w")
