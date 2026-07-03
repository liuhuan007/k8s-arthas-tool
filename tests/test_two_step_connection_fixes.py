#!/usr/bin/env python3
"""
测试两步连接流程的三个关键修复:

1. Arthas 已连接时隐藏 Pod 连接按钮
2. 状态提示不重复显示
3. 断开连接接口支持幂等性
"""
import unittest
from pathlib import Path


class TestTwoStepConnectionFixes(unittest.TestCase):
    """测试两步连接流程修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.two_step_js = (self.root / 'static' / 'js' / 'components' / 'two-step-connection.js').read_text(encoding='utf-8')
        self.pod_apis_py = (self.root / 'api' / 'pod_apis.py').read_text(encoding='utf-8')
        self.css = (self.root / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')

    # ── 问题 1: Arthas 已连接时隐藏 Pod 连接按钮 ─────────────────────────

    def test_hide_pod_button_when_arthas_ready(self):
        """测试 Arthas 已就绪时隐藏 Pod 连接按钮"""
        # 应该在 ARTHAS_READY 状态隐藏按钮
        self.assertIn("btn.style.display = 'none'", self.two_step_js,
                     "❌ Arthas 已连接时应隐藏 Pod 连接按钮")
        
        # 应该在注释中说明
        self.assertIn('Arthas 已连接时隐藏 Pod 连接按钮', self.two_step_js,
                     "❌ 应有注释说明隐藏逻辑")

    def test_show_pod_button_when_disconnected(self):
        """测试断开连接后重新显示 Pod 连接按钮"""
        # 断开后应重新显示按钮
        self.assertIn("btn.style.display = ''", self.two_step_js,
                     "❌ 断开连接后应重新显示 Pod 连接按钮")

    def test_hide_upgrade_button_when_disconnected(self):
        """测试未连接时隐藏 Arthas 升级按钮"""
        # DISCONNECTED 状态应隐藏升级按钮
        self.assertIn("upgradeBtn.style.display = 'none'", self.two_step_js,
                     "❌ 未连接时应隐藏 Arthas 升级按钮")

    # ── 问题 2: 状态提示不重复显示 ──────────────────────────────────────

    def test_no_duplicate_status_display(self):
        """测试不重复显示状态提示"""
        # 不应调用 setCpSt 显示重复状态
        self.assertNotIn("setCpSt('ok', `✓ ${d.message}", self.two_step_js,
                        "❌ 不应调用 setCpSt 重复显示状态")
        
        # 应只调用 updateConnectionStatus
        self.assertIn("updateConnectionStatus(", self.two_step_js,
                     "❌ 应使用 updateConnectionStatus 显示状态")

    def test_status_message_without_extra_info(self):
        """测试状态消息不包含多余信息"""
        # 状态消息不应包含 d.message (已在 tooltip 中显示)
        pattern = r"Arthas 诊断环境就绪.*?- \$\{d\.message\}"
        import re
        self.assertNotRegex(self.two_step_js, pattern,
                           "❌ 状态消息不应包含 d.message (避免重复)")

    def test_pod_target_collapses_after_successful_connection(self):
        """测试连接成功后 Pod 目标选择区真正收起"""
        self.assertIn('podTarget.classList.add(\'collapsed\')', self.two_step_js,
                     "❌ Pod 连接成功后应给目标选择区添加 collapsed")
        self.assertIn('.pod-target.pod-target-main.collapsed{max-height:0', self.css,
                     "❌ collapsed 状态不能被 pod-target-main 样式覆盖")
        self.assertIn('overflow:hidden', self.css.split('.pod-target.pod-target-main.collapsed', 1)[1].split('}', 1)[0],
                     "❌ collapsed 状态应隐藏溢出内容")

    # ── 问题 3: 断开连接接口幂等性 ─────────────────────────────────────

    def test_disconnect_idempotent(self):
        """测试断开连接接口支持幂等性"""
        # 连接不存在时应返回成功
        self.assertIn('连接不存在（可能已断开）', self.pod_apis_py,
                     "❌ 连接不存在时应返回成功 (幂等性)")
        
        # 应返回 ok: True
        self.assertIn('return jsonify({"ok": True, "message": "连接已断开"})', self.pod_apis_py,
                     "❌ 应返回成功响应")

    def test_disconnect_checks_unified_connection_lookup(self):
        """测试断开连接通过统一连接池入口查找连接"""
        # 应先走统一入口，避免继续依赖旧的 _pod_connections
        self.assertIn('entry = _shared_get_connection_entry(conn_id)', self.pod_apis_py,
                     "❌ 应优先使用共享连接查询入口")

        # 共享入口未命中时，应回退到 _connections 池
        self.assertIn('_connections.get(conn_id)', self.pod_apis_py,
                     "❌ 应回退检查 _connections 统一连接池")

    def test_disconnect_fallback_to_old_api(self):
        """测试前端支持旧版 API 回退"""
        # 前端应尝试 /api/arthas/disconnect 作为回退
        self.assertIn('/arthas/disconnect', self.two_step_js,
                     "❌ 前端应支持旧版 API 回退")
        
        # 应捕获错误并尝试回退
        self.assertIn('尝试旧接口', self.two_step_js,
                     "❌ 应有回退逻辑")

    # ── 综合测试 ─────────────────────────────────────────────────────────

    def test_complete_button_visibility_flow(self):
        """测试完整的按钮可见性流程"""
        issues = []
        
        # 1. 初始状态: Pod 按钮可见,升级按钮隐藏
        if "btn.textContent = '🔌 Pod 连接'" not in self.two_step_js:
            issues.append("❌ 初始状态 Pod 按钮文本不正确")
        
        # 2. Pod 已连接: 升级按钮可见
        if "upgradeBtn.style.display = ''" not in self.two_step_js:
            issues.append("❌ Pod 连接后升级按钮应可见")
        
        # 3. Arthas 已就绪: Pod 按钮隐藏
        if "btn.style.display = 'none'" not in self.two_step_js:
            issues.append("❌ Arthas 已就绪时 Pod 按钮应隐藏")
        
        # 4. 断开后: Pod 按钮重新显示
        if self.two_step_js.count("btn.style.display = ''") < 2:
            issues.append("❌ 断开后应重新显示 Pod 按钮")
        
        if issues:
            self.fail("按钮可见性流程存在问题:\n" + "\n".join(issues))

    def test_complete_disconnect_flow(self):
        """测试完整的断开连接流程"""
        issues = []
        
        # 1. 前端优先使用 _currentConnId
        if 'const activeConnId = _currentConnId || _podConnId' not in self.two_step_js:
            issues.append("❌ 前端应优先使用 _currentConnId")
        
        # 2. 前端尝试新接口
        if '/pod/disconnect' not in self.two_step_js:
            issues.append("❌ 前端应优先调用新接口")
        
        # 3. 前端支持旧接口回退
        if '/arthas/disconnect' not in self.two_step_js:
            issues.append("❌ 前端应支持旧接口回退")
        
        # 4. 后端支持幂等性
        if '连接不存在（可能已断开）' not in self.pod_apis_py:
            issues.append("❌ 后端应支持幂等性")
        
        # 5. 后端检查两个连接池
        if '_connections.get(conn_id)' not in self.pod_apis_py:
            issues.append("❌ 后端应检查两个连接池")
        
        if issues:
            self.fail("断开连接流程存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
