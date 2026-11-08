# Önfrissítés: verzióellenőrzés (hamis GitHub-válaszokkal) és a fájlcsere biztonsága (ideiglenes mappában).
import sys, os, io, json, zipfile, tempfile, shutil, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import updater

ok = True
def check(n, c, x=""):
    global ok; print(("PASS " if c else "FAIL ") + n, x); ok &= bool(c)

SHA = "a" * 40
def fake(routes):
    def f(url, timeout=15.0, limit=0):
        for k, v in routes.items():
            if k in url:
                if isinstance(v, Exception): raise v
                return json.dumps(v).encode() if not isinstance(v, bytes) else v
        raise urllib.error.HTTPError(url, 404, "nf", {}, None)
    return f
head = {"sha": SHA, "commit": {"message": "Új dolog\n\nrészletek", "committer": {"date": "2026-11-09T10:00:00Z"}}}

check("local_hash: hash+dátum", updater.local_hash("ef137e0 2026-11-08") == "ef137e0")
check("local_hash: dev / $Format -> üres", updater.local_hash("dev") == "" and updater.local_hash("$Format:%h %cs$") == "")
r = updater.check("aaaaaaa 2026-11-09", fake({"commits/main": head}))
check("azonos commit -> current", r["state"] == "current", r)
r = updater.check("bbbbbbb 2026-11-01", fake({"commits/main": head, "compare": {"status": "ahead", "commits": [
    {"commit": {"message": "első\nx"}}, {"commit": {"message": "második"}}]}}))
check("van újabb -> available, változáslista újabbtól régebbi felé", r["state"] == "available" and r["changes"] == ["második", "első"], r)
r = updater.check("bbbbbbb 2026-11-01", fake({"commits/main": head, "compare": {"status": "behind", "commits": []}}))
check("a helyi újabb a GitHubosnál -> current", r["state"] == "current", r)
r = updater.check("bbbbbbb 2026-11-01", fake({"commits/main": head}))
check("ismeretlen helyi azonosító (404) -> available", r["state"] == "available" and r["changes"] == ["Új dolog"], r)
r = updater.check("dev", fake({"commits/main": head}))
check("dev/ismeretlen verzió -> available", r["state"] == "available", r)
r = updater.check("bbbbbbb x", fake({"commits/main": urllib.error.HTTPError("u", 403, "rate", {}, None)}))
check("hálózati/HTTP hiba -> error, nem dob", r["state"] == "error" and "403" in r["error"], r)
r = updater.check("bbbbbbb x", fake({"commits/main": urllib.error.URLError("nincs net")}))
check("nincs internet -> error", r["state"] == "error" and r["error"], r)

def mkzip(files, root="orbiq-" + SHA):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k, v in files.items(): z.writestr(f"{root}/{k}", v)
    return b.getvalue()

GOOD = {"orbiq.py": "print('új')\n", "core.py": "X=2\n", "i18n.py": "Y=1\n", "storage.py": "Z=1\n",
        "requirements.txt": "sgp4\n", "lang/hu.json": '{"a":"b"}', "assets/logo.png": "PNG",
        "START.bat": "@echo off\r\n", "tests/test_x.py": "BAD SYNTAX (((", "data/config.json": "{\"hack\":1}",
        ".github/workflows/x.yml": "evil", "../evil.py": "x"}
def setup():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "data")); os.makedirs(os.path.join(d, "lang"))
    open(os.path.join(d, "orbiq.py"), "w").write("print('régi')\n")
    open(os.path.join(d, "core.py"), "w").write("X=2\n")
    open(os.path.join(d, "lang", "hu.json"), "w").write('{"old":1}')
    open(os.path.join(d, "data", "config.json"), "w").write('{"station":"titok"}')
    open(os.path.join(d, "config.json"), "w").write("{}")
    return d
rd = lambda d, *p: open(os.path.join(d, *p), encoding="utf-8").read()

