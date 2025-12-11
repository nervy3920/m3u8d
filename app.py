from flask import Flask, request, jsonify, send_from_directory, send_file, make_response
from flask_cors import CORS
import os
import traceback
from pathlib import Path
from functools import wraps
import hashlib
import secrets
import requests

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


@app.route('/')
def index():
    """返回前端页面"""
    return send_file('static/index.html')


@app.route('/app.js')
def serve_app_js():
    """返回前端逻辑代码"""
    return send_from_directory('static', 'app.js')


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
    if delete_file and task['file_path'] and os.path.exists(task['file_path']):
        try:
            os.remove(task['file_path'])
        except:
            pass

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
