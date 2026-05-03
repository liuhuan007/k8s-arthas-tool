#!/usr/bin/env python3
"""ConnectionStateManager tests — validates state transitions, TTL cleanup, and persistence."""
import os
import sqlite3
import tempfile
import time
import threading
from datetime import datetime, timedelta, timezone

import pytest

from backend.config import Config
from backend.core.connection_state import (
    ConnectionState,
    ConnectionStateManager,
    STABLE_STATES,
)
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


@pytest.fixture
def manager(fresh_db):
    """Provide a ConnectionStateManager with a fresh DB."""
    return ConnectionStateManager(fresh_db)


@pytest.fixture
def sample_connection(fresh_db, manager):
    """Insert a sample connection row and initialize its state to POD_SELECTED."""
    conn_id = "test-conn-001"
    fresh_db.execute(
        "INSERT INTO connections (id, cluster_name, namespace, pod_name) VALUES (?, ?, ?, ?)",
        (conn_id, "cluster-a", "default", "pod-1"),
    )
    # Seed the initial lifecycle state in memory
    manager._memory_states[conn_id] = {
        "state": ConnectionState.POD_SELECTED,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "message": "",
    }
    return conn_id


# ═══════════════════════════════════════════════════════════════════════════
# State transition validation
# ═══════════════════════════════════════════════════════════════════════════

class TestStateTransitions:
    def test_valid_pod_selected_to_pod_checked(self, manager, sample_connection):
        assert manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )

    def test_valid_pod_checked_to_http_reusable(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.HTTP_REUSABLE
        )

    def test_valid_pod_checked_to_agent_reusable(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.AGENT_REUSABLE
        )

    def test_valid_pod_checked_to_need_jar(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.NEED_JAR
        )

    def test_valid_pod_checked_to_start_agent(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.START_AGENT
        )

    def test_valid_http_reusable_to_ready(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.HTTP_REUSABLE
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.HTTP_REUSABLE, ConnectionState.READY
        )

    def test_valid_agent_reusable_to_port_forward(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.AGENT_REUSABLE
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.AGENT_REUSABLE, ConnectionState.PORT_FORWARD
        )

    def test_valid_need_jar_to_start_agent(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.NEED_JAR
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.NEED_JAR, ConnectionState.START_AGENT
        )

    def test_valid_start_agent_to_port_forward(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.START_AGENT
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.START_AGENT, ConnectionState.PORT_FORWARD
        )

    def test_valid_port_forward_to_ping_http(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.START_AGENT
        )
        manager.transition_state(
            sample_connection, ConnectionState.START_AGENT, ConnectionState.PORT_FORWARD
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.PORT_FORWARD, ConnectionState.PING_HTTP
        )

    def test_valid_ping_http_to_ready(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.START_AGENT
        )
        manager.transition_state(
            sample_connection, ConnectionState.START_AGENT, ConnectionState.PORT_FORWARD
        )
        manager.transition_state(
            sample_connection, ConnectionState.PORT_FORWARD, ConnectionState.PING_HTTP
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.PING_HTTP, ConnectionState.READY
        )

    def test_valid_ping_http_to_retry_ping(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.START_AGENT
        )
        manager.transition_state(
            sample_connection, ConnectionState.START_AGENT, ConnectionState.PORT_FORWARD
        )
        manager.transition_state(
            sample_connection, ConnectionState.PORT_FORWARD, ConnectionState.PING_HTTP
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.PING_HTTP, ConnectionState.RETRY_PING
        )

    def test_valid_retry_ping_to_ready(self, manager, sample_connection):
        self._reach_retry_ping(manager, sample_connection)
        assert manager.transition_state(
            sample_connection, ConnectionState.RETRY_PING, ConnectionState.READY
        )

    def test_valid_retry_ping_to_failed(self, manager, sample_connection):
        self._reach_retry_ping(manager, sample_connection)
        assert manager.transition_state(
            sample_connection, ConnectionState.RETRY_PING, ConnectionState.FAILED
        )

    def test_valid_any_to_failed(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.FAILED
        )

    def test_valid_any_to_disconnected(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.DISCONNECTED
        )

    def test_valid_failed_to_pod_selected(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.FAILED
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.FAILED, ConnectionState.POD_SELECTED
        )

    def test_valid_disconnected_to_pod_selected(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.DISCONNECTED
        )
        assert manager.transition_state(
            sample_connection, ConnectionState.DISCONNECTED, ConnectionState.POD_SELECTED
        )

    def test_invalid_pod_selected_to_ready(self, manager, sample_connection):
        assert not manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.READY
        )

    def test_invalid_pod_checked_to_port_forward(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        assert not manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.PORT_FORWARD
        )

    def test_idempotent_same_state(self, manager, sample_connection):
        assert manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_SELECTED
        )

    def test_mismatch_from_state(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        assert not manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.READY
        )

    @staticmethod
    def _reach_retry_ping(manager, connection_id):
        manager.transition_state(
            connection_id, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            connection_id, ConnectionState.POD_CHECKED, ConnectionState.START_AGENT
        )
        manager.transition_state(
            connection_id, ConnectionState.START_AGENT, ConnectionState.PORT_FORWARD
        )
        manager.transition_state(
            connection_id, ConnectionState.PORT_FORWARD, ConnectionState.PING_HTTP
        )
        manager.transition_state(
            connection_id, ConnectionState.PING_HTTP, ConnectionState.RETRY_PING
        )


