# -*- coding: utf-8 -*-
"""Orbiq - motor (GUI nélkül).

Tartalmaz: konfiguráció, pályaszámítás (SGP4), Doppler, áthaladások,
műhold-választó logika, rigctl kliens (SDR++), NTP, helymeghatározás.
"""
from __future__ import annotations

import copy
import json
import math
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional

import storage
from i18n import tl

C = 299792458.0                 # fénysebesség, m/s
WGS84_A = 6378.137              # km
WGS84_F = 1.0 / 298.257223563
OMEGA_E = 7.2921150e-5          # Föld forgása, rad/s
APP_NAME = "Orbiq"
HEADERS = {"User-Agent": "Orbiq/1.0"}

DEFAULT_CONFIG = {
    "station": {"lat": 0.0, "lon": 0.0, "alt_m": 100.0,
                "gps_port": "COM3", "gps_baud": 9600},
    "rig": {"host": "127.0.0.1", "port": 4532, "interval_ms": 100,
            "recorder_enabled": True, "aos_cmd": "AOS", "los_cmd": "LOS"},
    "tracking": {"enabled": True, "min_elev": 20.0,
                 "switch_margin": 10.0, "min_dwell": 30.0, "pass_margin": 3.0,
                 "mode": "selected", "pinned": None, "schedule": [], "skipped": []},
    "time": {"use_correction": True},
    "ui": {"maximized": True, "language": "auto"},
    "sats": [],
}


# --------------------------------------------------------------------------
# Konfiguráció
# --------------------------------------------------------------------------
def config_dir() -> str:
    return storage.data_dir()


def config_path() -> str:
    return storage.config_path()


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


