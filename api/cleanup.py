#!/usr/bin/env python3
"""
清理服务 API - 连接自动清理与磁盘保护

端点:
- POST /api/cleanup/run - 手动触发完整清理
- GET  /api/cleanup/stats - 获取磁盘和目录统计
- GET  /api/cleanup/config - 获取清理配置
- POST /api/cleanup/config - 更新清理配置
"""
import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from services.cleanup_service import CleanupService

log = logging.getLogger(__name__)

cleanup_bp = Blueprint('cleanup', __name__)

# 全局清理服务实例
_cleanup_service = CleanupService()


@cleanup_bp.route('/api/cleanup/run', methods=['POST'])
@login_required
def run_cleanup():
    """
    手动触发完整清理
    
    请求体(可选):
    {
        "user_only": true  // 仅清理当前用户的连接
    }
    
    返回:
    {
        "ok": true,
        "report": { ... }
    }
    """
    d = request.json or {}
    user_only = d.get('user_only', False)

    try:
        user_id = current_user.id if user_only else None
        report = _cleanup_service.run_full_cleanup(user_id)

        # 审计日志
        from services.audit_service import AuditService
        AuditService._log_raw(
            current_user.id,
            'cleanup_manual',
            'cleanup',
            '',
            f'手动触发清理: user_only={user_only}, 清理 {report["total_cleaned_items"]} 项'
        )

        return jsonify({
            'ok': True,
            'report': report
        })

    except Exception as e:
        log.error("Cleanup failed: %s", e, exc_info=True)
        return jsonify({'error': f'清理失败: {str(e)}'}), 500


@cleanup_bp.route('/api/cleanup/stats', methods=['GET'])
@login_required
def get_cleanup_stats():
    """
    获取清理统计信息
    
    返回:
    - 磁盘使用率
    - profiler_output 目录统计
    - 连接数量统计
    """
    try:
        # 磁盘使用率
        disk_usage = _cleanup_service.check_disk_usage()

        # 目录统计
        dir_stats = _cleanup_service.get_directory_stats()

        # 连接数量统计
        total_conns = db_fetch_one(
            'SELECT COUNT(*) as cnt FROM connections'
        )
        ready_conns = db_fetch_one(
            "SELECT COUNT(*) as cnt FROM connections WHERE status = 'ready'"
        )
        expired_conns = db_fetch_one(
            "SELECT COUNT(*) as cnt FROM connections WHERE status != 'ready' AND "
            "(last_ping_at IS NULL OR last_ping_at < datetime('now', '-24 hours'))"
        )

        return jsonify({
            'ok': True,
            'disk_usage': disk_usage,
            'directory_stats': dir_stats,
            'connections': {
                'total': total_conns['cnt'] if total_conns else 0,
                'ready': ready_conns['cnt'] if ready_conns else 0,
                'expired': expired_conns['cnt'] if expired_conns else 0
            }
        })

    except Exception as e:
        log.error("Failed to get cleanup stats: %s", e, exc_info=True)
        return jsonify({'error': f'获取统计失败: {str(e)}'}), 500


@cleanup_bp.route('/api/cleanup/config', methods=['GET'])
@login_required
def get_cleanup_config():
    """
    获取清理配置
    
    返回当前清理策略配置
    """
    return jsonify({
        'ok': True,
        'config': _cleanup_service.config
    })


@cleanup_bp.route('/api/cleanup/config', methods=['POST'])
@login_required
def update_cleanup_config():
    """
    更新清理配置(仅管理员)
    
    请求体:
    {
        "connection_ttl_hours": 24,
        "artifact_retention_days": 7,
        "log_retention_days": 30,
        "disk_warning_threshold": 0.80,
        "max_heapdump_size_gb": 2
    }
    """
    # 检查管理员权限
    if current_user.role != 'admin':
        return jsonify({'error': '仅管理员可修改清理配置'}), 403

    d = request.json or {}

    # 验证配置值
    allowed_keys = {
        'connection_ttl_hours': (int, 1, 168),      # 1小时 ~ 7天
        'artifact_retention_days': (int, 1, 365),    # 1天 ~ 1年
        'log_retention_days': (int, 1, 365),         # 1天 ~ 1年
        'disk_warning_threshold': (float, 0.5, 0.95), # 50% ~ 95%
        'max_heapdump_size_gb': (int, 1, 10)         # 1GB ~ 10GB
    }

    updates = {}
    for key, value in d.items():
        if key not in allowed_keys:
            return jsonify({'error': f'未知配置项: {key}'}), 400

        type_check, min_val, max_val = allowed_keys[key]
        try:
            value = type_check(value)
            if not (min_val <= value <= max_val):
                return jsonify({
                    'error': f'{key} 超出范围 [{min_val}, {max_val}]'
                }), 400
            updates[key] = value
        except (ValueError, TypeError):
            return jsonify({'error': f'{key} 类型错误,需要 {type_check.__name__}'}), 400

    # 更新配置
    _cleanup_service.config.update(updates)

    # 审计日志
    from services.audit_service import AuditService
    AuditService._log_raw(
        current_user.id,
        'cleanup_config_updated',
        'cleanup',
        '',
        f'更新清理配置: {updates}'
    )

    return jsonify({
        'ok': True,
        'config': _cleanup_service.config
    })


def db_fetch_one(query, params=()):
    """安全查询数据库"""
    from models.db import db
    return db.fetch_one(query, params)
