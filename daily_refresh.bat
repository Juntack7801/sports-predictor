@echo off
cd /d "%~dp0"

echo ============================================
echo  Refreshing MLB...
echo ============================================
python collectors\mlb_collector.py
python collectors\mlb_team_stats_collector.py --season 2026

echo ============================================
echo  Refreshing KBO...
echo ============================================
python collectors\kbo_collector.py
python collectors\kbo_team_stats_collector.py --season 2026

echo ============================================
echo  Refreshing NPB...
echo ============================================
python collectors\npb_collector.py
python collectors\npb_team_stats_collector.py --season 2026

echo ============================================
echo  Fetching real over/under lines from Betman...
echo ============================================
python collectors\betman_odds_collector.py

echo ============================================
echo  Calculating predictions...
echo ============================================
python run_predictions.py --season 2026

echo ============================================
echo  Updating yesterday final scores...
echo ============================================
python update_yesterday_results.py

echo ============================================
echo  Checking yesterday's results...
echo ============================================
python check_accuracy.py

echo.
echo ============================================
echo   COMPLETE - all data collection finished
echo ============================================
echo.
pause
