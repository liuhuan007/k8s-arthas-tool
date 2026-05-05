#!/usr/bin/env python3
"""
测试热修复 MC 编译功能

验证:
1. 前端传递正确的字段名 java_file_path
2. 后端返回正确的字段名 class_file
3. MC 命令超时设置合理
4. 详细的调试日志
"""
import unittest
import re
from pathlib import Path


class TestHotfixMcCompile(unittest.TestCase):
    """测试热修复 MC 编译功能"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_js = (self.root / 'static' / 'js' / 'components' / 'hotfix.js').read_text(encoding='utf-8')
        self.hotfix_service_py = (self.root / 'services' / 'hotfix_service.py').read_text(encoding='utf-8')

    def test_frontend_uses_java_file_path(self):
        """测试前端使用正确的字段名 java_file_path"""
        # 不应该使用 source_file
        if 'source_file: _hfState.uploadedFile' in self.hotfix_js:
            self.fail("❌ 前端仍在使用 source_file 字段,应使用 java_file_path")
        
        # 应该使用 java_file_path
        self.assertIn('java_file_path: _hfState.uploadedFile', self.hotfix_js,
                     "❌ 前端应该使用 java_file_path 字段")

    def test_backend_returns_class_file(self):
        """测试后端返回 class_file 字段"""
        # 应该返回 class_file
        self.assertIn('"class_file": class_file_path', self.hotfix_service_py,
                     "❌ 后端应该返回 class_file 字段")

    def test_mc_timeout_increased(self):
        """测试 MC 超时增加到 60s"""
        self.assertIn('timeout_ms=60000', self.hotfix_service_py,
                     "❌ MC 超时应该设置为 60000ms")

    def test_mc_has_debug_logs(self):
        """测试 MC 有详细调试日志"""
        # 应该有命令日志
        self.assertIn('log.info("[MC] 执行命令:', self.hotfix_service_py,
                     "❌ 应该记录 MC 命令")
        
        # 应该有响应日志
        self.assertIn('log.info("[MC] 响应:', self.hotfix_service_py,
                     "❌ 应该记录 MC 响应")
        
        # 应该有文件数量日志
        self.assertIn('log.info("[MC] 找到', self.hotfix_service_py,
                     "❌ 应该记录找到的 .class 文件数量")

    def test_mc_extracts_from_body_results(self):
        """测试 MC 从 body.results 提取输出"""
        self.assertIn("body.get('results', [])", self.hotfix_service_py,
                     "❌ 应该从 body.results 提取输出")
        
        self.assertIn("results[0].get('java_class', '')", self.hotfix_service_py,
                     "❌ 应该提取 java_class 字段")

    def test_frontend_has_debug_logs(self):
        """测试前端有调试日志"""
        # 应该记录开始编译日志
        self.assertIn("console.log('[Hotfix MC] 开始编译:'", self.hotfix_js,
                     "❌ 前端应该记录开始编译")
        
        self.assertIn("console.log('[Hotfix MC] 响应:'", self.hotfix_js,
                     "❌ 前端应该记录响应")

    def test_frontend_handles_empty_output(self):
        """测试前端处理空输出"""
        # ✅ 更新: 现在有更详细的空输出处理
        self.assertIn("编译成功,但未生成 .class 文件", self.hotfix_js,
                     "❌ 前端应该处理空输出情况")
        self.assertIn("可能原因:", self.hotfix_js,
                     "❌ 前端应该提示可能原因")

    def test_complete_mc_flow(self):
        """测试完整的 MC 编译流程"""
        issues = []
        
        # 1. 前端字段名
        if 'source_file: _hfState.uploadedFile' in self.hotfix_js:
            issues.append("❌ 前端仍在使用 source_file")
        
        if 'java_file_path: _hfState.uploadedFile' not in self.hotfix_js:
            issues.append("❌ 前端未使用 java_file_path")
        
        # 2. 后端字段名
        if '"class_file": class_file_path' not in self.hotfix_service_py:
            issues.append("❌ 后端未返回 class_file")
        
        # 3. 超时设置
        if 'timeout_ms=60000' not in self.hotfix_service_py:
            issues.append("❌ MC 超时未设置为 60s")
        
        # 4. 调试日志
        if 'log.info("[MC] 执行命令:' not in self.hotfix_service_py:
            issues.append("❌ 缺少 MC 命令日志")
        
        if issues:
            self.fail("MC 编译流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
