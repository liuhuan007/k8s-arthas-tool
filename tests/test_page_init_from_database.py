#!/usr/bin/env python3
"""
测试页面初始化从数据库加载连接

验证:
1. DOMContentLoaded 时调用 /api/arthas/connections
2. 数据库加载成功后更新 localStorage
3. 数据库加载失败时降级到 localStorage
"""
import unittest
import re
from pathlib import Path


class TestPageInitFromDatabase(unittest.TestCase):
    """测试页面初始化从数据库加载"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')

    def test_init_uses_async_function(self):
        """测试 DOMContentLoaded 使用 async 函数"""
        self.assertIn("document.addEventListener('DOMContentLoaded', async function()", self.app_ui_js,
                     "❌ DOMContentLoaded 应该使用 async function")

    def test_init_fetches_from_database(self):
        """测试初始化时从数据库 API 加载"""
        # 找到 DOMContentLoaded 回调
        init_match = re.search(
            r"document\.addEventListener\('DOMContentLoaded', async function\(\)\s*\{(.*?)loadClusters\(\)",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(init_match, "未找到 DOMContentLoaded 回调")
        init_body = init_match.group(1)
        
        # 应该调用 /api/arthas/connections
        self.assertIn('/arthas/connections', init_body,
                     "❌ 应该调用 /api/arthas/connections API")
        
        # 应该有 credentials: 'include'
        self.assertIn("credentials: 'include'", init_body,
                     "❌ 应该包含 credentials: 'include'")

    def test_init_updates_localStorage(self):
        """测试初始化成功后更新 localStorage"""
        init_match = re.search(
            r"document\.addEventListener\('DOMContentLoaded', async function\(\)\s*\{(.*?)loadClusters\(\)",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(init_match, "未找到 DOMContentLoaded 回调")
        init_body = init_match.group(1)
        
        # 应该更新 localStorage
        self.assertIn('localStorage.setItem(key, JSON.stringify(_connections))', init_body,
                     "❌ 应该更新 localStorage")

    def test_init_has_fallback_to_localStorage(self):
        """测试数据库加载失败时降级到 localStorage"""
        init_match = re.search(
            r"document\.addEventListener\('DOMContentLoaded', async function\(\)\s*\{(.*?)loadClusters\(\)",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(init_match, "未找到 DOMContentLoaded 回调")
        init_body = init_match.group(1)
        
        # 应该有 catch 块调用 loadConnections()
        self.assertIn('loadConnections()', init_body,
                     "❌ 应该有降级到 loadConnections()")
        
        # 应该有错误日志
        self.assertIn("console.error('[初始化]", init_body,
                     "❌ 应该有初始化错误日志")

    def test_init_calls_syncState(self):
        """测试初始化后同步状态"""
        init_match = re.search(
            r"document\.addEventListener\('DOMContentLoaded', async function\(\)\s*\{(.*?)loadClusters\(\)",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(init_match, "未找到 DOMContentLoaded 回调")
        init_body = init_match.group(1)
        
        # 应该调用 _syncState()
        self.assertIn('_syncState()', init_body,
                     "❌ 应该调用 _syncState() 同步状态")

    def test_init_calls_renderConnList(self):
        """测试初始化后渲染连接列表"""
        init_match = re.search(
            r"document\.addEventListener\('DOMContentLoaded', async function\(\)\s*\{(.*?)loadClusters\(\)",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(init_match, "未找到 DOMContentLoaded 回调")
        init_body = init_match.group(1)
        
        # 应该调用 renderConnList()
        self.assertIn('renderConnList()', init_body,
                     "❌ 应该调用 renderConnList()")

    def test_init_has_debug_log(self):
        """测试初始化有调试日志"""
        self.assertIn("console.log('[初始化] 从数据库加载连接:'", self.app_ui_js,
                     "❌ 应该有初始化调试日志")

    def test_complete_init_flow(self):
        """测试完整的初始化流程"""
        issues = []
        
        # 1. async function
        if "async function()" not in self.app_ui_js:
            issues.append("❌ DOMContentLoaded 未使用 async function")
        
        # 2. 数据库 API
        init_match = re.search(
            r"document\.addEventListener\('DOMContentLoaded', async function\(\)\s*\{(.*?)loadClusters\(\)",
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        if init_match:
            init_body = init_match.group(1)
            if '/arthas/connections' not in init_body:
                issues.append("❌ 未调用 /api/arthas/connections")
            if '_syncState()' not in init_body:
                issues.append("❌ 未调用 _syncState()")
            if 'renderConnList()' not in init_body:
                issues.append("❌ 未调用 renderConnList()")
            if 'loadConnections()' not in init_body:
                issues.append("❌ 未调用 loadConnections() 作为降级")
        
        if issues:
            self.fail("初始化流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
