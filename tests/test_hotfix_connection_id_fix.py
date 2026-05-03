#!/usr/bin/env python3
"""
P1b-1 热修复连接ID获取修复测试

验证:
1. getCurrentConnectionId 优先使用 window._currentConnId
2. 不再从 csbTarget 文本获取(那是显示文本,不是连接ID)
3. 兼容 _hfState.connectionId
"""
import unittest
import re
from pathlib import Path


class TestHotfixConnectionIdFix(unittest.TestCase):
    """测试热修复连接ID获取修复"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_js = (self.root / 'static' / 'js' / 'components' / 'hotfix.js').read_text(encoding='utf-8')

    def test_getCurrentConnectionId_uses_window_currentConnId(self):
        """测试 getCurrentConnectionId 优先使用 window._currentConnId"""
        # 应该检查 window._currentConnId
        self.assertIn('window._currentConnId', self.hotfix_js)
        
        # 找到 getCurrentConnectionId 函数
        func_match = re.search(
            r'function getCurrentConnectionId\(\)\s*\{(.*?)^\}',
            self.hotfix_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 getCurrentConnectionId 函数")
        func_body = func_match.group(1)
        
        # 应该优先检查 window._currentConnId
        window_pos = func_body.find('window._currentConnId')
        hfstate_pos = func_body.find('_hfState.connectionId')
        
        self.assertGreater(window_pos, -1, "应该检查 window._currentConnId")
        self.assertGreater(hfstate_pos, -1, "应该检查 _hfState.connectionId")
        self.assertLess(window_pos, hfstate_pos, "应该优先检查 window._currentConnId")

    def test_not_using_csbTarget_text(self):
        """测试不再从 csbTarget 获取连接ID"""
        # 找到 getCurrentConnectionId 函数
        func_match = re.search(
            r'function getCurrentConnectionId\(\)\s*\{(.*?)^\}',
            self.hotfix_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 getCurrentConnectionId 函数")
        func_body = func_match.group(1)
        
        # 不应该再使用 csbTarget(那是显示文本,不是连接ID)
        self.assertNotIn('csbTarget', func_body, "不应该从 csbTarget 获取连接ID")
        self.assertNotIn('textContent', func_body, "不应该使用 textContent 获取连接ID")

    def test_returns_null_when_no_connection(self):
        """测试没有连接时返回 null"""
        # 找到 getCurrentConnectionId 函数
        func_match = re.search(
            r'function getCurrentConnectionId\(\)\s*\{(.*?)^\}',
            self.hotfix_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 getCurrentConnectionId 函数")
        func_body = func_match.group(1)
        
        # 应该有 return null
        self.assertIn('return null', func_body)

    def test_all_functions_use_getCurrentConnectionId(self):
        """测试所有热修复函数都使用 getCurrentConnectionId"""
        functions = [
            ('hotfixJad', r'async function hotfixJad\(\)'),
            ('hotfixUploadFile', r'async function hotfixUploadFile\(input\)'),
            ('hotfixCompile', r'async function hotfixCompile\(\)'),
            ('hotfixRedefine', r'async function hotfixRedefine\(\)'),
            ('hotfixVerify', r'async function hotfixVerify\(\)')
        ]
        
        for func_name, pattern in functions:
            # 找到函数定义
            func_match = re.search(
                rf'{pattern}\s*\{{(.*?)^\}}',
                self.hotfix_js,
                re.MULTILINE | re.DOTALL
            )
            self.assertIsNotNone(func_match, f"未找到 {func_name} 函数")
            func_body = func_match.group(1)
            
            # 应该调用 getCurrentConnectionId
            self.assertIn('getCurrentConnectionId()', func_body, 
                         f"{func_name} 应该调用 getCurrentConnectionId()")

    def test_connection_id_validation(self):
        """测试连接ID验证逻辑"""
        # 找到 hotfixJad 函数作为示例
        func_match = re.search(
            r'async function hotfixJad\(\)\s*\{(.*?)^\}',
            self.hotfix_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 hotfixJad 函数")
        func_body = func_match.group(1)
        
        # 应该有连接ID检查
        self.assertIn('if (!connId)', func_body, "应该检查 connId 是否存在")
        # 现在改为弹出多连接选择器,而不是简单提示
        self.assertIn('showConnectionSelectorForHotfix', func_body, "应该弹出多连接选择器")

    def test_complete_fix(self):
        """测试完整修复"""
        # 1. 使用 window._currentConnId
        self.assertIn('window._currentConnId', self.hotfix_js)
        
        # 2. 不使用 csbTarget
        func_match = re.search(
            r'function getCurrentConnectionId\(\)\s*\{(.*?)^\}',
            self.hotfix_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 getCurrentConnectionId 函数")
        func_body = func_match.group(1)
        self.assertNotIn('csbTarget', func_body)
        
        # 3. 所有函数都使用 getCurrentConnectionId
        self.assertIn('getCurrentConnectionId()', self.hotfix_js)


if __name__ == '__main__':
    unittest.main()
