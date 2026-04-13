@echo off
setlocal
echo.
echo  ============================================
echo   WiringWizard
echo   Wiring Diagram and Harness Planner
echo  ============================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    echo  Starting WiringWizard (GUI mode)...
    start "" pythonw "%SCRIPT_DIR%WiringWizard.py"
    exit /b 0
)

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

echo  Starting WiringWizard...
start "" python "%SCRIPT_DIR%WiringWizard.py"
