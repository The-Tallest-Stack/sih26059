@echo off
title Refreshing Antarctic forecast
echo ===================================================
echo  Refreshing 10-day forecast (sea ice, currents,
echo  waves, wind). Takes about 5-10 minutes.
echo ===================================================

cd /d "%~dp0backend"
set PYTHONPATH=src
set PYTHONWARNINGS=ignore
.\.venv\Scripts\python.exe -u src\antarctic_dss\data\sync_forecasts.py
if errorlevel 1 (
    echo.
    echo Forecast refresh FAILED - see the messages above.
    echo The previous forecast is still in place and the app will keep using it.
    pause
    exit /b 1
)

echo.
echo Forecast refreshed. Restart the backend to be safe; this window closes in 5 seconds...
timeout /t 5 >nul
exit
