#!/usr/bin/env python3
"""
连接 TTL 配置服务 — Phase 5

提供连接 TTL 选项的获取、验证和持久化能力。
TTL（Time To Live）控制连接在最后一次活跃后的自动过期时间。
"""
import logging
from typing import Dict, List, Optional, Tuple

from models.db import Database

log = logging.getLogger(__name__)

# ── 预定义 TTL 选项（小时）─────────────────────────────────────────────
TTL_PRESET_OPTIONS: List[Dict[str, object]] = [
    {"hours": 0, "label": "不过期", "description": "连接不会自动过期，需手动断开"},
    {"hours": 1, "label": "1 小时", "description": "适合临时调试场景"},
    {"hours": 2, "label": "2 小时", "description": "适合短时性能诊断"},
    {"hours": 4, "label": "4 小时", "description": "适合较长时间的排查"},
    {"hours": 8, "label": "8 小时（默认）", "description": "适合一个工作时段"},
    {"hours": 24, "label": "24 小时", "description": "适合跨天持续监控"},
    {"hours": 72, "label": "3 天", "description": "适合长时间运行的场景"},
]

# 最大允许 TTL 小时数
MAX_TTL_HOURS = 720  # 30 天


class ConnectionTTLConfig:
    """连接 TTL 配置服务。

    提供 TTL 预设选项查询、自定义 TTL 验证、以及持久化到数据库的能力。
    """

    def __init__(self, db: Database):
        self.db = db

    # ── 查询 ────────────────────────────────────────────────────────────────

    def get_preset_options(self) -> List[Dict[str, object]]:
        """返回所有预定义的 TTL 选项。"""
        return list(TTL_PRESET_OPTIONS)

    def get_connection_ttl(self, connection_id: str) -> int:
        """获取指定连接当前的 TTL 配置（小时）。

        Args:
            connection_id: 连接 ID

        Returns:
            TTL 小时数，0 表示不过期
        """
        row = self.db.fetch_one(
            "SELECT ttl_hours FROM connections WHERE id = ?",
            (connection_id,),
        )
        if row and row.get("ttl_hours") is not None:
            return int(row["ttl_hours"])
        return 0

    # ── 验证 ────────────────────────────────────────────────────────────────

    def validate_ttl(self, ttl_hours: int) -> Tuple[bool, Optional[str]]:
        """验证 TTL 值是否合法。

        Args:
            ttl_hours: 要设置的 TTL 小时数

        Returns:
            (is_valid, error_message) — valid 时 error_message 为 None
        """
        if not isinstance(ttl_hours, int):
            return False, "TTL 必须为整数"
        if ttl_hours < 0:
            return False, "TTL 不能为负数"
        if ttl_hours > MAX_TTL_HOURS:
            return False, f"TTL 不能超过 {MAX_TTL_HOURS} 小时（{MAX_TTL_HOURS // 24} 天）"
        return True, None

    # ── 持久化 ──────────────────────────────────────────────────────────────

    def set_connection_ttl(self, connection_id: str, ttl_hours: int) -> Dict[str, object]:
        """设置指定连接的 TTL 配置。

        Args:
            connection_id: 连接 ID
            ttl_hours: TTL 小时数（0 = 不过期）

        Returns:
            {"ok": True, "ttl_hours": int, "connection_id": str}
            或 {"ok": False, "error": str}
        """
        # 验证
        valid, err = self.validate_ttl(ttl_hours)
        if not valid:
            return {"ok": False, "error": err}

        # 检查连接是否存在
        row = self.db.fetch_one(
            "SELECT id FROM connections WHERE id = ?",
            (connection_id,),
        )
        if not row:
            return {"ok": False, "error": "连接不存在"}

        # 持久化
        self.db.update(
            "connections",
            {"ttl_hours": ttl_hours, "updated_at": "datetime('now', 'localtime')"},
            "id = ?",
            (connection_id,),
        )

        log.info(
            "[TTLConfig] 连接 %s TTL 已更新为 %dh",
            connection_id,
            ttl_hours,
        )

        return {
            "ok": True,
            "ttl_hours": ttl_hours,
            "connection_id": connection_id,
        }

    # ── 批量操作 ────────────────────────────────────────────────────────────

    def get_connections_ttl_summary(self, user_id: Optional[int] = None) -> List[Dict[str, object]]:
        """获取所有连接的 TTL 配置摘要。

        Args:
            user_id: 可选，仅返回指定用户的连接

        Returns:
            连接 TTL 列表 [{id, cluster_name, pod_name, ttl_hours, health_status}]
        """
        sql = (
            "SELECT id, cluster_name, namespace, pod_name, ttl_hours, health_status, status "
            "FROM connections WHERE status != 'disconnected'"
        )
        params: tuple = ()

        if user_id is not None:
            sql += " AND user_id = ?"
            params = (user_id,)

        sql += " ORDER BY updated_at DESC"

        rows = self.db.fetch_all(sql, params)
        return [
            {
                "id": row.get("id", ""),
                "cluster_name": row.get("cluster_name", ""),
                "namespace": row.get("namespace", ""),
                "pod_name": row.get("pod_name", ""),
                "ttl_hours": row.get("ttl_hours", 0),
                "health_status": row.get("health_status", "unknown"),
                "status": row.get("status", "unknown"),
            }
            for row in (rows or [])
        ]

    def batch_set_ttl(self, connection_ids: List[str], ttl_hours: int) -> Dict[str, object]:
        """批量设置连接 TTL。

        Args:
            connection_ids: 连接 ID 列表
            ttl_hours: TTL 小时数

        Returns:
            {"ok": True, "updated": int, "failed": int}
            或 {"ok": False, "error": str}
        """
        valid, err = self.validate_ttl(ttl_hours)
        if not valid:
            return {"ok": False, "error": err}

        updated = 0
        failed = 0

        for conn_id in connection_ids:
            row = self.db.fetch_one(
                "SELECT id FROM connections WHERE id = ?",
                (conn_id,),
            )
            if not row:
                failed += 1
                continue

            self.db.update(
                "connections",
                {"ttl_hours": ttl_hours, "updated_at": "datetime('now', 'localtime')"},
                "id = ?",
                (conn_id,),
            )
            updated += 1

        log.info(
            "[TTLConfig] 批量设置 TTL=%dh: updated=%d, failed=%d",
            ttl_hours,
            updated,
            failed,
        )

        return {"ok": True, "updated": updated, "failed": failed}
