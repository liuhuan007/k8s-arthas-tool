#!/usr/bin/env python3
"""
测试连接数据字段精简

验证:
1. 数据库表不包含 runtime/pod_phase/owner_user_id 字段迁移
2. API 查询不包含 runtime/pod_phase 字段
3. Pod 连接创建时不保存 runtime
"""
import unittest
import re
from pathlib import Path


class TestConnectionDataSimplified(unittest.TestCase):
    """测试连接数据字段精简"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.db_py = (self.root / 'models' / 'db.py').read_text(encoding='utf-8')
        self.pod_apis_py = (self.root / 'api' / 'pod_apis.py').read_text(encoding='utf-8')

    def test_db_schema_no_redundant_fields(self):
        """测试数据库迁移不包含冗余字段"""
        # 不应该添加这些字段
        self.assertNotIn('"runtime"', self.db_py,
                        "❌ db.py 不应该添加 runtime 字段")
        self.assertNotIn('"pod_phase"', self.db_py,
                        "❌ db.py 不应该添加 pod_phase 字段")
        self.assertNotIn('"owner_user_id"', self.db_py,
                        "❌ db.py 不应该添加 owner_user_id 字段")
        print("✅ 数据库 Schema 不包含冗余字段")

    def test_api_query_no_redundant_fields(self):
        """测试 API 查询不包含冗余字段"""
        # 找到 list_arthas_connections 函数
        func_match = re.search(
            r"def list_arthas_connections\(\):.*?return jsonify",
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 list_arthas_connections 函数")
        
        func_body = func_match.group(0)
        
        # 不应该查询这些字段
        self.assertNotIn('runtime', func_body,
                        "❌ API 查询不应该包含 runtime 字段")
        self.assertNotIn('pod_phase', func_body,
                        "❌ API 查询不应该包含 pod_phase 字段")
        self.assertNotIn('pod_conn_id', func_body,
                        "❌ API 查询不应该包含 pod_conn_id 字段")
        
        print("✅ API 查询不包含冗余字段")

    def test_pod_connect_no_runtime_save(self):
        """测试 Pod 连接创建时不保存 runtime 到数据库"""
        # 找到 pod_connect 函数中的数据库插入部分
        func_match = re.search(
            r"conn_data = \{.*?\}",
            self.pod_apis_py,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 conn_data 定义")
        
        conn_data_body = func_match.group(0)
        
        # conn_data 不应该包含 runtime 字段
        self.assertNotIn('runtime', conn_data_body,
                        "❌ conn_data 不应该包含 runtime 字段")
        self.assertNotIn('pod_phase', conn_data_body,
                        "❌ conn_data 不应该包含 pod_phase 字段")
        self.assertNotIn('pod_conn_id', conn_data_body,
                        "❌ conn_data 不应该包含 pod_conn_id 字段")
        
        print("✅ Pod 连接创建时不保存 runtime/pod_phase/pod_conn_id 到数据库")


if __name__ == '__main__':
    unittest.main(verbosity=2)
