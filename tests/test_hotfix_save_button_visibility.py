#!/usr/bin/env python3
"""
测试热修复在线编辑保存按钮显示修复

验证:
1. hotfixEnableEdit() 检查元素存在性
2. 保存按钮正确显示
3. 步骤 2 区域自动显示 (如果被隐藏)
4. 自动滚动到编辑区域
"""
import unittest
from pathlib import Path


class TestHotfixSaveButtonVisibility(unittest.TestCase):
    """测试热修复保存按钮显示修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_js = (self.root / 'static' / 'js' / 'components' / 'hotfix.js').read_text(encoding='utf-8')

    def test_checks_editor_exists(self):
        """测试检查编辑器元素存在"""
        self.assertIn("if (!editor)", self.hotfix_js,
                     "❌ 应检查 editor 元素是否存在")
        
        self.assertIn('hfEditor 元素不存在', self.hotfix_js,
                     " 应有 editor 不存在的错误提示")

    def test_checks_save_button_exists(self):
        """测试检查保存按钮元素存在"""
        self.assertIn("if (!saveBtn)", self.hotfix_js,
                     "❌ 应检查 saveBtn 元素是否存在")
        
        self.assertIn('btnSaveEdit 元素不存在', self.hotfix_js,
                     "❌ 应有 saveBtn 不存在的错误提示")

    def test_shows_save_button(self):
        """测试显示保存按钮"""
        self.assertIn("saveBtn.style.display = 'inline-block'", self.hotfix_js,
                     "❌ 应显示保存按钮")

    def test_shows_step2_container(self):
        """测试显示步骤 2 容器"""
        # 应查找并显示步骤 2 容器
        self.assertIn("editor.closest('.hotfix-step')", self.hotfix_js,
                     " 应查找步骤 2 容器")
        
        self.assertIn("step2Container.style.display = ''", self.hotfix_js,
                     " 应显示步骤 2 容器")

    def test_scrolls_to_editor(self):
        """测试滚动到编辑器"""
        self.assertIn("step2Container.scrollIntoView", self.hotfix_js,
                     "❌ 应滚动到编辑器区域")

    def test_has_debug_logs(self):
        """测试包含调试日志"""
        self.assertIn("[Hotfix EnableEdit]", self.hotfix_js,
                     "❌ 应有调试日志")
        
        self.assertIn("saveBtn 当前 display", self.hotfix_js,
                     "❌ 应记录按钮当前状态")
        
        self.assertIn("保存按钮已显示", self.hotfix_js,
                     "❌ 应记录按钮显示成功")

    def test_complete_enable_edit_flow(self):
        """测试完整的启用编辑流程"""
        issues = []
        
        # 1. 检查元素存在
        if "if (!editor)" not in self.hotfix_js:
            issues.append("❌ 未检查 editor 存在")
        
        if "if (!saveBtn)" not in self.hotfix_js:
            issues.append("❌ 未检查 saveBtn 存在")
        
        # 2. 显示步骤 2 容器
        if "step2Container.style.display = ''" not in self.hotfix_js:
            issues.append("❌ 未显示步骤 2 容器")
        
        # 3. 显示保存按钮
        if "saveBtn.style.display = 'inline-block'" not in self.hotfix_js:
            issues.append("❌ 未显示保存按钮")
        
        # 4. 滚动到编辑器
        if "scrollIntoView" not in self.hotfix_js:
            issues.append("❌ 未滚动到编辑器")
        
        # 5. 设置编辑器值
        if "editor.value = _hfState.sourceCode" not in self.hotfix_js:
            issues.append("❌ 未设置编辑器值")
        
        # 6. 显示状态提示
        if "editStatus.style.display = 'block'" not in self.hotfix_js:
            issues.append("❌ 未显示状态提示")
        
        if issues:
            self.fail("启用编辑流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
