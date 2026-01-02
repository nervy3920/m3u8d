
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
from ftp_uploader import FTPUploader

class DownloadManager:
    def __init__(self, db):
        self.db = db
        
        self.active_tasks = {}  # task_id: process
        self.waiting_queue = Queue() # 存储等待中的 task_id
        self.queue_lock = threading.Lock()
        # 取消标志，用于在任务尚未启动或正在运行时请求取消
        self.cancel_flags = {}  # task_id: threading.Event()
        
        # 启动队列处理线程
        self.queue_processor = threading.Thread(target=self._queue_processor_worker, daemon=True)
        self.queue_processor.start()

    def start_download(self, task_id, url, custom_name=None):
        """提交下载任务"""
        # 如果已在活动任务中，拒绝重复提交
        with self.queue_lock:
            if task_id in self.active_tasks:
                return False, "任务已在运行中"
            # 初始化/清除取消标志
            self.cancel_flags[task_id] = threading.Event()
        
        # 将任务加入等待队列
        self.waiting_queue.put({
            'task_id': task_id,
            'url': url,
            'custom_name': custom_name
        })
        
        # 重置任务状态（pending）
        try:
            self.db.update_task(task_id, status='pending', progress=0, error_message='', speed='', eta='')
            self.db.add_log(task_id, "任务已加入等待队列")
        except Exception:
            pass
        
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
                        
                        # 如果取消标志已被设置，跳过此任务
                        with self.queue_lock:
                            cancel_event = self.cancel_flags.get(task_id)
                        if cancel_event and cancel_event.is_set():
                            try:
                                self.db.update_task(task_id, status='cancelled')
                                self.db.add_log(task_id, "任务在队列中被取消")
                            except Exception:
                                pass
                            continue
                        
                        # 再次检查任务状态，防止已被取消或状态异常
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
                            try:
                                self.db.add_log(task_id, "任务状态异常，跳过执行")
                            except Exception:
                                pass
                
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
            try:
                self.db.update_task(task_id,
                                  status='downloading',
                                  started_at=datetime.now().isoformat())
                self.db.add_log(task_id, "开始下载任务")
            except Exception:
                pass

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

            try:
                self.db.add_log(task_id, f"执行命令: {' '.join(cmd)}")
            except Exception:
                pass

            # 执行下载：使用新会话以便更可靠地终止子进程，并设置 close_fds 以避免文件描述符泄露
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                close_fds=True,
                start_new_session=True
            )

            # 更新 process 对象
            with self.queue_lock:
                if task_id in self.active_tasks:
                    self.active_tasks[task_id] = process
                else:
                    # 任务可能在启动过程中被取消
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    return

            # 读取输出：放在单独线程中读取 stdout，避免主线程被阻塞或因编码问题造成问题
            def _stdout_reader(proc, tid):
                try:
                    last_progress = None
                    last_update_time = 0
                    while True:
                        line = proc.stdout.readline()
                        if line == '' and proc.poll() is not None:
                            break
                        if not line:
                            # 短暂等待以避免 busy loop
                            time.sleep(0.1)
                            continue
                        line = line.strip()
                        if line:
                            try:
                                self.db.add_log(tid, line)
                            except Exception:
                                pass
                            try:
                                progress_info = self._parse_progress(line)
                                if progress_info:
                                    update_data = {'progress': progress_info['progress']}
                                    if 'speed' in progress_info: update_data['speed'] = progress_info['speed']
                                    if 'eta' in progress_info: update_data['eta'] = progress_info['eta']
                                    if 'total_size' in progress_info: update_data['total_size'] = progress_info['total_size']
                                    if 'downloaded_size' in progress_info: update_data['downloaded_size'] = progress_info['downloaded_size']
                                    try:
                                        # 节流：1s 内最多一次或进度变化显著时写 DB
                                        now_ts = time.time()
                                        if (now_ts - last_update_time) >= 1 or last_progress is None or abs(update_data.get('progress', 0) - (last_progress or 0)) >= 0.5:
                                            self.db.update_task(tid, **update_data)
                                            last_update_time = now_ts
                                            last_progress = update_data.get('progress', last_progress)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                except Exception as e:
                    try:
                        self.db.add_log(tid, f"读取日志线程异常: {e}")
                    except Exception:
                        pass

            reader_thread = threading.Thread(target=_stdout_reader, args=(process, task_id), daemon=True)
            reader_thread.start()

            # 等待进程结束（主线程仅等待，不再直接读 stdout）
            try:
                while True:
                    if process.poll() is not None:
                        break
                    # 检查取消标志，如果被设置则尝试优雅结束
                    with self.queue_lock:
                        cancel_event = self.cancel_flags.get(task_id)
                    if cancel_event and cancel_event.is_set():
                        try:
                            process.terminate()
                        except Exception:
                            pass
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            try:
                                process.kill()
                            except Exception:
                                pass
                        break
                    time.sleep(0.5)
            except Exception as e:
                try:
                    self.db.add_log(task_id, f"等待进程结束时异常: {e}")
                except Exception:
                    pass
            # 确保 reader 线程结束
            try:
                reader_thread.join(timeout=2)
            except Exception:
                pass
            return_code = process.returncode if process.returncode is not None else (process.wait() if process.poll() is None else process.returncode)

            # 移除活动任务
            with self.queue_lock:
                if task_id in self.active_tasks:
                    try:
                        del self.active_tasks[task_id]
                    except Exception:
                        pass
                # 清理取消标志
                if task_id in self.cancel_flags:
                    try:
                        del self.cancel_flags[task_id]
                    except Exception:
                        pass

            if return_code == 0:
                # 下载成功，查找输出文件
                output_file = self._find_output_file(save_name, download_dir)

                if output_file:
                    try:
                        file_size = os.path.getsize(output_file)
                    except Exception:
                        file_size = None
                    try:
                        duration = self._get_video_duration(output_file)
                    except Exception:
                        duration = None

                    try:
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
                    except Exception:
                        pass
                    
                    # Aria2 推送
                    aria2_gid = None
                    try:
                        if self.db.get_setting('aria2_enabled') == 'true':
                            aria2_gid = self._push_to_aria2(task_id, output_file)
                    except Exception:
                        aria2_gid = None

                    # FTP 上传
                    ftp_uploaded = False
                    try:
                        if self.db.get_setting('ftp_enabled') == 'true':
                            ftp_uploaded = self._upload_to_ftp(task_id, output_file)
                    except Exception:
                        ftp_uploaded = False

                    # 删除源文件
                    try:
                        # FTP 上传后删除
                        if ftp_uploaded and self.db.get_setting('ftp_delete_after_upload') == 'true':
                            try:
                                os.remove(output_file)
                                try:
                                    self.db.add_log(task_id, "FTP 上传完成，源文件已删除")
                                except Exception:
                                    pass
                                # 更新 file_path 为空
                                try:
                                    task = self.db.get_task(task_id)
                                    if task and not task.get('custom_name'):
                                        filename = os.path.basename(output_file)
                                        self.db.update_task(task_id, custom_name=filename)
                                    self.db.update_task(task_id, file_path="")
                                except Exception:
                                    pass
                            except Exception as e:
                                try:
                                    self.db.add_log(task_id, f"删除源文件失败: {e}")
                                except Exception:
                                    pass
                        # Aria2 推送后删除
                        elif self.db.get_setting('delete_after_download') == 'true':
                            if aria2_gid:
                                # 如果推送到 Aria2，启动监控线程等待 Aria2 下载完成再删除
                                threading.Thread(
                                    target=self._monitor_aria2_and_delete,
                                    args=(task_id, aria2_gid, output_file),
                                    daemon=True
                                ).start()
                                try:
                                    self.db.add_log(task_id, "已启动 Aria2 监控，将在传输完成后删除源文件")
                                except Exception:
                                    pass
                            else:
                                # 直接删除
                                try:
                                    os.remove(output_file)
                                    try:
                                        self.db.add_log(task_id, "源文件已删除 (根据配置)")
                                    except Exception:
                                        pass
                                    # 更新 file_path 为空，防止前端尝试播放
                                    try:
                                        task = self.db.get_task(task_id)
                                        if task and not task.get('custom_name'):
                                            filename = os.path.basename(output_file)
                                            self.db.update_task(task_id, custom_name=filename)
                                        self.db.update_task(task_id, file_path="")
                                    except Exception:
                                        pass
                                except Exception as e:
                                    try:
                                        self.db.add_log(task_id, f"删除源文件失败: {e}")
                                    except Exception:
                                        pass
                    except Exception:
                        pass

                else:
                    try:
                        self.db.update_task(
                            task_id,
                            status='failed',
                            error_message='找不到输出文件'
                        )
                        self.db.add_log(task_id, "错误: 找不到输出文件")
                    except Exception:
                        pass
            else:
                # 检查是否是被手动停止的 (return code 通常是负数或特定值)
                try:
                    self.db.update_task(
                        task_id,
                        status='failed',
                        error_message=f'下载失败，退出码: {return_code}'
                    )
                    self.db.add_log(task_id, f"下载失败，退出码: {return_code}")
                except Exception:
                    pass

        except Exception as e:
            try:
                self.db.update_task(
                    task_id,
                    status='failed',
                    error_message=str(e)
                )
                self.db.add_log(task_id, f"异常: {str(e)}")
            except Exception:
                pass

            with self.queue_lock:
                if task_id in self.active_tasks:
                    try:
                        del self.active_tasks[task_id]
                    except Exception:
                        pass

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

        # 5. 匹配合并状态
        if "Merging" in line or "muxing" in line.lower():
             info['progress'] = 100
             info['speed'] = '合并中...'
             info['eta'] = '请稍候'

        return info

    def _find_output_file(self, save_name, download_dir):
        """查找输出文件"""
        # 查找可能的文件扩展名
        extensions = ['.mp4', '.mkv', '.ts', '.m4a']

        for ext in extensions:
            file_path = os.path.join(download_dir, save_name + ext)
            if os.path.exists(file_path):
                return file_path

        # 如果找不到，尝试模糊匹配并选择最近修改的匹配文件作为回退
        try:
            candidates = []
            for file in os.listdir(download_dir):
                if file.startswith(save_name):
                    full = os.path.join(download_dir, file)
                    try:
                        mtime = os.path.getmtime(full)
                        candidates.append((mtime, full))
                    except Exception:
                        candidates.append((0, full))
            if candidates:
                candidates.sort(reverse=True)
                return candidates[0][1]
        except Exception:
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
        # 设置取消标志，优先通知等待/运行线程
        with self.queue_lock:
            cancel_event = self.cancel_flags.get(task_id)
            if cancel_event:
                cancel_event.set()

            if task_id in self.active_tasks:
                process = self.active_tasks[task_id]
                if process: # 进程已启动
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            process.kill()
                        except Exception:
                            pass
                
                try:
                    del self.active_tasks[task_id]
                except Exception:
                    pass
                
                try:
                    self.db.update_task(task_id, status='cancelled')
                    self.db.add_log(task_id, "任务已取消")
                except Exception:
                    pass
                return True, "任务已停止"

        # 检查是否在等待队列中 (需要遍历队列，比较麻烦，简单做法是标记取消标志)
        task = self.db.get_task(task_id)
        if task and task['status'] == 'pending':
            try:
                # 设置取消标志会让队列处理线程跳过该任务
                with self.queue_lock:
                    if task_id not in self.cancel_flags:
                        self.cancel_flags[task_id] = threading.Event()
                    self.cancel_flags[task_id].set()
                self.db.update_task(task_id, status='cancelled')
                self.db.add_log(task_id, "等待中的任务已取消")
            except Exception:
                pass
            return True, "任务已从队列中取消"

        return False, "任务未在运行或等待中"

    def get_active_tasks(self):
        """获取活动任务列表"""
        with self.queue_lock:
            return list(self.active_tasks.keys())

    def _push_to_aria2(self, task_id, file_path):
        """推送到 Aria2。支持可选设置 aria2_out_dir（在 storage settings 中）作为 aria2 的 dir 参数。"""
        try:
            rpc_url = self.db.get_setting('aria2_rpc_url')
            rpc_secret = self.db.get_setting('aria2_rpc_secret')
            public_host = self.db.get_setting('public_host', 'http://localhost:5000').rstrip('/')
            aria2_out_dir = self.db.get_setting('aria2_out_dir', '') or ''
            
            filename = os.path.basename(file_path)
            file_url = f"{public_host}/videos/{quote(filename)}"
            
            self.db.add_log(task_id, f"正在推送到 Aria2: {file_url}")
            
            options = {
                "out": filename
            }
            # 如果配置了远端目录，传递 dir 参数给 aria2
            if aria2_out_dir:
                options['dir'] = aria2_out_dir

            params = [[file_url], options]

            payload = {
                "jsonrpc": "2.0",
                "method": "aria2.addUri",
                "id": f"task-{task_id}",
                "params": params
            }
            
            # 如果设置了 secret，需要把 token 放到 params 开头
            if rpc_secret:
                payload['params'].insert(0, f"token:{rpc_secret}")
                
            try:
                response = requests.post(rpc_url, json=payload, timeout=10)
            except Exception as e:
                self.db.add_log(task_id, f"Aria2 RPC 请求失败: {e}")
                return None
            
            if response.status_code == 200:
                try:
                    result = response.json()
                except Exception:
                    self.db.add_log(task_id, f"Aria2 返回不可解析的 JSON: {response.text}")
                    return None

                gid = result.get('result')
                self.db.add_log(task_id, f"Aria2 推送成功, GID: {gid}")
                if gid:
                    try:
                        self.db.update_task(task_id, aria2_gid=gid)
                    except Exception:
                        pass
                return gid
            else:
                self.db.add_log(task_id, f"Aria2 推送失败: {response.status_code} {response.text}")
                return None
                
        except Exception as e:
            try:
                self.db.add_log(task_id, f"Aria2 推送异常: {str(e)}")
            except Exception:
                pass
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
                            # 保留文件名以便前端显示，只清空路径或标记为已删除
                            # 这里我们不把 file_path 设为空，而是设为一个特殊标记或者保留原路径但增加一个 deleted 标记
                            # 但为了兼容现有逻辑，我们可以把 file_path 设为空，但确保 custom_name 或其他字段存有文件名
                            # 实际上，前端显示逻辑优先取 custom_name，其次取 file_path 的 basename
                            # 如果 file_path 被清空，且没有 custom_name，前端就无法显示文件名了
                            # 解决方案：在清空 file_path 之前，确保 custom_name 有值（如果是自动生成的）
                            
                            task = self.db.get_task(task_id)
                            if task and not task.get('custom_name'):
                                # 如果没有自定义名，把当前文件名保存为自定义名
                                filename = os.path.basename(file_path)
                                self.db.update_task(task_id, custom_name=filename)
                                
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
        
        # 1. 尝试删除以 task_id 命名的临时目录（如果有）
        # N_m3u8DL-RE 可能会创建以 save_name 为前缀的临时目录
        if custom_name:
            save_name = custom_name
        else:
            # 这里很难精确知道自动生成的 save_name 中的时间戳，
            # 但通常 N_m3u8DL-RE 会在 temp_dir 下创建临时文件
            # 如果我们无法精确匹配，可能只能依赖 N_m3u8DL-RE 的 --del-after-done
            pass
            
        # 简单实现：尝试删除 temp_dir 下包含 task_id 的文件或目录
        # 注意：这可能不完全准确，取决于 N_m3u8DL-RE 的行为
        try:
            for item in os.listdir(temp_dir):
                if str(task_id) in item:
                    full_path = os.path.join(temp_dir, item)
                    if os.path.isdir(full_path):
                        shutil.rmtree(full_path, ignore_errors=True)
                    else:
                        os.remove(full_path)
        except Exception:
            pass

    def _upload_to_ftp(self, task_id, file_path):
        """上传文件到 FTP 服务器"""
        try:
            # 获取 FTP 配置
            ftp_host = self.db.get_setting('ftp_host', '')
            ftp_port_str = self.db.get_setting('ftp_port', '21')
            ftp_port = int(ftp_port_str) if ftp_port_str and ftp_port_str.strip() else 21
            ftp_username = self.db.get_setting('ftp_username', '')
            ftp_password = self.db.get_setting('ftp_password', '')
            ftp_remote_dir = self.db.get_setting('ftp_remote_dir', '')
            ftp_passive = self.db.get_setting('ftp_passive_mode', 'true') == 'true'

            if not ftp_host or not ftp_username:
                self.db.add_log(task_id, "FTP 配置不完整，跳过上传")
                return False

            self.db.add_log(task_id, f"开始上传到 FTP: {ftp_host}")

            # 创建 FTP 上传器
            uploader = FTPUploader(
                host=ftp_host,
                port=ftp_port,
                username=ftp_username,
                password=ftp_password,
                remote_dir=ftp_remote_dir,
                use_passive=ftp_passive
            )

            # 连接 FTP
            success, msg = uploader.connect()
            if not success:
                self.db.add_log(task_id, f"FTP 连接失败: {msg}")
                return False

            self.db.add_log(task_id, "FTP 连接成功，开始上传文件...")

            # 上传文件，带进度回调
            def progress_callback(uploaded, total):
                try:
                    progress = (uploaded / total) * 100 if total > 0 else 0
                    if int(progress) % 10 == 0:  # 每 10% 记录一次
                        self.db.add_log(task_id, f"FTP 上传进度: {progress:.1f}%")
                except Exception:
                    pass

            filename = os.path.basename(file_path)
            success, msg = uploader.upload_file(file_path, filename, progress_callback)

            uploader.disconnect()

            if success:
                self.db.add_log(task_id, f"FTP 上传成功: {filename}")
                return True
            else:
                self.db.add_log(task_id, f"FTP 上传失败: {msg}")
                return False

        except Exception as e:
            try:
                self.db.add_log(task_id, f"FTP 上传异常: {str(e)}")
            except Exception:
                pass
            return False
