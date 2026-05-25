#!/usr/bin/env python3
"""
Phase 6 告警 API 测试

覆盖:
  - GET  /api/anomaly/events         - 查询异常事件
  - GET  /api/anomaly/events/stats   - 异常事件统计
  - DELETE /api/anomaly/events/<id>  - 删除异常事件
  - GET  /api/anomaly/rules          - 获取告警规则
  - POST /api/anomaly/rules          - 创建告警规则
  - PUT  /api/anomaly/rules/<id>     - 更新告警规则
  - DELETE /api/anomaly/rules/<id>   - 删除告警规则
  - GET  /api/anomaly/notifications      - 获取通知列表
  - POST /api/anomaly/notifications/<id>/read  - 标记已读
  - POST /api/anomaly/notifications/read-all  - 全部已读
"""

import os
import sys
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _TestDB:
    """封装测试用临时数据库，提供与 Database 类兼容的接口"""

    def __init__(self, db_path):
        self._db_file = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")

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


def _create_test_db():
    """创建带有完整表结构的临时数据库"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # users 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # audit_logs 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            details TEXT,
            ip_address TEXT,
            user_agent TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    # clusters 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clusters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kubeconfig TEXT,
            context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # connections 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS connections (
            id TEXT PRIMARY KEY,
            cluster_name TEXT NOT NULL,
            namespace TEXT NOT NULL,
            pod_name TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'arthas',
            local_port INTEGER,
            user_id INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            owner_user_id INTEGER,
            container_name TEXT,
            java_pid INTEGER,
            arthas_version TEXT,
            last_ping_at TIMESTAMP,
            status TEXT DEFAULT 'disconnected',
            last_active_at TIMESTAMP,
            ttl_hours INTEGER DEFAULT 0
        )
    ''')

    # user_clusters 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            cluster_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, cluster_id)
        )
    ''')

    # user_namespaces 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_namespaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            cluster_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, cluster_id, namespace)
        )
    ''')

    # profiler_tasks 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profiler_tasks (
            id TEXT PRIMARY KEY,
            connection_id TEXT,
            user_id INTEGER,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            cluster_name TEXT,
            namespace TEXT,
            pod_name TEXT,
            mode TEXT,
            event TEXT,
            duration INTEGER,
            format TEXT,
            output_path TEXT,
            progress INTEGER DEFAULT 0,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # arthas_command_logs 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS arthas_command_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id TEXT NOT NULL,
            user_id INTEGER,
            command TEXT NOT NULL,
            output TEXT,
            error TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    # diagnosis_capabilities 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnosis_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            level INTEGER,
            description TEXT,
            arthas_command TEXT,
            parameters_schema TEXT,
            risk_level TEXT DEFAULT 'low',
            estimated_duration INTEGER,
            steps_json TEXT,
            handler TEXT,
            confirm_required INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # task_logs 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_logs (
            id TEXT PRIMARY KEY,
            task_id INTEGER,
            capability_id INTEGER,
            user_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            execution_mode TEXT NOT NULL DEFAULT 'manual',
            execution_type TEXT DEFAULT 'script',
            run_type TEXT DEFAULT 'script',
            target_json TEXT DEFAULT '{}',
            params_json TEXT DEFAULT '{}',
            result_json TEXT,
            stdout TEXT,
            stderr TEXT,
            exit_code INTEGER,
            duration_ms INTEGER,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            error_message TEXT,
            work_dir TEXT,
            capability_name TEXT,
            capability_version INTEGER,
            rendered_command TEXT,
            connection_snapshot_json TEXT,
            capability_snapshot_json TEXT,
            ai_analysis_result TEXT,
            log_path TEXT,
            retention_days INTEGER DEFAULT 30,
            is_archived INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    # system_configs 表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_configs (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # anomaly_events 表
    cursor.execute('''
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
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_events_cluster ON anomaly_events(cluster)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_events_severity ON anomaly_events(severity)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_events_created ON anomaly_events(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomaly_events_pod_rule ON anomaly_events(pod, rule_name, created_at DESC)")

    # alert_rules 表
    cursor.execute('''
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
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled)")

    # alert_notifications 表
    cursor.execute('''
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
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_notif_user_read ON alert_notifications(user_id, is_read)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_notif_created ON alert_notifications(created_at DESC)")

    # 插入测试用户
    import bcrypt
    pw_hash = bcrypt.hashpw(b'test123', bcrypt.gensalt()).decode('utf-8')
    cursor.execute(
        'INSERT INTO users (username, password_hash, role, status) VALUES (?, ?, ?, ?)',
        ('testuser', pw_hash, 'admin', 'active')
    )

    conn.commit()
    conn.close()

    return db_path


class AlertAPITestBase(unittest.TestCase):
    """API 测试基类：创建临时数据库并 patch 到 server 的 db 层"""

    _temp_db_path = None

    @classmethod
    def setUpClass(cls):
        cls._temp_db_path = _create_test_db()
        cls._test_db = _TestDB(cls._temp_db_path)

        # Patch models.db.get_db 使其返回测试 DB
        cls._patcher = patch('models.db.get_db', return_value=cls._test_db)
        cls._patcher.start()

        # 确保 anomaly detector 也使用测试 DB
        import services.anomaly_detector as ad_mod
        ad_mod._detector_instance = None

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()

        # 关闭数据库连接后再删除文件
        if hasattr(cls, '_test_db') and cls._test_db:
            try:
                cls._test_db._conn.close()
            except Exception:
                pass

        if cls._temp_db_path and os.path.exists(cls._temp_db_path):
            try:
                os.unlink(cls._temp_db_path)
            except PermissionError:
                pass  # Windows 文件锁，忽略

    def setUp(self):
        self.client = server.app.test_client()
        self.client.testing = True
        # 每个测试前清空异常检测相关表，避免跨测试数据污染
        self._test_db._conn.execute("DELETE FROM anomaly_events")
        self._test_db._conn.execute("DELETE FROM alert_rules")
        self._test_db._conn.execute("DELETE FROM alert_notifications")
        self._test_db._conn.commit()
        # 重置 anomaly detector 单例
        import services.anomaly_detector as ad_mod
        ad_mod._detector_instance = None
        # 登录获取 session
        resp = self.client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'test123',
        })
        self.assertEqual(resp.status_code, 200, f"登录失败: {resp.data}")

    def tearDown(self):
        self.client.get('/api/auth/logout')



import server


class TestAnomalyEventsAPI(AlertAPITestBase):
    """异常事件 API 测试"""

    def _record_event(self, cluster="test-cluster", namespace="default",
                      pod="test-pod", rule_name="CPU过高",
                      severity="warning", message="CPU = 92%"):
        """辅助方法：通过检测器记录事件"""
        from services.anomaly_detector import AnomalyDetector
        detector = AnomalyDetector(db=self._test_db)
        return detector._record_event(
            cluster=cluster, namespace=namespace, pod=pod,
            rule_name=rule_name, severity=severity,
            message=message, metrics_json={"cpu": 92},
        )

    def test_list_events_empty(self):
        """查询空事件列表"""
        resp = self.client.get('/api/anomaly/events')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["total"], 0)
        self.assertEqual(len(data["events"]), 0)

    def test_list_events_with_data(self):
        """查询有数据的事件列表"""
        self._record_event()
        resp = self.client.get('/api/anomaly/events')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["events"]), 1)

    def test_list_events_filter_severity(self):
        """按严重级别过滤"""
        self._record_event(severity="warning")
        self._record_event(severity="critical")

        resp = self.client.get('/api/anomaly/events?severity=critical')
        data = json.loads(resp.data)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["events"][0]["severity"], "critical")

    def test_list_events_filter_cluster(self):
        """按集群过滤"""
        self._record_event(cluster="prod")
        self._record_event(cluster="staging")

        resp = self.client.get('/api/anomaly/events?cluster=prod')
        data = json.loads(resp.data)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["events"][0]["cluster"], "prod")

    def test_list_events_filter_pod(self):
        """按 Pod 过滤"""
        self._record_event(pod="pod-a")
        self._record_event(pod="pod-b")

        resp = self.client.get('/api/anomaly/events?pod=pod-a')
        data = json.loads(resp.data)
        self.assertEqual(data["total"], 1)

    def test_list_events_pagination(self):
        """分页"""
        for i in range(15):
            self._record_event(pod=f"pod-{i}")

        resp = self.client.get('/api/anomaly/events?page=1&page_size=5')
        data = json.loads(resp.data)
        self.assertEqual(len(data["events"]), 5)
        self.assertEqual(data["total"], 15)

    def test_delete_event(self):
        """删除事件"""
        self._record_event()
        events_resp = self.client.get('/api/anomaly/events')
        events = json.loads(events_resp.data)["events"]
        event_id = events[0]["id"]

        resp = self.client.delete(f'/api/anomaly/events/{event_id}')
        self.assertEqual(resp.status_code, 200)

        # 验证已删除
        resp2 = self.client.get('/api/anomaly/events')
        self.assertEqual(json.loads(resp2.data)["total"], 0)

    def test_delete_event_not_found(self):
        """删除不存在的事件"""
        resp = self.client.delete('/api/anomaly/events/99999')
        self.assertEqual(resp.status_code, 404)

    def test_events_stats(self):
        """事件统计"""
        self._record_event(severity="warning")
        self._record_event(severity="critical")
        self._record_event(severity="info")

        resp = self.client.get('/api/anomaly/events/stats')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["total"], 3)
        self.assertEqual(data["by_severity"]["warning"], 1)
        self.assertEqual(data["by_severity"]["critical"], 1)


class TestAnomalyRulesAPI(AlertAPITestBase):
    """告警规则 API 测试"""

    def _create_detector(self):
        from services.anomaly_detector import AnomalyDetector
        return AnomalyDetector(db=self._test_db)

    def test_list_rules_with_defaults(self):
        """查询规则列表 - 默认规则"""
        detector = self._create_detector()
        detector._init_default_rules()

        resp = self.client.get('/api/anomaly/rules')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("rules", data)
        self.assertEqual(len(data["rules"]), 5)

    def test_create_rule(self):
        """创建规则"""
        resp = self.client.post('/api/anomaly/rules', json={
            "name": "自定义规则",
            "metric": "cpu.usagePercent",
            "operator": ">",
            "threshold": 90,
            "duration": 120,
            "severity": "critical",
            "enabled": True,
            "description": "CPU > 90% 持续 2 分钟",
        })
        self.assertEqual(resp.status_code, 201)
        data = json.loads(resp.data)
        self.assertTrue(data["ok"])
        self.assertEqual(data["rule"]["name"], "自定义规则")

    def test_create_rule_validation(self):
        """创建规则验证 - 名称和指标为空"""
        resp = self.client.post('/api/anomaly/rules', json={
            "name": "",
            "metric": "",
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_rule_missing_metric(self):
        """创建规则缺少 metric"""
        resp = self.client.post('/api/anomaly/rules', json={
            "name": "规则",
        })
        self.assertEqual(resp.status_code, 400)

    def test_update_rule(self):
        """更新规则"""
        detector = self._create_detector()
        detector._init_default_rules()

        list_resp = self.client.get('/api/anomaly/rules')
        rules = json.loads(list_resp.data)["rules"]
        rule_id = rules[0]["id"]

        resp = self.client.put(f'/api/anomaly/rules/{rule_id}', json={
            "name": "更新后的名称",
            "threshold": 95,
        })
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["rule"]["name"], "更新后的名称")
        self.assertEqual(data["rule"]["threshold"], 95.0)

    def test_update_rule_not_found(self):
        """更新不存在的规则"""
        resp = self.client.put('/api/anomaly/rules/99999', json={"name": "x"})
        self.assertEqual(resp.status_code, 404)

    def test_delete_rule(self):
        """删除规则"""
        resp = self.client.post('/api/anomaly/rules', json={
            "name": "待删除",
            "metric": "cpu.usagePercent",
            "operator": ">",
            "threshold": 80,
        })
        rule_id = json.loads(resp.data)["rule"]["id"]

        resp = self.client.delete(f'/api/anomaly/rules/{rule_id}')
        self.assertEqual(resp.status_code, 200)

    def test_delete_rule_not_found(self):
        """删除不存在的规则"""
        resp = self.client.delete('/api/anomaly/rules/99999')
        self.assertEqual(resp.status_code, 404)

    def test_toggle_rule(self):
        """切换规则启用/禁用"""
        resp = self.client.post('/api/anomaly/rules', json={
            "name": "可禁用",
            "metric": "cpu.usagePercent",
            "operator": ">",
            "threshold": 80,
            "enabled": True,
        })
        rule_id = json.loads(resp.data)["rule"]["id"]

        resp = self.client.put(f'/api/anomaly/rules/{rule_id}', json={
            "enabled": False,
        })
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["rule"]["enabled"], 0)


class TestAnomalyNotificationsAPI(AlertAPITestBase):
    """通知 API 测试"""

    def _create_event_and_notification(self):
        """创建事件和通知"""
        from services.anomaly_detector import AnomalyDetector
        detector = AnomalyDetector(db=self._test_db)
        detector._record_event(
            cluster="c1", namespace="ns", pod="pod1",
            rule_name="CPU过高", severity="warning",
            message="msg", metrics_json={},
        )

    def test_list_notifications_empty(self):
        """查询空通知列表"""
        resp = self.client.get('/api/anomaly/notifications')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data["notifications"]), 0)
        self.assertEqual(data["unread_count"], 0)

    def test_list_notifications_with_data(self):
        """查询有数据的通知列表"""
        self._create_event_and_notification()

        resp = self.client.get('/api/anomaly/notifications')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertGreater(len(data["notifications"]), 0)
        self.assertGreater(data["unread_count"], 0)

    def test_mark_notification_read(self):
        """标记通知已读"""
        self._create_event_and_notification()

        resp = self.client.get('/api/anomaly/notifications')
        notifs = json.loads(resp.data)["notifications"]
        notif_id = notifs[0]["id"]

        resp = self.client.post(f'/api/anomaly/notifications/{notif_id}/read')
        self.assertEqual(resp.status_code, 200)

        resp2 = self.client.get('/api/anomaly/notifications')
        data = json.loads(resp2.data)
        self.assertEqual(data["unread_count"], 0)

    def test_mark_notification_read_not_found(self):
        """标记不存在的通知"""
        resp = self.client.post('/api/anomaly/notifications/99999/read')
        self.assertEqual(resp.status_code, 404)

    def test_mark_all_read(self):
        """全部已读"""
        self._create_event_and_notification()
        self._create_event_and_notification()

        resp = self.client.post('/api/anomaly/notifications/read-all')
        self.assertEqual(resp.status_code, 200)

        resp2 = self.client.get('/api/anomaly/notifications')
        data = json.loads(resp2.data)
        self.assertEqual(data["unread_count"], 0)

    def test_unread_only_filter(self):
        """只获取未读通知"""
        self._create_event_and_notification()

        resp = self.client.get('/api/anomaly/notifications?unread_only=true')
        data = json.loads(resp.data)
        self.assertGreater(len(data["notifications"]), 0)
        for n in data["notifications"]:
            self.assertEqual(n["is_read"], 0)


class TestAlertPageRoutes(AlertAPITestBase):
    """页面路由测试"""

    def test_alerts_page(self):
        """告警页面可访问"""
        resp = self.client.get('/alerts')
        self.assertEqual(resp.status_code, 200)

    def test_alerts_page_html(self):
        """告警页面 HTML 格式"""
        resp = self.client.get('/alerts.html')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'alert-card.js', resp.data)
        self.assertIn(b'alert-rules.js', resp.data)


if __name__ == "__main__":
    unittest.main()
