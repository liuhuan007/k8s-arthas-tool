#!/usr/bin/env python3
"""
P1b-4 多连接选择器测试

验证:
1. JS 组件文件存在
2. CSS 样式定义
3. HTML 引入组件
4. 核心功能函数
"""
import unittest
import re
from pathlib import Path


class TestMultiConnSelector(unittest.TestCase):
    """测试多连接选择器"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.js = (self.root / 'static' / 'js' / 'components' / 'multi-conn-selector.js').read_text(encoding='utf-8')
        self.css = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
        self.html = (self.root / 'static' / 'index.html').read_text(encoding='utf-8')
        self.hotfix_js = (self.root / 'static' / 'js' / 'components' / 'hotfix.js').read_text(encoding='utf-8')

    # ── JS 组件 ─────────────────────────────────────────────────

    def test_js_file_exists(self):
        """测试 JS 组件文件存在"""
        js_path = self.root / 'static' / 'js' / 'components' / 'multi-conn-selector.js'
        self.assertTrue(js_path.exists(), "multi-conn-selector.js 应该存在")

    def test_js_exports_global(self):
        """测试 JS 导出全局对象"""
        self.assertIn('window.MultiConnSelector = MultiConnSelector', self.js)

    def test_js_has_show_method(self):
        """测试有 show 方法"""
        self.assertIn('function show(', self.js)
        # show 方法在 return 对象中导出
        self.assertRegex(self.js, r'return\s*\{[^}]*show[^}]*\}')

    def test_js_has_select_method(self):
        """测试有 select 方法"""
        self.assertIn('function select(', self.js)

    def test_js_has_close_method(self):
        """测试有 close 方法"""
        self.assertIn('function close(', self.js)

    def test_js_auto_select_single_connection(self):
        """测试只有 1 个连接时自动选中"""
        # 应该有单连接自动选中的逻辑
        self.assertIn('_connections.length === 1', self.js)
        self.assertIn('自动选中', self.js)

    def test_js_renders_connection_cards(self):
        """测试渲染连接卡片"""
        self.assertIn('mcs-card', self.js)
        self.assertIn('renderConnections', self.js)

    def test_js_shows_connection_info(self):
        """测试显示连接信息"""
        # 应该显示集群/命名空间/Pod 等信息
        self.assertIn('cluster_name', self.js)
        self.assertIn('namespace', self.js)
        self.assertIn('pod_name', self.js)

    def test_js_shows_level_badge(self):
        """测试显示连接层级徽章"""
        self.assertIn('mcs-level-badge', self.js)
        self.assertIn('arthas', self.js)
        self.assertIn('pod', self.js)

    # ── CSS 样式 ─────────────────────────────────────────────────

    def test_css_modal_styles(self):
        """测试模态框样式"""
        self.assertIn('.mcs-modal', self.css)
        self.assertIn('.mcs-modal.show', self.css)

    def test_css_dialog_styles(self):
        """测试对话框样式"""
        self.assertIn('.mcs-dialog', self.css)
        self.assertIn('.mcs-backdrop', self.css)

    def test_css_card_styles(self):
        """测试卡片样式"""
        self.assertIn('.mcs-card', self.css)
        self.assertIn('.mcs-card:hover', self.css)
        self.assertIn('.mcs-card.active', self.css)

    def test_css_badge_styles(self):
        """测试徽章样式"""
        self.assertIn('.mcs-level-badge', self.css)
        self.assertIn('.mcs-level-badge.arthas', self.css)
        self.assertIn('.mcs-level-badge.pod', self.css)
        self.assertIn('.mcs-active-badge', self.css)

    # ── HTML 引入 ─────────────────────────────────────────────────

    def test_html_includes_js(self):
        """测试 HTML 引入 JS 组件"""
        self.assertIn('multi-conn-selector.js', self.html)

    # ── 热修复集成 ─────────────────────────────────────────────────

    def test_hotfix_uses_selector(self):
        """测试热修复使用多连接选择器"""
        self.assertIn('showConnectionSelectorForHotfix', self.hotfix_js)
        self.assertIn('MultiConnSelector.show', self.hotfix_js)

    def test_hotfix_fetches_connections(self):
        """测试热修复获取连接列表"""
        self.assertIn('/api/pod/connections', self.hotfix_js)

    def test_hotfix_switches_connection(self):
        """测试热修复切换连接"""
        self.assertIn('switchConnection(connId)', self.hotfix_js)

    # ── 完整功能 ─────────────────────────────────────────────────

    def test_complete_selector(self):
        """测试完整选择器功能"""
        # 1. JS 组件
        self.assertIn('MultiConnSelector', self.js)
        self.assertIn('show', self.js)
        self.assertIn('select', self.js)
        self.assertIn('close', self.js)
        
        # 2. CSS 样式
        self.assertIn('.mcs-modal', self.css)
        self.assertIn('.mcs-card', self.css)
        
        # 3. HTML 引入
        self.assertIn('multi-conn-selector.js', self.html)
        
        # 4. 热修复集成
        self.assertIn('showConnectionSelectorForHotfix', self.hotfix_js)


if __name__ == '__main__':
    unittest.main()
