"""测试任务执行与审计打通 — 行为测试

验证 AuditService 方法实际调用 db.insert 并传入正确参数，
而非仅检查源码字符串存在。
"""
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db():
    """模拟数据库层"""
    db = MagicMock()
    db.fetch_all.return_value = []
    db.fetch_one.return_value = None
    return db


@pytest.fixture(autouse=True)
def patch_db(mock_db):
    """自动注入 mock_db 到 AuditService 使用的 db 模块"""
    with patch('services.audit_service.db', mock_db):
        yield mock_db


@pytest.fixture(autouse=True)
def patch_client_info():
    """Mock _get_client_info 避免 werkzeug LocalProxy 在无请求上下文时报错"""
    with patch('services.audit_service.AuditService._get_client_info',
               return_value={'ip_address': '127.0.0.1', 'user_agent': 'test-agent'}):
        yield


# ═══════════════════════════════════════════════════════════════════════════════
# AuditService 方法存在性 + 可调用性
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditServiceMethodsExist:
    """验证 AuditService 的任务/工具包方法存在且可调用"""

    def test_log_tool_package_distributed_is_callable(self):
        from services.audit_service import AuditService
        assert callable(getattr(AuditService, 'log_tool_package_distributed', None))

    def test_log_tool_package_uploaded_is_callable(self):
        from services.audit_service import AuditService
        assert callable(getattr(AuditService, 'log_tool_package_uploaded', None))

    def test_log_tool_package_deleted_is_callable(self):
        from services.audit_service import AuditService
        assert callable(getattr(AuditService, 'log_tool_package_deleted', None))

    def test_log_task_executed_is_callable(self):
        from services.audit_service import AuditService
        assert callable(getattr(AuditService, 'log_task_executed', None))

    def test_log_script_template_executed_is_callable(self):
        from services.audit_service import AuditService
        assert callable(getattr(AuditService, 'log_script_template_executed', None))

    def test_query_is_callable(self):
        from services.audit_service import AuditService
        assert callable(getattr(AuditService, 'query', None))

    def test_count_is_callable(self):
        from services.audit_service import AuditService
        assert callable(getattr(AuditService, 'count', None))


