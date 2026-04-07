#!/usr/bin/env python3
"""用户管理服务"""
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from models.user import User
from services.audit_service import AuditService
from services.auth_service import hash_password


class UserService:
    """用户管理服务 - 统一处理用户 CRUD 操作"""
    
    @staticmethod
    def get_all() -> List[User]:
        """获取所有用户"""
        return User.get_all()
    
    @staticmethod
    def get_by_id(user_id: int) -> Optional[User]:
        """根据 ID 获取用户"""
        return User.get_by_id(user_id)
    
    @staticmethod
    def get_by_username(username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return User.get_by_username(username)
    
    @staticmethod
    def create(operator_id: int, username: str, password: str, 
               role: str = 'user', status: str = 'active') -> Tuple[Optional[int], Optional[str]]:
        """
        创建用户
        返回: (user_id, error_message)
        """
        # 验证输入
        if not username or not password:
            return None, "用户名和密码必填"
        
        if len(password) < 6:
            return None, "密码长度至少6位"
        
        if role not in ('admin', 'user'):
            return None, "角色必须是 admin 或 user"
        
        if status not in ('active', 'inactive'):
            return None, "状态必须是 active 或 inactive"
        
        # 检查用户名是否存在
        if User.exists_username(username):
            return None, "用户名已存在"
        
        # 创建用户
        password_hash = hash_password(password)
        user_id = User.create(username, password_hash, role, status)
        
        # 记录审计日志
        AuditService.log_user_created(operator_id, username, role)
        
        return user_id, None
    
    @staticmethod
    def update(operator_id: int, user_id: int, username: str = None,
               role: str = None, status: str = None) -> Tuple[Optional[str], Optional[str]]:
        """
        更新用户
        返回: (changes_string, error_message)
        """
        # 获取用户
        user = User.get_by_id(user_id)
        if not user:
            return None, "用户不存在"
        
        # 检查是否在修改自己的角色
        if operator_id == user_id and role and role != user.role:
            return None, "不能修改自己的角色"
        
        # 构建更新字段
        updates = {}
        changes = []
        
        if username and username != user.username:
            if User.exists_username(username, user_id):
                return None, "用户名已存在"
            updates['username'] = username
            changes.append(f"用户名: {user.username} -> {username}")
        
        if role and role != user.role:
            if role not in ('admin', 'user'):
                return None, "角色必须是 admin 或 user"
            updates['role'] = role
            changes.append(f"角色: {user.role} -> {role}")
        
        if status and status != user.status:
            if status not in ('active', 'inactive'):
                return None, "状态必须是 active 或 inactive"
            updates['status'] = status
            changes.append(f"状态: {user.status} -> {status}")
        
        if not updates:
            return "", None
        
        # 执行更新
        updates['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db_update = User.get_by_id(user_id)
        from models.db import db
        db.update('users', updates, 'id = ?', (user_id,))
        
        # 记录审计日志
        AuditService.log_user_updated(operator_id, user.username, "; ".join(changes))
        
        return "; ".join(changes), None
    
    @staticmethod
    def delete(operator_id: int, user_id: int) -> Optional[str]:
        """
        删除用户
        返回: error_message 或 None 表示成功
        """
        # 获取用户
        user = User.get_by_id(user_id)
        if not user:
            return "用户不存在"
        
        # 检查是否删除最后一个 admin
        if user.role == 'admin':
            admin_count = User.count_by_role('admin')
            if admin_count <= 1:
                return "不能删除最后一个 admin 用户"
        
        # 检查是否删除自己
        if operator_id == user_id:
            return "不能删除自己的账户"
        
        # 删除用户
        User.delete(user_id)
        
        # 记录审计日志
        AuditService.log_user_deleted(operator_id, user.username)
        
        return None
    
    @staticmethod
    def set_status(operator_id: int, user_id: int, status: str) -> Optional[str]:
        """
        设置用户状态
        返回: error_message 或 None 表示成功
        """
        if status not in ('active', 'inactive'):
            return "状态必须是 active 或 inactive"
        
        # 获取用户
        user = User.get_by_id(user_id)
        if not user:
            return "用户不存在"
        
        # 检查是否停用最后一个 admin
        if user.role == 'admin' and status == 'inactive':
            admin_count = User.count_by_role('admin')
            if admin_count <= 1:
                return "不能停用最后一个 admin 用户"
        
        # 检查是否停用自己
        if operator_id == user_id and status == 'inactive':
            return "不能停用自己的账户"
        
        # 更新状态
        from models.db import db
        db.update('users', {'status': status, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                  'id = ?', (user_id,))
        
        # 记录审计日志
        AuditService.log_user_status_changed(operator_id, user.username, status)
        
        return None