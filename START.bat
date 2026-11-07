@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Orbiq

where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python is not installed on this computer. / A Python nincs telepítve ezen a gépen.
  echo 1. Download / Töltsd le: https://www.python.org/downloads/windows/
  echo 2. During setup tick "Add python.exe to PATH" and "tcl/tk and IDLE".
  echo    Telepítéskor pipáld be: "Add python.exe to PATH" és "tcl/tk and IDLE".
  echo 3. Then run this file again. / Utána futtasd újra ezt a fájlt.
  echo.
  start https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

echo Checking required packages (slow only the first time)... / Szükséges csomagok ellenőrzése (csak először tart sokáig)...
py -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo Package installation failed. Is there an internet connection? / A csomagok telepítése nem sikerült. Van internet?
  pause
  exit /b 1
)

start "" pyw orbiq.py
