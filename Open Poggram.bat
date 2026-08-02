@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

title Poggram

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo.
    echo Run these commands first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%a in ('tasklist /fi "imagename eq python.exe" /fi "windowtitle eq Poggram*" 2^>nul ^| findstr /i "python.exe"') do (
    echo [WARNING] Another instance may already be running.
    echo If the app doesn't open, close existing python.exe processes first.
    echo.
)

echo Starting Poggram...
echo.

.venv\Scripts\python.exe app.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] App exited with code %errorlevel%.
    echo Check the output above for details.
)

echo.
pause
