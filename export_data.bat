@echo off
chcp 65001 >nul
title Export MetaTrader data for backtest
cd /d "%~dp0"
echo ================================================
echo  [DATA] Running export_data.py ...
echo  (MetaTrader 5 must be open and logged in)
echo ================================================
echo.
python export_data.py
echo.
echo ================================================
echo  [DATA] Finished.
echo ================================================
pause
