@echo off
cd /d "%~dp0"

echo Starting server...
start "sports-predictor-server" python -m uvicorn api.server:app --host 0.0.0.0 --port 8000

timeout /t 2 /nobreak > NUL

echo Opening screen...
start "" "web\index.html"

echo.
echo Done. Keep the new window open (server runs there). Do not close it.
pause
