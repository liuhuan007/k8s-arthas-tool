#!/usr/bin/env python3
"""
健康检查服务 — Phase 5

负责后台线程定期检测所有活跃 Arthas 连接的 HTTP 可达性，
将检查结果写入内存缓存和 health_check_logs 表。
"""
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

from models.db import Database

log = logging.getLogger(__name__)


class HealthCheckService:
    """后台健康检查服务。

    每隔 ``interval_seconds`` 秒扫描 ``connections`` 字典中所有活跃连接，
    通过 Arthas HTTP 端口发送 ``version`` 命令进行探活。

    Attributes:
        db: 数据库实例
        connections: 活跃连接字典 {conn_id: {"conn": ArthasConnection, ...}}
        connections_lock: 连接字典的线程锁
        conn_health: 健康状态缓存 {conn_id: {"status", "last_check_at", "latency_ms"}}
        conn_health_lock: 健康缓存的线程锁
        interval_seconds: 检查间隔（秒）
    """

    def __init__(
        self,
        db: Database,
        connections: Dict[str, dict],
        connections_lock: threading.Lock,
        conn_health: Dict[str, dict],
        conn_health_lock: threading.Lock,
        interval_seconds: Optional[int] = None,
    ):
        self.db = db
        self.connections = connections
        self.connections_lock = connections_lock
        self.conn_health = conn_health
        self.conn_health_lock = conn_health_lock

        # 从配置读取间隔，环境变量可覆盖
        if interval_seconds is None:
            try:
                from backend.config import Config
                interval_seconds = Config.HEALTH_CHECK_INTERVAL_SECONDS
            except Exception:
                interval_seconds = 30
        self.interval_seconds = interval_seconds

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ── 生命周期 ────────────────────────────────────────────────────────────

    def start(self):
        """启动后台健康检查线程。"""
        if self._thread is not None and self._thread.is_alive():
            log.info("[HealthCheckService] 已在运行，跳过重复启动")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="health-check-svc",
        )
        self._thread.start()
        log.info(
            "[HealthCheckService] 后台线程已启动 (间隔 %ds)", self.interval_seconds
        )

    def stop(self):
        """通知后台线程停止。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    # ── 核心循环 ────────────────────────────────────────────────────────────

    def _loop(self):
        """定时循环，每次间隔后执行一轮检查。"""
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self._check_all()
            except Exception as e:
                log.error("[HealthCheckService] 检查出错: %s", e, exc_info=True)

    def _check_all(self):
        """对当前所有活跃连接执行健康检查。"""
        # 1. 快照当前活跃连接
        with self.connections_lock:
            snapshot = {
                cid: entry.copy() for cid, entry in self.connections.items()
            }

        for conn_id, entry in snapshot.items():
            status, latency_ms = self._check_single(entry)

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 2. 更新内存缓存
            with self.conn_health_lock:
                self.conn_health[conn_id] = {
                    "status": status,
                    "last_check_at": now_str,
                    "latency_ms": latency_ms,
                }

            # 3. 更新数据库中的 health_status / last_health_check
            try:
                self.db.update(
                    "connections",
                    {
                        "health_status": status,
                        "last_health_check": now_str,
                    },
                    "id = ?",
                    (conn_id,),
                )
            except Exception as e:
                log.debug(
                    "[HealthCheckService] 更新数据库健康状态失败 %s: %s",
                    conn_id,
                    e,
                )

            # 4. 记录健康检查日志
            try:
                self.db.insert(
                    "health_check_logs",
                    {
                        "connection_id": conn_id,
                        "status": status,
                        "latency_ms": latency_ms,
                        "error_message": None,
                        "checked_at": now_str,
                    },
                )
            except Exception as e:
                log.debug(
                    "[HealthCheckService] 写入健康检查日志失败 %s: %s",
                    conn_id,
                    e,
                )

            log.debug(
                "[HealthCheckService] %s status=%s latency=%sms",
                conn_id,
                status,
                latency_ms,
            )

        # 5. 清理已不在活跃连接中的健康记录
        with self.conn_health_lock:
            stale_keys = [
                k for k in self.conn_health if k not in snapshot
            ]
            for k in stale_keys:
                del self.conn_health[k]

    def _check_single(self, entry: dict) -> tuple:
        """对单个连接执行 HTTP 探活。

        Returns:
            (status, latency_ms) — status 为 "healthy" / "unhealthy" / "unknown"
        """
        conn = entry.get("conn")
        status = "unknown"
        latency_ms: Optional[float] = None

        if conn and hasattr(conn, "http_client") and conn.http_client:
            try:
                start = time.time()
                result = (
                    conn.http_client.exec_once("version")
                    if hasattr(conn.http_client, "exec_once")
                    else None
                )
                elapsed = (time.time() - start) * 1000

                if (
                    result
                    and isinstance(result, dict)
                    and result.get("state") == "SUCCEEDED"
                ):
                    status = "healthy"
                    latency_ms = round(elapsed, 2)
                else:
                    status = "unhealthy"
            except Exception as e:
                log.debug(
                    "[HealthCheckService] 探活失败 %s: %s",
                    entry.get("conn_id", "?"),
                    e,
                )
                status = "unhealthy"
        else:
            status = "unknown"

        return status, latency_ms

    # ── 查询接口 ────────────────────────────────────────────────────────────

    def get_health(self, conn_id: str) -> Optional[dict]:
        """获取指定连接的健康状态缓存。"""
        with self.conn_health_lock:
            return self.conn_health.get(conn_id)

    def get_all_health(self) -> Dict[str, dict]:
        """获取所有连接的健康状态缓存快照。"""
        with self.conn_health_lock:
            return dict(self.conn_health)

    def check_now(self, conn_id: str) -> Optional[dict]:
        """立即对指定连接执行一次健康检查（同步）。
        如果连接不在活跃列表中返回 None。
        """
        with self.connections_lock:
            entry = self.connections.get(conn_id)
        if not entry:
            return None

        status, latency_ms = self._check_single(entry)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.conn_health_lock:
            self.conn_health[conn_id] = {
                "status": status,
                "last_check_at": now_str,
                "latency_ms": latency_ms,
            }

        # 写入数据库
        try:
            self.db.update(
                "connections",
                {
                    "health_status": status,
                    "last_health_check": now_str,
                },
                "id = ?",
                (conn_id,),
            )
            self.db.insert(
                "health_check_logs",
                {
                    "connection_id": conn_id,
                    "status": status,
                    "latency_ms": latency_ms,
                    "error_message": None,
                    "checked_at": now_str,
                },
            )
        except Exception as e:
            log.debug("[HealthCheckService] 同步检查写入DB失败 %s: %s", conn_id, e)

        return {"status": status, "latency_ms": latency_ms, "checked_at": now_str}
