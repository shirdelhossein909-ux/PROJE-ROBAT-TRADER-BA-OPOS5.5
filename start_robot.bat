@echo off
rem Resolve this folder BEFORE changing the code page (non-English folder names break otherwise)
set "HERE=%~dp0"
cd /d "%HERE%"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title Zone Trading Robot
:loop
echo ================================================
echo  [ROBOT] Starting live_trader.py ...
echo  (Stop: press Ctrl+C, or run stop_robot.bat)
echo ================================================
python "%HERE%live_trader.py"
rem Exit code 3 = stopped on purpose (Ctrl+C, another robot already running,
rem real account, basket mismatch). Do not restart in that case.
if errorlevel 3 if not errorlevel 4 goto stopped
rem stop_robot.bat leaves this flag: stopped on purpose, do not restart
if exist "%HERE%logs\robot_stopped.flag" goto stopped
echo.
echo  [ROBOT] Stopped or crashed! Restarting in 10 seconds...
timeout /t 10
goto loop
:stopped
echo.
echo  [ROBOT] Stopped on purpose - not restarting. Read the messages above.
pause
