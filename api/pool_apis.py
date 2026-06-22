"""
连接池 API - /api/pool/*

提供连接池的 REST API：
  POST   /api/pool/connect        - 添加连接到池
  POST   /api/pool/{id}/focus     - 切换焦点（零延迟）
  DELETE /api/pool/{id}           - 移除连接
  GET    /api/pool                - 列出所有连接
  GET    /api/pool/{id}/status    - 获取指定连接状态
  POST   /api/pool/{id}/heartbeat - 手动心跳检查
  GET    /api/pool/{id}/workspace - 获取工作区状态
  PUT    /api/pool/{id}/workspace - 更新工作区状态
"""
from __future__ import annotations

import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

log = logging.getLogger(__name__)

pool_bp = Blueprint('pool', __name__)

# 全局连接池实例（由 server.py 注入）
_pool = None
_db = None
_make_runner = None
_state_manager = None


def init_pool_api(pool, db, make_runner, state_manager):
    """初始化连接池 API
    
    Args:
        pool: ConnectionPool 实例
        db: Database 实例
        make_runner: 创建 KubectlRunner 的函数
        state_manager: ConnectionStateManager 实例
    """
    global _pool, _db, _make_runner, _state_manager
    _pool = pool
    _db = db
    _make_runner = make_runner
    _state_manager = state_manager


def _check_conn_owner(conn_id: str) -> bool:
    """检查当前用户是否是连接的拥有者"""
    if current_user.is_admin:
        return True
    pool_conn = _pool.get(conn_id)
    return pool_conn and pool_conn.user_id == current_user.id


# ── 连接池操作 ──────────────────────────────────────────────────────────────

@pool_bp.route('/connect', methods=['POST'])
@login_required
def pool_connect():
    """添加连接到池
    
    请求体:
        cluster_name: 集群名称
        namespace: 命名空间
        pod_name: Pod 名称
        container: 容器名称（可选）
        java_pid: Java PID（可选）
        ttl_hours: 连接有效期（可选）
    """
    from backend import PodTarget, ArthasConnection
    from services.authorization_service import AuthorizationService
    
    d = request.json or {}
    cluster_name = d.get('cluster_name', '')
    namespace = d.get('namespace', 'default')
    pod = d.get('pod_name', '')
    container = d.get('container', '')
    java_pid = d.get('java_pid')
    ttl_hours = d.get('ttl_hours', 0)
    
    if not cluster_name or not pod:
        return jsonify({"error": "缺少必要参数: cluster_name, pod_name"}), 400
    
    # 权限检查
    auth_err, auth_code = AuthorizationService.require_namespace_access(
        current_user, cluster_name, namespace
    )
    if auth_err:
        return jsonify(auth_err), auth_code
    
    # 生成连接 ID
    conn_id = f"{cluster_name}/{namespace}/{pod}"
    if not current_user.is_admin:
        conn_id = f"{cluster_name}/{namespace}/{pod}@u{current_user.id}"
    
    # 检查是否已在池中
    existing = _pool.get(conn_id)
    if existing:
        # 已存在，直接切换焦点
        _pool.set_focus(conn_id)
        return jsonify({
            "ok": True,
            "conn_id": conn_id,
            "message": "连接已存在，已切换焦点",
            "existing": True,
        })
    
    # 创建连接
    runner, err = _make_runner(cluster_name)
    if err:
        return jsonify({"error": err}), 400
    
    target = PodTarget(
        cluster_name=cluster_name,
        namespace=namespace,
        pod_name=pod,
        container=container,
    )
    conn = ArthasConnection(runner, target, state_manager=_state_manager)
    conn.connection_id = conn_id
    conn._managed_by_pool = True  # 进入池管理，状态同步由 ConnectionPool.update_state() 统一处理
    
    # 设置 Java PID
    if java_pid:
        conn.agent_mgr._pid = int(java_pid)
    
    # 建立连接
    ok, msg = conn.connect()
    if not ok:
        if isinstance(msg, dict):
            return jsonify({"ok": False, **msg}), 400
        return jsonify({"ok": False, "error": msg}), 400
    
    # 检测 MCP 端点
    mcp_available = conn.agent_mgr._check_mcp_available(conn.target.arthas_http_port)
    
    # 添加到连接池
    _pool.add(conn_id, conn, user_id=current_user.id, mcp_available=mcp_available)
    _pool.set_focus(conn_id)
    
    # 持久化到数据库
    from datetime import datetime
    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if _db.exists('connections', 'id = ?', (conn_id,)):
        _db.update('connections', {
            'level': 'arthas',
            'local_port': conn.local_port,
            'java_pid': conn.java_pid,
            'arthas_version': conn.arthas_version,
            'status': 'ready',
            'last_ping_at': now_ts,
            'last_active_at': now_ts,
            'ttl_hours': ttl_hours,
            'user_id': current_user.id,
            'updated_at': now_ts,
        }, 'id = ?', (conn_id,))
    else:
        _db.insert('connections', {
            'id': conn_id,
            'cluster_name': cluster_name,
            'namespace': namespace,
            'pod_name': pod,
            'container_name': container,
            'level': 'arthas',
            'local_port': conn.local_port,
            'java_pid': conn.java_pid,
            'arthas_version': conn.arthas_version,
            'status': 'ready',
            'last_ping_at': now_ts,
            'last_active_at': now_ts,
            'ttl_hours': ttl_hours,
            'user_id': current_user.id,
            'updated_at': now_ts,
        })
    
    # 审计日志
    from services.audit_service import AuditService
    AuditService.log_connection_created(current_user.id, conn_id, pod, namespace)
    
    return jsonify({
        "ok": True,
        "conn_id": conn_id,
        "local_port": conn.local_port,
        "java_pid": conn.java_pid,
        "http_url": f"http://localhost:{conn.local_port}",
        "arthas_version": conn.arthas_version,
        "arthas_address": conn.arthas_address,
        "mcp_available": mcp_available,
        "message": msg,
    })


