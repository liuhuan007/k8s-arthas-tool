#!/usr/bin/env python3
"""
测试清理后界面刷新

验证:
1. 清理后调用 _syncState()
2. 清理后调用 renderConnList()
3. 清理后状态正确同步到 window
"""
import unittest
import re
from pathlib import Path


class TestCleanupUIRefresh(unittest.TestCase):
    """测试清理后UI刷新"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')

    def test_cleanup_calls_syncState(self):
        """测试清理后调用 _syncState()"""
        # 找到 cleanupStaleConnections 函数
        func_match = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 cleanupStaleConnections 函数")
        func_body = func_match.group(1)
        
        # 应该调用 _syncState()
        self.assertIn('_syncState()', func_body,
                     "❌ 清理后应该调用 _syncState() 同步到 window")

    def test_cleanup_calls_renderConnList(self):
        """测试清理后调用 renderConnList()"""
        func_match = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 cleanupStaleConnections 函数")
        func_body = func_match.group(1)
        
        # 应该调用 renderConnList()
        self.assertIn('renderConnList()', func_body,
                     "❌ 清理后应该调用 renderConnList()")

    def test_cleanup_has_debug_log(self):
        """测试清理有调试日志"""
        self.assertIn("console.log('[清理]", self.app_ui_js,
                     "❌ 应该有清理调试日志")

    def test_syncState_before_renderConnList(self):
        """测试 _syncState() 在 renderConnList() 之前调用"""
        func_match = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 cleanupStaleConnections 函数")
        func_body = func_match.group(1)
        
        sync_pos = func_body.find('_syncState()')
        render_pos = func_body.find('renderConnList()')
        
        self.assertGreater(sync_pos, -1, "❌ 应该调用 _syncState()")
        self.assertGreater(render_pos, -1, "❌ 应该调用 renderConnList()")
        self.assertLess(sync_pos, render_pos, 
                       "❌ _syncState() 应该在 renderConnList() 之前调用")

    def test_cleanup_filters_connections(self):
        """测试清理过滤连接"""
        func_match = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 cleanupStaleConnections 函数")
        func_body = func_match.group(1)
        
        # 应该过滤 _connections
        self.assertIn('_connections.filter', func_body,
                     "❌ 应该过滤 _connections")
        
        # 应该删除 _connHealth
        self.assertIn('delete _connHealth[id]', func_body,
                     "❌ 应该删除 _connHealth")

    def test_cleanup_resets_current_conn(self):
        """测试清理重置当前连接"""
        func_match = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 cleanupStaleConnections 函数")
        func_body = func_match.group(1)
        
        # 如果当前连接被清理,应该重置
        self.assertIn('staleIds.includes(_currentConnId)', func_body,
                     "❌ 应该检查当前连接是否被清理")
        
        self.assertIn('_currentConnId = null', func_body,
                     "❌ 应该重置 _currentConnId")


if __name__ == '__main__':
    unittest.main()
