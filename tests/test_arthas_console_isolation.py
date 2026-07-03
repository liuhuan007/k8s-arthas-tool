#!/usr/bin/env python3
"""Arthas console collapse and per-connection isolation regressions."""

import unittest
from pathlib import Path


class TestArthasConsoleIsolation(unittest.TestCase):
    """Keep command output and input state bound to the focused connection."""

    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app_ui_js = (root / 'static' / 'js' / 'app-ui.js').read_text(encoding='utf-8')
        self.css = (root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')

    def test_result_collapsible_toggles_outer_wrapper(self):
        self.assertIn('function toggleResultCollapse(id) {', self.app_ui_js)
        self.assertIn("wrap.classList.toggle('open')", self.app_ui_js)
        self.assertIn('return `<div class="r-coll ${open?\'open\':\'\'}" id="${id}">', self.app_ui_js)
        self.assertIn('aria-expanded="${open?\'true\':\'false\'}"', self.app_ui_js)
        self.assertIn('aria-controls="${bodyId}"', self.app_ui_js)
        self.assertIn('id="${bodyId}"', self.app_ui_js)
        self.assertNotIn("document.getElementById('${id}').classList.toggle('open')", self.app_ui_js)
        self.assertIn('.r-coll.open .r-coll-b{display:block}', self.css)

    def test_command_line_state_is_saved_and_restored_per_connection(self):
        self.assertIn('let _cmdHistByConn = {}, _cmdDraftByConn = {};', self.app_ui_js)
        self.assertIn('function saveCommandConsoleState(connId = activeCommandConnId()) {', self.app_ui_js)
        self.assertIn('_cmdHistByConn[connId] = Array.isArray(_cmdHist) ? _cmdHist.slice(-100) : [];', self.app_ui_js)
        self.assertIn('function restoreCommandConsoleState(connId = activeCommandConnId()) {', self.app_ui_js)
        self.assertIn('_cmdHist = (connId && _cmdHistByConn[connId] ? _cmdHistByConn[connId] : []).slice();', self.app_ui_js)
        self.assertIn('saveCommandConsoleState(oldConnId);', self.app_ui_js)
        self.assertIn('restoreCommandConsoleState(connId);', self.app_ui_js)
        self.assertIn('saveCommandConsoleState(_currentConnId);', self.app_ui_js)

    def test_connection_history_load_does_not_write_after_focus_changes(self):
        load_block = self.app_ui_js[
            self.app_ui_js.index('async function loadConnectionCommands(connId) {'):
            self.app_ui_js.index('async function switchConnection(connId) {')
        ]
        self.assertIn('if (!isActiveCommandConnection(connId)) return;', load_block)

    def test_once_command_result_does_not_cross_write_between_connections(self):
        run_once = self.app_ui_js[
            self.app_ui_js.index('async function runOnce(command) {'):
            self.app_ui_js.index('async function runStream(command) {')
        ]
        self.assertIn('const runConnId = activeCommandConnId();', run_once)
        self.assertIn('const runTarget = { ..._ap };', run_once)
        self.assertIn('connection_id: runConnId', run_once)
        self.assertIn('if (!isActiveCommandConnection(runConnId)) return;', run_once)
        self.assertIn('if (isActiveCommandConnection(runConnId)) clog', run_once)

    def test_stream_command_result_is_bound_to_connection_session(self):
        run_stream = self.app_ui_js[
            self.app_ui_js.index('async function runStream(command) {'):
            self.app_ui_js.index('function stopPoll() {')
        ]
        self.assertIn('const runConnId = activeCommandConnId();', run_stream)
        self.assertIn('const runTarget = { ..._ap };', run_stream)
        self.assertIn('if(!_sid || _sidConnId !== runConnId) {', run_stream)
        self.assertIn('_sid = d.sessionId; _cid = d.consumerId; _sidConnId = runConnId;', run_stream)
        self.assertIn('JSON.stringify(runTarget)', run_stream)
        self.assertIn('JSON.stringify({...runTarget, command, session_id: _sid})', run_stream)
        self.assertIn('JSON.stringify({...runTarget, session_id: _sid, consumer_id: _cid})', run_stream)
        self.assertIn('if(!_polling || !isActiveCommandConnection(runConnId)) return;', run_stream)
        self.assertIn('if (!isActiveCommandConnection(runConnId)) return;', run_stream)

    def test_reset_command_session_state_hides_interrupt_button(self):
        reset_block = self.app_ui_js[
            self.app_ui_js.index('function resetCommandSessionState() {'):
            self.app_ui_js.index('// ── Server Health Check')
        ]
        self.assertIn('_sidConnId = null;', reset_block)
        self.assertIn("document.getElementById('btnStop')", reset_block)
        self.assertIn("stopBtn.style.display = 'none';", reset_block)


if __name__ == '__main__':
    unittest.main()