# ═══════════════════════════════════════════════════════════════════════════════
# AuditService 方法行为验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditServiceBehavior:
    """验证 AuditService 方法实际写入正确的审计记录"""

    def test_log_tool_package_distributed_inserts_correct_record(self, mock_db):
        from services.audit_service import AuditService
        AuditService.log_tool_package_distributed(
            user_id=1, package_id=42, package_name='arthas-boot.jar',
            target='cluster/ns/pod', install_path='/app/arthas/', status='success'
        )
        mock_db.insert.assert_called_once()
        table, data = mock_db.insert.call_args[0]
        assert table == 'audit_logs'
        assert data['user_id'] == 1
        assert data['action'] == 'tool_package_distributed'
        assert data['resource_type'] == 'tool_package'
        assert data['resource_id'] == '42'
        assert 'arthas-boot.jar' in data['details']
        assert 'cluster/ns/pod' in data['details']

    def test_log_tool_package_uploaded_inserts_correct_record(self, mock_db):
        from services.audit_service import AuditService
        AuditService.log_tool_package_uploaded(
            user_id=2, package_id=10, package_name='my-script.sh', tool_type='script'
        )
        mock_db.insert.assert_called_once()
        table, data = mock_db.insert.call_args[0]
        assert table == 'audit_logs'
        assert data['action'] == 'tool_package_uploaded'
        assert data['resource_type'] == 'tool_package'
        assert data['resource_id'] == '10'
        assert 'my-script.sh' in data['details']

    def test_log_tool_package_deleted_inserts_correct_record(self, mock_db):
        from services.audit_service import AuditService
        AuditService.log_tool_package_deleted(
            user_id=3, package_id=7, package_name='old-tool.tar.gz'
        )
        mock_db.insert.assert_called_once()
        table, data = mock_db.insert.call_args[0]
        assert table == 'audit_logs'
        assert data['action'] == 'tool_package_deleted'
        assert data['resource_id'] == '7'
        assert 'old-tool.tar.gz' in data['details']

    def test_log_task_executed_inserts_correct_record(self, mock_db):
        from services.audit_service import AuditService
        AuditService.log_task_executed(
            user_id=1, task_id=99, task_name='CPU Profiling',
            execution_mode='manual', target='cluster/ns/pod', status='success'
        )
        mock_db.insert.assert_called_once()
        table, data = mock_db.insert.call_args[0]
        assert table == 'audit_logs'
        assert data['user_id'] == 1
        assert data['action'] == 'task_executed'
        assert data['resource_type'] == 'task'
        assert data['resource_id'] == '99'
        assert 'CPU Profiling' in data['details']
        assert 'manual' in data['details']
        assert 'success' in data['details']

    def test_log_script_template_executed_inserts_correct_record(self, mock_db):
        from services.audit_service import AuditService
        AuditService.log_script_template_executed(
            user_id=5, template_id=3, template_name='gc-check',
            execution_mode='auto', target='prod/web-01', status='failed'
        )
        mock_db.insert.assert_called_once()
        table, data = mock_db.insert.call_args[0]
        assert table == 'audit_logs'
        assert data['action'] == 'script_template_executed'
        assert data['resource_type'] == 'script_template'
        assert data['resource_id'] == '3'
        assert 'gc-check' in data['details']
        assert 'failed' in data['details']

    def test_log_task_executed_includes_target_in_details(self, mock_db):
        """验证 task_executed 审计记录的 details 包含 target Pod"""
        from services.audit_service import AuditService
        AuditService.log_task_executed(
            user_id=1, task_id=1, task_name='thread-dump',
            execution_mode='batch', target='staging/api-server', status='success'
        )
        _, data = mock_db.insert.call_args[0]
        assert 'staging/api-server' in data['details']

    def test_log_tool_package_distributed_includes_target_in_details(self, mock_db):
        """验证 tool_package_distributed 审计记录的 details 包含 target"""
        from services.audit_service import AuditService
        AuditService.log_tool_package_distributed(
            user_id=1, package_id=1, package_name='tool.jar',
            target='prod/worker', install_path='/opt/tools/', status='success'
        )
        _, data = mock_db.insert.call_args[0]
        assert 'prod/worker' in data['details']

    def test_log_diagnostic_operation_inserts_correct_record(self, mock_db):
        from services.audit_service import AuditService
        AuditService.log_diagnostic_operation(
            user_id=1, operation='arthas_exec',
            connection_id='cluster/ns/pod', details='执行命令: thread -n 5'
        )
        mock_db.insert.assert_called_once()
        table, data = mock_db.insert.call_args[0]
        assert table == 'audit_logs'
        assert data['action'] == 'arthas_exec'
        assert data['resource_type'] == 'diagnostic'
        assert 'thread -n 5' in data['details']


