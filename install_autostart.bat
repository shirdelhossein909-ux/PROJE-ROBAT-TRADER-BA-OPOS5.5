@echo off
rem Registers the watchdog in Windows Task Scheduler (run this file ONCE as administrator):
rem   - starts at every Windows login (e.g. after the VPS restarts for updates)
rem   - checked every 5 minutes: if the watchdog was closed, it is started again
rem   - runs without a window, so it cannot be closed by mistake
rem The watchdog then keeps the robot running and reports every stop (and its reason) to Bale.
set "HERE=%~dp0"
cd /d "%HERE%"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set WATCHDOG_FROM_BAT=1
python "%HERE%watchdog.py" --install
pause
