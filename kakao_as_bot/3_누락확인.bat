@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
where python > nul 2> nul
if %errorlevel%==0 (
  python check_missing.py
) else (
  py check_missing.py
)
pause
