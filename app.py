from flask import Flask, jsonify
from flask_cors import CORS
from pathlib import Path
import traceback

import storage
from downloader import DownloadManager
from utils import SECRET_KEY
from routes.auth import create_auth_blueprint
from routes.views import create_views_blueprint
from routes.api import create_api_blueprint

app = Flask(__name__)

# 确保旧的数据目录与新存储目录存在
Path('./data').mkdir(parents=True, exist_ok=True)
Path('./storage').mkdir(parents=True, exist_ok=True)

app.config['SECRET_KEY'] = SECRET_KEY

CORS(app, supports_credentials=True)

# 初始化基于文件的存储
storage.init_storage()

# 提供一个兼容原先 Database 接口的轻量包装器给其他模块使用
class StorageDB:
    def get_setting(self, key, default=None):
        return storage.get_setting(key, default)

    def set_setting(self, key, value):
        return storage.set_setting(key, value)

    def get_all_settings(self):
        return storage.get_all_settings()

    def create_task(self, url, custom_name=None):
        return storage.create_task(url, custom_name)

    def get_task(self, task_id):
        return storage.get_task(task_id)

    def get_all_tasks(self):
        return storage.get_all_tasks()

    def get_tasks_by_status(self, status):
        return storage.get_tasks_by_status(status)

    def update_task(self, task_id, **kwargs):
        return storage.update_task(task_id, **kwargs)

    def add_log(self, task_id, message):
        return storage.add_log(task_id, message)

    def get_task_logs(self, task_id):
        return storage.get_task_logs(task_id)

    def delete_task(self, task_id):
        return storage.delete_task(task_id)

# 实例化并传递给下载管理器与蓝图
db = StorageDB()

# 初始化下载管理器 (配置将从 storage 读取)
download_manager = DownloadManager(db)

# 注册蓝图
app.register_blueprint(create_auth_blueprint(db))
app.register_blueprint(create_views_blueprint(db))
app.register_blueprint(create_api_blueprint(db, download_manager))

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
