from flask import Flask, request, jsonify, send_from_directory, send_file, make_response
from flask_cors import CORS
from dotenv import load_dotenv
import os
from pathlib import Path
from functools import wraps
import hashlib
import secrets

from database import Database
from downloader import DownloadManager

# 加载环境变量
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
CORS(app, supports_credentials=True)

# 初始化配置
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
N_M3U8DL_PATH = os.getenv('N_M3U8DL_PATH', './bin/N_m3u8DL-RE')
FFMPEG_PATH = os.getenv('FFMPEG_PATH', 'ffmpeg')
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', './downloads')
TEMP_DIR = os.getenv('TEMP_DIR', './temp')
DATABASE_PATH = os.getenv('DATABASE_PATH', './data/tasks.db')
MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '3'))

# 初始化数据库和下载管理器
db = Database(DATABASE_PATH)
download_manager = DownloadManager(db, N_M3U8DL_PATH, FFMPEG_PATH, DOWNLOAD_DIR, TEMP_DIR, MAX_CONCURRENT_DOWNLOADS)

# 生成认证令牌
def generate_auth_token(password):
    """生成认证令牌"""
    return hashlib.sha256(f"{password}{app.config['SECRET_KEY']}".encode()).hexdigest()

# 验证令牌
def verify_auth_token(token):
    """验证认证令牌"""
    expected_token = generate_auth_token(ADMIN_PASSWORD)
    return token == expected_token

def require_auth(f):
    """验证密码装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 优先检查 Cookie
        token = request.cookies.get('auth_token')
        if token and verify_auth_token(token):
            return f(*args, **kwargs)

        # 其次检查 Header（兼容旧方式）
        password = request.headers.get('X-Admin-Password')
        if password == ADMIN_PASSWORD:
            return f(*args, **kwargs)

        return jsonify({'error': '未授权，请重新登录'}), 401
    return decorated_function


@app.route('/')
def index():
    """返回前端页面"""
    return send_file('static/index.html')


@app.route('/app.js')
def serve_app_js():
    """返回前端逻辑代码"""
    return send_from_directory('static', 'app.js')


@app.route('/api/auth', methods=['POST'])
def auth():
    """验证密码"""
    data = request.get_json()
    password = data.get('password', '')

    if password == ADMIN_PASSWORD:
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
    token = request.cookies.get('auth_token')
    if token and verify_auth_token(token):
        return jsonify({'authenticated': True})
    return jsonify({'authenticated': False})


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
    task_id = db.create_task(url)

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
@require_auth
def serve_video(filename):
    """提供视频文件"""
    try:
        return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=False)
    except Exception as e:
        return jsonify({'error': f'文件不存在: {str(e)}'}), 404


@app.route('/api/download/<int:task_id>')
@require_auth
def download_video(task_id):
    """下载视频文件"""
    task = db.get_task(task_id)
    if not task or not task['file_path']:
        return jsonify({'error': '文件不存在'}), 404

    filename = os.path.basename(task['file_path'])
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


@app.route('/api/config', methods=['GET'])
def get_config():
    """获取配置信息（不需要认证）"""
    return jsonify({
        'n_m3u8dl_exists': os.path.exists(N_M3U8DL_PATH),
        'ffmpeg_exists': os.path.exists(FFMPEG_PATH) or os.system(f'which {FFMPEG_PATH} > /dev/null 2>&1') == 0,
        'download_dir': DOWNLOAD_DIR,
        'temp_dir': TEMP_DIR
    })


if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    print(f"启动服务器: http://{host}:{port}")
    print(f"N_m3u8DL-RE 路径: {N_M3U8DL_PATH}")
    print(f"FFmpeg 路径: {FFMPEG_PATH}")
    print(f"下载目录: {DOWNLOAD_DIR}")

    app.run(host=host, port=port, debug=debug)
