import sys
import os
import pathlib
import tempfile
import pytest
import json
import sqlite3
from unittest.mock import MagicMock, patch

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope='session')
def temp_db():
    """创建临时数据库用于测试"""
    # 创建临时数据库文件
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    # 初始化数据库表结构
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建 connections 表（匹配 models/db.py 中的结构）
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
            owner_user_id INTEGER,
            container_name TEXT,
            java_pid INTEGER,
            arthas_version TEXT,
            last_ping_at TIMESTAMP,
            status TEXT DEFAULT 'disconnected',
            last_active_at TIMESTAMP,
            ttl_hours INTEGER DEFAULT 0
        )
    ''')
    
    # 创建 diagnosis_capabilities 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnosis_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            level INTEGER,
            description TEXT,
            arthas_command TEXT,
            parameters_schema TEXT,
            risk_level TEXT DEFAULT 'low',
            estimated_duration INTEGER,
            steps_json TEXT,
            handler TEXT,
            confirm_required INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建 task_logs 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_logs (
            id TEXT PRIMARY KEY,
            task_id INTEGER,
            capability_id INTEGER,
            user_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            execution_mode TEXT NOT NULL DEFAULT 'manual',
            execution_type TEXT DEFAULT 'script',
            run_type TEXT DEFAULT 'script',
            target_json TEXT DEFAULT '{}',
            params_json TEXT DEFAULT '{}',
            result_json TEXT,
            stdout TEXT,
            stderr TEXT,
            exit_code INTEGER,
            duration_ms INTEGER,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            error_message TEXT,
            work_dir TEXT,
            capability_name TEXT,
            capability_version INTEGER,
            rendered_command TEXT,
            connection_snapshot_json TEXT,
            capability_snapshot_json TEXT,
            ai_analysis_result TEXT,
            log_path TEXT,
            retention_days INTEGER DEFAULT 30,
            is_archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建 step_logs 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS step_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            step_name TEXT,
            step_type TEXT,
            command TEXT,
            output TEXT,
            status TEXT DEFAULT 'pending',
            duration_ms INTEGER,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES task_logs(id)
        )
    ''')
    
    # 创建 skill_registry 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS skill_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT,
            category TEXT,
            level INTEGER,
            risk_level TEXT,
            estimated_duration INTEGER,
            source TEXT DEFAULT 'custom',
            status TEXT DEFAULT 'draft',
            dsl TEXT,
            parameters_schema TEXT,
            llm_prompt TEXT,
            arthas_command TEXT,
            handler TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(name, version)
        )
    ''')
    
    # 插入测试连接
    cursor.execute('''
        INSERT INTO connections (id, user_id, cluster_name, namespace, pod_name, status, local_port, java_pid)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('test-conn-001', 1, 'test-cluster', 'default', 'test-pod-001', 'connected', 3658, 12345))
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    # 清理
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def app_context(temp_db):
    """创建 Flask 应用上下文"""
    # 模拟 Flask 应用
    app = MagicMock()
    app.config = {
        'DATABASE': temp_db,
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key'
    }
    
    # 创建一个简单的数据库包装器
    class TestDatabaseWrapper:
        def __init__(self, db_path):
            self.db_path = db_path
        
        def fetch_one(self, sql, params=()):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(sql, params).fetchone()
            conn.close()
            return dict(row) if row else None
        
        def fetch_all(self, sql, params=()):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(row) for row in rows]
        
        def execute(self, sql, params=()):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            conn.commit()
            conn.close()
            return cursor
        
        def insert(self, table, data):
            cols = ', '.join(data.keys())
            placeholders = ', '.join(['?'] * len(data))
            sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
            return self.execute(sql, tuple(data.values()))
    
    db = TestDatabaseWrapper(temp_db)
    
    # 注入到模块
    import models.db
    models.db._db = db
    
    yield app, db


@pytest.fixture
def mock_arthas_connection():
    """创建模拟的 Arthas 连接"""
    connection = MagicMock()
    connection.id = 'test-conn-001'
    connection.user_id = 1
    connection.cluster_name = 'test-cluster'
    connection.namespace = 'default'
    connection.pod_name = 'test-pod-001'
    connection.status = 'connected'
    connection.local_port = 3658
    connection.java_pid = 12345
    
    # 模拟 HTTP 客户端
    connection.http_client = MagicMock()
    connection.http_client.exec_once.return_value = {
        'state': 'SUCCEEDED',
        'body': {
            'results': [{'output': 'Mock output'}]
        },
        'duration_ms': 100
    }
    
    return connection


@pytest.fixture
def mock_db():
    """创建模拟的数据库"""
    db = MagicMock()
    db.fetch_one.return_value = None
    db.fetch_all.return_value = []
    db.execute.return_value = None
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# 前端测试 Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope='session')
def project_root():
    """项目根目录"""
    return pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope='session')
def static_dir(project_root):
    """静态资源目录"""
    return project_root / 'static'


@pytest.fixture(scope='session')
def index_html(static_dir):
    """index.html 内容"""
    return (static_dir / 'index.html').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def js_components(static_dir):
    """JS 组件目录"""
    return static_dir / 'js' / 'components'


@pytest.fixture(scope='session')
def js_core(static_dir):
    """JS 核心目录"""
    return static_dir / 'js' / 'core'


@pytest.fixture(scope='session')
def diagnosis_js_source(js_components):
    """diagnosis.js 源码"""
    return (js_components / 'diagnosis.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def diagnosis_form_js_source(js_components):
    """diagnosis-form.js 源码"""
    return (js_components / 'diagnosis-form.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def diagnosis_progress_js_source(js_components):
    """diagnosis-progress.js 源码"""
    return (js_components / 'diagnosis-progress.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def diagnosis_result_js_source(js_components):
    """diagnosis-result.js 源码"""
    return (js_components / 'diagnosis-result.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def diagnosis_history_js_source(js_components):
    """diagnosis-history.js 源码"""
    return (js_components / 'diagnosis-history.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def diagnosis_execution_js_source(js_components):
    """diagnosis-execution.js 源码"""
    return (js_components / 'diagnosis-execution.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def diagnosis_renderer_js_source(js_components):
    """diagnosis-renderer.js 源码"""
    return (js_components / 'diagnosis-renderer.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def diagnosis_context_js_source(js_core):
    """diagnosis-context.js 源码"""
    return (js_core / 'diagnosis-context.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def api_js_source(static_dir):
    """api.js 源码"""
    return (static_dir / 'js' / 'core' / 'api.js').read_text(encoding='utf-8')


@pytest.fixture(scope='session')
def ai_chat_js_source(static_dir):
    """ai-chat.js 源码"""
    return (static_dir / 'js' / 'ai-chat.js').read_text(encoding='utf-8')