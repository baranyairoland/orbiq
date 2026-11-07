import sys, socket, threading, time, copy, math
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), ".."))
from core import *
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "test_pinned.py")).read().split("cmds=[]")[0].split("from core import *")[1])  # Circ modell
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
A=Circ(raan=30,phase=10); ps=find_passes(A,obs,t0,24); p=ps[0]
cfg=copy.deepcopy(DEFAULT_CONFIG); cfg["station"].update(lat=47.7,lon=17.65,alt_m=120)
cfg["rig"].update(port=port,interval_ms=20); cfg["tracking"].update(min_elev=10,mode="selected",pinned=1)
cfg["sats"]=[asdict(SatEntry(norad=1,name="SAT1",freq_hz=437.625e6,offset_hz=300.0,freq_desc="Mode U",mode="SSTV"))]
cfg_pristine=copy.deepcopy(cfg)
ok=True
def check(n,c,x=""):
    global ok; print(("PASS " if c else "FAIL ")+n,x); ok&=bool(c)
e=Engine(cfg,autosave=False); e.models[1]=A
check("régi offset beépült az alapfrekvenciába", e.sats[1].freq_hz==437.625e6+300 and e.sats[1].offset_hz==0.0, f"{e.sats[1].freq_hz}")
e.sats[1].freq_hz=437.625e6
e.now=lambda: p.tmax   # fix időpont -> a Doppler állandó
e.start(); time.sleep(0.5)
f1=int([c for c in cmds if c.startswith("F ")][-1].split()[1]); shift1=e.snap["live"]["shift"]
e.adjust_base(1,+1000); time.sleep(0.5)
f2=int([c for c in cmds if c.startswith("F ")][-1].split()[1]); shift2=e.snap["live"]["shift"]
check("alapfrekvencia +1 kHz -> a kimenő frekvencia is +1 kHz", abs((f2-f1)-1000)<=1, f"{f2-f1} Hz")
check("a Doppler-eltolódás nem változott", abs(shift2-shift1)<1.0, f"{shift1:.1f} -> {shift2:.1f}")
check("szám a kijelzőhöz: live.freq = alap + Doppler", abs(e.snap["live"]["freq"]-(e.sats[1].freq_hz+shift2))<1.0)
check("kézi módosítás után a leírás/mód törlődik", e.sats[1].freq_desc=="" and e.sats[1].mode=="")
e.adjust_base(1,-10**9); check("alsó korlát: nem megy 1 MHz alá", e.sats[1].freq_hz==1e6)
e.stop(); e.join(3)
c2=copy.deepcopy(cfg_pristine); e2=Engine(c2,autosave=False); e2.adjust_base(1,500); e2.save()
check("az új alapfrekvencia a configba mentődik", abs(c2["sats"][0]["freq_hz"]-(437.625e6+300+500))<1 or abs(c2["sats"][0]["freq_hz"]-(437.625e6+500+300))<1, str(c2["sats"][0]["freq_hz"]))
print("OK" if ok else "VAN HIBA"); sys.exit(0 if ok else 1)
