import importlib
import json
from types import SimpleNamespace

from flask import Flask
from flask_login import LoginManager


class FakeDatabase:
    def __init__(self, run):
        self.run = run
        self.updated = None

    def fetch_one(self, query, _params=()):
        if "FROM task_logs" in query:
            return self.run
        if "FROM ai_config" in query:
            return {
                "base_url": "https://llm.example/v1",
                "model": "test-model",
                "api_key": "test-key",
            }
        return None

    def update(self, table, data, where, params):
        self.updated = (table, data, where, params)
        return 1


def _client(monkeypatch, user_id, run):
    module = importlib.import_module("models.db")
    fake_db = FakeDatabase(run)
    monkeypatch.setattr(module, "db", fake_db)

    app = Flask(__name__)
    app.secret_key = "test-key"
    login_manager = LoginManager(app)

    @login_manager.user_loader
    def load_user(value):
        return SimpleNamespace(
            id=int(value),
            is_admin=False,
            is_authenticated=True,
            is_active=True,
            is_anonymous=False,
            get_id=lambda: value,
        )

    from api.performance_diagnose import diag_bp
    app.register_blueprint(diag_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    return client, fake_db


def test_report_rejects_run_owned_by_another_user(monkeypatch):
    client, _db = _client(monkeypatch, 2, {
        "id": "diag-run-1",
        "user_id": 1,
        "result_json": json.dumps({"target": "general"}),
        "is_archived": 0,
    })

    response = client.post(
        "/api/ai/diagnose_performance/report",
        json={"run_id": "diag-run-1"},
    )

    assert response.status_code == 403


def test_report_uses_saved_evidence_and_persists_llm_result(monkeypatch):
    run = {
        "id": "diag-run-1",
        "user_id": 2,
        "result_json": json.dumps({
            "target": "general",
            "namespace": "prod",
            "pod": "service-1",
            "status": "partial",
            "collection_complete": False,
            "steps": [{"name": "thread", "status": "failed", "error": "timeout"}],
            "rules_triggered": [],
            "highlights": [],
            "recommendations": [],
            "metrics": {"dashboard": "saved server evidence"},
        }),
        "is_archived": 0,
    }
    client, fake_db = _client(monkeypatch, 2, run)

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "基于证据的报告"}}]
            }).encode()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    response = client.post(
        "/api/ai/diagnose_performance/report",
        json={
            "run_id": "diag-run-1",
            "diagnosis": {"metrics": {"dashboard": "client-forged evidence"}},
        },
    )

    assert response.status_code == 200
    assert response.json["report"] == "基于证据的报告"
    assert response.json["run_id"] == "diag-run-1"
    assert fake_db.updated == (
        "task_logs",
        {"ai_analysis_result": "基于证据的报告"},
        "id = ?",
        ("diag-run-1",),
    )


def test_report_hides_archived_or_missing_runs(monkeypatch):
    client, _db = _client(monkeypatch, 2, None)

    response = client.post(
        "/api/ai/diagnose_performance/report",
        json={"run_id": "diag-run-archived"},
    )

    assert response.status_code == 404
