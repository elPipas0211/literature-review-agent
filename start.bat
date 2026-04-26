@echo off
:: start.bat — start backend (uvicorn :8000) and frontend (Vite :5173)
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Literature Review Agent

set "ROOT=%~dp0"
cd /d "%ROOT%"

set BACKEND_PORT=8000
set FRONTEND_PORT=5173

if not exist ".logs" mkdir .logs

:: ── Kill any existing processes on these ports ─────────────────────────────────
echo Checking for existing processes...
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr /R " 0\.0\.0\.0:%BACKEND_PORT% \|127\.0\.0\.1:%BACKEND_PORT% "') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr /R " 0\.0\.0\.0:%FRONTEND_PORT% \|127\.0\.0\.1:%FRONTEND_PORT% "') do (
    taskkill /F /PID %%p >nul 2>&1
)

:: ── Start backend in a new console window ─────────────────────────────────────
:: /D sets the working directory of the new window directly, which is more
:: reliable than cd-ing inside the command string (avoids quoting issues with
:: paths that contain spaces).
echo Starting backend on port %BACKEND_PORT%...
start "LRA-Backend" /D "%ROOT%" cmd /k "conda activate litreview && uvicorn backend.main:app --host 127.0.0.1 --port %BACKEND_PORT%"

:: ── Start frontend in a new console window ────────────────────────────────────
echo Starting frontend on port %FRONTEND_PORT%...
start "LRA-Frontend" /D "%ROOT%frontend" cmd /k "npm run dev"

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
