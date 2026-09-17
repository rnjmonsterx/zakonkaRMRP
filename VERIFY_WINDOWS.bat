@echo off
setlocal
cd /d "%~dp0"
py -3 windows_smoke_test.py
exit /b %errorlevel%
