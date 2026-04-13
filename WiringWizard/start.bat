@echo off
setlocal EnableDelayedExpansion
echo.
echo  ============================================
echo   WiringWizard
echo   Wiring Diagram and Harness Planner
echo  ============================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM -- Prefer the standalone executable when present --
if exist "%SCRIPT_DIR%WiringWizard.exe" (
    echo  Starting WiringWizard - standalone exe...
    start "" "%SCRIPT_DIR%WiringWizard.exe"
    exit /b 0
)

REM -- Fall back through Python interpreters in priority order --
REM pythonw - GUI mode, no console window (best UX)
where pythonw >nul 2>&1
if !errorlevel! equ 0 (
    echo  Starting WiringWizard - GUI mode via pythonw...
    start "" pythonw "%SCRIPT_DIR%WiringWizard.py"
    exit /b 0
)

REM pyw - Python launcher for Windows, windowless mode
where pyw >nul 2>&1
if !errorlevel! equ 0 (
    echo  Starting WiringWizard - GUI mode via pyw...
    start "" pyw "%SCRIPT_DIR%WiringWizard.py"
    exit /b 0
)

REM python - standard interpreter (console window visible)
where python >nul 2>&1
if !errorlevel! equ 0 (
    echo  Starting WiringWizard - via python...
    start "" python "%SCRIPT_DIR%WiringWizard.py"
    exit /b 0
)

REM py - Python launcher for Windows, console mode fallback
where py >nul 2>&1
if !errorlevel! equ 0 (
    echo  Starting WiringWizard - via py launcher...
    start "" py "%SCRIPT_DIR%WiringWizard.py"
    exit /b 0
)

echo  ERROR: Neither WiringWizard.exe nor Python was found!
echo.
echo  Option A - Download the standalone exe from GitHub Releases:
echo  https://github.com/mikejsmith1985/MakerTools/releases
echo.
echo  Option B - Install Python from:
echo  https://www.python.org/downloads/
echo  Make sure to check "Add Python to PATH" during install.
echo.
pause
exit /b 1
