@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PORT=9222"
set "PROFILE=%~dp0chrome_debug_profile"

REM Find Chrome / Edge (Windows)
set "FOUND="
for %%P in (
  "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
) do (
  if exist %%~P (
    set "FOUND=%%~P"
    goto :launch
  )
)

echo Chrome or Edge not found.
echo.
echo Install Google Chrome: https://www.google.com/chrome/
echo Or run manually — fix the path:
echo   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=%PORT%
echo.
pause
exit /b 1

:launch
echo Launching browser with remote debugging:
echo   !FOUND!
echo Port: %PORT%
echo Profile: %PROFILE%
echo.
echo Next: log into Facebook in this window, then run start_web.bat
echo.

if not exist "%PROFILE%" mkdir "%PROFILE%"

REM Already running on this port?
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/json/version' -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
if %ERRORLEVEL%==0 (
  echo Chrome debug is ALREADY running on port %PORT%.
  echo Open http://127.0.0.1:%PORT%/json/version to confirm.
  echo Keep Chrome open while WinnerSpy scans.
  pause
  exit /b 0
)

start "" "!FOUND!" ^
  --remote-debugging-port=%PORT% ^
  --user-data-dir="%PROFILE%" ^
  --disable-session-crashed-bubble ^
  --no-first-run ^
  https://www.facebook.com/ads/library/

timeout /t 3 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%/json/version' -TimeoutSec 5).Content } catch { Write-Host 'NOT READY YET - wait 5 seconds and open the link above again'; exit 1 }"

echo.
echo Started. Keep the browser window open while scanning.
echo If Chrome asks to restore pages — click Close or No, do not force restore.
echo Next: run .\start_web.bat then click Check connection in the web UI.
pause