def load_config(path: Optional[str] = None) -> dict:
    """Beállítások betöltése. Sérült fájl esetén automatikusan az utolsó ép mentésből áll vissza
    (lásd storage.last_load_info)."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    data, _info = storage.load_json(path or config_path())
    if data is not None:
        _merge(cfg, data)
    return cfg


def save_config(cfg: dict, path: Optional[str] = None) -> None:
    storage.atomic_write_json(path or config_path(), cfg)


@dataclass
class SatEntry:
    norad: int
    name: str = ""
    enabled: bool = True
    record: bool = True
    min_elev: Optional[float] = None     # None = globális érték
    freq_hz: float = 0.0                 # névleges (nyugalmi) letöltési frekvencia
    freq_desc: str = ""
    mode: str = ""
    offset_hz: float = 0.0               # kézi finomhangolás
    tle1: str = ""
    tle2: str = ""
    tle_fetched: float = 0.0
    transmitters: list = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> "SatEntry":
        known = set(SatEntry.__dataclass_fields__)
        s = SatEntry(**{k: v for k, v in d.items() if k in known})
        s.fill_mode_from_transmitters()
        return s

    def fill_mode_from_transmitters(self) -> bool:
        """Ha nincs mód elmentve, de a mentett SatNOGS-lista tartalmaz az aktuális frekvenciával egyező adót, abból veszi."""
        if self.mode or not self.freq_hz:
            return False
        for t in self.transmitters or []:
            try:
                if abs(float(t.get("downlink_hz") or 0) - self.freq_hz) < 1 and t.get("mode"):
                    self.mode = t["mode"]
                    if not self.freq_desc or self.freq_desc == tl("dialog.kezi"):
                        self.freq_desc = t.get("description") or t.get("type") or self.freq_desc
                    return True
            except (TypeError, ValueError):
                continue
        return False


# --------------------------------------------------------------------------
# Geometria
# --------------------------------------------------------------------------
def jd_from_ts(ts: float) -> float:
    return ts / 86400.0 + 2440587.5


def gmst_rad(jd: float) -> float:
    d = jd - 2451545.0
    T = d / 36525.0
    g = 280.46061837 + 360.98564736629 * d + 0.000387933 * T * T - T ** 3 / 38710000.0
    return math.radians(g % 360.0)


@dataclass
class Obs:
    az: float      # fok
    el: float      # fok
    rng: float     # km
    rr: float      # km/s (pozitív = távolodik)


class Observer:
    def __init__(self, lat_deg: float, lon_deg: float, alt_m: float):
        self.lat_deg, self.lon_deg, self.alt_m = lat_deg, lon_deg, alt_m
        self.lat = math.radians(lat_deg)
        self.lon = math.radians(lon_deg)
        h = alt_m / 1000.0
        e2 = 2 * WGS84_F - WGS84_F ** 2
        sl, cl = math.sin(self.lat), math.cos(self.lat)
        N = WGS84_A / math.sqrt(1 - e2 * sl * sl)
        self.ex = (N + h) * cl * math.cos(self.lon)
        self.ey = (N + h) * cl * math.sin(self.lon)
        self.ez = (N * (1 - e2) + h) * sl
        self.sl, self.cl = sl, cl
        self.sL, self.cL = math.sin(self.lon), math.cos(self.lon)

    def look(self, r, v, ts: float) -> Obs:
        """r [km], v [km/s] TEME-ben -> azimut, elevació, távolság, távolságváltozás."""
        th = gmst_rad(jd_from_ts(ts))
        c, s = math.cos(th), math.sin(th)
        ox = self.ex * c - self.ey * s
        oy = self.ex * s + self.ey * c
        oz = self.ez
        ovx, ovy = -OMEGA_E * oy, OMEGA_E * ox
        rx, ry, rz = r[0] - ox, r[1] - oy, r[2] - oz
        vx, vy, vz = v[0] - ovx, v[1] - ovy, v[2]
        rng = math.sqrt(rx * rx + ry * ry + rz * rz)
        rr = (rx * vx + ry * vy + rz * vz) / rng
        xe = rx * c + ry * s
        ye = -rx * s + ry * c
        ze = rz
        e = -self.sL * xe + self.cL * ye
        n = -self.sl * self.cL * xe - self.sl * self.sL * ye + self.cl * ze
        u = self.cl * self.cL * xe + self.cl * self.sL * ye + self.sl * ze
        az = math.degrees(math.atan2(e, n)) % 360.0
        el = math.degrees(math.asin(max(-1.0, min(1.0, u / rng))))
        return Obs(az, el, rng, rr)


class SGP4Model:
    """TLE alapú pályamodell (sgp4 csomag)."""

    def __init__(self, line1: str, line2: str):
        from sgp4.api import Satrec
        self.sat = Satrec.twoline2rv(line1, line2)
        self.epoch_ts = (self.sat.jdsatepoch + self.sat.jdsatepochF - 2440587.5) * 86400.0

    def state(self, ts: float):
        total = jd_from_ts(ts)
        jd = math.floor(total - 0.5) + 0.5
        fr = total - jd
        e, r, v = self.sat.sgp4(jd, fr)
        if e != 0:
            raise ValueError(f"SGP4 hiba ({e})")
        return r, v


def observe(model, obs: Observer, ts: float) -> Obs:
    r, v = model.state(ts)
    return obs.look(r, v, ts)


def doppler_shift_hz(f0_hz: float, rr_kms: float) -> float:
    """Vételi frekvenciaeltolódás (Hz). Távolodó műhold -> negatív."""
    return -f0_hz * (rr_kms * 1000.0) / C


# --------------------------------------------------------------------------
# Áthaladások
# --------------------------------------------------------------------------
@dataclass
class Pass:
    aos: float
    los: float
    tmax: float
    max_el: float
    aos_az: float
    los_az: float
    started: bool = False     # a keresés kezdetekor már fent volt


def _bisect(f, a, b, level, rising):
    for _ in range(12):
        m = (a + b) / 2
        if (f(m) > level) == rising:
            b = m
        else:
            a = m
    return (a + b) / 2


def find_passes(model, observer: Observer, t0: float, hours: float = 24.0,
                step: float = 20.0, horizon: float = 0.0) -> list:
    t1 = t0 + hours * 3600.0

    def look(t):
        try:
            o = observe(model, observer, t)
            return o.az, o.el
        except Exception:
            return 0.0, -90.0

    def el(t):
        return look(t)[1]

    def finish(cur, los):
        a, b = cur["tbest"] - step, cur["tbest"] + step
        for _ in range(25):                      # ternary search a maximumra
            m1, m2 = a + (b - a) / 3, b - (b - a) / 3
            if el(m1) < el(m2):
                a = m1
            else:
                b = m2
        tm = (a + b) / 2
        mx = max(el(tm), cur["best"])
        return Pass(cur["aos"], los, tm, mx, look(cur["aos"])[0], look(los)[0], cur["started"])

    passes = []
    t, e = t0, el(t0)
    cur = None
    if e > horizon:
        cur = {"aos": t0, "started": True, "best": e, "tbest": t0}
    while t < t1 or cur is not None:
        # messze a horizont alatt a műhold elevációja lassan változik: nagyobb lépés (gyorsabb keresés, ugyanaz az eredmény)
        tn = t + (step if e > -8.0 else min(90.0, step + (-e - 8.0) * 2.5))
        en = el(tn)
        if cur is not None and en > cur["best"]:
            cur["best"], cur["tbest"] = en, tn
        if cur is None and en > horizon >= e:
            cur = {"aos": _bisect(el, t, tn, horizon, True), "started": False,
                   "best": en, "tbest": tn}
        elif cur is not None and en <= horizon < e:
            los = _bisect(el, t, tn, horizon, False)
            passes.append(finish(cur, los))
            cur = None
        t, e = tn, en
        if t >= t1 and cur is None:
            break
        if t > t1 + 7200:      # biztonsági kilépés
            break
    return passes


def pass_track(model, observer: Observer, aos: float, los: float, step: float = 10.0) -> list:
    """Egy áthaladás pályája: [(időbélyeg, azimut, eleváció), ...] AOS-tól LOS-ig."""
    pts = []
    t = aos
    while t < los:
        o = observe(model, observer, t)
        pts.append((t, o.az, o.el))
        t += step
    o = observe(model, observer, los)
    pts.append((los, o.az, o.el))
    return pts


def compute_track(model, observer: Observer, now: float, step: float = 10.0,
                  max_span: float = 1800.0) -> Optional[dict]:
    """Az éppen zajló áthaladás pályája (az égbolt-körhöz)."""
    def f(t):
        o = observe(model, observer, t)
        return o.az, o.el
    if f(now)[1] <= 0:
        return None
    a = now
    while now - a < max_span and f(a - step)[1] > 0:
        a -= step
    b = now
    while b - now < max_span and f(b + step)[1] > 0:
        b += step
    pts = []
    t = a
    while t <= b:
        pts.append(f(t))
        t += step
    pts.append(f(b))
    return {"aos": a, "los": b, "pts": pts, "peak": max(el for _az, el in pts)}


# --------------------------------------------------------------------------
# Műhold-választó
# --------------------------------------------------------------------------
class Selector:
    """Eldönti, melyik műholdat kövessük.

    * Csak az a műhold jöhet szóba, amelyik a (saját vagy globális) minimum
      elevációja fölött van.
    * Ha nincs követett műhold: a legmagasabb elevációjú.
    * Ha van: addig marad, amíg
        - a minimum elevációja alá nem megy (ekkor azonnal vált), vagy
        - egy másik legalább `margin` fokkal magasabban nincs ÉS a
          legutóbbi váltás óta eltelt legalább `dwell` másodperc.
      Így a magasan járó műholdat nem dobjuk el egy éppen felbukkanó miatt.
    """

    def __init__(self):
        self.current = None
        self.since = 0.0

    def reset(self):
        self.current = None
        self.since = 0.0

    def choose(self, cands: dict, now: float, margin: float, dwell: float):
        """cands: {norad: (elevacio, min_elevacio)}"""
        ok = {n: el for n, (el, mn) in cands.items() if el >= mn}
        cur = self.current
        if not ok:
            new = None
        else:
            best = max(sorted(ok), key=lambda n: ok[n])
            if cur in ok:
                if best != cur and ok[best] >= ok[cur] + margin and now - self.since >= dwell:
                    new = best
                else:
                    new = cur
            else:
                new = best
        if new != cur:
            self.current = new
            self.since = now
        return new


# --------------------------------------------------------------------------
# rigctl kliens (SDR++ Rigctl Server)
# --------------------------------------------------------------------------
class RigctlClient:
    def __init__(self):
        self.host, self.port = "127.0.0.1", 4532
        self.sock = None
        self.connected = False
        self.last_error = ""
        self._last_try = 0.0
        self._connecting = False
        self._ilock = threading.Lock()   # csak a háttér-csatlakozás eredményének beírásához
        self._gen = 0                  # a host/port váltását jelzi a futó háttér-csatlakozásnak
        self.lock = threading.Lock()

    def configure(self, host: str, port: int):
        with self.lock:
            if (host, int(port)) != (self.host, self.port):
                self._close()
                self._gen += 1
                self._last_try = 0.0
            self.host, self.port = host, int(port)

    def _close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.connected = False

    def close(self):
        with self.lock:
            self._close()

    def _open(self):
        """Egy csatlakozási kísérlet. Visszaad: (socket vagy None, hiba). Lassú is lehet - ne tartsd közben a zárat."""
        targets = [self.host]
        if self.host in ("127.0.0.1", "localhost"):          # az IPv6-os ::1 címet is kipróbáljuk
            targets.append("::1")
        last = None
        for h in targets:
            try:
                s = socket.create_connection((h, self.port), timeout=0.6)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.settimeout(0.4)
                return s, None
            except OSError as e:
                last = e
        return None, last

    def _install(self, s, err):
        if s is not None:
            self.sock = s
            self.connected = True
            self.last_error = ""
        else:
            self.connected = False
            self.last_error = str(err)

    def _bg_connect(self, gen):
        s, err = self._open()
        with self._ilock:
            if gen != self._gen or self.sock is not None:     # közben host/port váltás vagy más már csatlakozott
                if s is not None:
                    s.close()
            else:
                self._install(s, err)
            self._connecting = False

    def _ensure(self, force=False) -> bool:
        """A csatlakozás háttérszálon fut, hogy a lassú (időtúllépéses) kísérlet ne fogja meg a motort és a felületet."""
        if self.sock is not None:
            return True
        if force:
            self._last_try = time.monotonic()
            self._install(*self._open())
            return self.sock is not None
        if self._connecting or time.monotonic() - self._last_try < 2.0:
            return False
        self._last_try = time.monotonic()
        self._connecting = True
        t = threading.Thread(target=self._bg_connect, args=(self._gen,), daemon=True)
        t.start()
        # a gyors (helyi) kapcsolat így azonnal létrejön; a lassú csak a háttérben folytatódik
        for _ in range(10):
            time.sleep(0.005)
            if not t.is_alive():
                break
        return self.sock is not None

    def command(self, line: str, wait_reply: bool = True, force: bool = False):
        """Visszaad: válasz-szöveg ('' ha nem jött), vagy None ha nem sikerült küldeni."""
        with self.lock:
            if not self._ensure(force):
                return None
            try:
                self.sock.sendall((line.strip() + "\n").encode("ascii", "replace"))
                if not wait_reply:
                    return ""
                buf = b""
                try:
                    while not buf.endswith(b"\n"):
                        chunk = self.sock.recv(256)
                        if not chunk:
                            raise ConnectionError(tl("core.a_kapcsolat_megszakadt"))
                        buf += chunk
                except socket.timeout:
                    pass
                return buf.decode(errors="replace").strip()
            except OSError as e:
                self._close()
                self.last_error = str(e)
                return None

    def set_freq(self, hz: int) -> bool:
        r = self.command(f"F {int(hz)}")
        if r is None:
            return False
        if r.startswith("RPRT") and r.split()[-1] != "0":
            self.last_error = tl("core.rigctl_error", reply=r)
            return False
        return True

    def get_freq(self, force=False):
        r = self.command("f", force=force)
        try:
            return int(float(r.split()[0]))
        except Exception:
            return None


def _win_timer(on: bool):
    if sys.platform == "win32":
        try:
            import ctypes
            (ctypes.windll.winmm.timeBeginPeriod if on else ctypes.windll.winmm.timeEndPeriod)(1)
        except Exception:
            pass


# --------------------------------------------------------------------------
# Motor (háttérszál)
# --------------------------------------------------------------------------
class Engine(threading.Thread):
    SEL_PERIOD = 0.5

    def __init__(self, cfg: dict, autosave: bool = True):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.autosave = autosave
        self._last_backup_check = 0.0
        self.lock = threading.RLock()
        self.stop_evt = threading.Event()
        self.sats = {}
        for d in cfg.get("sats", []):
            s = SatEntry.from_dict(d)
            self.sats[s.norad] = s
        self.models = {}
        self.selector = Selector()
        self.rig = RigctlClient()
        self.tracking_on = bool(cfg["tracking"].get("enabled", True))
        self.mode = cfg["tracking"].get("mode", "selected")      # "selected" | "auto"
        self.pinned = cfg["tracking"].get("pinned")              # a kijelölt (követett) műhold
        self.schedule = [dict(x) for x in cfg["tracking"].get("schedule", [])]   # ütemezett áthaladások
        self._pcache = {}                                                        # norad -> (kulcs, mikor, [Pass])
        self.skipped = [dict(x) for x in cfg["tracking"].get("skipped", [])]     # kézzel kihagyott áthaladások
        self._sel_now = False
        self.ntp_offset = 0.0
        self.ntp_info = tl("log.nincs_meres")
        self.current = None
        self.recording = False
        self.last_sent = None
        self.log = deque(maxlen=300)
        self.sat_snap = {}
        self.tracks = {}
        self.tracks_pub = {}
        self.live = {}
        self.snap = {}
        self._dirty = False
        self._last_save = time.monotonic()
        self._rig_prev = None
        self._last_ping = 0.0
        self._last_err = ("", 0.0)
        self.observer = None
        self.apply_config()
        for s in self.sats.values():
            self._build_model(s)
        for s in self.sats.values():       # a régi "kézi eltolást" beépítjük az alapfrekvenciába
            if s.offset_hz:
                s.freq_hz += s.offset_hz
                self._log(tl("log.p_a_korabbi_kezi", p=s.name or s.norad, offset_hz=s.offset_hz))
                s.offset_hz = 0.0
                self._dirty = True

    # ---- segédek --------------------------------------------------------
    def now(self) -> float:
        off = self.ntp_offset if self.cfg["time"].get("use_correction", True) else 0.0
        return time.time() + off

    def _log(self, msg: str):
        self.log.append((self.now(), msg))

    def location_ok(self) -> bool:
        st = self.cfg["station"]
        return not (float(st["lat"]) == 0.0 and float(st["lon"]) == 0.0)

    def pass_margin(self) -> float:
        """Csúcs-hiszterézis: egy áthaladás csak akkor követhető, ha a csúcsa min. eleváció + ennyi fok."""
        try:
            return max(0.0, float(self.cfg["tracking"].get("pass_margin", 3.0)))
        except (TypeError, ValueError):
            return 3.0

    def peak_threshold(self, s: SatEntry) -> float:
        return self.eff_min_elev(s) + self.pass_margin()

    def eff_min_elev(self, s: SatEntry) -> float:
        return float(s.min_elev) if s.min_elev is not None else float(self.cfg["tracking"]["min_elev"])

    def apply_config(self):
        st = self.cfg["station"]
        self.observer = Observer(float(st["lat"]), float(st["lon"]), float(st["alt_m"]))
        self.rig.configure(self.cfg["rig"]["host"], int(self.cfg["rig"]["port"]))

    def _build_model(self, s: SatEntry):
        self.models.pop(s.norad, None)
        if s.tle1 and s.tle2:
            try:
                self.models[s.norad] = SGP4Model(s.tle1, s.tle2)
            except Exception as e:
                self._log(f"TLE hiba ({s.name or s.norad}): {e}")

    def save(self):
        self.cfg["sats"] = [asdict(s) for s in self.sats.values()]
        self.cfg["tracking"]["enabled"] = self.tracking_on
        self.cfg["tracking"]["mode"] = self.mode
        self.cfg["tracking"]["pinned"] = self.pinned
        self.cfg["tracking"]["schedule"] = self.schedule
        self.cfg["tracking"]["skipped"] = self.skipped
        if self.autosave:
            try:
                save_config(self.cfg)
                if time.monotonic() - self._last_backup_check > 600:      # időnként automatikus biztonsági mentés
                    self._last_backup_check = time.monotonic()
                    storage.auto_backup(config_path())
            except OSError as e:
                self._log(tl("core.mentesi_hiba_e", e=e))
        self._dirty = False
        self._last_save = time.monotonic()

    # ---- GUI felé nyújtott műveletek -----------------------------------
    def set_tracking(self, on: bool):
        with self.lock:
            self.tracking_on = on
            if not on:
                self.selector.reset()
                if self.current is not None:
                    self._switch(None, self.now())
            self.save()
            self._log(tl("log.tracking_on" if on else "log.tracking_off"))

    def set_mode(self, mode: str):
        """'selected': a kijelölt műholdat követi mindig; 'auto': elevációs szabályok szerint vált."""
        with self.lock:
            if mode not in ("selected", "auto", "passes") or mode == self.mode:
                return
            self.mode = mode
            self.selector.reset()
            self._sel_now = True
            self.save()
            self._log(tl("log.mode", name={"selected": tl("core.kijelolt_muhold_kovetese"), "auto": tl("core.automatikus_valtas"),
                                         "passes": tl("core.csak_a_kijelolt_athaladasok")}[mode]))

    def set_pinned(self, norad):
        with self.lock:
            if norad == self.pinned:
                return
            self.pinned = norad
            self._sel_now = True
            self.save()

    # ---- ütemezett áthaladások ---------------------------------------
    @staticmethod
    def _match(e, norad, los):
        return e["norad"] == norad and abs(e["los"] - los) < 120

    def is_scheduled(self, norad: int, los: float) -> bool:
        return any(self._match(e, norad, los) for e in self.schedule)

    def add_pass(self, norad: int, name: str, aos: float, los: float, tmax: float, max_el: float):
        with self.lock:
            if not self.is_scheduled(norad, los):
                self.schedule.append({"norad": norad, "name": name, "aos": aos, "los": los,
                                      "tmax": tmax, "max_el": max_el})
                self.schedule.sort(key=lambda e: e["aos"])
                self._sel_now = True
                self.save()
                self._log(tl("core.athaladas_utemezve_name_max", name=name, max_el=max_el))

    def remove_pass(self, norad: int, los: float):
        with self.lock:
            keep = [e for e in self.schedule if not self._match(e, norad, los)]
            if len(keep) != len(self.schedule):
                self.schedule = keep
                self._sel_now = True
                self.save()

    def is_skipped(self, norad: int, los: float) -> bool:
        return any(self._match(e, norad, los) for e in self.skipped)

    def toggle_skip(self, norad: int, los: float) -> bool:
        """Egyetlen áthaladás kihagyása / visszavétele. Visszaad: True, ha most ki van hagyva."""
        with self.lock:
            if self.is_skipped(norad, los):
                self.skipped = [e for e in self.skipped if not self._match(e, norad, los)]
                res = False
            else:
                self.skipped.append({"norad": norad, "los": los})
                res = True
            self._sel_now = True
            self.save()
            return res

    def reset_choices(self):
        """Az összes kézi választás visszaállítása: minden műhold bekapcsolva, nincs kihagyott és ütemezett áthaladás.
        A frekvenciákhoz, küszöbökhöz és módhoz nem nyúl."""
        with self.lock:
            for s in self.sats.values():
                s.enabled = True
            self.skipped = []
            self.schedule = []
            self._sel_now = True
            self.save()
            self._log(tl("log.reset_choices"))

    def clear_schedule(self):
        with self.lock:
            self.schedule = []
            self._sel_now = True
            self.save()

    def next_scheduled(self, now: float):
        c = [e for e in self.schedule if e["los"] > now]
        return min(c, key=lambda e: e["aos"]) if c else None

    def _sched_active(self, norad: int, now: float) -> bool:
        return any(e["norad"] == norad and e["aos"] - 5 <= now <= e["los"] + 5 for e in self.schedule)

    def _prune_schedule(self, now: float):
        ks = [e for e in self.skipped if e["los"] > now - 30]
        if len(ks) != len(self.skipped):
            self.skipped = ks
            self._dirty = True
        keep = [e for e in self.schedule if e["los"] > now - 30]
        if len(keep) != len(self.schedule):
            self.schedule = keep
            self._dirty = True

    def add_sat(self, s: SatEntry):
        with self.lock:
            self.sats[s.norad] = s
            self._build_model(s)
            self.save()

    SATLIST_FIELDS = ("norad", "name", "enabled", "record", "min_elev", "freq_hz", "freq_desc", "mode", "offset_hz",
                      "transmitters", "radio")

    def export_satlist(self) -> dict:
        """Megosztható műholdlista: csak a műholdak adatai - állomás-helyzet, beállítások, TLE nincs benne."""
        with self.lock:
            rows = []
            for s in self.sats.values():
                d = asdict(s)
                rows.append({k: d[k] for k in self.SATLIST_FIELDS if k in d})
        return {"orbiq_satlist": 1, "sats": rows}

    def import_satlist(self, data: dict, replace: bool = False):
        """Visszaad: (új, frissített, [az új/frissített műholdak NORAD-jai]). A pályaadatot (TLE) később kell letölteni."""
        if not isinstance(data, dict) or data.get("orbiq_satlist") != 1 or not isinstance(data.get("sats"), list):
            raise ValueError("not a satellite list")
        rows = []
        for d in data["sats"]:
            try:
                n = int(d["norad"])
                if n <= 0:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                continue
            rows.append((n, {k: d[k] for k in self.SATLIST_FIELDS if k in d and k != "norad"}))
        added = updated = 0
        touched = []
        with self.lock:
            if replace:
                for n in list(self.sats):
                    if n not in {r[0] for r in rows}:
                        self.remove_sat(n)
            for n, kw in rows:
                if n in self.sats:
                    self.update_sat(n, **kw)
                    updated += 1
                else:
                    s = SatEntry.from_dict({"norad": n, **kw})
                    self.sats[n] = s
                    added += 1
                touched.append(n)
            self.save()
        return added, updated, touched

    def remove_sat(self, norad: int):
        with self.lock:
            if self.pinned == norad:
                self.pinned = None
            self.schedule = [e for e in self.schedule if e["norad"] != norad]
            if self.current == norad:
                self.selector.reset()
                self._switch(None, self.now())
            self.sats.pop(norad, None)
            self.models.pop(norad, None)
            self.tracks.pop(norad, None)
            self.save()

    def update_sat(self, norad: int, **kw):
        with self.lock:
            s = self.sats.get(norad)
            if not s:
                return
            freq_changed = "freq_hz" in kw and kw["freq_hz"] != s.freq_hz
            for k, v in kw.items():
                setattr(s, k, v)
            if "tle1" in kw or "tle2" in kw:
                self._build_model(s)
            if freq_changed and self.current == norad:
                self.last_sent = None
            self.save()

    def adjust_offset(self, norad: int, delta_hz: float):
        with self.lock:
            s = self.sats.get(norad)
            if s:
                s.offset_hz += delta_hz
                self._dirty = True

    def adjust_base(self, norad: int, delta_hz: float):
        """Az alapfrekvencia (Doppler nélküli, névleges) kézi módosítása."""
        with self.lock:
            s = self.sats.get(norad)
            if s:
                s.freq_hz = max(1e6, s.freq_hz + delta_hz)
                s.freq_desc, s.mode = "", ""          # már nem a listából való érték
                self._dirty = True

    def reset_offset(self, norad: int):
        with self.lock:
            s = self.sats.get(norad)
            if s:
                s.offset_hz = 0.0
                self.save()

    def commit_offset(self, norad: int):
        """A kézi eltolást beleolvasztja a mentett (névleges) frekvenciába."""
        with self.lock:
            s = self.sats.get(norad)
            if s:
                s.freq_hz += s.offset_hz
                s.offset_hz = 0.0
                self.save()

    def apply_settings(self, rig=None, tracking=None, station=None, time_=None, ui=None):
        with self.lock:
            if rig:
                self.cfg["rig"].update(rig)
            if tracking:
                tracking = dict(tracking)
                tracking.pop("enabled", None)
                self.cfg["tracking"].update(tracking)
            if station:
                self.cfg["station"].update(station)
            if time_:
                self.cfg["time"].update(time_)
            if ui:
                self.cfg["ui"].update(ui)
            self.apply_config()
            self.save()

    def refresh_tle(self, norad: int) -> str:
        """Hálózati hívás - háttérszálból hívd! Visszaad: a műhold neve."""
        name, l1, l2 = fetch_tle(norad)
        with self.lock:
            s = self.sats.get(norad)
            if s:
                s.tle1, s.tle2, s.tle_fetched = l1, l2, time.time()
                if not s.name and name:
                    s.name = name
                self._build_model(s)
                self.save()
        return name

    PASS_CACHE_S = 600.0

    def _pass_key(self, norad: int, hours: float):
        s, m = self.sats.get(norad), self.models.get(norad)
        st = self.cfg["station"]
        return (id(m), s.tle_fetched if s else None, st["lat"], st["lon"], st["alt_m"], hours)

    def cached_passes(self, norad: int, hours: float = 24.0):
        """A gyorsítótárban lévő (még friss) áthaladás-lista, vagy None. Gyors, bármelyik szálból hívható."""
        c = self._pcache.get(norad)
        if c is not None and c[0] == self._pass_key(norad, hours) and abs(self.now() - c[1]) < self.PASS_CACHE_S:
            return c[2]
        return None

    def compute_passes(self, norad: int, hours: float = 24.0, force: bool = False) -> list:
        """Egy műhold áthaladásai a következő `hours` órában. Az eredményt 10 percig megőrzi (közös a felület minden része
        között), így ugyanazt nem számoljuk újra meg újra. Számolós hívás - háttérszálból hívd!"""
        m = self.models.get(norad)
        if m is None:
            return []
        if not force:
            hit = self.cached_passes(norad, hours)
            if hit is not None:
                return hit
        key, now = self._pass_key(norad, hours), self.now()
        res = find_passes(m, self.observer, now, hours)
        self._pcache[norad] = (key, now, res)
        return res

    def next_suitable_pass(self, norad: int, hours: float = 24.0):
        """A következő (vagy éppen zajló) áthaladás, amelynek maximuma eléri a műhold minimum elevációját.
        None, ha a megadott időn belül nincs ilyen. Számolós hívás - háttérszálból hívd!"""
        s = self.sats.get(norad)
        if s is None:
            return None
        mn = self.peak_threshold(s)
        now = self.now()
        for p in self.compute_passes(norad, hours):
            if p.los > now and p.max_el >= mn and not self.is_skipped(norad, p.los):
                return p
        return None

    def measure_ntp(self) -> str:
        """Hálózati hívás - háttérszálból hívd!"""
        off, server = ntp_offset()
        with self.lock:
            self.ntp_offset = off
            self.ntp_info = f"{off:+.3f} s ({server})"
        return self.ntp_info

    def stop(self):
        self.stop_evt.set()

    # ---- fő ciklus ------------------------------------------------------
    def run(self):
        _win_timer(True)
        last_sel = 0.0
        next_t = time.perf_counter()
        try:
            while not self.stop_evt.is_set():
                try:
                    with self.lock:
                        now = self.now()
                        mono = time.monotonic()
                        if self._sel_now or mono - last_sel >= self.SEL_PERIOD:
                            self._sel_now = False
                            last_sel = mono
                            self._update_all(now)
                        self._doppler_step(now)
                        self._publish(now)
                        if self._dirty and mono - self._last_save > 5.0:
                            self.save()
                except Exception as e:      # a ciklus soha ne álljon le
                    msg = repr(e)
                    if msg != self._last_err[0] or time.monotonic() - self._last_err[1] > 30:
                        self._last_err = (msg, time.monotonic())
                        self._log(tl("log.internal_error", msg=msg))
                interval = max(1, min(1000, int(self.cfg["rig"]["interval_ms"]))) / 1000.0
                next_t += interval
                delay = next_t - time.perf_counter()
                if delay < 0:
                    next_t = time.perf_counter()
                    delay = 0
                if delay > 0:
                    self.stop_evt.wait(delay)
        finally:
            with self.lock:
                if self.recording:
                    self.rig.command(self.cfg["rig"]["los_cmd"])
                    self.recording = False
                if self._dirty:
                    self.save()
            self.rig.close()
            _win_timer(False)

    def _update_all(self, now: float):
        snap, cands, weak, skip = {}, {}, set(), set()
        self._prune_schedule(now)
        for n, s in self.sats.items():
            m = self.models.get(n)
            info = {"name": s.name or str(n), "enabled": s.enabled, "az": None, "el": None,
                    "rng": None, "rr": None, "status": "", "code": ""}
            if m is None:
                info["status"], info["code"] = tl("log.nincs_tle"), "no_tle"
            else:
                try:
                    o = observe(m, self.observer, now)
                    info.update(az=o.az, el=o.el, rng=o.rng, rr=o.rr)
                    if o.el > 0:
                        tr = self.tracks.get(n)
                        if s.enabled and (tr is None or now > tr["los"]):
                            self.tracks[n] = compute_track(m, self.observer, now)
                    else:
                        self.tracks.pop(n, None)
                    if s.enabled:
                        cands[n] = (o.el, self.eff_min_elev(s))
                        tk_ = self.tracks.get(n)
                        if tk_ is not None and tk_.get("peak", 99.0) < self.peak_threshold(s):
                            weak.add(n)
                        if tk_ is not None and self.is_skipped(n, tk_["los"]):
                            skip.add(n)
                except Exception as e:
                    info["status"], info["code"] = tl("log.szamitasi_hiba"), "error"
                    self._log(tl("log.szamitasi_hiba_p_e", p=s.name or n, e=e))
            if not s.enabled:
                info["status"], info["code"] = tl("log.kikapcsolva"), "disabled"
                self.tracks.pop(n, None)
            snap[n] = info
        for n in list(self.tracks):
            if n not in self.sats or self.tracks[n] is None:
                self.tracks.pop(n, None)
        self.tracks_pub = dict(self.tracks)

        if self.tracking_on and self.location_ok():
            if self.mode == "selected":
                # a kijelölt műholdat követjük folyamatosan (elevációtól függetlenül)
                p = self.pinned
                ok = p in self.sats and self.sats[p].enabled and p in self.models
                new = p if ok else None
                self.selector.reset()
            else:
                if self.mode == "auto":     # csak a megfelelően magas csúcsú áthaladások (a kézzel ütemezettek mindig mennek)
                    use = {n: v for n, v in cands.items() if (n not in weak or n == self.current) and n not in skip}
                else:
                    use = {n: v for n, v in cands.items() if self._sched_active(n, now)}
                new = self.selector.choose(use, now, float(self.cfg["tracking"]["switch_margin"]),
                                           float(self.cfg["tracking"]["min_dwell"]))
        else:
            self.selector.reset()
            new = None
        if new != self.current:
            self._switch(new, now)

        # tétlenül is tartsuk fenn / ellenőrizzük a kapcsolatot az SDR++-szal
        if self.current is None and time.monotonic() - self._last_ping > 3.0:
            self._last_ping = time.monotonic()
            self.rig.get_freq()

        for n, info in snap.items():
            if info["status"]:
                continue
            if n == self.current:
                info["code"] = "tracked"
                info["status"] = tl("log.kovetve") if (info["el"] or 0) >= 0 else tl("log.kovetve_horizont_alatt")
            elif info["el"] is not None and info["el"] > 0:
                mn = cands.get(n, (0, 0))[1]
                if n in skip and info["el"] >= mn:
                    info["code"], info["status"] = "visible_skipped", tl("log.lathato_kihagyva")
                elif n in weak and info["el"] >= mn:
                    info["code"], info["status"] = "visible_weak", tl("log.lathato_gyenge")
                else:
                    info["code"] = "visible" if info["el"] >= mn else "visible_low"
                    info["status"] = tl("log.lathato") if info["el"] >= mn else tl("log.lathato_tul_alacsony")
            else:
                info["status"], info["code"] = tl("log.horizont_alatt"), "below"
        self.sat_snap = snap

    def _switch(self, new, now: float):
        old = self.current
        rc = self.cfg["rig"]
        if self.recording:
            self.rig.command(rc["los_cmd"])
            self.recording = False
            self._log(tl("log.felvetel_leallitva_los"))
        self.current = new
        self.last_sent = None
        if new is None:
            if old is not None:
                self._log(tl("log.kovetes_vege_p", p=self.sats[old].name if old in self.sats else old))
            return
        s = self.sats[new]
        self._log(tl("log.kovetes_p_new_p2", p=s.name or new, new=new, p2=s.freq_hz / 1e6))
        self._doppler_step(now)

    def _want_record(self, s: SatEntry) -> bool:
        return bool(self.cfg["rig"].get("recorder_enabled")) and s.record

    def _doppler_step(self, now: float):
        n = self.current
        if n is None:
            self.live = {}
            return
        s, m = self.sats[n], self.models[n]
        o = observe(m, self.observer, now)
        shift = doppler_shift_hz(s.freq_hz, o.rr)
        f = s.freq_hz + shift + s.offset_hz
        fi = int(round(f))
        if fi != self.last_sent:
            if self.rig.set_freq(fi):
                self.last_sent = fi
        # felvétel: csak amíg a műhold a minimum elevációja fölött van
        rec_ok = self._want_record(s) and o.el >= self.eff_min_elev(s)
        if self.recording and not rec_ok:
            self.rig.command(self.cfg["rig"]["los_cmd"])
            self.recording = False
            self._log(tl("log.felvetel_leallitva_los"))
        elif self.last_sent is not None and not self.recording and rec_ok:
            if self.rig.command(self.cfg["rig"]["aos_cmd"]) is not None:
                self.recording = True
                self._log(tl("log.felvetel_inditva_aos"))
        self.live = {"norad": n, "freq": f, "shift": shift, "offset": s.offset_hz,
                     "az": o.az, "el": o.el, "rng": o.rng, "rr": o.rr}

    def _publish(self, now: float):
        rig_ok = self.rig.connected
        if rig_ok and self._rig_prev is not True:
            self._log(tl("log.rigctl_kapcsolodva"))
            self._rig_prev = True
        elif not rig_ok and self._rig_prev is not False and (self._rig_prev is True or self.rig.last_error):
            self._log(tl("log.rig_no_connection", err=self.rig.last_error))
            self._rig_prev = False
        self.snap = {"t": now, "tracking_on": self.tracking_on, "current": self.current,
                     "sats": self.sat_snap, "tracks": self.tracks_pub, "live": dict(self.live),
                     "rig_connected": rig_ok, "rig_error": self.rig.last_error,
                     "recording": self.recording, "location_ok": self.location_ok()}


# --------------------------------------------------------------------------
# Hálózati adatforrások: TLE (CelesTrak / SatNOGS) és frekvenciák (SatNOGS DB)
# --------------------------------------------------------------------------
def _get(url: str, params=None, timeout: float = 20.0):
    import requests
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def fetch_tle(norad: int):
    """(név, 1. sor, 2. sor)"""
    err = None
    try:
        t = _get("https://celestrak.org/NORAD/elements/gp.php",
                 {"CATNR": int(norad), "FORMAT": "TLE"}).text
        lines = [x.rstrip() for x in t.splitlines() if x.strip()]
        for i in range(len(lines) - 1):
            if lines[i].startswith("1 ") and lines[i + 1].startswith("2 "):
                name = lines[i - 1].strip() if i > 0 else ""
                return name, lines[i], lines[i + 1]
        err = tl("core.a_celestrak_nem_ismeri")
    except Exception as e:
        err = str(e)
    try:                                  # tartalék: SatNOGS
        data = _get("https://db.satnogs.org/api/tle/", {"norad_cat_id": int(norad), "format": "json"}).json()
        if isinstance(data, dict):
            data = data.get("results", [])
        if data:
            d = data[0]
            return (d.get("tle0") or "").lstrip("0 ").strip(), d["tle1"], d["tle2"]
    except Exception as e:
        err = f"{err}; SatNOGS: {e}"
    raise RuntimeError(tl("core.tle_failed", err=err))


def fetch_sat_info(norad: int) -> dict:
    try:
        data = _get("https://db.satnogs.org/api/satellites/",
                    {"norad_cat_id": int(norad), "format": "json"}).json()
        if isinstance(data, dict):
            data = data.get("results", [])
        return data[0] if data else {}
    except Exception:
        return {}


def fetch_transmitters(norad: int) -> list:
    data = _get("https://db.satnogs.org/api/transmitters/",
                {"satellite__norad_cat_id": int(norad), "format": "json"}).json()
    if isinstance(data, dict):
        data = data.get("results", [])
    out = []
    for d in data:
        dl = d.get("downlink_low")
        if not dl or d.get("status") == "invalid":
            continue
        out.append({
            "uuid": d.get("uuid", ""),
            "description": d.get("description") or "",
            "downlink_hz": float(dl),
            "downlink_high_hz": float(d["downlink_high"]) if d.get("downlink_high") else None,
            "uplink_hz": float(d["uplink_low"]) if d.get("uplink_low") else None,
            "mode": d.get("mode") or "",
            "baud": d.get("baud"),
            "type": d.get("type") or "",
            "alive": bool(d.get("alive", d.get("status") == "active")),
            "status": d.get("status") or "",
        })
    out.sort(key=lambda x: (not x["alive"], x["downlink_hz"]))
    return out


# --------------------------------------------------------------------------
# Idő: NTP mérés, Windows óraszinkron
# --------------------------------------------------------------------------
NTP_SERVERS = ["hu.pool.ntp.org", "pool.ntp.org", "time.windows.com", "time.google.com"]


def ntp_offset(servers=None, timeout: float = 3.0):
    """(eltérés mp, szerver). Eltérés = pontos idő - a gép órája."""
    last = None
    for host in servers or NTP_SERVERS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            pkt = b"\x1b" + 47 * b"\0"
            t0 = time.time()
            s.sendto(pkt, (host, 123))
            data, _ = s.recvfrom(512)
            t3 = time.time()
            s.close()
            w = struct.unpack("!12I", data[:48])
            delta = 2208988800
            t1 = w[8] - delta + w[9] / 2 ** 32
            t2 = w[10] - delta + w[11] / 2 ** 32
            return ((t1 - t0) + (t2 - t3)) / 2.0, host
        except Exception as e:
            last = e
    raise RuntimeError(tl("core.nem_erheto_el_ntp", last=last))


def windows_time_sync() -> bool:
    """Elindítja (rendszergazdai jóváhagyással) a Windows óraszinkront."""
    if sys.platform != "win32":
        return False
    inner = ('net start w32time & w32tm /config /manualpeerlist:"hu.pool.ntp.org,0x8 time.windows.com,0x8" '
             '/syncfromflags:manual /reliable:NO /update & w32tm /resync /force')
    ps = "Start-Process cmd -Verb RunAs -WindowStyle Hidden -ArgumentList '/c " + inner + "'"
    subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return True


# --------------------------------------------------------------------------
# Helyzet: Windows helyszolgáltatás, NMEA GPS, Maidenhead
# --------------------------------------------------------------------------
def windows_location(timeout: float = 30.0) -> dict:
    if sys.platform != "win32":
        raise RuntimeError(tl("core.ez_a_funkcio_csak"))
    script = r"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::High)
$null = $w.TryStart($false,[TimeSpan]::FromSeconds(10))
$end=(Get-Date).AddSeconds(15)
while($w.Position.Location.IsUnknown -and (Get-Date) -lt $end){Start-Sleep -Milliseconds 300}
$l=$w.Position.Location
if($l.IsUnknown){ 'UNKNOWN' } else {
 $ci=[cultureinfo]::InvariantCulture
 '{0};{1};{2};{3}' -f $l.Latitude.ToString($ci),$l.Longitude.ToString($ci),$l.Altitude.ToString($ci),$l.HorizontalAccuracy.ToString($ci) }
"""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                       text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = (r.stdout or "").strip().splitlines()
    out = out[-1] if out else ""
    if not out or out == "UNKNOWN" or ";" not in out:
        raise RuntimeError(tl("core.a_windows_nem_adott"))
    p = out.split(";")
    alt = float(p[2]) if p[2] not in ("NaN", "") else None
    return {"lat": float(p[0]), "lon": float(p[1]), "alt_m": alt, "acc_m": float(p[3])}


