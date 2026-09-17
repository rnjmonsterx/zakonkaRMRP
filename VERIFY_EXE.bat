@echo off
setlocal
cd /d "%~dp0"
if not exist "dist\LegalDesk.exe" exit /b 1
"dist\LegalDesk.exe" --smoke-test
if errorlevel 1 exit /b 1
echo Frozen EXE smoke test OK.
exit /b 0
