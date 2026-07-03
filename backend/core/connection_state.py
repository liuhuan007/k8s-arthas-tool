"""Connection state management - tracks connection lifecycle states."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, Optional, Any

from models.db import Database
from services.audit_service import AuditService

log = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection lifecycle states."""

    POD_SELECTED = "pod_selected"
    POD_CHECKED = "pod_checked"
    HTTP_REUSABLE = "http_reusable"
    AGENT_REUSABLE = "agent_reusable"
    NEED_JAR = "need_jar"
    START_AGENT = "start_agent"
    PORT_FORWARD = "port_forward"
    PING_HTTP = "ping_http"
    RETRY_PING = "retry_ping"
    READY = "ready"
    FAILED = "failed"
    DISCONNECTED = "disconnected"


# States that are persisted to the database
STABLE_STATES = {ConnectionState.READY, ConnectionState.FAILED, ConnectionState.DISCONNECTED}

# Valid state transitions (excluding global error/disconnect rules)
VALID_TRANSITIONS: Dict[ConnectionState, set] = {
    ConnectionState.POD_SELECTED: {ConnectionState.POD_CHECKED},
    ConnectionState.POD_CHECKED: {
        ConnectionState.HTTP_REUSABLE,
        ConnectionState.AGENT_REUSABLE,
        ConnectionState.NEED_JAR,
        ConnectionState.START_AGENT,
    },
    ConnectionState.HTTP_REUSABLE: {ConnectionState.READY},
    ConnectionState.AGENT_REUSABLE: {ConnectionState.PORT_FORWARD},
    ConnectionState.NEED_JAR: {ConnectionState.START_AGENT},
    ConnectionState.START_AGENT: {ConnectionState.PORT_FORWARD},
    ConnectionState.PORT_FORWARD: {ConnectionState.PING_HTTP},
    ConnectionState.PING_HTTP: {ConnectionState.READY, ConnectionState.RETRY_PING},
    ConnectionState.RETRY_PING: {ConnectionState.READY, ConnectionState.FAILED},
    # Recovery transitions
    ConnectionState.FAILED: {ConnectionState.POD_SELECTED},
    ConnectionState.DISCONNECTED: {ConnectionState.POD_SELECTED, ConnectionState.READY},
}

# Global transitions allowed from any state
GLOBAL_TRANSITIONS = {ConnectionState.FAILED, ConnectionState.DISCONNECTED}


