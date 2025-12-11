from flask import Flask, request, jsonify, send_from_directory, send_file, make_response, render_template, redirect, url_for
from flask_cors import CORS
import os
import traceback
from pathlib import Path
from functools import wraps
import hashlib
import secrets
import requests
import re

from database import Database
from downloader import DownloadManager

app = Flask(__name__)

# 确保数据目录存在
Path('./data').mkdir(parents=True, exist_ok=True)

# 简单的 Secret Key 管理
secret_file = Path('./data/secret.key')
if not secret_file.exists():
    secret_file.write_text(secrets.token_hex(32))
app.config['SECRET_KEY'] = secret_file.read_text().strip()

CORS(app, supports_credentials=True)

DATABASE_PATH = './data/tasks.db'

# 初始化数据库
db = Database(DATABASE_PATH)

# 初始化下载管理器 (配置将从数据库读取)
download_manager = DownloadManager(db)

# 获取管理员密码
def get_admin_password():
    return db.get_setting('admin_password')

# 生成认证令牌
def generate_auth_token(password):
    """生成认证令牌"""
    return hashlib.sha256(f"{password}{app.config['SECRET_KEY']}".encode()).hexdigest()

# 验证令牌
def verify_auth_token(token):
    """验证认证令牌"""
    password = get_admin_password()
    if not password:
        return False
    expected_token = generate_auth_token(password)
    return token == expected_token

