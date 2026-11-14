import json
import importlib
from types import SimpleNamespace

from api.performance_diagnose import _persist_diagnosis_run


class FakeDatabase:
    def __init__(self):
        self.inserted = None

    def insert(self, table, data):
        self.inserted = (table, data)


def test_persist_diagnosis_run_saves_server_evidence(monkeypatch):
    db_module = importlib.import_module("models.db")

    fake_db = FakeDatabase()
    monkeypatch.setattr(db_module, "db", fake_db)
    conn = SimpleNamespace(
        target=SimpleNamespace(
            cluster_name="cluster",
            namespace="ns",
            pod_name="pod",
            container="app",
        )
    )
    diagnosis = {
        "timestamp": "2026-03-22T12:00:00",
        "connection_id": "cluster/ns/pod",
        "target": "general",
        "status": "partial",
        "steps": [{"name": "thread", "status": "failed", "error": "timeout"}],
        "metrics": {"dashboard": '{"state":"SUCCEEDED"}'},
    }

    run_id = _persist_diagnosis_run(diagnosis, conn, user_id=7, duration_ms=1500)

    table, row = fake_db.inserted
    assert table == "task_logs"
    assert run_id.startswith("diag-")
    assert row["id"] == run_id
    assert row["user_id"] == 7
    assert row["status"] == "partial"
    assert row["duration_ms"] == 1500
    assert row["error_message"] == "thread: timeout"
    assert json.loads(row["result_json"]) == diagnosis
    assert json.loads(row["target_json"])["connection_id"] == "cluster/ns/pod"
