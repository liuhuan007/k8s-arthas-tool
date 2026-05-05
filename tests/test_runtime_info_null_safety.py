#!/usr/bin/env python3
"""
验证 two-step-connection.js 的空值保护
"""
import unittest
import os

class TestRuntimeInfoNullSafety(unittest.TestCase):
    """测试 runtime_info 空值保护"""
    
    def setUp(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        js_path = os.path.join(self.project_root, 'static', 'js', 'components', 'two-step-connection.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            self.js = f.read()
    
    def test_runtime_info_assignment_null_safe(self):
        """测试 _runtimeInfo 赋值有空值保护"""
        # 应该有 || null 保护
        self.assertIn('_runtimeInfo = d.runtime || null', self.js,
                     "❌ _runtimeInfo 赋值应该有空值保护: d.runtime || null")
    
    def test_pod_phase_assignment_null_safe(self):
        """测试 _podPhase 赋值有空值保护"""
        self.assertIn('_podPhase = d.pod_phase || null', self.js,
                     "❌ _podPhase 赋值应该有空值保护: d.pod_phase || null")
    
    def test_runtime_type_access_null_safe_in_updateRuntimeDisplay(self):
        """测试 updateRuntimeDisplay 中访问 runtime_type 有空值保护"""
        # 不应该直接访问 _runtimeInfo.runtime_type
        self.assertNotIn('runtimeIcons[_runtimeInfo.runtime_type]', self.js,
                        "❌ 不应该直接访问 _runtimeInfo.runtime_type")
        
        # 应该有空值保护
        self.assertIn('const runtimeType = _runtimeInfo ? _runtimeInfo.runtime_type', self.js,
                     "❌ runtimeType 应该有空值保护")
    
    def test_runtime_type_access_null_safe_in_podConnect(self):
        """测试 podConnect 中访问 runtime_type 有空值保护"""
        # 查找 updateConnectionStatus 调用
        lines = self.js.split('\n')
        for i, line in enumerate(lines):
            if '✓ Pod 连接成功' in line and '_runtimeInfo' in line:
                # 不应该直接访问 _runtimeInfo.runtime_type
                self.assertNotIn('_runtimeInfo.runtime_type', line,
                               f"❌ 第 {i+1} 行不应该直接访问 _runtimeInfo.runtime_type")
                break
    
    def test_update_runtime_display_handles_null(self):
        """测试 updateRuntimeDisplay 处理 null 的情况"""
        # 应该将 'unknown' 转换为 '未知'
        self.assertIn("runtimeType === 'unknown' ? '未知' : runtimeType", self.js,
                     "❌ 应该将 'unknown' 转换为 '未知'")

if __name__ == '__main__':
    unittest.main(verbosity=2)
