# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from viewlogic import overlaps
import core

assert overlaps({1: (0, 10), 2: (5, 15), 3: (20, 30)}) == {1: [2], 2: [1]}
assert overlaps({1: (0, 10), 2: (10, 15)}) == {}      # csak érintkezik: nem ütközés
assert overlaps({}) == {}

e = core.Engine.__new__(core.Engine)
e.cfg = {"tracking": {"min_elev": 10.0, "pass_margin": 3.0}}
s = core.SatEntry(norad=1, name="x")
assert e.pass_margin() == 3.0 and e.peak_threshold(s) == 13.0
e.cfg["tracking"].pop("pass_margin")
assert e.pass_margin() == 3.0            # régi konfig: alapérték
e.cfg["tracking"]["pass_margin"] = "hibás"
assert e.pass_margin() == 3.0
print("OK")

# --- motor: a gyenge csúcsú áthaladás nem kerül követésre / nem "megfelelő" ---
import copy
HERE = os.path.dirname(os.path.abspath(__file__))
from core import *
exec(open(os.path.join(HERE, "test_pinned.py")).read().split("cmds=[]")[0].split("from core import *")[1])   # Circ modell
cfg = copy.deepcopy(DEFAULT_CONFIG)
cfg["station"].update(lat=47.6375, lon=17.604167, alt_m=115)
eng = Engine(cfg, autosave=False)
eng.sats[1] = SatEntry(norad=1, name="A", freq_hz=437.8e6); eng.models[1] = Circ(raan=30, phase=10)
t0 = 1_793_000_000.0
eng.now = lambda: t0
passes = eng.compute_passes(1, 48)
p = passes[0]
good = True
def chk(n, c):
    global good
    print(("PASS " if c else "FAIL ") + n); good &= bool(c)
# a küszöböt a legelső áthaladás csúcsa alá/fölé tesszük
eng.cfg["tracking"]["pass_margin"] = 3.0
eng.sats[1].min_elev = p.max_el - 1.0          # a csúcs csak 1°-kal van a minimum fölött
nxt = eng.next_suitable_pass(1, 48)
chk("1° túllógás < 3° hiszterézis: az áthaladás kimarad", nxt is None or nxt.aos > p.aos + 1)
eng.cfg["tracking"]["pass_margin"] = 0.5
nxt = eng.next_suitable_pass(1, 48)
chk("0,5° hiszterézissel már megfelelő", nxt is not None and abs(nxt.aos - p.aos) < 1)
# élő követés auto módban
eng.cfg["tracking"]["pass_margin"] = 3.0
eng.mode = "auto"; eng.tracking_on = True
eng.now = lambda: p.tmax
eng._update_all(p.tmax)
chk("auto módban a gyenge áthaladást nem követi", eng.selector.current is None)
chk("állapotkód: visible_weak", eng.sat_snap[1]["code"] == "visible_weak")
eng.cfg["tracking"]["pass_margin"] = 0.5
eng._update_all(p.tmax)
chk("kisebb hiszterézissel követi", eng.selector.current == 1)

# --- egyetlen áthaladás kihagyása ---
eng.cfg["tracking"]["pass_margin"] = 0.0
eng.sats[1].min_elev = 5.0
eng.now = lambda: t0
first = eng.next_suitable_pass(1, 48)
assert eng.toggle_skip(1, first.los) is True and eng.is_skipped(1, first.los)
second = eng.next_suitable_pass(1, 48)
chk("kihagyott áthaladás helyett a következő jön", second is not None and second.aos > first.aos + 60)
chk("a műhold maga bekapcsolva marad", eng.sats[1].enabled)
eng.mode = "auto"; eng.tracking_on = True; eng.selector.reset()
eng.now = lambda: first.tmax
eng._update_all(first.tmax)
chk("kihagyott áthaladást auto módban nem követi", eng.selector.current is None and eng.sat_snap[1]["code"] == "visible_skipped")
assert eng.toggle_skip(1, first.los) is False
eng._update_all(first.tmax)
chk("visszavétel után követi", eng.selector.current == 1)
eng.toggle_skip(1, first.los); eng.save()
chk("mentésbe kerül", eng.cfg["tracking"]["skipped"] and eng.cfg["tracking"]["skipped"][0]["norad"] == 1)
eng._prune_schedule(first.los + 100)
chk("lejárt kihagyás törlődik", eng.skipped == [])

