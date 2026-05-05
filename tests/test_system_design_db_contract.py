#!/usr/bin/env python3
"""数据库合同测试 — 验证 P0-1 增量字段、索引、WAL 配置。"""
import os
import sqlite3
import tempfile
import pytest

from models.db import Database


@pytest.fixture
def fresh_db():
    """提供一个使用临时数据库文件的 Database 实例，测试后自动清理。"""
    from backend.config import Config  # 延迟导入避免循环依赖
    tmpdir = tempfile.mkdtemp()
    db_file = os.path.join(tmpdir, "test.db")
    original_db_file = Config.DB_FILE
    Config.DB_FILE = db_file
    Database._instance = None
    db = Database()
    db.initialize()
    yield db
    Database._instance = None
    Config.DB_FILE = original_db_file


# ═══════════════════════════════════════════════════════════════════════════
# 测试：Connection PRAGMA 设置
# ═══════════════════════════════════════════════════════════════════════════
class TestConnectionPragmas:
    def test_wal_mode_enabled(self, fresh_db):
        with fresh_db.connection() as conn:
            result = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert result.lower() == "wal", f"Expected WAL, got {result}"

    def test_busy_timeout_is_5000(self, fresh_db):
        with fresh_db.connection() as conn:
            result = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert result == 5000, f"Expected 5000, got {result}"

    def test_foreign_keys_is_on(self, fresh_db):
        with fresh_db.connection() as conn:
            result = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert result == 1, f"Expected 1 (ON), got {result}"


# ═══════════════════════════════════════════════════════════════════════════
# 测试：connections 表增量字段
# ═══════════════════════════════════════════════════════════════════════════
class TestConnectionsIncrementalFields:
    EXPECTED_COLUMNS = [
        "id", "cluster_name", "namespace", "pod_name", "level",
        "local_port", "user_id", "updated_at",
        "container_name", "java_pid", "arthas_version",
        "last_ping_at", "owner_user_id", "status",
    ]

    def test_all_columns_exist(self, fresh_db):
        with fresh_db.connection() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(connections)").fetchall()}
        for col in self.EXPECTED_COLUMNS:
            assert col in cols, f"Missing column: connections.{col}"

    def test_status_default_value(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO connections (id, cluster_name, namespace, pod_name) VALUES (?, ?, ?, ?)",
            ("test-conn", "c1", "ns1", "pod1"),
        )
        row = fresh_db.fetch_one("SELECT status FROM connections WHERE id = ?", ("test-conn",))
        assert row["status"] == "disconnected"

    def test_insert_with_all_p0_fields(self, fresh_db):
        fresh_db.execute(
            """INSERT INTO connections
               (id, cluster_name, namespace, pod_name, container_name, java_pid,
                arthas_version, last_ping_at, owner_user_id, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("c2", "c1", "ns1", "pod1", "main", 1234, "4.0.2",
             "2026-05-02T10:00:00", 1, "ready"),
        )
        row = fresh_db.fetch_one("SELECT * FROM connections WHERE id = ?", ("c2",))
        assert row is not None
        assert row["container_name"] == "main"
        assert row["java_pid"] == 1234
        assert row["arthas_version"] == "4.0.2"
        assert row["owner_user_id"] == 1
        assert row["status"] == "ready"


# ═══════════════════════════════════════════════════════════════════════════
# 测试：arthas_commands 表增量字段
# ═══════════════════════════════════════════════════════════════════════════
class TestArthasCommandsIncrementalFields:
    EXPECTED_COLUMNS = [
        "id", "connection_id", "user_id", "command", "output", "error", "timestamp",
        "template_type", "risk_level", "duration_ms", "exit_status", "masked_output",
    ]

    def test_all_columns_exist(self, fresh_db):
        with fresh_db.connection() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(arthas_commands)").fetchall()}
        for col in self.EXPECTED_COLUMNS:
            assert col in cols, f"Missing column: arthas_commands.{col}"

    def test_risk_level_default_value(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO connections (id, cluster_name, namespace, pod_name) VALUES (?, ?, ?, ?)",
            ("c3", "c1", "ns1", "pod1"),
        )
        fresh_db.execute(
            "INSERT INTO arthas_commands (connection_id, command) VALUES (?, ?)",
            ("c3", "help"),
        )
        row = fresh_db.fetch_one(
            "SELECT risk_level FROM arthas_commands WHERE connection_id = ?", ("c3",)
        )
        assert row["risk_level"] == "low"

    def test_insert_with_p0_fields(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO connections (id, cluster_name, namespace, pod_name) VALUES (?, ?, ?, ?)",
            ("c4", "c1", "ns1", "pod1"),
        )
        fresh_db.execute(
            """INSERT INTO arthas_commands
               (connection_id, user_id, command, template_type, risk_level,
                duration_ms, exit_status, masked_output)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("c4", 1, "trace com.example.Service hello", "trace", "low", 150, "SUCCEEDED", "masked..."),
        )
        row = fresh_db.fetch_one("SELECT * FROM arthas_commands WHERE connection_id = ?", ("c4",))
        assert row is not None


# ═══════════════════════════════════════════════════════════════════════════
# 测试：profiler_tasks 表增量字段
# ═══════════════════════════════════════════════════════════════════════════
class TestProfilerTasksIncrementalFields:
    EXPECTED_COLUMNS = [
        "id", "connection_id", "user_id", "type", "status", "cluster_name",
        "namespace", "pod_name", "mode", "event", "duration", "format",
        "output_path", "progress", "message", "created_at", "updated_at",
        "artifact_size", "artifact_sha256", "max_duration", "cancel_reason",
    ]

    def test_all_columns_exist(self, fresh_db):
        with fresh_db.connection() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(profiler_tasks)").fetchall()}
        for col in self.EXPECTED_COLUMNS:
            assert col in cols, f"Missing column: profiler_tasks.{col}"

    def test_insert_with_p0_fields(self, fresh_db):
        fresh_db.execute(
            "INSERT INTO connections (id, cluster_name, namespace, pod_name) VALUES (?, ?, ?, ?)",
            ("c5", "c1", "ns1", "pod1"),
        )
        fresh_db.execute(
            """INSERT INTO profiler_tasks
               (id, connection_id, user_id, type, status, artifact_size,
                artifact_sha256, max_duration, cancel_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("t1", "c5", 1, "cpu", "success", 1024, "abc123", 300, None),
        )
        row = fresh_db.fetch_one("SELECT * FROM profiler_tasks WHERE id = ?", ("t1",))
        assert row is not None
        assert row["artifact_size"] == 1024
        assert row["artifact_sha256"] == "abc123"
        assert row["max_duration"] == 300
        assert row["cancel_reason"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 测试：索引存在性
# ═══════════════════════════════════════════════════════════════════════════
class TestIndexes:
    EXPECTED_INDEXES = [
        "idx_connections_user",
        "idx_connections_status",
        "idx_arthas_commands_user_cluster_created",
        "idx_profiler_tasks_user_status_created",
    ]

    def test_all_indexes_exist(self, fresh_db):
        with fresh_db.connection() as conn:
            indexes = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()}
        for idx in self.EXPECTED_INDEXES:
            assert idx in indexes, f"Missing index: {idx}"


# ═══════════════════════════════════════════════════════════════════════════
# 测试：Migration 兼容性（initialize 幂等性）
# ═══════════════════════════════════════════════════════════════════════════
class TestMigrationCompatibility:
    def test_initialize_is_idempotent(self, fresh_db):
        """initialize() 可以安全地多次调用，不会抛异常。"""
        fresh_db.initialize()
        fresh_db.initialize()
