from flask import Blueprint, request, jsonify, send_from_directory
from utils import require_auth
import os
import requests
import re
import secrets
import traceback
import threading

def create_api_blueprint(db, download_manager):
    api_bp = Blueprint('api', __name__)

    @api_bp.route('/api/tasks', methods=['GET'])
    @require_auth(db)
    def get_tasks():
        """获取所有任务，支持 status 参数和分页（page, per_page）"""
        status = request.args.get('status')
        try:
            page = int(request.args.get('page', '1'))
            per_page = int(request.args.get('per_page', '20'))
        except Exception:
            page = 1
            per_page = 20
        page = max(1, page)
        per_page = max(1, per_page)

        if status:
            tasks = db.get_tasks_by_status(status)
        else:
            tasks = db.get_all_tasks()

        total = len(tasks)
        total_pages = (total + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        page_tasks = tasks[start:end]

        return jsonify({
            'tasks': page_tasks,
            'pagination': {
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': total_pages
            }
        })

    @api_bp.route('/api/tasks', methods=['POST'])
    @require_auth(db)
    def create_task():
        """
        创建新任务
        支持单个提交和批量提交：
        - 单个：{ "url": "http://...m3u8", "name": "optional" }
        - 批量：{ "text": "http...\\nhttp...|name\\n..." } 或 提交单个 url 字段包含多行
        响应会尽快返回，并在后台启动下载以避免提交时阻塞。
        """
        data = request.get_json() or {}
        text = (data.get('text') or '').strip()
        url = (data.get('url') or '').strip()
        custom_name = (data.get('name') or '').strip() or None

        lines = []
        # 优先处理 text（批量）
        if text:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                lines.append(line)
        else:
            # 如果 url 包含多行，也当作批量
            if '\n' in url:
                for line in url.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    lines.append(line)
            elif url:
                lines.append(url)
            else:
                return jsonify({'error': '请提供下载链接或文本批量内容'}), 400

        created = []
        for entry in lines:
            # 支持 "url|filename" 的格式
            if '|' in entry:
                parts = entry.split('|', 1)
                u = parts[0].strip()
                name = parts[1].strip() or None
            else:
                u = entry
                # 如果是单条提交且没有在 url 中指定 name，则使用传入的 custom_name
                # 注意：如果是批量提交（text 不为空），custom_name 通常为空，除非用户想给所有批量任务同一个名字（不太合理）
                # 这里逻辑是：如果 entry 来自 text，则 name 为 None（除非 | 指定）；
                # 如果 entry 来自 url（单条），则 name 为 custom_name
                if not text and len(lines) == 1:
                     name = custom_name
                else:
                     name = None
            
            if not u:
                continue
            tid = db.create_task(u, name)
            created.append({'task_id': tid, 'url': u, 'name': name})

        # 后台启动下载，避免阻塞 HTTP 响应
        def _start_tasks(tasks):
            for it in tasks:
                try:
                    download_manager.start_download(it['task_id'], it['url'], it.get('name'))
                except Exception as e:
                    # 记录失败到日志
                    try:
                        db.add_log(it['task_id'], f"start_download error: {str(e)}")
                        db.update_task(it['task_id'], status='failed', error_message=str(e))
                    except Exception:
                        pass

        if created:
            t = threading.Thread(target=_start_tasks, args=(created,), daemon=True)
            t.start()

        return jsonify({
            'success': True,
            'created': created,
            'count': len(created)
        })

    @api_bp.route('/api/tasks/<int:task_id>', methods=['GET'])
    @require_auth(db)
    def get_task(task_id):
        """获取任务详情"""
        task = db.get_task(task_id)

        if not task:
            return jsonify({'error': '任务不存在'}), 404

        return jsonify({'task': task})

    @api_bp.route('/api/tasks/<int:task_id>/logs', methods=['GET'])
    @require_auth(db)
    def get_task_logs(task_id):
        """获取任务日志"""
        logs = db.get_task_logs(task_id)
        return jsonify({'logs': logs})

    @api_bp.route('/api/tasks/<int:task_id>/stop', methods=['POST'])
    @require_auth(db)
    def stop_task(task_id):
        """停止任务"""
        success, message = download_manager.stop_download(task_id)

        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'error': message}), 400

    @api_bp.route('/api/tasks/<int:task_id>/retry', methods=['POST'])
    @require_auth(db)
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

    @api_bp.route('/api/tasks/<int:task_id>', methods=['DELETE'])
    @require_auth(db)
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
            
            # 2. 删除临时文件
            download_manager.clean_temp_files(task_id, task.get('custom_name'))

        # 删除数据库记录
        db.delete_task(task_id)
    
        return jsonify({'success': True, 'message': '任务已删除'})

    @api_bp.route('/api/tasks/batch-delete', methods=['POST'])
    @require_auth(db)
    def batch_delete_tasks():
        """
        批量删除任务（请求 JSON: { ids: [1,2,3], delete_file: true }）
        会先停止正在运行的任务，再删除文件/临时文件（可选），最后删除任务记录。
        返回每个 id 的处理结果。
        """
        data = request.get_json() or {}
        ids = data.get('ids') or []
        delete_file = data.get('delete_file', True)

        if not isinstance(ids, list):
            return jsonify({'error': 'ids 必须为数组'}), 400

        results = []
        for tid in ids:
            try:
                tid_int = int(tid)
            except Exception:
                results.append({'id': tid, 'status': 'invalid_id'})
                continue

            task = db.get_task(tid_int)
            if not task:
                results.append({'id': tid_int, 'status': 'not_found'})
                continue

            # 停止运行中的任务
            try:
                if tid_int in download_manager.get_active_tasks():
                    download_manager.stop_download(tid_int)
            except Exception as e:
                # 记录但继续处理删除
                try:
                    db.add_log(tid_int, f"stop before delete error: {str(e)}")
                except Exception:
                    pass

            # 删除文件（可选）
            if delete_file:
                try:
                    if task.get('file_path') and os.path.exists(task.get('file_path')):
                        os.remove(task.get('file_path'))
                except Exception:
                    pass
                try:
                    download_manager.clean_temp_files(tid_int, task.get('custom_name'))
                except Exception:
                    pass

            # 删除记录与日志
            try:
                db.delete_task(tid_int)
                results.append({'id': tid_int, 'status': 'deleted'})
            except Exception as e:
                results.append({'id': tid_int, 'status': 'error', 'message': str(e)})

        return jsonify({'success': True, 'results': results})

    @api_bp.route('/api/stats', methods=['GET'])
    @require_auth(db)
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

    @api_bp.route('/api/download/<int:task_id>')
    @require_auth(db)
    def download_video(task_id):
        """下载视频文件"""
        task = db.get_task(task_id)
        if not task or not task['file_path']:
            return jsonify({'error': '文件不存在'}), 404

        download_dir = db.get_setting('download_dir', './downloads')
        filename = os.path.basename(task['file_path'])
        return send_from_directory(download_dir, filename, as_attachment=True)

    @api_bp.route('/api/settings', methods=['GET'])
    @require_auth(db)
    def get_settings():
        """获取系统设置"""
        settings = db.get_all_settings()
        # 移除敏感信息
        if 'admin_password' in settings:
            del settings['admin_password']
        return jsonify(settings)

    @api_bp.route('/api/settings', methods=['POST'])
    @require_auth(db)
    def update_settings():
        """更新系统设置"""
        data = request.get_json()
        
        # 校验路径是否存在
        path_keys = ['n_m3u8dl_path', 'ffmpeg_path', 'chromedriver_path']
        for key in path_keys:
            if key in data:
                path = data[key]
                if not path: continue # 允许为空
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

    @api_bp.route('/api/settings/apikey', methods=['POST'])
    @require_auth(db)
    def generate_api_key():
        """生成新的 API Key"""
        new_key = secrets.token_hex(16)
        db.set_setting('api_key', new_key)
        return jsonify({'success': True, 'api_key': new_key})

    @api_bp.route('/api/config', methods=['GET'])
    def get_config():
        """获取基础配置信息（不需要认证）"""
        n_path = db.get_setting('n_m3u8dl_path')
        f_path = db.get_setting('ffmpeg_path')
        
        return jsonify({
            'n_m3u8dl_exists': os.path.exists(n_path) if ('/' in n_path or '\\' in n_path) else True,
            'ffmpeg_exists': os.path.exists(f_path) if ('/' in f_path or '\\' in f_path) else True,
        })

    def _parse_video_logic(url, use_selenium):
        """内部解析逻辑，返回字典或抛出异常"""
        html_content = ""
        
        if use_selenium:
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                from selenium.webdriver.chrome.service import Service
                import time
                
                chrome_options = Options()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--remote-debugging-port=9222')
                chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                
                chromedriver_path = db.get_setting('chromedriver_path')
                service = None
                if chromedriver_path:
                    if not os.path.isabs(chromedriver_path):
                        chromedriver_path = os.path.abspath(chromedriver_path)
                    
                    if not os.path.exists(chromedriver_path):
                            raise Exception(f'ChromeDriver 不存在: {chromedriver_path}')

                    service = Service(executable_path=chromedriver_path)
                
                driver = webdriver.Chrome(service=service, options=chrome_options)
                try:
                    driver.get(url)
                    time.sleep(5)
                    html_content = driver.page_source
                finally:
                    driver.quit()
                    
            except ImportError:
                raise Exception('服务器未安装 selenium 库')
            except Exception as e:
                raise Exception(f'Selenium 抓取失败: {str(e)}')
        else:
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
            
            session = requests.Session()
            response = session.get(url, headers=headers, timeout=15)
            
            if response.status_code == 403:
                try:
                    import cloudscraper
                    scraper = cloudscraper.create_scraper(
                        browser={
                            'browser': 'chrome',
                            'platform': 'windows',
                            'desktop': True
                        }
                    )
                    response = scraper.get(url)
                    if response.status_code == 403:
                            raise Exception('解析失败 (403 Forbidden): Cloudscraper 也无法绕过')
                except ImportError:
                    raise Exception('解析失败 (403 Forbidden): 未安装 cloudscraper')
                except Exception as e:
                    raise Exception(f'Cloudscraper 尝试失败: {str(e)}')
            
            response.raise_for_status()
            html_content = response.text
        
        title = "未命名视频"
        
        def clean_title(text):
            text = re.sub(r'<[^>]+>', '', text)
            # 移除换行符，防止批量格式错乱
            text = text.replace('\n', ' ').replace('\r', '')
            text = re.sub(r'[^\w\s\-\u4e00-\u9fa5]', '', text)
            return text.strip()

        title_tag_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE)
        if title_tag_match:
            raw_title = title_tag_match.group(1).strip()
            if ' - ' in raw_title:
                raw_title = raw_title.split(' - ')[0]
            elif ' | ' in raw_title:
                raw_title = raw_title.split(' | ')[0]
            
            cleaned = clean_title(raw_title)
            if cleaned:
                title = cleaned

        m3u8_urls = set()
        matches = re.findall(r"var\s+hlsUrl\s*=\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", html_content)
        for m in matches: m3u8_urls.add(m)

        matches = re.findall(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', html_content)
        for m in matches:
            m3u8_urls.add(m.replace('\\/', '/'))

        matches = re.findall(r'src\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html_content)
        for m in matches: m3u8_urls.add(m)

        matches = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)', html_content)
        for m in matches: m3u8_urls.add(m)

        valid_urls = []
        for u in m3u8_urls:
            if u.startswith('http'):
                valid_urls.append(u)
        
        if not valid_urls:
            raise Exception('未找到 M3U8 链接或不支持该网站')
            
        return {
            'success': True,
            'count': len(valid_urls),
            'results': valid_urls,
            'title': title,
            'url': url
        }

    @api_bp.route('/api/parse/universal', methods=['POST'])
    @require_auth(db)
    def parse_universal():
        """通用视频解析"""
        data = request.get_json()
        url = data.get('url', '').strip()
        use_selenium = data.get('use_selenium', False)
        
        if not url:
            return jsonify({'error': '请提供视频链接'}), 400
            
        try:
            result = _parse_video_logic(url, use_selenium)
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @api_bp.route('/api/parse/batch', methods=['POST'])
    @require_auth(db)
    def parse_batch():
        """批量视频解析"""
        data = request.get_json()
        urls = data.get('urls', [])
        use_selenium = data.get('use_selenium', False)
        
        if not urls:
            return jsonify({'error': '请提供视频链接列表'}), 400
            
        results = []
        for url in urls:
            url = str(url).strip()
            if not url: continue
            
            try:
                res = _parse_video_logic(url, use_selenium)
                results.append(res)
            except Exception as e:
                results.append({
                    'success': False,
                    'url': url,
                    'error': str(e)
                })
                
        return jsonify({
            'success': True,
            'results': results
        })

    return api_bp