class ConnectionStateManager:
    """Manages connection lifecycle states with memory/DB persistence and TTL cleanup."""

    def __init__(self, db: Database):
        self.db = db
        self._memory_states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._ttl_thread: Optional[threading.Thread] = None
        self._stop_ttl_event = threading.Event()

    # ── State queries ────────────────────────────────────────────────────────

    def get_connection_state(self, connection_id: str) -> dict:
        """Return current state info from memory or DB."""
        with self._lock:
            mem = self._memory_states.get(connection_id)
            if mem is not None:
                return {
                    "connection_id": connection_id,
                    "state": mem["state"],
                    "last_ping_at": mem.get("last_ping_at"),
                    "updated_at": mem.get("updated_at"),
                    "message": mem.get("message", ""),
                }

        # Fall back to DB for stable states
        row = self.db.fetch_one(
            "SELECT status, last_ping_at, updated_at FROM connections WHERE id = ?",
            (connection_id,),
        )
        if row is not None and row.get("status"):
            state = self._state_from_str(row["status"])
            return {
                "connection_id": connection_id,
                "state": state,
                "last_ping_at": row.get("last_ping_at"),
                "updated_at": row.get("updated_at"),
                "message": "",
            }

        return {
            "connection_id": connection_id,
            "state": ConnectionState.DISCONNECTED,
            "last_ping_at": None,
            "updated_at": None,
            "message": "",
        }

    # ── State transitions ────────────────────────────────────────────────────

    def transition_state(
        self,
        connection_id: str,
        from_state: ConnectionState,
        to_state: ConnectionState,
        **kwargs: Any,
    ) -> bool:
        """Validate and perform a state transition, logging an audit event.

        Returns True if the transition succeeded (or was idempotent).
        """
        if from_state == to_state:
            return True

        with self._lock:
            current_info = self._get_current_state_unlocked(connection_id)
            current_state = current_info["state"]

            if current_state != from_state:
                log.warning(
                    "State transition mismatch for %s: expected %s, got %s",
                    connection_id,
                    from_state.value,
                    current_state.value,
                )
                return False

            if not self._is_valid_transition(current_state, to_state):
                log.warning(
                    "Invalid state transition for %s: %s -> %s",
                    connection_id,
                    current_state.value,
                    to_state.value,
                )
                return False

            self._apply_state_unlocked(connection_id, to_state, **kwargs)

        # Audit logging outside the lock to avoid DB contention
        user_id = kwargs.get("user_id")
        message = kwargs.get("message", "")
        details = f"Connection {connection_id} state: {current_state.value} -> {to_state.value}"
        if message:
            details += f" | {message}"
        AuditService._log_raw(
            user_id=user_id,
            action="connection_state_changed",
            resource_type="connection",
            resource_id=connection_id,
            details=details,
        )

        return True

    def request_reconnect(self, connection_id: str) -> bool:
        """Trigger a reconnect workflow for a FAILED or DISCONNECTED connection."""
        info = self.get_connection_state(connection_id)
        current = info["state"]
        if current not in (ConnectionState.FAILED, ConnectionState.DISCONNECTED):
            log.warning(
                "Cannot reconnect %s from state %s", connection_id, current.value
            )
            return False
        return self.transition_state(
            connection_id,
            current,
            ConnectionState.POD_SELECTED,
            message="reconnect requested",
        )

    # ── TTL cleanup ──────────────────────────────────────────────────────────

    def schedule_ttl_cleanup(self, interval_seconds: int = 1800):
        """Start a background thread to clean expired connections."""
        if self._ttl_thread is not None and self._ttl_thread.is_alive():
            log.info("TTL cleanup thread already running")
            return

        self._stop_ttl_event.clear()
        self._ttl_thread = threading.Thread(
            target=self._ttl_cleanup_loop,
            args=(interval_seconds,),
            daemon=True,
            name="connection-ttl-cleanup",
        )
        self._ttl_thread.start()
        log.info("TTL cleanup scheduled every %d seconds", interval_seconds)

    def stop_ttl_cleanup(self):
        """Signal the TTL cleanup thread to stop."""
        self._stop_ttl_event.set()
        if self._ttl_thread is not None:
            self._ttl_thread.join(timeout=5)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_current_state_unlocked(self, connection_id: str) -> dict:
        """Get current state info (must hold self._lock)."""
        mem = self._memory_states.get(connection_id)
        if mem is not None:
            return {
                "state": mem["state"],
                "last_ping_at": mem.get("last_ping_at"),
            }

        row = self.db.fetch_one(
            "SELECT status, last_ping_at FROM connections WHERE id = ?",
            (connection_id,),
        )
        if row is not None and row.get("status"):
            return {
                "state": self._state_from_str(row["status"]),
                "last_ping_at": row.get("last_ping_at"),
            }

        return {"state": ConnectionState.DISCONNECTED, "last_ping_at": None}

    def _apply_state_unlocked(
        self, connection_id: str, to_state: ConnectionState, **kwargs: Any
    ):
        """Persist the new state (must hold self._lock)."""
        now = datetime.now(timezone.utc).isoformat()

        if to_state in STABLE_STATES:
            # Persist to DB and evict from memory
            update_data: Dict[str, Any] = {"status": to_state.value, "updated_at": now}
            if to_state == ConnectionState.READY:
                update_data["last_ping_at"] = now
            self.db.update(
                "connections",
                update_data,
                "id = ?",
                (connection_id,),
            )
            self._memory_states.pop(connection_id, None)
        else:
            # Keep in memory only
            self._memory_states[connection_id] = {
                "state": to_state,
                "updated_at": now,
                "last_ping_at": kwargs.get("last_ping_at"),
                "message": kwargs.get("message", ""),
            }

    @staticmethod
    def _is_valid_transition(
        current: ConnectionState, target: ConnectionState
    ) -> bool:
        if target in GLOBAL_TRANSITIONS:
            return True
        allowed = VALID_TRANSITIONS.get(current, set())
        return target in allowed

    @staticmethod
    def _state_from_str(value: str) -> ConnectionState:
        try:
            return ConnectionState(value)
        except ValueError:
            return ConnectionState.DISCONNECTED

    def _ttl_cleanup_loop(self, interval_seconds: int):
        """Background loop that cleans expired connections."""
        while not self._stop_ttl_event.wait(interval_seconds):
            try:
                self._run_ttl_cleanup()
            except Exception as e:
                log.error("TTL cleanup error: %s", e, exc_info=True)

    def _run_ttl_cleanup(self):
        """Mark expired connections as disconnected.

        Each connection can have a custom `ttl_hours` field:
        - ttl_hours = 0: never expires (default, no auto-cleanup)
        - ttl_hours > 0: auto-disconnect after this many hours since last_active_at
        """
        now = datetime.now(timezone.utc)

        # Find connections that should be cleaned up:
        # - status is 'ready' or other active states (not already 'disconnected'/'failed')
        # - ttl_hours > 0 (has a custom expiration)
        # - last_active_at is older than ttl_hours
        rows = self.db.fetch_all(
            "SELECT id, status, last_ping_at, last_active_at, ttl_hours FROM connections "
            "WHERE status NOT IN (?, ?) AND ttl_hours > 0 "
            "AND (last_active_at IS NOT NULL AND last_active_at < ?)",
            (
                ConnectionState.DISCONNECTED.value,
                ConnectionState.FAILED.value,
                (now - timedelta(hours=1)).isoformat(),  # quick pre-filter: skip if active in last hour
            ),
        )

        for row in rows:
            conn_id = row["id"]
            ttl_hours = row.get("ttl_hours", 0)
            last_active = row.get("last_active_at") or row.get("last_ping_at")

            if ttl_hours <= 0 or not last_active:
                continue

            # Parse last_active_at
            try:
                if isinstance(last_active, str):
                    last_active_dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                else:
                    last_active_dt = last_active
                if last_active_dt.tzinfo is None:
                    last_active_dt = last_active_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                log.warning("TTL cleanup: invalid last_active_at for %s: %s", conn_id, last_active)
                continue

            expired_at = last_active_dt + timedelta(hours=ttl_hours)
            if now < expired_at:
                continue  # Not expired yet

            log.info(
                "TTL cleanup: marking %s as disconnected (ttl_hours=%d, last_active=%s)",
                conn_id, ttl_hours, last_active,
            )
            self.db.update(
                "connections",
                {
                    "status": ConnectionState.DISCONNECTED.value,
                    "health_status": "unknown",
                    "updated_at": now.isoformat(),
                },
                "id = ?",
                (conn_id,),
            )
            with self._lock:
                self._memory_states.pop(conn_id, None)

            AuditService._log_raw(
                user_id=None,
                action="connection_ttl_disconnected",
                resource_type="connection",
                resource_id=conn_id,
                details=f"Connection {conn_id} auto-disconnected after {ttl_hours}h TTL",
            )
