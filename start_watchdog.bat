@echo off
set "HERE=%~dp0"
cd /d "%HERE%"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Robot Watchdog
:loop
python "%HERE%watchdog.py"
if errorlevel 3 if not errorlevel 4 goto stopped
echo  [WATCHDOG] Stopped - restarting in 30 seconds...
timeout /t 30
goto loop
:stopped
echo  [WATCHDOG] Another watchdog is already running - this one is closing.
timeout /t 10
