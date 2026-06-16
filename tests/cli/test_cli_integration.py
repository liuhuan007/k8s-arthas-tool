import pytest
from backend.cli import (
    CommandRegistry, SafetyGuard, ErrorMapper, StructuredOutput,
    HealthChecker, KubectlAdapter, ArthasAdapter
)
from backend.cli.adapter import RiskLevel
from unittest.mock import patch


def test_command_registry_returns_kubectl_commands():
    commands = CommandRegistry.get_commands("kubectl")
    assert len(commands) > 0
    names = [c["name"] for c in commands]
    assert "get_pods" in names
    assert "delete_pod" in names


def test_command_registry_returns_arthas_commands():
    commands = CommandRegistry.get_commands("arthas")
    assert len(commands) > 0
    names = [c["name"] for c in commands]
    assert "thread" in names
    assert "heapdump" in names


def test_command_registry_get_help():
    help_info = CommandRegistry.get_help("kubectl", "get_pods")
    assert help_info is not None
    assert help_info["risk_level"] == "read"


def test_safety_guard_risk_levels():
    read = SafetyGuard.check_risk("kubectl", "get_pods")
    assert read["level"] == RiskLevel.READ
    assert read["requires_confirm"] is False

    high = SafetyGuard.check_risk("kubectl", "delete_pod")
    assert high["level"] == RiskLevel.HIGH
    assert high["requires_confirm"] is True

    low = SafetyGuard.check_risk("kubectl", "exec_in_pod")
    assert low["level"] == RiskLevel.LOW
    assert low["requires_confirm"] is False


def test_safety_guard_dry_run_generation():
    result = SafetyGuard.dry_run(
        "kubectl", "delete_pod",
        {"name": "test-pod", "namespace": "default"}
    )
    assert result["dry_run"] is True
    assert "--dry-run=client" in result["command"]
    assert "delete" in result["command"]


def test_error_mapper_not_found():
    error = ErrorMapper.map_kubectl_error(
        "Error from server: pods nginx not found", 1
    )
    assert error.code == "E1001"
    assert error.retryable is False


def test_error_mapper_permission_denied():
    error = ErrorMapper.map_kubectl_error(
        "Error from server (Forbidden): pods is forbidden", 1
    )
    assert error.code == "E0003"
    assert error.retryable is False


def test_error_mapper_timeout():
    error = ErrorMapper.map_kubectl_error("", -1, timeout_msg="timed out")
    assert error.code == "E0001"
    assert error.retryable is True


def test_error_mapper_connection_failed():
    error = ErrorMapper.map_kubectl_error("some random error", 1)
    assert error.code == "E0002"
    assert error.retryable is True


def test_structured_output_parse_pod_list():
    text = (
        "NAME                    READY   STATUS    RESTARTS   AGE\n"
        "nginx-7c5ddbdf54-abc12   1/1     Running   0          5d\n"
        "redis-5d6f7b8c9d-xyz34   1/1     Running   2          3d\n"
    )
    pods = StructuredOutput.parse_pod_list(text)
    assert len(pods) == 2
    assert pods[0]["name"] == "nginx-7c5ddbdf54-abc12"
    assert pods[1]["restarts"] == 2


def test_structured_output_parse_top_pods():
    text = (
        "NAME                    CPU(cores)   MEMORY(bytes)\n"
        "nginx-7c5ddbdf54-abc12   100m         128Mi\n"
    )
    pods = StructuredOutput.parse_top_pods(text)
    assert len(pods) == 1
    assert pods[0]["cpu"] == "100m"
    assert pods[0]["memory"] == "128Mi"


def test_health_checker_pod_health_healthy():
    healthy = HealthChecker.check_pod({
        "status": "Running",
        "ready": "1/1",
        "restarts": 0
    })
    assert healthy["status"] == "healthy"


def test_health_checker_pod_health_unhealthy():
    unhealthy = HealthChecker.check_pod({
        "status": "CrashLoopBackOff",
        "ready": "0/1",
        "restarts": 10
    })
    assert unhealthy["status"] == "unhealthy"


def test_health_checker_jvm_health_healthy():
    healthy = HealthChecker.check_jvm({
        "cpu_percent": 30,
        "memory_percent": 50,
        "gc_pause_ms": 10
    })
    assert healthy["status"] == "healthy"


def test_health_checker_jvm_health_unhealthy():
    unhealthy = HealthChecker.check_jvm({
        "cpu_percent": 95,
        "memory_percent": 92,
        "gc_pause_ms": 15000
    })
    assert unhealthy["status"] == "unhealthy"
    assert len(unhealthy["issues"]) > 0


def test_full_workflow_command_discovery_to_execution():
    adapter = KubectlAdapter()
    commands = CommandRegistry.get_commands("kubectl")
    assert len(commands) > 0

    cmd_name = "get_pods"
    safety = SafetyGuard.check_risk("kubectl", cmd_name)
    assert safety["level"] == RiskLevel.READ

    mock_output = (
        "NAME                    READY   STATUS    RESTARTS   AGE\n"
        "nginx-7c5ddbdf54-abc12   1/1     Running   0          5d\n"
    )
    with patch.object(adapter, "_run", return_value=(0, mock_output, "")):
        result = adapter.execute(cmd_name, {"namespace": "default"})
    assert result.ok is True
    assert len(result.data) == 1

    health = result.health
    assert health["total"] == 1
    assert health["healthy"] == 1


def test_full_workflow_error_handling():
    adapter = KubectlAdapter()
    with patch.object(adapter, "_run", return_value=(1, "", "Error from server: pods nginx not found")):
        result = adapter.execute("describe_pod", {"name": "nginx", "namespace": "default"})
    assert result.ok is False
    assert result.error == "E1001"


def test_full_workflow_high_risk_blocks_execution():
    adapter = KubectlAdapter()
    result = adapter.execute("delete_pod", {"name": "nginx", "namespace": "default"})
    assert result.ok is False
    assert result.error == "REQUIRES_CONFIRMATION"


def test_full_workflow_dry_run_before_high_risk():
    dry = SafetyGuard.dry_run(
        "kubectl", "delete_pod",
        {"name": "nginx", "namespace": "default"}
    )
    assert dry["dry_run"] is True
    assert "--dry-run=client" in dry["command"]
