#!/usr/bin/env python3
"""User 模型"""
from datetime import datetime
from flask_login import UserMixin
from typing import Optional, Dict
from models.db import db


class User(UserMixin):
    """Flask-Login User 模型"""
    
    def __init__(self, user_id: int, username: str, password_hash: str, role: str, status: str):
        self.id = user_id
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.status = status
    
    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'
    
    @property
    def is_active(self) -> bool:
        return self.status == 'active'
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "status": self.status,
            "is_admin": self.is_admin,
            "is_active": self.is_active
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'User':
        """从字典创建"""
        return User(
            user_id=data['id'],
            username=data['username'],
            password_hash=data.get('password_hash', ''),
            role=data['role'],
            status=data['status']
        )
    
    @staticmethod
    def get_by_id(user_id: int) -> Optional['User']:
        """根据 ID 获取用户"""
        row = db.fetch_one('SELECT * FROM users WHERE id = ?', (user_id,))
        if row:
            return User(
                user_id=row['id'],
                username=row['username'],
                password_hash=row['password_hash'],
                role=row['role'],
                status=row['status']
            )
        return None
    
    @staticmethod
    def get_by_username(username: str) -> Optional['User']:
        """根据用户名获取用户"""
        row = db.fetch_one('SELECT * FROM users WHERE username = ?', (username,))
        if row:
            return User(
                user_id=row['id'],
                username=row['username'],
                password_hash=row['password_hash'],
                role=row['role'],
                status=row['status']
            )
        return None
    
    @staticmethod
    def get_all() -> list:
        """获取所有用户"""
        rows = db.fetch_all('SELECT * FROM users ORDER BY created_at DESC')
        return [User(
            user_id=row['id'],
            username=row['username'],
            password_hash=row['password_hash'],
            role=row['role'],
            status=row['status']
        ) for row in rows]
    
    def save(self) -> int:
        """保存用户（更新）"""
        return db.update('users', {
            'username': self.username,
            'role': self.role,
            'status': self.status,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, 'id = ?', (self.id,))
    
    @staticmethod
    def create(username: str, password_hash: str, role: str = 'user', status: str = 'active') -> int:
        """创建用户"""
        return db.insert('users', {
            'username': username,
            'password_hash': password_hash,
            'role': role,
            'status': status
        })
    
    def delete(self) -> int:
        """删除用户"""
        return db.delete('users', 'id = ?', (self.id,))
    
    @staticmethod
    def count() -> int:
        """统计用户数"""
        return db.count('users')
    
    @staticmethod
    def count_by_role(role: str) -> int:
        """按角色统计用户数"""
        return db.count('users', 'role = ?', (role,))
    
    @staticmethod
    def exists_username(username: str, exclude_id: int = None) -> bool:
        """检查用户名是否已存在"""
        if exclude_id:
            return db.exists('users', 'username = ? AND id != ?', (username, exclude_id))
        return db.exists('users', 'username = ?', (username,))