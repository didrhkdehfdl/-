@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ===== 시험 실행 =====
echo 폴더: %cd%
if not exist run.py (
  echo [오류] 이 폴더에 run.py 가 없습니다. 압축을 푼 폴더 안의 0_시험실행.bat 를 실행하세요.
  goto end
)
for %%f in (run.py excel_writer.py kakao_reader.py config.json) do if not exist %%f echo [오류] %%f 파일이 없습니다 (백신이 지웠을 수 있음)
where python > nul 2> nul
if %errorlevel%==0 (
  python --version
  python run.py
) else (
  echo python 명령이 없어 py 로 실행합니다
  py --version
  py run.py
)
echo 종료 코드: %errorlevel%
:end
echo.
echo ===== 끝 (이 화면을 캡처해서 보내주세요) =====
pause
