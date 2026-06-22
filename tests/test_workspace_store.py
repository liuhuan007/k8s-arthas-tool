"""Tests for WorkspaceStore"""
import threading
from backend.core.workspace_store import WorkspaceStore
from backend.core.connection_pool import WorkspaceState, WorkspaceTab


def test_get_or_create():
    store = WorkspaceStore()
    ws = store.get_or_create("a/b/c")
    assert isinstance(ws, WorkspaceState)
    assert ws.active_tab == WorkspaceTab.MONITOR
    # same id returns same object
    assert store.get_or_create("a/b/c") is ws


def test_get_nonexistent():
    store = WorkspaceStore()
    assert store.get("nonexistent") is None


def test_remove():
    store = WorkspaceStore()
    store.get_or_create("a/b/c")
    assert store.remove("a/b/c") is True
    assert store.get("a/b/c") is None


def test_remove_nonexistent():
    store = WorkspaceStore()
    assert store.remove("nonexistent") is False


def test_remove_preserve():
    store = WorkspaceStore()
    store.get_or_create("a/b/c")
    assert store.remove("a/b/c", preserve=True) is True
    # preserved — still accessible
    ws = store.get("a/b/c")
    assert ws is not None


def test_clear():
    store = WorkspaceStore()
    store.get_or_create("a")
    store.get_or_create("b")
    store.get_or_create("c")
    assert store.count() == 3
    store.clear()
    assert store.count() == 0


def test_list_all():
    store = WorkspaceStore()
    store.get_or_create("a/b/c")
    store.get_or_create("d/e/f")
    all_ws = store.list_all()
    assert len(all_ws) == 2
    assert "a/b/c" in all_ws
    assert "d/e/f" in all_ws


def test_concurrent_safety():
    store = WorkspaceStore()
    errors = []

    def worker(i):
        try:
            ws = store.get_or_create(f"conn-{i}")
            ws.active_tab = WorkspaceTab.SAMPLING if i % 2 == 0 else WorkspaceTab.MONITOR
            ws.sub_tab = str(i)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    assert len(errors) == 0, f"Concurrent errors: {errors}"
    assert store.count() == 30
