@echo off
chcp 65001 >nul
echo ======================================
echo   M3U8 下载管理器启动脚本
echo ======================================

REM 检查 Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误: 未找到 Python，请先安装 Python 3.7+
    pause
    exit /b 1
)

echo Python 版本:
python --version

REM 检查 .env 文件
if not exist .env (
    echo 警告: 未找到 .env 文件，正在从 .env.example 创建...
    copy .env.example .env
    echo 请编辑 .env 文件配置您的设置
)

REM 检查虚拟环境
if not exist venv (
    echo 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
echo 激活虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖
echo 安装依赖包...
pip install -r requirements.txt

REM 检查 N_m3u8DL-RE
if not exist "bin\N_m3u8DL-RE.exe" (
    echo 警告: 未找到 N_m3u8DL-RE.exe，请确保已下载并放置在 .\bin\ 目录
    echo 下载地址: https://github.com/nilaoda/N_m3u8DL-RE/releases
)

REM 检查 FFmpeg
where ffmpeg >nul 2>nul
if %errorlevel% neq 0 (
    echo 警告: 未找到 FFmpeg，某些功能可能无法使用
    echo 请下载 FFmpeg: https://ffmpeg.org/download.html
)

REM 创建必要的目录
echo 创建必要的目录...
if not exist downloads mkdir downloads
if not exist temp mkdir temp
if not exist data mkdir data
if not exist static mkdir static

REM 启动应用
echo.
echo ======================================
echo   启动 Flask 应用...
echo ======================================
python app.py

pause
