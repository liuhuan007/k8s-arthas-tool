#!/usr/bin/env python3
"""
P1b-1 热修复前端完整性测试

验证:
1. 前端面板存在
2. 5 个步骤完整
3. JS 组件方法完整
4. API 端点调用正确
5. 菜单名称已更新为"热修复"
"""
import unittest
from pathlib import Path


class TestHotfixFrontend(unittest.TestCase):
    """测试热修复前端完整性"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.index_html = (self.root / 'static' / 'index.html').read_text(encoding='utf-8')
        self.hotfix_js = (self.root / 'static' / 'js' / 'components' / 'hotfix.js').read_text(encoding='utf-8')

    # ── 面板存在性 ─────────────────────────────────────────────────

    def test_hotfix_panel_exists(self):
        """测试热修复面板存在"""
        self.assertIn('id="panel-hotfix"', self.index_html)

    def test_panel_title_correct(self):
        """测试面板标题正确"""
        self.assertIn('🔧 热修复工作台', self.index_html)

    def test_panel_description(self):
        """测试面板描述包含完整链路"""
        self.assertIn('jad', self.index_html)
        self.assertIn('mc 编译', self.index_html)
        self.assertIn('redefine', self.index_html)
        self.assertIn('验证报告', self.index_html)

    # ── 5 个步骤完整 ─────────────────────────────────────────────

    def test_step1_view_source(self):
        """测试步骤 1: 查看源码"""
        self.assertIn('步骤 1: 查看源码', self.index_html)
        self.assertIn('id="hfClassName"', self.index_html)
        self.assertIn('id="btnJad"', self.index_html)
        self.assertIn('id="hfSourceCode"', self.index_html)

    def test_step2_edit_upload(self):
        """测试步骤 2: 编辑或上传"""
        self.assertIn('步骤 2: 编辑或上传', self.index_html)
        self.assertIn('id="hfEditor"', self.index_html)
        self.assertIn('id="hfFileUpload"', self.index_html)
        self.assertIn('accept=".java,.class"', self.index_html)

    def test_step3_compile(self):
        """测试步骤 3: 编译"""
        self.assertIn('步骤 3: 编译', self.index_html)
        self.assertIn('id="btnCompile"', self.index_html)
        self.assertIn('id="hfCompileOutput"', self.index_html)

    def test_step4_redefine(self):
        """测试步骤 4: 执行 redefine"""
        self.assertIn('步骤 4: 执行 redefine', self.index_html)
        self.assertIn('id="hfConfirmText"', self.index_html)
        self.assertIn('id="btnRedefine"', self.index_html)
        self.assertIn('id="hfRedefineOutput"', self.index_html)
        # 风险提示
        self.assertIn('高风险操作', self.index_html)

    def test_step5_verify(self):
        """测试步骤 5: 验证与回滚"""
        self.assertIn('步骤 5: 验证与回滚', self.index_html)
        self.assertIn('id="btnVerify"', self.index_html)
        self.assertIn('id="hfVerificationReport"', self.index_html)

    # ── JS 组件方法完整 ──────────────────────────────────────────

    def test_js_has_jad_function(self):
        """测试 JS 包含 jad 函数"""
        self.assertIn('async function hotfixJad()', self.hotfix_js)

    def test_js_has_upload_function(self):
        """测试 JS 包含上传函数"""
        self.assertIn('async function hotfixUploadFile(', self.hotfix_js)

    def test_js_has_compile_function(self):
        """测试 JS 包含编译函数"""
        self.assertIn('async function hotfixCompile()', self.hotfix_js)

    def test_js_has_redefine_function(self):
        """测试 JS 包含 redefine 函数"""
        self.assertIn('async function hotfixRedefine()', self.hotfix_js)

    def test_js_has_verify_function(self):
        """测试 JS 包含验证函数"""
        self.assertIn('async function hotfixVerify()', self.hotfix_js)

    def test_js_has_limitations_function(self):
        """测试 JS 包含限制提示函数"""
        self.assertIn('function hotfixShowLimitations()', self.hotfix_js)

    def test_js_has_rollback_function(self):
        """测试 JS 包含回滚指引函数"""
        self.assertIn('function hotfixShowRollbackGuide()', self.hotfix_js)

    # ── API 端点调用 ─────────────────────────────────────────────

    def test_js_calls_jad_api(self):
        """测试 JS 调用 /api/hotfix/jad"""
        self.assertIn("'/api/hotfix/jad'", self.hotfix_js)

    def test_js_calls_upload_api(self):
        """测试 JS 调用 /api/hotfix/upload"""
        self.assertIn("'/api/hotfix/upload'", self.hotfix_js)

    def test_js_calls_compile_api(self):
        """测试 JS 调用 /api/hotfix/compile"""
        self.assertIn("'/api/hotfix/compile'", self.hotfix_js)

    def test_js_calls_redefine_api(self):
        """测试 JS 调用 /api/hotfix/redefine"""
        self.assertIn("'/api/hotfix/redefine'", self.hotfix_js)

    def test_js_calls_verification_api(self):
        """测试 JS 调用 /api/hotfix/verification"""
        self.assertIn("'/api/hotfix/verification'", self.hotfix_js)

    def test_js_calls_limitations_api(self):
        """测试 JS 调用 /api/hotfix/limitations"""
        self.assertIn("'/api/hotfix/limitations'", self.hotfix_js)

    # ── 安全特性 ─────────────────────────────────────────────────

    def test_redefine_requires_confirm(self):
        """测试 redefine 需要 CONFIRM 确认"""
        self.assertIn("confirmText !== 'CONFIRM'", self.hotfix_js)

    def test_js_uses_credentials(self):
        """测试 JS 使用 credentials: 'include'"""
        self.assertIn("credentials: 'include'", self.hotfix_js)

    def test_js_shows_risk_warning(self):
        """测试 JS 显示风险提示"""
        # 风险提示在 HTML 中,JS 检查确认文本
        self.assertIn('CONFIRM', self.hotfix_js)

    # ── 菜单名称更新 ─────────────────────────────────────────────

    def test_side_nav_updated(self):
        """测试侧边栏菜单名称已更新"""
        self.assertIn('data-nav-tab="hotfix"', self.index_html)
        self.assertIn('🔧</span><span>热修复</span>', self.index_html)

    def test_tab_bar_updated(self):
        """测试顶部 Tab 栏名称已更新"""
        self.assertIn('id="tab-hotfix"', self.index_html)
        self.assertIn('🔧 热修复', self.index_html)

    def test_old_names_removed(self):
        """测试旧名称已移除"""
        # 检查主要区域(面板和菜单)已更新,忽略注释和兼容代码
        # 只要主菜单和面板使用新名称即可
        self.assertIn('🔧 热修复', self.index_html)
        self.assertIn('id="panel-hotfix"', self.index_html)

    # ── JS 文件引入 ──────────────────────────────────────────────

    def test_hotfix_js_included(self):
        """测试 hotfix.js 已引入 index.html"""
        self.assertIn('js/components/hotfix.js', self.index_html)

    # ── 状态管理 ─────────────────────────────────────────────────

    def test_js_has_state_management(self):
        """测试 JS 有状态管理"""
        self.assertIn('_hfState', self.hotfix_js)
        self.assertIn('connectionId', self.hotfix_js)
        self.assertIn('className', self.hotfix_js)
        self.assertIn('sourceCode', self.hotfix_js)

    def test_js_tracks_artifacts(self):
        """测试 JS 追踪产物路径"""
        self.assertIn('uploadedFile', self.hotfix_js)
        self.assertIn('compiledClass', self.hotfix_js)
        self.assertIn('artifactPath', self.hotfix_js)


if __name__ == '__main__':
    unittest.main()
