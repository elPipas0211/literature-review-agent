@echo off
:: stop.bat - kill uvicorn (:8000) and Vite (:5173)
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

set BACKEND_PORT=8000
set FRONTEND_PORT=5173

echo Stopping Literature Review Agent...

:: -- Kill by port ---------------------------------------------------------------
set FOUND_BACKEND=0
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr /R " 0\.0\.0\.0:%BACKEND_PORT% \|127\.0\.0\.1:%BACKEND_PORT% "') do (
    echo   Stopping PID %%p on port %BACKEND_PORT%
    taskkill /F /PID %%p >nul 2>&1
    set FOUND_BACKEND=1
)
if "%FOUND_BACKEND%"=="0" echo   No process found on port %BACKEND_PORT%.

set FOUND_FRONTEND=0
for /f "tokens=5" %%p in ('netstat -aon 2^>nul ^| findstr /R " 0\.0\.0\.0:%FRONTEND_PORT% \|127\.0\.0\.1:%FRONTEND_PORT% "') do (
    echo   Stopping PID %%p on port %FRONTEND_PORT%
    taskkill /F /PID %%p >nul 2>&1
    set FOUND_FRONTEND=1
)
if "%FOUND_FRONTEND%"=="0" echo   No process found on port %FRONTEND_PORT%.

echo Done.
endlocal