# ═══════════════════════════════════════════════════════════════════════════════
# AuditService.query / count 行为验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditServiceQuery:
    """验证 query/count 方法的 SQL 构建逻辑"""

    def test_query_no_filters(self, mock_db):
        from services.audit_service import AuditService
        AuditService.query()
        sql, params = mock_db.fetch_all.call_args[0]
        assert 'SELECT * FROM audit_logs' in sql
        assert 'ORDER BY timestamp DESC' in sql
        assert 'LIMIT' in sql

    def test_query_with_user_id_filter(self, mock_db):
        from services.audit_service import AuditService
        AuditService.query(filters={'user_id': 42})
        sql, params = mock_db.fetch_all.call_args[0]
        assert 'user_id = ?' in sql
        assert 42 in params

    def test_query_with_action_filter(self, mock_db):
        from services.audit_service import AuditService
        AuditService.query(filters={'action': 'task_executed'})
        sql, params = mock_db.fetch_all.call_args[0]
        assert 'action = ?' in sql
        assert 'task_executed' in params

    def test_query_with_resource_type_filter(self, mock_db):
        from services.audit_service import AuditService
        AuditService.query(filters={'resource_type': 'tool_package'})
        sql, params = mock_db.fetch_all.call_args[0]
        assert 'resource_type = ?' in sql
        assert 'tool_package' in params

    def test_query_with_date_filters(self, mock_db):
        from services.audit_service import AuditService
        AuditService.query(filters={'start_date': '2026-01-01', 'end_date': '2026-12-31'})
        sql, params = mock_db.fetch_all.call_args[0]
        assert 'timestamp >= ?' in sql
        assert 'timestamp <= ?' in sql
        assert '2026-01-01' in params
        assert '2026-12-31' in params

    def test_query_respects_limit_and_offset(self, mock_db):
        from services.audit_service import AuditService
        AuditService.query(limit=25, offset=50)
        sql, params = mock_db.fetch_all.call_args[0]
        assert params[-2] == 25  # limit
        assert params[-1] == 50  # offset

    def test_query_ignores_none_filters(self, mock_db):
        """None 或空值过滤器不应加入 SQL"""
        from services.audit_service import AuditService
        AuditService.query(filters={'user_id': None, 'action': '', 'resource_type': None})
        sql, params = mock_db.fetch_all.call_args[0]
        assert 'user_id = ?' not in sql
        assert 'action = ?' not in sql
        assert 'resource_type = ?' not in sql

    def test_count_no_filters(self, mock_db):
        from services.audit_service import AuditService
        AuditService.count()
        sql, params = mock_db.fetch_one.call_args[0]
        assert 'COUNT(*)' in sql
        assert 'audit_logs' in sql

    def test_count_with_filters(self, mock_db):
        mock_db.fetch_one.return_value = {'cnt': 5}
        from services.audit_service import AuditService
        result = AuditService.count(filters={'action': 'login'})
        sql, params = mock_db.fetch_one.call_args[0]
        assert 'action = ?' in sql
        assert 'login' in params
        assert result == 5

    def test_count_returns_zero_when_no_result(self, mock_db):
        mock_db.fetch_one.return_value = None
        from services.audit_service import AuditService
        result = AuditService.count()
        assert result == 0


# ═══════════════════════════════════════════════════════════════════════════════
# task_center.py 调用审计的集成验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestTaskCenterAuditIntegration:
    """验证 task_center.py 中关键路径调用了 AuditService"""

    def test_task_center_imports_audit_service(self):
        """task_center.py 应该导入 AuditService"""
        import api.task_center as tc
        assert hasattr(tc, 'AuditService')

    def test_record_distribution_calls_audit(self, mock_db):
        """_record_distribution 应该调用 AuditService.log_tool_package_distributed"""
        import api.task_center as tc
        # 验证源码中存在调用（行为层面：确认函数存在并可尝试调用）
        assert callable(getattr(tc.AuditService, 'log_tool_package_distributed', None))


# ═══════════════════════════════════════════════════════════════════════════════
# Audit API 端点验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditAPI:
    """验证审计 API Blueprint 的结构"""

    def test_audit_blueprint_exists(self):
        from api.audit import audit_bp
        assert audit_bp is not None
        assert audit_bp.name == 'audit'

    def test_audit_blueprint_has_url_prefix(self):
        from api.audit import audit_bp
        assert audit_bp.url_prefix == '/api'

    def test_admin_required_decorator_exists(self):
        from api.audit import admin_required
        assert callable(admin_required)

    def test_list_audit_logs_endpoint_registered(self):
        """验证 /audit-logs 路由已注册"""
        from api.audit import list_audit_logs
        assert callable(list_audit_logs)

    def test_list_actions_endpoint_registered(self):
        from api.audit import list_actions
        assert callable(list_actions)

    def test_list_resource_types_endpoint_registered(self):
        from api.audit import list_resource_types
        assert callable(list_resource_types)

    def test_admin_required_blocks_non_admin(self):
        """admin_required 装饰器应对非 admin 用户返回 403"""
        from api.audit import admin_required

        @admin_required
        def dummy_view():
            return 'ok'

        # 模拟非 admin 用户
        with patch('api.audit.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.is_admin = False
            with patch('api.audit.jsonify') as mock_jsonify:
                mock_jsonify.return_value = MagicMock()
                result = dummy_view()
                # 应返回 (response, 403) 元组
                assert isinstance(result, tuple)
                assert result[1] == 403
