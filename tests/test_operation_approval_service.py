import time

import pytest

from services.operation_approval_service import OperationApprovalService


class FakeDatabase:
    def __init__(self):
        self.rows = []

    def delete(self, table, where, params):
        now, = params
        self.rows = [
            row for row in self.rows
            if row["expires_at"] > now and row["consumed_at"] is None
        ]

    def insert(self, table, values):
        self.rows.append(dict(values, consumed_at=None))
        return len(self.rows)

    def update(self, table, values, where, params):
        token_hash, user_id, connection_id, action, duration, now = params
        for row in self.rows:
            if (
                row["token_hash"] == token_hash
                and row["user_id"] == user_id
                and row["connection_id"] == connection_id
                and row["action"] == action
                and row["duration"] == duration
                and row["consumed_at"] is None
                and row["expires_at"] > now
            ):
                row.update(values)
                return 1
        return 0


def test_approval_is_bound_to_user_connection_action_and_duration_and_single_use():
    database = FakeDatabase()
    approvals = OperationApprovalService(database)
    token = approvals.issue(10, "cluster/ns/pod", "profiler", 300)

    assert not approvals.consume(token, 11, "cluster/ns/pod", "profiler", 300)
    assert not approvals.consume(token, 10, "cluster/ns/other", "profiler", 300)
    assert not approvals.consume(token, 10, "cluster/ns/pod", "jfr", 300)
    assert not approvals.consume(token, 10, "cluster/ns/pod", "profiler", 301)
    assert approvals.consume(token, 10, "cluster/ns/pod", "profiler", 300)
    assert not approvals.consume(token, 10, "cluster/ns/pod", "profiler", 300)


def test_heap_dump_approval_is_admin_only():
    approvals = OperationApprovalService(FakeDatabase())

    with pytest.raises(PermissionError):
        approvals.issue(10, "cluster/ns/pod", "heapdump", 0)

    token = approvals.issue(
        10, "cluster/ns/pod", "heapdump", 0, is_admin=True)
    assert approvals.consume(token, 10, "cluster/ns/pod", "heapdump", 0)


def test_expired_approval_cannot_be_consumed():
    database = FakeDatabase()
    approvals = OperationApprovalService(database)
    token = approvals.issue(10, "cluster/ns/pod", "profiler", 300)
    database.rows[0]["expires_at"] = time.time() - 1

    assert not approvals.consume(token, 10, "cluster/ns/pod", "profiler", 300)
