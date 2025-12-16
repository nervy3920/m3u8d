# M3U8 视频下载管理器

一个基于 Python Flask 和 N_m3u8DL-RE 的现代化 M3U8 视频下载管理系统。提供简洁友好的 Web 界面，支持任务队列、并发控制、实时进度监控、在线播放、Aria2 自动推送以及 **智能视频解析**。

## ✨ 功能特性

* **Web 管理界面**：基于 Bootstrap 5 的响应式设计，操作直观，支持移动端访问。
* **智能解析**：
  * **通用解析**：输入网页地址自动提取 M3U8 链接和视频标题。
  * **批量解析**：支持批量输入网页链接，自动解析并添加到下载队列。
  * **高级模式**：支持调用 Chrome (Selenium) 模拟浏览器行为，绕过部分反爬虫限制。
* **任务管理**：
  * 支持自定义文件名（解析时自动获取标题）。
  * 支持任务队列管理，可设置最大并发下载数。
  * 支持暂停、恢复、删除任务（可选同时删除文件）。
* **实时监控**：实时显示下载进度、速度、剩余时间以及详细的控制台日志。
* **在线预览**：下载完成后可直接在浏览器中预览播放视频（支持 MP4/HLS）。
* **Aria2 推送**：支持下载完成后自动将视频直链推送到 Aria2 进行二次分发或存储。
* **API 支持**：提供完整的 API 接口，支持生成 API Key 进行免登录调用。
* **安全认证**：内置初始化向导和密码认证机制，保护系统安全。

## 🛠️ 系统要求

* **操作系统**: Linux / macOS / Windows
* **Python**: 3.7+
* **核心工具**:
  * [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE) (必须)
  * [FFmpeg](https://ffmpeg.org/) (必须，用于视频合并)
  * Google Chrome & ChromeDriver (可选，用于高级解析)

## 🚀 安装部署

### 1. 获取代码与安装依赖

```bash
# 克隆项目 (如果已下载可跳过)
git clone https://github.com/nervy3920/m3u8d.git
cd m3u8d

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 配置核心工具

本项目依赖 `N_m3u8DL-RE` 和 `FFmpeg`。

1. **N_m3u8DL-RE**: 下载对应系统的版本，解压并将可执行文件放置在项目根目录下的 `./bin/` 文件夹中（或者在系统设置中指定绝对路径）。
2. **FFmpeg**: 确保系统已安装 FFmpeg，或者将其可执行文件放置在 `./bin/` 目录下。

### 3. 配置 Chrome 环境 (可选)

如果需要使用 **Selenium 高级解析** 功能（用于抓取动态加载或有反爬限制的网页），需要在服务器上安装 Chrome 浏览器。

**Debian / Ubuntu 系统:**

```bash
# 1. 下载安装包
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 2. 安装
sudo apt install ./google-chrome-stable_current_amd64.deb

# 3. 修复依赖 (如果安装报错)
sudo apt -f install
```

**CentOS / Fedora / RHEL 系统:**

```bash
# 1. 下载安装包
wget https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm

# 2. 安装
sudo dnf localinstall ./google-chrome-stable_current_x86_64.rpm
```

*注：系统会自动寻找匹配的 ChromeDriver，如果失败请手动下载对应版本的 ChromeDriver 并配置路径。*

### 4. 启动服务

**Linux / macOS:**

```bash
python app.py
```

**Windows:**

```bash
python app.py
```

服务启动后，默认访问地址：`http://localhost:5000`

首次访问将进入 **初始化向导**，请设置管理员密码。

## 📖 使用指南

### 任务下载

1. **新建任务**：直接输入 M3U8 链接，可手动指定文件名。
2. **视频解析**：
   * **单条解析**：输入视频播放页 URL，点击解析。成功后可预览视频，点击“下载”自动创建任务（文件名自动填充）。
   * **批量解析**：切换到“批量解析”标签，每行输入一个视频页 URL。解析成功后可一键全部添加到下载队列。
   * **使用 Selenium**：勾选“使用 Selenium”可应对复杂网页，但速度较慢且消耗服务器资源。

### 系统设置

* **并发设置**：在设置页面调整“最大并发下载数”，多余任务将排队等待。
* **路径配置**：如果工具不在默认目录，请在设置中填写 N_m3u8DL-RE 和 FFmpeg 的绝对路径。
* **Aria2 配置**：填写 Aria2 RPC 地址和密钥，开启后下载完成的文件将自动推送到 Aria2。

## 🔌 API 文档

开启 API 访问功能后，在 Header 中添加 `X-API-Key` 即可调用。

### 1. 创建任务 (支持批量)

* **URL**: `/api/tasks`
* **Method**: `POST`
* **Body**:
  ```json
  // 单个任务
  {
      "url": "http://example.com/video.m3u8",
      "name": "自定义文件名"
  }
  
  // 批量任务 (文本格式)
  {
      "text": "http://url1.m3u8|文件名1\nhttp://url2.m3u8"
  }
  ```

### 2. 批量解析

* **URL**: `/api/parse/batch`
* **Method**: `POST`
* **Body**:
  ```json
  {
      "urls": ["http://page1.html", "http://page2.html"],
      "use_selenium": false
  }
  ```

## ⚠️ 免责声明

1. 本项目仅供技术学习和交流使用。
2. 使用者应自行遵守当地法律法规，请勿使用本项目下载侵犯版权的视频内容。
3. 开发者不对使用者因使用本项目而产生的任何法律后果承担责任。

## 📄 License

MIT License