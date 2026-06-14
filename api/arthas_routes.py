"""
Arthas connection management routes - extracted from server.py.

Endpoints:
  POST /api/arthas/connect          创建 Arthas 连接
  POST /api/arthas/disconnect       断开 Arthas 连接
  POST /api/arthas/exec             执行 Arthas 命令
  POST /api/arthas/status           获取连接状态
  POST /api/arthas/session/create   创建会话
  POST /api/arthas/session/exec     会话执行命令
  POST /api/arthas/session/pull     拉取会话输出
  POST /api/arthas/session/interrupt 中断会话
  POST /api/arthas/session/close    关闭会话
  GET  /api/arthas/commands         命令历史
  POST /api/check                   检测 Java 进程
"""
import json
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models.db import db
from backend import PodTarget, ArthasConnection
from backend.app_context import (
    connections, connections_lock,
    get_state_manager, make_runner,
    check_conn_owner, get_conn, ensure_connection,
    save_arthas_command,
)
from services.authorization_service import AuthorizationService
from services.audit_service import AuditService

log = logging.getLogger(__name__)

arthas_bp = Blueprint('arthas', __name__)


# ── Java 进程检测 ──────────────────────────────────────────────────────────

@arthas_bp.route('/api/check', methods=['POST'])
@login_required
def check_pod():
    """检测 Pod 内 Java 进程，返回详细列表供用户选择"""
    d = request.json or {}
    runner, err = make_runner(d.get('cluster_name', ''))
    if err:
        return jsonify({"error": err, "java_pid": None}), 400

    ns = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')

    rc, out, _ = runner.exec_pod(ns, pod, container,
        "jps -l 2>/dev/null || ps -ef 2>/dev/null | grep java | grep -v grep", timeout=10)

    java_processes = []
    arthas_keywords = ['arthas', 'arthas-boot', 'as-boot', 'arthas.jar', 'jps', 'sun.tools.jps']

    for line in out.strip().splitlines():
        line_lower = line.lower()
        if any(kw in line_lower for kw in arthas_keywords):
            continue
        parts = line.strip().split(None, 1)
        if parts and parts[0].isdigit():
            pid = parts[0]
            desc = parts[1] if len(parts) > 1 else "java"
            java_processes.append({"pid": pid, "description": desc.strip()})

    default_pid = java_processes[0]["pid"] if java_processes else None

    return jsonify({
        "cluster_name": d.get('cluster_name'),
        "namespace": ns,
        "pod_name": pod,
        "container": container,
        "java_pid": default_pid,
        "java_pids": [p["pid"] for p in java_processes],
        "java_processes": java_processes,
        "has_multiple_jvms": len(java_processes) > 1,
    })


# ── Arthas 连接管理 ────────────────────────────────────────────────────────

