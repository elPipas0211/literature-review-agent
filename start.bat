@echo off
:: start.bat - start backend (:8000) and frontend (:5173) in two windows
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "ROOT=%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First run: installing dependencies...
    call "%ROOT%install.bat" || exit /b 1
)
if not exist "frontend\node_modules" (
    pushd frontend & call npm install --no-audit --no-fund & popd
)

call "%ROOT%stop.bat" >nul 2>&1

echo Starting backend on http://127.0.0.1:8000 ...
start "LRA-Backend" /D "%ROOT%" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
echo Starting frontend on http://localhost:5173 ...
start "LRA-Frontend" /D "%ROOT%frontend" cmd /k "npm run dev"

ping -n 5 127.0.0.1 >nul
start "" http://localhost:5173
echo.
echo   App:      http://localhost:5173
echo   API docs: http://127.0.0.1:8000/docs
echo   Stop:     stop.bat  (or close the two windows)
endlocal
