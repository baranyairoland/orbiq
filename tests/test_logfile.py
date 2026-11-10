import os, sys, tempfile, time
tmp = tempfile.mkdtemp()
os.environ["ORBIQ_DATA_DIR"] = tmp
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import storage, core
ok = True
def check(n, c, x=""):
    global ok; print(("PASS " if c else "FAIL ") + n, x); ok &= bool(c)

t = 1_793_000_000.0
storage.append_log(t, "teszt egy")
storage.append_log(t + 1.5, "teszt\nkettő")
fn = os.listdir(storage.logs_dir())
check("egy napi naplófájl jön létre", len(fn) == 1 and fn[0].startswith("orbiq-") and fn[0].endswith(".log"), fn)
lines = open(os.path.join(storage.logs_dir(), fn[0]), encoding="utf-8").read().splitlines()
check("minden bejegyzés külön sor, időbélyeggel", len(lines) == 2 and lines[0][4] == "-" and lines[1].endswith("teszt kettő"), lines)
old = os.path.join(storage.logs_dir(), "orbiq-2020-01-01.log"); open(old, "w").write("x")
os.utime(old, (t - 40 * 86400, t - 40 * 86400))
other = os.path.join(storage.logs_dir(), "masik.txt"); open(other, "w").write("x"); os.utime(other, (t - 40 * 86400,) * 2)
storage.prune_logs(t)
check("a régi napló törlődik, az idegen fájl nem", not os.path.exists(old) and os.path.exists(other))
check("az új napló megmarad", os.path.exists(os.path.join(storage.logs_dir(), fn[0])))

# motor: _log a fájlba is ír; összegzés és szünet az áthaladás végén
cfg = core.default_config() if hasattr(core, "default_config") else __import__("copy").deepcopy(core.DEFAULT_CONFIG)
cfg["sats"] = []
e = core.Engine(cfg, autosave=False)
e._log("csak memória")
check("autosave nélkül nincs fájlírás", "csak memória" not in "".join(open(os.path.join(storage.logs_dir(), f), encoding="utf-8").read() for f in os.listdir(storage.logs_dir()) if f.startswith("orbiq-")))
e.autosave = True
e._log("fájlba is megy")
check("autosave mellett a napló fájlba is kerül", any("fájlba is megy" in open(os.path.join(storage.logs_dir(), f), encoding="utf-8").read() for f in os.listdir(storage.logs_dir()) if f.startswith("orbiq-")))
check("a diagnosztikai számlálók léteznek", set(e._pstat) >= {"n", "fail", "gap_max", "last"})
print("OK" if ok else "VAN HIBA"); sys.exit(0 if ok else 1)
