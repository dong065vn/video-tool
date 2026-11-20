@echo off
REM ============================================================
REM  video-tool.bat - CLI Launcher cho Video Tool v2
REM  Cho phep go `video-tool` o bat ky thu muc nao sau khi add PATH:
REM    video-tool                       -> Mo giao dien GUI (main.py)
REM    video-tool gui                   -> Mo giao dien GUI (main.py)
REM    video-tool --cli ...             -> Chay main.py --cli ...
REM    video-tool gpu / mirror / speed / image / sticker / batch / chunk / info / play / silence ...
REM                                     -> Chay video_processor.py <lenh> ...
REM ============================================================
setlocal

set "TOOL_DIR=%~dp0"
if "%TOOL_DIR:~-1%"=="\" set "TOOL_DIR=%TOOL_DIR:~0,-1%"

REM Fallback: neu phien CMD/Explorer hien tai chua refresh PATH sau khi cai Python
set "PY_CMD=python"
%PY_CMD% --version >nul 2>nul
if errorlevel 1 (
    for %%V in (Python314 Python313 Python312 Python311 Python310) do (
        if exist "%LOCALAPPDATA%\Programs\Python\%%V\python.exe" (
            set "PATH=%LOCALAPPDATA%\Programs\Python\%%V;%LOCALAPPDATA%\Programs\Python\%%V\Scripts;%PATH%"
            set "PY_CMD=%LOCALAPPDATA%\Programs\Python\%%V\python.exe"
            goto :py_found
        )
    )
)
:py_found

REM Fallback: neu phien CMD/Explorer hien tai chua refresh PATH cho FFmpeg
where ffmpeg >nul 2>nul
if errorlevel 1 (
    for /f "delims=" %%F in ('dir /b /s "%LOCALAPPDATA%\Microsoft\WinGet\Packages\ffmpeg.exe" 2^>nul') do (
        set "PATH=%%~dpF;%PATH%"
        goto :ff_found
    )
    for /f "delims=" %%F in ('dir /b /s "%LOCALAPPDATA%\Programs\ffmpeg\ffmpeg.exe" 2^>nul') do (
        set "PATH=%%~dpF;%PATH%"
        goto :ff_found
    )
)
:ff_found

if "%~1"=="" goto :run_gui
if /I "%~1"=="gui" goto :run_gui
if /I "%~1"=="--cli" goto :run_main

for %%C in (gpu mirror speed image sticker batch chunk info play silence -h --help) do (
    if /I "%~1"=="%%C" goto :run_processor
)

:run_main
"%PY_CMD%" "%TOOL_DIR%\main.py" %*
exit /b %ERRORLEVEL%

:run_gui
"%PY_CMD%" "%TOOL_DIR%\main.py"
exit /b %ERRORLEVEL%

:run_processor
"%PY_CMD%" "%TOOL_DIR%\video_processor.py" %*
exit /b %ERRORLEVEL%
