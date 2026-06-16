import pytest
from unittest.mock import patch, MagicMock
from backend.cli.kubectl_adapter import KubectlAdapter
from backend.cli.adapter import StructuredResult


def test_kubectl_adapter_init():
    adapter = KubectlAdapter(kubeconfig="/path/to/kubeconfig", context="my-context")
    assert adapter.kubeconfig == "/path/to/kubeconfig"
    assert adapter.context == "my-context"
    base = adapter._base_cmd()
    assert base[0] == "kubectl"
    assert "--kubeconfig" in base
    assert "/path/to/kubeconfig" in base
    assert "--context" in base
    assert "my-context" in base


def test_kubectl_adapter_init_defaults():
    adapter = KubectlAdapter()
    assert adapter.kubeconfig == ""
    assert adapter.context == ""
    base = adapter._base_cmd()
    assert base == ["kubectl"]


def test_kubectl_adapter_execute_get_pods():
    adapter = KubectlAdapter()
    mock_output = (
        "NAME                    READY   STATUS    RESTARTS   AGE\n"
        "nginx-7c5ddbdf54-abc12   1/1     Running   0          5d\n"
    )
    with patch.object(adapter, "_run", return_value=(0, mock_output, "")):
        result = adapter.execute("get_pods", {"namespace": "default"})
    assert isinstance(result, StructuredResult)
    assert result.ok is True
    assert isinstance(result.data, list)
    assert len(result.data) == 1
    assert result.data[0]["name"] == "nginx-7c5ddbdf54-abc12"
    assert result.data[0]["status"] == "Running"
    assert result.health is not None
    assert result.health["total"] == 1
    assert result.health["healthy"] == 1


def test_kubectl_adapter_execute_error():
    adapter = KubectlAdapter()
    with patch.object(adapter, "_run", return_value=(1, "", "Error from server: pods nginx not found")):
        result = adapter.execute("describe_pod", {"name": "nginx", "namespace": "default"})
    assert result.ok is False
    assert result.error == "E1001"


def test_kubectl_adapter_execute_requires_confirm():
    adapter = KubectlAdapter()
    result = adapter.execute("delete_pod", {"name": "nginx", "namespace": "default"})
    assert result.ok is False
    assert result.error == "REQUIRES_CONFIRMATION"


def test_kubectl_adapter_build_args():
    adapter = KubectlAdapter()
    assert adapter._build_args("get_pods", {"namespace": "kube-system"}, "kube-system") == [
        "-n", "kube-system", "get", "pods", "-o", "wide"
    ]
    assert adapter._build_args("describe_pod", {"name": "nginx"}, "default") == [
        "-n", "default", "describe", "pod", "nginx"
    ]
    assert adapter._build_args("delete_pod", {"name": "nginx"}, "default") == [
        "-n", "default", "delete", "pod", "nginx"
    ]
    assert adapter._build_args("top_pods", {}, "default") == [
        "-n", "default", "top", "pods", "--no-headers"
    ]


def test_kubectl_adapter_get_commands():
    adapter = KubectlAdapter()
    commands = adapter.get_commands()
    assert len(commands) > 0
    names = [c["name"] for c in commands]
    assert "get_pods" in names
    assert "describe_pod" in names
    assert "delete_pod" in names


def test_kubectl_adapter_dry_run():
    adapter = KubectlAdapter()
    result = adapter.dry_run("delete_pod", {"name": "nginx", "namespace": "default"})
    assert result["dry_run"] is True
    assert "--dry-run=client" in result["command"]


def test_kubectl_adapter_health_check():
    adapter = KubectlAdapter()
    result = adapter.health_check(target="test-pod")
    assert result["status"] == "implemented"
    assert result["target"] == "test-pod"
