@echo off
chcp 65001 > nul
cd /d "%~dp0"
schtasks /Create /SC HOURLY /MO 1 /TN "KakaoASBot" /TR "\"%~dp0run.bat\"" /IT /F
echo.
echo 1시간마다 자동 실행이 등록되었습니다. (작업 스케줄러 - KakaoASBot)
echo 끄려면: schtasks /Delete /TN "KakaoASBot" /F
pause
