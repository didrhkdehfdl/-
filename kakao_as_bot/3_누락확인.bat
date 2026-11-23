@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ===== 누락 확인 =====
echo 엑셀을 닫은 상태에서 실행하는 것을 권장합니다.
where python > nul 2> nul
if %errorlevel%==0 (
  python check_missing.py
) else (
  py check_missing.py
)
echo.
echo ===== 끝 =====
pause
