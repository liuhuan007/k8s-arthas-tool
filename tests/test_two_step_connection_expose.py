#!/usr/bin/env python3
"""
测试 two-step-connection 全局函数暴露修复

验证:
1. 不重复定义 ConnectionState
2. 在 DOMContentLoaded 后暴露全局函数
3. 使用 connection-store.js 中的 ConnectionState
"""
import unittest
import re
from pathlib import Path


class TestTwoStepConnectionExpose(unittest.TestCase):
    """测试 two-step-connection 全局函数暴露修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.two_step_js = (self.root / 'static' / 'js' / 'components' / 'two-step-connection.js').read_text(encoding='utf-8')

    def test_no_duplicate_connection_state(self):
        """测试不重复定义 ConnectionState"""
        # 不应该有 const ConnectionState = { 定义
        self.assertNotIn('const ConnectionState = {', self.two_step_js,
                        "❌ two-step-connection.js 不应该重复定义 ConnectionState")
        
        # 应该使用 connection-store.js 中的 ConnectionState
        self.assertIn('typeof ConnectionState', self.two_step_js,
                     "✅ 应该检查 ConnectionState 是否存在")
        
        print("✅ 不重复定义 ConnectionState,使用 connection-store.js 中的定义")

    def test_expose_functions_in_dom_ready(self):
        """测试在 DOMContentLoaded 后暴露全局函数"""
        # 应该有 _exposeGlobalFunctions 函数
        self.assertIn('function _exposeGlobalFunctions', self.two_step_js,
                     "✅ 应该有 _exposeGlobalFunctions 函数")
        
        # 应该在 DOMContentLoaded 中调用
        self.assertIn("document.addEventListener('DOMContentLoaded', _exposeGlobalFunctions)", 
                     self.two_step_js,
                     "✅ 应该在 DOMContentLoaded 后暴露全局函数")
        
        print("✅ 在 DOMContentLoaded 后暴露全局函数")

    def test_no_duplicate_expose_in_script_load(self):
        """测试不在脚本加载时立即暴露函数"""
        # 不应该在脚本顶部直接暴露 (旧代码)
        # 检查是否有 window.podConnect = podConnect 在第807行之前(立即执行)
        lines = self.two_step_js.split('\n')
        
        # 找到 _exposeGlobalFunctions 函数定义的位置
        expose_func_line = None
        for i, line in enumerate(lines):
            if 'function _exposeGlobalFunctions' in line:
                expose_func_line = i
                break
        
        self.assertIsNotNone(expose_func_line, "应该定义 _exposeGlobalFunctions 函数")
        
        # 在该函数定义之前，不应该有 window.podConnect = podConnect
        before_expose = '\n'.join(lines[:expose_func_line])
        self.assertNotIn('window.podConnect = podConnect', before_expose,
                        "❌ 不应该在 _exposeGlobalFunctions 之前直接暴露 podConnect")
        
        print("✅ 不在脚本加载时立即暴露函数,延迟到 DOMContentLoaded")

    def test_expose_all_functions_in_dom_ready(self):
        """测试暴露所有必要的全局函数"""
        # 应该有所有函数的暴露
        self.assertIn('window.podConnect = podConnect', self.two_step_js,
                     "✅ 应该暴露 podConnect")
        self.assertIn('window.podDisconnect = podDisconnect', self.two_step_js,
                     "✅ 应该暴露 podDisconnect")
        self.assertIn('window.upgradeToArthas = upgradeToArthas', self.two_step_js,
                     "✅ 应该暴露 upgradeToArthas")
        self.assertIn('window.getConnectionState = getConnectionState', self.two_step_js,
                     "✅ 应该暴露 getConnectionState")
        
        print("✅ 暴露所有必要的全局函数")


if __name__ == '__main__':
    unittest.main(verbosity=2)
