#!/usr/bin/env python3
"""
测试 _connState 等变量不重复声明

验证:
1. app-ui.js 声明了 _connState, _runtimeInfo, _podConnId, _podPhase
2. two-step-connection.js 不再声明这些变量
"""
import unittest
from pathlib import Path


class TestNoDuplicateVariables(unittest.TestCase):
    """测试变量不重复声明"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.two_step_js = (self.root / 'static' / 'js' / 'components' / 'two-step-connection.js').read_text(encoding='utf-8')

    def test_app_ui_declares_variables(self):
        """测试 app-ui.js 声明了必要的变量"""
        variables = [
            'let _connState',
            'let _runtimeInfo',
            'let _podConnId',
            'let _podPhase'
        ]
        
        for var in variables:
            self.assertIn(var, self.app_ui_js,
                         f"❌ app-ui.js 应该声明 {var}")
        
        print("✅ app-ui.js 声明了所有必要的变量")

    def test_two_step_no_duplicate_conn_state(self):
        """测试 two-step-connection.js 不重复声明 _connState"""
        # 不应该有 let _connState
        self.assertNotIn('let _connState', self.two_step_js,
                        "❌ two-step-connection.js 不应该声明 let _connState")
        
        # 应该有注释说明使用 app-ui.js 的变量
        self.assertIn('由 app-ui.js 声明', self.two_step_js,
                     "✅ 应该有注释说明变量由 app-ui.js 声明")
        
        print("✅ two-step-connection.js 不重复声明 _connState")

    def test_two_step_no_duplicate_pod_conn_id(self):
        """测试 two-step-connection.js 不重复声明 _podConnId"""
        # 不应该有 let _podConnId
        self.assertNotIn('let _podConnId', self.two_step_js,
                        "❌ two-step-connection.js 不应该声明 let _podConnId")
        
        print("✅ two-step-connection.js 不重复声明 _podConnId")

    def test_two_step_no_duplicate_runtime_info(self):
        """测试 two-step-connection.js 不重复声明 _runtimeInfo"""
        # 不应该有 let _runtimeInfo
        self.assertNotIn('let _runtimeInfo', self.two_step_js,
                        "❌ two-step-connection.js 不应该声明 let _runtimeInfo")
        
        print("✅ two-step-connection.js 不重复声明 _runtimeInfo")

    def test_two_step_no_duplicate_pod_phase(self):
        """测试 two-step-connection.js 不重复声明 _podPhase"""
        # 不应该有 let _podPhase
        self.assertNotIn('let _podPhase', self.two_step_js,
                        "❌ two-step-connection.js 不应该声明 let _podPhase")
        
        print("✅ two-step-connection.js 不重复声明 _podPhase")


if __name__ == '__main__':
    unittest.main(verbosity=2)
