@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo WinnerSpy Web v5
echo Login: admin@local / admin123
echo Chrome debug: run start_chrome_debug.bat first
echo PowerShell: .\start_web.bat   (needs .\ prefix)
echo.

set "PY=python"
where py >nul 2>&1
if not errorlevel 1 set "PY=py -3"

set "VENV_PY=%~dp0venv\Scripts\python.exe"

if exist "%VENV_PY%" goto :install

echo Creating new Windows venv...
if exist "venv" (
  echo Removing old venv - was WSL or Linux...
  rmdir /s /q "venv" 2>nul
)

%PY% -m venv venv
if not exist "%VENV_PY%" (
  echo ERROR: could not create venv. Install Python from python.org
  pause
  exit /b 1
)

:install
echo Installing web dependencies...
"%VENV_PY%" -m pip install --upgrade pip -q
"%VENV_PY%" -m pip install -r requirements-web.txt
if errorlevel 1 (
  echo ERROR installing pip packages
  pause
  exit /b 1
)

echo.
echo Open http://127.0.0.1:5050
"%VENV_PY%" web_app.py
pause
