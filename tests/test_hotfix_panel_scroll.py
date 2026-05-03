#!/usr/bin/env python3
"""
测试热修复面板滚动条修复

验证:
1. #panel-hotfix 允许垂直滚动 (overflow-y: auto)
2. 隐藏水平滚动 (overflow-x: hidden)
3. 自定义滚动条样式
"""
import unittest
from pathlib import Path


class TestHotfixPanelScroll(unittest.TestCase):
    """测试热修复面板滚动条修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_css = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')

    def test_hotfix_panel_allows_vertical_scroll(self):
        """测试热修复面板允许垂直滚动"""
        # 应有 overflow-y: auto
        self.assertIn('#panel-hotfix.panel.on {', self.app_css,
                     "❌ 应有 #panel-hotfix.panel.on 选择器")
        
        self.assertIn('overflow-y: auto', self.app_css,
                     "❌ 应设置 overflow-y: auto")

    def test_hotfix_panel_hides_horizontal_scroll(self):
        """测试热修复面板隐藏水平滚动"""
        self.assertIn('overflow-x: hidden', self.app_css,
                     "❌ 应设置 overflow-x: hidden")

    def test_hotfix_panel_has_custom_scrollbar(self):
        """测试热修复面板有自定义滚动条"""
        # 应有滚动条样式
        self.assertIn('#panel-hotfix.panel.on::-webkit-scrollbar', self.app_css,
                     "❌ 应有自定义滚动条样式")

    def test_scrollbar_width(self):
        """测试滚动条宽度"""
        # 检查滚动条样式块中有 width: 6px
        self.assertIn('width: 6px', self.app_css,
                     " 滚动条宽度应为 6px")
    
    def test_scrollbar_thumb_styled(self):
        """测试滚动条滑块有样式"""
        self.assertIn('#panel-hotfix.panel.on::-webkit-scrollbar-thumb', self.app_css,
                     " 应有滚动条滑块样式")
            
        # 应有 background 和 border-radius (不要求在同一规则块)
        self.assertIn('background: var(--ln2)', self.app_css,
                     " 滚动条滑块应有背景")
            
        self.assertIn('border-radius: 3px', self.app_css,
                     " 滚动条滑块应有圆角")

    def test_scrollbar_track_styled(self):
        """测试滚动条轨道有样式"""
        self.assertIn('#panel-hotfix.panel.on::-webkit-scrollbar-track', self.app_css,
                     "❌ 应有滚动条轨道样式")

    def test_complete_scrollbar_fix(self):
        """测试完整的滚动条修复"""
        issues = []
        
        # 1. 垂直滚动
        if 'overflow-y: auto' not in self.app_css:
            issues.append("❌ 未设置 overflow-y: auto")
        
        # 2. 隐藏水平滚动
        if 'overflow-x: hidden' not in self.app_css:
            issues.append("❌ 未设置 overflow-x: hidden")
        
        # 3. 滚动条样式
        if '#panel-hotfix.panel.on::-webkit-scrollbar' not in self.app_css:
            issues.append("❌ 未设置滚动条样式")
        
        # 4. 滚动条宽度
        if 'width: 6px' not in self.app_css:
            issues.append("❌ 滚动条宽度不正确")
        
        # 5. 滚动条滑块
        if '#panel-hotfix.panel.on::-webkit-scrollbar-thumb' not in self.app_css:
            issues.append("❌ 未设置滚动条滑块样式")
        
        # 6. 滚动条轨道
        if '#panel-hotfix.panel.on::-webkit-scrollbar-track' not in self.app_css:
            issues.append("❌ 未设置滚动条轨道样式")
        
        if issues:
            self.fail("滚动条修复存在问题:\n" + "\n".join(issues))

    def test_panel_selector_specificity(self):
        """测试选择器优先级正确"""
        # 应使用 #panel-hotfix.panel.on 而非单独的 .panel
        # 这样可以覆盖默认的 overflow:hidden
        self.assertIn('#panel-hotfix.panel.on {', self.app_css,
                     "❌ 应使用高优先级选择器")


if __name__ == '__main__':
    unittest.main()
