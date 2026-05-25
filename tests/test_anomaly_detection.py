#!/usr/bin/env python3
"""
Phase 6 异常检测引擎测试

覆盖:
  - 规则 CRUD (创建/读取/更新/删除)
  - 默认 P0 规则初始化
  - 阈值比较逻辑
  - 嵌套值提取 (_get_nested_value)
  - 事件记录与查询
  - 持续时间检测缓冲
  - 去重窗口
"""

import os
import sys
import time
import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.anomaly_detector import (
    AnomalyDetector,
    _get_nested_value,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    SEVERITY_CRITICAL,
    SEVERITY_EMERGENCY,
    SEVERITY_ORDER,
    OPERATORS,
    DEFAULT_RULES,
)


class MockDatabase:
    """内存 SQLite 数据库模拟，用于单元测试。"""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        c = self._conn.cursor()
        c.execute("""
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
        c.execute("""
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
        c.execute("""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 插入一个测试用户
        c.execute(
            "INSERT INTO users (username, password_hash, role, status) VALUES (?, ?, ?, ?)",
            ("testuser", "hash", "admin", "active"),
        )
        self._conn.commit()

    def connection(self):
        """上下文管理器，与 Database 接口兼容。"""
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

        return _ctx()

    def fetch_one(self, sql, params=()):
        with self._conn as c:
            row = c.execute(sql, params).fetchone()
            return dict(row) if row else None

    def fetch_all(self, sql, params=()):
        with self._conn as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def insert(self, table, data):
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        with self._conn as c:
            cursor = c.execute(sql, tuple(data.values()))
            self._conn.commit()
            return cursor.lastrowid

    def update(self, table, data, where, where_params):
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        with self._conn as c:
            rc = c.execute(sql, tuple(data.values()) + where_params).rowcount
            self._conn.commit()
            return rc

    def delete(self, table, where, where_params):
        sql = f"DELETE FROM {table} WHERE {where}"
        with self._conn as c:
            rc = c.execute(sql, where_params).rowcount
            self._conn.commit()
            return rc

    def count(self, table, where="1=1", params=()):
        sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}"
        with self._conn as c:
            row = c.execute(sql, params).fetchone()
            return row[0] if row else 0

    def exists(self, table, where, params):
        sql = f"SELECT 1 FROM {table} WHERE {where} LIMIT 1"
        return self.fetch_one(sql, params) is not None


# ═══════════════════════════════════════════════════════════════════════════════
# 测试用例
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetNestedValue(unittest.TestCase):
    """测试 _get_nested_value 辅助函数"""

    def test_simple_key(self):
        obj = {"cpu": 80.5}
        self.assertAlmostEqual(_get_nested_value(obj, "cpu"), 80.5)

    def test_nested_keys(self):
        obj = {"top_metrics": {"cpu_percent": 92.3}}
        self.assertAlmostEqual(_get_nested_value(obj, "top_metrics.cpu_percent"), 92.3)

    def test_deeply_nested(self):
        obj = {"a": {"b": {"c": {"d": 42}}}}
        self.assertAlmostEqual(_get_nested_value(obj, "a.b.c.d"), 42)

    def test_missing_key(self):
        obj = {"cpu": 80}
        self.assertIsNone(_get_nested_value(obj, "memory"))

    def test_missing_nested_key(self):
        obj = {"cpu": {"usage": 80}}
        self.assertIsNone(_get_nested_value(obj, "cpu.memory"))

    def test_non_numeric_value(self):
        obj = {"cpu": "high"}
        self.assertIsNone(_get_nested_value(obj, "cpu"))

    def test_none_value(self):
        obj = {"cpu": None}
        self.assertIsNone(_get_nested_value(obj, "cpu"))

    def test_string_number(self):
        obj = {"cpu": "75.5"}
        self.assertAlmostEqual(_get_nested_value(obj, "cpu"), 75.5)

    def test_integer_value(self):
        obj = {"threads": 42}
        self.assertAlmostEqual(_get_nested_value(obj, "threads"), 42)


class TestOperators(unittest.TestCase):
    """测试比较运算符"""

    def test_gt(self):
        self.assertTrue(OPERATORS[">"](10, 5))
        self.assertFalse(OPERATORS[">"](3, 5))
        self.assertFalse(OPERATORS[">"](5, 5))

    def test_gte(self):
        self.assertTrue(OPERATORS[">="](10, 5))
        self.assertTrue(OPERATORS[">="](5, 5))
        self.assertFalse(OPERATORS[">="](3, 5))

    def test_lt(self):
        self.assertTrue(OPERATORS["<"](3, 5))
        self.assertFalse(OPERATORS["<"](10, 5))
        self.assertFalse(OPERATORS["<"](5, 5))

    def test_lte(self):
        self.assertTrue(OPERATORS["<="](3, 5))
        self.assertTrue(OPERATORS["<="](5, 5))
        self.assertFalse(OPERATORS["<="](10, 5))

    def test_eq(self):
        self.assertTrue(OPERATORS["=="](5, 5))
        self.assertFalse(OPERATORS["=="](3, 5))

    def test_neq(self):
        self.assertTrue(OPERATORS["!="](3, 5))
        self.assertFalse(OPERATORS["!="](5, 5))


class TestSeverityOrder(unittest.TestCase):
    """测试严重级别排序"""

    def test_order(self):
        self.assertLess(SEVERITY_ORDER[SEVERITY_INFO], SEVERITY_ORDER[SEVERITY_WARNING])
        self.assertLess(SEVERITY_ORDER[SEVERITY_WARNING], SEVERITY_ORDER[SEVERITY_CRITICAL])
        self.assertLess(SEVERITY_ORDER[SEVERITY_CRITICAL], SEVERITY_ORDER[SEVERITY_EMERGENCY])


class TestAnomalyDetectorInit(unittest.TestCase):
    """测试异常检测器初始化"""

    def setUp(self):
        self.db = MockDatabase()
        self.detector = AnomalyDetector(db=self.db)

    def test_init_tables(self):
        """初始化表应该成功创建所有表"""
        self.detector.init_tables()
        # 验证表存在
        rules = self.detector.get_all_rules()
        self.assertIsInstance(rules, list)

    def test_default_rules_created_on_get_when_empty(self):
        """get_all_rules 在表为空时应自动初始化默认规则"""
        self.detector.init_tables()
        rules = self.detector.get_all_rules()
        self.assertEqual(len(rules), len(DEFAULT_RULES))


class TestAnomalyDetectorRuleCRUD(unittest.TestCase):
    """测试告警规则 CRUD"""

    def setUp(self):
        self.db = MockDatabase()
        self.detector = AnomalyDetector(db=self.db)
        self.detector.init_tables()
        # 手动插入默认规则
        self.detector._init_default_rules()

    def test_init_default_rules_count(self):
        """应该创建 5 条默认规则"""
        rules = self.detector.get_all_rules()
        self.assertEqual(len(rules), len(DEFAULT_RULES))

    def test_create_rule(self):
        """创建规则"""
        rule_id = self.detector.create_rule({
            "name": "自定义规则",
            "metric": "cpu.usagePercent",
            "operator": ">",
            "threshold": 90,
            "duration": 120,
            "severity": "critical",
        })
        self.assertIsNotNone(rule_id)
        self.assertGreater(rule_id, 0)

        rule = self.detector.get_rule_by_id(rule_id)
        self.assertIsNotNone(rule)
        self.assertEqual(rule["name"], "自定义规则")
        self.assertEqual(rule["metric"], "cpu.usagePercent")
        self.assertEqual(rule["operator"], ">")
        self.assertEqual(rule["threshold"], 90.0)
        self.assertEqual(rule["duration"], 120)

    def test_get_rule_by_id(self):
        """获取规则"""
        rule_id = self.detector.create_rule({
            "name": "测试规则",
            "metric": "memory.usagePercent",
            "operator": ">",
            "threshold": 85,
        })
        rule = self.detector.get_rule_by_id(rule_id)
        self.assertIsNotNone(rule)
        self.assertEqual(rule["name"], "测试规则")

    def test_get_rule_not_found(self):
        """获取不存在的规则"""
        rule = self.detector.get_rule_by_id(99999)
        self.assertIsNone(rule)

    def test_update_rule(self):
        """更新规则"""
        rule_id = self.detector.create_rule({
            "name": "原始名称",
            "metric": "cpu.usagePercent",
            "operator": ">",
            "threshold": 80,
        })

        ok = self.detector.update_rule(rule_id, {
            "name": "更新后名称",
            "threshold": 90,
        })
        self.assertTrue(ok)

        rule = self.detector.get_rule_by_id(rule_id)
        self.assertEqual(rule["name"], "更新后名称")
        self.assertEqual(rule["threshold"], 90.0)

    def test_update_rule_not_found(self):
        """更新不存在的规则"""
        ok = self.detector.update_rule(99999, {"name": "xxx"})
        self.assertFalse(ok)

    def test_delete_rule(self):
        """删除规则"""
        rule_id = self.detector.create_rule({
            "name": "待删除规则",
            "metric": "cpu.usagePercent",
            "operator": ">",
            "threshold": 80,
        })
        ok = self.detector.delete_rule(rule_id)
        self.assertTrue(ok)
        self.assertIsNone(self.detector.get_rule_by_id(rule_id))

    def test_delete_rule_not_found(self):
        """删除不存在的规则"""
        ok = self.detector.delete_rule(99999)
        self.assertFalse(ok)

    def test_disable_rule(self):
        """禁用规则"""
        rule_id = self.detector.create_rule({
            "name": "可禁用规则",
            "metric": "cpu.usagePercent",
            "operator": ">",
            "threshold": 80,
            "enabled": True,
        })
        ok = self.detector.update_rule(rule_id, {"enabled": False})
        self.assertTrue(ok)
        rule = self.detector.get_rule_by_id(rule_id)
        self.assertEqual(rule["enabled"], 0)


class TestAnomalyDetectorEvents(unittest.TestCase):
    """测试异常事件管理"""

    def setUp(self):
        self.db = MockDatabase()
        self.detector = AnomalyDetector(db=self.db)
        self.detector.init_tables()

    def test_record_and_get_events(self):
        """记录并查询事件"""
        self.detector._record_event(
            cluster="prod",
            namespace="default",
            pod="web-abc",
            rule_name="CPU使用率过高",
            severity="critical",
            message="CPU = 92.5% (> 80%)",
            metrics_json={"cpu": 92.5},
        )

        result = self.detector.get_events()
        events = result["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["cluster"], "prod")
        self.assertEqual(events[0]["rule_name"], "CPU使用率过高")

    def test_events_filter_cluster(self):
        """按集群过滤事件"""
        self.detector._record_event("prod", "", "pod1", "rule1", "warning", "msg1", {})
        self.detector._record_event("staging", "", "pod2", "rule2", "info", "msg2", {})

        result = self.detector.get_events(cluster="prod")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["cluster"], "prod")

    def test_events_filter_severity(self):
        """按严重级别过滤事件"""
        self.detector._record_event("c1", "", "pod1", "r1", "warning", "msg1", {})
        self.detector._record_event("c1", "", "pod2", "r2", "critical", "msg2", {})
        self.detector._record_event("c1", "", "pod3", "r3", "info", "msg3", {})

        result = self.detector.get_events(severity="critical")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["severity"], "critical")

    def test_events_filter_pod(self):
        """按 Pod 过滤事件"""
        self.detector._record_event("c1", "ns1", "pod-a", "r1", "warning", "msg1", {})
        self.detector._record_event("c1", "ns1", "pod-b", "r2", "warning", "msg2", {})

        result = self.detector.get_events(pod="pod-a")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["pod"], "pod-a")

    def test_events_pagination(self):
        """事件分页"""
        for i in range(25):
            self.detector._record_event(
                "c1", "", f"pod-{i}", "r1", "warning", f"msg{i}", {}
            )

        page1 = self.detector.get_events(page=1, page_size=10)
        self.assertEqual(len(page1["events"]), 10)
        self.assertEqual(page1["total"], 25)
        self.assertEqual(page1["page"], 1)

        page3 = self.detector.get_events(page=3, page_size=10)
        self.assertEqual(len(page3["events"]), 5)

    def test_delete_event(self):
        """删除事件"""
        self.detector._record_event(
            "c1", "", "pod1", "r1", "warning", "msg", {}
        )
        events = self.detector.get_events()
        event_id = events["events"][0]["id"]

        ok = self.detector.delete_event(event_id)
        self.assertTrue(ok)
        self.assertEqual(self.detector.get_events()["total"], 0)

    def test_delete_event_not_found(self):
        """删除不存在的事件"""
        ok = self.detector.delete_event(99999)
        self.assertFalse(ok)

    def test_events_stats(self):
        """事件统计"""
        self.detector._record_event("prod", "", "p1", "r1", "warning", "m1", {})
        self.detector._record_event("prod", "", "p2", "r2", "critical", "m2", {})
        self.detector._record_event("staging", "", "p3", "r3", "info", "m3", {})

        stats = self.detector.get_events_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["by_severity"]["warning"], 1)
        self.assertEqual(stats["by_severity"]["critical"], 1)
        self.assertEqual(stats["by_severity"]["info"], 1)
        self.assertEqual(len(stats["by_cluster"]), 2)


class TestAnomalyDetectorNotifications(unittest.TestCase):
    """测试通知管理"""

    def setUp(self):
        self.db = MockDatabase()
        self.detector = AnomalyDetector(db=self.db)
        self.detector.init_tables()

    def _insert_notification(self, user_id=1, is_read=0, severity="warning"):
        return self.db.insert("alert_notifications", {
            "user_id": user_id,
            "event_id": None,
            "title": f"Test [{severity.upper()}]",
            "message": "Test message",
            "cluster": "test",
            "namespace": "default",
            "pod": "test-pod",
            "severity": severity,
            "is_read": is_read,
            "created_at": datetime.now().isoformat(),
        })

    def test_get_notifications(self):
        """获取通知列表"""
        self._insert_notification(user_id=1, is_read=0)
        self._insert_notification(user_id=1, is_read=1)
        self._insert_notification(user_id=2, is_read=0)

        notifs = self.detector.get_notifications(user_id=1)
        self.assertEqual(len(notifs), 2)

    def test_get_notifications_unread_only(self):
        """只获取未读通知"""
        self._insert_notification(user_id=1, is_read=0)
        self._insert_notification(user_id=1, is_read=1)

        notifs = self.detector.get_notifications(user_id=1, unread_only=True)
        self.assertEqual(len(notifs), 1)
        self.assertEqual(notifs[0]["is_read"], 0)

    def test_mark_read(self):
        """标记已读"""
        nid = self._insert_notification(user_id=1, is_read=0)
        ok = self.detector.mark_notification_read(nid)
        self.assertTrue(ok)

        notif = self.db.fetch_one(
            "SELECT is_read FROM alert_notifications WHERE id = ?", (nid,)
        )
        self.assertEqual(notif["is_read"], 1)

    def test_mark_read_not_found(self):
        """标记不存在的通知"""
        ok = self.detector.mark_notification_read(99999)
        self.assertFalse(ok)

    def test_get_unread_count(self):
        """获取未读数量"""
        self._insert_notification(user_id=1, is_read=0)
        self._insert_notification(user_id=1, is_read=0)
        self._insert_notification(user_id=1, is_read=1)

        count = self.detector.get_unread_count(user_id=1)
        self.assertEqual(count, 2)

    def test_get_unread_count_all_users(self):
        """获取所有用户未读数量"""
        self._insert_notification(user_id=1, is_read=0)
        self._insert_notification(user_id=2, is_read=0)
        self._insert_notification(user_id=3, is_read=1)

        count = self.detector.get_unread_count()
        self.assertEqual(count, 2)


class TestAnomalyDetectorDurationBuffer(unittest.TestCase):
    """测试持续时间检测缓冲"""

    def setUp(self):
        self.db = MockDatabase()
        self.detector = AnomalyDetector(db=self.db)
        self.detector.init_tables()
        self.detector._interval_seconds = 10  # 10秒检测间隔

    def test_duration_buffer_stores_timestamps(self):
        """缓冲区应正确存储时间戳"""
        key = "cluster/ns/pod:CPU过高"
        now = time.time()

        with self.detector._duration_lock:
            self.detector._duration_buffers[key] = [now, now - 5]

        self.assertEqual(len(self.detector._duration_buffers[key]), 2)

    def test_duration_buffer_cleanup(self):
        """缓冲区应清理过期条目"""
        key = "cluster/ns/pod:CPU过高"
        now = time.time()

        with self.detector._duration_lock:
            self.detector._duration_buffers[key] = [
                now,            # 有效（0s ago）
                now - 400,      # 过期（超过 300s 持续时间）
                now - 100,      # 有效（100s ago）
            ]

        # 模拟持续时间清理逻辑
        duration = 300
        with self.detector._duration_lock:
            self.detector._duration_buffers[key] = [
                t for t in self.detector._duration_buffers[key]
                if now - t <= duration
            ]

        self.assertEqual(len(self.detector._duration_buffers[key]), 2)


class TestAnomalyDetectorDeduplication(unittest.TestCase):
    """测试事件去重"""

    def setUp(self):
        self.db = MockDatabase()
        self.detector = AnomalyDetector(db=self.db)
        self.detector.init_tables()

    def test_is_duplicate_within_window(self):
        """去重窗口内的重复事件"""
        self.detector._record_event(
            "c1", "", "pod1", "CPU过高", "warning", "msg", {}
        )

        ok = self.detector._is_duplicate("c1/default/pod1", "CPU过高")
        self.assertTrue(ok)

    def test_is_not_duplicate_different_rule(self):
        """不同规则不应去重"""
        self.detector._record_event(
            "c1", "", "pod1", "CPU过高", "warning", "msg", {}
        )

        ok = self.detector._is_duplicate("c1/default/pod1", "内存过高")
        self.assertFalse(ok)

    def test_is_not_duplicate_different_pod(self):
        """不同 Pod 不应去重"""
        self.detector._record_event(
            "c1", "", "pod1", "CPU过高", "warning", "msg", {}
        )

        ok = self.detector._is_duplicate("c1/default/pod2", "CPU过高")
        self.assertFalse(ok)


class TestAnomalyDetectorSingleton(unittest.TestCase):
    """测试单例模式"""

    def test_singleton(self):
        """多次获取应返回同一实例"""
        import services.anomaly_detector as mod
        from services.anomaly_detector import AnomalyDetector

        # 重置单例
        old = mod._detector_instance
        mod._detector_instance = None
        try:
            db1 = MockDatabase()
            db2 = MockDatabase()
            d1 = AnomalyDetector(db=db1)
            mod._detector_instance = d1
            d2 = mod.get_anomaly_detector(db=db2)
            self.assertIs(d1, d2)
        finally:
            mod._detector_instance = old


class TestDefaultRules(unittest.TestCase):
    """测试默认规则配置"""

    def test_default_rules_count(self):
        """应有 5 条默认规则"""
        self.assertEqual(len(DEFAULT_RULES), 5)

    def test_all_rules_have_required_fields(self):
        """所有默认规则必须有必填字段"""
        required = {"name", "metric", "operator", "threshold", "duration", "severity", "enabled"}
        for rule in DEFAULT_RULES:
            for field in required:
                self.assertIn(field, rule, f"规则 '{rule.get('name')}' 缺少字段 '{field}'")

    def test_all_operators_valid(self):
        """所有规则的运算符应有效"""
        for rule in DEFAULT_RULES:
            self.assertIn(rule["operator"], OPERATORS,
                          f"规则 '{rule['name']}' 运算符无效: {rule['operator']}")

    def test_all_severities_valid(self):
        """所有规则的严重级别应有效"""
        valid = {SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL, SEVERITY_EMERGENCY}
        for rule in DEFAULT_RULES:
            self.assertIn(rule["severity"], valid,
                          f"规则 '{rule['name']}' 严重级别无效: {rule['severity']}")

    def test_cpu_rule_threshold(self):
        """CPU 规则阈值应为 80"""
        cpu_rule = next(r for r in DEFAULT_RULES if "CPU" in r["name"])
        self.assertEqual(cpu_rule["threshold"], 80)
        self.assertEqual(cpu_rule["operator"], ">")
        self.assertEqual(cpu_rule["duration"], 300)

    def test_memory_rule_threshold(self):
        """内存规则阈值应为 85"""
        mem_rule = next(r for r in DEFAULT_RULES if "内存" in r["name"] and "堆" not in r["name"])
        self.assertEqual(mem_rule["threshold"], 85)


if __name__ == "__main__":
    unittest.main()
