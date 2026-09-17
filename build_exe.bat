@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py >nul 2>nul || (echo Python launcher ^(py^) not found.& exit /b 1)
py -3 -m pip install --upgrade pyinstaller
if errorlevel 1 exit /b 1
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name "LegalDesk" --add-data "data;data" --add-data "assets;assets" main.py
if errorlevel 1 exit /b 1
echo Build OK: dist\LegalDesk.exe
exit /b 0
