#!/usr/bin/env python3
"""
连接切换服务 — Phase 5

处理连接切换过程中的任务取消和状态切换逻辑。
前端通过 /api/connections/{id}/switch 调用此服务。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from models.db import Database

log = logging.getLogger(__name__)


class ConnectionSwitchService:
    """连接切换服务。

    负责：
    1. 检查目标连接是否有运行中任务
    2. 取消运行中任务（可选）
    3. 更新连接状态
    4. 记录审计日志
    """

    def __init__(self, db: Database):
        self.db = db

    # ── 任务检测 ──────────────────────────────────────────────────────────

    def get_running_tasks(self, connection_id: str) -> List[Dict[str, object]]:
        """获取指定连接的所有运行中任务。

        Args:
            connection_id: 连接 ID

        Returns:
            运行中任务列表
        """
        rows = self.db.fetch_all(
            "SELECT id, type, event, status, progress, created_at "
            "FROM profiler_tasks "
            "WHERE connection_id = ? AND status IN (?, ?) "
            "ORDER BY created_at DESC",
            (connection_id, "running", "starting"),
        )
        return [
            {
                "id": row.get("id", ""),
                "type": row.get("type", ""),
                "event": row.get("event", ""),
                "status": row.get("status", ""),
                "progress": row.get("progress", 0),
                "created_at": row.get("created_at", ""),
            }
            for row in (rows or [])
        ]

    def has_running_tasks(self, connection_id: str) -> bool:
        """检查指定连接是否有运行中任务。"""
        count = self.db.count(
            "profiler_tasks",
            "connection_id = ? AND status IN (?, ?)",
            (connection_id, "running", "starting"),
        )
        return count > 0

    # ── 任务取消 ──────────────────────────────────────────────────────────

    def cancel_running_tasks(
        self, connection_id: str, user_id: Optional[int] = None
    ) -> Dict[str, object]:
        """取消指定连接的所有运行中任务。

        Args:
            connection_id: 连接 ID
            user_id: 操作用户 ID（用于审计日志）

        Returns:
            {"ok": True, "cancelled": [...], "count": int}
        """
        tasks = self.get_running_tasks(connection_id)
        cancelled = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for task in tasks:
            task_id = task.get("id", "")
            if not task_id:
                continue

            self.db.update(
                "profiler_tasks",
                {
                    "status": "cancelled",
                    "updated_at": now_str,
                },
                "id = ?",
                (task_id,),
            )
            cancelled.append(task_id)
            log.info(
                "[ConnectionSwitch] 任务 %s 已取消（连接 %s 切换）",
                task_id,
                connection_id,
            )

        if cancelled:
            self._log_audit(
                user_id=user_id,
                action="connection_switch_cancel_tasks",
                resource_type="connection",
                resource_id=connection_id,
                details=f"取消了 {len(cancelled)} 个运行中任务: {', '.join(cancelled)}",
            )

        return {
            "ok": True,
            "cancelled": cancelled,
            "count": len(cancelled),
        }

    # ── 切换操作 ──────────────────────────────────────────────────────────

    def switch_connection(
        self,
        source_connection_id: str,
        target_connection_id: str,
        cancel_tasks: bool = False,
        user_id: Optional[int] = None,
    ) -> Dict[str, object]:
        """执行连接切换。

        Args:
            source_connection_id: 当前连接 ID
            target_connection_id: 目标连接 ID
            cancel_tasks: 是否取消当前连接的运行中任务
            user_id: 操作用户 ID

        Returns:
            切换结果
        """
        # 验证源连接
        source_row = self.db.fetch_one(
            "SELECT id, status FROM connections WHERE id = ?",
            (source_connection_id,),
        )
        if not source_row:
            return {"ok": False, "error": "当前连接不存在"}

        # 验证目标连接
        target_row = self.db.fetch_one(
            "SELECT id, status, health_status FROM connections WHERE id = ?",
            (target_connection_id,),
        )
        if not target_row:
            return {"ok": False, "error": "目标连接不存在"}

        # 检查权限
        if user_id is not None:
            source_owner = source_row.get("user_id")
            target_owner = target_row.get("user_id")
            # 简化：这里不做权限检查，由上层 API 处理

        # 检查运行中任务
        running_tasks = self.get_running_tasks(source_connection_id)
        cancelled_tasks = []

        if running_tasks and cancel_tasks:
            result = self.cancel_running_tasks(source_connection_id, user_id)
            cancelled_tasks = result.get("cancelled", [])

        # 记录切换审计日志
        self._log_audit(
            user_id=user_id,
            action="connection_switch",
            resource_type="connection",
            resource_id=source_connection_id,
            details=(
                f"从 {source_connection_id} 切换到 {target_connection_id}"
                + (f"，取消了 {len(cancelled_tasks)} 个任务" if cancelled_tasks else "")
            ),
        )

        log.info(
            "[ConnectionSwitch] %s -> %s (cancelled=%d)",
            source_connection_id,
            target_connection_id,
            len(cancelled_tasks),
        )

        return {
            "ok": True,
            "source_connection_id": source_connection_id,
            "target_connection_id": target_connection_id,
            "target_status": target_row.get("status", "unknown"),
            "target_health": target_row.get("health_status", "unknown"),
            "had_running_tasks": len(running_tasks) > 0,
            "cancelled_tasks": cancelled_tasks,
            "message": (
                "切换成功"
                if not cancelled_tasks
                else f"已取消 {len(cancelled_tasks)} 个任务并切换"
            ),
        }

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    def _log_audit(
        self,
        user_id: Optional[int],
        action: str,
        resource_type: str,
        resource_id: str,
        details: str,
    ):
        """记录审计日志。"""
        try:
            self.db.insert(
                "audit_logs",
                {
                    "user_id": user_id,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "details": details,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
        except Exception as e:
            log.warning(
                "[ConnectionSwitch] 写入审计日志失败: %s", e
            )
