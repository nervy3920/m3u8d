import subprocess
import threading
import os
import re
import json
import time
import shutil
import requests
from urllib.parse import quote
from pathlib import Path
from datetime import datetime
from queue import Queue


class DownloadManager:
    def __init__(self, db):
        self.db = db
        
        self.active_tasks = {}  # task_id: process
        self.waiting_queue = Queue() # 存储等待中的 task_id
        self.queue_lock = threading.Lock()
        
        # 启动队列处理线程
        self.queue_processor = threading.Thread(target=self._queue_processor_worker, daemon=True)
        self.queue_processor.start()

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
        
        # 重置任务状态
        self.db.update_task(task_id, status='pending', progress=0, error_message='', speed='', eta='')
        self.db.add_log(task_id, "任务已加入等待队列")
        
        return True, "任务已加入队列"

    def _queue_processor_worker(self):
        """队列处理线程"""
        while True:
            try:
                # 检查是否可以启动新任务
                with self.queue_lock:
                    current_active = len(self.active_tasks)
                
                max_concurrent = int(self.db.get_setting('max_concurrent_downloads', 3))
                
                if current_active < max_concurrent:
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
            # 获取配置
            n_m3u8dl_path = self.db.get_setting('n_m3u8dl_path', './bin/N_m3u8DL-RE')
            download_dir = self.db.get_setting('download_dir', './downloads')
            temp_dir = self.db.get_setting('temp_dir', './temp')
            
            # 确保目录存在
            Path(download_dir).mkdir(parents=True, exist_ok=True)
            Path(temp_dir).mkdir(parents=True, exist_ok=True)

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
                n_m3u8dl_path,
                url,
                '--save-dir', download_dir,
                '--save-name', save_name,
                '--tmp-dir', temp_dir,
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
                    progress_info = self._parse_progress(line)
                    if progress_info:
                        update_data = {'progress': progress_info['progress']}
                        if 'speed' in progress_info: update_data['speed'] = progress_info['speed']
                        if 'eta' in progress_info: update_data['eta'] = progress_info['eta']
                        if 'total_size' in progress_info: update_data['total_size'] = progress_info['total_size']
                        if 'downloaded_size' in progress_info: update_data['downloaded_size'] = progress_info['downloaded_size']
                        
                        self.db.update_task(task_id, **update_data)

            # 等待进程结束
            return_code = process.wait()

            # 移除活动任务
            with self.queue_lock:
                if task_id in self.active_tasks:
                    del self.active_tasks[task_id]

            if return_code == 0:
                # 下载成功，查找输出文件
                # 传递 download_dir 给 _find_output_file
                output_file = self._find_output_file(save_name, download_dir)

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
                    
                    # Aria2 推送
                    aria2_gid = None
                    if self.db.get_setting('aria2_enabled') == 'true':
                        aria2_gid = self._push_to_aria2(task_id, output_file)
                        
                    # 删除源文件
                    if self.db.get_setting('delete_after_download') == 'true':
                        if aria2_gid:
                            # 如果推送到 Aria2，启动监控线程等待 Aria2 下载完成再删除
                            threading.Thread(
                                target=self._monitor_aria2_and_delete,
                                args=(task_id, aria2_gid, output_file),
                                daemon=True
                            ).start()
                            self.db.add_log(task_id, "已启动 Aria2 监控，将在传输完成后删除源文件")
                        else:
                            # 直接删除
                            try:
                                os.remove(output_file)
                                self.db.add_log(task_id, "源文件已删除 (根据配置)")
                                # 更新 file_path 为空，防止前端尝试播放
                                self.db.update_task(task_id, file_path="")
                            except Exception as e:
                                self.db.add_log(task_id, f"删除源文件失败: {e}")

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
        info = {}
        
        # 1. 匹配进度 (百分比)
        match_progress = re.search(r'(\d+(?:\.\d+)?)\s*%', line)
        if match_progress:
            try:
                info['progress'] = float(match_progress.group(1))
            except:
                pass
        
        if 'progress' not in info:
            return None

        # 2. 匹配速度
        # 格式: 24.69MBps 或 12.5 MB/s
        match_speed = re.search(r'(\d+(?:\.\d+)?\s*[KMGT]?B(?:ps|/s))', line, re.IGNORECASE)
        if match_speed:
            info['speed'] = match_speed.group(1)
            
        # 3. 匹配大小
        # 格式: 602.51MB/1.71GB
        match_size = re.search(r'(\d+(?:\.\d+)?\s*[KMGT]?B)\s*/\s*(\d+(?:\.\d+)?\s*[KMGT]?B)', line, re.IGNORECASE)
        if match_size:
            info['downloaded_size'] = match_size.group(1)
            info['total_size'] = match_size.group(2)

        # 4. 匹配 ETA
        # 格式: 00:00:48 (通常在行尾)
        # 排除开头的 timestamp [xx:xx:xx]
        
        # 尝试匹配 "ETA: 00:00:00"
        match_eta_label = re.search(r'ETA[:\s]+(\d{2}:\d{2}:\d{2})', line, re.IGNORECASE)
        if match_eta_label:
            info['eta'] = match_eta_label.group(1)
        else:
            # 尝试匹配行尾的时间 (针对无 ETA 标签的情况)
            # [00:51:53] ... 00:00:48
            matches_time = re.findall(r'(\d{2}:\d{2}:\d{2})', line)
            if matches_time:
                # 如果有多个时间，最后一个通常是 ETA (第一个可能是日志时间戳)
                # 只有当它看起来像是在行尾时才认为是 ETA
                last_time = matches_time[-1]
                if line.strip().endswith(last_time):
                    info['eta'] = last_time

        return info

    def _find_output_file(self, save_name, download_dir):
        """查找输出文件"""
        # 查找可能的文件扩展名
        extensions = ['.mp4', '.mkv', '.ts', '.m4a']

        for ext in extensions:
            file_path = os.path.join(download_dir, save_name + ext)
            if os.path.exists(file_path):
                return file_path

        # 如果找不到，尝试模糊匹配
        try:
            for file in os.listdir(download_dir):
                if file.startswith(save_name):
                    return os.path.join(download_dir, file)
        except:
            pass

        return None

    def _get_video_duration(self, file_path):
        """获取视频时长"""
        try:
            ffmpeg_path = self.db.get_setting('ffmpeg_path', 'ffmpeg')
            cmd = [
                ffmpeg_path,
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

    def _push_to_aria2(self, task_id, file_path):
        """推送到 Aria2"""
        try:
            rpc_url = self.db.get_setting('aria2_rpc_url')
            rpc_secret = self.db.get_setting('aria2_rpc_secret')
            public_host = self.db.get_setting('public_host', 'http://localhost:5000').rstrip('/')
            
            filename = os.path.basename(file_path)
            file_url = f"{public_host}/videos/{quote(filename)}"
            
            self.db.add_log(task_id, f"正在推送到 Aria2: {file_url}")
            
            payload = {
                "jsonrpc": "2.0",
                "method": "aria2.addUri",
                "id": f"task-{task_id}",
                "params": [
                    [file_url],
                    {
                        "out": filename
                    }
                ]
            }
            
            if rpc_secret:
                payload['params'].insert(0, f"token:{rpc_secret}")
                
            response = requests.post(rpc_url, json=payload, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                gid = result.get('result')
                self.db.add_log(task_id, f"Aria2 推送成功, GID: {gid}")
                if gid:
                    self.db.update_task(task_id, aria2_gid=gid)
                return gid
            else:
                self.db.add_log(task_id, f"Aria2 推送失败: {response.status_code} {response.text}")
                return None
                
        except Exception as e:
            self.db.add_log(task_id, f"Aria2 推送异常: {str(e)}")
            return None

    def _monitor_aria2_and_delete(self, task_id, gid, file_path):
        """监控 Aria2 任务状态并在完成后删除源文件"""
        rpc_url = self.db.get_setting('aria2_rpc_url')
        rpc_secret = self.db.get_setting('aria2_rpc_secret')
        
        max_retries = 60 * 60 # 1 hour timeout (assuming 1s sleep)
        retries = 0
        
        while retries < max_retries:
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "aria2.tellStatus",
                    "id": f"monitor-{task_id}",
                    "params": [gid]
                }
                
                if rpc_secret:
                    payload['params'].insert(0, f"token:{rpc_secret}")
                    
                response = requests.post(rpc_url, json=payload, timeout=5)
                
                if response.status_code == 200:
                    status_data = response.json().get('result', {})
                    status = status_data.get('status')
                    
                    if status == 'complete':
                        self.db.add_log(task_id, "Aria2 下载完成，正在删除源文件")
                        try:
                            os.remove(file_path)
                            self.db.update_task(task_id, file_path="")
                            self.db.add_log(task_id, "源文件已删除")
                        except Exception as e:
                            self.db.add_log(task_id, f"删除源文件失败: {e}")
                        return
                    
                    elif status in ['error', 'removed']:
                        self.db.add_log(task_id, f"Aria2 任务结束状态异常: {status}")
                        return
                        
                time.sleep(2)
                retries += 1
                
            except Exception as e:
                print(f"Aria2 监控异常: {e}")
                time.sleep(5)
                retries += 1
                
        self.db.add_log(task_id, "Aria2 监控超时，未删除源文件")

    def clean_temp_files(self, task_id, custom_name=None):
        """清理临时文件"""
        temp_dir = self.db.get_setting('temp_dir', './temp')
        
        # 尝试构建可能的临时目录名
        # 1. 使用 custom_name
        if custom_name:
            possible_dir = os.path.join(temp_dir, custom_name)
            if os.path.exists(possible_dir) and os.path.isdir(possible_dir):
                try:
                    shutil.rmtree(possible_dir)
                    print(f"已删除临时目录: {possible_dir}")
                except Exception as e:
                    print(f"删除临时目录失败: {e}")
        
        # 2. 使用默认命名规则 (video_{task_id}_...)
        # 由于时间戳不确定，我们需要遍历 temp 目录查找匹配的文件夹
        try:
            prefix = f"video_{task_id}_"
            for item in os.listdir(temp_dir):
                if item.startswith(prefix):
                    full_path = os.path.join(temp_dir, item)
                    if os.path.isdir(full_path):
                        try:
                            shutil.rmtree(full_path)
                            print(f"已删除临时目录: {full_path}")
                        except Exception as e:
                            print(f"删除临时目录失败: {e}")
        except Exception as e:
            print(f"清理临时文件出错: {e}")