def require_auth(f):
    """验证密码装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查系统是否已初始化
        if not get_admin_password():
             return jsonify({'error': '系统未初始化', 'code': 'NOT_INITIALIZED'}), 403

        # 1. 检查 API Key (如果开启)
        api_key = request.headers.get('X-API-Key')
        if api_key:
            if db.get_setting('api_enabled') == 'true' and api_key == db.get_setting('api_key'):
                return f(*args, **kwargs)

        # 2. 检查 Cookie
        token = request.cookies.get('auth_token')
        if token and verify_auth_token(token):
            return f(*args, **kwargs)

        # 3. 检查 Header 密码（兼容旧方式）
        password = request.headers.get('X-Admin-Password')
        if password and password == get_admin_password():
            return f(*args, **kwargs)

        return jsonify({'error': '未授权，请重新登录或提供有效的 API Key'}), 401
    return decorated_function


# 页面路由
@app.route('/')
def index():
    """首页重定向"""
    if not get_admin_password():
        return redirect(url_for('init_page'))
    
    token = request.cookies.get('auth_token')
    if token and verify_auth_token(token):
        return redirect(url_for('new_task_page'))
    return redirect(url_for('login_page'))

@app.route('/init')
def init_page():
    """初始化页面"""
    if get_admin_password():
        return redirect(url_for('login_page'))
    return render_template('init.html')

@app.route('/login')
def login_page():
    """登录页面"""
    if not get_admin_password():
        return redirect(url_for('init_page'))
    
    token = request.cookies.get('auth_token')
    if token and verify_auth_token(token):
        return redirect(url_for('new_task_page'))
    return render_template('login.html')

def check_page_auth():
    """页面权限检查"""
    if not get_admin_password():
        return redirect(url_for('init_page'))
    
    token = request.cookies.get('auth_token')
    if not token or not verify_auth_token(token):
        return redirect(url_for('login_page'))
    return None

@app.route('/new')
def new_task_page():
    auth_redirect = check_page_auth()
    if auth_redirect: return auth_redirect
    return render_template('new_task.html', active_page='new')

@app.route('/downloading')
def downloading_page():
    auth_redirect = check_page_auth()
    if auth_redirect: return auth_redirect
    return render_template('downloading.html', active_page='downloading')

@app.route('/completed')
def completed_page():
    auth_redirect = check_page_auth()
    if auth_redirect: return auth_redirect
    return render_template('completed.html', active_page='completed')

@app.route('/all')
def all_tasks_page():
    auth_redirect = check_page_auth()
    if auth_redirect: return auth_redirect
    return render_template('all_tasks.html', active_page='all')

@app.route('/settings')
def settings_page():
    auth_redirect = check_page_auth()
    if auth_redirect: return auth_redirect
    return render_template('settings.html', active_page='settings')

@app.route('/parser')
def parser_page():
    auth_redirect = check_page_auth()
    if auth_redirect: return auth_redirect
    return render_template('parser.html', active_page='parser')


@app.route('/api/init', methods=['POST'])
def init_system():
    """初始化系统（设置密码）"""
    if get_admin_password():
        return jsonify({'error': '系统已初始化'}), 400
    
    data = request.get_json()
    password = data.get('password', '').strip()
    
    if not password:
        return jsonify({'error': '密码不能为空'}), 400
        
    db.set_setting('admin_password', password)
    return jsonify({'success': True, 'message': '初始化成功'})

@app.route('/api/auth', methods=['POST'])
def auth():
    """验证密码"""
    data = request.get_json()
    password = data.get('password', '')
    
    admin_password = get_admin_password()
    
    if not admin_password:
        return jsonify({'error': '系统未初始化', 'code': 'NOT_INITIALIZED'}), 403

    if password == admin_password:
        # 生成认证令牌
        token = generate_auth_token(password)

        response = make_response(jsonify({'success': True, 'message': '验证成功', 'token': token}))
        # 设置 Cookie，有效期 30 天
        response.set_cookie('auth_token', token, max_age=30*24*60*60, httponly=True, samesite='Lax')
        return response
    else:
        return jsonify({'success': False, 'message': '密码错误'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    """退出登录"""
    response = make_response(jsonify({'success': True, 'message': '已退出登录'}))
    response.set_cookie('auth_token', '', max_age=0)
    return response


@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """检查登录状态"""
    if not get_admin_password():
        return jsonify({'authenticated': False, 'initialized': False})
        
    token = request.cookies.get('auth_token')
    if token and verify_auth_token(token):
        return jsonify({'authenticated': True, 'initialized': True})
    return jsonify({'authenticated': False, 'initialized': True})


@app.route('/api/tasks', methods=['GET'])
@require_auth
def get_tasks():
    """获取所有任务"""
    status = request.args.get('status')

    if status:
        tasks = db.get_tasks_by_status(status)
    else:
        tasks = db.get_all_tasks()

    return jsonify({'tasks': tasks})


@app.route('/api/tasks', methods=['POST'])
@require_auth
def create_task():
    """创建新任务"""
    data = request.get_json()
    url = data.get('url', '').strip()
    custom_name = data.get('name', '').strip() or None

    if not url:
        return jsonify({'error': '请提供下载链接'}), 400

    # 创建任务
    task_id = db.create_task(url, custom_name)

    # 启动下载
    success, message = download_manager.start_download(task_id, url, custom_name)

    if success:
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': message
        })
    else:
        return jsonify({'error': message}), 400


@app.route('/api/tasks/<int:task_id>', methods=['GET'])
@require_auth
def get_task(task_id):
    """获取任务详情"""
    task = db.get_task(task_id)

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    return jsonify({'task': task})


@app.route('/api/tasks/<int:task_id>/logs', methods=['GET'])
@require_auth
def get_task_logs(task_id):
    """获取任务日志"""
    logs = db.get_task_logs(task_id)
    return jsonify({'logs': logs})


@app.route('/api/tasks/<int:task_id>/stop', methods=['POST'])
@require_auth
def stop_task(task_id):
    """停止任务"""
    success, message = download_manager.stop_download(task_id)

    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 400


@app.route('/api/tasks/<int:task_id>/retry', methods=['POST'])
@require_auth
def retry_task(task_id):
    """重试/恢复任务"""
    task = db.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
        
    # 检查任务状态
    if task['status'] in ['downloading', 'pending']:
        return jsonify({'error': '任务正在运行或等待中'}), 400
        
    # 重新启动下载
    success, message = download_manager.start_download(task_id, task['url'], task.get('custom_name'))
    
    if success:
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'error': message}), 400


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@require_auth
def delete_task(task_id):
    """删除任务"""
    delete_file = request.args.get('delete_file', 'true').lower() == 'true'
    task = db.get_task(task_id)

    if not task:
        return jsonify({'error': '任务不存在'}), 404

    # 如果任务正在运行，先停止
    if task_id in download_manager.get_active_tasks():
        download_manager.stop_download(task_id)

    # 删除文件
    if delete_file:
        # 1. 删除已下载的视频文件
        if task['file_path'] and os.path.exists(task['file_path']):
            try:
                os.remove(task['file_path'])
            except:
                pass
        
        # 2. 删除临时文件 (N_m3u8DL-RE 的临时目录)
        # 临时目录结构通常是: temp_dir/save_name/
        # 我们需要获取 save_name，这通常在 downloader.py 中生成，但这里我们可以尝试推断
        # 或者更简单地，我们在 downloader.py 中添加一个清理临时文件的方法，或者在这里处理
        # 由于 save_name 并没有直接存储在 task 表中（只有 custom_name），
        # 但我们可以利用 task_id 来查找。
        # N_m3u8DL-RE 默认会在 temp 目录下创建一个以 save_name 命名的文件夹
        
        # 更好的方式是调用 download_manager 的清理方法
        download_manager.clean_temp_files(task_id, task.get('custom_name'))

    # 删除数据库记录
    db.delete_task(task_id)

    return jsonify({'success': True, 'message': '任务已删除'})


@app.route('/api/stats', methods=['GET'])
@require_auth
def get_stats():
    """获取统计信息"""
    all_tasks = db.get_all_tasks()

    stats = {
        'total': len(all_tasks),
        'completed': len([t for t in all_tasks if t['status'] == 'completed']),
        'downloading': len([t for t in all_tasks if t['status'] == 'downloading']),
        'failed': len([t for t in all_tasks if t['status'] == 'failed']),
        'pending': len([t for t in all_tasks if t['status'] == 'pending']),
        'active_tasks': download_manager.get_active_tasks()
    }

    return jsonify(stats)


@app.route('/videos/<path:filename>')
def serve_video(filename):
    """提供视频文件 (公开访问，供 Aria2 和播放器使用)"""
    download_dir = db.get_setting('download_dir', './downloads')
    try:
        return send_from_directory(download_dir, filename, as_attachment=False)
    except Exception as e:
        return jsonify({'error': f'文件不存在: {str(e)}'}), 404


@app.route('/api/download/<int:task_id>')
@require_auth
def download_video(task_id):
    """下载视频文件"""
    task = db.get_task(task_id)
    if not task or not task['file_path']:
        return jsonify({'error': '文件不存在'}), 404

    download_dir = db.get_setting('download_dir', './downloads')
    filename = os.path.basename(task['file_path'])
    return send_from_directory(download_dir, filename, as_attachment=True)


@app.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    """获取系统设置"""
    settings = db.get_all_settings()
    # 移除敏感信息
    if 'admin_password' in settings:
        del settings['admin_password']
    return jsonify(settings)

@app.route('/api/settings', methods=['POST'])
@require_auth
def update_settings():
    """更新系统设置"""
    data = request.get_json()
    
    # 校验路径是否存在
    path_keys = ['n_m3u8dl_path', 'ffmpeg_path']
    for key in path_keys:
        if key in data:
            path = data[key]
            # 简单的路径检查，如果是命令(如 ffmpeg)则跳过检查，如果是路径则检查存在性
            if '/' in path or '\\' in path:
                if not os.path.exists(path):
                    return jsonify({'error': f'路径不存在: {path}'}), 400
    
    # 更新设置
    for key, value in data.items():
        # 禁止通过此接口修改密码
        if key == 'admin_password':
            continue
        db.set_setting(key, value)
        
    return jsonify({'success': True, 'message': '设置已更新'})

@app.route('/api/settings/apikey', methods=['POST'])
@require_auth
def generate_api_key():
    """生成新的 API Key"""
    new_key = secrets.token_hex(16)
    db.set_setting('api_key', new_key)
    return jsonify({'success': True, 'api_key': new_key})

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取基础配置信息（不需要认证）"""
    n_path = db.get_setting('n_m3u8dl_path')
    f_path = db.get_setting('ffmpeg_path')
    
    return jsonify({
        'n_m3u8dl_exists': os.path.exists(n_path) if ('/' in n_path or '\\' in n_path) else True,
        'ffmpeg_exists': os.path.exists(f_path) if ('/' in f_path or '\\' in f_path) else True,
    })

