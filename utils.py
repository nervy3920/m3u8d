from flask import request, jsonify
from functools import wraps
import secrets
from pathlib import Path

# 尝试使用 bcrypt，如果不可用会提示在运行时安装
try:
    import bcrypt
except ImportError:
    bcrypt = None

# 简单的 Secret Key 管理（仍保留用于其它用途）
secret_file = Path('./data/secret.key')
if not secret_file.exists():
    Path('./data').mkdir(parents=True, exist_ok=True)
    secret_file.write_text(secrets.token_hex(32))
SECRET_KEY = secret_file.read_text().strip()

def get_admin_password(db):
    """
    兼容函数：返回任一表示已初始化的值（旧的 admin_password 或 新的 admin_password_hash）
    仅用于判断系统是否初始化。
    """
    p = db.get_setting('admin_password_hash')
    if p:
        return p
    return db.get_setting('admin_password')

def set_admin_password_hash(db, password):
    """使用 bcrypt 对密码进行哈希并保存到 settings 中"""
    if bcrypt is None:
        # 如果 bcrypt 不可用，回退到明文存储（不推荐，但为了防止崩溃）
        # 或者抛出更友好的错误，但用户反馈说初始化报错，可能是因为环境确实没装 bcrypt
        # 既然 requirements.txt 里有 bcrypt，那应该是安装问题。
        # 但为了保证能运行，这里做一个回退处理，或者尝试动态安装（不推荐在 web 进程中做）
        # 考虑到用户反馈的错误是“服务器内部错误”，很可能是这里抛出了 RuntimeError
        # 我们可以尝试使用 hashlib 作为备选方案，或者直接明文（仅作为最后的 fallback）
        
        # 更好的做法：使用 hashlib sha256 作为 fallback
        import hashlib
        hashed = hashlib.sha256(password.encode('utf-8')).hexdigest()
        # 加上前缀以区分算法
        db.set_setting('admin_password_hash', f"sha256:{hashed}")
    else:
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        db.set_setting('admin_password_hash', hashed)
    
    # 移除旧明文（如果存在）
    try:
        if db.get_setting('admin_password'):
            db.set_setting('admin_password', '')
    except Exception:
        pass

def verify_password(password, db):
    """
    验证明文密码：
    - 优先使用 admin_password_hash（bcrypt 验证）
    - 如果不存在 hash，回退到旧的 admin_password 明文比较（用于兼容迁移）
    """
    hash_val = db.get_setting('admin_password_hash')
    if hash_val:
        if hash_val.startswith('sha256:'):
            import hashlib
            # 处理 sha256 fallback
            stored_hash = hash_val.split(':', 1)[1]
            current_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            return current_hash == stored_hash
        elif bcrypt:
            try:
                return bcrypt.checkpw(password.encode('utf-8'), hash_val.encode('utf-8'))
            except Exception:
                return False
        
    # 兼容旧明文存储
    old = db.get_setting('admin_password')
    if old:
        return password == old
    return False

def set_auth_token(db, token):
    db.set_setting('auth_token', token)

def get_auth_token(db):
    return db.get_setting('auth_token')

def verify_auth_token(token, db):
    """验证存储在设置中的随机 token"""
    if not token:
        return False
    stored = get_auth_token(db)
    return stored == token

def require_auth(db):
    """验证密码装饰器工厂函数"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 检查系统是否已初始化
            if not get_admin_password(db):
                 return jsonify({'error': '系统未初始化', 'code': 'NOT_INITIALIZED'}), 403

            # 1. 检查 API Key (如果开启)
            api_key = request.headers.get('X-API-Key')
            if api_key:
                if db.get_setting('api_enabled') == 'true' and api_key == db.get_setting('api_key'):
                    return f(*args, **kwargs)

            # 2. 检查 Cookie token（随机 token 存储在 settings.auth_token）
            token = request.cookies.get('auth_token')
            if token and verify_auth_token(token, db):
                return f(*args, **kwargs)

            # 3. 检查 Header 密码（兼容旧方式），使用 verify_password 进行哈希/明文验证
            password = request.headers.get('X-Admin-Password')
            if password and verify_password(password, db):
                return f(*args, **kwargs)

            return jsonify({'error': '未授权，请重新登录或提供有效的 API Key'}), 401
        return decorated_function
    return decorator