import subprocess
import threading
import os
import re
import json
import time
from pathlib import Path
from datetime import datetime
from queue import Queue


class DownloadManager:
    def __init__(self, db, n_m3u8dl_path, ffmpeg_path, download_dir, temp_dir, max_concurrent=3):
        self.db = db
        self.n_m3u8dl_path = n_m3u8dl_path
        self.ffmpeg_path = ffmpeg_path
        self.download_dir = download_dir
        self.temp_dir = temp_dir
        self.max_concurrent = max_concurrent
        
        self.active_tasks = {}  # task_id: process
        self.waiting_queue = Queue() # 存储等待中的 task_id
        self.queue_lock = threading.Lock()
        
        # 启动队列处理线程
        self.queue_processor = threading.Thread(target=self._queue_processor_worker, daemon=True)
        self.queue_processor.start()

        # 确保目录存在
        Path(download_dir).mkdir(parents=True, exist_ok=True)
        Path(temp_dir).mkdir(parents=True, exist_ok=True)

    def start_download(self, task_id, url, custom_name=None):
        """提交下载任务"""
        if task_id in self.active_tasks:
            return False, "任务已在运行中"
        
        # 将任务加入等待队列
        self.waiting_queue.put({
            'task_id': task_id,
            'url': url,
            'custom_name': custom_name
        })
        
        self.db.update_task(task_id, status='pending')
        self.db.add_log(task_id, "任务已加入等待队列")
        
        return True, "任务已加入队列"

    def _queue_processor_worker(self):
        """队列处理线程"""
        while True:
            try:
                # 检查是否可以启动新任务
                with self.queue_lock:
                    current_active = len(self.active_tasks)
                
                if current_active < self.max_concurrent:
                    if not self.waiting_queue.empty():
                        task_data = self.waiting_queue.get()
                        task_id = task_data['task_id']
                        
                        # 再次检查任务状态，防止已被取消
                        task = self.db.get_task(task_id)
                        if task and task['status'] == 'pending':
                            # 启动下载线程
                            thread = threading.Thread(
                                target=self._download_worker, 
                                args=(task_id, task_data['url'], task_data['custom_name'])
                            )
                            thread.daemon = True
                            thread.start()
                        else:
                            self.db.add_log(task_id, "任务状态异常，跳过执行")
                
                time.sleep(1) # 避免空转过快
            except Exception as e:
                print(f"队列处理器异常: {e}")
                time.sleep(5)

    def _download_worker(self, task_id, url, custom_name=None):
        """下载工作线程"""
        try:
            # 注册为活动任务 (占位，process 稍后赋值)
            with self.queue_lock:
                self.active_tasks[task_id] = None

            # 更新任务状态
            self.db.update_task(task_id,
                              status='downloading',
                              started_at=datetime.now().isoformat())
            self.db.add_log(task_id, "开始下载任务")

            # 生成文件名
            if custom_name:
                save_name = custom_name
            else:
                save_name = f"video_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 构建命令
            cmd = [
                self.n_m3u8dl_path,
                url,
                '--save-dir', self.download_dir,
                '--save-name', save_name,
                '--tmp-dir', self.temp_dir,
                '--thread-count', '16',
                '--download-retry-count', '5',
                '--auto-select',
                '-M', 'format=mp4',
                '--del-after-done',
                '--log-level', 'INFO'
            ]

            self.db.add_log(task_id, f"执行命令: {' '.join(cmd)}")

            # 执行下载
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # 更新 process 对象
            with self.queue_lock:
                if task_id in self.active_tasks:
                    self.active_tasks[task_id] = process
                else:
                    # 任务可能在启动过程中被取消
                    process.terminate()
                    return

            # 读取输出
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.db.add_log(task_id, line)

                    # 解析进度
                    progress = self._parse_progress(line)
                    if progress is not None:
                        self.db.update_task(task_id, progress=progress)

            # 等待进程结束
            return_code = process.wait()

            # 移除活动任务
            with self.queue_lock:
                if task_id in self.active_tasks:
                    del self.active_tasks[task_id]

            if return_code == 0:
                # 下载成功，查找输出文件
                output_file = self._find_output_file(save_name)

                if output_file:
                    file_size = os.path.getsize(output_file)
                    duration = self._get_video_duration(output_file)

                    self.db.update_task(
                        task_id,
                        status='completed',
                        progress=100,
                        completed_at=datetime.now().isoformat(),
                        file_path=output_file,
                        file_size=file_size,
                        duration=duration
                    )
                    self.db.add_log(task_id, f"下载完成: {output_file}")
                else:
                    self.db.update_task(
                        task_id,
                        status='failed',
                        error_message='找不到输出文件'
                    )
                    self.db.add_log(task_id, "错误: 找不到输出文件")
            else:
                # 检查是否是被手动停止的 (return code 通常是负数或特定值)
                # 但这里我们主要依赖 active_tasks 的移除逻辑来判断是否是用户取消
                # 如果是正常流程走到这里且 return_code != 0，那就是失败
                self.db.update_task(
                    task_id,
                    status='failed',
                    error_message=f'下载失败，退出码: {return_code}'
                )
                self.db.add_log(task_id, f"下载失败，退出码: {return_code}")

        except Exception as e:
            self.db.update_task(
                task_id,
                status='failed',
                error_message=str(e)
            )
            self.db.add_log(task_id, f"异常: {str(e)}")

            with self.queue_lock:
                if task_id in self.active_tasks:
                    del self.active_tasks[task_id]

    def _parse_progress(self, line):
        """解析进度信息"""
        # 尝试匹配百分比
        match = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
        if match:
            try:
                return float(match.group(1))
            except:
                pass
        return None

    def _find_output_file(self, save_name):
        """查找输出文件"""
        # 查找可能的文件扩展名
        extensions = ['.mp4', '.mkv', '.ts', '.m4a']

        for ext in extensions:
            file_path = os.path.join(self.download_dir, save_name + ext)
            if os.path.exists(file_path):
                return file_path

        # 如果找不到，尝试模糊匹配
        try:
            for file in os.listdir(self.download_dir):
                if file.startswith(save_name):
                    return os.path.join(self.download_dir, file)
        except:
            pass

        return None

    def _get_video_duration(self, file_path):
        """获取视频时长"""
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', file_path,
                '-hide_banner'
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            # ffmpeg 的信息在 stderr 中
            output = result.stderr

            # 查找 Duration 行
            match = re.search(r'Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d{2})', output)
            if match:
                hours, minutes, seconds = match.groups()
                return f"{hours}:{minutes}:{seconds.split('.')[0]}"
        except:
            pass

        return None

    def stop_download(self, task_id):
        """停止下载任务"""
        # 1. 检查是否在活动任务中
        with self.queue_lock:
            if task_id in self.active_tasks:
                process = self.active_tasks[task_id]
                if process: # 进程已启动
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                
                del self.active_tasks[task_id]
                
                self.db.update_task(task_id, status='cancelled')
                self.db.add_log(task_id, "任务已取消")
                return True, "任务已停止"

        # 2. 检查是否在等待队列中 (需要遍历队列，比较麻烦，简单做法是标记数据库状态)
        # 由于队列取出时会检查数据库状态，所以直接更新数据库即可
        task = self.db.get_task(task_id)
        if task and task['status'] == 'pending':
            self.db.update_task(task_id, status='cancelled')
            self.db.add_log(task_id, "等待中的任务已取消")
            return True, "任务已从队列中取消"

        return False, "任务未在运行或等待中"

    def get_active_tasks(self):
        """获取活动任务列表"""
        with self.queue_lock:
            return list(self.active_tasks.keys())
