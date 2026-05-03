#!/usr/bin/env python3
"""
测试热修复服务使用正确的 Arthas API

验证:
1. jad 使用 exec_once 而非 execute
2. mc 使用 exec_once 而非 execute
3. redefine 使用 exec_once 而非 execute
4. 正确解析 Arthas HTTP API 响应格式
"""
import unittest
import re
from pathlib import Path


class TestHotfixArthasApiUsage(unittest.TestCase):
    """测试热修复服务使用正确的 Arthas API"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_service_py = (self.root / 'services' / 'hotfix_service.py').read_text(encoding='utf-8')

    def test_jad_uses_exec_once(self):
        """测试 jad 使用 exec_once"""
        # 直接检查文件内容
        self.assertIn('.exec_once(', self.hotfix_service_py,
                     "❌ 应该使用 exec_once 方法")
        
        # 不应该使用 .execute(
        lines = self.hotfix_service_py.split('\n')
        for i, line in enumerate(lines, 1):
            if '.execute(' in line and not line.strip().startswith('#'):
                self.fail(f"❌ 第 {i} 行仍在使用 .execute() 方法: {line.strip()}")

    def test_mc_uses_exec_once(self):
        """测试 mc 使用 exec_once"""
        # exec_once 应该被调用 3 次 (jad, mc, redefine)
        exec_once_count = self.hotfix_service_py.count('.exec_once(')
        self.assertGreaterEqual(exec_once_count, 3,
                               f"❌ exec_once 调用次数不足: {exec_once_count} < 3")

    def test_redefine_uses_exec_once(self):
        """测试 redefine 使用 exec_once"""
        # 已经在 test_mc_uses_exec_once 中验证
        exec_once_count = self.hotfix_service_py.count('.exec_once(')
        self.assertGreaterEqual(exec_once_count, 3,
                               f"❌ exec_once 调用次数不足: {exec_once_count} < 3")

    def test_jad_checks_state_field(self):
        """测试 jad 检查 state 字段"""
        # state 字段检查应该至少 3 次
        state_check_count = self.hotfix_service_py.count("result.get('state')")
        self.assertGreaterEqual(state_check_count, 3,
                               f"❌ state 字段检查次数不足: {state_check_count} < 3")
        
        # 应该检查 SUCCEEDED
        self.assertIn('SUCCEEDED', self.hotfix_service_py,
                     "❌ 应该检查 SUCCEEDED 状态")

    def test_jad_extracts_source_from_body(self):
        """测试 jad 从 body 提取源码"""
        # 应该从 body 提取
        self.assertIn("result.get('body'", self.hotfix_service_py,
                     "❌ 应该从 body 提取源码")
        
        # 应该处理 results 数组
        self.assertIn("body.get('results'", self.hotfix_service_py,
                     "❌ 应该处理 results 数组")

    def test_mc_checks_state_field(self):
        """测试 mc 检查 state 字段"""
        # 已经在 test_jad_checks_state_field 中验证
        state_check_count = self.hotfix_service_py.count("result.get('state')")
        self.assertGreaterEqual(state_check_count, 3,
                               f"❌ state 字段检查次数不足: {state_check_count} < 3")

    def test_redefine_checks_state_field(self):
        """测试 redefine 检查 state 字段"""
        # 已经在 test_jad_checks_state_field 中验证
        state_check_count = self.hotfix_service_py.count("result.get('state')")
        self.assertGreaterEqual(state_check_count, 3,
                               f"❌ state 字段检查次数不足: {state_check_count} < 3")

    def test_no_execute_method_calls(self):
        """测试没有使用 .execute() 方法"""
        # 检查整个文件
        if '.execute(' in self.hotfix_service_py:
            # 排除注释中的
            lines = self.hotfix_service_py.split('\n')
            for i, line in enumerate(lines, 1):
                if '.execute(' in line and not line.strip().startswith('#'):
                    self.fail(f"❌ 第 {i} 行仍在使用 .execute() 方法: {line.strip()}")

    def test_complete_api_usage(self):
        """测试完整的 API 使用"""
        issues = []
        
        # 1. 所有命令都应该使用 exec_once
        exec_once_count = self.hotfix_service_py.count('.exec_once(')
        if exec_once_count < 3:
            issues.append(f"❌ exec_once 调用次数不足: {exec_once_count} < 3")
        
        # 2. 不应该有 .execute()
        if '.execute(' in self.hotfix_service_py:
            issues.append("❌ 仍在使用 .execute() 方法")
        
        # 3. 应该检查 state 字段
        state_check_count = self.hotfix_service_py.count("result.get('state')")
        if state_check_count < 3:
            issues.append(f"❌ state 字段检查次数不足: {state_check_count} < 3")
        
        if issues:
            self.fail("API 使用存在问题:\n" + "\n".join(issues))


if __name__ == '__main__':
    unittest.main()
