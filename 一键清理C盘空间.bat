@echo off
:: 设置编码为 UTF-8，防止中文显示乱码
chcp 65001 >nul
title Docker ^& WSL2 C盘空间一键清理工具

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] 请右键选择“以管理员身份运行”此脚本！
    echo.
    pause
    exit /b
)

echo ==================================================
echo        后勤三部人事系统 - Docker C盘空间清理工具
echo ==================================================
echo.
echo 提示：此脚本将执行以下操作：
echo 1. 清理 Docker 内部构建缓存 (Build Cache)、悬挂镜像和无用容器。
echo 2. 暂时关闭 Docker Desktop 并强制终止 WSL2 虚拟机以解锁文件。
echo 3. 使用 Windows diskpart 工具对 C 盘的 docker_data.vhdx 虚拟磁盘文件执行物理压缩。
echo 4. 重新启动 com.docker.service 并拉起 Docker Desktop。
echo.
set /p confirm="您确定要开始清理吗？[Y/N]: "
if /i "%confirm%" neq "Y" (
    echo 已取消清理。
    pause
    exit /b
)

echo.
echo ==================================================
echo [1/4] 正在清理 Docker 内部多余缓存...
echo ==================================================
docker builder prune -a -f
docker system prune -f
docker volume prune -f

echo.
echo ==================================================
echo [2/4] 正在停止 Docker 服务与 WSL2 虚拟机...
echo ==================================================
powershell -Command "Stop-Service -Name com.docker.service -ErrorAction SilentlyContinue"
powershell -Command "Get-Process | Where-Object {$_.Name -like '*docker*'} | Stop-Process -Force -ErrorAction SilentlyContinue"
wsl --shutdown

echo.
echo ==================================================
echo [3/4] 正在压缩 WSL2 虚拟磁盘文件...
echo ==================================================
set VHDX_PATH=C:\Users\Administrator\AppData\Local\Docker\wsl\disk\docker_data.vhdx
if not exist "%VHDX_PATH%" (
    set VHDX_PATH=%USERPROFILE%\AppData\Local\Docker\wsl\disk\docker_data.vhdx
)

if exist "%VHDX_PATH%" (
    echo 找到虚拟磁盘文件：%VHDX_PATH%
    echo select vdisk file="%VHDX_PATH%" > %TEMP%\docker_compact.txt
    echo attach vdisk readonly >> %TEMP%\docker_compact.txt
    echo compact vdisk >> %TEMP%\docker_compact.txt
    echo detach vdisk >> %TEMP%\docker_compact.txt
    
    diskpart /s %TEMP%\docker_compact.txt
    del %TEMP%\docker_compact.txt
    echo 磁盘文件压缩完成！
) else (
    echo [WARNING] 未找到 Docker WSL2 虚拟磁盘文件，跳过物理压缩。
)

echo.
echo ==================================================
echo [4/4] 正在重新启动 Docker 服务与应用程序...
echo ==================================================
powershell -Command "Start-Service -Name com.docker.service -ErrorAction SilentlyContinue"
echo 正在拉起 Docker Desktop 客户端...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

echo.
echo ==================================================
echo 🌟 清理及压缩工作已全部完成！C盘空间已成功回收。
echo ==================================================
pause
