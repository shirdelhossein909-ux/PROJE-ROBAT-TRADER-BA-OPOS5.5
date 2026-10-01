@echo off
rem Stops the robot on purpose: the watchdog will NOT start it again
rem until you run start_robot.bat yourself.
set "HERE=%~dp0"
cd /d "%HERE%"
if not exist "%HERE%logs" mkdir "%HERE%logs"
echo stopped> "%HERE%logs\robot_stopped.flag"
set "PID="
if exist "%HERE%logs\robot.pid" set /p PID=<"%HERE%logs\robot.pid"
if defined PID (
    taskkill /PID %PID% /F >nul 2>&1
    echo  [ROBOT] Robot process %PID% stopped.
) else (
    echo  [ROBOT] No running robot found.
)
echo  Orders and positions stay in MetaTrader (SL/TP are on the broker server).
echo  The watchdog will not restart it. To start again: start_robot.bat
pause
