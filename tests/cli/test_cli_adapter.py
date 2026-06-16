import pytest
from backend.cli.adapter import CLIAdapter, StructuredResult, RiskLevel
from backend.cli.error_mapper import ErrorCode, ErrorMapper, MappedError
from backend.cli.safety_guard import SafetyGuard


def test_structured_result_creation():
    result = StructuredResult(ok=True, command="get pods", data={"items": []})
    assert result.ok is True
    assert result.command == "get pods"
    assert result.data == {"items": []}
    assert result.health is None
    assert result.error is None


def test_structured_result_with_error():
    result = StructuredResult(ok=False, command="get pods", error="E1001")
    assert result.ok is False
    assert result.error == "E1001"


def test_risk_level_enum():
    assert RiskLevel.READ.value == "read"
    assert RiskLevel.HIGH.value == "high"


def test_cli_adapter_is_abstract():
    with pytest.raises(TypeError):
        CLIAdapter()


def test_error_code_values():
    assert ErrorCode.POD_NOT_FOUND == "E1001"
    assert ErrorCode.TIMEOUT == "E0001"
    assert ErrorCode.PERMISSION_DENIED == "E0003"


def test_error_mapper_map_kubectl_not_found():
    error = ErrorMapper.map_kubectl_error("Error from server: pods nginx not found", 1)
    assert error.code == ErrorCode.POD_NOT_FOUND
    assert error.retryable is False


def test_error_mapper_map_timeout():
    error = ErrorMapper.map_kubectl_error("", -1, timeout_msg="timed out")
    assert error.code == ErrorCode.TIMEOUT
    assert error.retryable is True


def test_error_mapper_map_permission_denied():
    error = ErrorMapper.map_kubectl_error("Error from server (Forbidden): pods is forbidden", 1)
    assert error.code == ErrorCode.PERMISSION_DENIED
    assert error.retryable is False


def test_safety_guard_read_commands():
    result = SafetyGuard.check_risk("kubectl", "get_pods")
    assert result["level"] == RiskLevel.READ
    assert result["requires_confirm"] is False


def test_safety_guard_high_risk_commands():
    result = SafetyGuard.check_risk("kubectl", "delete_pod")
    assert result["level"] == RiskLevel.HIGH
    assert result["requires_confirm"] is True


def test_safety_guard_dry_run():
    result = SafetyGuard.dry_run("kubectl", "delete_pod", {"name": "test-pod", "namespace": "default"})
    assert result["dry_run"] is True
    assert "--dry-run=client" in result["command"]


def test_safety_guard_arthas_read():
    result = SafetyGuard.check_risk("arthas", "thread")
    assert result["level"] == RiskLevel.READ
    assert result["requires_confirm"] is False


def test_safety_guard_arthas_heapdump():
    result = SafetyGuard.check_risk("arthas", "heapdump")
    assert result["level"] == RiskLevel.HIGH
    assert result["requires_confirm"] is True
