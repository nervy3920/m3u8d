from flask import Blueprint, request, jsonify, make_response
import secrets
from utils import get_admin_password, set_admin_password_hash, verify_password, set_auth_token, get_auth_token

def create_auth_blueprint(db):
    auth_bp = Blueprint('auth', __name__)

    @auth_bp.route('/api/init', methods=['POST'])
    def init_system():
        """初始化系统（设置密码）"""
        if get_admin_password(db):
            return jsonify({'error': '系统已初始化'}), 400
        
        data = request.get_json()
        password = data.get('password', '').strip()
        
        if not password:
            return jsonify({'error': '密码不能为空'}), 400
        try:
            # 使用 bcrypt 哈希存储密码
            set_admin_password_hash(db, password)
        except Exception as e:
            return jsonify({'error': f'初始化失败: {e}'}), 500
        return jsonify({'success': True, 'message': '初始化成功'})

    @auth_bp.route('/api/auth', methods=['POST'])
    def auth():
        """验证密码（支持旧明文兼容与自动迁移到 bcrypt）"""
        data = request.get_json()
        password = data.get('password', '')
        
        if not get_admin_password(db):
            return jsonify({'error': '系统未初始化', 'code': 'NOT_INITIALIZED'}), 403

        # 使用 verify_password 检查（会兼容明文并在 init 时迁移）
        if verify_password(password, db):
            # 生成随机 token 并保存到 settings（避免基于密码的可逆 token）
            token = secrets.token_hex(32)
            try:
                set_auth_token(db, token)
            except Exception:
                pass

            response = make_response(jsonify({'success': True, 'message': '验证成功', 'token': token}))
            # 设置 Cookie，有效期 30 天
            response.set_cookie('auth_token', token, max_age=30*24*60*60, httponly=True, samesite='Lax')
            return response
        else:
            return jsonify({'success': False, 'message': '密码错误'}), 401

    @auth_bp.route('/api/logout', methods=['POST'])
    def logout():
        """退出登录"""
        response = make_response(jsonify({'success': True, 'message': '已退出登录'}))
        response.set_cookie('auth_token', '', max_age=0)
        return response

    @auth_bp.route('/api/check-auth', methods=['GET'])
    def check_auth():
        """检查登录状态"""
        if not get_admin_password(db):
            return jsonify({'authenticated': False, 'initialized': False})
            
        token = request.cookies.get('auth_token')
        # 使用随机 token 验证方式
        if token and get_auth_token(db) == token:
            return jsonify({'authenticated': True, 'initialized': True})
        return jsonify({'authenticated': False, 'initialized': True})

    return auth_bp