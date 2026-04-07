#!/usr/bin/env python3
"""认证服务"""
from typing import Optional, Tuple, Dict
import bcrypt
from models.user import User
from services.audit_service import AuditService


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """使用 bcrypt 验证密码"""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


class AuthService:
    """认证服务 - 统一处理登录、登出、密码修改"""
    
    @staticmethod
    def login(username: str, password: str) -> Tuple[Optional[User], Optional[str]]:
        """
        用户登录
        返回: (User对象, error_message)
        """
        if not username or not password:
            return None, "用户名和密码必填"
        
        # 查询用户
        user = User.get_by_username(username)
        
        if not user:
            # 用户不存在
            AuditService.log_login_failed(None, username, "用户不存在")
            return None, "用户名或密码错误"
        
        # 检查账户状态
        if not user.is_active:
            AuditService.log_login_failed(user.id, username, "账户已停用")
            return None, "账户已被停用"
        
        # 验证密码
        if not verify_password(password, user.password_hash):
            AuditService.log_login_failed(user.id, username, "密码错误")
            return None, "用户名或密码错误"
        
        # 登录成功
        AuditService.log_login_success(user.id, user.username)
        
        return user, None
    
    @staticmethod
    def change_password(user_id: int, old_password: str, new_password: str) -> Optional[str]:
        """
        修改密码
        返回: error_message 或 None 表示成功
        """
        if not old_password or not new_password:
            return "旧密码和新密码必填"
        
        if len(new_password) < 6:
            return "新密码长度至少6位"
        
        # 获取用户
        user = User.get_by_id(user_id)
        if not user:
            return "用户不存在"
        
        # 验证旧密码
        if not verify_password(old_password, user.password_hash):
            return "旧密码错误"
        
        # 更新密码
        new_hash = hash_password(new_password)
        db_update = User.get_by_id(user_id)
        # 直接更新数据库
        from models.db import db
        db.update('users', {'password_hash': new_hash}, 'id = ?', (user_id,))
        
        # 记录审计日志
        AuditService.log_password_changed(user_id, user.username)
        
        return None
    
    @staticmethod
    def logout(user_id: int, username: str):
        """记录登出"""
        AuditService.log_logout(user_id, username)