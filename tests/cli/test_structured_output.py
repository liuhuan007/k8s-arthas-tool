import pytest
from backend.cli.structured_output import StructuredOutput


def test_parse_pod_list():
    raw = """NAME                    READY   STATUS    RESTARTS   AGE
nginx-7c5ddbdf54-abc12   1/1     Running   0          2d
redis-yyy                0/1     Error     3          1h"""
    result = StructuredOutput.parse_pod_list(raw)
    assert len(result) == 2
    assert result[0]["name"] == "nginx-7c5ddbdf54-abc12"
    assert result[0]["status"] == "Running"
    assert result[0]["restarts"] == 0
    assert result[1]["status"] == "Error"
    assert result[1]["restarts"] == 3


def test_parse_top_pods():
    raw = """NAME                    CPU(bytes)   MEMORY(bytes)
nginx-7c5ddbdf54-abc12   100m         128Mi
redis-yyy                50m          64Mi"""
    result = StructuredOutput.parse_top_pods(raw)
    assert len(result) == 2
    assert result[0]["cpu"] == "100m"
    assert result[0]["memory"] == "128Mi"


def test_parse_empty_output():
    result = StructuredOutput.parse_pod_list("")
    assert result == []
