<p align="center">
  <img src="assets/logo.png" width="160" alt="Orbiq logo">
</p>

<h1 align="center">Orbiq</h1>

**Satellite pass follower with Doppler correction for SDR++** (Windows, graphical, no command line).

Orbiq follows amateur-radio and weather satellites for you: it predicts passes, calculates the
Doppler-shifted frequency in real time and sends it to **SDR++** through its *Rigctl Server*.
It can also start and stop the SDR++ recorder at AOS / LOS.

*Magyarul: lásd [README.hu.md](README.hu.md).*

## Features
- Add satellites by **NORAD ID**; transmitter frequencies are fetched from the SatNOGS database
- Live Doppler-corrected receive frequency + separately editable base frequency (SDR++-style digits)
- 24-hour pass list with maximum elevation, sky plot with the predicted path of any selected pass
- Three modes: follow the selected satellite / automatic switching by elevation rules / follow only chosen passes
- Minimum elevation, switching margin and minimum dwell time are configurable
- AOS / LOS commands for the SDR++ recorder, update interval 1–1000 ms
- Time sync (NTP offset, optional Windows clock sync); precise station position (decimal degrees, Windows location, USB GPS) with a Google Maps check button

## Quick start
1. Install Python 3 for Windows (tick *Add Python to PATH*).
2. Run `START.bat` – it installs the needed packages and starts the program.
3. In SDR++: add the **rigctl_server** module, port `4532`, press *Start*.
4. In Orbiq: *Settings* → enter your position → *Apply and save*, then *Add satellite*.

A single `Orbiq.exe` can be built with `BUILD_EXE.bat`.

## Status
Early development. Tested on live passes with SDR++ (UmKA-1). Feedback and bug reports are welcome.

## Languages
The interface text lives in `lang/<code>.json` (currently English and Hungarian; the language follows your Windows language the first time and can be changed in *Settings → Appearance*). To add a language, copy `lang/en.json` to
`lang/<code>.json`, translate the values and set `_meta.name` to the language's own name; it then shows up in
*Settings → Appearance*. Keys and `{placeholders}` must stay unchanged.

## Your data and backups
All your data (satellite list, frequencies, station position, schedule, TLEs) is stored next to the program in the
`data` folder (`data/config.json`). Copy that folder to move or back up everything. The program writes safely
(temporary file + previous good copy), creates an automatic backup at start-up and every 6 hours (the last 40 are kept
in `data/backups`) and, if the settings file is ever damaged (e.g. after a Windows crash), restores the newest good
backup by itself. *Settings → Data and backup* has buttons for a manual backup, export to a file, and restore.
Settings from older versions (`%APPDATA%\Orbiq`) are taken over automatically on first start.


## Contact
- Telegram group: **[Orbiq Sat Tracker](https://t.me/orbiq_tracker)** – questions, bugs, ideas
- E-mail: **orbiq_tracker@icloud.com**

When reporting a bug, please include the Orbiq version (shown in the window title) and a screenshot.

## License
MIT – see [LICENSE](LICENSE). This is a beta version; feedback is very welcome.