@app.route('/api/parse/universal', methods=['POST'])
@require_auth
def parse_universal():
    """通用视频解析"""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': '请提供视频链接'}), 400
        
    try:
        # 使用更真实的 Headers 模拟浏览器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # 创建 Session 以维持 Cookie
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=15)
        
        # 如果遇到 403，尝试使用 cloudscraper (如果安装了) 或者提示用户
        if response.status_code == 403:
            try:
                import cloudscraper
                # 创建 scraper 实例，尝试模拟不同的浏览器指纹
                scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'desktop': True
                    }
                )
                response = scraper.get(url)
                # cloudscraper 不会自动抛出 403 异常，需要手动检查
                if response.status_code == 403:
                     return jsonify({'error': '解析失败 (403 Forbidden): 即使使用了 Cloudscraper 也无法绕过防护。请稍后重试或手动获取 M3U8 链接。'}), 403
            except ImportError:
                return jsonify({'error': '解析失败 (403 Forbidden): 目标网站开启了 Cloudflare 防护，服务器未安装 cloudscraper 库。请尝试手动获取 M3U8 链接。'}), 403
            except Exception as e:
                return jsonify({'error': f'Cloudscraper 尝试失败: {str(e)}'}), 500
        
        response.raise_for_status()
        html_content = response.text
        
        # 提取标题
        title = "未命名视频"
        
        def clean_title(text):
            # 去除 HTML 标签
            text = re.sub(r'<[^>]+>', '', text)
            # 去除特殊符号，只保留字母、数字、中文、空格、连字符
            # 这一步是为了防止文件名错乱
            text = re.sub(r'[^\w\s\-\u4e00-\u9fa5]', '', text)
            return text.strip()

        # 仅从 <title> 标签提取
        title_tag_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE)
        if title_tag_match:
            raw_title = title_tag_match.group(1).strip()
            # 通常 title 包含网站名，如 "视频标题 - 网站名"
            # 简单处理：取 - 或 | 前面的部分
            if ' - ' in raw_title:
                raw_title = raw_title.split(' - ')[0]
            elif ' | ' in raw_title:
                raw_title = raw_title.split(' | ')[0]
            
            cleaned = clean_title(raw_title)
            if cleaned:
                title = cleaned

        # 提取 M3U8 链接
        m3u8_urls = set()

        # 规则 1: var hlsUrl = '...'; (Jable)
        matches = re.findall(r"var\s+hlsUrl\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", html_content)
        for m in matches: m3u8_urls.add(m)

        # 规则 2: JSON 格式 "url":"...m3u8" (DPlayer 等)
        # 匹配 "url":"https:\/\/...index.m3u8"
        matches = re.findall(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', html_content)
        for m in matches:
            # 处理转义字符 \/ -> /
            m3u8_urls.add(m.replace('\\/', '/'))

        # 规则 3: <video ... src="..."> 或 <source ... src="...">
        matches = re.findall(r'src\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html_content)
        for m in matches: m3u8_urls.add(m)

        # 规则 4: 通用 http...m3u8 匹配 (最宽泛，可能误判，放在最后)
        # 限制一下，必须以 http 开头，中间不含空白字符
        matches = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)', html_content)
        for m in matches: m3u8_urls.add(m)

        # 过滤无效链接
        valid_urls = []
        for u in m3u8_urls:
            if u.startswith('http'):
                valid_urls.append(u)
        
        if not valid_urls:
            return jsonify({'error': '未找到 M3U8 链接或不支持该网站'}), 400
            
        return jsonify({
            'success': True,
            'count': len(valid_urls),
            'results': valid_urls,
            'title': title
        })
        
    except Exception as e:
        return jsonify({'error': f'解析失败: {str(e)}'}), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理，确保返回 JSON"""
    # 如果是 HTTP 错误，保留状态码
    if hasattr(e, 'code'):
        code = e.code
    else:
        code = 500
    
    # 记录错误堆栈
    app.logger.error(f"发生未捕获异常: {str(e)}")
    app.logger.error(traceback.format_exc())

    return jsonify({
        'error': str(e),
        'success': False,
        'message': '服务器内部错误'
    }), code


if __name__ == '__main__':
    host = '0.0.0.0'
    port = 5000
    debug = False

    print(f"启动服务器: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
