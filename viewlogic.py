# -*- coding: utf-8 -*-
"""A felület tisztán számolós segédei (tkinter nélkül, tesztelhetők)."""
from __future__ import annotations

import datetime as dt
import math
import re

from i18n import tl


def fmt_mhz(hz, nd: int = 4) -> str:
    return "—" if not hz else f"{hz / 1e6:.{nd}f}"


def fmt_signed_hz(v: float) -> str:
    return f"{v:+,.0f}".replace(",", " ").replace("-", "−") + " Hz"


def fmt_dur(sec: float) -> str:
    sec = int(max(0, round(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_time(ts: float, with_date: bool = False) -> str:
    d = dt.datetime.fromtimestamp(ts)
    return d.strftime("%m.%d. %H:%M:%S") if with_date else d.strftime("%H:%M:%S")


_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def parse_coord(text: str) -> float:
    """Egy koordináta beolvasása: 47.497912 | 47,497912 | -47.6 | 47.6 N | 19°2'24.85"E | 19 2.414 (fok perc másodperc)."""
    t = str(text).strip().upper().replace("NY", "W")
    nums = _NUM.findall(t)
    if not nums or len(nums) > 3:
        raise ValueError("Nem értelmezhető koordináta.")
    vals = [abs(float(x.replace(",", "."))) for x in nums]
    deg = vals[0] + (vals[1] / 60 if len(vals) > 1 else 0) + (vals[2] / 3600 if len(vals) > 2 else 0)
    neg = nums[0].startswith("-") or re.search(r"(?<![A-Z])[SW](?![A-Z])", t) is not None
    return -deg if neg else deg


def split_coord_pair(text: str):
    """„47.497912, 19.040235” (Google Térképről másolva) -> ("47.497912", "19.040235"); ha nem két érték, None."""
    t = str(text).strip()
    if not t:
        return None
    if ";" in t:
        parts = t.split(";")
    elif t.count(",") == 1 and "." in t:
        parts = t.split(",")
    else:
        m = re.match(r"^(.*?[NS])\s*[,;]?\s*(.+)$", t.upper())
        if m:
            parts = [m.group(1), m.group(2)]
        else:
            parts = t.split()
    parts = [p.strip() for p in parts if p.strip()]
    return (parts[0], parts[1]) if len(parts) == 2 else None


def map_url(lat: float, lon: float) -> str:
    """Google Térkép-hivatkozás: a megadott koordinátára tett jelölő."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("A koordináta kívül esik a megengedett tartományon.")
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"


def sat_order(rows) -> list:
    """Műholdak sorrendje a listában. rows: [(norad, bekapcsolt, következő_AOS_vagy_None, név)].

    Elöl a bekapcsoltak a következő megfelelő áthaladás kezdete szerint (a már zajló áthaladás van legelöl),
    utánuk a bekapcsoltak, amelyeknek nincs megfelelő áthaladásuk, a végén a kikapcsoltak (név szerint).
    """
    def key(r):
        n, enabled, aos, name = r
        if not enabled:
            return (2, 0.0, name.lower(), n)
        if aos is None:
            return (1, 0.0, name.lower(), n)
        return (0, float(aos), name.lower(), n)
    return [r[0] for r in sorted(rows, key=key)]


def overlaps(items: dict) -> dict:
    """items: {norad: (aos, los)} -> {norad: [azokkal, amelyekkel az időszaka átfedi]} (csak az ütközők szerepelnek)."""
    out: dict = {}
    keys = list(items)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if items[a][0] < items[b][1] and items[b][0] < items[a][1]:
                out.setdefault(a, []).append(b)
                out.setdefault(b, []).append(a)
    return out


def clashing(aos: float, los: float, others: dict) -> list:
    """others: {név: [(aos, los, max_el), ...]} -> [(név, max_el, aos, los)] azokról, amelyeknek van az [aos, los]
    idővel átfedő áthaladásuk (ha több is van, a legmagasabb), a legmagasabb elevációjúval kezdve."""
    out = []
    for name, spans in others.items():
        hits = [(m, a, b) for a, b, m in spans if a < los and aos < b]
        if hits:
            m, a, b = max(hits)
            out.append((name, m, a, b))
    return sorted(out, key=lambda x: -x[1])


def fmt_clash(items: list, own_el: float) -> str:
    """„⇄ Geoscan-1 19° ▲” – a nyíl: a másik áthaladás magasabb (▲) vagy alacsonyabb (▼), mint ez."""
    if not items:
        return ""
    return "⇄ " + ", ".join(f"{it[0]} {it[1]:.1f}° {'▲' if it[1] > own_el else '▼'}" for it in items)


def aoslos_text(s, rec_global: bool, recording_norad=None) -> str:
    """Küld-e ez a műhold AOS/LOS parancsot az SDR++-nak (saját kapcsoló ÉS általános beállítás együtt)."""
    if recording_norad is not None and s.norad == recording_norad:
        return tl("list.rec_now")
    if not s.record:
        return tl("list.rec_no")
    return tl("list.rec_yes") if rec_global else tl("list.rec_global_off")


def sat_list_rows(items, rec_global: bool = True, recording_norad=None) -> list:
    """A hozzáadott műholdak listája szöveges sorokként (megjelenítéshez, vágólapra, CSV-be).
    items: [(SatEntry, effektív_min_el, következő_megfelelő_áthaladás_vagy_None)] - a sorrend megmarad.
    rec_global: az AOS/LOS vezérlés általános kapcsolója; recording_norad: amelyik műhold felvétele épp fut."""
    rows = []
    for s, mn, p in items:
        if p is None:
            nxt, mx = "—", "—"
        else:
            nxt, mx = dt.datetime.fromtimestamp(p.aos).strftime("%Y.%m.%d. %H:%M:%S"), f"{p.max_el:.1f}°"
        rows.append([s.name or str(s.norad), str(s.norad), fmt_mhz(s.freq_hz, 6), s.mode or "—",
                     f"{mn:g}°" + ("" if s.min_elev is not None else " " + tl("list.global_tag")),
                     aoslos_text(s, rec_global, recording_norad),
                     tl("list.on") if s.enabled else tl("list.off"), nxt, mx,
                     dt.datetime.fromtimestamp(s.tle_fetched).strftime("%Y.%m.%d. %H:%M") if s.tle_fetched else "—"])
    return rows


def rows_to_text(header: list, rows: list, sep: str = "\t") -> str:
    return "\n".join(sep.join(r) for r in [header] + rows) + "\n"


def az_name(az_deg: float) -> str:
    """Azimut -> magyar égtáj (É, ÉK, K, DK, D, DNy, Ny, ÉNy)."""
    names = [tl(f"compass8.{k}") for k in ("n", "ne", "e", "se", "s", "sw", "w", "nw")]
    return names[int(((az_deg % 360.0) + 22.5) // 45) % 8]


def polar_xy(az_deg: float, el_deg: float, cx: float, cy: float, radius: float):
    """Égbolt-kör: észak felül, kelet jobbra, zenit a középpont."""
    r = radius * (90.0 - max(0.0, min(90.0, el_deg))) / 90.0
    a = math.radians(az_deg)
    return cx + r * math.sin(a), cy - r * math.cos(a)


class DigitLayout:
    """SDR++-szerű számjegyes frekvenciakijelző kiosztása.

    A cellák balról jobbra: 10^(n-1) ... 10^0 helyiértékek, 3-asával pontokkal.
    """

    def __init__(self, ndigits: int = 10, digw: float = 36, sepw: float = 16, pad: float = 12):
        self.ndigits, self.digw, self.sepw, self.pad = ndigits, digw, sepw, pad
        self.cells = []        # (x0, x1, hatvány)
        self.seps = []         # a pontok x-középpontja
        x = pad
        for i in range(ndigits):
            p = ndigits - 1 - i
            self.cells.append((x, x + digw, p))
            x += digw
            if p % 3 == 0 and p != 0:
                self.seps.append(x + sepw / 2)
                x += sepw
        self.width = x + pad

    def hit(self, x: float):
        for x0, x1, p in self.cells:
            if x0 <= x < x1:
                return p
        return None

    def digits(self, value: int):
        """[(karakter, halvány-e)] balról jobbra."""
        value = max(0, int(value))
        s = str(value).rjust(self.ndigits, "0")[-self.ndigits:]
        out, leading = [], True
        for ch in s:
            if ch != "0":
                leading = False
            out.append((ch, leading))
        return out
