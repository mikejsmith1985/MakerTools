@echo off
echo.
echo  ============================================
echo   MisterWizard
echo   Mist Coolant Setup for Onefinity CNC
echo  ============================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python is not installed!
    echo.
    echo  Please download Python from:
    echo  https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo  Starting MisterWizard...
python MisterWizard.py
