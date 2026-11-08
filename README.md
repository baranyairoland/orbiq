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

## Installation (Windows)
Orbiq runs as a Python program; there is no separate installer. The steps below take a few minutes.

### Step 1 – install Python (once)
1. Open [python.org/downloads/windows](https://www.python.org/downloads/windows/).
2. Find the latest **Python 3.13** release and download the **"Windows installer (64-bit)"** file. (Not the "embeddable package" and not the 32-bit installer.)
3. Run the downloaded file. **On the very first screen, before installing:**
   - **Tick the "Add python.exe to PATH" box at the bottom.** This is the most important step! Without it START.bat cannot find Python.
   - Leave "Use admin privileges when installing py.exe" (if shown) at its default.
   - Then click **"Install Now"** (you do not need "Customize installation").
4. If Windows asks "Do you want to allow this app to make changes?", answer **Yes**.
5. On the "Setup was successful" screen click **Close**. (If you see "Disable path length limit", you may click it too, but it is not required.)

### Step 2 – download Orbiq
1. On the GitHub page click the green **Code** button, then **Download ZIP**.
2. **Extract** the ZIP into a folder of your own, e.g. `C:\Radio\Orbiq`. Extracting is mandatory: run the program from the extracted folder, not from inside the ZIP.
3. Your data (satellite list, settings) is saved next to the program in the `data` folder.

### Step 3 – start it
1. Open the extracted folder and double-click **`START.bat`**.
2. On the first start a black window appears and downloads the required packages. Internet is needed and it can take a minute or two. Yellow *WARNING* lines are usually harmless – just wait.
3. Then the Orbiq window opens. Later starts are fast.
4. If START.bat says Python is not installed although you installed it, either the **Add python.exe to PATH** tick was missed (run the Python installer again, choose **Modify**, then *Add Python to environment variables*) or you did not close and reopen START.bat after the installation.

To update later you do not have to download the ZIP again: use **Settings → Update → Check for updates** to update in one step.

### Then
1. In SDR++: add the **rigctl_server** module, port `4532`, press *Start*.
2. In Orbiq: *Settings* → enter your position → *Apply and save*, then *Add satellite*.

If you want a standalone `.exe`, you can build one yourself from the source with **`BUILD_EXE.bat`** (result: `dist\Orbiq.exe`).

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
