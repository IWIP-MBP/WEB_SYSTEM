@echo off

:: Check for Administrator privileges using fltmc (more reliable than net session)
fltmc >nul 2>&1
if %errorlevel% neq 0 (
    :: If we already tried to elevate and failed, abort to prevent infinite loop
    if "%1"=="elevated" (
        echo [ERROR] 未能获取管理员权限，请右键选择“以管理员身份运行”此脚本。
        pause
        exit /b
    )
    echo 正在请求管理员权限...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
    exit /b
)

:: Run the PowerShell script directly (already elevated!)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0clean_c_drive.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 脚本执行失败。错误码: %errorlevel%
    pause
) else (
    echo.
    echo 任务已成功完成！
    pause
)
