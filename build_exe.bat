@echo off
title Build Retirement Planner EXE
echo.
echo ======================================================
echo   Build Retirement Planner — Windows Standalone EXE
echo ======================================================
echo.

where python >nul 2>&1
if %errorlevel% == 0 (set PYTHON=python) else (set PYTHON=python3)

echo   Installing PyInstaller...
%PYTHON% -m pip install pyinstaller --quiet

echo   Building RetirementPlanner.exe...
%PYTHON% -m PyInstaller RetirementPlanner.spec --noconfirm

if exist dist\RetirementPlanner.exe (
    copy /Y dist\RetirementPlanner.exe RetirementPlanner.exe
    echo.
    echo ======================================================
    echo   SUCCESS! RetirementPlanner.exe is ready.
    echo   Share this single file with anyone on Windows.
    echo ======================================================
) else (
    echo   ERROR: Build failed. See output above.
)
echo.
pause
