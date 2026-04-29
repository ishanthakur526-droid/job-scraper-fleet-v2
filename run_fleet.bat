@echo off
set ROOT=%~dp0
set PYTHONPATH=%ROOT%src
python -m jobfleet.cli --config-dir "%ROOT%config" --output-dir "%ROOT%outputs" --max-per-category 40 %*
