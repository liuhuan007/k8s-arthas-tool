#!/usr/bin/env python3
"""
测试连接历史加载优先级修复

验证:
1. ConnectionStore 初始化时不加载 connections (保持空数组)
2. 数据库 API 加载后同步到 ConnectionStore
3. renderConnList() 能正确显示数据库中的连接
"""
import unittest
import re
from pathlib import Path


class TestConnectionHistoryFix(unittest.TestCase):
    """测试连接历史加载优先级修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.conn_store_js = (self.root / 'static' / 'js' / 'core' / 'connection-store.js').read_text(encoding='utf-8')
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')

    def test_connection_store_not_load_connections_on_init(self):
        """测试 ConnectionStore 初始化时不加载 connections"""
        # 找到 DOMContentLoaded 回调
        init_match = re.search(
            r"document\.addEventListener\('DOMContentLoaded',\s*\(\)\s*=>\s*\{(.*?)\}\);",
            self.conn_store_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(init_match, "未找到 ConnectionStore DOMContentLoaded 回调")
        
        init_body = init_match.group(1)
        
        # 不应该调用 ConnectionStore.init() (它会加载 connections)
        self.assertNotIn('ConnectionStore.init()', init_body,
                        "❌ ConnectionStore 初始化不应调用 init() 方法 (会加载空的 connections)")
        
        # 应该保留其他状态但不加载 connections
        self.assertIn('_state.currentConnId', init_body,
                     "✅ 应该加载 currentConnId")
        self.assertIn('_state.connState', init_body,
                     "✅ 应该加载 connState")
        
        print("✅ ConnectionStore 初始化正确: 不加载 connections,保留其他状态")

    def test_database_api_syncs_to_connection_store(self):
        """测试数据库 API 加载后同步到 ConnectionStore"""
        # 找到初始化代码中的数据库加载部分
        db_load_match = re.search(
            r"// ✅ P0修复: 先从数据库 API 加载最新连接.*?try\s*\{(.*?)loadClusters\(\);",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(db_load_match, "未找到数据库加载代码")
        
        db_load_body = db_load_match.group(1)
        
        # 应该同步到 ConnectionStore
        self.assertIn('ConnectionStore.setConnections', db_load_body,
                     "❌ 数据库加载后应该同步到 ConnectionStore")
        self.assertIn('ConnectionStore._persist()', db_load_body,
                     "❌ 应该持久化到 localStorage")
        
        print("✅ 数据库加载后正确同步到 ConnectionStore")

    def test_render_conn_list_uses_connections_array(self):
        """测试 renderConnList 使用 _connections 数组"""
        # 找到 renderConnList 函数
        render_match = re.search(
            r"function renderConnList\(\)\s*\{(.*?)\n\}",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(render_match, "未找到 renderConnList 函数")
        
        render_body = render_match.group(1)
        
        # 应该检查 _connections.length
        self.assertIn('_connections.length', render_body,
                     "✅ renderConnList 应该检查 _connections.length")
        
        # 应该遍历 _connections
        self.assertIn('_connections.forEach', render_body,
                     "✅ renderConnList 应该遍历 _connections")
        
        print("✅ renderConnList 正确使用 _connections 数组")


if __name__ == '__main__':
    unittest.main(verbosity=2)
