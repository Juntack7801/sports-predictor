@echo off
cd /d "%~dp0"

echo Registering a daily task that runs daily_refresh.bat at 8:00 AM...
schtasks /create /tn "SportsPredictorDailyRefresh" /tr "\"%~dp0daily_refresh.bat\"" /sc daily /st 08:00 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Done. It will run automatically every day at 8:00 AM.
    echo You can change the time in Windows "Task Scheduler" app - look for "SportsPredictorDailyRefresh".
) else (
    echo.
    echo Something went wrong. Try running this file as Administrator (right-click - Run as administrator).
)

pause
