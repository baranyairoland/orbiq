"""Önfrissítés a GitHub-tárolóból (csak a forrásból futtatott változatnál): verzióellenőrzés és biztonságos fájlcsere.

Biztonsági elvek: csak HTTPS és csak a saját tároló; csak a program fájljai cserélődnek (az adatok, a beállítások és a
`data` mappa soha); minden .py fájl szintaxisát ellenőrizzük csere előtt; a régi fájlok a `backup_previous` mappába
kerülnek, és hiba esetén automatikusan visszaállnak."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

REPO = "baranyairoland/orbiq"
API = f"https://api.github.com/repos/{REPO}"
ZIP_URL = f"https://github.com/{REPO}/archive/{{sha}}.zip"
UA = "Orbiq-updater"
BACKUP_DIR = "backup_previous"
MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 60 * 1024 * 1024
# ami cserélődhet: a program gyökerében ezek a kiterjesztések, plusz a lang/ és az assets/ mappa
TOP_EXT = (".py", ".bat", ".txt", ".md")
TOP_NAMES = ("LICENSE",)
DIRS = ("lang", "assets")
REQUIRED = ("orbiq.py", "core.py", "i18n.py", "storage.py")


def app_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def local_hash(build_id: str) -> str:
    """A build_id első szava, ha commit-azonosítónak látszik (7-40 hexa jegy), különben üres."""
    w = (build_id or "").split()
    return w[0].lower() if w and re.fullmatch(r"[0-9a-fA-F]{7,40}", w[0]) else ""


def can_self_update(base: str | None = None) -> tuple[bool, str]:
    """(lehet-e, ok ha nem) – a lehetetlen eseteket a felület szövegesen magyarázza."""
    base = base or app_dir()
    if getattr(sys, "frozen", False):
        return False, "frozen"
    if os.path.isdir(os.path.join(base, ".git")):
        return False, "git"
    if not os.access(base, os.W_OK):
        return False, "readonly"
    return True, ""


def _get(url: str, timeout: float = 15.0, limit: int = MAX_TOTAL) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("only https")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("response too large")
    return data


def check(build_id: str, fetch=_get) -> dict:
    """Megnézi a GitHubon, van-e újabb változat. Hálózati hívás - háttérszálból hívd!
    Visszaad: {"state": "current"|"available"|"error", "sha", "short", "date", "changes": [..], "error": ""}"""
    out = {"state": "error", "sha": "", "short": "", "date": "", "changes": [], "error": ""}
    try:
        head = json.loads(fetch(f"{API}/commits/main"))
        sha = head["sha"].lower()
        out.update(sha=sha, short=sha[:7], date=(head["commit"]["committer"]["date"] or "")[:10])
        first = lambda c: (c["commit"]["message"] or "").strip().split("\n")[0]
        loc = local_hash(build_id)
        if loc and sha.startswith(loc[:40]) or (loc and loc.startswith(sha[:7]) and len(loc) >= 7):
            out["state"] = "current"
            return out
        state, changes = "available", [first(head)]
        if loc:
            try:
                cmp_ = json.loads(fetch(f"{API}/compare/{loc}...main"))
                st = cmp_.get("status")
                if st in ("identical", "behind"):           # a helyi változat azonos vagy újabb, mint a GitHubon lévő
                    state, changes = "current", []
                else:
                    changes = [first(c) for c in cmp_.get("commits", [])][::-1][:8] or changes
            except urllib.error.HTTPError as e:
                if e.code not in (404, 422):                # ismeretlen helyi azonosító (pl. újraírt előzmény): frissíthető
                    raise
        out.update(state=state, changes=changes)
    except urllib.error.HTTPError as e:
        out["error"] = f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        out["error"] = str(e)
    return out


def download(sha: str, fetch=_get) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("bad sha")
    return fetch(ZIP_URL.format(sha=sha), 60.0)


def _wanted(rel: str) -> bool:
    """rel: a gyökérmappa nélküli, / jeles útvonal a zip-ben."""
    if not rel or rel.endswith("/") or ".." in rel.split("/") or rel.startswith("/") or ":" in rel:
        return False
    parts = rel.split("/")
    if len(parts) == 1:
        return parts[0] in TOP_NAMES or parts[0].lower().endswith(TOP_EXT)
    return parts[0] in DIRS and len(parts) == 2 and not parts[1].startswith(".")


def install_zip(data: bytes, base: str | None = None) -> dict:
    """A letöltött zip tartalmából kicseréli a program fájljait. Visszaad: {"changed": [...], "added": [...],
    "requirements": bool}. Hiba esetén visszaállítja az előző állapotot és kivételt dob (ValueError/OSError)."""
    base = base or app_dir()
    ok, why = can_self_update(base)
    if not ok:
        raise ValueError(f"cannot update: {why}")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ValueError("bad zip") from e
    names = [n for n in zf.namelist() if not n.endswith("/")]
    roots = {n.split("/", 1)[0] for n in names}
    if len(roots) != 1:
        raise ValueError("unexpected zip layout")
    root = roots.pop() + "/"
    files: dict[str, bytes] = {}
    total = 0
    for info in zf.infolist():
        if not info.filename.startswith(root) or info.is_dir():
            continue
        rel = info.filename[len(root):]
        if not _wanted(rel):
            continue
        if info.file_size > MAX_FILE:
            raise ValueError("file too large: " + rel)
        total += info.file_size
        if total > MAX_TOTAL:
            raise ValueError("update too large")
        files[rel] = zf.read(info)
    for need in REQUIRED:
        if need not in files:
            raise ValueError("missing in update: " + need)
    for rel, blob in files.items():                       # szintaxis-ellenőrzés a csere ELŐTT
        if rel.endswith(".py"):
            try:
                compile(blob, rel, "exec")
            except SyntaxError as e:
                raise ValueError(f"syntax error in {rel}: {e}") from e
        if rel.startswith("lang/") and rel.endswith(".json"):
            try:
                json.loads(blob.decode("utf-8"))
            except ValueError as e:
                raise ValueError(f"bad language file {rel}") from e

    def dest(rel):
        return os.path.join(base, *rel.split("/"))

    changed, added, todo = [], [], []
    for rel, blob in files.items():
        p = dest(rel)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                if f.read() == blob:
                    continue
            changed.append(rel)
        else:
            added.append(rel)
        todo.append(rel)
    bdir = os.path.join(base, BACKUP_DIR)
    if todo:
        shutil.rmtree(bdir, ignore_errors=True)
        for rel in changed:
            bp = os.path.join(bdir, *rel.split("/"))
            os.makedirs(os.path.dirname(bp), exist_ok=True)
            shutil.copy2(dest(rel), bp)
    done = []
    try:
        for rel in todo:
            p = dest(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".new"
            with open(tmp, "wb") as f:
                f.write(files[rel])
            os.replace(tmp, p)
            done.append(rel)
    except Exception:                                    # noqa: BLE001 - bármilyen hiba: vissza az előzőre
        for rel in todo:
            try:
                os.remove(dest(rel) + ".new")
            except OSError:
                pass
        for rel in done:
            p = dest(rel)
            if rel in added:
                try:
                    os.remove(p)
                except OSError:
                    pass
            else:
                shutil.copy2(os.path.join(bdir, *rel.split("/")), p)
        raise
    return {"changed": changed, "added": added, "requirements": "requirements.txt" in changed + added}


def restart_command(base: str | None = None) -> tuple[list, str]:
    """(parancs, munkamappa) az újraindításhoz: a START.bat (az új csomagokat is telepíti), különben közvetlenül."""
    base = base or app_dir()
    exe = sys.executable
    if os.name == "nt":                      # konzolablak nélküli értelmező (pythonw), hogy ne maradjon fekete ablak
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(w):
            exe = w
    return [exe, os.path.join(base, "orbiq.py")], base
