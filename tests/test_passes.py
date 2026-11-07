import sys, socket, threading, time, copy, math
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), ".."))
from core import *
MU=398600.4418
class Circ:
    def __init__(self, raan=0, inc=51.6, phase=0, alt=400.0):
        self.R=6378.137+alt; self.n=math.sqrt(MU/self.R**3); i,o=math.radians(inc),math.radians(raan)
        self.P=(math.cos(o),math.sin(o),0.0); self.Q=(-math.sin(o)*math.cos(i),math.cos(o)*math.cos(i),math.sin(i)); self.ph=math.radians(phase)
    def state(self,ts):
        a=self.n*ts+self.ph
        return ([self.R*(math.cos(a)*self.P[k]+math.sin(a)*self.Q[k]) for k in range(3)],
                [self.R*self.n*(-math.sin(a)*self.P[k]+math.cos(a)*self.Q[k]) for k in range(3)])
cmds=[]
srv=socket.socket(); srv.bind(("127.0.0.1",0)); srv.listen(2); port=srv.getsockname()[1]
def serve():
    while True:
        try: cn,_=srv.accept()
        except OSError: return
        def h(cn=cn):
            f=cn.makefile("rwb",buffering=0)
            while True:
                l=f.readline()
                if not l: break
                cmds.append((time.time(),l.decode().strip())); cn.sendall(b"RPRT 0\n")
        threading.Thread(target=h,daemon=True).start()
threading.Thread(target=serve,daemon=True).start()
obs=Observer(47.7,17.65,120); t0=1_793_000_000.0
A=Circ(raan=30,phase=10)
ps=find_passes(A,obs,t0,24)
# két közeli passz kell: használjuk az elsőt (+88s) és a másodikat (kb. +5951s, max 3.5°) -> a másodikhoz minimum 0°
MIN=10.0
good=[p for p in ps if p.max_el>MIN]
p1,p2=good[0],good[1]
print("1. passz max %.1f° | 2. passz max %.1f° (+%.0f perc)"%(p1.max_el,p2.max_el,(p2.aos-p1.aos)/60))
cfg=copy.deepcopy(DEFAULT_CONFIG); cfg["station"].update(lat=47.7,lon=17.65,alt_m=120)
cfg["rig"].update(port=port,interval_ms=20); cfg["tracking"].update(min_elev=MIN,mode="passes")
e=Engine(cfg,autosave=False); e.sats[1]=SatEntry(norad=1,name="SAT1",freq_hz=437.8e6); e.models[1]=A
ok=True
def check(n,c,x=""):
    global ok; print(("PASS " if c else "FAIL ")+n,x); ok&=bool(c)
speed=40.0; start=p1.aos-120; base=time.time()
e.now=lambda: start+(time.time()-base)*speed
e.start(); time.sleep(0.8)
check("pass módban, ütemezés nélkül nincs F parancs", not any(c.startswith("F ") for _,c in cmds))
# a P2-t NEM ütemezzük; P1-et igen
e.add_pass(1,"SAT1",p1.aos,p1.los,p1.tmax,p1.max_el)
check("is_scheduled (±120s tűréssel)", e.is_scheduled(1,p1.los+60) and not e.is_scheduled(1,p2.los) and not e.is_scheduled(2,p1.los))
nx=e.next_scheduled(e.now()); check("next_scheduled = P1", nx and abs(nx["los"]-p1.los)<1)
time.sleep((p1.los-p1.aos+200)/speed)
sim_end=e.now()
e.stop(); e.join(3)
fs=[(t,c) for t,c in cmds if c.startswith("F ")]
# a szimulált idő a parancs érkezésekor:
simt=lambda t: start+(t-base)*speed
tr=[(t,az,el) for t,az,el in pass_track(A,obs,p1.aos,p1.los)]
above=[t for t,_,el in tr if el>=MIN]; w0,w1=above[0],above[-1]
first,last=simt(fs[0][0]),simt(fs[-1][0])
check("az első F parancs a követhető szakasz elején (±30 s)", abs(first-w0)<30, f"{first-w0:+.0f}s")
check("az utolsó F parancs a követhető szakasz végén (±30 s)", abs(last-w1)<30, f"{last-w1:+.0f}s")
seq=[c for _,c in cmds if c in("AOS","LOS")]
check("AOS majd LOS", seq==["AOS","LOS"], str(seq))
# a következő (nem ütemezett) passzt nem követi: szimuláljuk P2 idejére is
# (rövid külön futás)
cmds.clear()
e2=Engine(copy.deepcopy(cfg),autosave=False); e2.sats[1]=SatEntry(norad=1,name="SAT1",freq_hz=437.8e6); e2.models[1]=A
e2.add_pass(1,"SAT1",p1.aos,p1.los,p1.tmax,p1.max_el)
base2=time.time(); s2=p2.aos-60
e2.now=lambda: s2+(time.time()-base2)*40
e2.start(); time.sleep((p2.los-p2.aos+120)/40+0.5); e2.stop(); e2.join(3)
check("nem ütemezett (2.) áthaladásra nem küld semmit", not any(c.startswith("F ") or c in("AOS","LOS") for _,c in cmds))
check("a lejárt ütemezés törlődött", e2.schedule==[], str(e2.schedule))
# mentés / visszatöltés
c3=copy.deepcopy(cfg); e3=Engine(c3,autosave=False); e3.add_pass(1,"SAT1",1.0,2.0,1.5,30.0); e3.save()
check("ütemezés a configba mentődik és visszatölt", Engine(c3,autosave=False).schedule[0]["max_el"]==30.0)
e3.remove_sat(1) if 1 in e3.sats else None
e3.sats[1]=SatEntry(norad=1); e3.remove_sat(1); check("műhold törlésekor az ütemezése is törlődik", e3.schedule==[])
print("OK" if ok else "VAN HIBA"); sys.exit(0 if ok else 1)
