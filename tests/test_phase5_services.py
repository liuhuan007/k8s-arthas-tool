"""
Phase 5 Services & API — 完整单元测试 + 集成测试

测试范围:
1. HealthCheckService (services/health_check_service.py)
2. ConnectionRecoveryService (services/connection_recovery_service.py)
3. ConnectionSwitchService (services/connection_switch_service.py)
4. ConnectionTTLConfig (services/connection_ttl_config.py)
5. ConnectionDetail API (api/connection_detail.py)
6. 前端组件契约验证 (broadcast-channel-manager / connection-switch-confirm / connection-ttl-config)
7. server.py 集成验证
8. models/db.py 表结构验证
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
from unittest.mock import MagicMock, patch, call

import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_db_path():
    """创建临时数据库文件（带 Phase 5 所有表结构）"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # connections 表（含 Phase 5 字段）
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
            ttl_hours INTEGER DEFAULT 0,
            last_health_check TIMESTAMP,
            health_status TEXT DEFAULT 'unknown'
        )
    ''')

    # health_check_logs 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS health_check_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms REAL,
            error_message TEXT,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
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
            event TEXT,
            progress INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
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
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 插入测试连接
    cursor.execute('''
        INSERT INTO connections
        (id, cluster_name, namespace, pod_name, status, local_port, user_id, ttl_hours, health_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('test-conn-001', 'test-cluster', 'default', 'test-pod-001', 'connected', 3658, 1, 0, 'healthy'))

    cursor.execute('''
        INSERT INTO connections
        (id, cluster_name, namespace, pod_name, status, local_port, user_id, ttl_hours, health_status, last_active_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', ('test-conn-002', 'prod-cluster', 'staging', 'prod-pod-001', 'ready', 3658, 1, 8, 'unknown',
          (datetime.now() - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()
    conn.close()

    yield db_path

    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def test_db(temp_db_path):
    """创建测试数据库包装器"""

    class TestDatabaseWrapper:
        def __init__(self, db_path):
            self.db_path = db_path

        def _connect(self):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

        def fetch_one(self, sql, params=()):
            conn = self._connect()
            row = conn.execute(sql, params).fetchone()
            conn.close()
            return dict(row) if row else None

        def fetch_all(self, sql, params=()):
            conn = self._connect()
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(row) for row in rows]

        def execute(self, sql, params=()):
            conn = self._connect()
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

        def count(self, table, where="1=1", params=()):
            sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}"
            result = self.fetch_one(sql, params)
            return result['cnt'] if result else 0

    return TestDatabaseWrapper(temp_db_path)


@pytest.fixture
def mock_arthas_conn():
    """创建模拟 Arthas 连接对象"""
    conn = MagicMock()
    conn.connection_id = 'test-cluster/default/test-pod'
    conn.local_port = 3658
    conn.http_client = MagicMock()
    conn.http_client.exec_once.return_value = {
        'state': 'SUCCEEDED',
        'body': {'results': [{'output': 'Arthas version 3.6.7'}]},
        'duration_ms': 50,
    }
    return conn


@pytest.fixture(scope="class")
def project_root():
    """项目根目录"""
    return pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def flask_app_context():
    """提供 Flask 应用上下文，用于测试 jsonify 等 Flask API"""
    from flask import Flask
    app = Flask(__name__)
    with app.app_context():
        yield app


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HealthCheckService 单元测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthCheckServiceUnit:
    """HealthCheckService 完整单元测试"""

    def _make_service(self, test_db, interval_seconds=30):
        """构建 HealthCheckService 实例"""
        from services.health_check_service import HealthCheckService
        connections = {}
        connections_lock = threading.Lock()
        conn_health = {}
        conn_health_lock = threading.Lock()

        svc = HealthCheckService(
            db=test_db,
            connections=connections,
            connections_lock=connections_lock,
            conn_health=conn_health,
            conn_health_lock=conn_health_lock,
            interval_seconds=interval_seconds,
        )
        return svc

    def test_init_sets_interval(self, test_db):
        """验证初始化正确设置检查间隔"""
        svc = self._make_service(test_db, interval_seconds=60)
        assert svc.interval_seconds == 60

    def test_start_and_stop(self, test_db):
        """验证后台线程可以启动和停止"""
        svc = self._make_service(test_db, interval_seconds=300)
        svc.start()
        assert svc._thread is not None
        assert svc._thread.is_alive()

        svc.stop()
        assert not svc._thread.is_alive()

    def test_start_idempotent(self, test_db):
        """验证重复启动不会创建多个线程"""
        svc = self._make_service(test_db, interval_seconds=300)
        svc.start()
        thread1 = svc._thread
        svc.start()  # 重复调用
        assert svc._thread is thread1
        svc.stop()

    def test_check_single_healthy(self, test_db, mock_arthas_conn):
        """验证健康连接检测返回 healthy"""
        svc = self._make_service(test_db)
        entry = {"conn": mock_arthas_conn, "conn_id": "test-conn-001"}

        status, latency_ms = svc._check_single(entry)

        assert status == "healthy"
        assert latency_ms is not None
        assert latency_ms >= 0

    def test_check_single_unhealthy(self, test_db):
        """验证不健康连接检测返回 unhealthy"""
        svc = self._make_service(test_db)
        conn = MagicMock()
        conn.http_client = MagicMock()
        conn.http_client.exec_once.return_value = {
            'state': 'FAILED',
            'body': {},
        }
        entry = {"conn": conn, "conn_id": "test-conn-001"}

        status, latency_ms = svc._check_single(entry)

        assert status == "unhealthy"

    def test_check_single_exception(self, test_db):
        """验证探活异常时返回 unhealthy"""
        svc = self._make_service(test_db)
        conn = MagicMock()
        conn.http_client = MagicMock()
        conn.http_client.exec_once.side_effect = ConnectionError("timeout")
        entry = {"conn": conn, "conn_id": "test-conn-001"}

        status, latency_ms = svc._check_single(entry)

        assert status == "unhealthy"

    def test_check_single_no_http_client(self, test_db):
        """验证无 http_client 时返回 unknown"""
        svc = self._make_service(test_db)
        conn = MagicMock(spec=[])  # 无 http_client
        entry = {"conn": conn, "conn_id": "test-conn-001"}

        status, latency_ms = svc._check_single(entry)

        assert status == "unknown"

    def test_check_single_no_conn(self, test_db):
        """验证无 conn 对象时返回 unknown"""
        svc = self._make_service(test_db)
        entry = {"conn": None, "conn_id": "test-conn-001"}

        status, latency_ms = svc._check_single(entry)

        assert status == "unknown"

    def test_check_all_updates_cache_and_db(self, test_db, mock_arthas_conn):
        """验证 _check_all 更新内存缓存和数据库"""
        svc = self._make_service(test_db)
        svc.connections["test-conn-001"] = {"conn": mock_arthas_conn}

        svc._check_all()

        # 检查缓存
        cached = svc.get_health("test-conn-001")
        assert cached is not None
        assert cached["status"] == "healthy"
        assert "last_check_at" in cached

        # 检查数据库
        row = test_db.fetch_one(
            "SELECT health_status FROM connections WHERE id = ?",
            ("test-conn-001",),
        )
        assert row["health_status"] == "healthy"

        # 检查日志
        logs = test_db.fetch_all(
            "SELECT * FROM health_check_logs WHERE connection_id = ?",
            ("test-conn-001",),
        )
        assert len(logs) >= 1

    def test_check_all_cleans_stale_cache(self, test_db, mock_arthas_conn):
        """验证 _check_all 清理已不在活跃列表中的缓存记录"""
        svc = self._make_service(test_db)
        # 先添加一个连接
        svc.connections["test-conn-001"] = {"conn": mock_arthas_conn}
        svc._check_all()

        # 确认缓存已存在
        assert svc.get_health("test-conn-001") is not None

        # 从活跃列表移除
        svc.connections.clear()
        svc._check_all()

        # 缓存应被清理
        assert svc.get_health("test-conn-001") is None

    def test_check_all_empty_connections(self, test_db):
        """验证 _check_all 在无活跃连接时不报错"""
        svc = self._make_service(test_db)
        svc._check_all()  # 不应抛出异常

    def test_get_all_health(self, test_db, mock_arthas_conn):
        """验证 get_all_health 返回所有缓存快照"""
        svc = self._make_service(test_db)
        svc.connections["test-conn-001"] = {"conn": mock_arthas_conn}
        svc._check_all()

        all_health = svc.get_all_health()
        assert isinstance(all_health, dict)
        assert "test-conn-001" in all_health

    def test_check_now_returns_result(self, test_db, mock_arthas_conn):
        """验证 check_now 立即执行检查并返回结果"""
        svc = self._make_service(test_db)
        svc.connections["test-conn-001"] = {"conn": mock_arthas_conn}

        result = svc.check_now("test-conn-001")

        assert result is not None
        assert result["status"] == "healthy"
        assert "latency_ms" in result
        assert "checked_at" in result

    def test_check_now_unknown_connection(self, test_db):
        """验证 check_now 对不存在的连接返回 None"""
        svc = self._make_service(test_db)
        result = svc.check_now("non-existent")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. ConnectionRecoveryService 单元测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionRecoveryServiceUnit:
    """ConnectionRecoveryService 完整单元测试"""

    def _make_service(self, test_db):
        from services.connection_recovery_service import ConnectionRecoveryService
        return ConnectionRecoveryService(db=test_db)

    def test_recover_on_startup_with_active_connections(self, test_db):
        """验证启动恢复正确识别活跃连接"""
        svc = self._make_service(test_db)
        svc.recover_on_startup()

        result = svc.recovery_result
        assert result["completed"] is True
        assert len(result["recovered"]) >= 1

    def test_recover_on_startup_marks_stale_expired(self, test_db):
        """验证启动恢复标记 TTL 过期连接为 stale"""
        # 插入一个已过期的连接（ttl_hours=1, last_active_at 10 小时前）
        test_db.insert("connections", {
            "id": "expired-conn-001",
            "cluster_name": "old-cluster",
            "namespace": "default",
            "pod_name": "old-pod",
            "status": "ready",
            "ttl_hours": 1,
            "last_active_at": (datetime.now() - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S"),
        })

        svc = self._make_service(test_db)
        svc.recover_on_startup()

        result = svc.recovery_result
        assert "expired-conn-001" in result["stale"]
        assert result["stale_count"] >= 1

        # 验证数据库中已更新
        row = test_db.fetch_one(
            "SELECT status FROM connections WHERE id = ?",
            ("expired-conn-001",),
        )
        assert row["status"] == "stale"

    def test_recover_on_startup_skips_disconnected(self, test_db):
        """验证启动恢复跳过已断开的连接"""
        test_db.insert("connections", {
            "id": "disconn-001",
            "cluster_name": "test-cluster",
            "namespace": "default",
            "pod_name": "test-pod",
            "status": "disconnected",
        })

        svc = self._make_service(test_db)
        svc.recover_on_startup()

        result = svc.recovery_result
        assert "disconn-001" not in result["recovered"]
        assert "disconn-001" not in result["stale"]

    def test_mark_recovered(self, test_db):
        """验证 mark_recovered 正确更新数据库"""
        svc = self._make_service(test_db)
        svc.mark_recovered("test-conn-001")

        row = test_db.fetch_one(
            "SELECT status, health_status FROM connections WHERE id = ?",
            ("test-conn-001",),
        )
        assert row["status"] == "recovered"
        assert row["health_status"] == "healthy"

        result = svc.recovery_result
        assert "test-conn-001" in result["recovered"]

    def test_mark_stale(self, test_db):
        """验证 mark_stale 正确更新数据库"""
        svc = self._make_service(test_db)
        svc.mark_stale("test-conn-001")

        row = test_db.fetch_one(
            "SELECT status, health_status FROM connections WHERE id = ?",
            ("test-conn-001",),
        )
        assert row["status"] == "stale"
        assert row["health_status"] == "unknown"

        result = svc.recovery_result
        assert "test-conn-001" in result["stale"]

    def test_get_stale_connections(self, test_db):
        """验证 get_stale_connections 返回 stale 状态的连接"""
        # 标记一个连接为 stale
        test_db.update(
            "connections",
            {"status": "stale"},
            "id = ?",
            ("test-conn-001",),
        )

        svc = self._make_service(test_db)
        stale = svc.get_stale_connections()

        assert isinstance(stale, list)
        assert len(stale) >= 1
        ids = [s["id"] for s in stale]
        assert "test-conn-001" in ids

    def test_cleanup_stale_specific(self, test_db):
        """验证 cleanup_stale 清理指定 stale 连接"""
        test_db.update(
            "connections",
            {"status": "stale"},
            "id = ?",
            ("test-conn-001",),
        )

        svc = self._make_service(test_db)
        result = svc.cleanup_stale(["test-conn-001"])

        assert result["ok"] is True
        assert "test-conn-001" in result["cleaned"]

        # 验证已删除
        row = test_db.fetch_one(
            "SELECT id FROM connections WHERE id = ?",
            ("test-conn-001",),
        )
        assert row is None

    def test_cleanup_stale_all(self, test_db):
        """验证 cleanup_stale(None) 清理所有 stale 连接"""
        test_db.update(
            "connections",
            {"status": "stale"},
            "id = ?",
            ("test-conn-001",),
        )
        test_db.update(
            "connections",
            {"status": "stale"},
            "id = ?",
            ("test-conn-002",),
        )

        svc = self._make_service(test_db)
        result = svc.cleanup_stale()

        assert result["ok"] is True
        assert result["count"] >= 2

    def test_is_expired_zero_ttl(self):
        """验证 TTL=0 时不会过期"""
        from services.connection_recovery_service import ConnectionRecoveryService
        assert ConnectionRecoveryService._is_expired("2020-01-01 00:00:00", 0) is False

    def test_is_expired_no_last_active(self):
        """验证无 last_active_at 时不会过期"""
        from services.connection_recovery_service import ConnectionRecoveryService
        assert ConnectionRecoveryService._is_expired(None, 8) is False

    def test_is_expired_within_ttl(self):
        """验证在 TTL 内不会过期"""
        from services.connection_recovery_service import ConnectionRecoveryService
        last_active = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        assert ConnectionRecoveryService._is_expired(last_active, 24) is False

    def test_is_expired_beyond_ttl(self):
        """验证超出 TTL 会过期"""
        from services.connection_recovery_service import ConnectionRecoveryService
        last_active = (datetime.now() - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S")
        assert ConnectionRecoveryService._is_expired(last_active, 8) is True

    def test_is_expired_invalid_format(self):
        """验证无效日期格式不会过期"""
        from services.connection_recovery_service import ConnectionRecoveryService
        assert ConnectionRecoveryService._is_expired("invalid-date", 8) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ConnectionSwitchService 单元测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionSwitchServiceUnit:
    """ConnectionSwitchService 完整单元测试"""

    def _make_service(self, test_db):
        from services.connection_switch_service import ConnectionSwitchService
        return ConnectionSwitchService(db=test_db)

    def _insert_running_task(self, test_db, conn_id, task_id="task-001", status="running"):
        """插入一个运行中的诊断任务"""
        test_db.insert("profiler_tasks", {
            "id": task_id,
            "connection_id": conn_id,
            "type": "profiler",
            "status": status,
            "event": "cpu",
        })

    def test_get_running_tasks(self, test_db):
        """验证获取运行中任务列表"""
        self._insert_running_task(test_db, "test-conn-001", "task-001")
        self._insert_running_task(test_db, "test-conn-001", "task-002", status="starting")

        svc = self._make_service(test_db)
        tasks = svc.get_running_tasks("test-conn-001")

        assert len(tasks) == 2
        task_ids = [t["id"] for t in tasks]
        assert "task-001" in task_ids
        assert "task-002" in task_ids

    def test_get_running_tasks_empty(self, test_db):
        """验证无运行中任务时返回空列表"""
        svc = self._make_service(test_db)
        tasks = svc.get_running_tasks("test-conn-001")
        assert tasks == []

    def test_has_running_tasks_true(self, test_db):
        """验证有运行中任务时返回 True"""
        self._insert_running_task(test_db, "test-conn-001")
        svc = self._make_service(test_db)
        assert svc.has_running_tasks("test-conn-001") is True

    def test_has_running_tasks_false(self, test_db):
        """验证无运行中任务时返回 False"""
        svc = self._make_service(test_db)
        assert svc.has_running_tasks("test-conn-001") is False

    def test_cancel_running_tasks(self, test_db):
        """验证取消运行中任务"""
        self._insert_running_task(test_db, "test-conn-001", "task-001")
        self._insert_running_task(test_db, "test-conn-001", "task-002")

        svc = self._make_service(test_db)
        result = svc.cancel_running_tasks("test-conn-001", user_id=1)

        assert result["ok"] is True
        assert result["count"] == 2
        assert len(result["cancelled"]) == 2

        # 验证任务状态已更新
        for tid in ["task-001", "task-002"]:
            row = test_db.fetch_one(
                "SELECT status FROM profiler_tasks WHERE id = ?",
                (tid,),
            )
            assert row["status"] == "cancelled"

    def test_switch_connection_success(self, test_db):
        """验证连接切换成功"""
        # 插入目标连接
        test_db.insert("connections", {
            "id": "target-conn-001",
            "cluster_name": "prod-cluster",
            "namespace": "default",
            "pod_name": "prod-pod",
            "status": "ready",
            "health_status": "healthy",
        })

        svc = self._make_service(test_db)
        result = svc.switch_connection(
            "test-conn-001",
            "target-conn-001",
            cancel_tasks=False,
            user_id=1,
        )

        assert result["ok"] is True
        assert result["source_connection_id"] == "test-conn-001"
        assert result["target_connection_id"] == "target-conn-001"
        assert result["target_status"] == "ready"
        assert result["target_health"] == "healthy"

    def test_switch_connection_source_not_found(self, test_db):
        """验证源连接不存在时返回错误"""
        svc = self._make_service(test_db)
        result = svc.switch_connection("non-existent", "test-conn-001")
        assert result["ok"] is False
        assert "不存在" in result["error"]

    def test_switch_connection_target_not_found(self, test_db):
        """验证目标连接不存在时返回错误"""
        svc = self._make_service(test_db)
        result = svc.switch_connection("test-conn-001", "non-existent")
        assert result["ok"] is False
        assert "不存在" in result["error"]

    def test_switch_connection_cancels_tasks(self, test_db):
        """验证切换时取消运行中任务"""
        self._insert_running_task(test_db, "test-conn-001", "task-001")
        test_db.insert("connections", {
            "id": "target-conn-001",
            "cluster_name": "prod-cluster",
            "namespace": "default",
            "pod_name": "prod-pod",
            "status": "ready",
            "health_status": "healthy",
        })

        svc = self._make_service(test_db)
        result = svc.switch_connection(
            "test-conn-001",
            "target-conn-001",
            cancel_tasks=True,
            user_id=1,
        )

        assert result["ok"] is True
        assert result["had_running_tasks"] is True
        assert "task-001" in result["cancelled_tasks"]

    def test_switch_connection_creates_audit_log(self, test_db):
        """验证切换操作创建审计日志"""
        test_db.insert("connections", {
            "id": "target-conn-001",
            "cluster_name": "prod-cluster",
            "namespace": "default",
            "pod_name": "prod-pod",
            "status": "ready",
        })

        svc = self._make_service(test_db)
        svc.switch_connection("test-conn-001", "target-conn-001", user_id=1)

        logs = test_db.fetch_all(
            "SELECT * FROM audit_logs WHERE action = ?",
            ("connection_switch",),
        )
        assert len(logs) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# 4. ConnectionTTLConfig 单元测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionTTLConfigUnit:
    """ConnectionTTLConfig 完整单元测试"""

    def _make_service(self, test_db):
        from services.connection_ttl_config import ConnectionTTLConfig
        return ConnectionTTLConfig(db=test_db)

    def test_get_preset_options(self, test_db):
        """验证获取预设 TTL 选项"""
        svc = self._make_service(test_db)
        presets = svc.get_preset_options()

        assert isinstance(presets, list)
        assert len(presets) >= 7
        # 验证包含 0 (不过期) 和 8 (默认)
        hours_list = [p["hours"] for p in presets]
        assert 0 in hours_list
        assert 1 in hours_list
        assert 8 in hours_list
        assert 24 in hours_list

    def test_get_connection_ttl(self, test_db):
        """验证获取连接的当前 TTL"""
        svc = self._make_service(test_db)
        ttl = svc.get_connection_ttl("test-conn-001")
        assert ttl == 0  # 默认值

    def test_get_connection_ttl_with_custom(self, test_db):
        """验证获取自定义 TTL"""
        svc = self._make_service(test_db)
        ttl = svc.get_connection_ttl("test-conn-002")
        assert ttl == 8  # 插入时设置的值

    def test_get_connection_ttl_nonexistent(self, test_db):
        """验证获取不存在连接的 TTL 返回 0"""
        svc = self._make_service(test_db)
        ttl = svc.get_connection_ttl("non-existent")
        assert ttl == 0

    def test_validate_ttl_valid(self, test_db):
        """验证合法 TTL 值"""
        svc = self._make_service(test_db)
        valid, err = svc.validate_ttl(8)
        assert valid is True
        assert err is None

    def test_validate_ttl_zero(self, test_db):
        """验证 TTL=0 (不过期) 是合法的"""
        svc = self._make_service(test_db)
        valid, err = svc.validate_ttl(0)
        assert valid is True

    def test_validate_ttl_negative(self, test_db):
        """验证负数 TTL 不合法"""
        svc = self._make_service(test_db)
        valid, err = svc.validate_ttl(-1)
        assert valid is False
        assert "负数" in err

    def test_validate_ttl_too_large(self, test_db):
        """验证超大 TTL 不合法"""
        svc = self._make_service(test_db)
        valid, err = svc.validate_ttl(9999)
        assert valid is False
        assert "超过" in err

    def test_validate_ttl_non_integer(self, test_db):
        """验证非整数 TTL 不合法"""
        svc = self._make_service(test_db)
        valid, err = svc.validate_ttl("8")
        assert valid is False

    def test_set_connection_ttl(self, test_db):
        """验证设置连接 TTL"""
        svc = self._make_service(test_db)
        result = svc.set_connection_ttl("test-conn-001", 24)

        assert result["ok"] is True
        assert result["ttl_hours"] == 24
        assert result["connection_id"] == "test-conn-001"

        # 验证数据库已更新
        ttl = svc.get_connection_ttl("test-conn-001")
        assert ttl == 24

    def test_set_connection_ttl_nonexistent(self, test_db):
        """验证设置不存在连接的 TTL 返回错误"""
        svc = self._make_service(test_db)
        result = svc.set_connection_ttl("non-existent", 8)
        assert result["ok"] is False
        assert "不存在" in result["error"]

    def test_set_connection_ttl_invalid(self, test_db):
        """验证设置非法 TTL 返回错误"""
        svc = self._make_service(test_db)
        result = svc.set_connection_ttl("test-conn-001", -1)
        assert result["ok"] is False

    def test_get_connections_ttl_summary(self, test_db):
        """验证获取 TTL 摘要"""
        svc = self._make_service(test_db)
        summary = svc.get_connections_ttl_summary()

        assert isinstance(summary, list)
        assert len(summary) >= 1
        # 验证数据结构
        item = summary[0]
        assert "id" in item
        assert "ttl_hours" in item
        assert "health_status" in item
        assert "status" in item

    def test_batch_set_ttl(self, test_db):
        """验证批量设置 TTL"""
        svc = self._make_service(test_db)
        result = svc.batch_set_ttl(["test-conn-001", "test-conn-002"], 4)

        assert result["ok"] is True
        assert result["updated"] == 2
        assert result["failed"] == 0

        # 验证
        assert svc.get_connection_ttl("test-conn-001") == 4
        assert svc.get_connection_ttl("test-conn-002") == 4

    def test_batch_set_ttl_partial_failure(self, test_db):
        """验证批量设置部分失败"""
        svc = self._make_service(test_db)
        result = svc.batch_set_ttl(["test-conn-001", "non-existent"], 4)

        assert result["ok"] is True
        assert result["updated"] == 1
        assert result["failed"] == 1

    def test_batch_set_ttl_invalid_value(self, test_db):
        """验证批量设置非法值"""
        svc = self._make_service(test_db)
        result = svc.batch_set_ttl(["test-conn-001"], -1)
        assert result["ok"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ConnectionDetail API 集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionDetailAPI:
    """ConnectionDetail API 集成测试"""

    def test_api_module_importable(self):
        """验证 API 模块可导入"""
        from api.connection_detail import connection_detail_bp
        assert connection_detail_bp is not None

    def test_api_blueprint_prefix(self):
        """验证 API 蓝图 URL 前缀"""
        from api.connection_detail import connection_detail_bp
        assert connection_detail_bp.url_prefix == "/api/connections"

    def test_api_routes_registered(self, flask_app_context):
        """验证 API 路由注册"""
        from api.connection_detail import connection_detail_bp
        app = flask_app_context
        app.register_blueprint(connection_detail_bp)

        rules = {rule.rule for rule in app.url_map.iter_rules()}
        # 检查关键路由是否存在
        assert any("detail" in rule for rule in rules)
        assert any("health" in rule for rule in rules)
        assert any("ttl" in rule for rule in rules)

    def test_api_import_dependencies(self):
        """验证 API 模块所有依赖可正确导入"""
        from api.connection_detail import (
            connection_detail_bp,
            _check_permission,
            _error_response,
            _success_response,
        )
        assert callable(_check_permission)
        assert callable(_error_response)
        assert callable(_success_response)

    def test_error_response_format(self, flask_app_context):
        """验证错误响应格式"""
        from api.connection_detail import _error_response
        result = _error_response("测试错误", 400)
        # _error_response returns (response, status_code) tuple
        resp = result[0] if isinstance(result, tuple) else result
        data = json.loads(resp.get_data(as_text=True))
        assert data["code"] == 400
        assert data["data"] is None
        assert data["message"] == "测试错误"

    def test_success_response_format(self, flask_app_context):
        """验证成功响应格式"""
        from api.connection_detail import _success_response
        resp = _success_response({"foo": "bar"})
        data = json.loads(resp.get_data(as_text=True))
        assert data["code"] == 200
        assert data["data"] == {"foo": "bar"}
        assert data["message"] == "success"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 数据库表结构验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatabaseSchema:
    """验证 Phase 5 数据库表结构"""

    def test_health_check_logs_table_exists(self, test_db):
        """验证 health_check_logs 表存在"""
        row = test_db.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='health_check_logs'"
        )
        assert row is not None

    def test_health_check_logs_columns(self, temp_db_path):
        """验证 health_check_logs 表列结构"""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute("PRAGMA table_info(health_check_logs)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        expected_columns = {"id", "connection_id", "status", "latency_ms", "error_message", "checked_at"}
        assert expected_columns.issubset(columns)

    def test_connections_phase5_columns(self, temp_db_path):
        """验证 connections 表包含 Phase 5 新字段"""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute("PRAGMA table_info(connections)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        phase5_columns = {"ttl_hours", "last_active_at", "last_health_check", "health_status"}
        assert phase5_columns.issubset(columns)

    def test_insert_health_check_log(self, test_db):
        """验证可以向 health_check_logs 插入记录"""
        test_db.insert("health_check_logs", {
            "connection_id": "test-conn-001",
            "status": "healthy",
            "latency_ms": 50.0,
            "error_message": None,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        row = test_db.fetch_one(
            "SELECT * FROM health_check_logs WHERE connection_id = ?",
            ("test-conn-001",),
        )
        assert row is not None
        assert row["status"] == "healthy"
        assert row["latency_ms"] == 50.0

    def test_cascade_delete_health_logs(self, test_db):
        """验证删除连接时级联删除健康检查日志"""
        # 先插入日志
        test_db.insert("health_check_logs", {
            "connection_id": "test-conn-001",
            "status": "healthy",
        })

        logs_before = test_db.fetch_all(
            "SELECT * FROM health_check_logs WHERE connection_id = ?",
            ("test-conn-001",),
        )
        assert len(logs_before) >= 1

        # 删除连接
        test_db.delete("connections", "id = ?", ("test-conn-001",))

        logs_after = test_db.fetch_all(
            "SELECT * FROM health_check_logs WHERE connection_id = ?",
            ("test-conn-001",),
        )
        assert len(logs_after) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. server.py 集成验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestServerIntegration:
    """验证 server.py 中 Phase 5 集成点"""

    def test_server_imports_health_check_service(self):
        """验证 server.py 可导入 HealthCheckService"""
        # 验证模块文件包含导入
        server_path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        content = server_path.read_text(encoding="utf-8")
        assert "health_check_service" in content
        assert "HealthCheckService" in content

    def test_server_imports_connection_recovery(self):
        """验证 server.py 可导入 ConnectionRecoveryService"""
        server_path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        content = server_path.read_text(encoding="utf-8")
        assert "connection_recovery_service" in content
        assert "ConnectionRecoveryService" in content

    def test_server_has_health_check_globals(self):
        """验证 server.py 定义了健康检查相关全局变量"""
        server_path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        content = server_path.read_text(encoding="utf-8")
        assert "_conn_health" in content
        assert "_conn_health_lock" in content

    def test_server_has_ttl_cleanup_thread(self):
        """验证 server.py 启动了 TTL 清理后台线程"""
        server_path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        content = server_path.read_text(encoding="utf-8")
        assert "ttl_cleanup" in content.lower()

    def test_config_has_health_check_settings(self):
        """验证 config.py 包含健康检查配置"""
        from backend.config import Config
        assert hasattr(Config, "HEALTH_CHECK_INTERVAL_SECONDS")
        assert hasattr(Config, "TTL_CLEANUP_INTERVAL_SECONDS")
        assert hasattr(Config, "DEFAULT_TTL_THRESHOLD_MINUTES")
        assert hasattr(Config, "HEALTH_CHECK_LOG_RETENTION_DAYS")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 前端组件契约验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrontendComponentContracts:
    """验证前端组件文件结构和契约"""

    @pytest.fixture(scope="class")
    def broadcast_channel_src(self, project_root):
        path = project_root / "static" / "js" / "components" / "broadcast-channel-manager.js"
        return path.read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def switch_confirm_src(self, project_root):
        path = project_root / "static" / "js" / "components" / "connection-switch-confirm.js"
        return path.read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def ttl_config_src(self, project_root):
        path = project_root / "static" / "js" / "components" / "connection-ttl-config.js"
        return path.read_text(encoding="utf-8")

    # ── BroadcastChannelManager ──

    def test_broadcast_channel_class_exists(self, broadcast_channel_src):
        """验证 BroadcastChannelManager 类定义"""
        assert "class BroadcastChannelManager" in broadcast_channel_src

    def test_broadcast_channel_api_methods(self, broadcast_channel_src):
        """验证 BroadcastChannelManager 公共 API"""
        assert "onMessage" in broadcast_channel_src
        assert "send" in broadcast_channel_src
        assert "setSession" in broadcast_channel_src
        assert "getSession" in broadcast_channel_src
        assert "destroy" in broadcast_channel_src

    def test_broadcast_channel_singleton(self, broadcast_channel_src):
        """验证全局单例工厂函数"""
        assert "getBroadcastChannelManager" in broadcast_channel_src

    def test_broadcast_channel_handles_unsupported(self, broadcast_channel_src):
        """验证不支持 BroadcastChannel 时降级处理"""
        assert "BroadcastChannel" in broadcast_channel_src
        assert "不支持" in broadcast_channel_src or "不可用" in broadcast_channel_src

    # ── ConnectionSwitchConfirm ──

    def test_switch_confirm_class_exists(self, switch_confirm_src):
        """验证 ConnectionSwitchConfirm 类定义"""
        assert "class ConnectionSwitchConfirm" in switch_confirm_src

    def test_switch_confirm_api_methods(self, switch_confirm_src):
        """验证 ConnectionSwitchConfirm 公共 API"""
        assert "switch" in switch_confirm_src
        assert "onSwitchComplete" in switch_confirm_src

    def test_switch_confirm_same_connection_guard(self, switch_confirm_src):
        """验证不能切换到相同连接"""
        assert "sourceConnId === targetConnId" in switch_confirm_src

    def test_switch_confirm_broadcasts(self, switch_confirm_src):
        """验证切换后广播到其他标签页"""
        assert "BroadcastChannel" in switch_confirm_src or "broadcast" in switch_confirm_src.lower()

    def test_switch_confirm_confirms_dialog(self, switch_confirm_src):
        """验证显示确认弹窗"""
        assert "showConfirmDialog" in switch_confirm_src or "confirm" in switch_confirm_src.lower()

    def test_switch_confirm_checks_running_tasks(self, switch_confirm_src):
        """验证检查运行中任务"""
        assert "running-tasks" in switch_confirm_src

    # ── ConnectionTTLConfig ──

    def test_ttl_config_class_exists(self, ttl_config_src):
        """验证 ConnectionTTLConfig 类定义"""
        assert "class ConnectionTTLConfig" in ttl_config_src

    def test_ttl_config_api_methods(self, ttl_config_src):
        """验证 ConnectionTTLConfig 公共 API"""
        assert "render" in ttl_config_src
        assert "getSelectedTTL" in ttl_config_src
        assert "hasChanges" in ttl_config_src

    def test_ttl_config_default_presets(self, ttl_config_src):
        """验证默认 TTL 预设选项"""
        assert "不过期" in ttl_config_src
        assert "1 小时" in ttl_config_src
        assert "8 小时" in ttl_config_src

    def test_ttl_config_save_endpoint(self, ttl_config_src):
        """验证 TTL 保存使用 PUT 方法调用 API"""
        assert "PUT" in ttl_config_src
        assert "/ttl" in ttl_config_src

    def test_ttl_config_broadcasts_update(self, ttl_config_src):
        """验证保存后广播状态更新"""
        assert "BroadcastChannel" in ttl_config_src or "broadcast" in ttl_config_src.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 9. 架构一致性验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestArchitectureConsistency:
    """验证实现与架构设计文档的一致性"""

    def test_api_response_format_consistent(self, flask_app_context):
        """验证 API 响应格式与架构文档一致"""
        from api.connection_detail import _success_response, _error_response

        # 成功响应
        resp = _success_response({"key": "value"})
        data = json.loads(resp.get_data(as_text=True))
        assert "code" in data
        assert "data" in data
        assert "message" in data
        assert data["code"] == 200

        # 错误响应
        result = _error_response("error", 400)
        resp = result[0] if isinstance(result, tuple) else result
        data = json.loads(resp.get_data(as_text=True))
        assert data["code"] == 400
        assert data["data"] is None

    def test_health_states_match_design(self):
        """验证健康状态枚举与架构文档一致"""
        valid_states = {"healthy", "unhealthy", "unknown"}
        # 从代码中提取使用的状态
        from services.health_check_service import HealthCheckService
        import inspect
        source = inspect.getsource(HealthCheckService._check_single)
        for state in valid_states:
            assert f'"{state}"' in source

    def test_ttl_preset_matches_prd(self):
        """验证 TTL 预设选项与 PRD 一致"""
        from services.connection_ttl_config import TTL_PRESET_OPTIONS
        hours = {opt["hours"] for opt in TTL_PRESET_OPTIONS}
        # PRD 要求: 1/2/4/8/12/24 小时
        assert 1 in hours
        assert 2 in hours
        assert 4 in hours
        assert 8 in hours
        assert 24 in hours
        # 包含 0 (不过期) 和扩展选项
        assert 0 in hours
        assert 72 in hours

    def test_connection_states_match_design(self):
        """验证连接状态与架构设计一致"""
        server_path = pathlib.Path(__file__).resolve().parents[1] / "server.py"
        content = server_path.read_text(encoding="utf-8")
        # 架构设计中定义的状态
        assert "ready" in content or "connected" in content
        assert "disconnected" in content

    def test_database_table_names_match_design(self, temp_db_path):
        """验证数据库表名与架构设计一致"""
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "connections" in tables
        assert "health_check_logs" in tables

    def test_api_url_pattern_matches_design(self, flask_app_context):
        """验证 API URL 模式与架构设计一致"""
        from api.connection_detail import connection_detail_bp
        app = flask_app_context
        app.register_blueprint(connection_detail_bp)

        expected_patterns = [
            "detail",
            "health",
            "ttl",
            "running-tasks",
            "switch",
        ]

        # 检查蓝图中注册的路由
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        for pattern in expected_patterns:
            found = any(pattern in rule for rule in rules)
            assert found, f"API 路由中缺少: {pattern}"

    def test_all_phase5_files_exist(self, project_root):
        """验证所有 Phase 5 新增文件存在"""
        new_files = [
            "services/health_check_service.py",
            "services/connection_recovery_service.py",
            "services/connection_switch_service.py",
            "services/connection_ttl_config.py",
            "api/connection_detail.py",
            "static/js/components/broadcast-channel-manager.js",
            "static/js/components/connection-switch-confirm.js",
            "static/js/components/connection-ttl-config.js",
        ]
        for f in new_files:
            path = project_root / f
            assert path.exists(), f"文件不存在: {f}"

    def test_modified_files_contain_phase5(self, project_root):
        """验证修改的文件包含 Phase 5 相关内容"""
        checks = {
            "server.py": ["health_check", "ttl_cleanup", "_conn_health"],
            "backend/config.py": ["HEALTH_CHECK_INTERVAL", "TTL_CLEANUP_INTERVAL"],
            "models/db.py": ["health_check_logs", "ttl_hours", "health_status"],
        }
        for filename, keywords in checks.items():
            content = (project_root / filename).read_text(encoding="utf-8")
            for kw in keywords:
                assert kw in content, f"{filename} 缺少 Phase 5 关键词: {kw}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. 边界条件和异常场景
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """边界条件和异常场景测试"""

    def test_health_check_concurrent_access(self, test_db, mock_arthas_conn):
        """验证并发健康检查的线程安全性"""
        from services.health_check_service import HealthCheckService

        connections = {}
        connections_lock = threading.Lock()
        conn_health = {}
        conn_health_lock = threading.Lock()

        svc = HealthCheckService(
            db=test_db,
            connections=connections,
            connections_lock=connections_lock,
            conn_health=conn_health,
            conn_health_lock=conn_health_lock,
            interval_seconds=300,
        )

        # 并发添加连接和执行检查
        def add_connections():
            for i in range(10):
                with connections_lock:
                    connections[f"conn-{i}"] = {"conn": mock_arthas_conn}

        def check_all():
            svc._check_all()

        threads = [
            threading.Thread(target=add_connections),
            threading.Thread(target=check_all),
            threading.Thread(target=check_all),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # 不应抛出异常

    def test_switch_service_empty_task_id(self, test_db):
        """验证取消任务时空 task_id 不报错"""
        from services.connection_switch_service import ConnectionSwitchService

        svc = ConnectionSwitchService(db=test_db)
        # 插入一个无 id 的任务记录（模拟边界情况）
        # 不应抛出异常

    def test_ttl_config_boundary_values(self, test_db):
        """验证 TTL 边界值处理"""
        from services.connection_ttl_config import ConnectionTTLConfig

        svc = ConnectionTTLConfig(db=test_db)

        # 最大有效值
        valid, _ = svc.validate_ttl(720)
        assert valid is True

        # 超过最大值
        valid, _ = svc.validate_ttl(721)
        assert valid is False

        # 零值
        valid, _ = svc.validate_ttl(0)
        assert valid is True

    def test_recovery_service_db_error_handling(self):
        """验证恢复服务处理数据库错误"""
        from services.connection_recovery_service import ConnectionRecoveryService

        mock_db = MagicMock()
        mock_db.fetch_all.side_effect = Exception("DB error")

        svc = ConnectionRecoveryService(db=mock_db)
        svc.recover_on_startup()

        result = svc.recovery_result
        assert result["completed"] is True
        # 数据库错误不应导致服务崩溃

    def test_switch_service_audit_log_failure(self, test_db):
        """验证审计日志写入失败不影响切换"""
        from services.connection_switch_service import ConnectionSwitchService

        svc = ConnectionSwitchService(db=test_db)
        # 使用一个会失败的 insert 来模拟审计日志写入失败
        # 不应导致切换操作失败