# ═══════════════════════════════════════════════════════════════════════════
# get_connection_state
# ═══════════════════════════════════════════════════════════════════════════

class TestGetConnectionState:
    def test_returns_memory_state_for_intermediate(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        info = manager.get_connection_state(sample_connection)
        assert info["state"] == ConnectionState.POD_CHECKED
        assert info["connection_id"] == sample_connection

    def test_returns_db_state_for_ready(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.HTTP_REUSABLE
        )
        manager.transition_state(
            sample_connection, ConnectionState.HTTP_REUSABLE, ConnectionState.READY
        )
        info = manager.get_connection_state(sample_connection)
        assert info["state"] == ConnectionState.READY

    def test_returns_disconnected_for_unknown(self, manager):
        info = manager.get_connection_state("nonexistent-id")
        assert info["state"] == ConnectionState.DISCONNECTED


# ═══════════════════════════════════════════════════════════════════════════
# State persistence (memory vs DB)
# ═══════════════════════════════════════════════════════════════════════════

class TestStatePersistence:
    def test_stable_states_written_to_db(self, manager, fresh_db, sample_connection):
        for stable in STABLE_STATES:
            # Reset to pod_selected via memory
            manager._memory_states[sample_connection] = {
                "state": ConnectionState.POD_SELECTED,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "message": "",
            }

            # Use a valid transition path to reach each stable state
            if stable == ConnectionState.READY:
                assert manager.transition_state(
                    sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
                )
                assert manager.transition_state(
                    sample_connection, ConnectionState.POD_CHECKED, ConnectionState.HTTP_REUSABLE
                )
                assert manager.transition_state(
                    sample_connection, ConnectionState.HTTP_REUSABLE, ConnectionState.READY
                )
            else:
                assert manager.transition_state(
                    sample_connection, ConnectionState.POD_SELECTED, stable
                )
            row = fresh_db.fetch_one(
                "SELECT status FROM connections WHERE id = ?", (sample_connection,)
            )
            assert row["status"] == stable.value
            assert sample_connection not in manager._memory_states

    def test_intermediate_states_stay_in_memory(self, manager, fresh_db, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        row = fresh_db.fetch_one(
            "SELECT status FROM connections WHERE id = ?", (sample_connection,)
        )
        assert row["status"] == "disconnected"  # unchanged in DB
        assert manager._memory_states[sample_connection]["state"] == ConnectionState.POD_CHECKED

    def test_ready_updates_last_ping_at(self, manager, fresh_db, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.HTTP_REUSABLE
        )
        manager.transition_state(
            sample_connection, ConnectionState.HTTP_REUSABLE, ConnectionState.READY
        )
        row = fresh_db.fetch_one(
            "SELECT last_ping_at FROM connections WHERE id = ?", (sample_connection,)
        )
        assert row["last_ping_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# TTL cleanup
# ═══════════════════════════════════════════════════════════════════════════

class TestTtlCleanup:
    def test_marks_expired_connections_as_disconnected(self, manager, fresh_db, sample_connection):
        old_ping = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        fresh_db.update(
            "connections",
            {"status": ConnectionState.FAILED.value, "last_ping_at": old_ping},
            "id = ?",
            (sample_connection,),
        )
        manager._run_ttl_cleanup()
        row = fresh_db.fetch_one(
            "SELECT status FROM connections WHERE id = ?", (sample_connection,)
        )
        assert row["status"] == ConnectionState.DISCONNECTED.value

    def test_does_not_touch_ready_connections(self, manager, fresh_db, sample_connection):
        old_ping = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        fresh_db.update(
            "connections",
            {"status": ConnectionState.READY.value, "last_ping_at": old_ping},
            "id = ?",
            (sample_connection,),
        )
        manager._run_ttl_cleanup()
        row = fresh_db.fetch_one(
            "SELECT status FROM connections WHERE id = ?", (sample_connection,)
        )
        assert row["status"] == ConnectionState.READY.value

    def test_does_not_touch_recent_connections(self, manager, fresh_db, sample_connection):
        recent_ping = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        fresh_db.update(
            "connections",
            {"status": ConnectionState.FAILED.value, "last_ping_at": recent_ping},
            "id = ?",
            (sample_connection,),
        )
        manager._run_ttl_cleanup()
        row = fresh_db.fetch_one(
            "SELECT status FROM connections WHERE id = ?", (sample_connection,)
        )
        assert row["status"] == ConnectionState.FAILED.value

    def test_removes_from_memory_on_cleanup(self, manager, fresh_db, sample_connection):
        old_ping = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        fresh_db.update(
            "connections",
            {"status": ConnectionState.FAILED.value, "last_ping_at": old_ping},
            "id = ?",
            (sample_connection,),
        )
        manager._memory_states[sample_connection] = {"state": ConnectionState.POD_CHECKED}
        manager._run_ttl_cleanup()
        assert sample_connection not in manager._memory_states

    def test_schedule_ttl_cleanup_starts_thread(self, manager):
        manager.schedule_ttl_cleanup(interval_seconds=3600)
        assert manager._ttl_thread is not None
        assert manager._ttl_thread.is_alive()
        manager.stop_ttl_cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# request_reconnect
# ═══════════════════════════════════════════════════════════════════════════

class TestRequestReconnect:
    def test_from_failed_to_pod_selected(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.FAILED
        )
        assert manager.request_reconnect(sample_connection)
        info = manager.get_connection_state(sample_connection)
        assert info["state"] == ConnectionState.POD_SELECTED

    def test_from_disconnected_to_pod_selected(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.DISCONNECTED
        )
        assert manager.request_reconnect(sample_connection)
        info = manager.get_connection_state(sample_connection)
        assert info["state"] == ConnectionState.POD_SELECTED

    def test_from_ready_is_rejected(self, manager, sample_connection):
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.READY
        )
        assert not manager.request_reconnect(sample_connection)


# ═══════════════════════════════════════════════════════════════════════════
# Audit logging
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditLogging:
    def test_audit_logged_on_transition(self, manager, fresh_db, sample_connection):
        manager.transition_state(
            sample_connection,
            ConnectionState.POD_SELECTED,
            ConnectionState.POD_CHECKED,
            user_id=None,
            message="pod exec ok",
        )
        logs = AuditService.query(
            filters={"action": "connection_state_changed", "resource_id": sample_connection},
            limit=10,
        )
        assert len(logs) == 1
        assert logs[0]["details"].startswith(
            f"Connection {sample_connection} state: pod_selected -> pod_checked"
        )
        assert "pod exec ok" in logs[0]["details"]

    def test_audit_logged_on_ttl_cleanup(self, manager, fresh_db, sample_connection):
        old_ping = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        fresh_db.update(
            "connections",
            {"status": ConnectionState.FAILED.value, "last_ping_at": old_ping},
            "id = ?",
            (sample_connection,),
        )
        manager._run_ttl_cleanup()
        logs = AuditService.query(
            filters={"action": "connection_ttl_disconnected", "resource_id": sample_connection},
            limit=10,
        )
        assert len(logs) == 1
        assert "TTL cleanup" in logs[0]["details"]


# ═══════════════════════════════════════════════════════════════════════════
# Thread safety
# ═══════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    def test_concurrent_transitions(self, manager, sample_connection):
        # Pre-establish http_reusable so threads race to ready
        manager.transition_state(
            sample_connection, ConnectionState.POD_SELECTED, ConnectionState.POD_CHECKED
        )
        manager.transition_state(
            sample_connection, ConnectionState.POD_CHECKED, ConnectionState.HTTP_REUSABLE
        )

        results = []

        def worker():
            ok = manager.transition_state(
                sample_connection, ConnectionState.HTTP_REUSABLE, ConnectionState.READY
            )
            results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one thread should succeed (first to acquire lock)
        assert sum(results) == 1
        info = manager.get_connection_state(sample_connection)
        assert info["state"] == ConnectionState.READY
