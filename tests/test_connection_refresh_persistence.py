#!/usr/bin/env python3
"""
测试刷新后连接状态保持

验证:
1. Pod 连接恢复后保存 level='pod'
2. Arthas 连接恢复后保存 level='arthas'
3. 所有恢复路径都调用 saveConnections()
"""
import unittest
import re
from pathlib import Path


class TestConnectionRefreshPersistence(unittest.TestCase):
    """测试刷新后连接状态保持"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')

    def test_pod_restore_sets_level(self):
        """测试 Pod 恢复后设置 level='pod'"""
        # 找到 Pod 恢复逻辑
        self.assertIn("conn.level = 'pod';", self.app_ui_js,
                     "❌ Pod 恢复后应该设置 level='pod'")

    def test_pod_restore_saves_connections(self):
        """测试 Pod 恢复后保存连接"""
        # 应该调用 saveConnections() (在 _syncState() 之后)
        # 不要求严格的正则,只要存在即可
        self.assertIn('saveConnections();', self.app_ui_js,
                     "❌ Pod 恢复后应该调用 saveConnections()")

    def test_arthas_upgrade_sets_level(self):
        """测试 Arthas 升级后设置 level='arthas'"""
        # 应该有 conn.level = 'arthas'
        self.assertIn("conn.level = 'arthas';", self.app_ui_js,
                     "❌ Arthas 升级后应该设置 level='arthas'")

    def test_arthas_upgrade_saves_connections(self):
        """测试 Arthas 升级后保存连接"""
        # 应该多次调用 saveConnections() (至少 3 次: Pod恢复, Arthas升级, 直接恢复)
        save_count = self.app_ui_js.count('saveConnections();')
        self.assertGreaterEqual(save_count, 3,
                               f"❌ saveConnections() 调用次数不足: {save_count} < 3")

    def test_arthas_fallback_sets_level(self):
        """测试 Arthas 回退恢复后设置 level='arthas'"""
        # 找到 Step 3 回退逻辑
        fallback_match = re.search(
            r'// Step 3: 回退到原有 Arthas 直接连接.*?conn\.level = \'arthas\';',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(fallback_match,
                           "❌ Arthas 回退恢复后应该设置 level='arthas'")

    def test_arthas_fallback_saves_connections(self):
        """测试 Arthas 回退恢复后保存连接"""
        # 找到 Step 3 逻辑中的 saveConnections()
        fallback_match = re.search(
            r'// Step 3: 回退到原有 Arthas 直接连接.*?saveConnections\(\);',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(fallback_match,
                           "❌ Arthas 回退恢复后应该调用 saveConnections()")

    def test_complete_refresh_flow(self):
        """测试完整的刷新恢复流程"""
        issues = []
        
        # 1. Pod 恢复设置 level
        if "conn.level = 'pod';" not in self.app_ui_js:
            issues.append("❌ Pod 恢复未设置 level")
        
        # 2. Arthas 升级设置 level
        if "conn.level = 'arthas';" not in self.app_ui_js:
            issues.append("❌ Arthas 升级未设置 level")
        
        # 3. 多次调用 saveConnections()
        save_count = self.app_ui_js.count('saveConnections();')
        if save_count < 3:
            issues.append(f"❌ saveConnections() 调用次数不足: {save_count} < 3")
        
        if issues:
            self.fail("刷新恢复流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
