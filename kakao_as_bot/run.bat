@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
where python > nul 2> nul
if %errorlevel%==0 (
  python run.py %* >> run_console.log 2>&1
) else (
  py run.py %* >> run_console.log 2>&1
)
