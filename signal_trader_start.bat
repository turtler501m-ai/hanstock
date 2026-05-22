@echo off
REM Signal Trader Background Launcher
REM 백그라운드에서 계속 실행

cd /d "%~dp0"

echo Starting Signal Trader...
echo This window will close. Check .runtime/signal_trader.log for output.

start /b python signal_trader.py >> .runtime/signal_trader.log 2>&1

echo Done! Signal Trader is running in background.