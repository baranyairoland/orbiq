import sys, socket, threading, time, copy
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), ".."))
from core import *
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
                cmds.append(l.decode().strip()); cn.sendall(b"434500000\n" if l.strip()==b"f" else b"RPRT 0\n")
        threading.Thread(target=h,daemon=True).start()
threading.Thread(target=serve,daemon=True).start()
cfg=copy.deepcopy(DEFAULT_CONFIG); cfg["station"].update(lat=47.6,lon=17.6); cfg["rig"].update(port=port,interval_ms=50)
e=Engine(cfg,autosave=False); e.start(); time.sleep(1.5)
print("idle (nincs követett műhold) -> connected:", e.snap.get("rig_connected"), "| parancsok:", cmds[:3])
assert e.snap.get("rig_connected") and "f" in cmds
srv.close(); e.stop(); e.join(2); print("OK")
