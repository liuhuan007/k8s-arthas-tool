#!/usr/bin/env python3
"""数据库统一抽象层"""
import sqlite3
import os
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

log = logging.getLogger(__name__)


class Database:
    """数据库统一抽象层 - 单例模式"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 延迟导入避免循环依赖
            from backend.config import Config
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
        """上下文管理器 - 自动提交/回滚，启用 WAL / busy_timeout / foreign_keys"""
        conn = sqlite3.connect(self._db_file, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
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

            # user_namespaces 表：账号到 cluster/namespace 的精细授权
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_namespaces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cluster_id TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, cluster_id, namespace)
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
                    level TEXT NOT NULL DEFAULT 'arthas',
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
            
            # ── 任务中心诊断重构：新增表 ──────────────────────────────────
            # 1. arthas_command_templates 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS arthas_command_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability_id INTEGER NOT NULL UNIQUE,
                    command_name TEXT NOT NULL,
                    command_category TEXT,
                    arthas_command TEXT NOT NULL,
                    syntax TEXT,
                    description TEXT,
                    params_json TEXT DEFAULT '[]',
                    options_json TEXT DEFAULT '[]',
                    examples TEXT,
                    doc_url TEXT,
                    min_version TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_arthas_cmd_templates_name ON arthas_command_templates(command_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_arthas_cmd_templates_category ON arthas_command_templates(command_category)')
            
            # 2. diagnosis_scenario_steps 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS diagnosis_scenario_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability_id INTEGER NOT NULL,
                    step_order INTEGER NOT NULL,
                    command TEXT NOT NULL,
                    desc TEXT,
                    timeout_ms INTEGER DEFAULT 60000,
                    fail_fast INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE,
                    UNIQUE(capability_id, step_order)
                )
            ''')
            
            # 3. ai_diagnosis_handlers 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_diagnosis_handlers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capability_id INTEGER NOT NULL UNIQUE,
                    handler TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE,
                    CHECK(handler LIKE 'performance_diagnose.%')
                )
            ''')
            
            # 4. task_logs_archive 归档表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_logs_archive (
                    id TEXT PRIMARY KEY,
                    task_id INTEGER,
                    capability_id INTEGER,
                    user_id INTEGER,
                    execution_mode TEXT NOT NULL,
                    execution_type TEXT NOT NULL,
                    target_json TEXT,
                    params_json TEXT,
                    status TEXT NOT NULL,
                    stdout TEXT,
                    stderr TEXT,
                    exit_code INTEGER,
                    result_json TEXT,
                    error_message TEXT,
                    duration_ms INTEGER,
                    work_dir TEXT,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    created_at TIMESTAMP,
                    retention_days INTEGER,
                    is_archived INTEGER DEFAULT 1,
                    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_logs_archive_finished_at ON task_logs_archive(finished_at)')
            
            # 5. system_configs 系统配置表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_configs (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 插入默认清理策略
            cursor.execute('''
                INSERT OR IGNORE INTO system_configs (key, value, description) VALUES
                ('task_logs.retention_days', '30', 'task_logs 活跃日志保留天数'),
                ('task_logs_archive.retention_days', '365', 'task_logs_archive 归档日志保留天数'),
                ('arthas_command_logs.retention_days', '30', 'arthas_command_logs 保留天数'),
                ('task_logs.cleanup_cron', '0 3 * * *', 'task_logs 清理定时任务 Cron 表达式'),
                ('task_logs_archive.cleanup_cron', '0 4 1 * *', 'task_logs_archive 清理定时任务 Cron 表达式')
            ''')
            
            # ── 任务中心诊断重构：表迁移 ──────────────────────────────────
            # 重命名 task_runs → task_logs（SQLite 不支持直接检查表是否存在，需要捕获异常）
            try:
                cursor.execute('SELECT 1 FROM task_logs LIMIT 1')
            except Exception:
                try:
                    cursor.execute('ALTER TABLE task_runs RENAME TO task_logs')
                    log.info("Schema migrated: task_runs renamed to task_logs")
                except Exception as e:
                    log.warning("Rename task_runs to task_logs failed: %s", e)
            
            # 扩展 task_logs 表字段
            for col, ddl in [
                ('capability_id', 'ALTER TABLE task_logs ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id)'),
                ('execution_type', "ALTER TABLE task_logs ADD COLUMN execution_type TEXT DEFAULT 'diagnosis'"),
                ('retention_days', 'ALTER TABLE task_logs ADD COLUMN retention_days INTEGER DEFAULT 30'),
                ('is_archived', 'ALTER TABLE task_logs ADD COLUMN is_archived INTEGER DEFAULT 0'),
                ('params_json', "ALTER TABLE task_logs ADD COLUMN params_json TEXT DEFAULT '{}'"),
                ('result_json', 'ALTER TABLE task_logs ADD COLUMN result_json TEXT'),
                ('execution_mode', "ALTER TABLE task_logs ADD COLUMN execution_mode TEXT DEFAULT 'immediate'"),
                ('capability_name', 'ALTER TABLE task_logs ADD COLUMN capability_name TEXT'),
                ('rendered_command', 'ALTER TABLE task_logs ADD COLUMN rendered_command TEXT'),
                ('run_type', "ALTER TABLE task_logs ADD COLUMN run_type TEXT DEFAULT 'script'"),
                ('anomaly_event_id', 'ALTER TABLE task_logs ADD COLUMN anomaly_event_id INTEGER'),
                ('connection_snapshot_json', 'ALTER TABLE task_logs ADD COLUMN connection_snapshot_json TEXT'),
                ('capability_snapshot_json', 'ALTER TABLE task_logs ADD COLUMN capability_snapshot_json TEXT'),
                ('ai_analysis_result', 'ALTER TABLE task_logs ADD COLUMN ai_analysis_result TEXT'),
                ('capability_version', 'ALTER TABLE task_logs ADD COLUMN capability_version INTEGER'),
                ('log_path', 'ALTER TABLE task_logs ADD COLUMN log_path TEXT'),
            ]:
                try:
                    cursor.execute(f'SELECT {col} FROM task_logs LIMIT 1')
                except Exception:
                    try:
                        cursor.execute(ddl)
                        log.info("Schema migrated: task_logs.%s added", col)
                    except Exception as e:
                        log.warning("Add column task_logs.%s failed: %s", col, e)
            
            # 重命名 arthas_commands → arthas_command_logs
            try:
                cursor.execute('SELECT 1 FROM arthas_command_logs LIMIT 1')
            except Exception:
                try:
                    cursor.execute('ALTER TABLE arthas_commands RENAME TO arthas_command_logs')
                    log.info("Schema migrated: arthas_commands renamed to arthas_command_logs")
                except Exception as e:
                    log.warning("Rename arthas_commands to arthas_command_logs failed: %s", e)
            
            # 扩展 arthas_command_logs 表字段
            for col, ddl in [
                ('template_id', 'ALTER TABLE arthas_command_logs ADD COLUMN template_id INTEGER REFERENCES arthas_command_templates(id)'),
                ('step_order', 'ALTER TABLE arthas_command_logs ADD COLUMN step_order INTEGER'),
                ('command_type', "ALTER TABLE arthas_command_logs ADD COLUMN command_type TEXT"),
            ]:
                try:
                    cursor.execute(f'SELECT {col} FROM arthas_command_logs LIMIT 1')
                except Exception:
                    try:
                        cursor.execute(ddl)
                        log.info("Schema migrated: arthas_command_logs.%s added", col)
                    except Exception as e:
                        log.warning("Add column arthas_command_logs.%s failed: %s", col, e)
            
            # script_templates 扩展 capability_id
            try:
                cursor.execute('SELECT capability_id FROM script_templates LIMIT 1')
            except Exception:
                try:
                    cursor.execute('ALTER TABLE script_templates ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id)')
                    log.info("Schema migrated: script_templates.capability_id added")
                except Exception as e:
                    log.warning("Add column script_templates.capability_id failed: %s", e)
            
            # connections 表增加 owner_user_id 字段（如果不存在）
            try:
                cursor.execute('SELECT owner_user_id FROM connections LIMIT 1')
            except Exception:
                try:
                    cursor.execute("ALTER TABLE connections ADD COLUMN owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
                    log.info("Schema migrated: connections.owner_user_id added")
                except Exception as e:
                    log.warning("Add column connections.owner_user_id failed: %s", e)
            
            # connections 表增加 container_name, java_pid 等字段（如果不存在）
            for col, ddl in [
                ('container_name', 'ALTER TABLE connections ADD COLUMN container_name TEXT'),
                ('java_pid', 'ALTER TABLE connections ADD COLUMN java_pid INTEGER'),
                ('arthas_version', 'ALTER TABLE connections ADD COLUMN arthas_version TEXT'),
                ('last_ping_at', 'ALTER TABLE connections ADD COLUMN last_ping_at TIMESTAMP'),
                ('status', "ALTER TABLE connections ADD COLUMN status TEXT DEFAULT 'disconnected'"),
                ('last_active_at', 'ALTER TABLE connections ADD COLUMN last_active_at TIMESTAMP'),
                ('ttl_hours', 'ALTER TABLE connections ADD COLUMN ttl_hours INTEGER DEFAULT 0'),
            ]:
                try:
                    cursor.execute(f'SELECT {col} FROM connections LIMIT 1')
                except Exception:
                    try:
                        cursor.execute(ddl)
                        log.info("Schema migrated: connections.%s added", col)
                    except Exception as e:
                        log.warning("Add column connections.%s failed: %s", col, e)

            # ── P0 索引 ──────────────────────────────────────────────────────────
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_connections_user ON connections(owner_user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_connections_status ON connections(status)")
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_arthas_command_logs_user_cluster_created
                ON arthas_command_logs(user_id, connection_id, timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_profiler_tasks_user_status_created
                ON profiler_tasks(user_id, status, created_at DESC)
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_user_created ON task_logs(user_id, created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_capability ON task_logs(capability_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_execution_mode ON task_logs(execution_mode)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_execution_type ON task_logs(execution_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_run_type ON task_logs(run_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_status_started ON task_logs(status, started_at DESC)")
            
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


# 延迟初始化的单例实例 (避免循环导入)
_db_instance: Optional['Database'] = None

def get_db() -> 'Database':
    """获取 Database 单例 (延迟初始化避免循环导入)"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance

# 向后兼容: 提供 db 属性
class _DbProxy:
    """Database 单例的延迟代理"""
    def __getattr__(self, name):
        return getattr(get_db(), name)
    def __call__(self):
        return get_db()

db = _DbProxy()