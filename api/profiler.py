#!/usr/bin/env python3
"""Profiler Blueprint - 性能采样 API 路由

本模块提供 Profiler 相关的 API 路由：
- POST   /api/profiler/tasks          创建任务
- POST   /api/profiler/tasks/<id>/start  启动任务
- POST   /api/profiler/tasks/<id>/stop   停止任务
- GET    /api/profiler/tasks/<id>        查询任务状态
- GET    /api/profiler/tasks           列出任务列表

Author: Kou (software-engineer)
Created: 2025-05-25
"""

import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from services.profiler_service import get_profiler_service

log = logging.getLogger(__name__)

# 创建 Blueprint
profiler_bp = Blueprint('profiler', __name__)


def _can_access_connection(connection_id: str) -> bool:
    if current_user.is_admin:
        return True

    from backend.app_context import get_connection_entry
    entry = get_connection_entry(connection_id)
    if entry:
        return entry.get('user_id') == current_user.id

    from models.db import db
    row = db.fetch_one(
        'SELECT user_id FROM connections WHERE id = ?',
        (connection_id,)
    )
    return bool(row and row.get('user_id') == current_user.id)


@profiler_bp.route('/api/profiler/tasks', methods=['POST'])
@login_required
def create_task():
    """创建 Profiler 任务"""
    d = request.json or {}
    
    connection_id = d.get('connection_id', '')
    task_type = d.get('type', 'cpu')  # cpu/jfr/threaddump/heapdump
    event = d.get('event', task_type)
    duration = int(d.get('duration', 60))
    fmt = d.get('format', 'html')  # html/jfr/txt/bin
    
    if not connection_id:
        return jsonify({"success": False, "error": "connection_id 必填"}), 400
    if not _can_access_connection(connection_id):
        return jsonify({"success": False, "error": "连接不存在或无权访问"}), 404

    if task_type == 'heapdump' and not current_user.is_admin:
        return jsonify({"success": False, "error": "Heap Dump 仅管理员可执行"}), 403
    
    # 验证任务类型
    valid_types = ('cpu', 'jfr', 'threaddump', 'heapdump')
    if task_type not in valid_types:
        return jsonify({
            "success": False, 
            "error": f"无效的任务类型: {task_type}，支持: {valid_types}"
        }), 400
    
    try:
        service = get_profiler_service()
        user_id = current_user.id if current_user.is_authenticated else None
        task_id = service.create_task(
            connection_id=connection_id,
            task_type=task_type,
            event=event,
            duration=duration,
            fmt=fmt,
            user_id=user_id
        )
        
        return jsonify({
            "success": True,
            "task_id": task_id,
            "message": "任务已创建"
        })
    except Exception as e:
        log.error("创建 Profiler 任务失败: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@profiler_bp.route('/api/profiler/tasks/<task_id>/start', methods=['POST'])
@login_required
def start_task(task_id: str):
    """启动 Profiler 任务"""
    try:
        d = request.json or {}
        service = get_profiler_service()
        result = service.start_task(
            task_id,
            user_id=current_user.id,
            is_admin=current_user.is_admin,
            approval_token=d.get('approval_token')
        )
        return jsonify(result)
    except Exception as e:
        log.error("启动 Profiler 任务失败: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@profiler_bp.route('/api/profiler/tasks/<task_id>/stop', methods=['POST'])
@login_required
def stop_task(task_id: str):
    """停止 Profiler 任务"""
    try:
        service = get_profiler_service()
        result = service.stop_task(
            task_id,
            user_id=current_user.id,
            is_admin=current_user.is_admin
        )
        return jsonify(result)
    except Exception as e:
        log.error("停止 Profiler 任务失败: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@profiler_bp.route('/api/profiler/tasks/<task_id>', methods=['GET'])
@login_required
def get_task_status(task_id: str):
    """查询任务状态"""
    try:
        service = get_profiler_service()
        result = service.get_task_status(
            task_id,
            user_id=current_user.id,
            is_admin=current_user.is_admin
        )
        return jsonify(result)
    except Exception as e:
        log.error("查询 Profiler 任务状态失败: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@profiler_bp.route('/api/profiler/tasks', methods=['GET'])
@login_required
def list_tasks():
    """列出任务列表"""
    connection_id = request.args.get('connection_id', '')
    status = request.args.get('status', '')
    
    try:
        service = get_profiler_service()
        user_id = current_user.id if current_user.is_authenticated else None
        
        # 如果不传 connection_id，根据权限返回
        tasks = service.list_tasks(
            connection_id=connection_id or None,
            user_id=user_id,
            is_admin=current_user.is_admin
        )
        
        # 如果指定了状态，过滤
        if status:
            tasks = [t for t in tasks if t.get('status') == status]
        
        return jsonify({
            "success": True,
            "tasks": tasks,
            "count": len(tasks)
        })
    except Exception as e:
        log.error("列出 Profiler 任务失败: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