eng.sats[1].enabled = False; eng.toggle_skip(1, 123.0); eng.add_pass(1, "A", 1.0, 2.0, 1.5, 30.0)
eng.reset_choices()
chk("reset: bekapcsolva, nincs kihagyás/ütemezés", eng.sats[1].enabled and eng.skipped == [] and eng.schedule == [])
chk("reset: frekvencia érintetlen", eng.sats[1].freq_hz == 437.8e6)
d = {"norad": 5, "name": "ISS", "freq_hz": 437.55e6, "mode": "", "freq_desc": "",
     "transmitters": [{"downlink_hz": 437.4e6, "mode": "FM", "description": "x"},
                      {"downlink_hz": 437.55e6, "mode": "SSTV", "description": "Mode U - SSTV - Robot-36"}]}
se = SatEntry.from_dict(d)
chk("mód a mentett adók közül pótlódik", se.mode == "SSTV" and "Robot-36" in se.freq_desc)
d2 = dict(d, mode="GFSK")
chk("meglévő mód nem íródik felül", SatEntry.from_dict(d2).mode == "GFSK")
d3 = dict(d, freq_hz=437.9e6)
chk("nincs egyező adó: marad üres", SatEntry.from_dict(d3).mode == "")
from viewlogic import sat_list_rows, rows_to_text
sa = SatEntry(norad=7, name="A", freq_hz=437.5e6, min_elev=None, record=True)
sb = SatEntry(norad=8, name="", freq_hz=145.8e6, min_elev=15.0, record=False, enabled=False, mode="FM")
rr = sat_list_rows([(sa, 20.0, passes[0]), (sb, 15.0, None)])
chk("lista: 2 sor, 10 oszlop", len(rr) == 2 and all(len(x) == 10 for x in rr))
chk("lista: globális jelölés és saját minimum", "(globális)" in rr[0][4] and rr[1][4] == "15°")
chk("lista: név nélküli műholdnál a NORAD", rr[1][0] == "8" and rr[1][6] == "ki" and rr[1][7] == "—")
chk("lista: frekvencia 6 tizedes", rr[0][2] == "437.500000")
def _raises(f):
    try:
        f()
    except ValueError:
        return True
    return False


from viewlogic import parse_coord, split_coord_pair
chk("koordináta: sima és vesszős tizedes", parse_coord("47.497912") == 47.497912 and parse_coord("47,497912") == 47.497912)
chk("koordináta: előjel és égtáj", parse_coord("-12.5") == -12.5 and parse_coord("12.5 S") == -12.5 and parse_coord("17.5 E") == 17.5)
chk("koordináta: fok-perc-másodperc", abs(parse_coord("19°2'24.85\"E") - 19.040236) < 1e-5 and abs(parse_coord("47 29.9") - 47.498333) < 1e-5)
chk("koordináta: hibás szöveg", all(_raises(lambda x=x: parse_coord(x)) for x in ("", "abc", "1 2 3 4")))
chk("pár: Google Térkép alak", split_coord_pair("47.497912, 19.040235") == ("47.497912", "19.040235"))
chk("pár: szóközzel és pontosvesszővel", split_coord_pair("47.6 17.6") == ("47.6", "17.6") and split_coord_pair("47,6;17,6") == ("47,6", "17,6"))
chk("pár: égtájjal", split_coord_pair("47.6 N 17.6 E") == ("47.6 N", "17.6 E"))
chk("pár: egyetlen érték nem pár", split_coord_pair("47.497912") is None and split_coord_pair("") is None)
chk("pár+érték: teljes kör", (parse_coord(split_coord_pair("47.497912, 19.040235")[0]), parse_coord(split_coord_pair("47.497912, 19.040235")[1])) == (47.497912, 19.040235))
from viewlogic import aoslos_text
from i18n import tl
chk("AOS/LOS cella: küld / nem küld", rr[0][5] == tl("list.rec_yes") and rr[1][5] == tl("list.rec_no"))
chk("AOS/LOS cella: általános kikapcsolva", sat_list_rows([(sa, 20.0, None)], False)[0][5] == tl("list.rec_global_off"))
chk("AOS/LOS cella: épp küld", aoslos_text(sa, True, 7) == tl("list.rec_now") and aoslos_text(sb, True, 7) == tl("list.rec_no"))
tx = rows_to_text(["a", "b"], [["1", "2"]], ";")
chk("lista: szöveg", tx == "a;b\n1;2\n")
from viewlogic import clashing, fmt_clash
r = clashing(10, 20, {"A": [(15, 30, 19.0)], "B": [(20, 25, 50.0)], "C": [(0, 5, 9.0), (19, 21, 33.0), (12, 14, 40.0)]})
chk("clashing: átfedő, legmagasabb elöl", r == [("C", 40.0, 12, 14), ("A", 19.0, 15, 30)])
chk("fmt_clash nyilak", fmt_clash(r, 30.0) == "⇄ C 40.0° ▲, A 19.0° ▼")
chk("fmt_clash üres", fmt_clash([], 30.0) == "")
print("CLASH: MINDEN OK" if good else "VAN HIBA")
sys.exit(0 if good else 1)
