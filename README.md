# M3U8 视频下载管理器

一个基于 Python Flask 和 N_m3u8DL-RE 的现代化 M3U8 视频下载管理系统。提供简洁友好的 Web 界面，支持任务队列、并发控制、实时进度监控和在线播放。

## ✨ 功能特性

*   **Web 管理界面**：基于 Bootstrap 5 的响应式设计，操作直观。
*   **任务管理**：支持创建、停止、删除下载任务。
*   **并发控制**：支持设置最大并发下载数，多余任务自动进入等待队列。
*   **实时监控**：实时显示下载进度、速度和详细日志。
*   **在线播放**：下载完成后可直接在浏览器中预览播放视频。
*   **安全认证**：内置简单的密码认证机制，保护管理入口。
*   **灵活配置**：支持自定义下载路径、并发数等参数。

## 🛠️ 系统要求

*   Python 3.7+
*   [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) (核心下载工具)
*   [FFmpeg](https://ffmpeg.org/) (用于视频合并与处理)

## 🚀 快速开始

### 1. 安装依赖

首先克隆或下载本项目，然后安装 Python 依赖：

```bash
pip install -r requirements.txt
```

### 2. 准备外部工具

本项目依赖 `N_m3u8DL-RE` 和 `FFmpeg`。

*   **N_m3u8DL-RE**: 下载对应系统的版本，解压并将可执行文件放置在 `./bin/` 目录下（或在 `.env` 中指定路径）。
*   **FFmpeg**: 确保系统已安装 FFmpeg，或者将其可执行文件放置在 `./bin/` 目录下。

### 3. 配置文件 (.env)

创建或编辑 `.env` 文件，并根据需要修改配置：

```ini
# 管理员登录密码
ADMIN_PASSWORD=admin123

# 最大并发下载任务数 (默认: 3)
MAX_CONCURRENT_DOWNLOADS=3

# 工具路径配置
N_M3U8DL_PATH=./bin/N_m3u8DL-RE
FFMPEG_PATH=./bin/ffmpeg

# 目录配置
DOWNLOAD_DIR=./downloads
TEMP_DIR=./temp

# Flask 安全配置 (生产环境请务必修改 SECRET_KEY)
SECRET_KEY=your-secret-key-change-this
FLASK_DEBUG=False
```

### 4. 启动服务

**Linux / macOS:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
直接运行 `start.bat` 或：
```bash
python app.py
```

服务启动后，访问浏览器：`http://localhost:5000`

## 📖 使用指南

1.  **登录**：输入 `.env` 中配置的 `ADMIN_PASSWORD`。
2.  **新建任务**：
    *   点击左侧“新建任务”。
    *   输入 M3U8 视频链接。
    *   (可选) 输入自定义文件名。
    *   点击“开始下载”。
3.  **任务队列**：
    *   如果当前下载任务数未达到 `MAX_CONCURRENT_DOWNLOADS`，任务会立即开始。
    *   如果已满，任务将显示为“等待中”，待有空闲位置时自动开始。
4.  **管理任务**：
    *   **停止**：可随时停止正在下载或等待中的任务。
    *   **删除**：删除任务时，会弹出确认框询问是否同时删除本地已下载的文件。
    *   **详情**：点击“详情”可查看详细的下载日志和文件信息。
5.  **播放与下载**：
    *   任务完成后，点击“播放”可直接在线观看。
    *   点击“下载”可将视频文件下载到本地设备。

## 📂 项目结构

```
.
├── app.py              # Flask 后端入口
├── database.py         # 数据库操作封装
├── downloader.py       # 下载管理器 (含队列与并发逻辑)
├── static/             # 前端静态资源
│   ├── index.html      # 单页应用主页
│   └── app.js          # 前端核心逻辑
├── data/               # SQLite 数据库存储目录
├── downloads/          # 视频下载目录
├── temp/               # 临时文件目录
├── bin/                # 外部工具目录 (N_m3u8DL-RE, ffmpeg)
└── .env                # 配置文件
```

## ⚠️ 注意事项

*   **安全性**：`FLASK_DEBUG=True` 仅用于开发调试，**生产环境请务必设置为 False**。同时请修改 `SECRET_KEY` 为随机字符串以确保 Session 安全。
*   **网络问题**：下载速度取决于您的网络环境以及源站点的带宽。
*   **版权声明**：本项目仅供学习交流使用，请勿用于下载受版权保护的视频内容。

## 📄 License

MIT License