<p align="center">
  <img src="assets/logo.png" width="160" alt="Orbiq logo">
</p>

<h1 align="center">Orbiq</h1>

**Műholdkövető program Doppler-korrekcióval, SDR++ vezérléssel** (Windows, grafikus felület, parancssor nélkül).

*English: see [README.md](README.md).*

## Első indítás
**A) lehetőség – `Orbiq.exe` (a legegyszerűbb, nem kell semmit telepíteni).**
Töltsd le az `Orbiq.exe`-t a [Releases](https://github.com/baranyairoland/orbiq/releases) oldalról, és tedd egy saját mappába (pl. `C:\Radio\Orbiq`) – az adataid mellé mentődnek.

> A Windows *„A Windows megvédte a számítógépét”* üzenetet (SmartScreen) mutathat: kattints a **További információ → Futtatás mindenképp** gombra.
> Egyes víruskeresők téves riasztást is adhatnak (jellemzően `Trojan:Script/Sabsik.FL.A!ml`), mert az EXE aláíratlan és PyInstallerrel készült. Az EXE-t a GitHub építi automatikusan a tárolóban lévő nyilvános forráskódból (lásd *Actions*). Ha blokkolja, engedélyezd a *Windows Biztonság → Védelmi előzmények* részen, vagy használd a B) lehetőséget.

**B) lehetőség – futtatás forrásból.**
1. Telepítsd a **Python 3.13-at (64 bites)** a [python.org/downloads/windows](https://www.python.org/downloads/windows/) oldalról: válaszd a *Windows installer (64-bit)* fájlt, és az első képernyőn pipáld be az **Add python.exe to PATH** opciót.
2. Töltsd le a tárolót (*Code → Download ZIP*), és csomagold ki (pl. `C:\Radio\Orbiq`).
3. Dupla kattintás: **`START.bat`** – az első alkalommal telepíti a hozzá kellő csomagokat (internet kell, lassú lehet), utána elindul a program.

**Utána, mindkét esetben:**
1. **Beállítások** fül: írd be az állomásod szélesség/hosszúság koordinátáját (tizedfokban, pl. `47.123456` / `17.123456`), a **📍** gombbal ellenőrizheted Google Térképen, majd **Alkalmaz és mentés**.
2. SDR++-ban: *Module Manager* → `rigctl_server` hozzáadása → port `4532` → *Start*. A Beállítások fülön a **Kapcsolat tesztelése** gombbal ellenőrizheted.
3. **Követés** fül → **Műhold hozzáadása**: NORAD ID (pl. `25544`), Keresés, válaszd ki a frekvenciát, Mentés.

Az EXE-t magad is elkészítheted a **`BUILD_EXE.bat`**-tal (eredmény: `dist\Orbiq.exe`).

## Az adataid és a biztonsági mentés
Minden adatod (műholdlista, frekvenciák, állomás helyzete, ütemezés, TLE-k) a program mellett, a **`data`** mappában
van (`data\config.json`). A mappa másolásával az egészet költöztetheted vagy elmentheted. A program biztonságosan ír
(ideiglenes fájl + az előző ép példány megőrzése), induláskor és 6 óránként automatikus mentést készít (a legutolsó 40
marad meg a `data\backups` mappában), és ha a beállításfájl valaha megsérül (például Windows-összeomlás után), magától
visszaáll az utolsó ép mentésre. A **Beállítások → Adatok és biztonsági mentés** részen van kézi mentés, mentés fájlba
és visszaállítás gomb. A régebbi változat adatait (`%APPDATA%\Orbiq`) az első indításkor automatikusan átveszi.


## Kapcsolat
- Telegram-csoport: **[Orbiq Sat Tracker](https://t.me/orbiq_tracker)** – kérdések, hibák, ötletek
- E-mail: **orbiq_tracker@icloud.com**

Hibánál kérlek írd meg az Orbiq verzióját (az ablak címsorában látszik), és csatolj képernyőképet.

## Licenc
MIT – lásd a [LICENSE](LICENSE) fájlt. Ez egy béta verzió; a visszajelzéseket nagyon szívesen várom.
