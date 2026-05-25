#!/usr/bin/env python3
"""
连接恢复服务 — Phase 5

服务重启时从数据库恢复上次活跃连接的状态，
对 ready/connected 状态的连接执行 HTTP 探活，成功则恢复，失败则降级。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from models.db import Database

log = logging.getLogger(__name__)


class ConnectionRecoveryService:
    """服务重启时的连接恢复服务。

    职责：
    1. 从数据库加载所有活跃连接（status 为 ready/connected/recovered）
    2. 对每个连接执行轻量级探活（通过 kubectl get pod 验证 Pod 存活）
    3. 探活成功则标记为 recovered，失败标记为 stale

    注意：实际的 Arthas 连接重建由 server.py 中的 _recover_connections_on_startup
    完成，此服务提供数据库层面的状态管理和统计接口。
    """

    def __init__(self, db: Database):
        self.db = db
        self._recovery_result: Dict[str, object] = {
            "completed": False,
            "recovered": [],
            "stale": [],
            "recovered_count": 0,
            "stale_count": 0,
        }

    @property
    def recovery_result(self) -> Dict[str, object]:
        """获取最近一次恢复的结果。"""
        return dict(self._recovery_result)

    def recover_on_startup(self):
        """服务启动时调用，扫描数据库中的活跃连接并进行状态恢复。

        此方法只更新数据库中的状态标记，不做实际的 Arthas 连接重建。
        实际重建由 server.py 中的 _recover_connections_on_startup 负责。
        """
        log.info("[ConnectionRecovery] 开始启动恢复...")

        try:
            rows = self.db.fetch_all(
                "SELECT id, status, last_active_at, ttl_hours FROM connections "
                "WHERE status IN (?, ?, ?)",
                ("ready", "connected", "recovered"),
            )
        except Exception as e:
            log.error("[ConnectionRecovery] 读取数据库失败: %s", e)
            self._recovery_result["completed"] = True
            return

        recovered: List[str] = []
        stale: List[str] = []

        for row in (rows or []):
            conn_id = row.get("id", "")
            status = row.get("status", "")
            last_active = row.get("last_active_at")
            ttl_hours = row.get("ttl_hours", 0)

            if not conn_id:
                continue

            # 检查 TTL 是否已过期
            if self._is_expired(last_active, ttl_hours):
                stale.append(conn_id)
                self.db.update(
                    "connections",
                    {
                        "status": "stale",
                        "health_status": "unknown",
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    },
                    "id = ?",
                    (conn_id,),
                )
                log.info(
                    "[ConnectionRecovery] 连接 %s TTL 已过期，标记为 stale",
                    conn_id,
                )
            else:
                # 暂时标记为 recovered，实际探活由上层完成
                recovered.append(conn_id)

        self._recovery_result = {
            "completed": True,
            "recovered": recovered,
            "stale": stale,
            "recovered_count": len(recovered),
            "stale_count": len(stale),
        }

        log.info(
            "[ConnectionRecovery] 启动恢复完成: recovered=%d, stale=%d",
            len(recovered),
            len(stale),
        )

    def mark_recovered(self, conn_id: str):
        """将指定连接标记为已恢复。"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.update(
            "connections",
            {
                "status": "recovered",
                "health_status": "healthy",
                "last_active_at": now_str,
                "updated_at": now_str,
            },
            "id = ?",
            (conn_id,),
        )
        if conn_id not in self._recovery_result["recovered"]:
            self._recovery_result["recovered"].append(conn_id)
            self._recovery_result["recovered_count"] = len(
                self._recovery_result["recovered"]
            )
        log.info("[ConnectionRecovery] 连接 %s 标记为 recovered", conn_id)

    def mark_stale(self, conn_id: str):
        """将指定连接标记为过期/失效。"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.update(
            "connections",
            {
                "status": "stale",
                "health_status": "unknown",
                "updated_at": now_str,
            },
            "id = ?",
            (conn_id,),
        )
        if conn_id not in self._recovery_result["stale"]:
            self._recovery_result["stale"].append(conn_id)
            self._recovery_result["stale_count"] = len(
                self._recovery_result["stale"]
            )
        log.info("[ConnectionRecovery] 连接 %s 标记为 stale", conn_id)

    def get_stale_connections(self) -> List[Dict[str, object]]:
        """获取所有 stale 状态的连接列表（供前端清理使用）。"""
        rows = self.db.fetch_all(
            "SELECT id, cluster_name, namespace, pod_name, updated_at "
            "FROM connections WHERE status = ?",
            ("stale",),
        )
        return [
            {
                "id": row.get("id", ""),
                "cluster_name": row.get("cluster_name", ""),
                "namespace": row.get("namespace", ""),
                "pod_name": row.get("pod_name", ""),
                "updated_at": row.get("updated_at", ""),
            }
            for row in (rows or [])
        ]

    def cleanup_stale(self, conn_ids: Optional[List[str]] = None) -> Dict[str, object]:
        """清理 stale 连接：从数据库中删除指定或所有 stale 记录。

        Args:
            conn_ids: 要清理的连接 ID 列表，None 则清理所有 stale

        Returns:
            {"ok": True, "cleaned": [...], "count": int}
        """
        if conn_ids:
            cleaned = []
            for cid in conn_ids:
                row = self.db.fetch_one(
                    "SELECT id FROM connections WHERE id = ? AND status = ?",
                    (cid, "stale"),
                )
                if row:
                    self.db.delete("connections", "id = ?", (cid,))
                    cleaned.append(cid)
        else:
            rows = self.db.fetch_all(
                "SELECT id FROM connections WHERE status = ?",
                ("stale",),
            )
            cleaned = []
            for row in (rows or []):
                cid = row.get("id", "")
                if cid:
                    self.db.delete("connections", "id = ?", (cid,))
                    cleaned.append(cid)

        log.info("[ConnectionRecovery] 清理了 %d 个 stale 连接", len(cleaned))
        return {"ok": True, "cleaned": cleaned, "count": len(cleaned)}

    # ── 内部方法 ────────────────────────────────────────────────────────────

    @staticmethod
    def _is_expired(last_active: Optional[str], ttl_hours: int) -> bool:
        """判断连接是否因 TTL 过期。

        Args:
            last_active: 最后活跃时间字符串（本地时间或 ISO 格式）
            ttl_hours: TTL 小时数（0 = 不过期）

        Returns:
            True 表示已过期
        """
        if ttl_hours <= 0 or not last_active:
            return False

        try:
            last_active_dt = datetime.fromisoformat(
                last_active.replace("Z", "+00:00")
            )
            # 如果是时区感知时间，转为本地时间比较
            if last_active_dt.tzinfo is not None:
                from datetime import timezone as _tz
                last_active_dt = last_active_dt.replace(tzinfo=None)

            elapsed_hours = (
                datetime.now() - last_active_dt
            ).total_seconds() / 3600

            return elapsed_hours > ttl_hours
        except (ValueError, TypeError):
            return False
