@echo off
:: install.bat — set up the Literature Review Agent (Windows)
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Literature Review Agent - Install

echo.
echo =========================================
echo   Literature Review Agent -- Install
echo =========================================
echo.

:: ── Check conda ────────────────────────────────────────────────────────────────
where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not found.
    echo         Install Miniconda from: https://docs.conda.io/en/latest/miniconda.html
    echo         Then reopen this terminal and run install.bat again.
    exit /b 1
)
echo [OK] conda found.

:: ── Check Node.js ──────────────────────────────────────────────────────────────
where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found.
    echo         Install v18+ from: https://nodejs.org
    exit /b 1
)
echo [OK] Node.js found.

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js v18+.
    exit /b 1
)
echo [OK] npm found.
echo.

:: ── Conda environment ──────────────────────────────────────────────────────────
conda env list | findstr /B /C:"litreview " >nul 2>&1
if errorlevel 1 (
    echo Creating litreview conda environment (this may take several minutes)...
    call conda env create -f environment.yml
) else (
    echo Updating litreview conda environment...
    call conda env update -n litreview -f environment.yml --prune
)
if errorlevel 1 (
    echo [ERROR] Failed to create/update the conda environment.
    exit /b 1
)
echo [OK] Conda environment 'litreview' ready.
echo.

:: ── Frontend dependencies ──────────────────────────────────────────────────────
echo Installing frontend dependencies...
cd frontend
call npm install
cd ..
if errorlevel 1 (
    echo [ERROR] npm install failed.
    exit /b 1
)
echo [OK] Frontend dependencies installed.

echo.
echo =========================================
echo   Installation complete!
echo   Run start.bat to launch the app.
echo =========================================
echo.
endlocal
