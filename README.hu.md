# Orbiq

**Műholdkövető program Doppler-korrekcióval, SDR++ vezérléssel** (Windows, grafikus felület, parancssor nélkül).

*English: see [README.md](README.md).*

## Első indítás
1. Csomagold ki a mappát valahová (pl. `C:\Radio\Orbiq`).
2. Dupla kattintás: **`START.bat`**
   - Az első alkalommal telepíti a hozzá kellő csomagokat (internet kell), utána elindul a program.
   - Ha nincs Python: a fájl megnyitja a letöltő oldalt. Telepítéskor pipáld be az *Add python.exe to PATH*
     opciót, majd futtasd újra a `START.bat`-ot.
3. **Beállítások** fül: írd be az állomásod szélesség/hosszúság koordinátáját (tizedfokban, pl. `47.123456` /
   `17.123456`), a **📍** gombbal ellenőrizheted Google Térképen, majd **Alkalmaz és mentés**.
4. SDR++-ban: *Module Manager* → `rigctl_server` hozzáadása → port `4532` → *Start*.
   A Beállítások fülön a **Kapcsolat tesztelése** gombbal ellenőrizheted.
5. **Követés** fül → **Műhold hozzáadása**: NORAD ID (pl. `25544`), Keresés, válaszd ki a frekvenciát, Mentés.

Egyetlen EXE-t szeretnél? Futtasd a **`BUILD_EXE.bat`**-ot, az eredmény: `dist\Orbiq.exe`.

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
