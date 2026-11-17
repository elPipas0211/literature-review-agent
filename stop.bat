@echo off
:: stop.bat - stop the backend (:8000) and the frontend (:5173)
setlocal
chcp 65001 >nul 2>&1

echo Stopping Literature Review Agent...
call :stop_port 8000 backend
call :stop_port 5173 frontend
echo Done.
endlocal
exit /b 0

:: Kill whatever is LISTENING on a port (IPv4 or IPv6, e.g. 127.0.0.1:8000 or [::1]:5173).
:stop_port
set "FOUND="
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /C:":%1 " ^| findstr LISTENING') do (
    if not "%%p"=="0" (
        echo   Stopping %2 ^(PID %%p, port %1^)
        taskkill /F /T /PID %%p >nul 2>&1
        set "FOUND=1"
    )
)
if not defined FOUND echo   %2 was not running.
exit /b 0
