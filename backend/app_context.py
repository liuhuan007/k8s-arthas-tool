"""
Application shared context — connection pool, state manager, and helper functions.

This module centralizes the shared mutable state that was previously scattered
across server.py module-level globals.  Blueprints import from here instead of
reaching back into ``server``, breaking the circular-import cycle.

Usage::

    from backend.app_context import (
        connections, connections_lock,
        conn_health, conn_health_lock,
        state_manager, recovery_status,
        make_runner, load_clusters,
        check_conn_owner, get_conn,
        ensure_connection, save_arthas_command,
    )
"""
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ── 连接池 ─────────────────────────────────────────────────────────────────
# 格式: {conn_id: {"conn": ArthasConnection, "user_id": int, ...}}
connections: Dict[str, dict] = {}
connections_lock = threading.Lock()

# Phase 5: 连接健康状态缓存
# 格式: {conn_id: {"status": "healthy"|"unhealthy"|"unknown", "last_check_at": str, "latency_ms": float|None}}
conn_health: Dict[str, dict] = {}
conn_health_lock = threading.Lock()

# Phase 5: 连接恢复状态
recovery_status: Dict[str, dict] = {"recovered": [], "stale": [], "completed": False}

# ── State manager (延迟初始化) ──────────────────────────────────────────────
_state_manager = None  # type: ignore


def get_state_manager():
    """Return the singleton ConnectionStateManager, creating it on first call."""
    global _state_manager
    if _state_manager is None:
        from models.db import db
        from backend.core.connection_state import ConnectionStateManager
        _state_manager = ConnectionStateManager(db)
        _state_manager.schedule_ttl_cleanup(interval_seconds=1800)
        log.info("ConnectionStateManager initialized with TTL cleanup (30min interval)")
    return _state_manager


# ── Helper functions ────────────────────────────────────────────────────────

def load_clusters() -> List[Dict]:
    """加载集群配置（委托给 api/clusters.py 统一实现）"""
    from api.clusters import _load_clusters as _load
    return _load()


def make_runner(cluster_name: str) -> Tuple[Optional[object], Optional[str]]:
    """创建 KubectlExecutor，返回 (runner, error_message)。"""
    from flask import has_request_context
    from flask_login import current_user
    from models.db import db
    from backend.core.kubectl import KubectlExecutor

    clusters = load_clusters()
    cluster = next((c for c in clusters if c.get('name') == cluster_name), None)
    if not cluster:
        return None, "集群不存在"

    # 非 admin 检查集群访问权限（仅在请求上下文中检查，启动恢复时跳过）
    if has_request_context() and current_user.is_authenticated:
        if not current_user.is_admin:
            user_clusters = db.fetch_all(
                'SELECT cluster_id FROM user_clusters WHERE user_id = ?',
                (current_user.id,)
            )
            allowed = {r['cluster_id'] for r in user_clusters}
            if cluster.get('id') not in allowed:
                return None, "无权访问此集群"

    kubeconfig = cluster.get('kubeconfig', '')
    context = cluster.get('context', '')
    return KubectlExecutor(kubeconfig=kubeconfig, context=context), None


def check_conn_owner(conn_id: str) -> bool:
    """检查当前用户是否是连接的拥有者（admin 拥有所有权限）"""
    from flask_login import current_user
    if current_user.is_admin:
        return True
    entry = connections.get(conn_id)
    return entry and entry.get('user_id') == current_user.id


def get_conn(conn_id: str):
    """获取连接对象(带权限检查)"""
    from flask_login import current_user
    entry = connections.get(conn_id)
    if not entry:
        return None

    # 权限检查: 非 admin 只能访问自己的连接
    if not current_user.is_admin and entry.get('user_id') != current_user.id:
        return None

    return entry.get('conn')