@pool_bp.route('/<path:conn_id>/focus', methods=['POST'])
@login_required
def pool_set_focus(conn_id):
    """切换焦点（零延迟）
    
    这是连接池的核心优势：切换焦点不触发任何网络操作，
    只是改变当前活跃连接的指针。
    """
    if not _check_conn_owner(conn_id):
        return jsonify({"error": "无权操作此连接"}), 403
    
    ok = _pool.set_focus(conn_id)
    if not ok:
        return jsonify({"error": "连接不存在"}), 404
    
    return jsonify({
        "ok": True,
        "conn_id": conn_id,
        "message": "焦点已切换",
    })


@pool_bp.route('/<path:conn_id>', methods=['DELETE'])
@login_required
def pool_remove(conn_id):
    """移除连接"""
    if not _check_conn_owner(conn_id):
        return jsonify({"error": "无权操作此连接"}), 403
    
    ok = _pool.remove(conn_id)
    if not ok:
        return jsonify({"error": "连接不存在"}), 404
    
    # 从数据库删除
    _db.delete('connections', 'id = ?', (conn_id,))
    
    # 审计日志
    parts = conn_id.split('/')
    if len(parts) >= 3:
        pod = parts[2].split('@')[0]
        namespace = parts[1]
        from services.audit_service import AuditService
        AuditService.log_connection_deleted(current_user.id, conn_id, pod, namespace)
    
    return jsonify({"ok": True})


@pool_bp.route('', methods=['GET'])
@login_required
def pool_list():
    """列出所有连接"""
    connections = _pool.list_all()
    
    # 过滤：非 admin 只能看到自己的连接
    if not current_user.is_admin:
        connections = [
            c for c in connections 
            if c.get('user_id') == current_user.id
        ]
    
    return jsonify({
        "ok": True,
        "connections": connections,
        "focus_id": _pool.get_focused_id(),
        "total": len(connections),
    })


@pool_bp.route('/<path:conn_id>/status', methods=['GET'])
@login_required
def pool_status(conn_id):
    """获取指定连接状态"""
    pool_conn = _pool.get(conn_id)
    if not pool_conn:
        return jsonify({"error": "连接不存在"}), 404
    
    if not _check_conn_owner(conn_id):
        return jsonify({"error": "无权访问此连接"}), 403
    
    info = pool_conn.to_dict()
    info['is_focused'] = (conn_id == _pool.get_focused_id())
    
    return jsonify({
        "ok": True,
        **info,
    })


@pool_bp.route('/<path:conn_id>/heartbeat', methods=['POST'])
@login_required
def pool_heartbeat(conn_id):
    """手动心跳检查"""
    pool_conn = _pool.get(conn_id)
    if not pool_conn:
        return jsonify({"error": "连接不存在"}), 404
    
    if not _check_conn_owner(conn_id):
        return jsonify({"error": "无权操作此连接"}), 403
    
    alive = pool_conn.conn.is_alive()
    
    return jsonify({
        "ok": True,
        "alive": alive,
        "state": pool_conn.state.value,
    })


@pool_bp.route('/<path:conn_id>/workspace', methods=['GET'])
@login_required
def pool_get_workspace(conn_id):
    """获取工作区状态"""
    workspace = _pool.get_workspace(conn_id)
    if not workspace:
        return jsonify({"error": "连接不存在"}), 404
    
    if not _check_conn_owner(conn_id):
        return jsonify({"error": "无权访问此连接"}), 403
    
    return jsonify({
        "ok": True,
        "active_tab": workspace.active_tab.value,
        "sub_tab": workspace.sub_tab,
        "scroll_positions": workspace.scroll_positions,
    })


@pool_bp.route('/<path:conn_id>/workspace', methods=['PUT'])
@login_required
def pool_update_workspace(conn_id):
    """更新工作区状态"""
    workspace = _pool.get_workspace(conn_id)
    if not workspace:
        return jsonify({"error": "连接不存在"}), 404
    
    if not _check_conn_owner(conn_id):
        return jsonify({"error": "无权操作此连接"}), 403
    
    d = request.json or {}
    
    from backend.core.connection_pool import WorkspaceTab
    
    if 'active_tab' in d:
        try:
            workspace.active_tab = WorkspaceTab(d['active_tab'])
        except ValueError:
            return jsonify({"error": f"无效的 tab: {d['active_tab']}"}), 400
    
    if 'sub_tab' in d:
        workspace.sub_tab = d['sub_tab']
    
    if 'scroll_positions' in d:
        workspace.scroll_positions = d['scroll_positions']
    
    return jsonify({"ok": True})


@pool_bp.route('/focus', methods=['GET'])
@login_required
def pool_get_focus():
    """获取当前焦点连接"""
    focus_id = _pool.get_focused_id()
    if not focus_id:
        return jsonify({
            "ok": True,
            "focus_id": None,
        })
    
    pool_conn = _pool.get(focus_id)
    if not pool_conn:
        return jsonify({
            "ok": True,
            "focus_id": None,
        })
    
    return jsonify({
        "ok": True,
        "focus_id": focus_id,
        "state": pool_conn.state.value,
        "local_port": pool_conn.conn.local_port,
        "java_pid": pool_conn.conn.java_pid,
        "arthas_version": pool_conn.conn.arthas_version,
    })
