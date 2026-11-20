@echo off
REM Double-click hoac go `run_video_tool` tu CMD/PowerShell de mo giao dien Video Tool v2.
chcp 65001 >nul 2>nul
call "%~dp0video-tool.bat" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo  [!] Khong chay duoc Video Tool ^(ma loi %EXIT_CODE%^).
    echo      Hay chay setup_python.bat truoc de cai dat Python va FFmpeg.
    pause
)
exit /b %EXIT_CODE%
