#!/usr/bin/env python3
"""连接池重连与健康状态文案回归测试"""

import unittest
from pathlib import Path


class TestConnectionPoolReconnectFixes(unittest.TestCase):
    """覆盖连接池重连验活与 warn 文案修复"""

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.pod_apis_py = (root / 'api' / 'pod_apis.py').read_text(encoding='utf-8')
        self.pool_js = (root / 'static' / 'js' / 'components' / 'connection-pool.js').read_text(encoding='utf-8')

    def test_pod_reconnect_reuse_checks_real_liveness(self):
        """复用旧 Pod 连接前应调用 is_alive 做真实验活"""
        self.assertIn("conn.is_alive() if hasattr(conn, 'is_alive') else True", self.pod_apis_py)
        self.assertIn('stale connection removed before reconnect', self.pod_apis_py)

    def test_warn_badge_text_is_clearer_than_weak(self):
        """warn 徽标文案应避免使用含义不清的“弱”"""
        self.assertIn("return '⚠ 不稳';", self.pool_js)
        self.assertNotIn("return '⚠ 弱';", self.pool_js)

    def test_warn_health_text_explains_unstable_connection(self):
        """warn 详情文案应明确表达连接不稳定"""
        self.assertIn("warn: '⚠ 连接不稳定'", self.pool_js)


if __name__ == '__main__':
    unittest.main()
