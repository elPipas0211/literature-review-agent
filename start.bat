@echo off
:: start.bat — bootstrap if needed, then start backend (:8000) and frontend (:5173)
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Literature Review Agent

set "ROOT=%~dp0"
cd /d "%ROOT%"

set BACKEND_PORT=8000
set FRONTEND_PORT=5173

if not exist ".logs" mkdir .logs

:: ── Prerequisites check ─────────────────────────────────────────────────────────
where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not found.
    echo         Install Miniconda from: https://docs.conda.io/en/latest/miniconda.html
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install v18+ from: https://nodejs.org
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js v18+ from: https://nodejs.org
    exit /b 1
)

:: ── Bootstrap conda environment ─────────────────────────────────────────────────
conda env list | findstr /B /C:"litreview " >nul 2>&1
if errorlevel 1 (
    echo Creating litreview conda environment (this may take several minutes^)...
    call conda env create -f environment.yml
    if errorlevel 1 (
        echo [ERROR] Failed to create the conda environment.
        exit /b 1
    )
    echo [OK] Conda environment 'litreview' ready.
) else (
    echo [OK] Conda environment 'litreview' already exists.
)

:: ── Bootstrap frontend dependencies ────────────────────────────────────────────
if not exist "%ROOT%frontend\node_modules" (
    echo Installing frontend dependencies...
    cd "%ROOT%frontend"
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        exit /b 1
    )
    cd /d "%ROOT%"
    echo [OK] Frontend dependencies installed.
)

:: ── Kill any existing processes on these ports ─────────────────────────────────
echo Checking for existing processes...
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr /R " 0\.0\.0\.0:%BACKEND_PORT% \|127\.0\.0\.1:%BACKEND_PORT% "') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr /R " 0\.0\.0\.0:%FRONTEND_PORT% \|127\.0\.0\.1:%FRONTEND_PORT% "') do (
    taskkill /F /PID %%p >nul 2>&1
)

:: ── Start backend in a new console window ─────────────────────────────────────
echo Starting backend on port %BACKEND_PORT%...
start "LRA-Backend" /D "%ROOT%" cmd /k "conda activate litreview && uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT%"

:: ── Start frontend in a new console window ────────────────────────────────────
if not exist "%SCRIPT_DIR%\frontend\node_modules" (
    echo Installing frontend dependencies...
    cd "%SCRIPT_DIR%\frontend"
    npm install
)

:: ── Wait for servers to initialise ────────────────────────────────────────────
timeout /t 4 /nobreak >nul

echo.
echo =============================================
echo   Literature Review Agent is running
echo =============================================
echo   Frontend  ^>  http://localhost:%FRONTEND_PORT%
echo   API docs  ^>  http://localhost:%BACKEND_PORT%/docs
echo =============================================
echo.
echo Two windows opened: LRA-Backend and LRA-Frontend.
echo Run stop.bat to stop both servers.
echo.
endlocal
