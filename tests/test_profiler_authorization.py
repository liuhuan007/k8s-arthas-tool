from services.profiler_service import ProfilerService


class FakeDatabase:
    def __init__(self):
        self.task = {
            "id": "prof-owner-task",
            "connection_id": "cluster/ns/pod",
            "user_id": 10,
            "type": "cpu",
            "mode": "cpu",
            "event": "cpu",
            "duration": 30,
            "format": "html",
            "status": "pending",
            "progress": 0,
            "output_path": "",
            "message": "",
            "created_at": "",
            "updated_at": "",
        }

    def fetch_one(self, query, params=()):
        if params == ("prof-owner-task",):
            return dict(self.task)
        return None


def _service():
    service = ProfilerService.__new__(ProfilerService)
    service.db = FakeDatabase()
    service._running_workflows = {}
    return service


def test_profiler_task_status_is_hidden_from_other_users():
    result = _service().get_task_status("prof-owner-task", user_id=11)

    assert result == {"success": False, "message": "任务不存在或无权访问"}


def test_profiler_task_cannot_be_started_or_stopped_by_other_users():
    service = _service()

    started = service.start_task("prof-owner-task", user_id=11)
    stopped = service.stop_task("prof-owner-task", user_id=11)

    assert started["success"] is False
    assert stopped["success"] is False
    assert service.db.task["status"] == "pending"


def test_profiler_task_owner_can_read_status():
    result = _service().get_task_status("prof-owner-task", user_id=10)

    assert result["success"] is True
    assert result["task"]["user_id"] == 10


def test_heapdump_is_admin_only_at_service_boundary():
    service = _service()
    service.db.task["type"] = "heapdump"

    denied = service.get_task_status("prof-owner-task", user_id=10)
    denied_start = service.start_task("prof-owner-task", user_id=10)
    allowed = service.get_task_status(
        "prof-owner-task", user_id=10, is_admin=True)

    assert denied == {"success": False, "message": "任务不存在或无权访问"}
    assert denied_start == {"success": False, "message": "任务不存在或无权访问"}
    assert allowed["success"] is True


def test_long_profiler_run_requires_explicit_confirmation():
    service = _service()
    service.db.task["duration"] = 121

    result = service.start_task("prof-owner-task", user_id=10)

    assert result["success"] is False
    assert result["requires_confirmation"] is True
    assert "逐次审批令牌" in result["message"]
    assert service.db.task["status"] == "pending"
