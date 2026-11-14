import asyncio
from types import SimpleNamespace

from services import mcp_server


def test_mcp_connection_lookup_requires_owner_or_admin(monkeypatch):
    conn = SimpleNamespace(http_client=object())
    entry = {"conn": conn, "user_id": 7}
    monkeypatch.setattr(
        "backend.app_context.get_connection_entry", lambda _connection_id: entry)

    assert mcp_server._get_connection("cluster/ns/pod") is None
    assert mcp_server._get_connection(
        "cluster/ns/pod", user_id=8) is None
    assert mcp_server._get_connection(
        "cluster/ns/pod", user_id=7) is conn
    assert mcp_server._get_connection(
        "cluster/ns/pod", user_id=8, is_admin=True) is conn


def test_mcp_tool_execution_requires_authenticated_user():
    result = asyncio.run(mcp_server.execute_tool(
        "pod_status", {"connection_id": "cluster/ns/pod"}))

    assert "必须绑定已认证用户" in result


def test_mcp_raw_heapdump_requires_confirmation_ui(monkeypatch):
    conn = SimpleNamespace(http_client=object())
    monkeypatch.setattr(mcp_server, "_get_connection", lambda *_args, **_kwargs: conn)

    result = asyncio.run(mcp_server.execute_tool(
        "execute_arthas",
        {"connection_id": "cluster/ns/pod", "command": "heapdump"},
        user_id=7,
    ))

    assert "逐次确认" in result


def test_mcp_cpu_sampling_schema_is_bounded():
    tool = next(tool for tool in mcp_server.TOOLS if tool["name"] == "profiler_cpu")

    assert tool["inputSchema"]["properties"]["duration"]["maximum"] == 120


def test_mcp_http_bridge_checks_connection_owner(monkeypatch):
    from api import mcp_standard

    entry = {"conn": object(), "user_id": 7}
    monkeypatch.setattr(
        "backend.app_context.get_connection_entry", lambda _connection_id: entry)
    monkeypatch.setattr(
        mcp_standard, "current_user",
        SimpleNamespace(id=8, is_admin=False))

    assert mcp_standard._can_access_connection("cluster/ns/pod") is False

    monkeypatch.setattr(
        mcp_standard, "current_user",
        SimpleNamespace(id=8, is_admin=True))
    assert mcp_standard._can_access_connection("cluster/ns/pod") is True
