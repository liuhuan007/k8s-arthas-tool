"""Integration tests for ConnectionPool with WorkspaceStore & acquire/release"""
import threading
from unittest.mock import MagicMock

from backend.core.connection_pool import ConnectionPool, ConnectionState
from backend.core.workspace_store import WorkspaceStore


def _dummy_conn():
    m = MagicMock()
    m.is_alive.return_value = True
    m.disconnect.return_value = None
    m.local_port = 32000
    m.java_pid = 1234
    m.arthas_version = "3.7.0"
    m.arthas_address = "http://127.0.0.1:32000"
    return m


def test_empty_stats():
    pool = ConnectionPool()
    s = pool.stats()
    assert s["total_connections"] == 0
    assert s["active_connections"] == 0
    assert s["idle_connections"] == 0
    assert s["max_connections"] == 20
    assert s["focus_id"] is None
    assert s["workspace_count"] == 0


def test_add_and_stats():
    pool = ConnectionPool()
    conn = _dummy_conn()
    assert pool.add("ns/pod", conn) is True

    s = pool.stats()
    assert s["total_connections"] == 1
    assert s["active_connections"] == 0
    assert s["idle_connections"] == 1
    assert s["workspace_count"] == 1  # auto-created


def test_acquire_release_lifecycle():
    pool = ConnectionPool()
    conn = _dummy_conn()
    pool.add("ns/pod", conn)

    assert pool.acquire("ns/pod") is True
    assert pool.is_active("ns/pod") is True
    assert pool.stats()["active_connections"] == 1

    assert pool.release("ns/pod") is True
    assert pool.is_active("ns/pod") is False
    assert pool.stats()["active_connections"] == 0


def test_acquire_nonexistent():
    pool = ConnectionPool()
    assert pool.acquire("nonexistent") is False


def test_release_nonexistent():
    pool = ConnectionPool()
    assert pool.release("nonexistent") is False


def test_active_conns_skipped_by_cleanup():
    pool = ConnectionPool()
    conn = _dummy_conn()
    pool.add("ns/pod", conn)

    pool.acquire("ns/pod")
    pool.update_state("ns/pod", ConnectionState.DEAD)

    assert pool.cleanup_dead() == 0  # active, not cleaned
    assert pool.get("ns/pod") is not None

    pool.release("ns/pod")
    assert pool.cleanup_dead() == 1  # now inactive, cleaned


def test_workspace_store_injection():
    ws_store = WorkspaceStore()
    pool = ConnectionPool(workspace_store=ws_store)

    conn = _dummy_conn()
    pool.add("ns/pod", conn)

    # workspace accessible via same store
    ws = ws_store.get("ns/pod")
    assert ws is not None
    assert pool.get_workspace("ns/pod") is ws
    assert ws_store.count() == 1
    assert pool.stats()["workspace_count"] == 1


def test_concurrent_acquire_release():
    pool = ConnectionPool()
    conn = _dummy_conn()
    pool.add("ns/pod", conn)

    errors = []

    def worker():
        try:
            for _ in range(50):
                pool.acquire("ns/pod")
                pool.release("ns/pod")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    assert len(errors) == 0, f"Concurrent errors: {errors}"
    assert pool.stats()["active_connections"] == 0


def test_max_connections_backpressure():
    pool = ConnectionPool(max_connections=3)
    conns = [_dummy_conn() for _ in range(4)]

    assert pool.add("a", conns[0]) is True
    assert pool.add("b", conns[1]) is True
    assert pool.add("c", conns[2]) is True
    assert pool.add("d", conns[3]) is False  # pool full

    assert pool.stats()["total_connections"] == 3


def test_upsert_replaces_existing_connection_and_preserves_focus():
    pool = ConnectionPool()
    pod_conn = _dummy_conn()
    arthas_conn = _dummy_conn()
    arthas_conn.local_port = 32001

    assert pool.upsert("cluster/ns/pod", pod_conn, user_id=7) is True
    assert pool.set_focus("cluster/ns/pod") is True

    assert pool.upsert("cluster/ns/pod", arthas_conn, user_id=7, mcp_available=True) is False

    focused = pool.get_focused()
    assert focused is not None
    assert focused.conn is arthas_conn
    assert focused.user_id == 7
    assert focused.mcp_available is True
    assert pool.stats()["total_connections"] == 1
    pod_conn.disconnect.assert_not_called()


def test_app_context_register_keeps_compat_dict_and_pool_in_sync():
    from backend import app_context

    original_pool = app_context.get_connection_pool()
    original_connections = dict(app_context.connections)
    pool = ConnectionPool()
    app_context.connections.clear()
    app_context.set_connection_pool(pool)
    try:
        conn = _dummy_conn()
        app_context.register_connection(
            "cluster/ns/pod",
            conn,
            user_id=42,
            level="arthas",
            mcp_available=True,
        )

        assert app_context.connections["cluster/ns/pod"]["conn"] is conn
        assert pool.get_connection("cluster/ns/pod") is conn
        assert pool.get_focused_id() == "cluster/ns/pod"

        entry = app_context.get_connection_entry("cluster/ns/pod")
        assert entry["conn"] is conn
        assert entry["user_id"] == 42
        assert entry["level"] == "arthas"

        assert app_context.unregister_connection("cluster/ns/pod") is conn
        assert "cluster/ns/pod" not in app_context.connections
        assert pool.get("cluster/ns/pod") is None
    finally:
        pool.disconnect_all()
        app_context.connections.clear()
        app_context.connections.update(original_connections)
        app_context.set_connection_pool(original_pool)
