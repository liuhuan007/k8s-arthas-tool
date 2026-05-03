#!/usr/bin/env python3
"""
连接健康检查和用户隔离修复测试

验证:
1. _get_conn 带权限检查
2. list_arthas_connections 使用正确的字段(user_id)
3. 健康检查不跨用户泄露数据
"""
import unittest
import re
from pathlib import Path


class TestConnectionHealthAndIsolation(unittest.TestCase):
    """测试连接健康检查和用户数据隔离"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.server_py = (self.root / 'server.py').read_text(encoding='utf-8')
        self.pod_apis_py = (self.root / 'api' / 'pod_apis.py').read_text(encoding='utf-8')

    # ── _get_conn 权限检查 ─────────────────────────────────────────────────

    def test_get_conn_has_permission_check(self):
        """测试 _get_conn 有权限检查"""
        # 应该检查 current_user.is_admin
        self.assertIn("if not current_user.is_admin", self.server_py,
                     "❌ _get_conn 应该检查 admin 权限")
        
        # 应该检查 user_id
        self.assertIn("entry.get('user_id') != current_user.id", self.server_py,
                     "❌ _get_conn 应该检查 user_id")

    def test_get_conn_handles_none_entry(self):
        """测试 _get_conn 处理 None entry"""
        # 应该检查 if not entry
        self.assertIn("if not entry:", self.server_py,
                     "❌ _get_conn 应该检查 entry 是否为 None")

    def test_get_conn_returns_conn_safely(self):
        """测试 _get_conn 安全返回 conn"""
        # 应该有 return entry.get('conn')
        func_match = re.search(
            r'def _get_conn\(conn_id: str\):.*?(?=\n@app\.route|\ndef [a-z])',
            self.server_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 _get_conn 函数")
        func_body = func_match.group(0)
        
        # 应该最后返回 conn
        self.assertIn("return entry.get('conn')", func_body,
                     "❌ _get_conn 应该返回 conn 对象")

    # ── list_arthas_connections 字段修复 ─────────────────────────────────────────────────

    def test_list_connections_uses_user_id_not_owner(self):
        """测试列表 API 使用 user_id 而非 owner_user_id"""
        # 不应该查询 owner_user_id
        list_func = re.search(
            r'def list_arthas_connections\(\):.*?(?=\n    @app\.route|\n    # ══)',
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(list_func, "未找到 list_arthas_connections 函数")
        func_body = list_func.group(0)
        
        # 不应该有 owner_user_id
        self.assertNotIn("owner_user_id", func_body,
                        "❌ 列表 API 不应该使用 owner_user_id 字段")
        
        # 应该有 user_id
        self.assertIn("user_id", func_body,
                     "❌ 列表 API 应该使用 user_id 字段")

    def test_list_connections_filters_by_user(self):
        """测试非 admin 按 user_id 过滤"""
        list_func = re.search(
            r'def list_arthas_connections\(\):.*?(?=\n    @app\.route|\n    # ══)',
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(list_func, "未找到 list_arthas_connections 函数")
        func_body = list_func.group(0)
        
        # 应该有 WHERE user_id = ?
        self.assertIn("WHERE user_id = ?", func_body,
                     "❌ 非 admin 应该有 WHERE user_id = ? 过滤")

    def test_list_connections_admin_sees_all(self):
        """测试 admin 看到所有连接"""
        list_func = re.search(
            r'def list_arthas_connections\(\):.*?(?=\n    @app\.route|\n    # ══)',
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(list_func, "未找到 list_arthas_connections 函数")
        func_body = list_func.group(0)
        
        # 应该有 admin 分支
        self.assertIn("if current_user.is_admin:", func_body,
                     "❌ 应该有 admin 分支")
        
        # admin 分支不应该有 WHERE
        admin_branch = func_body.split("if current_user.is_admin:")[1].split("else:")[0]
        self.assertNotIn("WHERE", admin_branch,
                        "❌ admin 分支不应该有 WHERE 条件")

    # ── 健康检查 API ─────────────────────────────────────────────────

    def test_health_check_uses_get_conn(self):
        """测试健康检查使用 _get_conn"""
        health_func = re.search(
            r'def check_connections_health\(\):.*?(?=\n@app\.route|\n\n)',
            self.server_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(health_func, "未找到 check_connections_health 函数")
        func_body = health_func.group(0)
        
        # 应该调用 _get_conn
        self.assertIn("_get_conn(conn_id)", func_body,
                     "❌ 健康检查应该调用 _get_conn(带权限检查)")

    def test_health_check_handles_no_conn(self):
        """测试健康检查处理连接不存在"""
        health_func = re.search(
            r'def check_connections_health\(\):.*?(?=\n@app\.route|\n\n)',
            self.server_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(health_func, "未找到 check_connections_health 函数")
        func_body = health_func.group(0)
        
        # 应该有 if conn: 检查
        self.assertIn("if conn:", func_body,
                     "❌ 健康检查应该检查 conn 是否存在")

    # ── 完整流程 ─────────────────────────────────────────────────

    def test_complete_isolation_flow(self):
        """测试完整用户隔离流程"""
        issues = []
        
        # 1. _get_conn 权限
        if "if not current_user.is_admin" not in self.server_py:
            issues.append("❌ _get_conn 缺少权限检查")
        
        if "entry.get('user_id') != current_user.id" not in self.server_py:
            issues.append("❌ _get_conn 缺少 user_id 检查")
        
        # 2. 列表 API 字段
        if "owner_user_id" in self.pod_apis_py:
            issues.append("❌ 列表 API 仍使用 owner_user_id(错误字段)")
        
        if "WHERE user_id = ?" not in self.pod_apis_py:
            issues.append("❌ 列表 API 缺少 user_id 过滤")
        
        # 3. 健康检查
        health_func = re.search(
            r'def check_connections_health\(\):.*?(?=\n@app\.route|\n\n)',
            self.server_py,
            re.MULTILINE | re.DOTALL
        )
        if health_func and "_get_conn" not in health_func.group(0):
            issues.append("❌ 健康检查未使用 _get_conn")
        
        if issues:
            self.fail("用户隔离存在问题:\n" + "\n".join(issues))

    def test_no_cross_user_data_leak(self):
        """测试无跨用户数据泄露"""
        # 检查所有查询连接的 API
        apis_to_check = [
            ('list_arthas_connections', self.pod_apis_py),
            ('check_connections_health', self.server_py),
        ]
        
        leaks = []
        for func_name, source in apis_to_check:
            func_match = re.search(
                rf'def {func_name}\(\):.*?(?=\n    @app\.route|\n    # ══|\n\n)',
                source,
                re.MULTILINE | re.DOTALL
            )
            if not func_match:
                continue
            
            func_body = func_match.group(0)
            
            # 应该有权限检查或用户过滤
            has_admin_check = 'current_user.is_admin' in func_body
            has_user_filter = 'user_id' in func_body and 'WHERE' in func_body
            has_conn_check = '_get_conn' in func_body or 'entry.get' in func_body
            
            if not (has_admin_check or has_user_filter or has_conn_check):
                leaks.append(f"❌ {func_name} 缺少用户隔离")
        
        if leaks:
            self.fail("发现数据泄露风险:\n" + "\n".join(leaks))


if __name__ == '__main__':
    unittest.main()
