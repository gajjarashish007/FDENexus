@echo off
echo ========================================
echo   SmartOps Portal - Self-Service Platform
echo ========================================
echo.

echo [1/3] Installing dependencies...
pip install -r requirements.txt -q

echo [2/3] Starting Backend API + WebSocket...
start "SmartOps Portal API" cmd /k python backend-api.py

timeout /t 4 /nobreak >nul

echo [3/3] Opening Portal...
start http://localhost:5000

echo.
echo ========================================
echo   SmartOps Portal Ready!
echo ========================================
echo   Backend API:  http://localhost:5000
echo   WebSocket:    ws://localhost:5000
echo   SmartOps Portal: http://localhost:5000
echo   AWS Setup:    Run "aws configure" before first use
echo   User Guide:   Open portal - Help - "Deploy to AWS"
echo ========================================
echo.
pause
