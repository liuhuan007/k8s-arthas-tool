#!/usr/bin/env python3
"""审计覆盖合同测试 — 验证 AuditService 新增便利方法均正确写入 audit_logs。"""
import os
import tempfile

import pytest

from backend.config import Config  # noqa: F401 — must import first to avoid circular imports
from models.db import Database
from services.audit_service import AuditService


@pytest.fixture
def fresh_db():
    """Provide a Database instance backed by a temporary file."""
    tmpdir = tempfile.mkdtemp()
    db_file = os.path.join(tmpdir, "test.db")
    original_db_file = Config.DB_FILE
    Config.DB_FILE = db_file
    Database._instance = None
    db = Database()
    db.initialize()
    # Patch singleton references so AuditService writes to the temp DB
    import models
    import services.audit_service as _audit_svc
    original_models_db = models.db
    original_audit_db = _audit_svc.db
    models.db = db
    _audit_svc.db = db
    yield db
    Database._instance = None
    Config.DB_FILE = original_db_file
    models.db = original_models_db
    _audit_svc.db = original_audit_db


# ═══════════════════════════════════════════════════════════════════════════
# 测试：log_event 通用方法
# ═══════════════════════════════════════════════════════════════════════════

class TestLogEvent:
    def test_log_event_inserts_record(self, fresh_db):
        AuditService.log_event(1, 'custom_action', 'resource', 'res-001', 'detail text')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('custom_action',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'resource'
        assert rows[0]['resource_id'] == 'res-001'
        assert rows[0]['details'] == 'detail text'


# ═══════════════════════════════════════════════════════════════════════════
# 测试：诊断操作便利方法
# ═══════════════════════════════════════════════════════════════════════════

class TestDiagnosticConvenienceMethods:
    def test_log_arthas_connect(self, fresh_db):
        AuditService.log_arthas_connect(1, 'conn-001', 'c1', 'ns1', 'pod-1')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('arthas_connect',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'diagnostic'
        assert rows[0]['resource_id'] == 'conn-001'
        assert 'c1/ns1/pod-1' in rows[0]['details']

    def test_log_arthas_disconnect(self, fresh_db):
        AuditService.log_arthas_disconnect(1, 'conn-002')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('arthas_disconnect',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'diagnostic'
        assert rows[0]['resource_id'] == 'conn-002'

    def test_log_arthas_exec(self, fresh_db):
        AuditService.log_arthas_exec(1, 'conn-003', 'thread -n 5')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('arthas_exec',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'diagnostic'
        assert rows[0]['resource_id'] == 'conn-003'
        assert 'thread -n 5' in rows[0]['details']

    def test_log_profiler_start(self, fresh_db):
        AuditService.log_profiler_start(1, 'task-004', 'cpu')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('profiler_start',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'diagnostic'
        assert rows[0]['resource_id'] == 'task-004'
        assert 'cpu' in rows[0]['details']

    def test_log_profiler_cancel(self, fresh_db):
        AuditService.log_profiler_cancel(1, 'task-005', 'user request')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('profiler_cancel',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'diagnostic'
        assert rows[0]['resource_id'] == 'task-005'
        assert 'user request' in rows[0]['details']

    def test_log_profiler_download(self, fresh_db):
        AuditService.log_profiler_download(1, 'task-006', 'result.html')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('profiler_download',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'diagnostic'
        assert rows[0]['resource_id'] == 'task-006'
        assert 'result.html' in rows[0]['details']

    def test_log_gc_download(self, fresh_db):
        AuditService.log_gc_download(1, 'c1', 'ns1', 'pod-1', 'gc.log')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('gc_download',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'gc_log'
        assert rows[0]['resource_id'] == 'gc.log'
        assert 'c1/ns1/pod-1' in rows[0]['details']

    def test_log_pod_file_read(self, fresh_db):
        AuditService.log_pod_file_read(1, 'conn-008', '/tmp/test.log')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('pod_file_read',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'diagnostic'
        assert rows[0]['resource_id'] == 'conn-008'
        assert '/tmp/test.log' in rows[0]['details']

    def test_log_pod_file_download(self, fresh_db):
        AuditService.log_pod_file_download(1, 'conn-009', '/tmp/heapdump.hprof')
        rows = fresh_db.fetch_all("SELECT * FROM audit_logs WHERE action = ?", ('pod_file_download',))
        assert len(rows) == 1
        assert rows[0]['user_id'] == 1
        assert rows[0]['resource_type'] == 'diagnostic'
        assert rows[0]['resource_id'] == 'conn-009'
        assert '/tmp/heapdump.hprof' in rows[0]['details']


# ═══════════════════════════════════════════════════════════════════════════
# 测试：查询方法返回插入记录
# ═══════════════════════════════════════════════════════════════════════════

class TestQueryMethods:
    def test_query_returns_inserted_records(self, fresh_db):
        AuditService.log_arthas_exec(1, 'conn-010', 'dashboard')
        AuditService.log_arthas_exec(1, 'conn-010', 'thread')
        AuditService.log_profiler_start(1, 'task-010', 'cpu')

        rows = AuditService.query(filters={'user_id': 1}, limit=10)
        assert len(rows) == 3

        arthas_rows = AuditService.query(filters={'action': 'arthas_exec'}, limit=10)
        assert len(arthas_rows) == 2

    def test_count_returns_correct_number(self, fresh_db):
        AuditService.log_arthas_exec(1, 'conn-011', 'dashboard')
        AuditService.log_arthas_exec(1, 'conn-011', 'thread')

        assert AuditService.count(filters={'user_id': 1}) == 2
        assert AuditService.count(filters={'action': 'arthas_exec'}) == 2
        assert AuditService.count(filters={'action': 'profiler_start'}) == 0

    def test_get_actions_returns_distinct_actions(self, fresh_db):
        AuditService.log_arthas_connect(1, 'conn-012', 'c1', 'ns1', 'pod-1')
        AuditService.log_arthas_disconnect(1, 'conn-012')

        actions = AuditService.get_actions()
        assert 'arthas_connect' in actions
        assert 'arthas_disconnect' in actions

    def test_get_resource_types_returns_distinct_types(self, fresh_db):
        AuditService.log_arthas_exec(1, 'conn-013', 'help')
        AuditService.log_gc_download(1, 'c1', 'ns1', 'pod-1', 'gc.log')

        types = AuditService.get_resource_types()
        assert 'diagnostic' in types
        assert 'gc_log' in types
