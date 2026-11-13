@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ===== 시험 실행 =====
where python
where python > nul 2> nul
if %errorlevel%==0 (
  python --version
  python run.py
) else (
  echo python 명령이 없어 py 로 실행합니다
  py --version
  py run.py
)
echo.
echo ===== 끝 (이 화면을 캡처해서 보내주세요) =====
pause
