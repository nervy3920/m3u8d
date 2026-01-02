"""
storage.py

基于文件系统的简单存储层：
- ./storage/settings.json: 存储系统设置（键值对）
- ./storage/tasks/: 每个任务一个 JSON 文件，文件名为 {id}.json
- ./storage/tasks/logs/: 每个任务的日志文件 {id}.log

提供的主要 API（面向替换 Database）：
- init_storage()
- get_setting(key, default=None)
- set_setting(key, value)
- get_all_settings()
- create_task(url, custom_name=None) -> task_id
- get_task(task_id) -> dict or None
- get_all_tasks() -> list[dict]
- get_tasks_by_status(status) -> list[dict]
- update_task(task_id, **kwargs)
- delete_task(task_id)
- add_log(task_id, message)
- get_task_logs(task_id) -> list[dict]
"""
import os
import json
from pathlib import Path
from datetime import datetime
import threading

LOCK = threading.Lock()

STORAGE_DIR = Path('./storage')
SETTINGS_PATH = STORAGE_DIR / 'settings.json'
TASKS_DIR = STORAGE_DIR / 'tasks'
LOGS_DIR = TASKS_DIR / 'logs'

DEFAULT_SETTINGS = {
    'max_concurrent_downloads': '3',
    'n_m3u8dl_path': './bin/N_m3u8DL-RE',
    'ffmpeg_path': './bin/ffmpeg',
    'download_dir': './downloads',
    'temp_dir': './temp',
    'aria2_enabled': 'false',
    'aria2_rpc_url': 'http://localhost:6800/jsonrpc',
    'aria2_rpc_secret': '',
    'aria2_out_dir': '',  # 可选：Aria2 在远端保存的目录（留空则使用 Aria2 默认）
    'delete_after_download': 'false',
    'public_host': 'http://localhost:5000',
    'api_enabled': 'false',
    'api_key': '',
    'ftp_enabled': 'false',
    'ftp_host': '',
    'ftp_port': '21',
    'ftp_username': '',
    'ftp_password': '',
    'ftp_remote_dir': '',
    'ftp_passive_mode': 'true',
    'ftp_delete_after_upload': 'false'
}


def init_storage():
    """确保存储目录和基础文件存在；如果 settings.json 不存在则写入默认设置。"""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not SETTINGS_PATH.exists():
        save_settings(DEFAULT_SETTINGS)


def load_settings():
    """读取 settings.json，返回 dict"""
    init_storage()
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        # 备份并重建默认
        try:
            SETTINGS_PATH.rename(SETTINGS_PATH.with_suffix('.json.bak'))
        except Exception:
            pass
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """将 dict 写入 settings.json 原子写入"""
    # 不在此处调用 init_storage() 避免循环调用（init_storage -> save_settings -> init_storage）
    # 确保目录存在
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    tmp.replace(SETTINGS_PATH)


def get_setting(key, default=None):
    settings = load_settings()
    return settings.get(key, default)


def set_setting(key, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)


def get_all_settings():
    return load_settings()


def _task_path(task_id):
    return TASKS_DIR / f"{task_id}.json"


def _log_path(task_id):
    return LOGS_DIR / f"{task_id}.log"


def _read_task_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _write_task_file(task_id, data):
    path = _task_path(task_id)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _next_task_id():
    """扫描 tasks 目录，返回下一个可用的整数 ID"""
    init_storage()
    max_id = 0
    for p in TASKS_DIR.glob("*.json"):
        try:
            n = int(p.stem)
            if n > max_id:
                max_id = n
        except Exception:
            continue
    return max_id + 1


def create_task(url, custom_name=None):
    """创建新任务，返回任务 id"""
    init_storage()
    with LOCK:
        task_id = _next_task_id()
        now = datetime.now().isoformat()
        task = {
            'id': task_id,
            'url': url,
            'status': 'pending',
            'progress': 0.0,
            'created_at': now,
            'started_at': None,
            'completed_at': None,
            'file_path': '',
            'file_size': None,
            'duration': None,
            'error_message': '',
            'log_file': str(_log_path(task_id)),
            'custom_name': custom_name,
            'speed': '',
            'eta': '',
            'total_size': '',
            'downloaded_size': '',
            'aria2_gid': ''
        }
        _write_task_file(task_id, task)
    return task_id


def get_task(task_id):
    path = _task_path(task_id)
    if not path.exists():
        return None
    return _read_task_file(path)


def get_all_tasks():
    init_storage()
    tasks = []
    for p in TASKS_DIR.glob("*.json"):
        data = _read_task_file(p)
        if data:
            tasks.append(data)
    # 按 created_at 降序排序（兼容原有行为）
    try:
        tasks.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    except Exception:
        pass
    return tasks


def get_tasks_by_status(status):
    return [t for t in get_all_tasks() if t.get('status') == status]


def update_task(task_id, **kwargs):
    """原子更新任务 JSON 中的字段"""
    path = _task_path(task_id)
    if not path.exists():
        return False
    with LOCK:
        task = _read_task_file(path)
        if not task:
            return False
        for k, v in kwargs.items():
            # 只允许更新白名单字段，防止注入或不小心覆盖重要字段
            if k in [
                'url', 'status', 'progress', 'started_at', 'completed_at',
                'file_path', 'file_size', 'duration', 'error_message',
                'log_file', 'custom_name', 'speed', 'eta', 'total_size',
                'downloaded_size', 'aria2_gid'
            ]:
                task[k] = v
        _write_task_file(task_id, task)
    return True


def delete_task(task_id):
    """删除任务 JSON 与日志文件"""
    path = _task_path(task_id)
    log = _log_path(task_id)
    with LOCK:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        try:
            if log.exists():
                log.unlink()
        except Exception:
            pass
    return True


def add_log(task_id, message):
    """向任务日志追加一行，并确保在任务 JSON 中保留简短信息"""
    init_storage()
    ts = datetime.now().isoformat()
    line = f"[{ts}] {message}\n"
    logp = _log_path(task_id)
    # 确保任务存在，否则不写入日志（避免删除后出现幽灵任务）
    if not _task_path(task_id).exists():
        return

    try:
        with open(logp, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass
    # 也把最新的关键字段写到 task json（例如 error_message）
    try:
        update_task(task_id, updated_at=ts)
    except Exception:
        pass


def get_task_logs(task_id):
    """返回日志的行数组，每行包含 timestamp 与 message"""
    logp = _log_path(task_id)
    if not logp.exists():
        return []
    out = []
    try:
        with open(logp, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 格式: [ISO] message
                if line.startswith('['):
                    try:
                        idx = line.find(']')
                        ts = line[1:idx]
                        msg = line[idx+2:] if len(line) > idx+2 else ''
                    except Exception:
                        ts = ''
                        msg = line
                else:
                    ts = ''
                    msg = line
                out.append({'timestamp': ts, 'message': msg})
    except Exception:
        pass
    return out

