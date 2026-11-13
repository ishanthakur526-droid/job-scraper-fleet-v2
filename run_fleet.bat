@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%src"
set "PYTHONUTF8=1"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m jobfleet.cli --config-dir "%ROOT%config" --output-dir "%ROOT%outputs" %*
exit /b %ERRORLEVEL%
