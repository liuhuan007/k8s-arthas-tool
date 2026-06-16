import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.cli.health_checker import HealthChecker


def test_check_pod_healthy():
    pod = {"status": "Running", "ready": "1/1", "restarts": 0}
    result = HealthChecker.check_pod(pod)
    assert result["status"] == "healthy"
    assert result["issues"] == []


def test_check_pod_unhealthy():
    pod = {"status": "CrashLoopBackOff", "ready": "0/1", "restarts": 5}
    result = HealthChecker.check_pod(pod)
    assert result["status"] == "unhealthy"
    assert len(result["issues"]) > 0


def test_check_pod_degraded():
    pod = {"status": "Running", "ready": "0/1", "restarts": 0}
    result = HealthChecker.check_pod(pod)
    assert result["status"] == "degraded"
    assert len(result["issues"]) > 0
