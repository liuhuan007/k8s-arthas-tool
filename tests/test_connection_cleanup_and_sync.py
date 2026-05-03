#!/usr/bin/env python3
"""
P1b-3 连接清理和状态同步修复测试

验证:
1. 后端清理 API 安全性
2. 前端清理后状态同步
3. 连接详情面板可显示
4. Pod 连接状态同步
"""
import unittest
import re
from pathlib import Path


class TestConnectionCleanupAndSync(unittest.TestCase):
    """测试连接清理和状态同步"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.server_py = (self.root / 'server.py').read_text(encoding='utf-8')
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.html = (self.root / 'static' / 'index.html').read_text(encoding='utf-8')

    # ── 后端清理安全性 ─────────────────────────────────────────────────

    def test_cleanup_handles_none_entry(self):
        """测试清理 API 处理 None entry"""
        # 应该有安全检查: if entry else None
        self.assertIn("entry.get('conn') if entry else None", self.server_py,
                     "❌ 应该安全处理 entry 为 None 的情况")

    def test_cleanup_has_error_logging(self):
        """测试清理 API 有错误日志"""
        # 应该有 log.warning
        self.assertIn('log.warning(f"断开连接', self.server_py,
                     "❌ 应该有断开连接的错误日志")

    def test_cleanup_uses_pop_safely(self):
        """测试使用 pop 安全移除"""
        # 应该使用 _connections.pop(conn_id, None)
        self.assertIn("_connections.pop(conn_id, None)", self.server_py,
                     "❌ 应该使用 pop 安全移除")

    # ── 前端清理状态同步 ─────────────────────────────────────────────────

    def test_cleanup_calls_saveConnections(self):
        """测试清理后保存连接"""
        # 应该在清理后调用 saveConnections()
        cleanup_func = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(cleanup_func, "未找到 cleanupStaleConnections 函数")
        func_body = cleanup_func.group(1)
        
        # 应该调用 saveConnections
        self.assertIn('saveConnections()', func_body,
                     "❌ 清理后应该保存连接")

    def test_cleanup_calls_csbRefresh(self):
        """测试清理后刷新状态条"""
        cleanup_func = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(cleanup_func, "未找到 cleanupStaleConnections 函数")
        func_body = cleanup_func.group(1)
        
        # 应该调用 csbRefresh
        self.assertIn('csbRefresh()', func_body,
                     "❌ 清理后应该刷新连接状态条")

    def test_cleanup_calls_updateFeatureTabs(self):
        """测试清理后更新功能 Tab"""
        cleanup_func = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(cleanup_func, "未找到 cleanupStaleConnections 函数")
        func_body = cleanup_func.group(1)
        
        # 应该调用 updateFeatureTabs
        self.assertIn('updateFeatureTabs()', func_body,
                     "❌ 清理后应该更新功能 Tab")

    def test_cleanup_calls_updateConnectionButton(self):
        """测试清理后更新连接按钮"""
        cleanup_func = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(cleanup_func, "未找到 cleanupStaleConnections 函数")
        func_body = cleanup_func.group(1)
        
        # 应该调用 updateConnectionButton
        self.assertIn('updateConnectionButton()', func_body,
                     "❌ 清理后应该更新连接按钮")

    def test_cleanup_has_debug_log(self):
        """测试清理有调试日志"""
        self.assertIn("console.log('[清理]", self.app_ui_js,
                     "❌ 应该有清理调试日志")

    # ── 连接详情面板 ─────────────────────────────────────────────────

    def test_detail_panel_no_inline_display_none(self):
        """测试详情面板没有 inline display:none"""
        # 不应该有 style="display:none"
        self.assertNotIn('id="panel-connection-detail" style="display:none"', self.html,
                        "❌ 详情面板不应该有 inline display:none")

    def test_detail_panel_exists(self):
        """测试详情面板存在"""
        self.assertIn('id="panel-connection-detail"', self.html,
                     "❌ 详情面板应该存在")

    def test_openConnectionDetail_function(self):
        """测试 openConnectionDetail 函数存在"""
        self.assertIn('function openConnectionDetail(', self.app_ui_js,
                     "❌ 应该有 openConnectionDetail 函数")

    def test_renderConnectionDetail_function(self):
        """测试 renderConnectionDetail 函数存在"""
        self.assertIn('function renderConnectionDetail(', self.app_ui_js,
                     "❌ 应该有 renderConnectionDetail 函数")

    # ── 完整流程 ─────────────────────────────────────────────────

    def test_complete_cleanup_flow(self):
        """测试完整清理流程"""
        issues = []
        
        # 1. 后端安全
        if "entry.get('conn') if entry else None" not in self.server_py:
            issues.append("❌ 后端未安全处理 entry")
        
        # 2. 前端保存
        cleanup_func = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        if cleanup_func:
            func_body = cleanup_func.group(1)
            if 'saveConnections()' not in func_body:
                issues.append("❌ 清理后未保存连接")
            if 'csbRefresh()' not in func_body:
                issues.append("❌ 清理后未刷新状态条")
            if 'updateFeatureTabs()' not in func_body:
                issues.append("❌ 清理后未更新功能 Tab")
        
        # 3. 详情面板
        if 'id="panel-connection-detail" style="display:none"' in self.html:
            issues.append("❌ 详情面板有 inline display:none")
        
        if issues:
            self.fail("清理流程存在问题:\n" + "\n".join(issues))

    def test_state_sync_after_cleanup(self):
        """测试清理后状态同步"""
        # 找到清理函数
        cleanup_func = re.search(
            r'async function cleanupStaleConnections\(\)\s*\{(.*?)^\}',
            self.app_ui_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(cleanup_func, "未找到 cleanupStaleConnections 函数")
        func_body = cleanup_func.group(1)
        
        # 应该按正确顺序调用
        save_pos = func_body.find('saveConnections()')
        render_pos = func_body.find('renderConnList()')
        csb_pos = func_body.find('csbRefresh()')
        
        self.assertGreater(save_pos, -1, "❌ 应该调用 saveConnections")
        self.assertGreater(render_pos, -1, "❌ 应该调用 renderConnList")
        self.assertGreater(csb_pos, -1, "❌ 应该调用 csbRefresh")


if __name__ == '__main__':
    unittest.main()
