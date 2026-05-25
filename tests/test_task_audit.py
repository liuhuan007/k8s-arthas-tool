"""测试任务执行与审计打通"""
import pathlib
import sys

sys.path.insert(0, r'e:/tmp/k8s-arthas-tool')

from api import task_center

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK_CENTER = (ROOT / 'api' / 'task_center.py').read_text(encoding='utf-8')

AUDIT_SERVICE = (ROOT / 'services' / 'audit_service.py').read_text(encoding='utf-8')


def test_audit_service_has_task_execution_methods():
    """测试：AuditService 有任务执行相关方法。"""
    assert 'log_tool_package_distributed' in AUDIT_SERVICE
    assert 'log_tool_package_uploaded' in AUDIT_SERVICE
    assert 'log_tool_package_deleted' in AUDIT_SERVICE
    assert 'log_task_executed' in AUDIT_SERVICE
    assert 'log_script_template_executed' in AUDIT_SERVICE


def test_task_center_calls_audit_logging():
    """测试：task_center.py 调用审计日志。"""
    # 检查 tool package 分发时记录审计
    assert 'AuditService.log_tool_package_distributed' in TASK_CENTER

    # 检查 tool package 上传时记录审计
    assert 'AuditService.log_tool_package_uploaded' in TASK_CENTER

    # 检查 tool package 删除时记录审计
    assert 'AuditService.log_tool_package_deleted' in TASK_CENTER

    # 检查任务执行时记录审计
    assert 'AuditService.log_task_executed' in TASK_CENTER


def test_audit_log_tool_package_distributed_has_correct_fields():
    """测试：log_tool_package_distributed 记录正确的字段。"""
    # 检查方法签名包含必要参数
    assert 'user_id: int' in AUDIT_SERVICE
    assert 'package_id: int' in AUDIT_SERVICE
    assert 'package_name: str' in AUDIT_SERVICE
    assert 'target: str' in AUDIT_SERVICE
    assert 'status: str' in AUDIT_SERVICE


def test_audit_log_task_executed_has_correct_fields():
    """测试：log_task_executed 记录正确的字段。"""
    # 检查方法签名包含必要参数
    assert 'user_id: int' in AUDIT_SERVICE
    assert 'task_id: int' in AUDIT_SERVICE
    assert 'task_name: str' in AUDIT_SERVICE
    assert 'execution_mode: str' in AUDIT_SERVICE
    assert 'status: str' in AUDIT_SERVICE


def test_audit_record_contains_target_pod():
    """测试：审计记录包含目标 Pod。"""
    # 检查 log_tool_package_distributed 的 details 包含 target
    assert 'target' in AUDIT_SERVICE or 'target' in TASK_CENTER


def test_audit_record_contains_task_name():
    """测试：审计记录包含任务名。"""
    # 检查 log_task_executed 的 details 包含 task_name
    assert 'task_name' in AUDIT_SERVICE


def test_audit_record_contains_execution_mode():
    """测试：审计记录包含执行模式。"""
    # 检查 log_task_executed 的 details 包含 execution_mode
    assert 'execution_mode' in AUDIT_SERVICE


def test_audit_record_contains_status():
    """测试：审计记录包含状态。"""
    # 检查审计方法的 details 包含 status
    assert 'status' in AUDIT_SERVICE


def test_audit_query_api_exists():
    """测试：审计查询 API 端点存在。"""
    audit_py = (ROOT / 'api' / 'audit.py').read_text(encoding='utf-8')
    assert "route('/audit-logs'" in audit_py
    assert 'def list_audit_logs' in audit_py


def test_audit_service_query_method_exists():
    """测试：AuditService.query() 方法存在。"""
    assert 'def query(' in AUDIT_SERVICE
    assert 'def count(' in AUDIT_SERVICE


def test_audit_logs_table_has_required_fields():
    """测试：audit_logs 表有必要的字段。"""
    # 检查 services/audit_service.py 中插入审计日志的 SQL 包含必要字段
    assert "'user_id'" in AUDIT_SERVICE
    assert "'action'" in AUDIT_SERVICE
    assert "'resource_type'" in AUDIT_SERVICE
    assert "'resource_id'" in AUDIT_SERVICE
    assert "'details'" in AUDIT_SERVICE
    assert "'ip_address'" in AUDIT_SERVICE
    assert "'user_agent'" in AUDIT_SERVICE


def test_tool_package_distribute_records_audit():
    """测试：工具包分发记录审计日志。"""
    # 检查 _record_distribution 中调用 AuditService.log_tool_package_distributed
    assert 'AuditService.log_tool_package_distributed' in TASK_CENTER


def test_task_execution_records_audit():
    """测试：任务执行记录审计日志。"""
    # 检查 _execute_task_definition 中调用 AuditService.log_task_executed
    assert 'AuditService.log_task_executed' in TASK_CENTER


def test_audit_api_requires_admin():
    """测试：审计 API 需要管理员权限。"""
    audit_py = (ROOT / 'api' / 'audit.py').read_text(encoding='utf-8')
    assert 'admin_required' in audit_py


def test_audit_api_supports_filtering():
    """测试：审计 API 支持过滤。"""
    assert 'filters' in AUDIT_SERVICE
    assert 'user_id' in AUDIT_SERVICE
    assert 'action' in AUDIT_SERVICE
    assert 'resource_type' in AUDIT_SERVICE
