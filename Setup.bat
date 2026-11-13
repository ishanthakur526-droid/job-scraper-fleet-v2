@echo off
setlocal EnableExtensions
title JobFleet setup
cd /d "%~dp0"
echo.
echo  =====================================================
echo    JobFleet setup  -  your free daily job finder
echo  =====================================================
echo.

if exist ".venv\Scripts\python.exe" goto :profile

echo  Step 1 of 2: installing JobFleet (one time, about a minute)...
where uv >nul 2>nul
if %errorlevel%==0 (
  uv sync --quiet
  if errorlevel 1 goto :fail
  goto :profile
)

set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY goto :nopython

%PY% -m venv .venv || goto :fail
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install --quiet -e . || goto :fail

:profile
echo.
echo  Step 2 of 2: tell JobFleet what you are looking for.
".venv\Scripts\python.exe" -m jobfleet setup
if errorlevel 1 goto :end
echo.
echo  All set! Double-click Run.bat to find jobs now.
echo  To run it automatically every weekday, open a terminal here and run:  .venv\Scripts\jobfleet schedule
goto :end

:nopython
echo.
echo  Python 3.11 or newer is needed and was not found.
echo  Install it from https://www.python.org/downloads/  (tick "Add python.exe to PATH"),
echo  or let Windows install it now with winget.
choice /C YN /M "  Install Python 3.12 with winget now"
if errorlevel 2 goto :end
winget install --id Python.Python.3.12 --exact --accept-package-agreements
echo.
echo  Python installed. Close this window and double-click Setup.bat again.
goto :end

:fail
echo.
echo  Something went wrong while installing. Check your internet connection and try again,
echo  or open an issue: https://github.com/ishanthakur526-droid/jobfleet/issues

:end
echo.
pause
