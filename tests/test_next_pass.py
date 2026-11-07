"""A következő megfelelő áthaladás és a műholdlista sorrendje."""
import copy, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from core import *
from viewlogic import sat_order
exec(open(os.path.join(HERE, "test_pinned.py")).read().split("cmds=[]")[0].split("from core import *")[1])   # Circ modell

ok = True
def check(name, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name, extra); ok &= bool(cond)

# 1) sorrend
rows = [(1, True, 500.0, "B"), (2, True, 100.0, "A"), (3, False, 50.0, "C"), (4, True, None, "D"), (5, True, -30.0, "E")]
check("sorrend: zajló, korábbi, későbbi, áthaladás nélküli, kikapcsolt", sat_order(rows) == [5, 2, 1, 4, 3], str(sat_order(rows)))
check("üres lista", sat_order([]) == [])
check("azonos időpont: név szerint", sat_order([(1, True, 10.0, "b"), (2, True, 10.0, "A")]) == [2, 1])

# 2) következő megfelelő áthaladás a motorból
obs = Observer(47.6375, 17.604167, 115)
cfg = copy.deepcopy(DEFAULT_CONFIG)
cfg["station"].update(lat=47.6375, lon=17.604167, alt_m=115)
cfg["tracking"].update(min_elev=10)
eng = Engine(cfg, autosave=False)
A, B = Circ(raan=30, phase=10), Circ(raan=33, phase=14)
eng.sats[1] = SatEntry(norad=1, name="A", freq_hz=437.8e6); eng.models[1] = A
eng.sats[2] = SatEntry(norad=2, name="B", freq_hz=145.8e6); eng.models[2] = B
t0 = 1_793_000_000.0
eng.now = lambda: t0
allp = eng.compute_passes(1, 24)
p = eng.next_suitable_pass(1)
check("van megfelelő áthaladás", p is not None and p.max_el >= 10 and p.los > t0, f"max {p.max_el:.1f}" if p else "")
first_ok = next(q for q in allp if q.los > t0 and q.max_el >= 10)
check("az első olyan, ami eléri a minimumot", abs(p.aos - first_ok.aos) < 1.0)
eng.sats[1].min_elev = 40.0
p40 = eng.next_suitable_pass(1)
exp = next((q for q in allp if q.los > t0 and q.max_el >= 40), None)
check("műholdankénti minimum elevációt veszi figyelembe", (p40 is None) == (exp is None) and (p40 is None or p40.max_el >= 40),
      f"{p40.max_el:.1f}" if p40 else "nincs")
eng.sats[1].min_elev = 89.9
check("ha nincs ilyen 24 órán belül: None", eng.next_suitable_pass(1) is None)
check("ismeretlen műhold: None", eng.next_suitable_pass(99) is None)
# zajló áthaladás is "következő": a közepén állunk
mid = allp[0].tmax
eng.now = lambda: mid
eng.sats[1].min_elev = 5.0
pm = eng.next_suitable_pass(1)
check("zajló áthaladás is megfelelő, ha eléri a minimumot", pm is not None and pm.aos <= mid <= pm.los)

print("\nÖSSZESEN:", "MINDEN OK" if ok else "VAN HIBA")
sys.exit(0 if ok else 1)
