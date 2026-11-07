import math, socket, sys, threading, time
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), ".."))
import core
from core import *

MU = 398600.4418

class EcefFixed:
    """ECEF-hez rögzített pont (geostacionárius-szerű): a Föld forgását követi."""
    def __init__(self, ecef): self.ecef = ecef
    def state(self, ts):
        th = gmst_rad(jd_from_ts(ts)); c, s = math.cos(th), math.sin(th)
        x, y, z = self.ecef
        r = (x*c - y*s, x*s + y*c, z)
        return r, (-OMEGA_E*r[1], OMEGA_E*r[0], 0.0)

class Circ:
    def __init__(self, raan=0, inc=51.6, phase=0, alt=400.0):
        self.R = 6378.137 + alt; self.n = math.sqrt(MU/self.R**3)
        i, o = math.radians(inc), math.radians(raan)
        self.P = (math.cos(o), math.sin(o), 0.0)
        self.Q = (-math.sin(o)*math.cos(i), math.cos(o)*math.cos(i), math.sin(i))
        self.ph = math.radians(phase)
    def state(self, ts):
        a = self.n*ts + self.ph
        r = [self.R*(math.cos(a)*self.P[k] + math.sin(a)*self.Q[k]) for k in range(3)]
        v = [self.R*self.n*(-math.sin(a)*self.P[k] + math.cos(a)*self.Q[k]) for k in range(3)]
        return r, v

ok = True
def check(name, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name, extra)
    ok &= bool(cond)

t0 = 1_793_000_000.0   # 2026-11-ish
obs = Observer(47.7, 17.65, 120.0)

# 1) zenit: az ECEF-ben a megfigyelő fölé 500 km-re rögzített pont
up = (obs.cl*obs.cL, obs.cl*obs.sL, obs.sl)
pt = (obs.ex + 500*up[0], obs.ey + 500*up[1], obs.ez + 500*up[2])
o = observe(EcefFixed(pt), obs, t0)
check("zenit el=90", abs(o.el-90) < 1e-6, f"el={o.el:.6f} rng={o.rng:.4f}")
check("zenit rng=500", abs(o.rng-500) < 1e-6)
check("fix pont rr=0 (megfigyelő sebessége helyesen)", abs(o.rr) < 1e-9, f"rr={o.rr:.2e}")

# 2) égtájak: pont 300 km-re északra/keletre a talajon
north = (-obs.sl*obs.cL, -obs.sl*obs.sL, obs.cl); east = (-obs.sL, obs.cL, 0)
for nm, d, azx in (("észak", north, 0), ("kelet", east, 90)):
    p = (obs.ex+300*d[0]+1*up[0], obs.ey+300*d[1]+1*up[1], obs.ez+300*d[2]+1*up[2])
    o = observe(EcefFixed(p), obs, t0)
    check(f"azimut {nm}", abs(((o.az-azx+180) % 360)-180) < 1e-6, f"az={o.az:.5f} el={o.el:.3f}")

# 3) rr = a távolság numerikus deriváltja
m = Circ(raan=30, phase=10)
for t in (t0, t0+600, t0+3000):
    a, b = observe(m, obs, t-0.5), observe(m, obs, t+0.5)
    o = observe(m, obs, t)
    fd = (b.rng - a.rng)/1.0
    check("rr = d(rng)/dt", abs(fd-o.rr) < 1e-4, f"rr={o.rr:.6f} fd={fd:.6f}")

# 4) Doppler előjel / nagyságrend
check("Doppler: távolodó -> negatív", doppler_shift_hz(435e6, +5.0) < 0)
check("Doppler 435MHz 7km/s ~ 10 kHz", abs(abs(doppler_shift_hz(435e6, 7.0))-10156) < 5, f"{doppler_shift_hz(435e6,7.0):.1f}")

# 5) áthaladások
ps = find_passes(m, obs, t0, 24)
check("van áthaladás 24 órában", len(ps) >= 2, f"db={len(ps)}")
good = True
for p in ps:
    good &= (p.aos < p.tmax < p.los or p.started) and p.max_el > 0
    good &= abs(observe(m, obs, p.los).el) < 0.02
    if not p.started: good &= abs(observe(m, obs, p.aos).el) < 0.02
    # maximum ellenőrzés
    good &= observe(m, obs, p.tmax).el >= observe(m, obs, p.tmax+30).el - 1e-3
    good &= observe(m, obs, p.tmax).el >= observe(m, obs, p.tmax-30).el - 1e-3
    good &= (p.los - p.aos) < 1500
check("passzok konzisztensek (AOS/LOS el≈0, max valóban max)", good)
for p in ps[:3]:
    print("   AOS +%6.0fs  LOS +%6.0fs  max %5.1f°" % (p.aos-t0, p.los-t0, p.max_el))
# folyamatban lévő pass
mid = ps[0].tmax
ps2 = find_passes(m, obs, mid, 1)
check("folyamatban lévő pass: started=True", ps2 and ps2[0].started and abs(ps2[0].los-ps[0].los) < 1.0)
tr = compute_track(m, obs, mid)
check("track AOS/LOS egyezik", tr and abs(tr["los"]-ps[0].los) < 10.5 and abs(tr["aos"]-ps[0].aos) < 10.5,
      f"pts={len(tr['pts'])}")

