@echo off
cd /d "%~dp0"
set "HOST=127.0.0.1"
set "PORT=8080"
py -3.13 app.py
if errorlevel 1 python app.py
pause
