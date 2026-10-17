@echo off
title Delta Exchange Trading Bot [LIVE MODE]
echo WARNING: YOU ARE STARTING LIVE TRADING MODE. REAL CAPITAL IS AT RISK.
set /p confirm=Type YES to continue: 
if /I not "%confirm%"=="YES" (
    echo Live trading cancelled.
    pause
    exit /b
)
python run_trader.py
pause
