#!/usr/bin/env python3
"""新工作区重连编排与 tab 收口回归测试"""

import unittest
from pathlib import Path


class TestWorkspaceReconnectFlow(unittest.TestCase):
    """确保新工作区成为连接/采样行为的唯一状态源"""

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.pool_js = (root / 'static' / 'js' / 'components' / 'connection-pool.js').read_text(encoding='utf-8')
        self.workspace_js = (root / 'static' / 'js' / 'components' / 'connection-workspace.js').read_text(encoding='utf-8')

    def test_shared_reconnect_tracks_previous_level_and_tab(self):
        self.assertIn("const previousLevel = options.previousLevel || _inferLevel(conn);", self.app_ui_js)
        self.assertIn("const previousTab = resolveConnectionWorkspaceTab(", self.app_ui_js)
        self.assertIn("const arthasReconnectOk = await upgradeToArthas({ silentError: true, reconnect: true });", self.app_ui_js)
        self.assertIn("setConnectionWorkspaceTab(activeConn.id, previousTab);", self.app_ui_js)

    def test_partial_reconnect_falls_back_to_monitor_when_arthas_restore_fails(self):
        self.assertIn("setConnectionWorkspaceTab(activeConn.id, 'monitor');", self.app_ui_js)
        self.assertIn("toast(`Arthas 恢复失败，已切回监控页", self.app_ui_js)
        self.assertIn("level: 'pod'", self.app_ui_js)

    def test_workspace_uses_single_tab_resolver_for_tabs_and_body(self):
        self.assertIn("const arthasOnlyTabs = ['sampling', 'console', 'hotfix', 'diag'];", self.workspace_js)
        self.assertIn("function resolveWorkspaceTab(c, vm, requestedTab) {", self.workspace_js)
        self.assertIn("const resolvedTab = resolveWorkspaceTab(conn, vm);", self.workspace_js)
        self.assertIn("renderTabs(next, vm, resolvedTab);", self.workspace_js)
        self.assertIn("renderBody(next, vm, resolvedTab);", self.workspace_js)

    def test_workspace_tab_resolver_can_be_called_with_connection_only(self):
        self.assertIn("const workspaceConn = c || {};", self.workspace_js)
        self.assertIn("const workspaceVm = vm || normalizeConnection(workspaceConn);", self.workspace_js)
        self.assertIn("if (arthasOnlyTabs.includes(tab) && !(workspaceVm.level === 'arthas' && workspaceVm.state === 'connected')) return 'monitor';", self.workspace_js)

    def test_workspace_keeps_pod_state_when_arthas_upgrade_is_starting(self):
        self.assertIn("const hasPodRuntime = !!(workspaceVm.runtimeRaw || workspaceVm.podConnId || workspaceConn.runtime || workspaceConn.runtime_type);", self.workspace_js)
        self.assertIn("workspaceVm.state === 'connecting' && (workspaceVm.level === 'pod' || hasPodRuntime)", self.workspace_js)

    def test_workspace_invalid_sampling_tab_cannot_keep_legacy_profiler_panel_mounted(self):
        self.assertIn("if (arthasOnlyTabs.includes(tab) && !(workspaceVm.level === 'arthas' && workspaceVm.state === 'connected')) return 'monitor';", self.workspace_js)
        self.assertIn("const activeTab = resolvedTab || resolveWorkspaceTab(c, vm);", self.workspace_js)
        self.assertIn("resolveWorkspaceTab(focusConn, normalizeConnection(focusConn)) !== 'monitor'", self.workspace_js)


if __name__ == '__main__':
    unittest.main()
