#!/usr/bin/env python3
"""Anomaly Detection API 路由

本模块提供异常检测相关的 API 路由：
- GET    /api/anomaly/events          查询异常事件（支持过滤和分页）
- GET    /api/anomaly/events/stats   获取异常事件统计
- GET    /api/anomaly/events/for-connection/<connection_id>  获取指定连接的异常事件
- DELETE /api/anomaly/events/<event_id>  删除异常事件
- GET    /api/anomaly/rules           获取告警规则
- POST   /api/anomaly/rules           创建告警规则
- PUT    /api/anomaly/rules/<rule_id>  更新告警规则
- DELETE /api/anomaly/rules/<rule_id>  删除告警规则

Author: Qi (team-lead)
Created: 2026-05-26
"""

import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from services.anomaly_detector import get_anomaly_detector

log = logging.getLogger(__name__)

# 创建 Blueprint
anomaly_bp = Blueprint('anomaly', __name__)


@anomaly_bp.route('/api/anomaly/events', methods=['GET'])
@login_required
def get_events():
    """查询异常事件（支持过滤和分页）"""
    try:
        detector = get_anomaly_detector()
        
        cluster = request.args.get('cluster', '')
        namespace = request.args.get('namespace', '')
        pod = request.args.get('pod', '')
        severity = request.args.get('severity', '')
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 50))
        
        result = detector.get_events(
            cluster=cluster,
            namespace=namespace,
            pod=pod,
            severity=severity,
            page=page,
            page_size=page_size,
        )
        
        return jsonify({
            "ok": True,
            **result,
        })
    except Exception as e:
        log.error("查询异常事件失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@anomaly_bp.route('/api/anomaly/events/stats', methods=['GET'])
@login_required
def get_events_stats():
    """获取异常事件统计"""
    try:
        detector = get_anomaly_detector()
        stats = detector.get_events_stats()
        
        return jsonify({
            "ok": True,
            **stats,
        })
    except Exception as e:
        log.error("获取异常统计失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@anomaly_bp.route('/api/anomaly/events/for-connection/<connection_id>', methods=['GET'])
@login_required
def get_events_for_connection(connection_id: str):
    """获取指定连接的异常事件（供 AI 分析使用）"""
    try:
        detector = get_anomaly_detector()
        
        # 解析 connection_id 获取 cluster/namespace/pod
        parts = connection_id.split('/')
        cluster = parts[0] if len(parts) > 0 else ''
        namespace = parts[1] if len(parts) > 1 else ''
        pod = parts[2] if len(parts) > 2 else ''
        
        # 获取最近 50 条异常事件
        result = detector.get_events(
            cluster=cluster,
            namespace=namespace,
            pod=pod,
            severity='',
            page=1,
            page_size=50,
        )
        
        # 格式化供 AI 使用
        events = result.get('events', [])
        formatted = []
        for evt in events:
            formatted.append({
                "time": evt.get('created_at', ''),
                "severity": evt.get('severity', ''),
                "rule_name": evt.get('rule_name', ''),
                "message": evt.get('message', ''),
                "metric_value": evt.get('metric_value', 0),
                "threshold": evt.get('threshold', 0),
            })
        
        return jsonify({
            "ok": True,
            "connection_id": connection_id,
            "event_count": len(formatted),
            "events": formatted,
        })
    except Exception as e:
        log.error("查询连接异常事件失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@anomaly_bp.route('/api/anomaly/events/<int:event_id>', methods=['DELETE'])
@login_required
def delete_event(event_id: int):
    """删除异常事件"""
    try:
        detector = get_anomaly_detector()
        success = detector.delete_event(event_id)
        
        if not success:
            return jsonify({"ok": False, "error": f"事件 {event_id} 不存在"}), 404
        
        return jsonify({"ok": True, "message": "事件已删除"})
    except Exception as e:
        log.error("删除异常事件失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 告警规则管理 ────────────────────────────────────────────────────────

@anomaly_bp.route('/api/anomaly/rules', methods=['GET'])
@login_required
def get_rules():
    """获取所有告警规则"""
    try:
        detector = get_anomaly_detector()
        rules = detector.get_all_rules()
        
        return jsonify({
            "ok": True,
            "rules": rules,
            "count": len(rules),
        })
    except Exception as e:
        log.error("查询告警规则失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@anomaly_bp.route('/api/anomaly/rules', methods=['POST'])
@login_required
def create_rule():
    """创建告警规则"""
    try:
        data = request.json or {}
        
        # 验证
        if not data.get('name'):
            return jsonify({"ok": False, "error": "规则名称不能为空"}), 400
        if not data.get('metric'):
            return jsonify({"ok": False, "error": "监控指标不能为空"}), 400
        
        detector = get_anomaly_detector()
        
        rule_id = detector.create_rule(data)
        rule = detector.get_rule_by_id(rule_id)  # 获取创建的规则详情
        
        return jsonify({
            "ok": True,
            "rule": rule,
        }), 201
    except Exception as e:
        log.error("创建告警规则失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@anomaly_bp.route('/api/anomaly/rules/<int:rule_id>', methods=['PUT'])
@login_required
def update_rule(rule_id: int):
    """更新告警规则"""
    try:
        data = request.json or {}
        detector = get_anomaly_detector()
        
        success = detector.update_rule(rule_id, data)
        
        if not success:
            return jsonify({"ok": False, "error": f"规则 {rule_id} 不存在"}), 404
        
        rule = detector.get_rule_by_id(rule_id)  # 获取更新后的规则详情
        return jsonify({
            "ok": True,
            "rule": rule,
        })
    except Exception as e:
        log.error("更新告警规则失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@anomaly_bp.route('/api/anomaly/rules/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_rule(rule_id: int):
    """删除告警规则"""
    try:
        detector = get_anomaly_detector()
        success = detector.delete_rule(rule_id)

        if not success:
            return jsonify({"ok": False, "error": f"规则 {rule_id} 不存在"}), 404

        return jsonify({"ok": True, "message": "规则已删除"})
    except Exception as e:
        log.error("删除告警规则失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 通知 ────────────────────────────────────────────────────────────────

@anomaly_bp.route('/api/anomaly/notifications', methods=['GET'])
@login_required
def list_notifications():
    """获取通知列表"""
    try:
        detector = get_anomaly_detector()
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        notifications = detector.get_notifications(
            user_id=current_user.id if current_user.is_authenticated else 0,
            unread_only=unread_only,
        )
        unread_count = detector.get_unread_count(
            user_id=current_user.id if current_user.is_authenticated else 0,
        )
        return jsonify({
            "ok": True,
            "notifications": notifications,
            "unread_count": unread_count,
        })
    except Exception as e:
        log.error("查询通知失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@anomaly_bp.route('/api/anomaly/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id: int):
    """标记通知为已读"""
    try:
        detector = get_anomaly_detector()
        success = detector.mark_notification_read(notif_id)
        if not success:
            return jsonify({"ok": False, "error": "通知不存在"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        log.error("标记通知已读失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@anomaly_bp.route('/api/anomaly/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """标记所有通知为已读"""
    try:
        from models.db import get_db
        db = get_db()
        db.update(
            "alert_notifications",
            {"is_read": 1},
            "user_id = ? AND is_read = 0",
            (current_user.id,),
        )
        return jsonify({"ok": True})
    except Exception as e:
        log.error("标记全部已读失败: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500
