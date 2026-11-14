"""One-time approvals for high-impact profiler operations."""
import hashlib
import secrets
import time


class OperationApprovalService:
    TOKEN_TTL_SECONDS = 300

    def __init__(self, database):
        self.db = database

    def issue(self, user_id: int, connection_id: str, action: str,
              duration: int, is_admin: bool = False) -> str:
        if not user_id or not connection_id:
            raise ValueError("Authenticated user and connection are required")
        if action not in ("profiler", "cpu", "jfr", "threaddump", "heapdump"):
            raise ValueError("Unsupported profiler action")
        if duration < 0 or duration > 1800:
            raise ValueError("Profiler duration must be between 0 and 1800 seconds")
        if action == "heapdump" and not is_admin:
            raise PermissionError("Heap Dump is restricted to administrators")
        if action != "heapdump" and duration <= 120:
            raise ValueError("Approval is only required for Heap Dump or sampling over 120 seconds")

        now = time.time()
        self.db.delete(
            "profiler_approvals",
            "expires_at <= ? OR consumed_at IS NOT NULL",
            (now,),
        )
        token = secrets.token_urlsafe(32)
        self.db.insert("profiler_approvals", {
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "user_id": user_id,
            "connection_id": connection_id,
            "action": action,
            "duration": duration,
            "expires_at": now + self.TOKEN_TTL_SECONDS,
        })
        return token

    def consume(self, token: str, user_id: int, connection_id: str,
                action: str, duration: int) -> bool:
        if not token or not user_id or not connection_id:
            return False
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        consumed_at = time.time()
        return self.db.update(
            "profiler_approvals",
            {"consumed_at": consumed_at},
            """token_hash = ? AND user_id = ? AND connection_id = ?
               AND action = ? AND duration = ? AND consumed_at IS NULL
               AND expires_at > ?""",
            (token_hash, user_id, connection_id, action, duration, consumed_at),
        ) == 1
