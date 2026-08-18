@echo off
REM build_windows.bat
REM Run this ON WINDOWS (not in this Linux sandbox) to produce LocalShare.exe.
REM Double-click it, or run it from a Command Prompt in this folder.

echo === Local Share - Windows build ===

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install it from https://python.org and re-run this script.
    pause
    exit /b 1
)

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip >nul
pip install -r requirements-build.txt

echo Building LocalShare.exe with PyInstaller...
pyinstaller localshare.spec --noconfirm

echo.
echo === Done ===
echo Your app is at: dist\LocalShare.exe
echo Copy that single file anywhere and double-click it to run - no Python needed on the target PC.
pause
