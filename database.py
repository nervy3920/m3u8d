import sqlite3
import json
from datetime import datetime
from pathlib import Path
import os


class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        # 确保数据库目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self):
        # 增加超时时间到 30 秒，防止 database is locked 错误
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """初始化数据库表"""
        conn = self.get_connection()
        
        # 启用 WAL 模式以支持更高的并发
        conn.execute('PRAGMA journal_mode=WAL')
        
        cursor = conn.cursor()

        # 创建任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                file_path TEXT,
                file_size INTEGER,
                duration TEXT,
                error_message TEXT,
                log_file TEXT
            )
        ''')

        # 创建日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                message TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks (id)
            )
        ''')

        conn.commit()
        conn.close()

    def create_task(self, url):
        """创建新任务"""
        conn = self.get_connection()
        cursor = conn.cursor()

        created_at = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO tasks (url, status, created_at)
            VALUES (?, ?, ?)
        ''', (url, 'pending', created_at))

        task_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return task_id

    def get_task(self, task_id):
        """获取任务详情"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        task = cursor.fetchone()

        conn.close()

        if task:
            return dict(task)
        return None

    def get_all_tasks(self):
        """获取所有任务"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM tasks ORDER BY created_at DESC')
        tasks = cursor.fetchall()

        conn.close()

        return [dict(task) for task in tasks]

    def get_tasks_by_status(self, status):
        """根据状态获取任务"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC', (status,))
        tasks = cursor.fetchall()

        conn.close()

        return [dict(task) for task in tasks]

    def update_task(self, task_id, **kwargs):
        """更新任务信息"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 构建更新语句
        fields = []
        values = []
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)

        values.append(task_id)

        query = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"
        cursor.execute(query, values)

        conn.commit()
        conn.close()

    def add_log(self, task_id, message):
        """添加日志"""
        conn = self.get_connection()
        cursor = conn.cursor()

        timestamp = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO logs (task_id, timestamp, message)
            VALUES (?, ?, ?)
        ''', (task_id, timestamp, message))

        conn.commit()
        conn.close()

    def get_task_logs(self, task_id):
        """获取任务日志"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM logs WHERE task_id = ? ORDER BY timestamp ASC
        ''', (task_id,))
        logs = cursor.fetchall()

        conn.close()

        return [dict(log) for log in logs]

    def delete_task(self, task_id):
        """删除任务"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # 删除日志
        cursor.execute('DELETE FROM logs WHERE task_id = ?', (task_id,))
        # 删除任务
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))

        conn.commit()
        conn.close()
