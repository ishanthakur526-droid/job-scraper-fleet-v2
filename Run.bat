@echo off
setlocal
title JobFleet
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo JobFleet is not installed yet. Double-click Setup.bat first.
  pause
  exit /b 2
)
if not exist "profile.toml" (
  echo No profile yet. Double-click Setup.bat first.
  pause
  exit /b 2
)
echo Finding jobs (this takes 2-4 minutes)...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_fleet.ps1" %*
set CODE=%errorlevel%
if exist "outputs\dashboard.html" start "" "outputs\dashboard.html"
if not "%CODE%"=="0" echo The run reported a problem (exit code %CODE%). See outputs\logs for details.
pause
exit /b %CODE%
