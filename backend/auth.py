#!/usr/bin/env python3
"""
认证模块 - 处理用户认证、审计日志、权限装饰器
"""
import bcrypt
from flask import request, jsonify
from flask_login import UserMixin, login_required, current_user, logout_user

# ═════════════════════════════════════════════════════════════════════════════
# Permission Decorators
# ═════════════════════════════════════════════════════════════════════════════

def admin_required(f):
    """Admin 权限装饰器 - 只有 admin 可以访问"""
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({"error": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return decorated_function


# ═════════════════════════════════════════════════════════════════════════════════════
# Password Utilities
# ═══════════════════════════════════════════════════════════════════════════════════════════

def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """使用 bcrypt 验证密码"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
