from types import SimpleNamespace

from api import diagnosis


def test_diagnosis_connection_lookup_enforces_owner(monkeypatch):
    conn = object()
    entry = {"conn": conn, "user_id": 7}
    monkeypatch.setattr(
        "backend.app_context.get_connection_entry", lambda _connection_id: entry)

    monkeypatch.setattr(
        diagnosis, "current_user",
        SimpleNamespace(is_authenticated=True, is_admin=False, id=8))
    assert diagnosis._get_arthas_connection("cluster/ns/pod") is None

    monkeypatch.setattr(
        diagnosis, "current_user",
        SimpleNamespace(is_authenticated=True, is_admin=False, id=7))
    assert diagnosis._get_arthas_connection("cluster/ns/pod") is conn

    monkeypatch.setattr(
        diagnosis, "current_user",
        SimpleNamespace(is_authenticated=False, is_admin=True, id=1))
    assert diagnosis._get_arthas_connection("cluster/ns/pod") is None
