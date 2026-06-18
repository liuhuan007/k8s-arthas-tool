#!/usr/bin/env python3
"""API 蓝图注册中心"""
from flask import Flask


def get_connection_by_id(conn_id: str):
    """根据连接 ID 获取底层连接对象。

    1. 先查内存 connections 池（正常路径）
    2. 如果内存中没有，尝试从数据库恢复（服务重启后内存清空的场景）
    """
    import logging
    log = logging.getLogger(__name__)

    from backend.app_context import connections, connections_lock
    with connections_lock:
        entry = connections.get(conn_id)
    if entry:
        return entry.get('conn')

    # 内存中没有，尝试从数据库恢复
    log.info("[get_connection_by_id] Connection %s not in memory, attempting recovery", conn_id)
    return _recover_connection_from_db(conn_id, log)


def _recover_connection_from_db(conn_id: str, log):
    """从数据库恢复连接到内存池。"""
    from models.db import db
    from backend.app_context import connections, connections_lock, make_runner

    row = db.fetch_one(
        'SELECT cluster_name, namespace, pod_name, container_name, status '
        'FROM connections WHERE id = ?',
        (conn_id,)
    )
    if not row:
        log.warning("[recovery] Connection %s not found in database", conn_id)
        return None

    status = row.get('status', '')
    if status not in ('ready', 'connected', 'recovered', 'pod_connected'):
        log.warning("[recovery] Connection %s has status=%s, cannot recover", conn_id, status)
        return None

    cluster_name = row.get('cluster_name', '')
    namespace = row.get('namespace', '')
    pod_name = row.get('pod_name', '')
    container_name = row.get('container_name', '')

    runner, err = make_runner(cluster_name)
    if err:
        log.warning("[recovery] Cannot create runner for %s: %s", conn_id, err)
        return None

    try:
        from backend import PodTarget, ArthasConnection
        target = PodTarget(
            cluster_name=cluster_name,
            namespace=namespace,
            pod_name=pod_name,
            container=container_name or '',
        )
        conn = ArthasConnection(runner, target)
        conn.connection_id = conn_id

        ok, msg = conn.connect()
        if ok:
            with connections_lock:
                connections[conn_id] = {"conn": conn, "user_id": None, "level": "arthas"}
            log.info("[recovery] Connection %s recovered from DB", conn_id)
            return conn
        else:
            log.warning("[recovery] Connection %s recovery failed: %s", conn_id, msg)
            return None
    except Exception as e:
        log.error("[recovery] Error recovering %s: %s", conn_id, e)
        return None


def register_blueprints(app: Flask):
    """注册所有 API 蓝图"""
    from api.auth import auth_bp
    from api.users import users_bp
    from api.clusters import clusters_bp
    from api.audit import audit_bp
    from api.mcp_proxy import mcp_bp
    from api.ai_chat import ai_bp
    from api.performance_diagnose import diag_bp
    from api.task_center import task_bp
    from api.hotfix import hotfix_bp
    from api.skills import skills_bp
    from api.diagnosis import diagnosis_bp
    from api.connection_detail import connection_detail_bp
    from api.profiler import profiler_bp
    from api.anomaly import anomaly_bp
    from api.agent import agent_bp
    from api.toolbox import toolbox_bp
    from api.knowledge import knowledge_bp
    from api.arthas_routes import arthas_bp
    from api.mcp_standard import mcp_std_bp
    from api.scheduler_routes import scheduler_bp
    from api.cli_api import cli_bp
    from api.agent_framework import agent_fw_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(clusters_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(mcp_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(diag_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(hotfix_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(diagnosis_bp)
    app.register_blueprint(connection_detail_bp)
    app.register_blueprint(profiler_bp)
    app.register_blueprint(anomaly_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(toolbox_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(arthas_bp)
    app.register_blueprint(scheduler_bp)
    app.register_blueprint(cli_bp)
    app.register_blueprint(mcp_std_bp)
    app.register_blueprint(agent_fw_bp)
