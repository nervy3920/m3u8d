"""
FTP 上传工具模块
支持将下载完成的视频文件上传到 FTP 服务器
"""
import os
import ftplib
from pathlib import Path
from datetime import datetime


class FTPUploader:
    """FTP 上传器"""

    def __init__(self, host, port, username, password, remote_dir='', use_passive=True):
        """
        初始化 FTP 上传器

        Args:
            host: FTP 服务器地址
            port: FTP 端口
            username: 用户名
            password: 密码
            remote_dir: 远程目录路径（可选）
            use_passive: 是否使用被动模式（默认 True）
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.remote_dir = remote_dir
        self.use_passive = use_passive
        self.ftp = None

    def connect(self):
        """连接到 FTP 服务器"""
        try:
            self.ftp = ftplib.FTP()
            self.ftp.connect(self.host, self.port, timeout=30)
            self.ftp.login(self.username, self.password)
            self.ftp.set_pasv(self.use_passive)

            # 切换到指定目录
            if self.remote_dir:
                self._ensure_remote_dir(self.remote_dir)
                self.ftp.cwd(self.remote_dir)

            return True, "FTP 连接成功"
        except Exception as e:
            return False, f"FTP 连接失败: {str(e)}"

    def _ensure_remote_dir(self, path):
        """确保远程目录存在，不存在则创建"""
        if not path or path == '/':
            return

        parts = path.strip('/').split('/')
        current = ''

        for part in parts:
            current += '/' + part
            try:
                self.ftp.cwd(current)
            except ftplib.error_perm:
                try:
                    self.ftp.mkd(current)
                    self.ftp.cwd(current)
                except Exception:
                    pass

    def upload_file(self, local_file, remote_filename=None, callback=None):
        """
        上传文件到 FTP 服务器

        Args:
            local_file: 本地文件路径
            remote_filename: 远程文件名（可选，默认使用本地文件名）
            callback: 进度回调函数，接收 (uploaded_bytes, total_bytes) 参数

        Returns:
            (success, message) 元组
        """
        if not os.path.exists(local_file):
            return False, f"本地文件不存在: {local_file}"

        if not self.ftp:
            success, msg = self.connect()
            if not success:
                return False, msg

        try:
            # 确定远程文件名
            if not remote_filename:
                remote_filename = os.path.basename(local_file)

            # 获取文件大小
            file_size = os.path.getsize(local_file)
            uploaded_size = 0

            # 定义进度回调
            def progress_callback(data):
                nonlocal uploaded_size
                uploaded_size += len(data)
                if callback:
                    callback(uploaded_size, file_size)

            # 上传文件
            with open(local_file, 'rb') as f:
                self.ftp.storbinary(f'STOR {remote_filename}', f, blocksize=8192, callback=progress_callback)

            return True, f"文件上传成功: {remote_filename}"

        except Exception as e:
            return False, f"文件上传失败: {str(e)}"

    def disconnect(self):
        """断开 FTP 连接"""
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                try:
                    self.ftp.close()
                except Exception:
                    pass
            finally:
                self.ftp = None

    def __enter__(self):
        """支持 with 语句"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.disconnect()


def test_ftp_connection(host, port, username, password, remote_dir=''):
    """
    测试 FTP 连接

    Returns:
        (success, message) 元组
    """
    try:
        uploader = FTPUploader(host, port, username, password, remote_dir)
        success, msg = uploader.connect()
        uploader.disconnect()
        return success, msg
    except Exception as e:
        return False, f"测试连接失败: {str(e)}"
