#!/usr/bin/env python3
"""Workspace history compat regression tests."""

import unittest
from pathlib import Path


class TestWorkspaceHistoryMount(unittest.TestCase):
    """Ensure history is workspace-owned while legacy history remains a compat shell."""

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.workspace_js = (root / 'static' / 'js' / 'components' / 'connection-workspace.js').read_text(encoding='utf-8')
        self.sampling_history_js = (root / 'static' / 'js' / 'components' / 'sampling-history.js').read_text(encoding='utf-8')

    def test_workspace_history_renders_its_own_host(self):
        self.assertIn("case 'history': renderWorkspaceHistory(el); break;", self.workspace_js)
        self.assertIn('data-history-host="workspace"', self.workspace_js)
        self.assertIn('data-history-role="panel-profiler"', self.workspace_js)
        self.assertIn('data-history-role="panel-files"', self.workspace_js)
        self.assertNotIn("case 'history': renderLegacyFeature(el, 'panel-history'", self.workspace_js)

    def test_history_helpers_resolve_active_host_in_both_modes(self):
        self.assertIn('const HISTORY_VIEW_SELECTORS = {', self.app_ui_js)
        self.assertIn('function getHistoryViewRoot() {', self.app_ui_js)
        self.assertIn("window.__workspaceHistoryHost = window.__workspaceHistoryHost || null;", self.app_ui_js)
        self.assertIn("const container = getHistoryViewElement('panel-profiler');", self.app_ui_js)
        self.assertIn("const el = getHistoryViewElement('panel-files');", self.app_ui_js)
        self.assertIn('if (!isHistoryViewVisible(root)) return;', self.app_ui_js)

    def test_sampling_history_updates_workspace_host_badges(self):
        self.assertIn("closest('[data-history-host]') || _root.closest('#panel-history')", self.sampling_history_js)
        self.assertIn("querySelector('[data-history-role=\"count-profiler\"]')", self.sampling_history_js)
        self.assertIn("if (typeof window.updateHistoryCounts === 'function') window.updateHistoryCounts();", self.sampling_history_js)


if __name__ == '__main__':
    unittest.main()
