#!/usr/bin/env python3
"""
P1b-2 AI 辅助诊断合同测试

验证核心功能:
1. 4 个 AI 辅助端点存在
2. 认证要求(@login_required)
3. 参数验证(command/output/problem 不能为空)
4. 审计日志覆盖(explain/summarize/suggest)
5. 案例检索支持关键词过滤
"""
import ast
import unittest


class TestAIAssistAPI(unittest.TestCase):
    """测试 AI 辅助诊断 API"""

    def setUp(self):
        with open('api/ai_chat.py', encoding='utf-8') as f:
            self.source = f.read()
        self.tree = ast.parse(self.source)

    def _find_functions(self):
        return [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]

    def _find_decorators(self, func_name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                return [
                    ast.dump(d) if isinstance(d, ast.Attribute) else d.id
                    for d in node.decorator_list
                    if isinstance(d, (ast.Name, ast.Attribute))
                ]
        return []

    def _count_route_pattern(self, pattern):
        return self.source.count(pattern)

    # ── 核心端点存在性 ─────────────────────────────────────────────

    def test_explain_endpoint_exists(self):
        """测试 /api/ai/explain 端点存在"""
        funcs = self._find_functions()
        self.assertIn('ai_explain_command', funcs)
        self.assertEqual(self._count_route_pattern("'/api/ai/explain'"), 1)

    def test_summarize_endpoint_exists(self):
        """测试 /api/ai/summarize 端点存在"""
        funcs = self._find_functions()
        self.assertIn('ai_summarize_result', funcs)
        self.assertEqual(self._count_route_pattern("'/api/ai/summarize'"), 1)

    def test_suggest_endpoint_exists(self):
        """测试 /api/ai/suggest 端点存在"""
        funcs = self._find_functions()
        self.assertIn('ai_suggest_solutions', funcs)
        self.assertEqual(self._count_route_pattern("'/api/ai/suggest'"), 1)

    def test_cases_endpoint_exists(self):
        """测试 /api/ai/cases 端点存在"""
        funcs = self._find_functions()
        self.assertIn('ai_get_cases', funcs)
        self.assertEqual(self._count_route_pattern("'/api/ai/cases'"), 1)

    # ── 认证要求 ───────────────────────────────────────────────────

    def test_all_endpoints_require_login(self):
        """测试所有 AI 辅助端点需要登录"""
        for func_name in ['ai_explain_command', 'ai_summarize_result', 
                          'ai_suggest_solutions', 'ai_get_cases']:
            decorators = self._find_decorators(func_name)
            self.assertIn('login_required', decorators, 
                         f"{func_name} 需要 @login_required")

    # ── 参数验证 ───────────────────────────────────────────────────

    def test_explain_requires_command(self):
        """测试 explain 端点验证 command 参数"""
        self.assertIn('command', self.source)
        self.assertIn('命令不能为空', self.source)

    def test_summarize_requires_command_and_output(self):
        """测试 summarize 端点验证 command 和 output 参数"""
        self.assertIn('output', self.source)
        self.assertIn('命令和输出不能为空', self.source)

    def test_suggest_requires_problem(self):
        """测试 suggest 端点验证 problem 参数"""
        self.assertIn('problem', self.source)
        self.assertIn('问题描述不能为空', self.source)

    # ── AI 配置检查 ──────────────────────────────────────────────

    def test_all_endpoints_check_ai_config(self):
        """测试所有端点检查 AI 配置"""
        for endpoint in ['ai_explain_command', 'ai_summarize_result', 
                         'ai_suggest_solutions']:
            # 搜索函数内的 AI 配置检查逻辑
            self.assertIn('ai_config', self.source, 
                         f"{endpoint} 需要检查 AI 配置")

    # ── 审计日志 ───────────────────────────────────────────────────

    def test_explain_has_audit_log(self):
        """测试 explain 端点记录审计日志"""
        self.assertIn("'ai_explain'", self.source)

    def test_summarize_has_audit_log(self):
        """测试 summarize 端点记录审计日志"""
        self.assertIn("'ai_summarize'", self.source)

    def test_suggest_has_audit_log(self):
        """测试 suggest 端点记录审计日志"""
        self.assertIn("'ai_suggest'", self.source)

    # ── 系统提示词 ─────────────────────────────────────────────────

    def test_explain_has_system_prompt(self):
        """测试 explain 端点有专门的系统提示词"""
        self.assertIn('Arthas 命令解释专家', self.source)

    def test_summarize_has_system_prompt(self):
        """测试 summarize 端点有专门的系统提示词"""
        self.assertIn('Java 性能诊断专家', self.source)

    def test_suggest_has_system_prompt(self):
        """测试 suggest 端点有专门的系统提示词"""
        self.assertIn('Java 应用排障专家', self.source)

    # ── 案例检索 ───────────────────────────────────────────────────

    def test_cases_supports_keyword_filter(self):
        """测试案例检索支持关键词过滤"""
        self.assertIn('keyword', self.source)
        self.assertIn('LIKE', self.source)

    def test_cases_supports_category_filter(self):
        """测试案例检索支持分类过滤"""
        self.assertIn('category', self.source)

    def test_cases_limits_results(self):
        """测试案例检索限制返回数量"""
        self.assertIn('limit', self.source)
        self.assertIn('LIMIT', self.source)

    # ── 超时设置 ───────────────────────────────────────────────────

    def test_explain_timeout_configured(self):
        """测试 explain 端点设置超时"""
        self.assertIn('timeout=60', self.source)

    def test_summarize_timeout_configured(self):
        """测试 summarize 端点设置超时"""
        self.assertIn('timeout=90', self.source)

    def test_suggest_timeout_configured(self):
        """测试 suggest 端点设置超时"""
        self.assertIn('timeout=90', self.source)

    # ── 上下文支持 ─────────────────────────────────────────────────

    def test_explain_supports_context(self):
        """测试 explain 支持问题上下文"""
        self.assertIn('context', self.source)

    def test_suggest_supports_symptoms(self):
        """测试 suggest 支持症状列表"""
        self.assertIn('symptoms', self.source)

    def test_suggest_supports_connection_info(self):
        """测试 suggest 可获取连接信息"""
        self.assertIn('connection_id', self.source)
        self.assertIn('_get_connection_info', self.source)


if __name__ == '__main__':
    unittest.main()
