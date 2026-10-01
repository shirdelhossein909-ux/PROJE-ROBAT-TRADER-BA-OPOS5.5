@echo off
rem Measures the real spread of each symbol from MetaTrader tick history (no candle download)
rem and writes spreads.csv next to the backtest data (Desktop\0).
set "HERE=%~dp0"
set "SCRIPT=%~dp0export_data.py"
pushd "%HERE%"
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set EXPORT_FROM_BAT=1
title Measure MetaTrader spreads for backtest
echo ================================================
echo  [SPREAD] Measuring real spreads ...
echo  (MetaTrader 5 must be open and logged in)
echo ================================================
echo.
if not exist "%SCRIPT%" (
    echo  [ERROR] export_data.py was not found next to this .bat file.
    echo  Looking for: "%SCRIPT%"
    goto end
)
python "%SCRIPT%" --spreads
:end
echo.
echo ================================================
echo  [SPREAD] Finished.
echo ================================================
popd
pause
