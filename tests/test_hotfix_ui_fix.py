#!/usr/bin/env python3
"""
P1b-1 热修复UI体验修复测试

验证:
1. WORKSPACE_META 包含 hotfix
2. updateWorkspaceHead 正确处理 hotfix tab
3. 菜单样式优化(字体/间距/渐变/阴影)
"""
import unittest
import re
from pathlib import Path


class TestHotfixUIFix(unittest.TestCase):
    """测试热修复 UI 体验修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.css = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')

    # ── 问题 1: 工作台标题修复 ──────────────────────────────────

    def test_workspace_meta_has_hotfix(self):
        """测试 WORKSPACE_META 包含 hotfix 配置"""
        self.assertIn('hotfix:', self.app_ui_js)
        self.assertIn('Hotfix Workbench', self.app_ui_js)
        self.assertIn('热修复', self.app_ui_js)

    def test_hotfix_meta_has_description(self):
        """测试 hotfix 描述包含完整链路"""
        meta_match = re.search(r"hotfix:\s*\{([^}]+)\}", self.app_ui_js)
        self.assertIsNotNone(meta_match, "未找到 hotfix 配置")
        self.assertIn('jad', meta_match.group(1))
        self.assertIn('redefine', meta_match.group(1))

    def test_updateWorkspaceHead_handles_hotfix(self):
        """测试 updateWorkspaceHead 正确处理 hotfix tab"""
        # 应该有 hotfix 的配置
        self.assertIn('hotfix:', self.app_ui_js)
        # updateWorkspaceHead 应该统一处理所有 tab(不再特殊隐藏)
        func_match = re.search(
            r'function updateWorkspaceHead\(tab\)\s*\{(.*?)\n\}',
            self.app_ui_js,
            re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 updateWorkspaceHead 函数")
        func_body = func_match.group(1)
        
        # 不应该有隐藏 header 的逻辑
        self.assertNotIn("kicker.style.display = 'none'", func_body)
        self.assertNotIn("title.style.display = 'none'", func_body)

    def test_updateWorkspaceHead_restores_other_tabs(self):
        """测试 updateWorkspaceHead 统一处理所有 tab"""
        # 所有 tab 都应该显示 header,统一处理
        func_match = re.search(
            r'function updateWorkspaceHead\(tab\)\s*\{(.*?)\n\}',
            self.app_ui_js,
            re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 updateWorkspaceHead 函数")
        func_body = func_match.group(1)
        
        # 应该有统一的更新逻辑
        self.assertIn('meta.kicker', func_body)
        self.assertIn('meta.title', func_body)
        self.assertIn('meta.sub', func_body)
        # 不应该有条件隐藏
        self.assertNotIn("style.display = 'none'", func_body)

    # ── 问题 3: 菜单样式优化 ─────────────────────────────────────

    def test_menu_item_font_size_increased(self):
        """测试菜单字体增大到 11.5px"""
        item_style = re.search(r'\.side-nav-item\{([^}]+)\}', self.css)
        self.assertIsNotNone(item_style, "未找到 .side-nav-item 样式")
        self.assertIn('11.5px', item_style.group(1), "字体应该是 11.5px")

    def test_menu_item_padding_increased(self):
        """测试菜单内边距增大"""
        item_style = re.search(r'\.side-nav-item\{([^}]+)\}', self.css)
        self.assertIn('9px 12px', item_style.group(1), "内边距应该是 9px 12px")

    def test_menu_icon_size_increased(self):
        """测试图标尺寸增大到 24px"""
        icon_style = re.search(r'\.side-nav-item > span:first-child\{([^}]+)\}', self.css)
        self.assertIsNotNone(icon_style, "未找到图标样式")
        self.assertIn('24px', icon_style.group(1), "图标尺寸应该是 24px")
        self.assertIn('13px', icon_style.group(1), "图标字体应该是 13px")

    def test_menu_hover_has_gradient(self):
        """测试 hover 状态使用渐变背景"""
        hover_style = re.search(r'\.side-nav-item:hover\{([^}]+)\}', self.css)
        self.assertIsNotNone(hover_style, "未找到 hover 样式")
        self.assertIn('linear-gradient', hover_style.group(1), "hover 应该使用渐变")

    def test_menu_hover_has_shadow(self):
        """测试 hover 状态有阴影效果"""
        hover_style = re.search(r'\.side-nav-item:hover\{([^}]+)\}', self.css)
        self.assertIn('box-shadow', hover_style.group(1), "hover 应该有阴影")

    def test_menu_active_has_gradient(self):
        """测试选中状态使用多色渐变"""
        on_style = re.search(r'\.side-nav-item\.on\{([^}]+)\}', self.css)
        self.assertIsNotNone(on_style, "未选中状态样式")
        self.assertIn('linear-gradient', on_style.group(1), "选中应该使用渐变")
        # 多色渐变(蓝色+紫色)
        self.assertIn('rgba(0,122,255', on_style.group(1))
        self.assertIn('rgba(167,139,250', on_style.group(1))

    def test_menu_active_has_glow(self):
        """测试选中状态有发光效果"""
        on_style = re.search(r'\.side-nav-item\.on\{([^}]+)\}', self.css)
        # 应该有多个 box-shadow(发光效果)
        shadows = on_style.group(1).count('box-shadow')
        self.assertGreaterEqual(shadows, 1, "选中状态应该有发光效果")

    def test_menu_active_text_white(self):
        """测试选中状态文字为白色"""
        on_style = re.search(r'\.side-nav-item\.on\{([^}]+)\}', self.css)
        self.assertIn('color:#fff', on_style.group(1), "选中文字应该是白色")

    def test_menu_active_icon_white(self):
        """测试选中状态图标为白色"""
        icon_on = re.search(r'\.side-nav-item\.on > span:first-child\{([^}]+)\}', self.css)
        self.assertIsNotNone(icon_on, "未找到选中图标样式")
        self.assertIn('color:#fff', icon_on.group(1), "选中图标应该是白色")

    def test_menu_hover_transform_increased(self):
        """测试 hover 位移增加到 3px"""
        hover_style = re.search(r'\.side-nav-item:hover\{([^}]+)\}', self.css)
        self.assertIn('translateX(3px)', hover_style.group(1), "hover 位移应该是 3px")

    def test_menu_transition_smooth(self):
        """测试过渡动画时间为 0.2s"""
        item_style = re.search(r'\.side-nav-item\{([^}]+)\}', self.css)
        self.assertIn('.2s', item_style.group(1), "过渡时间应该是 0.2s")

    def test_menu_letter_spacing(self):
        """测试菜单有字间距"""
        item_style = re.search(r'\.side-nav-item\{([^}]+)\}', self.css)
        self.assertIn('letter-spacing', item_style.group(1), "应该有字间距")

    # ── 综合验证 ─────────────────────────────────────────────────

    def test_complete_ui_fix(self):
        """测试完整 UI 修复"""
        # 1. 工作台标题配置
        self.assertIn('hotfix:', self.app_ui_js)
        
        # 2. 统一处理逻辑(不再特殊隐藏)
        func_match = re.search(
            r'function updateWorkspaceHead\(tab\)\s*\{(.*?)\n\}',
            self.app_ui_js,
            re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 updateWorkspaceHead 函数")
        func_body = func_match.group(1)
        # 应该有统一更新逻辑
        self.assertIn('meta.kicker', func_body)
        self.assertIn('meta.title', func_body)
        
        # 3. 菜单样式
        self.assertIn('11.5px', self.css)
        self.assertIn('24px', self.css)
        self.assertIn('linear-gradient', self.css)


if __name__ == '__main__':
    unittest.main()