def ensure_connection(conn_id: str, d: dict):
    """确保连接存在，若内存中不存在则自动重建（线程安全）。

    Returns:
        (conn, error_message)  — 成功时 error_message 为 None
    """
    from flask_login import current_user
    from models.db import db
    from backend import PodTarget, ArthasConnection
    from services.authorization_service import AuthorizationService

    with connections_lock:
        if conn_id and conn_id in connections:
            if not check_conn_owner(conn_id):
                return None, "无权操作此连接"
            return connections[conn_id].get('conn'), None

    # 从请求参数中提取连接信息并自动重建
    cluster_name = d.get('cluster_name', '')
    namespace = d.get('namespace', '')
    pod = d.get('pod_name', '')
    container = d.get('container', '')

    # 从 conn_id 解析连接信息（比请求参数更可靠）
    if conn_id:
        parts = conn_id.split('/')
        if len(parts) >= 3 and not cluster_name:
            cluster_name = parts[0]
        if len(parts) >= 2 and not namespace:
            namespace = parts[1]
        if len(parts) >= 3:
            pod_part = parts[2].split('@')[0]
            if not pod:
                pod = pod_part

    if not namespace:
        namespace = 'default'

    if not conn_id:
        conn_id = f"{cluster_name}/{namespace}/{pod}"
        if not current_user.is_admin:
            conn_id = f"{cluster_name}/{namespace}/{pod}@u{current_user.id}"

    if not cluster_name or not pod:
        return None, "连接不存在且缺少连接参数，请重新连接"

    # 检查用户是否有权访问该集群
    if not current_user.is_admin:
        user_clusters = db.fetch_all(
            'SELECT cluster_id FROM user_clusters WHERE user_id = ?',
            (current_user.id,)
        )
        allowed_cluster_ids = {r['cluster_id'] for r in user_clusters}
        clusters = load_clusters()
        target_cluster = next((c for c in clusters if c.get('name') == cluster_name), None)
        if not target_cluster or target_cluster.get('id') not in allowed_cluster_ids:
            return None, "无权访问此集群"

    # 尝试自动重建连接
    runner, err = make_runner(cluster_name)
    if err:
        return None, f"连接已丢失，自动重连失败: {err}"

    target = PodTarget(cluster_name=cluster_name, namespace=namespace, pod_name=pod, container=container)
    sm = get_state_manager()
    conn = ArthasConnection(runner, target, state_manager=sm)
    conn.connection_id = conn_id

    log.info("[ensure_connection] 开始建立连接, conn_id=%s", conn_id)

    # 先建立 Pod 连接
    try:
        ok, msg = conn.pod_conn.connect()
        log.info("[ensure_connection] Pod 连接结果: ok=%s, msg=%s", ok, msg)
    except Exception as e:
        log.error("[ensure_connection] Pod 连接异常: %s", e, exc_info=True)
        return None, f"连接已丢失，自动重连失败: {str(e)}"

    if not ok:
        err_str = msg.get("message", str(msg)) if isinstance(msg, dict) else msg
        return None, f"连接已丢失，自动重连失败: {err_str}"

    # 同步 Pod 连接状态到 ArthasConnection
    conn._pod_connected = True
    conn._healthy = True
    conn._runtime_info = conn.pod_conn._runtime_info
    conn._pod_phase = conn.pod_conn._pod_phase

    # 再建立 Arthas 连接
    log.info("[ensure_connection] 开始建立 Arthas 连接...")
    ok2, msg2 = conn.connect_arthas(timeout=30)
    log.info("[ensure_connection] Arthas 连接结果: ok=%s, msg=%s, msg_type=%s", ok2, msg2, type(msg2).__name__)

    if not ok2:
        err_str = msg2.get("message", str(msg2)) if isinstance(msg2, dict) else msg2
        return None, f"连接已丢失，自动重连失败: {err_str}"

    # Arthas 连接成功，更新数据库中的元数据
    with connections_lock:
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if db.exists('connections', 'id = ?', (conn_id,)):
            db.update('connections', {
                'level': 'arthas',
                'local_port': conn.local_port,
                'java_pid': conn.java_pid,
                'arthas_version': conn.arthas_version,
                'status': 'ready',
                'last_ping_at': now_ts,
                'last_active_at': now_ts,
                'user_id': current_user.id,
                'updated_at': now_ts,
            }, 'id = ?', (conn_id,))
        else:
            db.insert('connections', {
                'id': conn_id,
                'cluster_name': cluster_name,
                'namespace': namespace,
                'pod_name': pod,
                'container_name': '',
                'level': 'arthas',
                'local_port': conn.local_port,
                'java_pid': conn.java_pid,
                'arthas_version': conn.arthas_version,
                'status': 'ready',
                'last_ping_at': now_ts,
                'last_active_at': now_ts,
                'user_id': current_user.id,
                'updated_at': now_ts,
            })

        if conn_id not in connections:
            connections[conn_id] = {"conn": conn, "user_id": current_user.id}

    log.info("Auto-reconnected: %s", conn_id)
    return conn, None


def save_arthas_command(conn_id: str, command: str, output: str = None, error: str = None):
    """保存 Arthas 命令历史"""
    from flask_login import current_user
    from models.db import db

    user_id = current_user.id if current_user.is_authenticated else None
    db.insert('arthas_command_logs', {
        'connection_id': conn_id,
        'user_id': user_id,
        'command': command,
        'output': output,
        'error': error,
    })
