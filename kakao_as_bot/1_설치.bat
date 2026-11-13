@echo off
chcp 65001 > nul
cd /d "%~dp0"
python -m pip install -r requirements.txt
echo.
echo 설치 완료. config.json 을 메모장으로 열어 방 이름과 엑셀 경로를 입력하세요.
pause