d = setup()
res = updater.install_zip(mkzip(GOOD), d)
check("a program fájljai cserélődtek", rd(d, "orbiq.py") == "print('új')\n" and rd(d, "lang", "hu.json") == '{"a":"b"}')
check("új fájlok bekerültek", os.path.isfile(os.path.join(d, "i18n.py")) and os.path.isfile(os.path.join(d, "assets", "logo.png")))
check("az adatok és a beállítás érintetlen", rd(d, "data", "config.json") == '{"station":"titok"}' and rd(d, "config.json") == "{}")
check("nem engedélyezett helyekre nem írt (tests, .github, ..)", not os.path.exists(os.path.join(d, "tests")) and not os.path.exists(os.path.join(d, ".github")) and not os.path.exists(os.path.join(os.path.dirname(d), "evil.py")))
check("változatlan fájl nincs a 'changed' listában", "core.py" not in res["changed"] and "orbiq.py" in res["changed"], res)
check("requirements jelzés", res["requirements"] is True)
check("biztonsági mentés az előző fájlokról", rd(d, "backup_previous", "orbiq.py") == "print('régi')\n" and rd(d, "backup_previous", "lang", "hu.json") == '{"old":1}')
shutil.rmtree(d)

def raises(fn, what):
    try: fn(); check(what, False)
    except ValueError: check(what, True)
d = setup()
bad = dict(GOOD); bad["core.py"] = "def (:\n"
raises(lambda: updater.install_zip(mkzip(bad), d), "szintaxishiba -> elutasítva")
check("szintaxishibánál semmi nem változott", rd(d, "orbiq.py") == "print('régi')\n" and not os.path.isdir(os.path.join(d, "backup_previous")))
bad = dict(GOOD); del bad["storage.py"]
raises(lambda: updater.install_zip(mkzip(bad), d), "hiányzó kötelező fájl -> elutasítva")
bad = dict(GOOD); bad["lang/en.json"] = "nem json"
raises(lambda: updater.install_zip(mkzip(bad), d), "hibás nyelvi fájl -> elutasítva")
raises(lambda: updater.install_zip(b"nem zip", d), "nem zip -> elutasítva")
b = io.BytesIO()
with zipfile.ZipFile(b, "w") as z: z.writestr("x/orbiq.py", "1"); z.writestr("y/core.py", "1")
raises(lambda: updater.install_zip(b.getvalue(), d), "több gyökérmappa -> elutasítva")
shutil.rmtree(d)

# fejlesztői (git) mappa nem frissíthető
d = setup(); os.makedirs(os.path.join(d, ".git"))
raises(lambda: updater.install_zip(mkzip(GOOD), d), ".git mappa -> elutasítva")
check("can_self_update: git", updater.can_self_update(d) == (False, "git"))
shutil.rmtree(d)

# csere közbeni hiba -> visszaállítás
d = setup()
real = os.replace; n = {"i": 0}
def flaky(a, b):
    n["i"] += 1
    if n["i"] == 2: raise OSError("lemez tele")
    return real(a, b)
updater.os.replace = flaky
try: updater.install_zip(mkzip(GOOD), d); check("csere közbeni hiba kivételt dob", False)
except OSError: check("csere közbeni hiba kivételt dob", True)
finally: updater.os.replace = real
check("hiba után az előző állapot áll helyre", rd(d, "orbiq.py") == "print('régi')\n" and rd(d, "lang", "hu.json") == '{"old":1}', rd(d, "orbiq.py"))
check("hiba után nem maradt ideiglenes fájl", not any(f.endswith(".new") for r_, _d, fs in os.walk(d) for f in fs))
shutil.rmtree(d)

try: updater._get("http://example.com"); check("http elutasítva", False)
except ValueError: check("http elutasítva", True)
try: updater.download("nem-sha"); check("rossz sha elutasítva", False)
except ValueError: check("rossz sha elutasítva", True)
print("ÖSSZESEN:", "MINDEN OK" if ok else "VAN HIBA"); sys.exit(0 if ok else 1)
