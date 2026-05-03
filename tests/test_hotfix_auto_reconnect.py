#!/usr/bin/env python3
"""
测试热修复自动重建连接

验证:
1. _get_connection 支持自动重建
2. 内存中不存在时调用 _ensure_connection
3. 重建失败时返回友好错误信息
"""
import unittest
import re
from pathlib import Path


class TestHotfixAutoReconnect(unittest.TestCase):
    """测试热修复自动重建连接"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_py = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')

    def test_get_connection_imports_ensure_connection(self):
        """测试 _get_connection 导入 _ensure_connection"""
        self.assertIn('from server import _connections, _connections_lock, _ensure_connection', self.hotfix_py,
                     "❌ 应该导入 _ensure_connection")

    def test_get_connection_has_two_step_logic(self):
        """测试 _get_connection 有两步逻辑"""
        # 第一步: 从内存获取
        self.assertIn('# ✅ 第一步: 尝试从内存获取', self.hotfix_py,
                     "❌ 应该有第一步: 从内存获取")
        
        # 第二步: 自动重建
        self.assertIn('# ✅ 第二步: 内存中不存在,尝试自动重建', self.hotfix_py,
                     "❌ 应该有第二步: 自动重建")

    def test_get_connection_calls_ensure_connection(self):
        """测试 _get_connection 调用 _ensure_connection"""
        self.assertIn('_ensure_connection(conn_id, d)', self.hotfix_py,
                     "❌ 应该调用 _ensure_connection")

    def test_get_connection_parses_conn_id(self):
        """测试 _get_connection 解析 conn_id"""
        self.assertIn("parts = conn_id.split('/')", self.hotfix_py,
                     "❌ 应该解析 conn_id")
        
        self.assertIn('cluster_name = parts[0]', self.hotfix_py,
                     "❌ 应该提取 cluster_name")
        
        self.assertIn('namespace = parts[1]', self.hotfix_py,
                     "❌ 应该提取 namespace")
        
        self.assertIn('pod_name = parts[2]', self.hotfix_py,
                     "❌ 应该提取 pod_name")

    def test_get_connection_has_friendly_error(self):
        """测试 _get_connection 返回友好错误信息"""
        self.assertIn('连接已丢失，请重新建立连接', self.hotfix_py,
                     "❌ 应该返回友好的错误信息")

    def test_get_connection_has_debug_logs(self):
        """测试 _get_connection 有调试日志"""
        self.assertIn("log.info(f\"[_get_connection] 内存中未找到,尝试自动重建 conn_id={conn_id}\")", self.hotfix_py,
                     "❌ 应该有自动重建调试日志")
        
        self.assertIn("log.info(f\"[_get_connection] 自动重建成功 conn_id={conn_id}\")", self.hotfix_py,
                     "❌ 应该有重建成功日志")

    def test_complete_auto_reconnect_flow(self):
        """测试完整的自动重建流程"""
        issues = []
        
        # 1. 导入
        if '_ensure_connection' not in self.hotfix_py:
            issues.append("❌ 未导入 _ensure_connection")
        
        # 2. 两步逻辑
        if '# ✅ 第一步: 尝试从内存获取' not in self.hotfix_py:
            issues.append("❌ 缺少第一步逻辑")
        
        if '# ✅ 第二步: 内存中不存在,尝试自动重建' not in self.hotfix_py:
            issues.append("❌ 缺少第二步逻辑")
        
        # 3. conn_id 解析
        if "parts = conn_id.split('/')" not in self.hotfix_py:
            issues.append("❌ 未解析 conn_id")
        
        # 4. 调用 _ensure_connection
        if '_ensure_connection(conn_id, d)' not in self.hotfix_py:
            issues.append("❌ 未调用 _ensure_connection")
        
        # 5. 错误处理
        if '连接已丢失，请重新建立连接' not in self.hotfix_py:
            issues.append("❌ 缺少友好错误信息")
        
        if issues:
            self.fail("自动重建流程存在问题:\n" + "\n".join(issues))

    def test_no_direct_return_on_missing_connection(self):
        """测试不在内存缺失时直接返回错误"""
        # 不应该有 "连接不存在" 的直接返回
        if 'return None, f"连接不存在 (conn_id={conn_id})"' in self.hotfix_py:
            # 检查是否在自动重建之前
            lines = self.hotfix_py.split('\n')
            for i, line in enumerate(lines):
                if 'return None, f"连接不存在 (conn_id={conn_id})"' in line:
                    # 检查后面是否有 _ensure_connection 调用
                    remaining = '\n'.join(lines[i:])
                    if '_ensure_connection' not in remaining:
                        self.fail("❌ 内存缺失时直接返回错误,未尝试自动重建")


if __name__ == '__main__':
    unittest.main()
