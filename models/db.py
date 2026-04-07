#!/usr/bin/env python3
"""数据库统一抽象层"""
import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from backend import Config


class Database:
    """数据库统一抽象层 - 单例模式"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._db_file = Config.DB_FILE
            cls._instance._ensure_db_dir()
        return cls._instance
    
    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_path = os.path.abspath(self._db_file)
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    @contextmanager
    def connection(self):
        """上下文管理器 - 自动提交/回滚"""
        conn = sqlite3.connect(self._db_file, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL 并返回 cursor"""
        with self.connection() as conn:
            return conn.execute(sql, params)
    
    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        """查询单条记录"""
        with self.connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
    
    def fetch_all(self, sql: str, params: tuple = ()) -> List[Dict]:
        """查询多条记录"""
        with self.connection() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
    
    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """插入记录"""
        cols = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        with self.connection() as conn:
            cursor = conn.execute(sql, tuple(data.values()))
            return cursor.lastrowid
    
    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple) -> int:
        """更新记录"""
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        with self.connection() as conn:
            return conn.execute(sql, tuple(data.values()) + where_params).rowcount
    
    def delete(self, table: str, where: str, where_params: tuple) -> int:
        """删除记录"""
        sql = f"DELETE FROM {table} WHERE {where}"
        with self.connection() as conn:
            return conn.execute(sql, where_params).rowcount
    
    def exists(self, table: str, where: str, where_params: tuple) -> bool:
        """检查记录是否存在"""
        sql = f"SELECT 1 FROM {table} WHERE {where} LIMIT 1"
        return self.fetch_one(sql, where_params) is not None
    
    def count(self, table: str, where: str = "1=1", where_params: tuple = ()) -> int:
        """统计记录数"""
        sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}"
        result = self.fetch_one(sql, where_params)
        return result['cnt'] if result else 0
    
    def initialize(self):
        """初始化数据库表结构"""
        with self.connection() as conn:
            cursor = conn.cursor()
            
            # users 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # user_clusters 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cluster_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, cluster_id)
                )
            ''')
            
            # clusters 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS clusters (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kubeconfig TEXT,
                    context TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # connections 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    cluster_name TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    pod_name TEXT NOT NULL,
                    local_port INTEGER,
                    user_id INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')
            
            # arthas_commands 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS arthas_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    connection_id TEXT NOT NULL,
                    user_id INTEGER,
                    command TEXT NOT NULL,
                    output TEXT,
                    error TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')
            
            # profiler_tasks 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profiler_tasks (
                    id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    user_id INTEGER,
                    type TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    cluster_name TEXT,
                    namespace TEXT,
                    pod_name TEXT,
                    mode TEXT,
                    event TEXT,
                    duration INTEGER,
                    format TEXT,
                    output_path TEXT,
                    progress INTEGER DEFAULT 0,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')
            
            # audit_logs 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    resource_type TEXT,
                    resource_id TEXT,
                    details TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            ''')
            
            # 创建默认 admin 账户
            cursor.execute('SELECT COUNT(*) FROM users')
            if cursor.fetchone()[0] == 0:
                import bcrypt
                password_hash = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode('utf-8')
                cursor.execute('''
                    INSERT INTO users (username, password_hash, role, status)
                    VALUES (?, ?, ?, ?)
                ''', ('admin', password_hash, 'admin', 'active'))
                print("✓ 已创建默认 admin 账户 (用户名: admin, 密码: admin123)")


# 单例实例
db = Database()