import json
from types import SimpleNamespace

import backend.core.arthas_executor as arthas_executor
from api.performance_diagnose import _run_diagnosis
from backend.core.rule_engine import extract_metrics_from_diagnosis


def test_extract_metrics_from_structured_arthas_responses():
    diagnosis = {
        "metrics": {
            "dashboard": json.dumps({
                "state": "SUCCEEDED",
                "body": {"results": [{
                    "cpu_percent": 96.5,
                    "memoryInfo": {
                        "heap": [
                            {"name": "Old Gen", "used": 1700 * 1024 * 1024},
                            {"name": "Eden Space", "used": 20 * 1024 * 1024},
                        ]
                    },
                    "gcInfos": [
                        {"name": "PS Scavenge", "collectionCount": 120},
                        {"name": "PS MarkSweep", "collectionCount": 2},
                    ],
                }]},
            }),
            "threads": json.dumps({
                "body": {"busyThreads": [
                    {"state": "BLOCKED"},
                    {"state": "RUNNABLE"},
                    {"state": "blocked"},
                ]}
            }),
            "trace": json.dumps({
                "body": {"results": [{"cost": 2500}, {"cost": 600}]}
            }),
        },
    }

    metrics = extract_metrics_from_diagnosis(diagnosis)

    assert metrics == {
        "cpu_percent": 96.5,
        "old_gen_mb": 1700,
        "blocked_threads": 2,
        "trace_ms": 2500,
    }


def test_thread_cpu_is_not_misclassified_as_jvm_cpu():
    diagnosis = {
        "metrics": {
            "dashboard": json.dumps({
                "body": {"results": [{"threads": [{"cpu": 99.0}]}]}
            }),
            "threads": json.dumps({
                "body": {"busyThreads": [{"state": "RUNNABLE", "cpu": 99.0}]}
            }),
        },
    }

    metrics = extract_metrics_from_diagnosis(diagnosis)

    assert "cpu_percent" not in metrics
    assert metrics["blocked_threads"] == 0


def test_legacy_dashboard_text_still_uses_regex_fallback():
    metrics = extract_metrics_from_diagnosis({
        "metrics": {"dashboard": "cpu=81.2% Old Gen: 1.5GB YGC: 101 FGC: 2"}
    })

    assert metrics["cpu_percent"] == 81.2
    assert metrics["old_gen_mb"] == 1536
    assert "young_gc_count" not in metrics
    assert "full_gc_count" not in metrics


def test_diagnosis_marks_partial_when_a_collection_step_fails(monkeypatch):
    def execute(_conn, command, **_kwargs):
        if command.startswith("dashboard"):
            return {
                "state": "SUCCEEDED",
                "body": {"results": [{
                    "memoryInfo": {"heap": [
                        {"name": "Old Gen", "used": 1700 * 1024 * 1024}
                    ]}
                }]},
            }
        raise RuntimeError("thread command timed out")

    monkeypatch.setattr(arthas_executor.ArthasCommandExecutor, "execute", execute)
    conn = SimpleNamespace(
        target=SimpleNamespace(
            cluster_name="cluster",
            container="app",
            pod_name="pod",
            namespace="ns",
        ),
        java_pid=123,
        http_client=object(),
    )

    diagnosis = _run_diagnosis(conn, "general", "", "")

    assert diagnosis["status"] == "partial"
    assert diagnosis["collection_complete"] is False
    assert diagnosis["severity"] == "critical"
    assert diagnosis["steps"][1]["error"] == "thread command timed out"
    assert "不能据此确认" in diagnosis["summary"]
