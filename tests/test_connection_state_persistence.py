#!/usr/bin/env python3
"""
测试连接刷新后状态保持

验证:
1. saveConnections 保存连接层级
2. loadConnections 读取连接层级
3. _restoreActiveConnection 根据层级决定是否升级
"""
import unittest
import re
from pathlib import Path


class TestConnectionStatePersistence(unittest.TestCase):
    """测试连接状态持久化"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')

    def test_saveConnections_saves_level(self):
        """测试 saveConnections 保存连接层级"""
        func_match = re.search(
            r'function saveConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 saveConnections 函数")
        func_body = func_match.group(1)
        
        # 应该保存 level
        self.assertIn('arthas_active_level_', func_body,
                     "❌ 应该保存连接层级到 localStorage")
        
        # 应该调用 _inferLevel
        self.assertIn('_inferLevel(currentConn)', func_body,
                     "❌ 应该调用 _inferLevel 获取层级")
        
        # 应该设置 localStorage
        self.assertIn('localStorage.setItem(levelKey, level)', func_body,
                     "❌ 应该保存 level 到 localStorage")

    def test_loadConnections_reads_level(self):
        """测试 loadConnections 读取连接层级"""
        func_match = re.search(
            r'function loadConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 loadConnections 函数")
        func_body = func_match.group(1)
        
        # 应该读取 level
        self.assertIn('arthas_active_level_', func_body,
                     "❌ 应该读取连接层级从 localStorage")
        
        # 应该传递给 _restoreActiveConnection
        self.assertIn('_restoreActiveConnection(conn, savedLevel)', func_body,
                     "❌ 应该传递 savedLevel 给恢复函数")

    def test_restoreActiveConnection_uses_savedLevel(self):
        """测试 _restoreActiveConnection 使用 savedLevel 参数"""
        func_match = re.search(
            r'async function _restoreActiveConnection\(conn, savedLevel\)',
            self.app_ui_js
        )
        self.assertIsNotNone(func_match, "❌ _restoreActiveConnection 应该有 savedLevel 参数")

    def test_restore_uses_savedLevel_not_arthas_version(self):
        """测试恢复时使用 savedLevel 而非 conn.arthas_version"""
        # 使用更简单的匹配方式
        self.assertIn("savedLevel === 'arthas'", self.app_ui_js,
                     "❌ 应该使用 savedLevel 判断是否升级")
        
        # 不应该有旧的判断逻辑
        if "if (conn.arthas_version && podD.runtime" in self.app_ui_js:
            self.fail("❌ 不应该仅依赖 conn.arthas_version 判断, 应使用 savedLevel")

    def test_restore_updates_conn_level(self):
        """测试恢复后更新 conn.level"""
        # 直接检查文件中是否有该语句
        self.assertIn("conn.level = 'arthas'", self.app_ui_js,
                     "❌ Arthas 升级后应该更新 conn.level")

    def test_restore_has_debug_logs(self):
        """测试恢复有调试日志"""
        # 直接检查文件中是否有调试日志
        self.assertIn("console.log('[恢复]", self.app_ui_js,
                     "❌ 应该有恢复调试日志")

    def test_complete_persistence_flow(self):
        """测试完整的持久化流程"""
        issues = []
        
        # 1. 保存
        save_match = re.search(
            r'function saveConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        if save_match:
            save_body = save_match.group(1)
            if 'arthas_active_level_' not in save_body:
                issues.append("❌ saveConnections 未保存 level")
            if '_inferLevel' not in save_body:
                issues.append("❌ saveConnections 未调用 _inferLevel")
        
        # 2. 加载
        load_match = re.search(
            r'function loadConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        if load_match:
            load_body = load_match.group(1)
            if 'arthas_active_level_' not in load_body:
                issues.append("❌ loadConnections 未读取 level")
            if '_restoreActiveConnection(conn, savedLevel)' not in load_body:
                issues.append("❌ loadConnections 未传递 savedLevel")
        
        # 3. 恢复
        restore_match = re.search(
            r'async function _restoreActiveConnection\(conn, savedLevel\)',
            self.app_ui_js
        )
        if not restore_match:
            issues.append("❌ _restoreActiveConnection 没有 savedLevel 参数")
        
        if issues:
            self.fail("持久化流程存在问题:\n" + "\n".join(issues))

    def test_no_level_degradation_on_refresh(self):
        """测试刷新不会降级 Arthas 连接"""
        # 应该检查 savedLevel === 'arthas'
        self.assertIn("savedLevel === 'arthas'", self.app_ui_js,
                     "❌ 应该检查 savedLevel 以保持 Arthas 连接")
        
        # 不应该有旧的判断逻辑
        if "if (conn.arthas_version && podD.runtime" in self.app_ui_js:
            self.fail("❌ 恢复逻辑不应仅依赖 conn.arthas_version, 会导致降级")


if __name__ == '__main__':
    unittest.main()
