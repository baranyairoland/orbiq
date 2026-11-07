# -*- coding: utf-8 -*-
"""Többnyelvűség: a szövegek a lang/<kód>.json fájlokban vannak, a kódban csak kulcsok.

Használat:   from i18n import tl        tl("main.add_sat")        tl("log.follow", name="ISS", mhz="437.8")
Új nyelv:    másold le a lang/hu.json fájlt lang/<kód>.json néven, fordítsd le az értékeket, és írd át a
             "_meta" részben a "name" mezőt (a nyelv saját neve). A kulcsokhoz és a {helyőrzőkhöz} ne nyúlj.
Tartalék:    ha egy kulcs hiányzik az aktuális nyelvből, a magyar szöveg jelenik meg (ha az sincs, a kulcs).
"""
from __future__ import annotations

import json
import os
import sys

DEFAULT_LANG = "hu"


def lang_dir() -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "lang")


def _load(code: str) -> dict:
    try:
        with open(os.path.join(lang_dir(), f"{code}.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def available() -> dict:
    """{kód: a nyelv saját neve} a lang mappában található fájlokból."""
    out = {}
    try:
        names = sorted(os.listdir(lang_dir()))
    except OSError:
        names = []
    for fn in names:
        if fn.endswith(".json"):
            code = fn[:-5]
            out[code] = str(_load(code).get("_meta", {}).get("name", code))
    return out


class _State:
    code = DEFAULT_LANG
    table: dict = {}
    fallback: dict = {}
    loaded = False
    missing: set = set()


def system_language() -> str:
    """A gép nyelve szerinti kód, ha van hozzá nyelvi fájl (magyar gépen hu, egyébként en); különben a magyar."""
    code = ""
    try:
        import locale
        code = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "")[:2].lower()      # pl. "hu_HU" -> "hu"
    except Exception:                                  # noqa: BLE001
        code = ""
    if os.name == "nt":
        try:
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF     # elsődleges nyelv-azonosító
            code = {0x0E: "hu", 0x09: "en"}.get(lid, code or "en")
        except Exception:                              # noqa: BLE001
            pass
    have = available()
    if code in have:
        return code
    return "en" if "en" in have and code else DEFAULT_LANG


def init(code: str | None = None) -> str:
    """Nyelv beállítása. Üres vagy "auto" érték esetén a gép nyelve dönt; ismeretlen kódnál a magyar marad."""
    code = (code or "auto").strip().lower()
    if code == "auto":
        code = system_language()
    _State.fallback = _load(DEFAULT_LANG)
    table = _load(code) if code != DEFAULT_LANG else _State.fallback
    if not table:
        code, table = DEFAULT_LANG, _State.fallback
    _State.code, _State.table, _State.loaded = code, table, True
    return code


def current() -> str:
    return _State.code


def t(key: str, **kw) -> str:
    if not _State.loaded:
        init(DEFAULT_LANG)
    s = _State.table.get(key)
    if s is None:
        s = _State.fallback.get(key)
        _State.missing.add(key)
        if s is None:
            s = key
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError, ValueError):
            return s
    return s


tl = t        # a kódban ezt használjuk: a 't' és a 'tr' név helyi változóként is előfordul (idő, pálya)
