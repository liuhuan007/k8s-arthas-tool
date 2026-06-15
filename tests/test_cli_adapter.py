import pytest
from backend.core.cli.adapter import CLIAdapter, StructuredResult, RiskLevel


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
