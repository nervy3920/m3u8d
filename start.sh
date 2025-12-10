#!/bin/bash

# M3U8 下载管理器启动脚本

echo "======================================"
echo "  M3U8 下载管理器启动脚本"
echo "======================================"

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3，请先安装 Python 3.7+"
    exit 1
fi

echo "Python 版本: $(python3 --version)"

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "警告: 未找到 .env 文件，正在从 .env.example 创建..."
    cp .env.example .env
    echo "请编辑 .env 文件配置您的设置"
fi

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "安装依赖包..."
pip install -r requirements.txt

# 检查 N_m3u8DL-RE
if [ ! -f "./bin/N_m3u8DL-RE" ]; then
    echo "警告: 未找到 N_m3u8DL-RE，请确保已下载并放置在 ./bin/ 目录"
    echo "下载地址: https://github.com/nilaoda/N_m3u8DL-RE/releases"
fi

# 检查 FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "警告: 未找到 FFmpeg，某些功能可能无法使用"
    echo "请安装 FFmpeg: sudo apt install ffmpeg"
fi

# 创建必要的目录
echo "创建必要的目录..."
mkdir -p downloads
mkdir -p temp
mkdir -p data
mkdir -p static

# 启动应用
echo ""
echo "======================================"
echo "  启动 Flask 应用..."
echo "======================================"
python3 app.py
