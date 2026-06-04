#!/usr/bin/env python3
"""用户管理 API"""
import logging
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from functools import wraps

from services.user_service import UserService

log = logging.getLogger(__name__)


def admin_required(f):
    """Admin 权限装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function


users_bp = Blueprint('users', __name__, url_prefix='/api')


@users_bp.route('/users', methods=['GET'])
@login_required
@admin_required
def list_users():
    """获取所有用户列表（仅 admin）"""
    users = UserService.get_all()
    return jsonify({
        'users': [u.to_dict() for u in users]
    })


@users_bp.route('/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    """创建新用户（仅 admin）"""
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'user').strip()
    status = data.get('status', 'active').strip()
    
    user_id, error = UserService.create(
        operator_id=current_user.id,
        username=username,
        password=password,
        role=role,
        status=status
    )
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({'ok': True, 'id': user_id}), 201


@users_bp.route('/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def update_user(user_id: int):
    """更新用户（仅 admin）"""
    data = request.json or {}
    username = data.get('username', '').strip()
    role = data.get('role', '').strip()
    status = data.get('status', '').strip()
    
    changes, error = UserService.update(
        operator_id=current_user.id,
        user_id=user_id,
        username=username if username else None,
        role=role if role else None,
        status=status if status else None
    )
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({'ok': True, 'changes': changes})


@users_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id: int):
    """删除用户（仅 admin）"""
    error = UserService.delete(operator_id=current_user.id, user_id=user_id)
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({'ok': True})


@users_bp.route('/users/<int:user_id>/status', methods=['PUT'])
@login_required
@admin_required
def set_user_status(user_id: int):
    """设置用户状态（仅 admin）"""
    data = request.json or {}
    status = data.get('status', '').strip()
    
    error = UserService.set_status(operator_id=current_user.id, user_id=user_id, status=status)
    
    if error:
        return jsonify({'error': error}), 400
    
    return jsonify({'ok': True})


# 集群分配相关 API
from models.db import db


@users_bp.route('/user-clusters/<int:user_id>', methods=['GET'])
@login_required
def get_user_clusters(user_id: int):
    """获取用户集群分配"""
    # 检查权限：只能查看自己的，或者 admin 查看任意
    if not current_user.is_admin and current_user.id != user_id:
        return jsonify({'error': '需要管理员权限'}), 403
    
    rows = db.fetch_all(
        'SELECT id, cluster_id FROM user_clusters WHERE user_id = ?',
        (user_id,)
    )
    return jsonify({'clusters': [dict(r) for r in rows]})


@users_bp.route('/user-clusters', methods=['POST'])
@login_required
@admin_required
def assign_cluster():
    """分配集群（仅 admin）"""
    data = request.json or {}
    user_id = data.get('user_id')
    cluster_id = data.get('cluster_id')
    
    if not user_id or not cluster_id:
        return jsonify({'error': 'user_id 和 cluster_id 必填'}), 400
    
    # 检查是否已存在
    if db.exists('user_clusters', 'user_id = ? AND cluster_id = ?', (user_id, cluster_id)):
        return jsonify({'error': '该分配已存在'}), 400
    
    db.insert('user_clusters', {
        'user_id': user_id,
        'cluster_id': cluster_id
    })
    
    return jsonify({'ok': True}), 201


@users_bp.route('/user-clusters/<int:assignment_id>', methods=['DELETE'])
@login_required
@admin_required
def remove_cluster_assignment(assignment_id: int):
    """取消分配（仅 admin）"""
    db.delete('user_clusters', 'id = ?', (assignment_id,))
    return jsonify({'ok': True})


@users_bp.route('/user-clusters/by-user-cluster', methods=['DELETE'])
@login_required
@admin_required
def remove_cluster_by_user_cluster():
    """按 user_id 和 cluster_id 取消分配（仅 admin）"""
    user_id = request.args.get('user_id', type=int)
    cluster_id = request.args.get('cluster_id')
    
    if not user_id or not cluster_id:
        return jsonify({'error': 'user_id 和 cluster_id 必填'}), 400
    
    db.delete('user_clusters', 'user_id = ? AND cluster_id = ?', (user_id, cluster_id))
    return jsonify({'ok': True})


@users_bp.route('/user-namespaces/<int:user_id>', methods=['GET'])
@login_required
def get_user_namespaces(user_id: int):
    """获取用户 namespace 授权。"""
    if not current_user.is_admin and current_user.id != user_id:
        return jsonify({'error': '需要管理员权限'}), 403
    rows = db.fetch_all(
        'SELECT id, cluster_id, namespace FROM user_namespaces WHERE user_id = ? ORDER BY cluster_id, namespace',
        (user_id,),
    )
    return jsonify({'namespaces': [dict(r) for r in rows]})


@users_bp.route('/user-namespaces', methods=['POST'])
@login_required
@admin_required
def assign_namespace():
    """给用户授权指定 cluster/namespace（仅 admin）。"""
    data = request.json or {}
    user_id = data.get('user_id')
    cluster_id = (data.get('cluster_id') or '').strip()
    namespace = (data.get('namespace') or '').strip()
    if not user_id or not cluster_id or not namespace:
        return jsonify({'error': 'user_id、cluster_id 和 namespace 必填'}), 400
    if db.exists(
        'user_namespaces',
        'user_id = ? AND cluster_id = ? AND namespace = ?',
        (user_id, cluster_id, namespace),
    ):
        return jsonify({'error': '该 namespace 授权已存在'}), 400
    assignment_id = db.insert('user_namespaces', {
        'user_id': user_id,
        'cluster_id': cluster_id,
        'namespace': namespace,
    })
    try:
        from services.audit_service import AuditService
        AuditService._log_raw(
            current_user.id,
            'namespace_permission_granted',
            'user_namespace',
            f'{user_id}:{cluster_id}:{namespace}',
            f'授权用户 {user_id} 操作 {cluster_id}/{namespace}',
        )
    except Exception as e:
        log.warning("审计日志写入失败(namespace_permission_granted): %s", e)
    return jsonify({'ok': True, 'id': assignment_id}), 201


@users_bp.route('/user-namespaces/<int:assignment_id>', methods=['DELETE'])
@login_required
@admin_required
def remove_namespace(assignment_id: int):
    """删除 namespace 授权（仅 admin）。"""
    row = db.fetch_one('SELECT * FROM user_namespaces WHERE id = ?', (assignment_id,))
    db.delete('user_namespaces', 'id = ?', (assignment_id,))
    if row:
        try:
            from services.audit_service import AuditService
            AuditService._log_raw(
                current_user.id,
                'namespace_permission_revoked',
                'user_namespace',
                f"{row['user_id']}:{row['cluster_id']}:{row['namespace']}",
                f"取消用户 {row['user_id']} 对 {row['cluster_id']}/{row['namespace']} 的授权",
            )
        except Exception as e:
            log.warning("审计日志写入失败(namespace_permission_revoked): %s", e)
    return jsonify({'ok': True})


@users_bp.route('/user-namespaces/by-user-cluster-namespace', methods=['DELETE'])
@login_required
@admin_required
def remove_namespace_by_user_cluster_namespace():
    """按 user_id、cluster_id 和 namespace 删除授权（仅 admin）。"""
    user_id = request.args.get('user_id', type=int)
    cluster_id = (request.args.get('cluster_id') or '').strip()
    namespace = (request.args.get('namespace') or '').strip()
    if not user_id or not cluster_id or not namespace:
        return jsonify({'error': 'user_id、cluster_id 和 namespace 必填'}), 400
    db.delete(
        'user_namespaces',
        'user_id = ? AND cluster_id = ? AND namespace = ?',
        (user_id, cluster_id, namespace),
    )
    try:
        from services.audit_service import AuditService
        AuditService._log_raw(
            current_user.id,
            'namespace_permission_revoked',
            'user_namespace',
            f'{user_id}:{cluster_id}:{namespace}',
            f'取消用户 {user_id} 对 {cluster_id}/{namespace} 的授权',
        )
    except Exception as e:
        log.warning("审计日志写入失败(namespace_permission_revoked): %s", e)
    return jsonify({'ok': True})