@echo off
echo.
echo  ============================================
echo   TextureForge Setup Wizard
echo   Surface Texture Stamping for Fusion 360
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

echo  Starting setup wizard...
python setup_wizard.py
