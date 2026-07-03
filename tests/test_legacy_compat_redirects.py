#!/usr/bin/env python3
"""Legacy compatibility redirect regression tests."""

import unittest
from pathlib import Path


class TestLegacyCompatRedirects(unittest.TestCase):
    """Ensure legacy standalone routes only act as redirect shims."""

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.layout_loader_js = (root / 'static' / 'js' / 'layout-loader.js').read_text(encoding='utf-8')
        self.compat_js = (root / 'static' / 'js' / 'legacy-compat.js').read_text(encoding='utf-8')
        self.index_html = (root / 'static' / 'index.html').read_text(encoding='utf-8')
        self.page_html = {
            'connections': (root / 'static' / 'connections.html').read_text(encoding='utf-8'),
            'workspace': (root / 'static' / 'workspace.html').read_text(encoding='utf-8'),
            'profiler': (root / 'static' / 'profiler.html').read_text(encoding='utf-8'),
            'monitor': (root / 'static' / 'monitor.html').read_text(encoding='utf-8'),
            'terminal': (root / 'static' / 'terminal.html').read_text(encoding='utf-8'),
            'filebrowser': (root / 'static' / 'filebrowser.html').read_text(encoding='utf-8'),
            'history': (root / 'static' / 'history.html').read_text(encoding='utf-8'),
            'arthas-console': (root / 'static' / 'arthas-console.html').read_text(encoding='utf-8'),
            'diagnose': (root / 'static' / 'diagnose.html').read_text(encoding='utf-8'),
        }

    def test_nav_routes_point_to_root_workspace_aliases(self):
        self.assertIn("'profiler':         '/#sampling',", self.app_ui_js)
        self.assertIn("'filebrowser':      '/#files',", self.app_ui_js)
        self.assertIn("'monitor':          '/#monitor',", self.app_ui_js)
        self.assertIn("'profiler':         '/#sampling',", self.layout_loader_js)
        self.assertIn("'filebrowser':      '/#files',", self.layout_loader_js)

    def test_root_workspace_reads_conn_and_hash_deeplink(self):
        self.assertIn("function normalizeWorkspaceDeepLinkTab(rawTab) {", self.app_ui_js)
        self.assertIn("const connId = params.get('conn') || params.get('connection_id') || params.get('connectionId') || '';", self.app_ui_js)
        self.assertIn("const preferredConnId = deepLinkIntent.connId", self.app_ui_js)
        self.assertIn("applyWorkspaceDeepLink();", self.app_ui_js)
        self.assertIn("if (typeof applyWorkspaceDeepLink === 'function') {", self.index_html)

    def test_shared_compat_script_maps_legacy_routes_to_new_tabs(self):
        self.assertIn("profiler: 'sampling',", self.compat_js)
        self.assertIn("filebrowser: 'files',", self.compat_js)
        self.assertIn("'arthas-console': 'console',", self.compat_js)
        self.assertIn("window.location.replace(target)", self.compat_js)

    def test_legacy_pages_are_redirect_shells(self):
        for route_name, html in self.page_html.items():
            self.assertIn(f'data-legacy-route="{route_name}"', html)
            self.assertIn('js/legacy-compat.js', html)
            self.assertIn('id="legacyCompatLink"', html)


if __name__ == '__main__':
    unittest.main()
