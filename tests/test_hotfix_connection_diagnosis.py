#!/usr/bin/env python3
"""
P1b-1 热修复连接ID完整诊断测试

诊断:
1. 前端 getCurrentConnectionId() 逻辑
2. 后端 _get_connection() 逻辑  
3. _connections 字典结构
4. 连接ID格式匹配
"""
import unittest
import re
from pathlib import Path


class TestHotfixConnectionDiagnosis(unittest.TestCase):
    """热修复连接ID完整诊断"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.hotfix_js = (self.root / 'static' / 'js' / 'components' / 'hotfix.js').read_text(encoding='utf-8')
        self.hotfix_py = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')
        self.server_py = (self.root / 'server.py').read_text(encoding='utf-8')

    # ── 前端诊断 ─────────────────────────────────────────────────

    def test_frontend_getCurrentConnectionId_priority(self):
        """诊断: 前端获取连接ID的优先级"""
        func_match = re.search(
            r'function getCurrentConnectionId\(\)\s*\{(.*?)^\}',
            self.hotfix_js,
            re.MULTILINE | re.DOTALL
        )
        self.assertIsNotNone(func_match, "未找到 getCurrentConnectionId 函数")
        func_body = func_match.group(1)
        
        # 应该优先使用 window._currentConnId
        window_pos = func_body.find('window._currentConnId')
        hfstate_pos = func_body.find('_hfState.connectionId')
        
        self.assertGreater(window_pos, -1, "❌ 应该检查 window._currentConnId")
        self.assertGreater(hfstate_pos, -1, "❌ 应该检查 _hfState.connectionId")
        self.assertLess(window_pos, hfstate_pos, "❌ 应该优先检查 window._currentConnId")
        
        print("[OK] 前端连接ID获取优先级正确: window._currentConnId > _hfState.connectionId")

    def test_frontend_has_debug_logs(self):
        """诊断: 前端是否有调试日志"""
        self.assertIn("console.log('[Hotfix] 初始 connId:'", self.hotfix_js,
                     "❌ 应该有初始 connId 调试日志")
        self.assertIn("console.log('[Hotfix] 最终 connId:'", self.hotfix_js,
                     "❌ 应该有最终 connId 调试日志")
        self.assertIn("console.log('[Hotfix] 请求参数:'", self.hotfix_js,
                     "❌ 应该有请求参数调试日志")
        
        print("[OK] 前端调试日志完整")

    def test_frontend_calls_api_correctly(self):
        """诊断: 前端调用 API 的方式"""
        # 应该有 credentials: 'include'
        self.assertIn("credentials: 'include'", self.hotfix_js,
                     "❌ 应该包含 credentials: 'include'")
        
        # 应该传递 connection_id
        self.assertIn("connection_id: connId", self.hotfix_js,
                     "❌ 应该传递 connection_id")
        
        print("[OK] 前端 API 调用正确")

    # ── 后端诊断 ─────────────────────────────────────────────────

    def test_backend_imports_connections(self):
        """诊断: 后端是否正确导入 _connections"""
        # 应该有 try-except 处理 ImportError
        self.assertIn("try:", self.hotfix_py)
        self.assertIn("from backend.app_context import connections, connections_lock, ensure_connection", self.hotfix_py)
        self.assertIn("except ImportError:", self.hotfix_py)
        
        print("[OK] 后端导入 _connections 有异常处理")

    def test_backend_connection_check(self):
        """诊断: 后端连接检查逻辑"""
        # 应该有连接不存在时的调试日志
        self.assertIn("available_ids = list(_connections.keys())", self.hotfix_py,
                     "❌ 应该输出可用连接ID列表")
        self.assertIn("log.warning", self.hotfix_py,
                     "❌ 应该有 warning 日志")
        
        # 应该有 conn_id 在错误信息中
        self.assertIn("conn_id={conn_id}", self.hotfix_py,
                     "❌ 错误信息应该包含 conn_id")
        
        print("[OK] 后端连接检查有详细日志")

    def test_backend_permission_check(self):
        """诊断: 后端权限检查"""
        # 应该检查 user_id
        self.assertIn("entry.get('user_id')", self.hotfix_py,
                     "❌ 应该检查 user_id")
        
        # 应该支持 admin
        self.assertIn("current_user.is_admin", self.hotfix_py,
                     "❌ 应该支持 admin 权限")
        
        print("[OK] 后端权限检查完整")

    def test_backend_conn_object_check(self):
        """诊断: 后端检查 conn 对象"""
        # 应该检查 conn 是否为空
        self.assertIn("if not conn:", self.hotfix_py,
                     "❌ 应该检查 conn 对象是否为空")
        
        print("[OK] 后端检查 conn 对象")

    # ── 连接池结构诊断 ─────────────────────────────────────────────────

    def test_connections_structure(self):
        """诊断: _connections 字典结构"""
        # server.py 中应该是 {"conn": conn, "user_id": user_id}
        self.assertIn('"conn": conn', self.server_py)
        self.assertIn('"user_id": current_user.id', self.server_py)
        
        print("[OK] _connections 结构正确: {conn, user_id}")

    def test_connections_lock_usage(self):
        """诊断: 连接池锁使用"""
        # 应该使用 _connections_lock
        self.assertIn("with _connections_lock:", self.hotfix_py,
                     "❌ 应该使用 _connections_lock")
        
        print("[OK] 连接池锁使用正确")

    # ── 完整流程诊断 ─────────────────────────────────────────────────

    def test_complete_flow(self):
        """诊断: 完整连接获取流程"""
        issues = []
        
        # 1. 前端优先级
        if 'window._currentConnId' not in self.hotfix_js:
            issues.append("❌ 前端未使用 window._currentConnId")
        
        # 2. 前端调试
        if "console.log('[Hotfix]" not in self.hotfix_js:
            issues.append("❌ 前端缺少调试日志")
        
        # 3. 后端导入
        if "from backend.app_context import connections" not in self.hotfix_py:
            issues.append("❌ 后端未导入 _connections")
        
        # 4. 后端日志
        if "available_ids = list(_connections.keys())" not in self.hotfix_py:
            issues.append("❌ 后端缺少可用连接ID日志")
        
        # 5. 权限检查
        if "entry.get('user_id')" not in self.hotfix_py:
            issues.append("❌ 后端缺少权限检查")
        
        if issues:
            self.fail("连接获取流程存在问题:\n" + "\n".join(issues))
        
        print("[OK] 完整连接获取流程无问题")

    def test_common_pitfalls(self):
        """诊断: 常见陷阱检查"""
        pitfalls = []
        
        # 1. 不应该使用 csbTarget 文本(那是显示文本,不是连接ID)
        func_match = re.search(
            r'function getCurrentConnectionId\(\)\s*\{(.*?)^\}',
            self.hotfix_js,
            re.MULTILINE | re.DOTALL
        )
        if func_match and 'csbTarget' in func_match.group(1):
            pitfalls.append("❌ 仍在从 csbTarget 获取连接ID(错误!)")
        
        # 2. 后端错误信息应该包含 conn_id
        if '连接不存在"' in self.hotfix_py and 'conn_id=' not in self.hotfix_py:
            pitfalls.append("❌ 后端错误信息未包含 conn_id,难以调试")
        
        # 3. 前端应该有 credentials
        if "credentials: 'include'" not in self.hotfix_js:
            pitfalls.append("❌ 前端缺少 credentials: 'include',session 可能丢失")
        
        if pitfalls:
            self.fail("发现常见陷阱:\n" + "\n".join(pitfalls))
        
        print("[OK] 无常见陷阱")


if __name__ == '__main__':
    # 运行测试并打印诊断信息
    unittest.main(verbosity=2)
