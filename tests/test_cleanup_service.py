#!/usr/bin/env python3
"""
P1b-3 清理服务合同测试

验证核心功能:
1. CleanupService 核心方法存在
2. 连接 TTL 清理逻辑
3. 产物清理逻辑
4. 日志清理逻辑
5. 磁盘水位监控
6. API 端点完整性
7. 配置验证和权限控制
"""
import ast
import unittest


class TestCleanupService(unittest.TestCase):
    """测试清理服务核心逻辑"""

    def setUp(self):
        with open('services/cleanup_service.py', encoding='utf-8') as f:
            self.source = f.read()
        self.tree = ast.parse(self.source)

    def _find_functions(self):
        return [n.name for n in ast.walk(self.tree) if isinstance(n, ast.FunctionDef)]

    def _find_class(self, class_name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    def _count_pattern(self, pattern):
        return self.source.count(pattern)

    # ── 核心方法存在性 ─────────────────────────────────────────────

    def test_cleanup_service_class_exists(self):
        """测试 CleanupService 类存在"""
        cls = self._find_class('CleanupService')
        self.assertIsNotNone(cls)

    def test_cleanup_expired_connections_exists(self):
        """测试清理过期连接方法存在"""
        funcs = self._find_functions()
        self.assertIn('cleanup_expired_connections', funcs)

    def test_cleanup_old_artifacts_exists(self):
        """测试清理过期产物方法存在"""
        funcs = self._find_functions()
        self.assertIn('cleanup_old_artifacts', funcs)

    def test_cleanup_old_logs_exists(self):
        """测试清理过期日志方法存在"""
        funcs = self._find_functions()
        self.assertIn('cleanup_old_logs', funcs)

    def test_check_disk_usage_exists(self):
        """测试磁盘使用率检查方法存在"""
        funcs = self._find_functions()
        self.assertIn('check_disk_usage', funcs)

    def test_run_full_cleanup_exists(self):
        """测试完整清理流程方法存在"""
        funcs = self._find_functions()
        self.assertIn('run_full_cleanup', funcs)

    # ── 默认配置 ───────────────────────────────────────────────────

    def test_default_config_connection_ttl(self):
        """测试默认连接 TTL 配置"""
        self.assertIn("'connection_ttl_hours': 24", self.source)

    def test_default_config_artifact_retention(self):
        """测试默认产物保留天数"""
        self.assertIn("'artifact_retention_days': 7", self.source)

    def test_default_config_log_retention(self):
        """测试默认日志保留天数"""
        self.assertIn("'log_retention_days': 30", self.source)

    def test_default_config_disk_threshold(self):
        """测试默认磁盘告警阈值"""
        self.assertIn("'disk_warning_threshold': 0.80", self.source)

    def test_default_config_max_heapdump(self):
        """测试默认 heapdump 大小限制"""
        self.assertIn("'max_heapdump_size_gb': 2", self.source)

    # ── 连接清理逻辑 ───────────────────────────────────────────────

    def test_connection_cleanup_status_check(self):
        """测试连接清理检查 status != 'ready'"""
        self.assertIn("status != 'ready'", self.source)

    def test_connection_cleanup_last_ping_check(self):
        """测试连接清理检查 last_ping_at"""
        self.assertIn('last_ping_at', self.source)

    def test_connection_cleanup_updates_status(self):
        """测试连接清理更新状态为 disconnected"""
        self.assertIn("'disconnected'", self.source)

    def test_connection_cleanup_has_audit_log(self):
        """测试连接清理记录审计日志"""
        self.assertIn("'connection_ttl_cleanup'", self.source)

    # ── 产物清理逻辑 ───────────────────────────────────────────────

    def test_artifact_cleanup_walks_directory(self):
        """测试产物清理遍历目录"""
        self.assertIn('os.walk', self.source)

    def test_artifact_cleanup_checks_mtime(self):
        """测试产物清理检查文件修改时间"""
        self.assertIn('getmtime', self.source)

    def test_artifact_cleanup_large_file_warning(self):
        """测试产物清理大文件告警"""
        self.assertIn('.hprof', self.source)
        self.assertIn('.jfr', self.source)

    def test_artifact_cleanup_removes_files(self):
        """测试产物清理删除文件"""
        self.assertIn('os.remove', self.source)

    def test_artifact_cleanup_empty_dirs(self):
        """测试产物清理空目录"""
        self.assertIn('_cleanup_empty_dirs', self.source)
        self.assertIn('os.rmdir', self.source)

    # ── 日志清理逻辑 ───────────────────────────────────────────────

    def test_log_cleanup_uses_cutoff_time(self):
        """测试日志清理使用截止时间"""
        self.assertIn('timedelta(days=', self.source)

    def test_log_cleanup_deletes_records(self):
        """测试日志清理删除数据库记录"""
        self.assertIn("db.delete('profiler_logs'", self.source)

    # ── 磁盘监控逻辑 ───────────────────────────────────────────────

    def test_disk_usage_uses_shutil(self):
        """测试磁盘监控使用 shutil.disk_usage"""
        self.assertIn('shutil.disk_usage', self.source)

    def test_disk_usage_calculates_percent(self):
        """测试磁盘监控计算使用率"""
        self.assertIn('usage_percent', self.source)

    def test_disk_usage_warning_threshold(self):
        """测试磁盘监控检查告警阈值"""
        self.assertIn('disk_warning_threshold', self.source)

    def test_disk_usage_returns_warning_flag(self):
        """测试磁盘监控返回警告标志"""
        self.assertIn("'warning': warning", self.source)

    # ── 完整清理流程 ───────────────────────────────────────────────

    def test_full_cleanup_calls_all_methods(self):
        """测试完整清理调用所有清理方法"""
        self.assertIn('cleanup_expired_connections', self.source)
        self.assertIn('cleanup_old_artifacts', self.source)
        self.assertIn('cleanup_old_logs', self.source)
        self.assertIn('check_disk_usage', self.source)

    def test_full_cleanup_returns_report(self):
        """测试完整清理返回报告"""
        self.assertIn("'timestamp'", self.source)
        self.assertIn("'elapsed_seconds'", self.source)
        self.assertIn("'total_cleaned_items'", self.source)

    # ── 目录统计 ───────────────────────────────────────────────────

    def test_directory_stats_counts_files(self):
        """测试目录统计文件数量"""
        self.assertIn('total_files', self.source)

    def test_directory_stats_calculates_size(self):
        """测试目录统计计算大小"""
        self.assertIn('total_size_mb', self.source)

    def test_directory_stats_tracks_oldest_newest(self):
        """测试目录统计追踪最旧/最新文件"""
        self.assertIn('oldest_file', self.source)
        self.assertIn('newest_file', self.source)


class TestCleanupAPI(unittest.TestCase):
    """测试清理 API 端点"""

    def setUp(self):
        with open('api/cleanup.py', encoding='utf-8') as f:
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

    # ── API 端点存在性 ─────────────────────────────────────────────

    def test_run_cleanup_endpoint_exists(self):
        """测试 /api/cleanup/run 端点存在"""
        funcs = self._find_functions()
        self.assertIn('run_cleanup', funcs)
        self.assertEqual(self._count_route_pattern("'/api/cleanup/run'"), 1)

    def test_stats_endpoint_exists(self):
        """测试 /api/cleanup/stats 端点存在"""
        funcs = self._find_functions()
        self.assertIn('get_cleanup_stats', funcs)
        self.assertEqual(self._count_route_pattern("'/api/cleanup/stats'"), 1)

    def test_config_get_endpoint_exists(self):
        """测试 GET /api/cleanup/config 端点存在"""
        funcs = self._find_functions()
        self.assertIn('get_cleanup_config', funcs)
        self.assertEqual(self._count_route_pattern("'/api/cleanup/config'"), 2)  # GET + POST

    def test_config_post_endpoint_exists(self):
        """测试 POST /api/cleanup/config 端点存在"""
        funcs = self._find_functions()
        self.assertIn('update_cleanup_config', funcs)

    # ── 认证要求 ───────────────────────────────────────────────────

    def test_all_endpoints_require_login(self):
        """测试所有清理端点需要登录"""
        for func_name in ['run_cleanup', 'get_cleanup_stats', 
                          'get_cleanup_config', 'update_cleanup_config']:
            decorators = self._find_decorators(func_name)
            self.assertIn('login_required', decorators, 
                         f"{func_name} 需要 @login_required")

    # ── 权限控制 ───────────────────────────────────────────────────

    def test_config_update_requires_admin(self):
        """测试配置更新需要管理员权限"""
        self.assertIn("current_user.role != 'admin'", self.source)
        self.assertIn('仅管理员可修改清理配置', self.source)

    # ── 配置验证 ───────────────────────────────────────────────────

    def test_config_validates_range(self):
        """测试配置值范围验证"""
        self.assertIn('connection_ttl_hours', self.source)
        self.assertIn('artifact_retention_days', self.source)
        self.assertIn('log_retention_days', self.source)
        self.assertIn('disk_warning_threshold', self.source)

    def test_config_validates_type(self):
        """测试配置类型验证"""
        self.assertIn('ValueError', self.source)
        self.assertIn('TypeError', self.source)

    # ── 审计日志 ───────────────────────────────────────────────────

    def test_run_cleanup_has_audit_log(self):
        """测试手动清理记录审计日志"""
        self.assertIn("'cleanup_manual'", self.source)

    def test_config_update_has_audit_log(self):
        """测试配置更新记录审计日志"""
        self.assertIn("'cleanup_config_updated'", self.source)

    # ── 统计功能 ───────────────────────────────────────────────────

    def test_stats_returns_disk_usage(self):
        """测试统计返回磁盘使用率"""
        self.assertIn('disk_usage', self.source)

    def test_stats_returns_connection_counts(self):
        """测试统计返回连接数量"""
        self.assertIn('total_conns', self.source)
        self.assertIn('ready_conns', self.source)
        self.assertIn('expired_conns', self.source)

    # ── 清理参数 ───────────────────────────────────────────────────

    def test_run_cleanup_supports_user_only(self):
        """测试清理支持仅清理当前用户"""
        self.assertIn('user_only', self.source)


if __name__ == '__main__':
    unittest.main()