def _nmea_coord(val: str, hemi: str) -> float:
    dot = val.index(".")
    deg = float(val[:dot - 2])
    mins = float(val[dot - 2:])
    r = deg + mins / 60.0
    return -r if hemi in ("S", "W") else r


def parse_nmea_gga(line: str) -> Optional[dict]:
    line = line.strip()
    if not line.startswith("$") or "GGA" not in line[:6]:
        return None
    p = line.split("*")[0].split(",")
    if len(p) < 10 or not p[6] or int(p[6] or 0) == 0 or not p[2] or not p[4]:
        return None
    return {"lat": _nmea_coord(p[2], p[3]), "lon": _nmea_coord(p[4], p[5]),
            "alt_m": float(p[9]) if p[9] else None, "sats": int(p[7] or 0)}


def nmea_location(port: str, baud: int = 9600, timeout: float = 25.0) -> dict:
    import serial
    end = time.time() + timeout
    with serial.Serial(port, baud, timeout=1) as ser:
        while time.time() < end:
            raw = ser.readline().decode("ascii", "ignore")
            r = parse_nmea_gga(raw)
            if r:
                return r
    raise RuntimeError(tl("core.nincs_gps_fix_vagy"))


def grid_to_latlon(grid: str):
    g = grid.strip()
    if len(g) < 4 or len(g) % 2:
        raise ValueError(tl("core.a_maidenhead_lokator_4"))
    lon = -180 + (ord(g[0].upper()) - 65) * 20 + int(g[2]) * 2
    lat = -90 + (ord(g[1].upper()) - 65) * 10 + int(g[3])
    if len(g) >= 6:
        lon += (ord(g[4].upper()) - 65) * (5 / 60) + 2.5 / 60
        lat += (ord(g[5].upper()) - 65) * (2.5 / 60) + 1.25 / 60
    else:
        lon += 1.0
        lat += 0.5
    return lat, lon
