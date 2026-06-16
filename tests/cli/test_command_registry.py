import pytest
from backend.cli.command_registry import CommandRegistry


def test_get_kubectl_commands():
    commands = CommandRegistry.get_commands("kubectl")
    assert len(commands) > 0
    names = [c["name"] for c in commands]
    assert "get_pods" in names
    assert "delete_pod" in names


def test_get_arthas_commands():
    commands = CommandRegistry.get_commands("arthas")
    assert len(commands) > 0
    names = [c["name"] for c in commands]
    assert "thread" in names
    assert "dashboard" in names
    assert "trace" in names


def test_get_command_help():
    help_info = CommandRegistry.get_help("kubectl", "get_pods")
    assert help_info is not None
    assert "description" in help_info
    assert "params" in help_info
