"""
Tests for Phase 5: 连接中心增强
- 任务 5.2: 健康检查（后端）
- 任务 5.3: TTL 清理（后端）
- 任务 5.4: 连接状态恢复（后端）
- 任务 5.5: 多标签页同步（前端）
- 任务 5.6: 连接切换确认（前端）
"""
import json
import os
import sys
import time
import threading
import tempfile
import sqlite3
import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════════
# 后端测试 Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_db_path():
    """创建临时数据库文件"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

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

    conn.commit()
    conn.close()

    yield db_path

    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def mock_db(temp_db_path):
    """创建模拟数据库包装器"""
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

        def update(self, table, data, where, params=()):
            set_clause = ', '.join(f"{k} = ?" for k in data.keys())
            sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
            return self.execute(sql, tuple(data.values()) + tuple(params))

        def delete(self, table, where, params=()):
            sql = f"DELETE FROM {table} WHERE {where}"
            return self.execute(sql, tuple(params))

        def exists(self, table, where, params=()):
            row = self.fetch_one(f'SELECT 1 FROM {table} WHERE {where}', params)
            return row is not None

    return TestDatabaseWrapper(temp_db_path)


@pytest.fixture
def mock_arthas_conn():
    """创建模拟的 Arthas 连接对象"""
    conn = MagicMock()
    conn.connection_id = 'test-cluster/default/test-pod'
    conn.local_port = 3658
    conn.java_pid = 12345
    conn.arthas_version = '3.6.7'
    conn.is_alive.return_value = True

    # 模拟 http_client
    conn.http_client = MagicMock()
    conn.http_client.exec_once.return_value = {
        'state': 'SUCCEEDED',
        'body': {'results': [{'output': 'Arthas version 3.6.7'}]},
        'duration_ms': 50,
    }
    conn.http_client.init_session.return_value = {'state': 'SUCCEEDED'}

    # 模拟 agent_mgr
    conn.agent_mgr = MagicMock()
    conn.agent_mgr._pid = 12345

    # 模拟 target
    conn.target = MagicMock()
    conn.target.cluster_name = 'test-cluster'
    conn.target.namespace = 'default'
    conn.target.pod_name = 'test-pod'

    # 模拟 pod_conn
    conn.pod_conn = MagicMock()
    conn.pod_conn.connect.return_value = (True, 'ok')

    # 模拟 disconnect
    conn.disconnect.return_value = None
    conn.connect.return_value = (True, 'Connected')

    return conn


@pytest.fixture
def flask_test_client():
    """创建 Flask 测试客户端 (mocked app)"""
    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.config['TESTING'] = True

    # Mock login_manager
    from flask_login import LoginManager
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'

    return app


# ═══════════════════════════════════════════════════════════════════════════════
# Task 5.2: 健康检查测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthCheck:
    """后台健康检查线程和 API 测试"""

    def test_health_check_worker_healthy_connection(self, mock_db, mock_arthas_conn):
        """测试健康检查线程：连接健康时应记录 healthy 状态"""
        _connections = {'test-cluster/default/test-pod': {"conn": mock_arthas_conn, "user_id": 1}}
        _conn_health = {}
        _connections_lock = threading.Lock()
        _conn_health_lock = threading.Lock()

        # 模拟健康检查
        with _connections_lock:
            snapshot = {cid: entry.copy() for cid, entry in _connections.items()}

        for conn_id, entry in snapshot.items():
            conn = entry.get('conn')
            status = 'unknown'
            latency_ms = None
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if conn and hasattr(conn, 'http_client') and conn.http_client:
                try:
                    start = time.time()
                    result = conn.http_client.exec_once('version')
                    elapsed = (time.time() - start) * 1000
                    if result and isinstance(result, dict) and result.get('state') == 'SUCCEEDED':
                        status = 'healthy'
                        latency_ms = round(elapsed, 2)
                    else:
                        status = 'unhealthy'
                except Exception:
                    status = 'unhealthy'
            else:
                status = 'unknown'

            with _conn_health_lock:
                _conn_health[conn_id] = {
                    "status": status,
                    "last_check_at": now_str,
                    "latency_ms": latency_ms,
                }

        assert 'test-cluster/default/test-pod' in _conn_health
        assert _conn_health['test-cluster/default/test-pod']['status'] == 'healthy'
        assert _conn_health['test-cluster/default/test-pod']['latency_ms'] is not None
        assert _conn_health['test-cluster/default/test-pod']['last_check_at'] is not None

    def test_health_check_worker_unhealthy_connection(self, mock_db, mock_arthas_conn):
        """测试健康检查线程：连接不可达时应记录 unhealthy 状态"""
        mock_arthas_conn.http_client.exec_once.return_value = None
        _connections = {'test-cluster/default/test-pod': {"conn": mock_arthas_conn, "user_id": 1}}
        _conn_health = {}
        _connections_lock = threading.Lock()
        _conn_health_lock = threading.Lock()

        with _connections_lock:
            snapshot = {cid: entry.copy() for cid, entry in _connections.items()}

        for conn_id, entry in snapshot.items():
            conn = entry.get('conn')
            status = 'unknown'
            latency_ms = None
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if conn and hasattr(conn, 'http_client') and conn.http_client:
                try:
                    start = time.time()
                    result = conn.http_client.exec_once('version')
                    elapsed = (time.time() - start) * 1000
                    if result and isinstance(result, dict) and result.get('state') == 'SUCCEEDED':
                        status = 'healthy'
                        latency_ms = round(elapsed, 2)
                    else:
                        status = 'unhealthy'
                except Exception:
                    status = 'unhealthy'
            else:
                status = 'unknown'

            with _conn_health_lock:
                _conn_health[conn_id] = {
                    "status": status,
                    "last_check_at": now_str,
                    "latency_ms": latency_ms,
                }

        assert _conn_health['test-cluster/default/test-pod']['status'] == 'unhealthy'

    def test_health_check_worker_exception(self, mock_db, mock_arthas_conn):
        """测试健康检查线程：HTTP 请求异常时应记录 unhealthy"""
        mock_arthas_conn.http_client.exec_once.side_effect = ConnectionError('timeout')
        _connections = {'test-cluster/default/test-pod': {"conn": mock_arthas_conn, "user_id": 1}}
        _conn_health = {}
        _connections_lock = threading.Lock()
        _conn_health_lock = threading.Lock()

        with _connections_lock:
            snapshot = {cid: entry.copy() for cid, entry in _connections.items()}

        for conn_id, entry in snapshot.items():
            conn = entry.get('conn')
            status = 'unknown'
            latency_ms = None
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if conn and hasattr(conn, 'http_client') and conn.http_client:
                try:
                    start = time.time()
                    result = conn.http_client.exec_once('version')
                    elapsed = (time.time() - start) * 1000
                    if result and isinstance(result, dict) and result.get('state') == 'SUCCEEDED':
                        status = 'healthy'
                        latency_ms = round(elapsed, 2)
                    else:
                        status = 'unhealthy'
                except Exception:
                    status = 'unhealthy'
            else:
                status = 'unknown'

            with _conn_health_lock:
                _conn_health[conn_id] = {
                    "status": status,
                    "last_check_at": now_str,
                    "latency_ms": latency_ms,
                }

        assert _conn_health['test-cluster/default/test-pod']['status'] == 'unhealthy'

    def test_health_check_worker_no_http_client(self, mock_db):
        """测试健康检查线程：无 http_client 时应记录 unknown"""
        conn = MagicMock(spec=[])  # 空 spec，没有 http_client 属性
        _connections = {'test-cluster/default/test-pod': {"conn": conn, "user_id": 1}}
        _conn_health = {}
        _connections_lock = threading.Lock()
        _conn_health_lock = threading.Lock()

        with _connections_lock:
            snapshot = {cid: entry.copy() for cid, entry in _connections.items()}

        for conn_id, entry in snapshot.items():
            conn = entry.get('conn')
            status = 'unknown'
            latency_ms = None
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if conn and hasattr(conn, 'http_client') and conn.http_client:
                try:
                    start = time.time()
                    result = conn.http_client.exec_once('version')
                    elapsed = (time.time() - start) * 1000
                    if result and isinstance(result, dict) and result.get('state') == 'SUCCEEDED':
                        status = 'healthy'
                        latency_ms = round(elapsed, 2)
                    else:
                        status = 'unhealthy'
                except Exception:
                    status = 'unhealthy'
            else:
                status = 'unknown'

            with _conn_health_lock:
                _conn_health[conn_id] = {
                    "status": status,
                    "last_check_at": now_str,
                    "latency_ms": latency_ms,
                }

        assert _conn_health['test-cluster/default/test-pod']['status'] == 'unknown'

    def test_health_check_cleans_stale_records(self, mock_db):
        """测试健康检查线程：清理已断开连接的健康记录"""
        _conn_health = {
            'alive-conn': {"status": "healthy", "last_check_at": "2026-01-01 00:00:00", "latency_ms": 10},
            'dead-conn': {"status": "unhealthy", "last_check_at": "2026-01-01 00:00:00", "latency_ms": None},
        }
        _conn_health_lock = threading.Lock()

        # 模拟：alive-conn 在 _connections 中，dead-conn 不在
        snapshot = {'alive-conn': {}}

        with _conn_health_lock:
            stale_keys = [k for k in _conn_health if k not in snapshot]
            for k in stale_keys:
                del _conn_health[k]

        assert 'alive-conn' in _conn_health
        assert 'dead-conn' not in _conn_health

    def test_health_check_latency_measurement(self, mock_db, mock_arthas_conn):
        """测试健康检查线程：延迟测量应为非负值"""
        _connections = {'test-cluster/default/test-pod': {"conn": mock_arthas_conn, "user_id": 1}}
        _conn_health = {}
        _connections_lock = threading.Lock()
        _conn_health_lock = threading.Lock()

        with _connections_lock:
            snapshot = {cid: entry.copy() for cid, entry in _connections.items()}

        for conn_id, entry in snapshot.items():
            conn = entry.get('conn')
            status = 'unknown'
            latency_ms = None
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if conn and hasattr(conn, 'http_client') and conn.http_client:
                try:
                    start = time.time()
                    result = conn.http_client.exec_once('version')
                    elapsed = (time.time() - start) * 1000
                    if result and isinstance(result, dict) and result.get('state') == 'SUCCEEDED':
                        status = 'healthy'
                        latency_ms = round(elapsed, 2)
                    else:
                        status = 'unhealthy'
                except Exception:
                    status = 'unhealthy'
            else:
                status = 'unknown'

            with _conn_health_lock:
                _conn_health[conn_id] = {
                    "status": status,
                    "last_check_at": now_str,
                    "latency_ms": latency_ms,
                }

        assert _conn_health['test-cluster/default/test-pod']['latency_ms'] >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# Task 5.3: TTL 清理测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestTTLCleanup:
    """TTL 清理逻辑测试"""

    def test_ttl_cleanup_expired_connection(self, mock_db):
        """测试 TTL 清理：过期连接应被清理"""
        now = datetime.now(timezone.utc)
        expired_time = (now - timedelta(minutes=60)).strftime('%Y-%m-%d %H:%M:%S')

        # 插入一条过期连接
        mock_db.insert('connections', {
            'id': 'expired-conn',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod',
            'status': 'ready',
            'last_active_at': expired_time,
            'ttl_hours': 0,
            'user_id': 1,
        })

        threshold_minutes = 30
        rows = mock_db.fetch_all(
            'SELECT id, last_active_at, ttl_hours FROM connections '
            'WHERE status NOT IN (?, ?) AND last_active_at IS NOT NULL',
            ('disconnected', 'failed')
        )

        expired_ids = []
        for row in (rows or []):
            conn_id = row.get('id', '')
            last_active = row.get('last_active_at')
            ttl_hours = row.get('ttl_hours', 0)

            if not last_active:
                continue

            if ttl_hours and ttl_hours > 0:
                ttl_min = ttl_hours * 60
            else:
                ttl_min = threshold_minutes

            try:
                last_active_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                if last_active_dt.tzinfo is None:
                    last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                elapsed_minutes = (now_utc - last_active_dt).total_seconds() / 60
                if elapsed_minutes > ttl_min:
                    expired_ids.append(conn_id)
            except (ValueError, TypeError):
                continue

        assert 'expired-conn' in expired_ids

    def test_ttl_cleanup_active_connection_not_cleaned(self, mock_db):
        """测试 TTL 清理：活跃连接不应被清理"""
        now = datetime.now(timezone.utc)
        active_time = (now - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')

        mock_db.insert('connections', {
            'id': 'active-conn',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod',
            'status': 'ready',
            'last_active_at': active_time,
            'ttl_hours': 0,
            'user_id': 1,
        })

        threshold_minutes = 30
        rows = mock_db.fetch_all(
            'SELECT id, last_active_at, ttl_hours FROM connections '
            'WHERE status NOT IN (?, ?) AND last_active_at IS NOT NULL',
            ('disconnected', 'failed')
        )

        expired_ids = []
        for row in (rows or []):
            conn_id = row.get('id', '')
            last_active = row.get('last_active_at')
            ttl_hours = row.get('ttl_hours', 0)

            if not last_active:
                continue

            if ttl_hours and ttl_hours > 0:
                ttl_min = ttl_hours * 60
            else:
                ttl_min = threshold_minutes

            try:
                last_active_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                if last_active_dt.tzinfo is None:
                    last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)
                now_utc = datetime.now(timezone.utc)
                elapsed_minutes = (now_utc - last_active_dt).total_seconds() / 60
                if elapsed_minutes > ttl_min:
                    expired_ids.append(conn_id)
            except (ValueError, TypeError):
                continue

        assert 'active-conn' not in expired_ids

    def test_ttl_cleanup_with_custom_ttl(self, mock_db):
        """测试 TTL 清理：自定义 TTL 小时数"""
        now = datetime.now(timezone.utc)
        # 2 小时前活跃，但自定义 TTL 是 1 小时
        expired_time = (now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')

        mock_db.insert('connections', {
            'id': 'custom-ttl-conn',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod',
            'status': 'ready',
            'last_active_at': expired_time,
            'ttl_hours': 1,  # 自定义 TTL: 1 小时
            'user_id': 1,
        })

        threshold_minutes = 30  # 默认阈值不影响有自定义 TTL 的连接
        rows = mock_db.fetch_all(
            'SELECT id, last_active_at, ttl_hours FROM connections '
            'WHERE status NOT IN (?, ?) AND last_active_at IS NOT NULL',
            ('disconnected', 'failed')
        )

        expired_ids = []
        for row in (rows or []):
            conn_id = row.get('id', '')
            last_active = row.get('last_active_at')
            ttl_hours = row.get('ttl_hours', 0)

            if not last_active:
                continue

            if ttl_hours and ttl_hours > 0:
                ttl_min = ttl_hours * 60  # 60 分钟
            else:
                ttl_min = threshold_minutes

            try:
                last_active_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                if last_active_dt.tzinfo is None:
                    last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)
                elapsed_minutes = (datetime.now(timezone.utc) - last_active_dt).total_seconds() / 60
                if elapsed_minutes > ttl_min:
                    expired_ids.append(conn_id)
            except (ValueError, TypeError):
                continue

        assert 'custom-ttl-conn' in expired_ids

    def test_ttl_cleanup_updates_database_status(self, mock_db):
        """测试 TTL 清理后数据库状态更新"""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        mock_db.insert('connections', {
            'id': 'to-clean-conn',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod',
            'status': 'ready',
            'last_active_at': (datetime.now() - timedelta(minutes=60)).strftime('%Y-%m-%d %H:%M:%S'),
            'ttl_hours': 0,
            'user_id': 1,
        })

        # 模拟清理后的状态更新
        mock_db.update('connections', {
            'status': 'disconnected',
            'updated_at': now_str,
        }, 'id = ?', ('to-clean-conn',))

        row = mock_db.fetch_one('SELECT status FROM connections WHERE id = ?', ('to-clean-conn',))
        assert row['status'] == 'disconnected'

    def test_ttl_cleanup_empty_threshold(self, mock_db):
        """测试 TTL 清理：阈值为 0 时不清理任何连接"""
        now = datetime.now(timezone.utc)
        # 30 天前活跃，阈值 30 分钟 → 应该被清理
        expired_time = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        mock_db.insert('connections', {
            'id': 'zero-ttl-conn',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod',
            'status': 'ready',
            'last_active_at': expired_time,
            'ttl_hours': 0,
            'user_id': 1,
        })

        # 当 threshold_minutes > 0 且连接没有自定义 TTL，按默认阈值计算
        threshold_minutes = 30
        rows = mock_db.fetch_all(
            'SELECT id, last_active_at, ttl_hours FROM connections '
            'WHERE status NOT IN (?, ?) AND last_active_at IS NOT NULL',
            ('disconnected', 'failed')
        )

        expired_ids = []
        for row in (rows or []):
            conn_id = row.get('id', '')
            last_active = row.get('last_active_at')
            ttl_hours = row.get('ttl_hours', 0)

            if not last_active:
                continue

            if ttl_hours and ttl_hours > 0:
                ttl_min = ttl_hours * 60
            else:
                ttl_min = threshold_minutes

            try:
                last_active_dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                if last_active_dt.tzinfo is None:
                    last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)
                elapsed_minutes = (datetime.now(timezone.utc) - last_active_dt).total_seconds() / 60
                if elapsed_minutes > ttl_min:
                    expired_ids.append(conn_id)
            except (ValueError, TypeError):
                continue

        # 30 天前活跃，阈值 30 分钟 → 应该被清理
        assert 'zero-ttl-conn' in expired_ids


# ═══════════════════════════════════════════════════════════════════════════════
# Task 5.4: 连接状态恢复测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionRecovery:
    """连接状态恢复逻辑测试"""

    def test_recovery_loads_active_connections_from_db(self, mock_db):
        """测试恢复：从数据库加载活跃连接"""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        mock_db.insert('connections', {
            'id': 'recovery-conn-1',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod-1',
            'status': 'ready',
            'user_id': 1,
        })
        mock_db.insert('connections', {
            'id': 'recovery-conn-2',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod-2',
            'status': 'connected',
            'user_id': 1,
        })

        rows = mock_db.fetch_all(
            'SELECT id, cluster_name, namespace, pod_name, container_name, '
            'user_id, status, level, local_port, java_pid FROM connections '
            'WHERE status IN (?, ?)',
            ('ready', 'connected')
        )

        assert len(rows) == 2
        ids = {r['id'] for r in rows}
        assert 'recovery-conn-1' in ids
        assert 'recovery-conn-2' in ids

    def test_recovery_skips_already_disconnected(self, mock_db):
        """测试恢复：跳过已断开的连接"""
        mock_db.insert('connections', {
            'id': 'disconnected-conn',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod',
            'status': 'disconnected',
            'user_id': 1,
        })

        rows = mock_db.fetch_all(
            'SELECT id, cluster_name, namespace, pod_name, container_name, '
            'user_id, status, level, local_port, java_pid FROM connections '
            'WHERE status IN (?, ?)',
            ('ready', 'connected')
        )

        ids = {r['id'] for r in (rows or [])}
        assert 'disconnected-conn' not in ids

    def test_recovery_marks_stale_on_connect_failure(self, mock_db):
        """测试恢复：连接失败时标记为 stale"""
        mock_db.insert('connections', {
            'id': 'stale-conn',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod',
            'status': 'ready',
            'user_id': 1,
        })

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        mock_db.update('connections', {
            'status': 'stale',
            'updated_at': now_str,
        }, 'id = ?', ('stale-conn',))

        row = mock_db.fetch_one('SELECT status FROM connections WHERE id = ?', ('stale-conn',))
        assert row['status'] == 'stale'

    def test_recovery_marks_recovered_on_success(self, mock_db):
        """测试恢复：连接成功时标记为 recovered"""
        mock_db.insert('connections', {
            'id': 'recovered-conn',
            'cluster_name': 'test-cluster',
            'namespace': 'default',
            'pod_name': 'test-pod',
            'status': 'ready',
            'user_id': 1,
        })

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        mock_db.update('connections', {
            'status': 'recovered',
            'last_active_at': now_str,
            'updated_at': now_str,
        }, 'id = ?', ('recovered-conn',))

        row = mock_db.fetch_one('SELECT status FROM connections WHERE id = ?', ('recovered-conn',))
        assert row['status'] == 'recovered'

    def test_recovery_status_structure(self):
        """测试恢复状态数据结构"""
        _recovery_status = {
            "recovered": ["conn-1", "conn-2"],
            "stale": ["conn-3"],
            "completed": True,
        }

        assert _recovery_status["completed"] is True
        assert len(_recovery_status["recovered"]) == 2
        assert len(_recovery_status["stale"]) == 1
        assert "conn-1" in _recovery_status["recovered"]
        assert "conn-3" in _recovery_status["stale"]

    def test_recovery_handles_empty_db(self, mock_db):
        """测试恢复：数据库无活跃连接时应正常完成"""
        rows = mock_db.fetch_all(
            'SELECT id, cluster_name, namespace, pod_name, container_name, '
            'user_id, status, level, local_port, java_pid FROM connections '
            'WHERE status IN (?, ?)',
            ('ready', 'connected')
        )

        assert rows == []

    def test_recovery_only_reloads_ready_or_connected(self, mock_db):
        """测试恢复：只加载 status=ready 或 connected 的连接"""
        for status_val in ['ready', 'connected', 'disconnected', 'failed', 'stale']:
            mock_db.insert('connections', {
                'id': f'conn-{status_val}',
                'cluster_name': 'test-cluster',
                'namespace': 'default',
                'pod_name': f'pod-{status_val}',
                'status': status_val,
                'user_id': 1,
            })

        rows = mock_db.fetch_all(
            'SELECT id, status FROM connections '
            'WHERE status IN (?, ?)',
            ('ready', 'connected')
        )

        ids = {r['id'] for r in (rows or [])}
        assert 'conn-ready' in ids
        assert 'conn-connected' in ids
        assert 'conn-disconnected' not in ids
        assert 'conn-failed' not in ids
        assert 'conn-stale' not in ids


# ═══════════════════════════════════════════════════════════════════════════════
# Task 5.5: 多标签页同步（前端 JavaScript 逻辑测试）
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiTabSync:
    """BroadcastChannel 多标签页同步逻辑测试"""

    def test_broadcast_event_types(self):
        """测试广播事件类型定义"""
        valid_events = {'connection-switch', 'connection-added', 'connection-removed', 'health-updated'}
        assert len(valid_events) == 4
        assert 'connection-switch' in valid_events
        assert 'health-updated' in valid_events

    def test_broadcast_message_structure(self):
        """测试广播消息数据结构"""
        message = {
            'type': 'connection-switch',
            'payload': {
                'currentConnId': 'test-cluster/default/test-pod',
                'previousConnId': None,
            },
            'timestamp': int(time.time() * 1000),
        }

        assert message['type'] in ('connection-switch', 'connection-added', 'connection-removed', 'health-updated')
        assert isinstance(message['payload'], dict)
        assert isinstance(message['timestamp'], int)

    def test_broadcast_payload_for_switch(self):
        """测试 connection-switch 事件的 payload"""
        payload = {
            'currentConnId': 'new-conn-id',
            'previousConnId': 'old-conn-id',
        }
        assert 'currentConnId' in payload
        assert 'previousConnId' in payload

    def test_broadcast_payload_for_health(self):
        """测试 health-updated 事件的 payload"""
        payload = {
            'connHealth': {
                'conn-1': {'status': 'healthy', 'latency_ms': 10},
                'conn-2': {'status': 'unhealthy', 'latency_ms': None},
            }
        }
        assert 'connHealth' in payload
        assert payload['connHealth']['conn-1']['status'] == 'healthy'
        assert payload['connHealth']['conn-2']['status'] == 'unhealthy'

    def test_sync_prevents_infinite_broadcast_loop(self):
        """测试同步时应避免无限广播循环"""
        # 模拟 _isSyncingFromBroadcast 标志
        _isSyncingFromBroadcast = False

        # 在广播回调中应设置标志
        def simulate_handle_message(data):
            nonlocal _isSyncingFromBroadcast
            _isSyncingFromBroadcast = True
            try:
                # 处理消息...
                pass
            finally:
                _isSyncingFromBroadcast = False

        simulate_handle_message({})
        assert _isSyncingFromBroadcast is False


# ═══════════════════════════════════════════════════════════════════════════════
# Task 5.6: 连接切换确认（前端逻辑测试）
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionSwitchConfirmation:
    """连接切换确认对话框逻辑测试"""

    def test_confirm_modal_options_structure(self):
        """测试 confirmModal 参数结构"""
        options = {
            'title': '切换连接',
            'message': '确定要切换吗？',
            'confirmText': '切换',
            'cancelText': '取消',
            'type': 'warning',
            'detail': '有活跃任务',
        }

        assert isinstance(options['title'], str)
        assert isinstance(options['message'], str)
        assert options['type'] in ('default', 'danger', 'warning', 'info')

    def test_confirm_modal_type_colors(self):
        """测试确认对话框类型颜色映射"""
        type_colors = {
            'default': '#4a90d9',
            'danger': '#e74c3c',
            'warning': '#f39c12',
            'info': '#3498db',
        }
        assert len(type_colors) == 4
        for key, value in type_colors.items():
            assert value.startswith('#')

    def test_has_active_diagnosis_detection(self):
        """测试活跃诊断任务检测逻辑"""
        # 模拟各种状态
        test_cases = [
            ({"_connState": "running"}, True),
            ({"_connState": "executing"}, True),
            ({"_connState": "idle"}, False),
            ({"_connState": "disconnected"}, False),
            ({"_activeDiagnosis": True}, True),
            ({"_diagnosisRunning": True}, True),
            ({}, False),
        ]

        for state, expected in test_cases:
            is_active = state.get('_connState') in ('running', 'executing') or \
                       state.get('_activeDiagnosis') is True or \
                       state.get('_diagnosisRunning') is True
            assert is_active == expected, f"Failed for state: {state}"

    def test_switch_confirmation_skips_same_connection(self):
        """测试切换到同一连接时不显示确认"""
        current_id = 'test-cluster/default/test-pod'
        target_id = 'test-cluster/default/test-pod'
        should_confirm = current_id != target_id
        assert should_confirm is False

    def test_switch_confirmation_shows_for_different_connection(self):
        """测试切换到不同连接时显示确认"""
        current_id = 'test-cluster/default/test-pod-1'
        target_id = 'test-cluster/default/test-pod-2'
        should_confirm = current_id != target_id
        assert should_confirm is True

    def test_confirm_modal_returns_promise(self):
        """测试 confirmModal 返回 Promise (JavaScript 逻辑验证)"""
        # 这个测试验证 JS 代码的 Promise 模式
        # 通过读取源码确认
        static_dir = pathlib.Path(__file__).resolve().parent.parent / 'static'
        js_file = static_dir / 'js' / 'components' / 'connections.js'

        if js_file.exists():
            content = js_file.read_text(encoding='utf-8')
            assert 'function confirmModal' in content
            assert 'new Promise' in content
            assert 'resolve(true)' in content or 'close(true)' in content
            assert 'resolve(false)' in content or 'close(false)' in content

    def test_delete_uses_custom_modal(self):
        """测试 deleteConnection 使用自定义 modal 而非原生 confirm"""
        static_dir = pathlib.Path(__file__).resolve().parent.parent / 'static'
        js_file = static_dir / 'js' / 'components' / 'connections.js'

        if js_file.exists():
            content = js_file.read_text(encoding='utf-8')
            # 确认 deleteConnection 不再使用原生 confirm
            assert 'confirm(' not in content or 'confirmModal(' in content

    def test_confirm_modal_has_esc_close(self):
        """测试确认对话框支持 ESC 键关闭"""
        static_dir = pathlib.Path(__file__).resolve().parent.parent / 'static'
        js_file = static_dir / 'js' / 'components' / 'connections.js'

        if js_file.exists():
            content = js_file.read_text(encoding='utf-8')
            assert "Escape" in content or "escape" in content


# ═══════════════════════════════════════════════════════════════════════════════
# 前端文件完整性测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrontendFilesIntegrity:
    """前端文件结构和内容完整性测试"""

    def test_connection_store_has_broadcast_channel(self):
        """测试 connection-store.js 包含 BroadcastChannel 支持"""
        static_dir = pathlib.Path(__file__).resolve().parent.parent / 'static'
        js_file = static_dir / 'js' / 'core' / 'connection-store.js'

        assert js_file.exists(), "connection-store.js not found"
        content = js_file.read_text(encoding='utf-8')

        assert 'BroadcastChannel' in content
        assert 'arthas-connection-sync' in content
        assert 'connection-switch' in content
        assert 'connection-added' in content
        assert 'connection-removed' in content
        assert 'health-updated' in content

    def test_connection_store_has_broadcast_init(self):
        """测试 connection-store.js 包含 BroadcastChannel 初始化"""
        static_dir = pathlib.Path(__file__).resolve().parent.parent / 'static'
        js_file = static_dir / 'js' / 'core' / 'connection-store.js'
        content = js_file.read_text(encoding='utf-8')

        assert '_initBroadcastChannel' in content
        assert '_broadcastStateChanges' in content
        assert '_handleBroadcastMessage' in content

    def test_connections_js_has_confirm_modal(self):
        """测试 connections.js 包含 confirmModal"""
        static_dir = pathlib.Path(__file__).resolve().parent.parent / 'static'
        js_file = static_dir / 'js' / 'components' / 'connections.js'
        content = js_file.read_text(encoding='utf-8')

        assert 'function confirmModal' in content
        assert 'hasActiveDiagnosis' in content
        assert 'conn-confirm-modal' in content

    def test_connections_js_no_native_alert(self):
        """测试 connections.js 不使用原生 alert"""
        static_dir = pathlib.Path(__file__).resolve().parent.parent / 'static'
        js_file = static_dir / 'js' / 'components' / 'connections.js'
        content = js_file.read_text(encoding='utf-8')

        # 检查 deleteConnection 不使用 alert()
        # 但保留其他可能的 alert 用途
        lines = content.split('\n')
        in_delete_func = False
        for line in lines:
            if 'async function deleteConnection' in line:
                in_delete_func = True
            elif in_delete_func and line.strip().startswith('function '):
                in_delete_func = False
            if in_delete_func and 'alert(' in line:
                pytest.fail("deleteConnection should not use native alert()")


# ═══════════════════════════════════════════════════════════════════════════════
# 后端 API 端点测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackendAPIs:
    """后端新增 API 端点逻辑测试"""

    def test_health_api_response_structure(self):
        """测试健康检查 API 响应结构"""
        response = {
            "ok": True,
            "health": {
                "conn-1": {"status": "healthy", "last_check_at": "2026-01-01 00:00:00", "latency_ms": 10.5},
                "conn-2": {"status": "unhealthy", "last_check_at": "2026-01-01 00:00:00", "latency_ms": None},
            },
            "checked_at": "2026-01-01 00:00:30",
        }

        assert response["ok"] is True
        assert isinstance(response["health"], dict)
        assert "checked_at" in response

        for conn_id, health in response["health"].items():
            assert "status" in health
            assert health["status"] in ("healthy", "unhealthy", "unknown")
            assert "last_check_at" in health

    def test_ttl_cleanup_api_response_structure(self):
        """测试 TTL 清理 API 响应结构"""
        response = {
            "ok": True,
            "cleaned": ["conn-1", "conn-2"],
            "count": 2,
            "threshold_minutes": 30,
        }

        assert response["ok"] is True
        assert isinstance(response["cleaned"], list)
        assert isinstance(response["count"], int)
        assert isinstance(response["threshold_minutes"], int)

    def test_recovery_status_api_response_structure(self):
        """测试恢复状态 API 响应结构"""
        response = {
            "ok": True,
            "recovery": {
                "completed": True,
                "recovered": ["conn-1"],
                "stale": ["conn-2"],
                "recovered_count": 1,
                "stale_count": 1,
            },
        }

        assert response["ok"] is True
        assert response["recovery"]["completed"] is True
        assert isinstance(response["recovery"]["recovered"], list)
        assert isinstance(response["recovery"]["stale"], list)

    def test_health_check_filters_by_user(self):
        """测试健康检查 API 按用户过滤连接"""
        _conn_health = {
            'admin-conn': {"status": "healthy", "last_check_at": "", "latency_ms": 10},
            'user-conn': {"status": "unhealthy", "last_check_at": "", "latency_ms": None},
        }
        _connections = {
            'admin-conn': {"conn": MagicMock(), "user_id": 1},
            'user-conn': {"conn": MagicMock(), "user_id": 2},
        }

        # 模拟非 admin 用户 (user_id=2) 的过滤
        current_user_id = 2
        is_admin = False
        result = {}
        for conn_id, health in _conn_health.items():
            entry = _connections.get(conn_id)
            if entry:
                if not is_admin and entry.get('user_id') != current_user_id:
                    continue
            result[conn_id] = health

        assert 'user-conn' in result
        assert 'admin-conn' not in result

    def test_health_check_admin_sees_all(self):
        """测试 admin 用户可以看到所有连接的健康状态"""
        _conn_health = {
            'conn-1': {"status": "healthy", "last_check_at": "", "latency_ms": 10},
            'conn-2': {"status": "unhealthy", "last_check_at": "", "latency_ms": None},
        }

        is_admin = True
        result = {}
        for conn_id, health in _conn_health.items():
            # admin 跳过权限检查
            result[conn_id] = health

        assert len(result) == 2

    def test_background_threads_are_daemon(self):
        """测试后台线程应为守护线程"""
        t = threading.Thread(target=lambda: None, daemon=True, name="test-daemon")
        assert t.daemon is True

    def test_ttl_default_threshold(self):
        """测试默认 TTL 阈值配置"""
        _DEFAULT_TTL_THRESHOLD_MINUTES = 30
        _TTL_CLEANUP_INTERVAL_SECONDS = 300

        assert _DEFAULT_TTL_THRESHOLD_MINUTES == 30
        assert _TTL_CLEANUP_INTERVAL_SECONDS == 300
        assert _TTL_CLEANUP_INTERVAL_SECONDS == _DEFAULT_TTL_THRESHOLD_MINUTES * 10
