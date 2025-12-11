# M3U8 视频下载管理器

一个基于 Python Flask 和 N_m3u8DL-RE 的现代化 M3U8 视频下载管理系统。提供简洁友好的 Web 界面，支持任务队列、并发控制、实时进度监控、在线播放、Aria2 自动推送以及 **Jable 视频解析**。

## ✨ 功能特性

*   **Web 管理界面**：基于 Bootstrap 5 的响应式设计，操作直观。
*   **任务管理**：支持创建、停止、删除下载任务。
*   **视频解析**：**新增** Jable 视频解析功能，自动提取 M3U8 链接和标题，支持 Cloudflare 绕过。
*   **并发控制**：支持设置最大并发下载数，多余任务自动进入等待队列。
*   **实时监控**：实时显示下载进度、速度和详细日志。
*   **在线播放**：下载完成后可直接在浏览器中预览播放视频。
*   **Aria2 推送**：支持下载完成后自动将视频直链推送到 Aria2 进行二次下载或分发。
*   **API 访问**：支持生成 API Key，实现免登录调用接口提交任务。
*   **动态配置**：所有配置（路径、并发数、Aria2等）均可在 Web 界面动态修改，无需重启服务。
*   **安全认证**：内置初始化向导和密码认证机制。

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

*   **N_m3u8DL-RE**: 下载对应系统的版本，解压并将可执行文件放置在 `./bin/` 目录下（或在系统设置中指定路径）。
*   **FFmpeg**: 确保系统已安装 FFmpeg，或者将其可执行文件放置在 `./bin/` 目录下。

### 3. 启动服务

**Linux / macOS:**
```bash
python app.py
```

**Windows:**
```bash
python app.py
```

服务启动后，访问浏览器：`http://localhost:5000`

### 4. 系统初始化

首次访问时，系统会进入**初始化向导**。请设置管理员密码，该密码将用于后续登录管理界面。

## 📖 使用指南

### 任务管理
1.  **新建任务**：输入 M3U8 链接，可选自定义文件名。
2.  **视频解析**：在“视频解析”页面输入 Jable 视频链接，系统将自动解析并创建任务。
3.  **任务队列**：任务会自动排队，根据“最大并发数”设置依次执行。
4.  **管理操作**：支持停止、删除（可选同时删除文件和临时文件）、查看详情。

### 系统设置
在侧边栏点击“系统设置”可配置：
*   **基础配置**：最大并发数、外部访问地址（用于生成直链）。
*   **工具路径**：N_m3u8DL-RE 和 FFmpeg 的路径。
*   **存储配置**：下载目录和临时目录。
*   **Aria2 配置**：开启后，下载完成的视频会自动推送到指定的 Aria2 RPC。
*   **API 访问**：开启后，可获取 API Key 用于外部程序调用。

## 🔌 API 文档

开启 API 访问功能后，可以通过在 Header 中添加 `X-API-Key` 来免登录调用接口。

### 1. 创建任务

*   **URL**: `/api/tasks`
*   **Method**: `POST`
*   **Headers**:
    *   `Content-Type`: `application/json`
    *   `X-API-Key`: `您的API_Key`
*   **Body**:
    ```json
    {
        "url": "https://example.com/video.m3u8",
        "name": "自定义文件名 (可选)"
    }
    ```

### 2. 解析 Jable 视频

*   **URL**: `/api/parse/jable`
*   **Method**: `POST`
*   **Headers**: `X-API-Key: 您的API_Key`
*   **Body**:
    ```json
    {
        "url": "https://jable.tv/videos/..."
    }
    ```

## 📂 项目结构

```
.
├── app.py              # Flask 后端入口
├── database.py         # 数据库操作封装 (SQLite)
├── downloader.py       # 下载管理器 (含队列、并发、Aria2推送)
├── templates/          # HTML 模板
│   ├── base.html       # 基础布局
│   ├── new_task.html   # 新建任务页
│   ├── parser.html     # 解析页
│   └── ...
├── static/             # 前端静态资源
│   ├── css/            # 样式文件
│   └── js/             # 逻辑脚本 (api.js, tasks.js 等)
├── data/               # 数据存储目录 (数据库、密钥)
├── downloads/          # 视频下载目录
├── temp/               # 临时文件目录
└── bin/                # 外部工具目录
```

## ⚠️ 注意事项

*   **安全性**：请妥善保管管理员密码和 API Key。
*   **Aria2 推送**：确保配置的“外部访问地址”是 Aria2 服务端可以访问到的地址（例如局域网 IP 或公网域名），否则 Aria2 无法下载推送的直链。
*   **版权声明**：本项目仅供学习交流使用，请勿用于下载受版权保护的视频内容。

## 📄 License

MIT License