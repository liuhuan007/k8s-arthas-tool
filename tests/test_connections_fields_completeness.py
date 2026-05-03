#!/usr/bin/env python3
"""
connections 表字段完整性测试

验证所有写入路径都包含必要字段
"""
import unittest
import re
from pathlib import Path


class TestConnectionsFieldsCompleteness(unittest.TestCase):
    """测试 connections 表字段完整性"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.server_py = (self.root / 'server.py').read_text(encoding='utf-8')
        self.pod_apis_py = (self.root / 'api' / 'pod_apis.py').read_text(encoding='utf-8')

    # ── 必需字段列表 ─────────────────────────────────────────────────

    REQUIRED_FIELDS = [
        'id', 'cluster_name', 'namespace', 'pod_name', 'container_name',
        'level', 'local_port', 'java_pid', 'arthas_version',
        'last_ping_at', 'user_id', 'status', 'updated_at'
    ]

    # ── server.py 写入路径 ─────────────────────────────────────────────────

    def test_server_arthas_connect_insert_has_all_fields(self):
        """测试 server.py arthas_connect insert 包含所有字段"""
        # 找到 insert 语句
        insert_match = re.search(
            r"db\.insert\('connections',\s*\{([^}]+)\}\)",
            self.server_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(insert_match, "未找到 insert 语句")
        insert_body = insert_match.group(1)
        
        # 检查必需字段
        missing = []
        for field in self.REQUIRED_FIELDS:
            if f"'{field}'" not in insert_body and f'"{field}"' not in insert_body:
                # container_name 可以为空字符串
                if field == 'container_name':
                    continue
                missing.append(field)
        
        if missing:
            self.fail(f"insert 缺少字段: {', '.join(missing)}")

    def test_server_arthas_connect_update_has_important_fields(self):
        """测试 server.py arthas_connect update 包含重要字段"""
        # 找到 update 语句(在 arthas_connect 函数中)
        func_match = re.search(
            r'def arthas_connect\(\):.*?(?=\n@app\.route)',
            self.server_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 arthas_connect 函数")
        func_body = func_match.group(0)
        
        # 检查重要字段
        important_fields = ['java_pid', 'arthas_version', 'status', 'last_ping_at']
        missing = []
        for field in important_fields:
            if f"'{field}'" not in func_body:
                missing.append(field)
        
        if missing:
            self.fail(f"update 缺少重要字段: {', '.join(missing)}")

    def test_server_auto_reconnect_has_all_fields(self):
        """测试 server.py 自动重连包含所有字段"""
        # 找到 _ensure_connection 函数
        func_match = re.search(
            r'def _ensure_connection\(.*?(?=\n@app\.route|\ndef [a-z])',
            self.server_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 _ensure_connection 函数")
        func_body = func_match.group(0)
        
        # 应该有 java_pid, arthas_version
        important_fields = ['java_pid', 'arthas_version', 'status', 'last_ping_at']
        missing = []
        for field in important_fields:
            if f"'{field}'" not in func_body:
                missing.append(field)
        
        if missing:
            self.fail(f"_ensure_connection 缺少字段: {', '.join(missing)}")

    # ── pod_apis.py 写入路径 ─────────────────────────────────────────────────

    def test_pod_connect_insert_has_all_fields(self):
        """测试 pod_apis.py Pod 连接创建包含所有字段"""
        # 找到 conn_data
        data_match = re.search(
            r"conn_data\s*=\s*\{([^}]+)\}",
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(data_match, "未找到 conn_data")
        data_body = data_match.group(1)
        
        # 检查必需字段
        pod_required = ['cluster_name', 'namespace', 'pod_name', 'container_name', 
                       'level', 'user_id', 'status', 'last_ping_at', 'updated_at']
        missing = []
        for field in pod_required:
            if f"'{field}'" not in data_body:
                missing.append(field)
        
        if missing:
            self.fail(f"Pod 连接创建缺少字段: {', '.join(missing)}")

    def test_pod_upgrade_has_all_fields(self):
        """测试 pod_apis.py 升级到 Arthas 包含所有字段"""
        # 找到 upgrade_data
        data_match = re.search(
            r"upgrade_data\s*=\s*\{([^}]+)\}",
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(data_match, "未找到 upgrade_data")
        data_body = data_match.group(1)
        
        # 检查必需字段
        upgrade_required = ['java_pid', 'arthas_version', 'local_port', 
                           'status', 'last_ping_at']
        missing = []
        for field in upgrade_required:
            if f"'{field}'" not in data_body:
                missing.append(field)
        
        if missing:
            self.fail(f"升级 Arthas 缺少字段: {', '.join(missing)}")

    # ── 字段值正确性 ─────────────────────────────────────────────────

    def test_status_field_values(self):
        """测试 status 字段使用正确的值"""
        # 应该有 'ready', 'pod_connected', 'disconnected'
        all_code = self.server_py + self.pod_apis_py
        
        self.assertIn("'ready'", all_code, "❌ 应该有 'ready' 状态")
        self.assertIn("'pod_connected'", all_code, "❌ 应该有 'pod_connected' 状态")
        self.assertIn("'disconnected'", all_code, "❌ 应该有 'disconnected' 状态")

    def test_level_field_values(self):
        """测试 level 字段使用正确的值"""
        all_code = self.server_py + self.pod_apis_py
        
        self.assertIn("'arthas'", all_code, "❌ 应该有 'arthas' 层级")
        self.assertIn("'pod'", all_code, "❌ 应该有 'pod' 层级")

    def test_java_pid_from_conn_object(self):
        """测试 java_pid 从 conn 对象获取"""
        # server.py 应该使用 conn.java_pid
        self.assertIn("conn.java_pid", self.server_py,
                     "❌ server.py 应该使用 conn.java_pid")
        
        # pod_apis.py 应该使用 arthas_conn.java_pid
        self.assertIn("arthas_conn.java_pid", self.pod_apis_py,
                     "❌ pod_apis.py 应该使用 arthas_conn.java_pid")

    def test_arthas_version_from_conn_object(self):
        """测试 arthas_version 从 conn 对象获取"""
        self.assertIn("conn.arthas_version", self.server_py,
                     "❌ server.py 应该使用 conn.arthas_version")
        
        self.assertIn("arthas_conn.arthas_version", self.pod_apis_py,
                     "❌ pod_apis.py 应该使用 arthas_conn.arthas_version")

    # ── 完整流程 ─────────────────────────────────────────────────

    def test_all_write_paths_complete(self):
        """测试所有写入路径字段完整"""
        issues = []
        
        # 1. server.py arthas_connect
        if "conn.java_pid" not in self.server_py:
            issues.append("❌ server.py 未写入 java_pid")
        
        if "conn.arthas_version" not in self.server_py:
            issues.append("❌ server.py 未写入 arthas_version")
        
        if "'status': 'ready'" not in self.server_py:
            issues.append("❌ server.py 未写入 status")
        
        if "'last_ping_at'" not in self.server_py:
            issues.append("❌ server.py 未写入 last_ping_at")
        
        # 2. pod_apis.py
        if "'container_name'" not in self.pod_apis_py:
            issues.append("❌ pod_apis.py 未写入 container_name")
        
        if "arthas_conn.java_pid" not in self.pod_apis_py:
            issues.append("❌ pod_apis.py 未写入 java_pid")
        
        if issues:
            self.fail("字段完整性存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
