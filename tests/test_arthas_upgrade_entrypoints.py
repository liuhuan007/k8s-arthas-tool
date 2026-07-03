#!/usr/bin/env python3
"""Arthas upgrade entrypoint regression tests."""

import unittest
from pathlib import Path


class TestArthasUpgradeEntrypoints(unittest.TestCase):
    """Ensure every Arthas start button uses the shared upgrade orchestration."""

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.pool_js = (root / 'static' / 'js' / 'components' / 'connection-pool.js').read_text(encoding='utf-8')
        self.connections_js = (root / 'static' / 'js' / 'components' / 'connections.js').read_text(encoding='utf-8')
        self.two_step_js = (root / 'static' / 'js' / 'components' / 'two-step-connection.js').read_text(encoding='utf-8')
        self.error_js = (root / 'static' / 'js' / 'components' / 'error-notification.js').read_text(encoding='utf-8')

    def test_shared_upgrade_orchestrator_switches_connection_before_upgrade(self):
        self.assertIn("async function upgradeConnectionById(connId, options = {}) {", self.app_ui_js)
        self.assertIn("await switchConnection(conn.id);", self.app_ui_js)
        self.assertIn("hydratePodConnectionForUpgrade(activeConn);", self.app_ui_js)
        self.assertIn("const arthasOk = await upgradeToArthas({ silentError: true });", self.app_ui_js)
        self.assertIn("window.upgradeConnectionById = upgradeConnectionById;", self.app_ui_js)

    def test_shared_upgrade_hydrates_real_pod_connection_id(self):
        self.assertIn("function hydratePodConnectionForUpgrade(conn) {", self.app_ui_js)
        self.assertIn("const podConnId = conn.pod_conn_id || conn.connection_id || conn.id;", self.app_ui_js)
        self.assertIn("_podConnId = podConnId;", self.app_ui_js)
        self.assertIn("connState: ConnectionState.POD_CONNECTED", self.app_ui_js)

    def test_legacy_upgrade_guard_rehydrates_focused_pod_state(self):
        self.assertIn("function hydrateFocusedPodStateForUpgrade() {", self.two_step_js)
        self.assertIn("const conn = getFocusedPodConnectionForUpgrade();", self.two_step_js)
        self.assertIn("if (typeof hydratePodConnectionForUpgrade === 'function') {", self.two_step_js)
        self.assertIn("return Boolean(_connState === ConnectionState.POD_CONNECTED && _runtimeInfo && _podConnId);", self.two_step_js)
        self.assertIn("return hydrateFocusedPodStateForUpgrade();", self.two_step_js)

    def test_shared_upgrade_finds_user_scoped_connection_id(self):
        self.assertIn("left.split('@u')[0] === right", self.app_ui_js)
        self.assertIn("sameId(c.pod_conn_id)", self.app_ui_js)
        self.assertIn("ConnectionStore.getConnections().find", self.app_ui_js)

    def test_connection_pool_upgrade_delegates_to_shared_entry(self):
        upgrade_block = self.pool_js[self.pool_js.index('async function upgradeArthas(id) {'):self.pool_js.index('function stopArthas')]
        self.assertIn("await window.upgradeConnectionById(id, { source: 'connection-pool' });", upgrade_block)
        self.assertIn("toast('正在启动 Arthas 诊断环境...', 'info');", upgrade_block)
        self.assertIn("toast(`启动 Arthas 失败: ${e.message}`, 'error');", upgrade_block)
        self.assertNotIn("fetch(`${API}/pod/upgrade-to-arthas`", upgrade_block)

    def test_connection_pool_add_uses_backend_connection_id(self):
        self.assertIn("const realId = d.connection_id || id;", self.pool_js)
        self.assertIn("ConnectionStore.removeConnection(id);", self.pool_js)
        self.assertIn("ConnectionStore.addConnection(connectionData);", self.pool_js)
        self.assertIn("focus(realId);", self.pool_js)

    def test_legacy_connection_list_upgrade_no_longer_relies_on_timeout(self):
        upgrade_block = self.connections_js[self.connections_js.index('async function upgradeConnectionFromList(connId) {'):self.connections_js.index('async function deleteConnection')]
        self.assertIn("await window.upgradeConnectionById(connId, { source: 'legacy-connection-list' });", upgrade_block)
        self.assertNotIn('setTimeout(() => {', upgrade_block)

    def test_connection_detail_upgrade_uses_shared_entry(self):
        detail_block = self.app_ui_js[self.app_ui_js.index('async function cdUpgradeToArthas() {'):self.app_ui_js.index('function cdHealthCheck()')]
        self.assertIn("await upgradeConnectionById(connId, { source: 'connection-detail' });", detail_block)

    def test_arthas_error_runtime_extraction_only_uses_explicit_runtime_field(self):
        extract_block = self.error_js[self.error_js.index('function extractRuntime(errorMessage) {'):self.error_js.index('return \'unknown\';', self.error_js.index('function extractRuntime(errorMessage) {'))]
        self.assertIn('/运行时[：:]\\s*(\\w+)/i', extract_block)
        self.assertIn('/runtime[：:]\\s*(\\w+)/i', extract_block)
        self.assertNotIn('/(java|node|python|go|unknown)/i', extract_block)


if __name__ == '__main__':
    unittest.main()
