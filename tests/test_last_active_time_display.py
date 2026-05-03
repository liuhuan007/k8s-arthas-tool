#!/usr/bin/env python3
"""
测试连接列表显示最后活跃时间

验证:
1. renderConnList 中显示 last_ping_at
2. _formatLastActive 函数存在且正确
3. CSS 样式 .conn-last-active 存在
"""
import unittest
import re
from pathlib import Path


class TestLastActiveTimeDisplay(unittest.TestCase):
    """测试连接列表显示最后活跃时间"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (self.root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.app_css = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')

    def test_render_conn_list_shows_last_active(self):
        """测试连接列表渲染最后活跃时间"""
        # 应该有 lastActiveLine 变量
        self.assertIn('lastActiveLine', self.app_ui_js,
                     "❌ 应该有 lastActiveLine 变量")
        
        # 应该检查 c.last_ping_at
        self.assertIn('c.last_ping_at', self.app_ui_js,
                     "❌ 应该检查 c.last_ping_at")
        
        # 应该调用 _formatLastActive
        self.assertIn('_formatLastActive(c.last_ping_at)', self.app_ui_js,
                     "❌ 应该调用 _formatLastActive")

    def test_format_last_active_function_exists(self):
        """测试 _formatLastActive 函数存在"""
        # 函数定义
        self.assertIn('function _formatLastActive(timestamp)', self.app_ui_js,
                     "❌ 应该有 _formatLastActive 函数定义")

    def test_format_last_active_handles_relative_time(self):
        """测试时间格式化支持相对时间"""
        # 应该有相对时间逻辑
        self.assertIn('分钟前', self.app_ui_js,
                     "❌ 应该支持 '分钟前'")
        self.assertIn('小时前', self.app_ui_js,
                     "❌ 应该支持 '小时前'")
        self.assertIn('天前', self.app_ui_js,
                     "❌ 应该支持 '天前'")
        self.assertIn('刚刚', self.app_ui_js,
                     "❌ 应该支持 '刚刚'")

    def test_format_last_active_handles_old_dates(self):
        """测试时间格式化处理旧日期"""
        # 超过 7 天应该显示具体日期
        date_pattern = r'`.*\$\{month\}.*\$\{day\}.*\$\{hours\}.*\$\{minutes\}.*`'
        self.assertRegex(self.app_ui_js, date_pattern,
                        "❌ 超过 7 天应该显示月/日 时:分")

    def test_css_last_active_style_exists(self):
        """测试 CSS 样式存在"""
        # 应该有 .conn-last-active 样式
        self.assertIn('.conn-last-active', self.app_css,
                     "❌ 应该有 .conn-last-active CSS 样式")

    def test_last_active_rendered_in_html(self):
        """测试最后活跃时间渲染到 HTML"""
        # 应该有 conn-last-active class
        self.assertIn('class="conn-last-active"', self.app_ui_js,
                     "❌ HTML 中应该有 conn-last-active class")
        
        # 应该有 🕒 图标
        self.assertIn('🕒', self.app_ui_js,
                     "❌ 应该显示 🕒 图标")

    def test_last_active_has_tooltip(self):
        """测试最后活跃时间有 tooltip"""
        # title 属性应该显示完整时间
        self.assertIn('title="最后活跃:', self.app_ui_js,
                     "❌ tooltip 应该显示 '最后活跃:'")

    def test_complete_last_active_flow(self):
        """测试完整的最后活跃时间显示流程"""
        issues = []
        
        # 1. 函数存在
        if 'function _formatLastActive(timestamp)' not in self.app_ui_js:
            issues.append("❌ _formatLastActive 函数不存在")
        
        # 2. 渲染逻辑
        if 'c.last_ping_at' not in self.app_ui_js:
            issues.append("❌ 未检查 c.last_ping_at")
        
        # 3. CSS 样式
        if '.conn-last-active' not in self.app_css:
            issues.append("❌ CSS 样式不存在")
        
        # 4. HTML 渲染
        if 'class="conn-last-active"' not in self.app_ui_js:
            issues.append("❌ HTML 未渲染")
        
        if issues:
            self.fail("最后活跃时间显示存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
