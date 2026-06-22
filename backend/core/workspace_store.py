from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

from .connection_pool import WorkspaceState

log = logging.getLogger(__name__)


class WorkspaceStore:
    """per-connection 工作区状态存储，与连接池生命周期解耦

    工作区状态可以比连接存活更久（例如连接断开后保留状态用于重连恢复）。
    ConnectionPool 委托 WorkspaceStore 管理工作区，自身只管理连接生命周期。
    """

    def __init__(self):
        self._workspaces: Dict[str, WorkspaceState] = {}
        self._lock = threading.RLock()

    def get_or_create(self, conn_id: str) -> WorkspaceState:
        with self._lock:
            if conn_id not in self._workspaces:
                self._workspaces[conn_id] = WorkspaceState()
            return self._workspaces[conn_id]

    def get(self, conn_id: str) -> Optional[WorkspaceState]:
        with self._lock:
            return self._workspaces.get(conn_id)

    def remove(self, conn_id: str, preserve: bool = False) -> bool:
        """移除工作区

        Args:
            conn_id: 连接 ID
            preserve: 是否保留（True 则只标记断开连接时不清理，False 则直接删除）

        Returns:
            bool: 是否存在并处理
        """
        with self._lock:
            if conn_id not in self._workspaces:
                return False
            if not preserve:
                del self._workspaces[conn_id]
            return True

    def clear(self):
        with self._lock:
            self._workspaces.clear()

    def list_all(self) -> Dict[str, dict]:
        with self._lock:
            return {
                conn_id: {
                    "active_tab": ws.active_tab.value,
                    "sub_tab": ws.sub_tab,
                    "scroll_positions": dict(ws.scroll_positions),
                }
                for conn_id, ws in self._workspaces.items()
            }

    def count(self) -> int:
        with self._lock:
            return len(self._workspaces)
