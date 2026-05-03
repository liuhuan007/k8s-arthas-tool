#!/usr/bin/env python3
"""
P1b-1 热修复前端导航修复测试

验证:
1. switchTab 函数包含 hotfix
2. ConnectionGuard REQUIREMENTS 包含 hotfix
3. 菜单选中状态样式正确
"""
import unittest
from pathlib import Path


class TestHotfixNavigationFix(unittest.TestCase):
    """测试热修复导航修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.connection_guard_js = (self.root / 'static' / 'js' / 'components' / 'connection-guard.js').read_text(encoding='utf-8')

    # ── switchTab 修复验证 ─────────────────────────────────────────

    def test_switchTab_allTabs_includes_hotfix(self):
        """测试 switchTab 的 allTabs 数组包含 hotfix"""
        # 查找 allTabs 定义
        self.assertIn("'hotfix'", self.app_ui_js)
        # 确保在 allTabs 数组中
        import re
        allTabs_match = re.search(r"const allTabs = \[([^\]]+)\]", self.app_ui_js)
        self.assertIsNotNone(allTabs_match, "未找到 allTabs 数组")
        self.assertIn("'hotfix'", allTabs_match.group(1), "allTabs 数组未包含 'hotfix'")

    def test_switchTab_tabMap_includes_hotfix(self):
        """测试 switchTab 的 tabMap 包含 hotfix 映射"""
        import re
        tabMap_match = re.search(r"const tabMap = \{([^}]+)\}", self.app_ui_js)
        self.assertIsNotNone(tabMap_match, "未找到 tabMap 对象")
        self.assertIn("'hotfix'", tabMap_match.group(1), "tabMap 未包含 'hotfix'")

    def test_switchTab_hotfix_index_correct(self):
        """测试 hotfix 在 tabMap 中的索引正确(应该是 3)"""
        import re
        tabMap_match = re.search(r"const tabMap = \{([^}]+)\}", self.app_ui_js)
        self.assertIn("3:'hotfix'", tabMap_match.group(1), "hotfix 索引应该是 3")

    # ── ConnectionGuard 修复验证 ───────────────────────────────────

    def test_connectionGuard_requirements_includes_hotfix(self):
        """测试 ConnectionGuard REQUIREMENTS 包含 hotfix"""
        self.assertIn("'hotfix'", self.connection_guard_js)

    def test_connectionGuard_hotfix_requires_arthas(self):
        """测试 hotfix 需要 arthas 连接"""
        import re
        # 查找 hotfix 的配置
        hotfix_match = re.search(r"'hotfix':\s*'(\w+)'", self.connection_guard_js)
        self.assertIsNotNone(hotfix_match, "未找到 hotfix 配置")
        self.assertEqual(hotfix_match.group(1), 'arthas', "hotfix 应该要求 arthas 连接")

    def test_connectionGuard_hotfix_has_comment(self):
        """测试 hotfix 配置有注释说明"""
        import re
        hotfix_line = re.search(r"'hotfix'.*?//.*\n", self.connection_guard_js)
        self.assertIsNotNone(hotfix_line, "hotfix 配置应该有注释")
        self.assertIn('热修复', hotfix_line.group(0), "注释应该包含'热修复'")

    # ── 菜单选中状态验证 ──────────────────────────────────────────

    def test_sideNav_item_on_style_exists(self):
        """测试 .side-nav-item.on 样式存在"""
        css_file = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
        self.assertIn('.side-nav-item.on', css_file)

    def test_sideNav_on_has_visible_background(self):
        """测试选中状态有明显背景色"""
        css_file = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
        import re
        # 查找 .side-nav-item.on 的样式
        on_style = re.search(r'\.side-nav-item\.on\{([^}]+)\}', css_file)
        self.assertIsNotNone(on_style, "未找到 .side-nav-item.on 样式")
        # 应该有 background 或 border
        self.assertTrue(
            'background' in on_style.group(1) or 'border' in on_style.group(1),
            "选中状态应该有 background 或 border"
        )

    def test_tab_on_style_exists(self):
        """测试 .tb-tab.on 样式存在"""
        css_file = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
        self.assertIn('.tb-tab.on', css_file)

    # ── 面板显示验证 ──────────────────────────────────────────────

    def test_panel_hotfix_has_correct_id(self):
        """测试热修复面板 ID 正确"""
        index_html = (self.root / 'static' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="panel-hotfix"', index_html)

    def test_panel_on_display_flex(self):
        """测试 .panel.on 使用 display:flex"""
        css_file = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
        import re
        panel_on = re.search(r'\.panel\.on\{([^}]+)\}', css_file)
        self.assertIsNotNone(panel_on, "未找到 .panel.on 样式")
        self.assertIn('display:flex', panel_on.group(1), ".panel.on 应该使用 display:flex")

    # ── 完整流程验证 ──────────────────────────────────────────────

    def test_hotfix_complete_flow(self):
        """测试热修复完整导航流程"""
        # 1. 菜单按钮存在
        index_html = (self.root / 'static' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('data-nav-tab="hotfix"', index_html)
        
        # 2. Tab 栏存在
        self.assertIn('id="tab-hotfix"', index_html)
        
        # 3. 面板存在
        self.assertIn('id="panel-hotfix"', index_html)
        
        # 4. switchTab 支持
        self.assertIn("'hotfix'", self.app_ui_js)
        
        # 5. ConnectionGuard 配置
        self.assertIn("'hotfix':", self.connection_guard_js)


if __name__ == '__main__':
    unittest.main()