# 6) Selector
S = Selector()
c = lambda **k: {n: v for n, v in k.items()}
check("üres -> None", S.choose({}, 0, 10, 30) is None)
check("egy felett a minimum", S.choose({1: (25, 20)}, 1, 10, 30) == 1)
check("alatta a minimumnak -> None", S.choose({1: (15, 20)}, 2, 10, 30) is None)
S = Selector()
check("egyszerre két műhold: a magasabb", S.choose({1: (25, 20), 2: (40, 20)}, 0, 10, 30) == 2)
check("marad (nem 10° különbség)", S.choose({1: (45, 20), 2: (40, 20)}, 1, 10, 30) == 2)
check("hiszterézis: kisebb különbség nem vált", S.choose({1: (49, 20), 2: (40, 20)}, 100, 10, 30) == 2)
S2 = Selector(); S2.choose({2: (40, 20)}, 0, 10, 30)
check("dwell: korai váltás tiltva", S2.choose({1: (70, 20), 2: (30, 20)}, 10, 10, 30) == 2)
check("dwell letelt + margin -> vált", S2.choose({1: (70, 20), 2: (30, 20)}, 40, 10, 30) == 1)
S = S2
check("a magasan járót nem dobja el az újonnan érkező miatt", S.choose({1: (60, 20), 2: (21, 20)}, 300, 10, 30) == 1)
check("ha a jelenlegi leesik a minimum alá, azonnal vált", S.choose({1: (15, 20), 2: (22, 20)}, 301, 10, 30) == 2)
check("egyéni min. elevációs küszöb: 3-as 35 fok kell", S.choose({2: (22, 20), 3: (30, 35)}, 302, 10, 30) == 2)

# 7) rigctl + AOS/LOS + váltás: hamis szerver
cmds = []
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); port = srv.getsockname()[1]
def serve():
    while True:
        try: cn, _ = srv.accept()
        except OSError: return
        def handle(cn=cn):
            f = cn.makefile("rwb", buffering=0)
            while True:
                ln = f.readline()
                if not ln: break
                cmds.append(ln.decode().strip())
                cn.sendall(b"RPRT 0\n")
        threading.Thread(target=handle, daemon=True).start()
threading.Thread(target=serve, daemon=True).start()
rc = RigctlClient(); rc.configure("127.0.0.1", port)
check("set_freq", rc.set_freq(437800000) and cmds[-1] == "F 437800000", str(cmds))
# kapcsolat nélküli kliens
bad = RigctlClient(); bad.configure("127.0.0.1", 1)
check("hibás port -> False, nem dob kivételt", bad.set_freq(1) is False and not bad.connected, bad.last_error[:40])

# 8) Engine integráció gyorsított idővel (két műhold, átfedő passzok)
cfg = copy.deepcopy(DEFAULT_CONFIG)
cfg["station"].update(lat=47.7, lon=17.65, alt_m=120)
cfg["rig"].update(port=port, interval_ms=20)
cfg["tracking"].update(min_elev=10, switch_margin=5, min_dwell=5, mode="auto")
eng = Engine(cfg, autosave=False)
A = Circ(raan=30, phase=10); B = Circ(raan=33, phase=14)
for n, mo, fr in ((1, A, 437.8e6), (2, B, 145.8e6)):
    eng.sats[n] = SatEntry(norad=n, name=f"SAT{n}", freq_hz=fr); eng.models[n] = mo
# keressünk olyan időpontot, ahol az A passz közeledik
psA = find_passes(A, obs, t0, 24)
start = psA[0].aos - 60
speed = 40.0
base = time.time()
eng.now = lambda: start + (time.time()-base)*speed
cmds.clear()
eng.start()
dur = (psA[0].los - psA[0].aos + 120) / speed + 1
time.sleep(min(dur, 25))
eng.stop(); eng.join(3)
fs = [c for c in cmds if c.startswith("F ")]
check("rigctl F parancsok mentek", len(fs) > 5, f"{len(fs)} db")
seq = [c for c in cmds if c in ("AOS", "LOS")]
print("   AOS/LOS sorrend:", seq, "| log:", [m for _, m in eng.log][:8])
check("AOS után LOS jön (párban)", len(seq) >= 2 and seq[0] == "AOS" and seq[-1] == "LOS")
fv = [int(c.split()[1]) for c in fs]
mono_dec = sum(1 for a, b in zip(fv, fv[1:]) if b <= a)
check("Doppler: frekvencia a passz alatt csökken (közeledőből távolodóba)", mono_dec > 0.8*len(fv),
      f"{fv[0]} -> {fv[-1]}, eltérés {(fv[-1]-fv[0])/1e3:.2f} kHz (névl. 437800)")

# 9) NMEA, Maidenhead
g = parse_nmea_gga("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
check("NMEA GGA", g and abs(g["lat"]-48.1173) < 1e-4 and abs(g["lon"]-11.51667) < 1e-4 and g["alt_m"] == 545.4, str(g))
check("NMEA nincs fix -> None", parse_nmea_gga("$GPGGA,123519,,,,,0,00,,,M,,M,,*47") is None)
la, lo = grid_to_latlon("JN87"); check("Maidenhead JN87", abs(la-47.5) < 1e-9 and abs(lo-17.0) < 1e-9, f"{la},{lo}")
la, lo = grid_to_latlon("JN58td"); check("Maidenhead 6 kar. (München JN58td)", abs(la-48.1458)<0.01 and abs(lo-11.625)<0.01, f"{la:.4f},{lo:.4f}")

# 10) config kör
import tempfile, os
p = os.path.join(tempfile.mkdtemp(), "c.json")
cc = copy.deepcopy(DEFAULT_CONFIG); cc["sats"] = [asdict(SatEntry(norad=25544, name="ISS", freq_hz=437.8e6))]
save_config(cc, p); l = load_config(p)
check("config mentés/betöltés", l["sats"][0]["norad"] == 25544 and l["rig"]["port"] == 4532)

print("\nÖSSZESEN:", "MINDEN OK" if ok else "VAN HIBA")
sys.exit(0 if ok else 1)
