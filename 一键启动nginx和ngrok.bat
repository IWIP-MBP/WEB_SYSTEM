@echo off
:: 设置编码为 UTF-8，防止中文提示变成乱码
chcp 65001 >nul
title Nginx ^& ngrok 自动化上线工具

:: ================= 配置区域 =================
:: 已根据你提供的信息填入绝对路径
set NGINX_DIR=D:\nginx-1.30.3
set NGROK_PATH=C:\Users\Administrator\AppData\Local\Microsoft\WindowsApps\ngrok.exe
set NGROK_URL=civil-grueling-enigmatic.ngrok-free.dev
:: ============================================

echo [0/3] 正在清理后台旧的 Nginx 和 ngrok 进程...
taskkill /f /im nginx.exe >nul 2>&1
taskkill /f /im ngrok.exe >nul 2>&1
timeout /t 1 /nobreak >nul

echo [1/3] 正在启动全新 Nginx...
cd /d "%NGINX_DIR%"
start nginx

echo [2/3] 正在真正的系统后台拉起 ngrok 隧道...
:: 【核心修复】利用 PowerShell 异步调用 Wscript.Shell，让 ngrok 彻底脱离当前 CMD 窗口独立运行
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject Wscript.Shell; $ws.Run('cmd /c \"\"%NGROK_PATH%\" http --url=%NGROK_URL% 80\"', 0, $false)"

echo [3/3] 开始检测 ngrok 上线状态，请稍候...
:check_loop
timeout /t 2 /nobreak >nul

:: 检测本地 ngrok 客户端的 Web 诊断界面是否包含你的域名
curl -s http://127.0.0.1:4040/api/tunnels | findstr /i "%NGROK_URL%" >nul

if %errorlevel% equ 0 (
    echo.
    echo ==================================================
    echo 🌟 恭喜！ngrok 隧道已成功上线！
    echo 🌍 外网访问地址: https://%NGROK_URL%
    echo 🚀 脚本将在 10 秒后自动安全退出，程序保持后台运行...
    echo ==================================================
    timeout /t 10 /nobreak >nul
    exit
) else (
    echo [! ] 仍在尝试连接 ngrok 服务器，请耐心等待...
    goto check_loop
)