@echo off
REM 论文阅读器一键启动（双击运行）
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" -Demo %*
set "SCRIPT_EXIT=%ERRORLEVEL%"
if not "%SCRIPT_EXIT%"=="0" echo [x] 启动失败，退出代码：%SCRIPT_EXIT%
pause
exit /b %SCRIPT_EXIT%
