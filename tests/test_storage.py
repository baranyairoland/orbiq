"""Adattárolás: biztonságos írás, sérült fájl helyreállítása, mentések, visszaállítás, átvétel a régi helyről."""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import storage, core

ok = True
def check(name, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name, extra); ok &= bool(cond)

def cfgwith(*names):
    return {"sats": [{"norad": i + 1, "name": n} for i, n in enumerate(names)], "station": {"lat": 1.0}}

T = tempfile.mkdtemp()
os.environ["ORBIQ_DATA_DIR"] = os.path.join(T, "data")
os.environ["APPDATA"] = os.path.join(T, "appdata")

# 1) adatmappa: a program melletti 'data' (itt: a felülírt hely), létrejön
p = storage.config_path()
check("adatmappa létrejön, a config.json ott lesz", os.path.isdir(os.path.dirname(p)) and p.endswith("config.json"), p)

# 2) mentés + .bak + visszaolvasás
core.save_config({**core.DEFAULT_CONFIG, **cfgwith("A")}, p)
core.save_config({**core.DEFAULT_CONFIG, **cfgwith("A", "B")}, p)
check(".bak az előző ép állapot", [s["name"] for s in json.load(open(p + ".bak"))["sats"]] == ["A"])
check("betöltés", [s["name"] for s in core.load_config(p)["sats"]] == ["A", "B"])
check("nem marad .tmp fájl", not os.path.exists(p + ".tmp"))

# 3) sérült fő fájl -> .bak-ból áll vissza, a sérült .hibas lesz
open(p, "w").write('{"sats": [{"norad": 1, "na')
c = core.load_config(p)
check("sérült fájl: visszaállás a .bak-ból", [s["name"] for s in c["sats"]] == ["A"], str(storage.last_load_info))
check("a sérült eredeti félre van téve", os.path.isfile(p + ".hibas"))
check("a felület értesítést kap (last_load_info)", storage.last_load_info and storage.last_load_info[0] == "recovered")

# 4) üres (0 bájtos) fájl - tipikus összeomlás utáni állapot
core.save_config({**core.DEFAULT_CONFIG, **cfgwith("A", "B", "C")}, p)
open(p, "w").close(); os.remove(p + ".bak")
storage.make_backup(p + ".nincs") is None
bd = storage.backups_dir(p); os.makedirs(bd, exist_ok=True)
json.dump(cfgwith("X", "Y"), open(os.path.join(bd, "config_20200101-000000_auto.json"), "w"))
c = core.load_config(p)
check("0 bájtos fájl: visszaállás a legújabb mentésből", [s["name"] for s in c["sats"]] == ["X", "Y"], str(storage.last_load_info))

# 5) a fő fájl hiányzik, de van mentés (pl. újratelepítés után csak a backups mappa maradt)
os.remove(p)
c = core.load_config(p)
check("hiányzó fájl: visszaállás mentésből", [s["name"] for s in c["sats"]] == ["X", "Y"])

# 6) nincs semmi -> alapértékek, nem dob kivételt
T2 = tempfile.mkdtemp()
c = core.load_config(os.path.join(T2, "config.json"))
check("üres adatmappa: alapértékek", c["sats"] == [] and storage.last_load_info is None)

# 7) mentések: kézi, automatikus (időzítés), törlés csak az autóknál
core.save_config({**core.DEFAULT_CONFIG, **cfgwith("Q")}, p)
m = storage.make_backup(p, "manual")
check("kézi mentés létrejön", m and os.path.isfile(m))
check("auto mentés: friss mentés mellett nem készül", storage.auto_backup(p) is None)
old = time.time() - 7 * 3600
for f, _t, _g in storage.list_backups(p): os.utime(f, (old, old))
a = storage.auto_backup(p)
check("auto mentés: 6 óránál régebbi után készül", a and a.endswith("_auto.json"))
storage.KEEP_AUTO = 3
for _ in range(6): storage.make_backup(p, "auto")
tags = [g for _f, _t, g in storage.list_backups(p)]
check("csak az automatikus mentésekből marad meg KEEP_AUTO db", tags.count("auto") == 3, str(tags))
check("a kézi mentés megmarad", tags.count("manual") >= 1)
open(p, "w").write("{rossz")
check("sérült fájlról nem készül 'ép' auto mentés", storage.auto_backup(p, force=True) is None)

# 8) export / import
core.save_config({**core.DEFAULT_CONFIG, **cfgwith("E1", "E2")}, p)
exp = os.path.join(T, "export.json"); storage.export_to(exp, p)
core.save_config({**core.DEFAULT_CONFIG, **cfgwith("MÁS")}, p)
storage.import_from(exp, p)
check("visszaállítás exportált fájlból", [s["name"] for s in core.load_config(p)["sats"]] == ["E1", "E2"])
check("visszaállítás előtt mentés készült a jelenlegi állapotról", any(g == "prerestore" for _f, _t, g in storage.list_backups(p)))
bad = os.path.join(T, "bad.json"); open(bad, "w").write('["nem", "beallitas"]')
try: storage.import_from(bad, p); raised = False
except ValueError: raised = True
check("idegen/hibás fájl visszautasítva", raised)
check("a visszautasítás nem rontja el a jelenlegi adatot", [s["name"] for s in core.load_config(p)["sats"]] == ["E1", "E2"])

# 9) átvétel a régi %APPDATA% helyről (első indítás az új adatmappával)
T3 = tempfile.mkdtemp()
os.environ["APPDATA"] = os.path.join(T3, "appdata")
os.makedirs(os.path.join(T3, "appdata", "PassPilot"))
json.dump(cfgwith("Régi"), open(os.path.join(T3, "appdata", "PassPilot", "config.json"), "w"))
os.environ["ORBIQ_DATA_DIR"] = os.path.join(T3, "ujdata")
c = core.load_config()
check("régi %APPDATA% adatok átvétele", [s["name"] for s in c["sats"]] == ["Régi"])
check("az új mappában ott a másolat, a régi érintetlen", os.path.isfile(os.path.join(T3, "ujdata", "config.json"))
      and os.path.isfile(os.path.join(T3, "appdata", "PassPilot", "config.json")))

print("\nÖSSZESEN:", "MINDEN OK" if ok else "VAN HIBA")
sys.exit(0 if ok else 1)
