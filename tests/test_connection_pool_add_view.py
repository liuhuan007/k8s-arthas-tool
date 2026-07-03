#!/usr/bin/env python3
"""新建连接视图回归测试"""

import unittest
from pathlib import Path


class TestConnectionPoolAddView(unittest.TestCase):
    """防止新建连接视图与工作区内容同时显示"""

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.pool_js = (root / 'static' / 'js' / 'components' / 'connection-pool.js').read_text(encoding='utf-8')
        self.workspace_js = (root / 'static' / 'js' / 'components' / 'connection-workspace.js').read_text(encoding='utf-8')
        self.index_html = (root / 'static' / 'index.html').read_text(encoding='utf-8')
        self.app_css = (root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')

    def test_add_view_has_explicit_open_state(self):
        self.assertIn('let addViewOpen = false;', self.pool_js)
        self.assertIn('addViewOpen = true;', self.pool_js)
        self.assertIn('addViewOpen = false;', self.pool_js)
        self.assertIn('function isAddViewOpen() {', self.pool_js)
        self.assertIn('showAddView, hideAddView, cancelAdd: hideAddView, hardenSearchInput, isAddViewOpen,', self.pool_js)

    def test_focusing_connection_closes_add_view(self):
        focus_block = self.pool_js[self.pool_js.index('function focus(id) {'):self.pool_js.index('function toggleDetail')]
        self.assertIn('if (addViewOpen) hideAddView();', focus_block)

    def test_workspace_render_skips_content_when_add_view_is_open(self):
        self.assertIn("ConnectionPool.isAddViewOpen()", self.workspace_js)
        self.assertIn("if (contentEl) contentEl.style.display = 'none';", self.workspace_js)
        self.assertIn('return;', self.workspace_js[self.workspace_js.index('function render() {'):self.workspace_js.index('// ── 头部')])

    def test_add_view_uses_stable_two_column_layout(self):
        self.assertIn('class="add-conn-view"', self.index_html)
        self.assertIn('class="add-conn-grid"', self.index_html)
        self.assertIn('class="add-conn-card add-conn-form"', self.index_html)
        self.assertIn('class="add-conn-card add-conn-preview-card"', self.index_html)
        self.assertIn('.add-conn-grid{', self.app_css)
        self.assertIn('.add-conn-pod-list{', self.app_css)


if __name__ == '__main__':
    unittest.main()
