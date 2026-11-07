import sys, math
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), ".."))
from core import *
from viewlogic import az_name
exec(open("test_core.py").read().split("ok = True")[0].split("MU = 398600.4418")[1].join(["MU = 398600.4418\n",""]) if False else "")
MU=398600.4418
class Circ:
    def __init__(self, raan=0, inc=51.6, phase=0, alt=400.0):
        self.R=6378.137+alt; self.n=math.sqrt(MU/self.R**3); i,o=math.radians(inc),math.radians(raan)
        self.P=(math.cos(o),math.sin(o),0.0); self.Q=(-math.sin(o)*math.cos(i),math.cos(o)*math.cos(i),math.sin(i)); self.ph=math.radians(phase)
    def state(self,ts):
        a=self.n*ts+self.ph
        return ([self.R*(math.cos(a)*self.P[k]+math.sin(a)*self.Q[k]) for k in range(3)],
                [self.R*self.n*(-math.sin(a)*self.P[k]+math.cos(a)*self.Q[k]) for k in range(3)])
ok=True
def check(n,c,x=""):
    global ok; print(("PASS " if c else "FAIL ")+n,x); ok&=bool(c)
for az,exp in ((0,"É"),(44,"ÉK"),(90,"K"),(135,"DK"),(180,"D"),(225,"DNy"),(270,"Ny"),(315,"ÉNy"),(359,"É"),(337.4,"ÉNy"),(338,"É")):
    check(f"az_name({az})", az_name(az)==exp, az_name(az))
obs=Observer(47.7,17.65,120); t0=1_793_000_000.0; m=Circ(raan=30,phase=10)
ps=find_passes(m,obs,t0,24); p=ps[0]
tr=pass_track(m,obs,p.aos,p.los)
check("track pontszám ~ időtartam/10 mp", abs(len(tr)-((p.los-p.aos)/10+1))<=1.01, f"{len(tr)} pont, {p.los-p.aos:.0f}s")
check("kezdő/záró eleváció ≈ 0", abs(tr[0][2])<0.05 and abs(tr[-1][2])<0.05, f"{tr[0][2]:.3f} {tr[-1][2]:.3f}")
check("az idők növekvők, az utolsó = LOS", all(a[0]<b[0] for a,b in zip(tr,tr[1:])) and tr[-1][0]==p.los)
mx=max(el for _,_,el in tr); check("track maximuma ≈ a passz max eleváció", abs(mx-p.max_el)<0.6, f"{mx:.2f} vs {p.max_el:.2f}")
check("azimut folytonos (nincs nagy ugrás)", all(min(abs(a[1]-b[1]),360-abs(a[1]-b[1]))<40 for a,b in zip(tr,tr[1:])))
print("   AOS", az_name(tr[0][1]), round(tr[0][1]), "→ LOS", az_name(tr[-1][1]), round(tr[-1][1]), f"max {p.max_el:.1f}°")
print("OK" if ok else "VAN HIBA"); sys.exit(0 if ok else 1)
