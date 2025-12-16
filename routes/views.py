from flask import Blueprint, render_template, redirect, url_for, request, send_from_directory, jsonify
from utils import get_admin_password, verify_auth_token
import os

def create_views_blueprint(db):
    views_bp = Blueprint('views', __name__)

    def check_page_auth():
        """页面权限检查"""
        if not get_admin_password(db):
            return redirect(url_for('views.init_page'))
        
        token = request.cookies.get('auth_token')
        if not token or not verify_auth_token(token, db):
            return redirect(url_for('views.login_page'))
        return None

    @views_bp.route('/')
    def index():
        """首页重定向"""
        if not get_admin_password(db):
            return redirect(url_for('views.init_page'))
        
        token = request.cookies.get('auth_token')
        if token and verify_auth_token(token, db):
            return redirect(url_for('views.new_task_page'))
        return redirect(url_for('views.login_page'))

    @views_bp.route('/init')
    def init_page():
        """初始化页面"""
        if get_admin_password(db):
            return redirect(url_for('views.login_page'))
        return render_template('init.html')

    @views_bp.route('/login')
    def login_page():
        """登录页面"""
        if not get_admin_password(db):
            return redirect(url_for('views.init_page'))
        
        token = request.cookies.get('auth_token')
        if token and verify_auth_token(token, db):
            return redirect(url_for('views.new_task_page'))
        return render_template('login.html')

    @views_bp.route('/new')
    def new_task_page():
        auth_redirect = check_page_auth()
        if auth_redirect: return auth_redirect
        return render_template('new_task.html', active_page='new')

    @views_bp.route('/downloading')
    def downloading_page():
        auth_redirect = check_page_auth()
        if auth_redirect: return auth_redirect
        return render_template('downloading.html', active_page='downloading')

    @views_bp.route('/completed')
    def completed_page():
        auth_redirect = check_page_auth()
        if auth_redirect: return auth_redirect
        return render_template('completed.html', active_page='completed')

    @views_bp.route('/failed')
    def failed_page():
        auth_redirect = check_page_auth()
        if auth_redirect: return auth_redirect
        return render_template('failed.html', active_page='failed')

    @views_bp.route('/all')
    def all_tasks_page():
        auth_redirect = check_page_auth()
        if auth_redirect: return auth_redirect
        return render_template('all_tasks.html', active_page='all')

    @views_bp.route('/settings')
    def settings_page():
        auth_redirect = check_page_auth()
        if auth_redirect: return auth_redirect
        return render_template('settings.html', active_page='settings')

    @views_bp.route('/parser')
    def parser_page():
        auth_redirect = check_page_auth()
        if auth_redirect: return auth_redirect
        return render_template('parser.html', active_page='parser')

    @views_bp.route('/videos/<path:filename>')
    def serve_video(filename):
        """提供视频文件 (公开访问，供 Aria2 和播放器使用)"""
        download_dir = db.get_setting('download_dir', './downloads')
        try:
            return send_from_directory(download_dir, filename, as_attachment=False)
        except Exception as e:
            return jsonify({'error': f'文件不存在: {str(e)}'}), 404

    return views_bp