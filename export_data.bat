@echo off
rem Resolve this folder BEFORE changing the code page: with a non-English folder
rem name, reading %~dp0 after "chcp 65001" can return a broken path.
set "HERE=%~dp0"
set "SCRIPT=%~dp0export_data.py"
pushd "%HERE%"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set EXPORT_FROM_BAT=1
title Export MetaTrader data for backtest
echo ================================================
echo  [DATA] Running export_data.py ...
echo  (MetaTrader 5 must be open and logged in)
echo ================================================
echo.
if not exist "%SCRIPT%" (
    echo  [ERROR] export_data.py was not found next to this .bat file.
    echo  Looking for: "%SCRIPT%"
    echo  Files in this folder:
    dir /b "%HERE%"
    goto end
)
python "%SCRIPT%"
:end
echo.
echo ================================================
echo  [DATA] Finished.
echo ================================================
popd
pause
