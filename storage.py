# -*- coding: utf-8 -*-
"""Adattárolás: helyi (hordozható) adatmappa, biztonságos mentés, automatikus biztonsági másolatok, visszaállítás.

Az adatok a program mappája melletti `data` mappában vannak (config.json + backups/). Így a mappa másolásával
az összes adat (műholdlista, frekvenciák, állomás helyzete, ütemezés, TLE-k) költöztethető vagy menthető.
Ha a program mappájába nem lehet írni (pl. Program Files), a %APPDATA%\\Orbiq mappa a tartalék.
Teszteléshez az ORBIQ_DATA_DIR környezeti változóval felülírható a mappa.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import time
from typing import Optional

from i18n import tl

APP_NAMES = ("Orbiq", "PassPilot", "SatFollower")   # a mostani és a korábbi nevek (régi adatok átvételéhez)
BACKUP_EVERY_S = 6 * 3600       # ennyi időnként készül automatikus mentés
KEEP_AUTO = 40                  # ennyi automatikus mentést őrzünk meg (a kézi és visszaállítás előtti mentéseket nem töröljük)
last_load_info: Optional[tuple] = None   # (None) vagy ("recovered", forrásfájl) - a felület ebből tájékoztat


def app_dir() -> str:
    if getattr(sys, "frozen", False):                 # PyInstaller EXE: az EXE mappája
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _appdata_base() -> str:
    return os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")


def _writable(d: str) -> bool:
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_test")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def _migrate_old(d: str) -> None:
    """Első indításkor átvesszük a régi (%APPDATA%\\Orbiq / PassPilot / SatFollower) beállításokat."""
    target = os.path.join(d, "config.json")
    if os.path.isfile(target):
        return
    base = _appdata_base()
    for name in APP_NAMES:
        old = os.path.join(base, name, "config.json")
        if os.path.isfile(old):
            try:
                shutil.copyfile(old, target)
            except OSError:
                pass
            return


def data_dir() -> str:
    env = os.environ.get("ORBIQ_DATA_DIR")
    d = env or os.path.join(app_dir(), "data")
    if not _writable(d):
        d = os.path.join(_appdata_base(), APP_NAMES[0])
        os.makedirs(d, exist_ok=True)
    _migrate_old(d)
    return d


def config_dir() -> str:
    return data_dir()


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def backups_dir(path: Optional[str] = None) -> str:
    return os.path.join(os.path.dirname(path or config_path()), "backups")


# ---- biztonságos írás / olvasás ------------------------------------------------
def _read_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _plausible(d) -> bool:
    return isinstance(d, dict) and (isinstance(d.get("sats"), list) or isinstance(d.get("station"), dict))


def atomic_write_json(path: str, data: dict) -> None:
    """Ideiglenes fájlba ír, lemezre kényszeríti, az előző ép fájlt .bak néven megőrzi, majd cserél."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    if os.path.isfile(path):
        try:
            _read_json(path)                       # csak ép fájlt őrzünk meg tartaléknak
            shutil.copyfile(path, path + ".bak")
        except (OSError, ValueError):
            pass
    os.replace(tmp, path)


def load_json(path: str):
    """(adat, info). Sérült vagy hiányzó fájl esetén a .bak, majd a legújabb ép biztonsági mentés.
    info: None, vagy ("recovered", forrás). Ha semmi nincs: (None, None)."""
    global last_load_info
    last_load_info = None
    cands = [path, path + ".bak"] + sorted(glob.glob(os.path.join(backups_dir(path), "config_*.json")), reverse=True)
    primary_exists = os.path.isfile(path)
    for i, c in enumerate(cands):
        try:
            d = _read_json(c)
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or (i > 0 and not _plausible(d)):
            continue
        if i == 0:
            return d, None
        if primary_exists:                          # a sérült eredetit félretesszük
            try:
                os.replace(path, path + ".hibas")
            except OSError:
                pass
        last_load_info = ("recovered", c)
        try:                                        # a helyreállított adat legyen újra a fő fájl
            atomic_write_json(path, d)
        except OSError:
            pass
        return d, last_load_info
    if primary_exists:                              # sérült, és nincs honnan visszaállítani
        try:
            os.replace(path, path + ".hibas")
        except OSError:
            pass
    return None, None


# ---- biztonsági mentések -------------------------------------------------------
def list_backups(path: Optional[str] = None) -> list:
    """[(fájl, időbélyeg, címke)] legújabb elöl."""
    out = []
    for f in glob.glob(os.path.join(backups_dir(path), "config_*.json")):
        tag = os.path.basename(f)[:-5].split("_")[-1]
        try:
            out.append((f, os.path.getmtime(f), tag))
        except OSError:
            pass
    return sorted(out, key=lambda x: x[1], reverse=True)


def make_backup(path: Optional[str] = None, tag: str = "manual") -> Optional[str]:
    """Másolat a backups mappába. Visszaadja a fájl útját (None, ha nincs mit menteni)."""
    path = path or config_path()
    if not os.path.isfile(path):
        return None
    d = backups_dir(path)
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, f"config_{time.strftime('%Y%m%d-%H%M%S')}_{tag}.json")
    n = 2
    while os.path.exists(dest):                     # azonos másodperc: ne írjuk felül
        dest = os.path.join(d, f"config_{time.strftime('%Y%m%d-%H%M%S')}-{n}_{tag}.json")
        n += 1
    shutil.copyfile(path, dest)
    autos = [f for f, _t, tg in list_backups(path) if tg == "auto"]
    for old in autos[KEEP_AUTO:]:
        try:
            os.remove(old)
        except OSError:
            pass
    return dest


def auto_backup(path: Optional[str] = None, force: bool = False) -> Optional[str]:
    """Automatikus mentés, ha az utolsó mentés régebbi, mint BACKUP_EVERY_S."""
    path = path or config_path()
    b = list_backups(path)
    if not force and b and time.time() - b[0][1] < BACKUP_EVERY_S:
        return None
    try:
        _d = _read_json(path)
        if not _plausible(_d):
            return None
    except (OSError, ValueError):
        return None                                  # sérült fájlt nem mentünk le "jóként"
    return make_backup(path, "auto")


def check_file(src: str) -> dict:
    """Ellenőrzi, hogy a fájl Orbiq-beállítás-e. ValueError (szöveggel), ha nem."""
    try:
        d = _read_json(src)
    except (OSError, ValueError) as e:
        raise ValueError(tl("storage.not_readable", err=e))
    if not _plausible(d):
        raise ValueError(tl("storage.not_orbiq"))
    return d


def export_to(dest: str, path: Optional[str] = None) -> None:
    path = path or config_path()
    shutil.copyfile(path, dest)


def import_from(src: str, path: Optional[str] = None) -> dict:
    """Visszaállítás fájlból: előbb mentés a jelenlegi állapotról, majd a fájl lesz a beállításfájl."""
    path = path or config_path()
    d = check_file(src)
    make_backup(path, "prerestore")
    atomic_write_json(path, d)
    return d
