import sys
from datetime import datetime, timedelta

sys.path.insert(0, r'e:/tmp/k8s-arthas-tool')

from api.task_center import _compute_next_run_at, _normalize_schedule_interval


def test_normalize_schedule_interval_enforces_bounds():
    assert _normalize_schedule_interval(0) == 60
    assert _normalize_schedule_interval(30) == 60
    assert _normalize_schedule_interval(120) == 120
    assert _normalize_schedule_interval(90000) == 86400


def test_compute_next_run_at_adds_interval_seconds():
    base = '2026-04-29 10:00:00'
    assert _compute_next_run_at(120, base) == '2026-04-29 10:02:00'


def test_compute_next_run_at_defaults_from_now_format():
    value = _compute_next_run_at(60)
    parsed = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    assert parsed > datetime.now() - timedelta(seconds=5)
