@echo off
:: install.bat - create .venv, install Python + frontend dependencies (Windows, no conda needed)
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo =========================================
echo   Literature Review Agent -- Install
echo =========================================
echo.

:: -- Python 3.11+ --------------------------------------------------------------
set "PY="
where py >nul 2>&1 && (py -3.12 -c "" >nul 2>&1 && set "PY=py -3.12")
if not defined PY where py >nul 2>&1 && (py -3.11 -c "" >nul 2>&1 && set "PY=py -3.11")
if not defined PY where py >nul 2>&1 && (py -3.13 -c "" >nul 2>&1 && set "PY=py -3.13")
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
    echo [ERROR] Python 3.11+ not found. Install it from https://www.python.org/downloads/
    exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.11 or newer is required.
    exit /b 1
)
echo [OK] Using %PY%

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js / npm not found. Install v18+ from https://nodejs.org
    exit /b 1
)
echo [OK] Node.js found.
echo.

:: -- Virtual environment -------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment .venv ...
    %PY% -m venv .venv || exit /b 1
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip -q || exit /b 1
echo Installing PyTorch (CPU) ...
"%VPY%" -m pip install torch --index-url https://download.pytorch.org/whl/cpu -q || exit /b 1
echo Installing Python packages ...
"%VPY%" -m pip install -r requirements.txt -q || exit /b 1
echo [OK] Python environment ready.
echo.

:: -- Frontend ------------------------------------------------------------------
echo Installing frontend dependencies ...
pushd frontend
call npm install --no-audit --no-fund
set "NPMERR=%errorlevel%"
popd
if not "%NPMERR%"=="0" (
    echo [ERROR] npm install failed.
    exit /b 1
)
echo [OK] Frontend ready.

echo.
echo =========================================
echo   Done. Run start.bat to launch the app.
echo   (the embedding model, ~470 MB, downloads on first start)
echo =========================================
endlocal
