@echo off
echo.
echo  ============================================
echo   PathMaker Setup Wizard
echo   AI-Powered CNC CAM for Fusion 360
echo  ============================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERROR: Python is not installed!
    echo.
    echo  Please download Python from:
    echo  https://www.python.org/downloads/
    echo.
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo  Starting setup wizard...
python setup_wizard.py
