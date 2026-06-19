from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_arthas_connection_exposes_pod_exec_command_proxy():
    source = (ROOT / "backend" / "core" / "connection.py").read_text(encoding="utf-8")

    assert "def exec_command(self, command: str, timeout: int = 30):" in source
    assert "return self.pod_conn.exec_command(command, timeout=timeout)" in source


def test_pod_diagnose_exec_uses_pod_connection_for_wrapped_arthas_connection():
    source = (ROOT / "api" / "pod_apis.py").read_text(encoding="utf-8")

    assert "getattr(conn, 'pod_conn', None)" in source
    assert "pod_conn.exec_command(cmd, timeout=timeout)" in source
    assert "current connection does not support Pod command execution" in source
