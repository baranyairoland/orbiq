# Műholdlista mentése/betöltése: csak műholdadatok (nincs helyzet, nincs TLE), összefésülés és csere.
import sys, os, json, copy
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import *

ok = True
def check(n, c, x=""):
    global ok; print(("PASS " if c else "FAIL ") + n, x); ok &= bool(c)

def eng(sats):
    cfg = copy.deepcopy(DEFAULT_CONFIG); cfg["station"].update(lat=47.123456, lon=17.654321, alt_m=111)
    cfg["sats"] = [asdict(s) for s in sats]
    return Engine(cfg, autosave=False)

a = eng([SatEntry(norad=25544, name="ISS", freq_hz=437.55e6, mode="FM", min_elev=10, record=False, tle1="1 X", tle2="2 X", tle_fetched=5.0,
                  transmitters=[{"downlink_hz": 437.55e6, "mode": "FM"}]),
         SatEntry(norad=62394, name="CroCube", freq_hz=436.775e6, enabled=False)])
d = a.export_satlist()
txt = json.dumps(d)
check("kiírt lista: 2 műhold, jelölővel", d["orbiq_satlist"] == 1 and len(d["sats"]) == 2)
check("nincs benne helyzet", "47.123456" not in txt and "17.654321" not in txt and "station" not in txt)
check("nincs benne TLE", "tle" not in txt.lower().replace("transmitters", ""), txt[:80])
check("adatok megvannak", d["sats"][0]["freq_hz"] == 437.55e6 and d["sats"][0]["min_elev"] == 10 and d["sats"][0]["record"] is False and d["sats"][1]["enabled"] is False)

b = eng([SatEntry(norad=25544, name="ISS régi", freq_hz=145.8e6, tle1="1 KEEP", tle2="2 KEEP", tle_fetched=9.0), SatEntry(norad=99999, name="Másik")])
added, updated, touched = b.import_satlist(json.loads(txt), replace=False)
check("összefésülés: 1 új, 1 frissített", (added, updated) == (1, 1), (added, updated))
check("a meglévő frissült, de a TLE megmaradt", b.sats[25544].freq_hz == 437.55e6 and b.sats[25544].tle1 == "1 KEEP")
check("a nem szereplő megmaradt", 99999 in b.sats and 62394 in b.sats)
check("új műhold TLE nélkül jön (később töltődik le)", b.sats[62394].tle1 == "" and not b.sats[62394].enabled)

c = eng([SatEntry(norad=99999, name="Másik"), SatEntry(norad=25544, name="ISS régi")])
added, updated, touched = c.import_satlist(json.loads(txt), replace=True)
check("csere: a nem szereplő törlődik", sorted(c.sats) == [25544, 62394] and (added, updated) == (1, 1), sorted(c.sats))

for bad in ({}, {"orbiq_satlist": 2, "sats": []}, {"orbiq_satlist": 1, "sats": "x"}, [1, 2], None):
    try:
        c.import_satlist(bad); check("rossz fájl elutasítva", False, bad)
    except ValueError:
        check("rossz fájl elutasítva", True)
e2 = eng([])
r = e2.import_satlist({"orbiq_satlist": 1, "sats": [{"norad": "abc"}, {"name": "x"}, {"norad": -5}, {"norad": 7, "name": "OK", "evil": 1}]})
check("hibás sorok kimaradnak, ismeretlen mező nem kerül be", r[0] == 1 and list(e2.sats) == [7] and not hasattr(e2.sats[7], "evil"), r)
print("ÖSSZESEN:", "MINDEN OK" if ok else "VAN HIBA"); sys.exit(0 if ok else 1)
