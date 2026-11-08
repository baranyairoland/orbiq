@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Orbiq - build EXE
echo Builds a single Orbiq.exe into the dist folder (may take a few minutes).
echo Egyetlen Orbiq.exe fájlt készít a dist mappába (eltarthat pár percig).
py -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller
if errorlevel 1 ( echo Install error / Telepítési hiba. & pause & exit /b 1 )
py -m PyInstaller --noconfirm --onefile --windowed --name Orbiq --collect-all sgp4 --icon assets\logo.ico --add-data "lang;lang" --add-data "assets;assets" orbiq.py
if errorlevel 1 ( echo Build failed / Az EXE készítése nem sikerült. & pause & exit /b 1 )
echo.
echo Done / Kész: %~dp0dist\Orbiq.exe
pause
