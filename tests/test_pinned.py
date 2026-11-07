import sys, socket, threading, time, copy
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..")); sys.path.insert(0, ".")
import importlib.util
spec = importlib.util.spec_from_file_location("tc", "test_core.py")
# csak a modellek kellenek: másoljuk át
from core import *
import math
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
                cmds.append(l.decode().strip()); cn.sendall(b"RPRT 0\n")
        threading.Thread(target=h,daemon=True).start()
threading.Thread(target=serve,daemon=True).start()
obs=Observer(47.7,17.65,120); t0=1_793_000_000.0
A=Circ(raan=30,phase=10); B=Circ(raan=33,phase=14)
ps=find_passes(A,obs,t0,24)
cfg=copy.deepcopy(DEFAULT_CONFIG); cfg["station"].update(lat=47.7,lon=17.65,alt_m=120)
cfg["rig"].update(port=port,interval_ms=20); cfg["tracking"].update(min_elev=10)
e=Engine(cfg,autosave=False)
for n,m,f in ((1,A,437.8e6),(2,B,145.8e6)):
    e.sats[n]=SatEntry(norad=n,name=f"SAT{n}",freq_hz=f); e.models[n]=m
start=ps[0].aos-120; speed=40; base=time.time()
e.now=lambda: start+(time.time()-base)*speed
ok=True
def check(n,c,x=""):
    global ok; print(("PASS " if c else "FAIL ")+n,x); ok&=bool(c)
check("alapértelmezett mód = kijelölt", e.mode=="selected")
e.start(); time.sleep(0.6)
check("nincs kijelölt -> nincs F parancs", not any(c.startswith("F ") for c in cmds))
e.set_pinned(1); time.sleep(1.0)
fs=[c for c in cmds if c.startswith("F ")]
el0=observe(A,obs,e.now()).el
check("kijelölés után azonnal megy az F parancs (horizont alatt is)", len(fs)>3 and el0<10, f"{len(fs)} db, el={el0:.1f}")
check("horizont alatt nincs AOS", "AOS" not in cmds)
time.sleep((ps[0].los-ps[0].aos+150)/speed)
e.set_pinned(2); time.sleep(0.8)
e.stop(); e.join(3)
seq=[c for c in cmds if c in("AOS","LOS")]
i_aos=cmds.index("AOS") if "AOS" in cmds else -1
i_f=next(i for i,c in enumerate(cmds) if c.startswith("F "))
check("F parancsok az AOS előtt kezdődtek", 0<=i_f<i_aos)
check("AOS majd LOS, minimum eleváció szerint", seq[:2]==["AOS","LOS"], str(seq))
last=[c for c in cmds if c.startswith("F ")][-1]
check("átkattintás a 2-es műholdra: 145.8 MHz körüli frekvencia megy", abs(int(last.split()[1])-145.8e6)<10000, last)
# automatikus mód nem nyúl hozzá, ha nincs jelölt
e2=Engine(copy.deepcopy(cfg),autosave=False); check("pinned mentődik/visszatölt", Engine(dict(cfg,tracking=dict(cfg["tracking"],pinned=2)),autosave=False).pinned==2)
print("OK" if ok else "VAN HIBA"); sys.exit(0 if ok else 1)
