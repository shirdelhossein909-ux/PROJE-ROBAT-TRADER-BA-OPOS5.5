@echo off
rem Registers the watchdog in Windows Task Scheduler so it starts by itself
rem every time you log in to Windows (e.g. after the VPS restarts for updates).
rem The watchdog then starts the robot. Run this file ONCE (right click -> Run as administrator).
set "HERE=%~dp0"
schtasks /Create /TN "ZoneRobot_Watchdog" /TR "\"%HERE%start_watchdog.bat\"" /SC ONLOGON /RL HIGHEST /IT /F
if errorlevel 1 (
    echo.
    echo  [ERROR] Could not create the task. Right click this file and choose "Run as administrator".
) else (
    echo.
    echo  [OK] Done. From now on the watchdog (and through it the robot) starts after every Windows login.
    echo  To remove it later:  schtasks /Delete /TN "ZoneRobot_Watchdog" /F
)
pause
