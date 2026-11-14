import json
from types import SimpleNamespace

from flask import Flask
from flask_login import LoginManager


class FakeDatabase:
    def __init__(self):
        self.queries = []

    def fetch_one(self, query, params=()):
        self.queries.append((query, params))
        return {"cnt": 1}

    def fetch_all(self, query, params=()):
        self.queries.append((query, params))
        return [{
            "id": "diag-run-1",
            "user_id": 7,
            "target_json": json.dumps({"pod": "service-1"}),
            "params_json": "{}",
            "result_json": json.dumps({"status": "partial"}),
            "ai_analysis_result": "saved report",
            "status": "partial",
        }]


def test_diagnosis_history_lists_runs_for_current_user(monkeypatch):
    from api import task_center

    fake_db = FakeDatabase()
    monkeypatch.setattr(task_center, "db", fake_db)

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

    app.register_blueprint(task_center.task_bp)
    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = "7"
        session["_fresh"] = True

    response = client.get("/api/tasks/diagnosis/history")

    assert response.status_code == 200
    assert response.json["history"][0]["id"] == "diag-run-1"
    assert response.json["history"][0]["target"] == {"pod": "service-1"}
    assert response.json["history"][0]["ai_analysis_result"] == "saved report"
    assert all("COALESCE(t.is_archived, 0) = 0" in query for query, _ in fake_db.queries)
    assert all("t.user_id = ?" in query and params[0] == 7
               for query, params in fake_db.queries)
