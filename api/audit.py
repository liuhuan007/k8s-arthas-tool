#!/usr/bin/env python3
"""审计日志 API"""
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from functools import wraps

from services.audit_service import AuditService


def admin_required(f):
    """Admin 权限装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function


audit_bp = Blueprint('audit', __name__, url_prefix='/api')


@audit_bp.route('/audit-logs', methods=['GET'])
@login_required
@admin_required
def list_audit_logs():
    """获取审计日志列表（仅 admin）"""
    # 获取查询参数
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '').strip()
    resource_type = request.args.get('resource_type', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    
    # 构建过滤条件
    filters = {}
    if user_id:
        filters['user_id'] = user_id
    if action:
        filters['action'] = action
    if resource_type:
        filters['resource_type'] = resource_type
    if start_date:
        filters['start_date'] = start_date
    if end_date:
        filters['end_date'] = end_date
    
    # 查询数据
    logs = AuditService.query(filters=filters, limit=limit, offset=offset)
    total = AuditService.count(filters=filters)
    
    return jsonify({
        'logs': logs,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@audit_bp.route('/audit-logs/actions', methods=['GET'])
@login_required
@admin_required
def list_actions():
    """获取所有可用的操作类型"""
    actions = AuditService.get_actions()
    return jsonify({'actions': actions})


@audit_bp.route('/audit-logs/resource-types', methods=['GET'])
@login_required
@admin_required
def list_resource_types():
    """获取所有可用的资源类型"""
    types = AuditService.get_resource_types()
    return jsonify({'resource_types': types})