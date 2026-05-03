#!/usr/bin/env python3
"""
测试热修复在线编辑保存功能

验证:
1. 前端有保存按钮 (btnSaveEdit)
2. 前端有编辑状态提示 (hfEditStatus)
3. 前端检测未保存修改 (hasUnsavedChanges)
4. 编译前检查未保存状态
5. 后端有 /save-edit 路由
6. 后端有 save_edit_content 方法
"""
import unittest
import re
from pathlib import Path


class TestHotfixSaveEdit(unittest.TestCase):
    """测试热修复在线编辑保存功能"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_js = (self.root / 'static' / 'js' / 'components' / 'hotfix.js').read_text(encoding='utf-8')
        self.index_html = (self.root / 'static' / 'index.html').read_text(encoding='utf-8')
        self.hotfix_api = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')
        self.hotfix_service = (self.root / 'services' / 'hotfix_service.py').read_text(encoding='utf-8')

    def test_html_has_save_button(self):
        """测试 HTML 有保存按钮"""
        self.assertIn('id="btnSaveEdit"', self.index_html,
                     "❌ HTML 应该有 btnSaveEdit 按钮")
        self.assertIn('onclick="hotfixSaveEdit()"', self.index_html,
                     "❌ 保存按钮应该调用 hotfixSaveEdit()")

    def test_html_has_edit_status(self):
        """测试 HTML 有编辑状态提示"""
        self.assertIn('id="hfEditStatus"', self.index_html,
                     "❌ HTML 应该有 hfEditStatus 状态提示")

    def test_js_has_save_edit_function(self):
        """测试 JS 有保存编辑函数"""
        self.assertIn('async function hotfixSaveEdit()', self.hotfix_js,
                     "❌ 应该有 hotfixSaveEdit 函数")

    def test_js_tracks_unsaved_changes(self):
        """测试 JS 跟踪未保存修改"""
        # 应该有 hasUnsavedChanges 标记
        self.assertIn('_hfState.hasUnsavedChanges = true', self.hotfix_js,
                     "❌ 应该设置 hasUnsavedChanges = true")
        
        # 应该监听 input 事件
        self.assertIn("editor.addEventListener('input'", self.hotfix_js,
                     "❌ 应该监听 editor input 事件")

    def test_compile_checks_unsaved_changes(self):
        """测试编译前检查未保存修改"""
        # 应该有未保存检测
        self.assertIn('_hfState.hasUnsavedChanges', self.hotfix_js,
                     "❌ 编译前应该检查 hasUnsavedChanges")
        
        # 应该有确认对话框
        self.assertIn('检测到未保存的修改', self.hotfix_js,
                     "❌ 应该提示用户有未保存的修改")

    def test_backend_has_save_edit_route(self):
        """测试后端有 save-edit 路由"""
        self.assertIn("@hotfix_bp.route('/save-edit'", self.hotfix_api,
                     "❌ 后端应该有 /save-edit 路由")
        
        self.assertIn('def hotfix_save_edit():', self.hotfix_api,
                     "❌ 后端应该有 hotfix_save_edit 函数")

    def test_backend_has_save_edit_method(self):
        """测试后端服务有保存方法"""
        self.assertIn('def save_edit_content(', self.hotfix_service,
                     "❌ 服务应该有 save_edit_content 方法")

    def test_save_writes_file_content(self):
        """测试保存方法写入文件内容"""
        # 应该有 write_text 调用
        self.assertIn('path.write_text(content', self.hotfix_service,
                     "❌ 应该调用 write_text 写入内容")

    def test_save_validates_file_exists(self):
        """测试保存方法验证文件存在"""
        # 应该检查文件是否存在
        self.assertIn('if not path.exists()', self.hotfix_service,
                     "❌ 应该检查文件是否存在")

    def test_complete_save_edit_flow(self):
        """测试完整的保存编辑流程"""
        issues = []
        
        # 1. 前端保存按钮
        if 'id="btnSaveEdit"' not in self.index_html:
            issues.append("❌ HTML 缺少保存按钮")
        
        # 2. 前端保存函数
        if 'async function hotfixSaveEdit()' not in self.hotfix_js:
            issues.append("❌ JS 缺少保存函数")
        
        # 3. 未保存检测
        if '_hfState.hasUnsavedChanges' not in self.hotfix_js:
            issues.append("❌ JS 未跟踪未保存状态")
        
        # 4. 编译前检查
        if '检测到未保存的修改' not in self.hotfix_js:
            issues.append("❌ 编译前未检查未保存状态")
        
        # 5. 后端路由
        if "/save-edit" not in self.hotfix_api:
            issues.append("❌ 后端缺少 /save-edit 路由")
        
        # 6. 后端方法
        if 'def save_edit_content(' not in self.hotfix_service:
            issues.append("❌ 服务缺少 save_edit_content 方法")
        
        if issues:
            self.fail("保存编辑流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
