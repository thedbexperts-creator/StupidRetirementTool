@echo off
title Retirement Planner
echo.
echo ======================================================
echo   Retirement Planner
echo   Starting server...
echo ======================================================
echo.

:: Try 'python' first, then 'python3'
where python >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=python
    goto found
)
where python3 >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=python3
    goto found
)

echo   ERROR: Python is not installed or not on your PATH.
echo.
echo   Please install Python from https://www.python.org/downloads/
echo   Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found
echo   Found: %PYTHON%
echo.
echo   Your browser will open at http://localhost:5000
echo   Close this window (or press Ctrl+C) to stop the app.
echo.

start "" http://localhost:5000
%PYTHON% app.py
pause
