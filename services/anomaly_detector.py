#!/usr/bin/env python3
"""
异常检测引擎 — Phase 6

功能：
  1. P0 预制规则（CPU / 内存 / GC / 线程 / 堆内存）
  2. 后台检测线程每 60 秒执行一次检测
  3. 支持自定义规则（JSON 配置）
  4. 异常事件记录到数据库
  5. WebSocket 实时告警推送
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── 严重级别常量 ──────────────────────────────────────────────────────────────
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"
SEVERITY_EMERGENCY = "emergency"

SEVERITY_ORDER = {
    SEVERITY_INFO: 0,
    SEVERITY_WARNING: 1,
    SEVERITY_CRITICAL: 2,
    SEVERITY_EMERGENCY: 3,
}

# ── 比较运算符 ────────────────────────────────────────────────────────────────
OPERATORS = {
    ">": lambda v, t: v > t,
    ">=": lambda v, t: v >= t,
    "<": lambda v, t: v < t,
    "<=": lambda v, t: v <= t,
    "==": lambda v, t: v == t,
    "!=": lambda v, t: v != t,
}

# ── 默认 P0 规则 ─────────────────────────────────────────────────────────────
DEFAULT_RULES = [
    {
        "name": "CPU使用率过高",
        "metric": "cpu.usagePercent",
        "operator": ">",
        "threshold": 80,
        "duration": 300,
        "severity": SEVERITY_CRITICAL,
        "enabled": True,
        "description": "CPU 使用率 > 80% 持续 5 分钟",
    },
    {
        "name": "内存使用率过高",
        "metric": "memory.usagePercent",
        "operator": ">",
        "threshold": 85,
        "duration": 0,
        "severity": SEVERITY_CRITICAL,
        "enabled": True,
        "description": "内存使用率 > 85%",
    },
    {
        "name": "GC暂停时间过长",
        "metric": "jvm.gcPauseMs",
        "operator": ">",
        "threshold": 500,
        "duration": 0,
        "severity": SEVERITY_WARNING,
        "enabled": True,
        "description": "GC 暂停时间 > 500ms",
    },
    {
        "name": "线程数过多",
        "metric": "jvm.threadCount",
        "operator": ">",
        "threshold": 500,
        "duration": 0,
        "severity": SEVERITY_CRITICAL,
        "enabled": True,
        "description": "线程数 > 500",
    },
    {
        "name": "堆内存使用率过高",
        "metric": "jvm.heapUsagePercent",
        "operator": ">",
        "threshold": 90,
        "duration": 0,
        "severity": SEVERITY_CRITICAL,
        "enabled": True,
        "description": "堆内存使用率 > 90%",
    },
]


def _get_nested_value(obj: Any, path: str) -> Optional[float]:
    """从嵌套字典中通过点号路径获取数值。

    Args:
        obj: 嵌套字典数据（如 Pod 指标快照）
        path: 点号分隔的路径（如 "cpu.usagePercent"）

    Returns:
        浮点数值，若路径无效或值非数值则返回 None
    """
    keys = path.split(".")
    current = obj
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    if current is None:
        return None
    try:
        return float(current)
    except (TypeError, ValueError):
        return None


class AnomalyDetector:
    """异常检测引擎。

    负责：
    - 从数据库加载告警规则
    - 采集最新指标数据（复用已有快照接口）
    - 对每条规则执行阈值检测
    - 将异常事件写入数据库
    - 通过 WebSocket 推送告警通知
    """

    def __init__(self, db=None):
        """初始化异常检测器。

        Args:
            db: Database 实例，延迟传入以避免循环导入
        """
        self._db = db
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval_seconds: int = 60
        # 持续时间检测缓冲：{(pod_key, rule_name): [触发时间戳列表]}
        self._duration_buffers: Dict[str, List[float]] = {}
        self._duration_lock = threading.Lock()
        # 事件去重窗口（秒）：同一 pod + 同一规则在此窗口内不重复告警
        self._dedup_window: int = 300

    def _get_db(self):
        """延迟获取数据库实例。"""
        if self._db is None:
            from models.db import get_db
            self._db = get_db()
        return self._db

    # ── 规则管理 ──────────────────────────────────────────────────────────────

    def get_all_rules(self) -> List[Dict]:
        """获取所有告警规则（数据库 + 内置默认规则合并）。

        Returns:
            规则列表
        """
        db = self._get_db()
        rows = db.fetch_all(
            "SELECT * FROM alert_rules ORDER BY created_at DESC"
        )

        # 如果数据库中没有规则，初始化默认规则
        if not rows:
            self._init_default_rules()
            rows = db.fetch_all(
                "SELECT * FROM alert_rules ORDER BY created_at DESC"
            )

        return rows

    def get_rule_by_id(self, rule_id: int) -> Optional[Dict]:
        """根据 ID 获取单条规则。

        Args:
            rule_id: 规则 ID

        Returns:
            规则字典，不存在则返回 None
        """
        db = self._get_db()
        return db.fetch_one(
            "SELECT * FROM alert_rules WHERE id = ?", (rule_id,)
        )

    def create_rule(self, data: Dict) -> int:
        """创建告警规则。

        Args:
            data: 包含规则字段的字典

        Returns:
            新规则的 ID
        """
        db = self._get_db()
        now = datetime.now().isoformat()
        record = {
            "name": data.get("name", "未命名规则"),
            "metric": data.get("metric", ""),
            "operator": data.get("operator", ">"),
            "threshold": float(data.get("threshold", 0)),
            "duration": int(data.get("duration", 0)),
            "severity": data.get("severity", SEVERITY_WARNING),
            "enabled": 1 if data.get("enabled", True) else 0,
            "description": data.get("description", ""),
            "created_by": data.get("created_by", ""),
            "created_at": now,
        }
        rule_id = db.insert("alert_rules", record)
        log.info("告警规则已创建: id=%s name=%s", rule_id, record["name"])
        return rule_id

    def update_rule(self, rule_id: int, data: Dict) -> bool:
        """更新告警规则。

        Args:
            rule_id: 规则 ID
            data: 待更新的字段

        Returns:
            是否更新成功
        """
        db = self._get_db()
        existing = self.get_rule_by_id(rule_id)
        if not existing:
            return False

        allowed_fields = {
            "name", "metric", "operator", "threshold", "duration",
            "severity", "enabled", "description",
        }
        update_data = {}
        for field in allowed_fields:
            if field in data:
                val = data[field]
                if field == "threshold":
                    val = float(val)
                elif field == "duration":
                    val = int(val)
                elif field == "enabled":
                    val = 1 if val else 0
                update_data[field] = val

        if not update_data:
            return False

        db.update("alert_rules", update_data, "id = ?", (rule_id,))
        log.info("告警规则已更新: id=%s", rule_id)
        return True

    def delete_rule(self, rule_id: int) -> bool:
        """删除告警规则。

        Args:
            rule_id: 规则 ID

        Returns:
            是否删除成功
        """
        db = self._get_db()
        existing = self.get_rule_by_id(rule_id)
        if not existing:
            return False
        db.delete("alert_rules", "id = ?", (rule_id,))
        log.info("告警规则已删除: id=%s", rule_id)
        return True

    # ── 事件管理 ──────────────────────────────────────────────────────────────

    def get_events(
        self,
        cluster: str = "",
        namespace: str = "",
        pod: str = "",
        severity: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> Dict:
        """查询异常事件（支持过滤和分页）。

        Args:
            cluster: 集群名过滤
            namespace: 命名空间过滤
            pod: Pod 名过滤
            severity: 严重级别过滤
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            包含 events 列表和 total 的字典
        """
        db = self._get_db()
        conditions = []
        params: list = []

        if cluster:
            conditions.append("cluster = ?")
            params.append(cluster)
        if namespace:
            conditions.append("namespace = ?")
            params.append(namespace)
        if pod:
            conditions.append("pod = ?")
            params.append(pod)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)

        where = " AND ".join(conditions) if conditions else "1=1"

        total = db.count("anomaly_events", where, tuple(params))
        offset = (max(page, 1) - 1) * page_size

        events = db.fetch_all(
            f"SELECT * FROM anomaly_events WHERE {where} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
            tuple(params) + (page_size, offset),
        )

        return {
            "events": events,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_events_stats(self) -> Dict:
        """获取异常事件统计。

        Returns:
            包含各类统计数据的字典
        """
        db = self._get_db()

        total = db.count("anomaly_events")

        # 按严重级别统计
        severity_stats = {}
        for sev in [SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL, SEVERITY_EMERGENCY]:
            cnt = db.count("anomaly_events", "severity = ?", (sev,))
            severity_stats[sev] = cnt

        # 最近 24 小时事件数
        day_ago = (datetime.now() - timedelta(hours=24)).isoformat()
        recent = db.count(
            "anomaly_events", "created_at >= ?", (day_ago,)
        )

        # 按集群统计
        cluster_rows = db.fetch_all(
            "SELECT cluster, COUNT(*) as cnt FROM anomaly_events "
            "GROUP BY cluster ORDER BY cnt DESC"
        )

        return {
            "total": total,
            "recent_24h": recent,
            "by_severity": severity_stats,
            "by_cluster": cluster_rows,
        }

    def delete_event(self, event_id: int) -> bool:
        """删除异常事件。

        Args:
            event_id: 事件 ID

        Returns:
            是否删除成功
        """
        db = self._get_db()
        existing = db.fetch_one(
            "SELECT id FROM anomaly_events WHERE id = ?", (event_id,)
        )
        if not existing:
            return False
        db.delete("anomaly_events", "id = ?", (event_id,))
        log.info("异常事件已删除: id=%s", event_id)
        return True

    # ── 通知管理 ──────────────────────────────────────────────────────────────

    def get_notifications(self, user_id: int = 0, unread_only: bool = False) -> List[Dict]:
        """获取通知列表。

        Args:
            user_id: 用户 ID 过滤（0 表示全部）
            unread_only: 是否只返回未读通知

        Returns:
            通知列表
        """
        db = self._get_db()
        conditions = []
        params: list = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if unread_only:
            conditions.append("is_read = 0")

        where = " AND ".join(conditions) if conditions else "1=1"

        return db.fetch_all(
            f"SELECT * FROM alert_notifications WHERE {where} "
            f"ORDER BY created_at DESC LIMIT 100",
            tuple(params),
        )

    def mark_notification_read(self, notification_id: int) -> bool:
        """标记通知为已读。

        Args:
            notification_id: 通知 ID

        Returns:
            是否更新成功
        """
        db = self._get_db()
        existing = db.fetch_one(
            "SELECT id FROM alert_notifications WHERE id = ?",
            (notification_id,),
        )
        if not existing:
            return False
        db.update(
            "alert_notifications",
            {"is_read": 1},
            "id = ?",
            (notification_id,),
        )
        return True

    def get_unread_count(self, user_id: int = 0) -> int:
        """获取未读通知数量。

        Args:
            user_id: 用户 ID（0 表示全部）

        Returns:
            未读通知数
        """
        db = self._get_db()
        if user_id:
            return db.count(
                "alert_notifications",
                "is_read = 0 AND user_id = ?",
                (user_id,),
            )
        return db.count("alert_notifications", "is_read = 0")

    # ── 检测引擎 ──────────────────────────────────────────────────────────────

    def start(self, interval_seconds: int = 60):
        """启动后台检测线程。

        Args:
            interval_seconds: 检测间隔（秒），默认 60
        """
        if self._running:
            log.warning("异常检测引擎已在运行")
            return

        self._interval_seconds = interval_seconds
        self._running = True
        self._thread = threading.Thread(
            target=self._detection_loop,
            name="anomaly-detector",
            daemon=True,
        )
        self._thread.start()
        log.info("异常检测引擎已启动 (间隔 %ds)", interval_seconds)

    def stop(self):
        """停止后台检测线程。"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        log.info("异常检测引擎已停止")

    def _detection_loop(self):
        """后台检测主循环。"""
        log.info("异常检测循环开始")
        while self._running:
            try:
                self._run_detection_cycle()
            except Exception as e:
                log.error("异常检测周期执行失败: %s", e, exc_info=True)
            # 分段 sleep 以便快速响应 stop 信号
            for _ in range(self._interval_seconds):
                if not self._running:
                    break
                time.sleep(1)
        log.info("异常检测循环结束")

    def _run_detection_cycle(self):
        """执行一次完整的检测周期：加载规则 → 采集指标 → 检测 → 记录事件。"""
        rules = self.get_all_rules()
        enabled_rules = [r for r in rules if r.get("enabled")]

        if not enabled_rules:
            return

        # 获取所有活跃连接对应的 Pod 指标
        metrics_samples = self._collect_latest_metrics()
        if not metrics_samples:
            return

        for sample in metrics_samples:
            self._check_sample(sample, enabled_rules)

    def _collect_latest_metrics(self) -> List[Dict]:
        """收集最新的 Pod 指标数据。

        优先从内存缓冲读取，若无缓冲数据则尝试实时采集。

        Returns:
            指标样本列表，每个包含 pod_key, cluster, namespace, pod, metrics
        """
        samples = []
        try:
            from backend.pod_monitor import _metrics_history, _metrics_lock

            with _metrics_lock:
                for key, history in _metrics_history.items():
                    if not history:
                        continue
                    latest = history[-1]
                    parts = key.split("/", 2)
                    if len(parts) != 3:
                        continue
                    cluster, namespace, pod = parts

                    # 从 latest 中提取指标
                    top = latest.get("top_metrics", {})
                    container = latest.get("container_metrics", {})

                    metrics = {
                        "cpu.usagePercent": top.get("cpu_percent", 0),
                        "memory.usagePercent": top.get("memory_percent", 0),
                        "jvm.gcPauseMs": container.get("jvm", {}).get("gc_pause_ms", 0),
                        "jvm.threadCount": container.get("jvm", {}).get("thread_count", 0),
                        "jvm.heapUsagePercent": container.get("jvm", {}).get("heap_usage_percent", 0),
                        "jvm.heapUsed": container.get("jvm", {}).get("heap_used", 0),
                        "jvm.heapMax": container.get("jvm", {}).get("heap_max", 0),
                        "disk.usePercent": float(
                            container.get("disk_use_pct", "0").replace("%", "")
                        ) if container.get("disk_use_pct") else 0,
                    }

                    samples.append({
                        "pod_key": key,
                        "cluster": cluster,
                        "namespace": namespace,
                        "pod": pod,
                        "metrics": metrics,
                        "raw": latest,
                    })
        except ImportError:
            log.debug("pod_monitor 模块不可用，跳过指标采集")
        except Exception as e:
            log.warning("采集指标数据失败: %s", e)

        return samples

    def _check_sample(self, sample: Dict, rules: List[Dict]):
        """对单个 Pod 样本执行所有规则的检测。

        Args:
            sample: 指标样本
            rules: 启用的规则列表
        """
        metrics = sample.get("metrics", {})
        pod_key = sample.get("pod_key", "")
        cluster = sample.get("cluster", "")
        namespace = sample.get("namespace", "")
        pod = sample.get("pod", "")

        for rule in rules:
            rule_name = rule.get("name", "")
            metric_path = rule.get("metric", "")
            operator_str = rule.get("operator", ">")
            threshold = float(rule.get("threshold", 0))
            duration = int(rule.get("duration", 0))
            severity = rule.get("severity", SEVERITY_WARNING)

            value = _get_nested_value(metrics, metric_path)
            if value is None:
                continue

            op_func = OPERATORS.get(operator_str)
            if not op_func:
                log.warning("未知运算符: %s", operator_str)
                continue

            triggered = op_func(value, threshold)

            # 持续时间检测
            if duration > 0:
                buf_key = f"{pod_key}:{rule_name}"
                now = time.time()
                with self._duration_lock:
                    if triggered:
                        if buf_key not in self._duration_buffers:
                            self._duration_buffers[buf_key] = []
                        self._duration_buffers[buf_key].append(now)
                        # 清理过期条目
                        self._duration_buffers[buf_key] = [
                            t for t in self._duration_buffers[buf_key]
                            if now - t <= duration
                        ]
                        triggered = len(self._duration_buffers[buf_key]) >= (
                            duration / self._interval_seconds
                        )
                    else:
                        self._duration_buffers.pop(buf_key, None)

            if triggered:
                # 去重检查
                if self._is_duplicate(pod_key, rule_name):
                    continue

                message = (
                    f"{rule_name}: {metric_path} = {value:.2f} "
                    f"(阈值 {operator_str} {threshold})"
                )
                if duration > 0:
                    message += f" 持续 {duration}s"

                self._record_event(
                    cluster=cluster,
                    namespace=namespace,
                    pod=pod,
                    rule_name=rule_name,
                    severity=severity,
                    message=message,
                    metrics_json=sample.get("raw", {}),
                )

    def _is_duplicate(self, pod_key: str, rule_name: str) -> bool:
        """检查是否在去重窗口内已有相同事件。

        Args:
            pod_key: Pod 标识 (cluster/namespace/pod)
            rule_name: 规则名称

        Returns:
            是否为重复事件
        """
        db = self._get_db()
        since = (
            datetime.now() - timedelta(seconds=self._dedup_window)
        ).isoformat()

        existing = db.fetch_one(
            "SELECT id FROM anomaly_events "
            "WHERE pod = ? AND rule_name = ? AND created_at >= ? "
            "ORDER BY created_at DESC LIMIT 1",
            (pod_key.split("/", 2)[-1] if "/" in pod_key else pod_key,
             rule_name, since),
        )
        return existing is not None

    def _record_event(
        self,
        cluster: str,
        namespace: str,
        pod: str,
        rule_name: str,
        severity: str,
        message: str,
        metrics_json: Dict,
    ):
        """记录异常事件到数据库并推送通知。

        Args:
            cluster: 集群名
            namespace: 命名空间
            pod: Pod 名
            rule_name: 触发的规则名
            severity: 严重级别
            message: 事件描述
            metrics_json: 当时的完整指标数据
        """
        db = self._get_db()
        now = datetime.now().isoformat()

        event_id = db.insert("anomaly_events", {
            "cluster": cluster,
            "namespace": namespace,
            "pod": pod,
            "rule_name": rule_name,
            "severity": severity,
            "message": message,
            "metrics_json": json.dumps(metrics_json, ensure_ascii=False, default=str),
            "created_at": now,
        })

        log.info(
            "异常事件已记录: [%s] %s/%s/%s - %s",
            severity.upper(), cluster, namespace, pod, rule_name,
        )

        # 创建通知记录
        self._create_notification(
            event_id=event_id,
            cluster=cluster,
            namespace=namespace,
            pod=pod,
            rule_name=rule_name,
            severity=severity,
            message=message,
        )

        # 尝试 WebSocket 推送
        self._push_ws_alert(
            event_id=event_id,
            cluster=cluster,
            namespace=namespace,
            pod=pod,
            rule_name=rule_name,
            severity=severity,
            message=message,
        )

    def _create_notification(
        self,
        event_id: int,
        cluster: str,
        namespace: str,
        pod: str,
        rule_name: str,
        severity: str,
        message: str,
    ):
        """为所有活跃用户创建通知记录。

        Args:
            event_id: 关联的事件 ID
            cluster: 集群名
            namespace: 命名空间
            pod: Pod 名
            rule_name: 规则名称
            severity: 严重级别
            message: 通知消息
        """
        db = self._get_db()
        now = datetime.now().isoformat()

        try:
            users = db.fetch_all(
                "SELECT id FROM users WHERE status = 'active'"
            )
            for user in users:
                db.insert("alert_notifications", {
                    "user_id": user["id"],
                    "event_id": event_id,
                    "title": f"[{severity.upper()}] {rule_name}",
                    "message": message,
                    "cluster": cluster,
                    "namespace": namespace,
                    "pod": pod,
                    "severity": severity,
                    "is_read": 0,
                    "created_at": now,
                })
        except Exception as e:
            log.warning("创建通知记录失败: %s", e)

    def _push_ws_alert(
        self,
        event_id: int,
        cluster: str,
        namespace: str,
        pod: str,
        rule_name: str,
        severity: str,
        message: str,
    ):
        """通过 WebSocket 推送告警。

        Args:
            event_id: 事件 ID
            cluster: 集群名
            namespace: 命名空间
            pod: Pod 名
            rule_name: 规则名称
            severity: 严重级别
            message: 告警消息
        """
        try:
            from backend.websocket_server import broadcast_to_all

            alert_payload = {
                "type": "anomaly_alert",
                "event_id": event_id,
                "cluster": cluster,
                "namespace": namespace,
                "pod": pod,
                "rule_name": rule_name,
                "severity": severity,
                "message": message,
                "timestamp": int(time.time()),
            }
            broadcast_to_all(alert_payload)
        except ImportError:
            pass
        except Exception as e:
            log.debug("WebSocket 推送失败: %s", e)

    # ── 数据库初始化 ──────────────────────────────────────────────────────────

    def init_tables(self):
        """初始化异常检测相关的数据库表。"""
        db = self._get_db()
        with db.connection() as conn:
            cursor = conn.cursor()

            # anomaly_events 表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS anomaly_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster TEXT NOT NULL DEFAULT '',
                    namespace TEXT NOT NULL DEFAULT '',
                    pod TEXT NOT NULL DEFAULT '',
                    rule_name TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL DEFAULT 'warning',
                    message TEXT NOT NULL DEFAULT '',
                    metrics_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_anomaly_events_cluster "
                "ON anomaly_events(cluster)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_anomaly_events_severity "
                "ON anomaly_events(severity)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_anomaly_events_created "
                "ON anomaly_events(created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_anomaly_events_pod_rule "
                "ON anomaly_events(pod, rule_name, created_at DESC)"
            )
            log.info("数据库表 anomaly_events 已初始化")

            # alert_rules 表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alert_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL DEFAULT '',
                    metric TEXT NOT NULL DEFAULT '',
                    operator TEXT NOT NULL DEFAULT '>',
                    threshold REAL NOT NULL DEFAULT 0,
                    duration INTEGER NOT NULL DEFAULT 0,
                    severity TEXT NOT NULL DEFAULT 'warning',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    description TEXT DEFAULT '',
                    created_by TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled "
                "ON alert_rules(enabled)"
            )
            log.info("数据库表 alert_rules 已初始化")

            # alert_notifications 表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alert_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    event_id INTEGER,
                    title TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    cluster TEXT DEFAULT '',
                    namespace TEXT DEFAULT '',
                    pod TEXT DEFAULT '',
                    severity TEXT NOT NULL DEFAULT 'warning',
                    is_read INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (event_id) REFERENCES anomaly_events(id) ON DELETE SET NULL
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_alert_notif_user_read "
                "ON alert_notifications(user_id, is_read)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_alert_notif_created "
                "ON alert_notifications(created_at DESC)"
            )
            log.info("数据库表 alert_notifications 已初始化")

    def _init_default_rules(self):
        """初始化内置 P0 默认规则。"""
        db = self._get_db()
        now = datetime.now().isoformat()
        for rule_data in DEFAULT_RULES:
            db.insert("alert_rules", {
                "name": rule_data["name"],
                "metric": rule_data["metric"],
                "operator": rule_data["operator"],
                "threshold": float(rule_data["threshold"]),
                "duration": int(rule_data["duration"]),
                "severity": rule_data["severity"],
                "enabled": 1,
                "description": rule_data.get("description", ""),
                "created_by": "system",
                "created_at": now,
            })
        log.info("已初始化 %d 条默认告警规则", len(DEFAULT_RULES))


# ── 单例 ──────────────────────────────────────────────────────────────────────

_detector_instance: Optional[AnomalyDetector] = None
_detector_lock = threading.Lock()


def get_anomaly_detector(db=None) -> AnomalyDetector:
    """获取 AnomalyDetector 单例。

    Args:
        db: 可选的 Database 实例，首次调用时设置

    Returns:
        AnomalyDetector 单例
    """
    global _detector_instance
    if _detector_instance is None:
        with _detector_lock:
            if _detector_instance is None:
                _detector_instance = AnomalyDetector(db=db)
    return _detector_instance
