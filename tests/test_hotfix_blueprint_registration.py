#!/usr/bin/env python3
"""
P1b-1 热修复 Blueprint 注册测试

验证:
1. hotfix_bp 在 api/__init__.py 中导入
2. hotfix_bp 在 api/__init__.py 中注册
3. 所有热修复 API 路由可用
"""
import unittest
import re
from pathlib import Path


class TestHotfixBlueprintRegistration(unittest.TestCase):
    """测试热修复 Blueprint 注册"""

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.api_init = (self.root / 'api' / '__init__.py').read_text(encoding='utf-8')

    def test_hotfix_bp_imported(self):
        """测试 hotfix_bp 在 api/__init__.py 中导入"""
        self.assertIn('from api.hotfix import hotfix_bp', self.api_init)

    def test_hotfix_bp_registered(self):
        """测试 hotfix_bp 在 api/__init__.py 中注册"""
        self.assertIn('app.register_blueprint(hotfix_bp)', self.api_init)

    def test_import_before_register(self):
        """测试导入在注册之前"""
        import_pos = self.api_init.find('from api.hotfix import hotfix_bp')
        register_pos = self.api_init.find('app.register_blueprint(hotfix_bp)')
        
        self.assertGreater(import_pos, -1, "应该导入 hotfix_bp")
        self.assertGreater(register_pos, -1, "应该注册 hotfix_bp")
        self.assertLess(import_pos, register_pos, "导入应该在注册之前")

    def test_hotfix_bp_defined(self):
        """测试 api/hotfix.py 中定义了 hotfix_bp"""
        hotfix_py = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')
        self.assertIn("Blueprint('hotfix'", hotfix_py)
        self.assertIn("url_prefix='/api/hotfix'", hotfix_py)

    def test_all_hotfix_routes_defined(self):
        """测试所有热修复路由都已定义"""
        hotfix_py = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')
        
        required_routes = [
            ("@hotfix_bp.route('/jad'", "jad 查看源码"),
            ("@hotfix_bp.route('/upload'", "upload 上传文件"),
            ("@hotfix_bp.route('/compile'", "compile 编译"),
            ("@hotfix_bp.route('/redefine'", "redefine 热更新"),
            ("@hotfix_bp.route('/verification'", "verification 验证报告"),
            ("@hotfix_bp.route('/limitations'", "limitations 技术限制"),
        ]
        
        for route, desc in required_routes:
            self.assertIn(route, hotfix_py, f"缺少路由: {desc}")

    def test_all_routes_use_post(self):
        """测试所有路由使用正确的方法"""
        hotfix_py = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')
        
        # 查找所有 @hotfix_bp.route 装饰器
        routes = re.findall(r"@hotfix_bp\.route\('([^']+)'.*methods=\['([^']+)'\]", hotfix_py)
        
        self.assertGreater(len(routes), 0, "应该至少有一个路由")
        
        # GET 路由(查询操作)
        get_routes = {'/artifacts', '/limitations'}
        
        for path, method in routes:
            if path in get_routes:
                self.assertEqual(method, 'GET', f"路由 {path} 应该使用 GET 方法")
            else:
                self.assertEqual(method, 'POST', f"路由 {path} 应该使用 POST 方法")

    def test_all_routes_login_required(self):
        """测试所有路由都有 @login_required 装饰器"""
        hotfix_py = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')
        
        # 查找所有路由函数
        func_defs = re.findall(r'@hotfix_bp\.route.*?\ndef (hotfix_\w+)\(\)', hotfix_py, re.DOTALL)
        
        self.assertGreater(len(func_defs), 0, "应该至少有一个路由函数")
        
        # 检查每个函数前是否有 @login_required
        for func_name in func_defs:
            # 查找函数定义前的装饰器
            func_pattern = rf'(@login_required\s*\n\s*def {func_name}\()'
            self.assertRegex(hotfix_py, func_pattern, f"函数 {func_name} 应该有 @login_required")

    def test_blueprint_url_prefix(self):
        """测试 Blueprint URL 前缀正确"""
        hotfix_py = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')
        self.assertIn("url_prefix='/api/hotfix'", hotfix_py)

    def test_complete_registration(self):
        """测试完整注册流程"""
        # 1. Blueprint 定义
        hotfix_py = (self.root / 'api' / 'hotfix.py').read_text(encoding='utf-8')
        self.assertIn("hotfix_bp = Blueprint('hotfix'", hotfix_py)
        
        # 2. 导入
        self.assertIn('from api.hotfix import hotfix_bp', self.api_init)
        
        # 3. 注册
        self.assertIn('app.register_blueprint(hotfix_bp)', self.api_init)
        
        # 4. 路由
        self.assertIn("@hotfix_bp.route('/jad'", hotfix_py)


if __name__ == '__main__':
    unittest.main()
