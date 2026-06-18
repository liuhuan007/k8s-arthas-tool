#!/usr/bin/env python3
"""热更新 API 合同测试 — P1b-1"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOTFIX_SERVICE = (ROOT / 'services' / 'hotfix_service.py').read_text(encoding='utf-8')
HOTFIX_API = (ROOT / 'api' / 'hotfix.py').read_text(encoding='utf-8')


# ═══════════════════════════════════════════════════════════════════════════
# 测试：HotfixService 核心方法存在
# ═══════════════════════════════════════════════════════════════════════════

def test_hotfix_service_has_required_methods():
    """HotfixService 必须包含 jad/upload/compile/redefine 方法"""
    required_methods = [
        'execute_jad',
        'upload_file',
        'execute_mc',
        'execute_redefine',
        'list_artifacts',
        'generate_verification_report',
        'get_redefine_limitations'
    ]
    for method in required_methods:
        assert f'def {method}(' in HOTFIX_SERVICE, f"hotfix_service.py 缺少方法: {method}"


def test_hotfix_service_has_redefine_limitations():
    """HotfixService 必须包含 8 项 redefine 技术限制"""
    assert 'REDEFINE_LIMITATIONS' in HOTFIX_SERVICE
    limitation_ids = [
        'method_signature',
        'field_change',
        'parent_interface',
        'annotation_change',
        'spring_bean',
        'jdk_version',
        'custom_classloader',
        'static_init'
    ]
    for lid in limitation_ids:
        assert f"'{lid}'" in HOTFIX_SERVICE or f'"{lid}"' in HOTFIX_SERVICE, \
            f"hotfix_service.py 缺少 redefine 限制: {lid}"


def test_hotfix_service_calculates_sha256():
    """HotfixService 必须支持 SHA256 计算"""
    assert '_calculate_sha256' in HOTFIX_SERVICE
    assert 'hashlib.sha256' in HOTFIX_SERVICE


def test_hotfix_service_artifact_directory_structure():
    """HotfixService 必须使用标准产物目录结构"""
    assert 'data/hotfix' in HOTFIX_SERVICE
    assert 'connection_id' in HOTFIX_SERVICE
    assert 'timestamp' in HOTFIX_SERVICE


# ═══════════════════════════════════════════════════════════════════════════
# 测试：Hotfix API 端点存在
# ═══════════════════════════════════════════════════════════════════════════

def test_hotfix_api_has_required_routes():
    """热更新 API 必须包含所有必需端点"""
    required_routes = [
        "/jad",
        "/upload",
        "/compile",
        "/redefine",
        "/artifacts",
        "/limitations",
        "/verification"
    ]
    for route in required_routes:
        assert f"'{route}'" in HOTFIX_API or f'"{route}"' in HOTFIX_API, \
            f"api/hotfix.py 缺少路由: {route}"


def test_hotfix_api_requires_authentication():
    """所有热更新 API 必须要求登录"""
    assert '@login_required' in HOTFIX_API


def test_hotfix_api_redefine_requires_confirmation():
    """redefine 端点必须要求二次确认"""
    assert 'confirmed' in HOTFIX_API
    assert 'require_confirm' in HOTFIX_API or '二次确认' in HOTFIX_API


def test_hotfix_api_logs_audit_events():
    """所有热更新操作必须记录审计日志"""
    audit_actions = [
        'hotfix_jad',
        'hotfix_upload',
        'hotfix_compile',
        'hotfix_redefine',
        'hotfix_verification'
    ]
    for action in audit_actions:
        assert f"'{action}'" in HOTFIX_API or f'"{action}"' in HOTFIX_API, \
            f"api/hotfix.py 缺少审计动作: {action}"


def test_hotfix_api_validates_file_types():
    """upload 端点必须验证文件类型"""
    assert '.java' in HOTFIX_API
    assert '.class' in HOTFIX_API


def test_hotfix_api_checks_connection_ownership():
    """所有端点必须检查连接归属"""
    assert '_get_connection' in HOTFIX_API
    assert 'user_id' in HOTFIX_API or 'current_user' in HOTFIX_API


# ═══════════════════════════════════════════════════════════════════════════
# 测试：验证报告生成
# ═══════════════════════════════════════════════════════════════════════════

def test_verification_report_contains_required_sections():
    """验证报告必须包含关键章节"""
    required_sections = [
        '基本信息',
        'redefine 结果',
        '修改对比',
        '验证步骤',
        '回滚指引',
        'redefine 技术限制'
    ]
    for section in required_sections:
        assert section in HOTFIX_SERVICE, f"验证报告缺少章节: {section}"


def test_verification_report_saved_to_correct_path():
    """验证报告必须保存到标准路径"""
    assert 'verification-report.md' in HOTFIX_SERVICE


# ═══════════════════════════════════════════════════════════════════════════
# 测试：redefine 技术限制提示
# ═══════════════════════════════════════════════════════════════════════════

def test_redefine_limitations_count():
    """必须包含 8 项 redefine 技术限制"""
    # 计算限制项数量
    limitation_count = HOTFIX_SERVICE.count('"id":')
    assert limitation_count >= 8, f"redefine 技术限制数量不足: {limitation_count} < 8"


def test_redefine_limitations_have_complete_info():
    """每项限制必须包含 title/description/action"""
    for field in ['title', 'description', 'action']:
        assert f'"{field}"' in HOTFIX_SERVICE or f"'{field}'" in HOTFIX_SERVICE, \
            f"redefine 限制缺少字段: {field}"


if __name__ == '__main__':
    import pytest
    import sys
    sys.exit(pytest.main([__file__, '-v']))
