#!/usr/bin/env python3
"""
测试 container_name 字段映射修复

验证:
1. normalizeConnTarget 使用 container_name 字段
2. switchConnection 使用 container_name 字段
3. 数据库查询包含 container_name 字段
"""
import unittest
import re
from pathlib import Path


class TestContainerNameFix(unittest.TestCase):
    """测试 container_name 字段映射修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.pod_apis_py = (self.root / 'api' / 'pod_apis.py').read_text(encoding='utf-8')

    def test_normalize_conn_target_uses_container_name(self):
        """测试 normalizeConnTarget 使用 container_name 字段"""
        # 找到 normalizeConnTarget 函数
        func_match = re.search(
            r"function normalizeConnTarget\(conn\)\s*\{(.*?)\n\}",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 normalizeConnTarget 函数")
        
        func_body = func_match.group(1)
        
        # 应该使用 container_name 字段
        self.assertIn('container_name', func_body,
                     "❌ normalizeConnTarget 应该使用 container_name 字段")
        
        # 应该有降级处理
        self.assertIn('conn.container_name || conn.container', func_body,
                     "✅ 应该有 container_name -> container 降级处理")
        
        print("✅ normalizeConnTarget 正确使用 container_name 字段")

    def test_switch_connection_uses_container_name(self):
        """测试 switchConnection 使用 container_name 字段"""
        # 找到 switchConnection 函数中的 t 对象定义
        t_match = re.search(
            r"const level = _inferLevel\(conn\);.*?const t = \{(.*?)\};",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(t_match, "未找到 switchConnection 中的 t 对象")
        
        t_body = t_match.group(1)
        
        # 应该使用 container_name 字段
        self.assertIn('container_name', t_body,
                     "❌ switchConnection 应该使用 container_name 字段")
        
        print("✅ switchConnection 正确使用 container_name 字段")

    def test_api_query_includes_container_name(self):
        """测试 API 查询包含 container_name 字段"""
        # 找到 list_arthas_connections 函数
        func_match = re.search(
            r"def list_arthas_connections\(\):.*?return jsonify",
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 list_arthas_connections 函数")
        
        func_body = func_match.group(0)
        
        # 应该查询 container_name
        self.assertIn('container_name', func_body,
                     "✅ API 查询应该包含 container_name 字段")
        
        print("✅ API 查询包含 container_name 字段")

    def test_pod_connect_saves_container_name(self):
        """测试 Pod 连接创建时保存 container_name"""
        # 找到 pod_connect 函数中的 conn_data
        conn_data_match = re.search(
            r"conn_data = \{(.*?)\}",
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(conn_data_match, "未找到 conn_data 定义")
        
        conn_data_body = conn_data_match.group(1)
        
        # 应该保存 container_name
        self.assertIn('container_name', conn_data_body,
                     "✅ conn_data 应该包含 container_name 字段")
        
        print("✅ Pod 连接创建时保存 container_name")


if __name__ == '__main__':
    unittest.main(verbosity=2)
