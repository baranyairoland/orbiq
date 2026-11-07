@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Orbiq

where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python is not installed on this computer. / A Python nincs telepítve ezen a gépen.
  echo 1. On the page that opens, download "Python 3.13" - "Windows installer (64-bit)".
  echo    A megnyíló oldalon töltsd le: "Python 3.13" - "Windows installer (64-bit)".
  echo 2. On the first screen of the installer tick "Add python.exe to PATH", then click Install Now.
  echo    A telepítő első képernyőjén pipáld be: "Add python.exe to PATH", majd Install Now.
  echo 3. Close this window and run START.bat again. / Zárd be ezt az ablakot, és futtasd újra a START.bat-ot.
  echo.
  echo Tip: no Python needed if you use Orbiq.exe from the Releases page on GitHub.
  echo Tipp: Python nélkül is megy az Orbiq.exe a GitHub Releases oldaláról.
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

where pyw >nul 2>nul
if errorlevel 1 (
  py orbiq.py
  if errorlevel 1 pause
) else (
  start "" pyw orbiq.py
)
