"""Tests for toolbox API endpoints."""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server


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

    def execute(self, sql, params=()):
        with self._conn as c:
            cursor = c.execute(sql, params)
            self._conn.commit()
            return cursor

    def count(self, table, where="1=1", params=()):
        sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}"
        with self._conn as c:
            row = c.execute(sql, params).fetchone()
            return row[0] if row else 0


def _create_test_db():
    """创建带有完整表结构的临时数据库"""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

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
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS step_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            step_name TEXT,
            step_type TEXT,
            command TEXT,
            output TEXT,
            status TEXT DEFAULT 'pending',
            duration_ms INTEGER,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS script_tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            runtime TEXT NOT NULL DEFAULT 'python',
            script_body TEXT NOT NULL,
            risk_level TEXT DEFAULT 'low',
            parameters_schema TEXT,
            capability_id INTEGER,
            description TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quick_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            command_template TEXT NOT NULL,
            parameters_schema TEXT,
            risk_level TEXT DEFAULT 'low',
            description TEXT,
            arthas_doc_url TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tool_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version TEXT,
            description TEXT,
            tool_type TEXT NOT NULL,
            file_path TEXT,
            file_size INTEGER,
            sha256 TEXT,
            status TEXT DEFAULT 'active',
            install_path TEXT,
            distributed INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tool_distributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_type TEXT NOT NULL,
            tool_id INTEGER NOT NULL,
            tool_name TEXT,
            target_cluster TEXT,
            target_namespace TEXT,
            target_pod TEXT,
            target_container TEXT,
            install_path TEXT,
            status TEXT DEFAULT 'pending',
            distributed_by INTEGER,
            distributed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clusters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kubeconfig TEXT,
            context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_configs (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    import bcrypt
    pw_hash = bcrypt.hashpw(b'test123', bcrypt.gensalt()).decode('utf-8')
    cursor.execute(
        'INSERT INTO users (username, password_hash, role, status) VALUES (?, ?, ?, ?)',
        ('testuser', pw_hash, 'admin', 'active')
    )

    conn.commit()
    conn.close()

    return db_path


class ToolboxTestBase(unittest.TestCase):
    """API 测试基类：创建临时数据库并 patch 到 server 的 db 层"""

    _temp_db_path = None

    @classmethod
    def setUpClass(cls):
        cls._temp_db_path = _create_test_db()
        cls._test_db = _TestDB(cls._temp_db_path)

        # Patch models.db.get_db 使其返回测试 DB
        cls._patcher = patch('models.db.get_db', return_value=cls._test_db)
        cls._patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()

        if hasattr(cls, '_test_db') and cls._test_db:
            try:
                cls._test_db._conn.close()
            except Exception:
                pass

        if cls._temp_db_path and os.path.exists(cls._temp_db_path):
            try:
                os.unlink(cls._temp_db_path)
            except PermissionError:
                pass

    def setUp(self):
        self.client = server.app.test_client()
        self.client.testing = True
        self._test_db._conn.execute("DELETE FROM script_tools")
        self._test_db._conn.execute("DELETE FROM quick_actions")
        self._test_db._conn.execute("DELETE FROM tool_distributions")
        self._test_db._conn.commit()
        resp = self.client.post('/api/auth/login', json={
            'username': 'testuser',
            'password': 'test123',
        })
        self.assertEqual(resp.status_code, 200, f"登录失败: {resp.data}")

    def tearDown(self):
        self.client.get('/api/auth/logout')


class TestScriptToolsAPI(ToolboxTestBase):
    """Test script tools CRUD endpoints."""

    def test_list_script_tools_empty(self):
        """GET /tasks/script-tools returns empty list initially."""
        resp = self.client.get('/api/tasks/script-tools')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('tools', data)
        self.assertEqual(len(data['tools']), 0)

    def test_create_script_tool(self):
        """POST /tasks/script-tools creates a new script tool."""
        resp = self.client.post('/api/tasks/script-tools', json={
            'name': 'CPU Analysis',
            'runtime': 'python',
            'script_body': 'print("hello")',
            'risk_level': 'low',
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['tool']['name'], 'CPU Analysis')
        self.assertEqual(data['tool']['runtime'], 'python')
        self.assertEqual(data['tool']['script_body'], 'print("hello")')
        self.assertEqual(data['tool']['risk_level'], 'low')

    def test_create_script_tool_validation(self):
        """POST /tasks/script-tools rejects empty name."""
        resp = self.client.post('/api/tasks/script-tools', json={
            'name': '',
            'script_body': 'print("hello")',
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_script_tool_validation_empty_script(self):
        """POST /tasks/script-tools rejects empty script body."""
        resp = self.client.post('/api/tasks/script-tools', json={
            'name': 'Test',
            'script_body': '',
        })
        self.assertEqual(resp.status_code, 400)

    def test_delete_script_tool(self):
        """DELETE /tasks/script-tools/:id removes the tool."""
        resp = self.client.post('/api/tasks/script-tools', json={
            'name': 'To Delete',
            'script_body': 'x = 1',
        })
        tool_id = resp.get_json()['tool']['id']
        resp = self.client.delete(f'/api/tasks/script-tools/{tool_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])

        resp = self.client.get('/api/tasks/script-tools')
        tools = resp.get_json()['tools']
        self.assertEqual(len(tools), 0)

    def test_delete_script_tool_not_found(self):
        """DELETE /tasks/script-tools/:id returns 404 for non-existent tool."""
        resp = self.client.delete('/api/tasks/script-tools/99999')
        self.assertEqual(resp.status_code, 404)

    def test_update_script_tool(self):
        """PUT /tasks/script-tools/:id updates a script tool."""
        resp = self.client.post('/api/tasks/script-tools', json={
            'name': 'Original',
            'script_body': 'x = 1',
        })
        tool_id = resp.get_json()['tool']['id']

        resp = self.client.put(f'/api/tasks/script-tools/{tool_id}', json={
            'name': 'Updated',
            'script_body': 'x = 2',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['tool']['name'], 'Updated')
        self.assertEqual(data['tool']['script_body'], 'x = 2')

    def test_update_script_tool_not_found(self):
        """PUT /tasks/script-tools/:id returns 404 for non-existent tool."""
        resp = self.client.put('/api/tasks/script-tools/99999', json={
            'name': 'Updated',
        })
        self.assertEqual(resp.status_code, 404)

    def test_list_script_tools_with_filter(self):
        """GET /tasks/script-tools with runtime filter."""
        self.client.post('/api/tasks/script-tools', json={
            'name': 'Python Tool',
            'runtime': 'python',
            'script_body': 'print("py")',
        })
        self.client.post('/api/tasks/script-tools', json={
            'name': 'Shell Tool',
            'runtime': 'shell',
            'script_body': 'echo "sh"',
        })

        resp = self.client.get('/api/tasks/script-tools?runtime=python')
        self.assertEqual(resp.status_code, 200)
        tools = resp.get_json()['tools']
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]['name'], 'Python Tool')


class TestQuickActionsAPI(ToolboxTestBase):
    """Test quick actions CRUD endpoints."""

    def test_create_quick_action(self):
        """POST /tasks/quick-actions creates a new quick action."""
        resp = self.client.post('/api/tasks/quick-actions', json={
            'name': 'jad 反编译',
            'category': 'jvm',
            'command_template': 'jad {class_name}',
            'risk_level': 'low',
        })
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['action']['name'], 'jad 反编译')
        self.assertEqual(data['action']['category'], 'jvm')
        self.assertEqual(data['action']['command_template'], 'jad {class_name}')

    def test_list_quick_actions(self):
        """GET /tasks/quick-actions returns list."""
        resp = self.client.get('/api/tasks/quick-actions')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('actions', resp.get_json())

    def test_create_quick_action_validation(self):
        """POST /tasks/quick-actions rejects empty name."""
        resp = self.client.post('/api/tasks/quick-actions', json={
            'name': '',
            'command_template': 'jad {class_name}',
        })
        self.assertEqual(resp.status_code, 400)

    def test_create_quick_action_validation_empty_command(self):
        """POST /tasks/quick-actions rejects empty command template."""
        resp = self.client.post('/api/tasks/quick-actions', json={
            'name': 'Test',
            'command_template': '',
        })
        self.assertEqual(resp.status_code, 400)

    def test_delete_quick_action(self):
        """DELETE /tasks/quick-actions/:id removes the action."""
        resp = self.client.post('/api/tasks/quick-actions', json={
            'name': 'To Delete',
            'command_template': 'test {param}',
        })
        action_id = resp.get_json()['action']['id']
        resp = self.client.delete(f'/api/tasks/quick-actions/{action_id}')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['ok'])

        resp = self.client.get('/api/tasks/quick-actions')
        actions = resp.get_json()['actions']
        self.assertEqual(len(actions), 0)

    def test_delete_quick_action_not_found(self):
        """DELETE /tasks/quick-actions/:id returns 404 for non-existent action."""
        resp = self.client.delete('/api/tasks/quick-actions/99999')
        self.assertEqual(resp.status_code, 404)

    def test_update_quick_action(self):
        """PUT /tasks/quick-actions/:id updates a quick action."""
        resp = self.client.post('/api/tasks/quick-actions', json={
            'name': 'Original',
            'command_template': 'jad {class_name}',
        })
        action_id = resp.get_json()['action']['id']

        resp = self.client.put(f'/api/tasks/quick-actions/{action_id}', json={
            'name': 'Updated',
            'command_template': 'jad --source-only {class_name}',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['action']['name'], 'Updated')
        self.assertEqual(data['action']['command_template'], 'jad --source-only {class_name}')

    def test_update_quick_action_not_found(self):
        """PUT /tasks/quick-actions/:id returns 404 for non-existent action."""
        resp = self.client.put('/api/tasks/quick-actions/99999', json={
            'name': 'Updated',
        })
        self.assertEqual(resp.status_code, 404)

    def test_list_quick_actions_with_filter(self):
        """GET /tasks/quick-actions with category filter."""
        self.client.post('/api/tasks/quick-actions', json={
            'name': 'JVM Action',
            'category': 'jvm',
            'command_template': 'jad {class_name}',
        })
        self.client.post('/api/tasks/quick-actions', json={
            'name': 'Network Action',
            'category': 'network',
            'command_template': 'netstat',
        })

        resp = self.client.get('/api/tasks/quick-actions?category=jvm')
        self.assertEqual(resp.status_code, 200)
        actions = resp.get_json()['actions']
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['name'], 'JVM Action')


class TestBatchDistribute(ToolboxTestBase):
    """Test batch distribution endpoint."""

    def test_batch_distribute_validation(self):
        """POST /tasks/batch-distribute rejects empty targets."""
        resp = self.client.post('/api/tasks/batch-distribute', json={
            'tool_ids': [],
            'targets': [],
        })
        self.assertEqual(resp.status_code, 400)

    def test_batch_distribute_validation_empty_tool_ids(self):
        """POST /tasks/batch-distribute rejects empty tool_ids."""
        resp = self.client.post('/api/tasks/batch-distribute', json={
            'tool_ids': [],
            'targets': [{'cluster': 'test', 'namespace': 'default', 'pod': 'pod-1'}],
        })
        self.assertEqual(resp.status_code, 400)

    def test_batch_distribute_validation_empty_targets(self):
        """POST /tasks/batch-distribute rejects empty targets."""
        resp = self.client.post('/api/tasks/batch-distribute', json={
            'tool_ids': [1],
            'targets': [],
        })
        self.assertEqual(resp.status_code, 400)


if __name__ == '__main__':
    unittest.main()