@arthas_bp.route('/api/arthas/connect', methods=['POST'])
@login_required
def arthas_connect():
    """创建 Arthas 连接，支持指定 Java PID"""
    d = request.json or {}
    cluster_name = d.get('cluster_name', '')
    namespace = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    java_pid = d.get('java_pid')
    ttl_hours = d.get('ttl_hours', 0)

    runner, err = make_runner(cluster_name)
    if err:
        return jsonify({"error": err}), 400
    auth_err, auth_code = AuthorizationService.require_namespace_access(current_user, cluster_name, namespace)
    if auth_err:
        return jsonify(auth_err), auth_code

    conn_id = f"{cluster_name}/{namespace}/{pod}"
    if not current_user.is_admin:
        conn_id = f"{cluster_name}/{namespace}/{pod}@u{current_user.id}"

    target = PodTarget(cluster_name=cluster_name, namespace=namespace, pod_name=pod, container=container)
    sm = get_state_manager()
    conn = ArthasConnection(runner, target, state_manager=sm)
    conn.connection_id = conn_id

    if java_pid:
        conn.agent_mgr._pid = int(java_pid)

    try:
        ok, msg = conn.connect()
        if not ok:
            if isinstance(msg, dict):
                return jsonify({"ok": False, **msg}), 400
            return jsonify({"ok": False, "error": msg}), 400

        mcp_available = conn.agent_mgr._check_mcp_available(conn.target.arthas_http_port)

        with connections_lock:
            connections[conn_id] = {"conn": conn, "user_id": current_user.id, "mcp_available": mcp_available}

        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if db.exists('connections', 'id = ?', (conn_id,)):
            db.update('connections', {
                'level': 'arthas', 'local_port': conn.local_port,
                'java_pid': conn.java_pid, 'arthas_version': conn.arthas_version,
                'status': 'ready', 'last_ping_at': now_ts, 'last_active_at': now_ts,
                'ttl_hours': ttl_hours, 'user_id': current_user.id, 'updated_at': now_ts,
            }, 'id = ?', (conn_id,))
        else:
            db.insert('connections', {
                'id': conn_id, 'cluster_name': cluster_name, 'namespace': namespace,
                'pod_name': pod, 'container_name': '', 'level': 'arthas',
                'local_port': conn.local_port, 'java_pid': conn.java_pid,
                'arthas_version': conn.arthas_version, 'status': 'ready',
                'last_ping_at': now_ts, 'last_active_at': now_ts,
                'ttl_hours': ttl_hours, 'user_id': current_user.id, 'updated_at': now_ts,
            })

        AuditService.log_connection_created(current_user.id, conn_id, pod, namespace)

        return jsonify({
            "ok": True,
            "conn_id": conn_id,
            "connection_id": conn_id,
            "local_port": conn.local_port,
            "java_pid": conn.java_pid,
            "http_url": f"http://localhost:{conn.local_port}",
            "arthas_version": conn.arthas_version,
            "arthas_address": conn.arthas_address,
            "mcp_available": mcp_available,
            "message": msg,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@arthas_bp.route('/api/arthas/disconnect', methods=['POST'])
@login_required
def arthas_disconnect():
    """断开 Arthas 连接"""
    d = request.json or {}
    conn_id = d.get('conn_id', '')

    if conn_id in connections:
        if not check_conn_owner(conn_id):
            return jsonify({"state": "FAILED", "message": "无权操作此连接"}), 403
        with connections_lock:
            entry = connections.pop(conn_id, None)
        conn = entry.get('conn') if entry else None
        if conn:
            conn.disconnect()

        db.delete('connections', 'id = ?', (conn_id,))

        parts = conn_id.split('/')
        if len(parts) >= 3:
            pod = parts[2]
            namespace = parts[1]
            AuditService.log_connection_deleted(current_user.id, conn_id, pod, namespace)

        return jsonify({"ok": True})

    return jsonify({"error": "连接不存在"}), 404


@arthas_bp.route('/api/arthas/exec', methods=['POST'])
@login_required
def arthas_exec():
    """执行 Arthas 命令"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    command = d.get('command', '').strip()

    conn, err = ensure_connection(conn_id, d)
    if err:
        return jsonify({"state": "FAILED", "message": err}), 404

    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        result = ArthasCommandExecutor.execute(conn, command, skip_audit=False, skip_history=False)

        save_arthas_command(conn_id, command,
            json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result), '')

        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            db.update('connections', {'last_active_at': now_ts}, 'id = ?', (conn_id,))
        except Exception as e:
            log.warning("更新连接 last_active_at 失败: %s", e)

        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@arthas_bp.route('/api/arthas/status', methods=['POST'])
@login_required
def arthas_status():
    """获取 Arthas 连接状态"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''

    conn = get_conn(conn_id)
    if not conn:
        return jsonify({"connected": False})

    if not check_conn_owner(conn_id):
        return jsonify({"connected": False, "message": "无权访问此连接"})

    return jsonify({
        "connected": conn.is_alive() if hasattr(conn, 'is_alive') else True,
        "local_port": conn.local_port if hasattr(conn, 'local_port') else 0,
        "java_pid": conn.java_pid if hasattr(conn, 'java_pid') else None,
    })


@arthas_bp.route('/api/arthas/commands', methods=['GET'])
@login_required
def get_arthas_commands():
    """获取 Arthas 命令历史"""
    conn_id = request.args.get('connection_id', '')
    limit = int(request.args.get('limit', 100))

    if not conn_id:
        return jsonify({"error": "connection_id 必填"}), 400

    if current_user.is_admin:
        commands = db.fetch_all(
            'SELECT command, output, error, timestamp FROM arthas_command_logs WHERE connection_id = ? ORDER BY timestamp DESC LIMIT ?',
            (conn_id, limit))
    else:
        commands = db.fetch_all(
            'SELECT command, output, error, timestamp FROM arthas_command_logs WHERE connection_id = ? AND user_id = ? ORDER BY timestamp DESC LIMIT ?',
            (conn_id, current_user.id, limit))
    return jsonify({"success": True, "commands": [dict(c) for c in (commands or [])]})


# ── Arthas Session ─────────────────────────────────────────────────────────

@arthas_bp.route('/api/arthas/session/create', methods=['POST'])
@login_required
def arthas_session_create():
    """创建 Arthas 会话"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''

    conn, err = ensure_connection(conn_id, d)
    if err:
        return jsonify({"state": "FAILED", "message": err}), 400

    if not conn or not hasattr(conn, 'http_client') or not conn.http_client:
        return jsonify({"state": "FAILED", "message": "未连接"}), 400

    try:
        result = conn.http_client.init_session() if hasattr(conn.http_client, 'init_session') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@arthas_bp.route('/api/arthas/session/exec', methods=['POST'])
@login_required
def arthas_session_exec():
    """在会话中执行命令"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    session_id = d.get('session_id', '')
    command = d.get('command', '')

    conn, err = ensure_connection(conn_id, d)
    if err or not conn or not hasattr(conn, 'http_client'):
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400

    try:
        result = conn.http_client.exec_async(session_id, command) if hasattr(conn.http_client, 'exec_async') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@arthas_bp.route('/api/arthas/session/pull', methods=['POST'])
@login_required
def arthas_session_pull():
    """拉取会话输出"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    session_id = d.get('session_id', '')
    consumer_id = d.get('consumer_id', '')

    conn, err = ensure_connection(conn_id, d)
    if err or not conn or not hasattr(conn, 'http_client'):
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400

    try:
        result = conn.http_client.pull_results(session_id, consumer_id) if hasattr(conn.http_client, 'pull_results') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@arthas_bp.route('/api/arthas/session/interrupt', methods=['POST'])
@login_required
def arthas_session_interrupt():
    """中断会话命令"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    session_id = d.get('session_id', '')

    conn, err = ensure_connection(conn_id, d)
    if err or not conn or not hasattr(conn, 'http_client'):
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400

    try:
        result = conn.http_client.interrupt_job(session_id) if hasattr(conn.http_client, 'interrupt_job') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500


@arthas_bp.route('/api/arthas/session/close', methods=['POST'])
@login_required
def arthas_session_close():
    """关闭会话"""
    d = request.json or {}
    conn_id = d.get('conn_id') or d.get('connection_id') or ''
    session_id = d.get('session_id', '')

    conn, err = ensure_connection(conn_id, d)
    if err or not conn or not hasattr(conn, 'http_client'):
        return jsonify({"state": "FAILED", "message": err or "未连接"}), 400

    try:
        result = conn.http_client.close_session(session_id) if hasattr(conn.http_client, 'close_session') else {"state": "FAILED", "message": "不支持会话模式"}
        return jsonify(result)
    except Exception as e:
        return jsonify({"state": "FAILED", "message": str(e)}), 500
