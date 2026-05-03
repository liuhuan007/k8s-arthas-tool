#!/usr/bin/env python3
"""
测试两步连接流程状态分离

验证:
1. 步骤3有独立状态显示 (podConnStatus)
2. 步骤4有独立状态显示 (arthasUpgradeStatus)
3. 步骤3和步骤4按钮独立控制
4. Pod 连接成功后 Arthas 升级按钮才可用
"""
import unittest
import re
from pathlib import Path


class TestTwoStepConnectionStateSeparation(unittest.TestCase):
    """测试两步连接流程状态分离"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.index_html = (self.root / 'static' / 'index.html').read_text(encoding='utf-8')
        self.two_step_js = (self.root / 'static' / 'js' / 'components' / 'two-step-connection.js').read_text(encoding='utf-8')

    def test_html_has_pod_status(self):
        """测试 HTML 有步骤3状态显示"""
        self.assertIn('id="podConnStatus"', self.index_html,
                     "❌ HTML 应该有 podConnStatus 元素")

    def test_html_has_arthas_status(self):
        """测试 HTML 有步骤4状态显示"""
        self.assertIn('id="arthasUpgradeStatus"', self.index_html,
                     "❌ HTML 应该有 arthasUpgradeStatus 元素")

    def test_html_has_upgrade_button_id(self):
        """测试升级按钮有 ID"""
        self.assertIn('id="ptUpgradeBtn"', self.index_html,
                     "❌ 升级按钮应该有 id=\"ptUpgradeBtn\"")

    def test_js_updates_pod_status(self):
        """测试 JS 更新步骤3状态"""
        # 应该有 podConnStatus 的引用
        self.assertIn('podConnStatus', self.two_step_js,
                     "❌ JS 应该引用 podConnStatus")

    def test_js_updates_arthas_status(self):
        """测试 JS 更新步骤4状态"""
        # 应该有 arthasUpgradeStatus 的引用
        self.assertIn('arthasUpgradeStatus', self.two_step_js,
                     "❌ JS 应该引用 arthasUpgradeStatus")

    def test_js_controls_upgrade_button(self):
        """测试 JS 控制升级按钮"""
        # 应该有 ptUpgradeBtn 的引用
        self.assertIn('ptUpgradeBtn', self.two_step_js,
                     "❌ JS 应该引用 ptUpgradeBtn")

    def test_js_separates_pod_and_arthas_states(self):
        """测试 JS 分离 Pod 和 Arthas 状态显示"""
        # 应该有 switch 语句根据状态显示不同区域
        self.assertIn('ConnectionState.POD_CONNECTING', self.two_step_js,
                     "❌ 应该处理 POD_CONNECTING 状态")
        self.assertIn('ConnectionState.ARTHAS_UPGRADING', self.two_step_js,
                     "❌ 应该处理 ARTHAS_UPGRADING 状态")

    def test_upgrade_button_disabled_before_pod_connect(self):
        """测试 Pod 连接前升级按钮禁用"""
        # 应该禁用升级按钮
        self.assertIn('upgradeBtn.disabled = true', self.two_step_js,
                     "❌ 应该有 upgradeBtn.disabled = true")

    def test_upgrade_button_enabled_after_pod_connect(self):
        """测试 Pod 连接后升级按钮可用"""
        # 应该启用升级按钮
        self.assertIn('upgradeBtn.disabled = false', self.two_step_js,
                     "❌ 应该有 upgradeBtn.disabled = false")

    def test_complete_state_separation(self):
        """测试完整的状态分离流程"""
        issues = []
        
        # 1. HTML 元素
        if 'id="podConnStatus"' not in self.index_html:
            issues.append("❌ HTML 缺少 podConnStatus")
        
        if 'id="arthasUpgradeStatus"' not in self.index_html:
            issues.append("❌ HTML 缺少 arthasUpgradeStatus")
        
        if 'id="ptUpgradeBtn"' not in self.index_html:
            issues.append("❌ HTML 缺少 ptUpgradeBtn")
        
        # 2. JS 状态分离
        if 'podConnStatus' not in self.two_step_js:
            issues.append("❌ JS 未使用 podConnStatus")
        
        if 'arthasUpgradeStatus' not in self.two_step_js:
            issues.append("❌ JS 未使用 arthasUpgradeStatus")
        
        if 'ptUpgradeBtn' not in self.two_step_js:
            issues.append("❌ JS 未使用 ptUpgradeBtn")
        
        if issues:
            self.fail("状态分离存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
