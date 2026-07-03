#!/usr/bin/env python3
"""重连失败交互提示回归测试"""

import unittest
from pathlib import Path


class TestReconnectErrorFeedback(unittest.TestCase):
    """确保重连失败时前端有明确交互反馈"""

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.pool_js = (root / 'static' / 'js' / 'components' / 'connection-pool.js').read_text(encoding='utf-8')
        self.two_step_js = (root / 'static' / 'js' / 'components' / 'two-step-connection.js').read_text(encoding='utf-8')
        self.app_ui_js = (root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')

    def test_connection_pool_reconnect_handles_http_error_and_shows_structured_error(self):
        reconnect_block = self.pool_js[self.pool_js.index('async function reconnect'):self.pool_js.index('async function disconnect')]
        self.assertIn("await window.reconnectConnectionById(id, { source: 'connection-pool' });", reconnect_block)
        self.assertNotIn("fetch(`${API}/pod/connect`", reconnect_block)
        self.assertIn("if (typeof showPodError === 'function') {", self.pool_js)
        self.assertIn("showPodError(e.message, {", self.pool_js)
        self.assertIn("toast(`重连失败: ${e.message}`, 'error');", self.pool_js)

    def test_pod_connect_returns_false_and_preserves_last_error(self):
        self.assertIn("window._lastPodConnectError = '';", self.two_step_js)
        self.assertIn("window._lastPodConnectError = e.message || 'Pod 连接失败';", self.two_step_js)
        self.assertIn("return false;", self.two_step_js)
        self.assertIn("return true;", self.two_step_js)

    def test_one_click_reconnect_uses_shared_orchestrator(self):
        self.assertIn("async function reconnectConnectionById(connId, options = {}) {", self.app_ui_js)
        self.assertIn("const podReconnectOk = await podConnect({ silentError: true });", self.app_ui_js)
        self.assertIn("throw new Error(window._lastPodConnectError || 'Pod 不存在或无法访问');", self.app_ui_js)
        self.assertIn("const result = await reconnectConnectionById(connId, { source: 'current-connection' });", self.app_ui_js)


if __name__ == '__main__':
    unittest.main()
