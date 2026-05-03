#!/usr/bin/env python3
"""
测试 JAD 后启用 MC 编译按钮

验证:
1. JAD 成功后保存 uploadedFile
2. JAD 成功后启用 btnCompile 按钮
3. MC 编译前检查 uploadedFile 是否为空
"""
import unittest
import re
from pathlib import Path


class TestJadEnablesCompile(unittest.TestCase):
    """测试 JAD 后启用 MC 编译按钮"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_js = (self.root / 'static' / 'js' / 'components' / 'hotfix.js').read_text(encoding='utf-8')

    def test_jad_saves_uploaded_file(self):
        """测试 JAD 成功后保存 uploadedFile"""
        # 应该保存 artifact_path 到 uploadedFile
        self.assertIn('_hfState.uploadedFile = data.artifact_path', self.hotfix_js,
                     "❌ JAD 成功后应该保存 uploadedFile")

    def test_jad_enables_compile_button(self):
        """测试 JAD 成功后启用编译按钮"""
        # 应该启用 btnCompile
        self.assertIn("document.getElementById('btnCompile').disabled = false", self.hotfix_js,
                     "❌ JAD 成功后应该启用 btnCompile 按钮")

    def test_mc_checks_uploaded_file(self):
        """测试 MC 编译前检查 uploadedFile"""
        # 应该检查 uploadedFile 是否为空
        self.assertIn('if (!_hfState.uploadedFile)', self.hotfix_js,
                     "❌ MC 编译前应该检查 uploadedFile")
        
        # 应该有错误提示
        self.assertIn("alert('请先查看源码或上传 Java 文件')", self.hotfix_js,
                     "❌ uploadedFile 为空时应该提示用户")

    def test_jad_shows_artifact_path_in_log(self):
        """测试 JAD 日志显示文件路径"""
        # 应该显示 artifact_path
        self.assertIn("data.artifact_path || '未知路径'", self.hotfix_js,
                     "❌ JAD 日志应该显示 artifact_path")

    def test_mc_has_detailed_logs(self):
        """测试 MC 有详细调试日志"""
        # 应该记录 _hfState
        self.assertIn("_hfState: _hfState", self.hotfix_js,
                     "❌ MC 日志应该记录 _hfState")

    def test_complete_jad_to_compile_flow(self):
        """测试完整的 JAD → 编译流程"""
        issues = []
        
        # 1. JAD 保存 uploadedFile
        if '_hfState.uploadedFile = data.artifact_path' not in self.hotfix_js:
            issues.append("❌ JAD 未保存 uploadedFile")
        
        # 2. JAD 启用编译按钮
        if "document.getElementById('btnCompile').disabled = false" not in self.hotfix_js:
            issues.append("❌ JAD 未启用编译按钮")
        
        # 3. MC 检查 uploadedFile
        if 'if (!_hfState.uploadedFile)' not in self.hotfix_js:
            issues.append("❌ MC 未检查 uploadedFile")
        
        if issues:
            self.fail("JAD → 编译流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
