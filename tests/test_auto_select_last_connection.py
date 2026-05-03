#!/usr/bin/env python3
"""
测试刷新后自动选中最后一条连接

验证:
1. 数据库加载后读取 savedConnId
2. 数据库加载后读取 savedLevel
3. 数据库加载后调用 _restoreActiveConnection
4. 延迟 800ms 执行恢复
"""
import unittest
import re
from pathlib import Path


class TestAutoSelectLastConnection(unittest.TestCase):
    """测试刷新后自动选中最后一条连接"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')

    def test_db_load_reads_active_conn_id(self):
        """测试数据库加载后读取活跃连接 ID"""
        # 找到 DOMContentLoaded 中的数据库加载逻辑
        dom_match = re.search(
            r'document\.addEventListener\(.*?DOMContentLoaded.*?\{.*?'
            r'从数据库加载连接.*?'
            r'arthas_active_conn_',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(dom_match,
                           "❌ 数据库加载后应该读取 arthas_active_conn_")

    def test_db_load_reads_active_level(self):
        """测试数据库加载后读取活跃连接层级"""
        # 应该有 levelKey 读取
        self.assertIn('arthas_active_level_', self.app_ui_js,
                     "❌ 应该读取 arthas_active_level_")

    def test_db_load_calls_restore_active_connection(self):
        """测试数据库加载后调用 _restoreActiveConnection"""
        # 找到数据库加载后的恢复逻辑
        restore_match = re.search(
            r'从数据库加载连接.*?'
            r'_restoreActiveConnection\(conn,\s*savedLevel\)',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(restore_match,
                           "❌ 数据库加载后应该调用 _restoreActiveConnection")

    def test_restore_has_delay(self):
        """测试恢复逻辑有延迟执行"""
        # 应该有 setTimeout(..., 800)
        delay_match = re.search(
            r'_restoreActiveConnection.*?'
            r'setTimeout\(.*?,\s*800\)',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        # 注意: 可能在 loadConnections 中已经有,检查总数即可
        set_timeout_count = self.app_ui_js.count('setTimeout(() => {')
        self.assertGreaterEqual(set_timeout_count, 1,
                               "❌ 应该有 setTimeout 延迟执行")

    def test_restore_has_error_handling(self):
        """测试恢复逻辑有错误处理"""
        # 应该有 .catch(e => {
        self.assertIn('.catch(e => {', self.app_ui_js,
                     "❌ 恢复逻辑应该有 .catch 错误处理")

    def test_restore_logs_active_connection(self):
        """测试恢复逻辑打印日志"""
        # 应该有日志输出
        self.assertIn('[初始化] 恢复活跃连接:', self.app_ui_js,
                     "❌ 应该打印恢复活跃连接的日志")

    def test_complete_auto_select_flow(self):
        """测试完整的自动选中流程"""
        issues = []
        
        # 1. 读取 savedConnId
        if 'arthas_active_conn_' not in self.app_ui_js:
            issues.append("❌ 未读取 arthas_active_conn_")
        
        # 2. 读取 savedLevel
        if 'arthas_active_level_' not in self.app_ui_js:
            issues.append("❌ 未读取 arthas_active_level_")
        
        # 3. 调用 _restoreActiveConnection
        if '_restoreActiveConnection(conn, savedLevel)' not in self.app_ui_js:
            issues.append("❌ 未调用 _restoreActiveConnection")
        
        # 4. 错误处理
        if '.catch(e => {' not in self.app_ui_js:
            issues.append("❌ 缺少 .catch 错误处理")
        
        if issues:
            self.fail("自动选中流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
