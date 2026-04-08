#!/usr/bin/env python3
"""
MCP 代理蓝图 — 方案 C：后端代理层

架构：
  AI 客户端 (Claude Desktop / Cherry Studio / Cline)
       │
       ▼
  Flask 后端 /mcp/{token}/... (认证 + 用户隔离)
       │
       ▼
  Pod 内 Arthas MCP Server (8563/mcp)

核心功能：
  1. Token 管理 — 每个用户可生成 MCP 接入 Token
  2. MCP 请求代理 — 将 AI 客户端的 MCP 请求转发到对应 Pod 的 Arthas MCP
  3. 连接管理 — Token 绑定到具体的 Arthas 连接
"""
import json
import logging
import secrets
import time
import urllib.request
from datetime import datetime
from flask import Blueprint, request, jsonify, Response, current_app
from flask_login import login_required, current_user

from models.db import db
from backend import ArthasConnection, PodTarget

log = logging.getLogger(__name__)

mcp_bp = Blueprint('mcp_proxy', __name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Token 管理 API（需要 Flask-Login 认证）
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_bp.route('/api/mcp/tokens', methods=['GET'])
@login_required
def list_mcp_tokens():
    """列出当前用户的所有 MCP Token"""
    tokens = db.fetch_all(
        'SELECT id, name, connection_id, created_at, last_used_at, is_active FROM mcp_tokens WHERE user_id = ? ORDER BY created_at DESC',
        (current_user.id,)
    )
    # 脱敏：不返回 token 原文
    return jsonify({"tokens": tokens or []})


@mcp_bp.route('/api/mcp/tokens', methods=['POST'])
@login_required
def create_mcp_token():
    """创建 MCP Token，绑定到指定连接"""
    d = request.json or {}
    name = d.get('name', '').strip() or f"MCP-{datetime.now().strftime('%m%d%H%M')}"
    connection_id = d.get('connection_id', '').strip()

    if not connection_id:
        return jsonify({"error": "请指定要绑定的连接"}), 400

    # 验证连接存在且属于当前用户
    # 1. 先检查内存中的活跃连接
    conn_entry = _get_connection_entry(connection_id)
    conn_alive = False

    if conn_entry:
        conn = conn_entry.get('conn')
        conn_alive = conn.is_alive() if conn else False
    else:
        # 2. 内存中没有，检查数据库中的历史连接
        db_conn = db.fetch_one(
            'SELECT id FROM connections WHERE id = ? AND user_id = ?',
            (connection_id, current_user.id)
        )
        if not db_conn:
            return jsonify({"error": "连接不存在或无权访问"}), 404

    # 生成 Token
    token = f"mcp_{secrets.token_hex(24)}"

    db.insert('mcp_tokens', {
        'token': token,
        'name': name,
        'user_id': current_user.id,
        'connection_id': connection_id,
        'is_active': 1,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

    # 记录审计
    from services.audit_service import AuditService
    AuditService._log_raw(current_user.id, 'mcp_token_created', 'mcp_token',
                          name, f'创建 MCP Token: {name}，绑定连接: {connection_id}')

    # 返回 Token 原文（仅此一次）
    result = {
        "ok": True,
        "token": token,
        "name": name,
        "connection_id": connection_id,
    }
    # 如果连接不活跃，返回警告
    if not conn_alive:
        result["warning"] = "连接当前未激活，请先在 Web 界面连接 Pod 后再使用 MCP"

    return jsonify(result)


@mcp_bp.route('/api/mcp/tokens/<int:token_id>', methods=['DELETE'])
@login_required
def delete_mcp_token(token_id):
    """删除 MCP Token"""
    entry = db.fetch_one('SELECT * FROM mcp_tokens WHERE id = ? AND user_id = ?',
                         (token_id, current_user.id))
    if not entry:
        return jsonify({"error": "Token 不存在"}), 404

    db.delete('mcp_tokens', 'id = ? AND user_id = ?', (token_id, current_user.id))

    from services.audit_service import AuditService
    AuditService._log_raw(current_user.id, 'mcp_token_deleted', 'mcp_token',
                          str(token_id), f'删除 MCP Token: {entry["name"]}')

    return jsonify({"ok": True})


@mcp_bp.route('/api/mcp/tokens/<int:token_id>/toggle', methods=['POST'])
@login_required
def toggle_mcp_token(token_id):
    """启用/禁用 MCP Token"""
    entry = db.fetch_one('SELECT * FROM mcp_tokens WHERE id = ? AND user_id = ?',
                         (token_id, current_user.id))
    if not entry:
        return jsonify({"error": "Token 不存在"}), 404

    new_status = 0 if entry['is_active'] else 1
    db.update('mcp_tokens', {'is_active': new_status}, 'id = ?', (token_id,))

    return jsonify({"ok": True, "is_active": bool(new_status)})


@mcp_bp.route('/api/mcp/tokens/<int:token_id>/bind', methods=['POST'])
@login_required
def bind_mcp_token(token_id):
    """Bind MCP Token to a specific Arthas connection (pod) by updating the connection_id."""
    data = request.json or {}
    new_conn = data.get('connection_id', '').strip()
    if not new_conn:
        return jsonify({"error": "请提供要绑定的连接ID"}), 400

    entry = db.fetch_one('SELECT * FROM mcp_tokens WHERE id = ? AND user_id = ?', (token_id, current_user.id))
    if not entry:
        return jsonify({"error": "Token 不存在"}), 404

    # 验证连接是否存在并属于当前用户
    db_conn = db.fetch_one('SELECT id FROM connections WHERE id = ? AND user_id = ?', (new_conn, current_user.id))
    if not db_conn:
        return jsonify({"error": "绑定的连接不存在或无权访问"}), 404

    db.update('mcp_tokens', {'connection_id': new_conn}, 'id = ?', (token_id,))

    # 审计日志
    from services.audit_service import AuditService
    AuditService._log_raw(current_user.id, 'mcp_token_bound', 'mcp_token', str(token_id), f'绑定 MCP Token: {entry["name"]} -> 连接: {new_conn}')

    return jsonify({"ok": True, "connection_id": new_conn})

@mcp_bp.route('/api/mcp/config/<int:token_id>', methods=['GET'])
@login_required
def get_mcp_client_config(token_id):
    """生成 AI 客户端的 MCP 配置 JSON"""
    entry = db.fetch_one('SELECT * FROM mcp_tokens WHERE id = ? AND user_id = ?',
                         (token_id, current_user.id))
    if not entry:
        return jsonify({"error": "Token 不存在"}), 404

    # 构建 MCP 端点 URL
    base_url = request.host_url.rstrip('/')
    mcp_url = f"{base_url}/mcp/{entry['token']}"
    mcp_sse_url = f"{base_url}/mcp/{entry['token']}/sse"

    configs = {
        "cherry_studio_cline": {
            "mcpServers": {
                "arthas-mcp": {
                    "type": "streamableHttp",
                    "url": mcp_url,
                }
            }
        },
        "cherry_studio_sse": {
            "mcpServers": {
                "arthas-mcp": {
                    "type": "sse",
                    "url": mcp_sse_url,
                }
            }
        },
        "claude_desktop": {
            "mcpServers": {
                "arthas-mcp": {
                    "type": "streamableHttp",
                    "url": mcp_url,
                }
            }
        },
        "cursor": {
            "mcpServers": {
                "arthas-mcp": {
                    "type": "streamableHttp",
                    "url": mcp_url,
                }
            }
        },
    }

    return jsonify({
        "ok": True,
        "mcp_url": mcp_url,
        "configs": configs,
        "connection_id": entry['connection_id'],
        "token_name": entry['name'],
        "is_active": bool(entry.get('is_active')),
        "hint": "将以上配置复制到 AI 客户端（Claude Desktop / Cherry Studio / Cursor 等）即可使用。确保绑定的 Arthas 连接在 Web 界面中处于活跃状态。",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# MCP 代理端点（Token 认证，不走 Flask-Login）
# ═══════════════════════════════════════════════════════════════════════════════

# 支持多种 MCP 传输协议路径
@mcp_bp.route('/mcp/<token>/', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
@mcp_bp.route('/mcp/<token>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
@mcp_bp.route('/mcp/<token>/sse', methods=['GET', 'OPTIONS'])
@mcp_bp.route('/mcp/<token>/message', methods=['POST', 'OPTIONS'])
@mcp_bp.route('/mcp/<token>/messages', methods=['POST', 'OPTIONS'])
def mcp_proxy(token):
    """MCP 请求代理 — 转发到 Pod 内 Arthas MCP Server

    认证方式：URL 中的 token 参数
    请求转发：直接透传到 Arthas MCP 端点
    """
    # CORS preflight
    if request.method == 'OPTIONS':
        resp = Response('', status=204)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, Mcp-Session-Id'
        resp.headers['Access-Control-Expose-Headers'] = 'Mcp-Session-Id'
        return resp

    # 验证 Token
    entry = db.fetch_one('SELECT * FROM mcp_tokens WHERE token = ? AND is_active = 1', (token,))
    if not entry:
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32001, "message": "Invalid or inactive MCP token"}, "id": None}), 401

    connection_id = entry['connection_id']

    # 获取 Arthas 连接
    conn = _get_connection_obj(connection_id)
    if not conn:
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32002, "message": "Arthas connection not found. The connection may have been removed. Please re-create the MCP Token and bind it to an active connection."}, "id": None}), 503

    if not conn.client:
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32002, "message": "Arthas HTTP client not available. Please reconnect the Pod in the web UI first, then try again."}, "id": None}), 503

    local_port = conn.local_port
    if not local_port:
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32002, "message": "Arthas port-forward is not active. Please reconnect the Pod in the web UI to establish a port-forward, then try again."}, "id": None}), 503

    # 更新 Token 最后使用时间
    try:
        db.update('mcp_tokens', {
            'last_used_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, 'id = ?', (entry['id'],))
    except Exception:
        pass

    # 转发请求到 Pod 内 Arthas MCP 端点
    try:
        # 根据请求路径决定转发的目标 URL
        path = request.path
        if path.endswith('/sse'):
            arthas_mcp_url = f"http://127.0.0.1:{local_port}/mcp/sse"
        elif path.endswith('/message') or path.endswith('/messages'):
            arthas_mcp_url = f"http://127.0.0.1:{local_port}/mcp/message"
        else:
            arthas_mcp_url = f"http://127.0.0.1:{local_port}/mcp"

        if request.method == 'GET':
            # MCP SSE 初始化 / 服务发现
            return _proxy_get(arthas_mcp_url)
        elif request.method == 'POST':
            # MCP JSON-RPC 请求
            return _proxy_post(arthas_mcp_url, request)
        elif request.method == 'PUT':
            # MCP 更新请求（部分客户端使用）
            return _proxy_post(arthas_mcp_url, request)
        elif request.method == 'DELETE':
            # MCP 会话关闭
            return _proxy_delete(arthas_mcp_url, request)
    except urllib.error.URLError as e:
        log.error("MCP proxy URLError for %s: %s", connection_id, e)
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32003, "message": f"Cannot reach Arthas MCP: {str(e)}"}, "id": None}), 502
    except Exception as e:
        log.error("MCP proxy error for %s: %s", connection_id, e, exc_info=True)
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32603, "message": f"Internal proxy error: {str(e)}"}, "id": None}), 500


# ═══════════════════════════════════════════════════════════════════════════════
# 连接可用性检查
# ═══════════════════════════════════════════════════════════════════════════════

@mcp_bp.route('/api/mcp/connections', methods=['GET'])
@login_required
def list_available_connections():
    """列出当前用户可用的 Arthas 连接（用于 Token 绑定选择）

    优先从内存读取活跃连接，同时从数据库读取历史连接记录
    """
    from server import _connections, _connections_lock

    # 从数据库读取用户的连接记录
    db_connections = db.fetch_all(
        'SELECT id, cluster_name, namespace, pod_name, updated_at FROM connections WHERE user_id = ? ORDER BY updated_at DESC',
        (current_user.id,)
    ) or []

    # 从内存读取活跃连接状态
    alive_map = {}
    mcp_map = {}
    with _connections_lock:
        for conn_id, entry in _connections.items():
            if entry.get('user_id') == current_user.id:
                conn = entry.get('conn')
                alive_map[conn_id] = {
                    'alive': conn.is_alive() if conn else False,
                    'local_port': conn.local_port if conn else 0,
                }
                mcp_map[conn_id] = entry.get('mcp_available', False)

    # 合并结果
    available = []
    seen_ids = set()

    # 1. 添加数据库中的连接记录
    for row in db_connections:
        conn_id = row['id']
        seen_ids.add(conn_id)
        alive_info = alive_map.get(conn_id, {'alive': False, 'local_port': 0})
        available.append({
            "id": conn_id,
            "alive": alive_info['alive'],
            "local_port": alive_info['local_port'],
            "cluster": row.get('cluster_name', ''),
            "namespace": row.get('namespace', ''),
            "pod": row.get('pod_name', ''),
            "status": 'connected' if alive_info['alive'] else 'disconnected',
            "mcp_available": mcp_map.get(conn_id, False),
        })

    # 2. 添加内存中有但数据库中没有的连接（边缘情况）
    for conn_id, alive_info in alive_map.items():
        if conn_id not in seen_ids:
            available.append({
                "id": conn_id,
                "alive": alive_info['alive'],
                "local_port": alive_info['local_port'],
                "cluster": '',
                "namespace": '',
                "pod": '',
                "status": 'connected' if alive_info['alive'] else 'disconnected',
                "mcp_available": mcp_map.get(conn_id, False),
            })

    return jsonify({"connections": available})


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _get_connection_entry(connection_id: str):
    """从内存中获取连接条目，验证归属"""
    from server import _connections, _connections_lock
    with _connections_lock:
        entry = _connections.get(connection_id)
        if entry and entry.get('user_id') == current_user.id:
            return entry
    return None


def _get_connection_obj(connection_id: str):
    """从内存中获取 ArthasConnection 对象"""
    from server import _connections, _connections_lock
    with _connections_lock:
        entry = _connections.get(connection_id)
        if entry:
            return entry.get('conn')
    return None


def _proxy_get(target_url: str):
    """代理 GET 请求（MCP 服务发现 / SSE 流）"""
    req = urllib.request.Request(target_url, method='GET')
    req.add_header('Accept', 'text/event-stream, application/json')

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        content_type = resp.headers.get('Content-Type', 'application/json')

        if 'text/event-stream' in content_type:
            # SSE 流式转发
            def generate():
                try:
                    while True:
                        chunk = resp.read(4096)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    resp.close()

            flask_resp = Response(generate(), status=200, content_type=content_type)
            flask_resp.headers['Access-Control-Allow-Origin'] = '*'
            flask_resp.headers['Cache-Control'] = 'no-cache'
            return flask_resp
        else:
            body = resp.read()
            resp.close()
            flask_resp = Response(body, status=200, content_type=content_type)
            flask_resp.headers['Access-Control-Allow-Origin'] = '*'
            return flask_resp
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b''
        flask_resp = Response(body, status=e.code,
                              content_type=e.headers.get('Content-Type', 'application/json'))
        flask_resp.headers['Access-Control-Allow-Origin'] = '*'
        return flask_resp


def _proxy_post(target_url: str, original_request):
    """代理 POST 请求（MCP JSON-RPC），支持 SSE 流式响应"""
    body = original_request.get_data()

    req = urllib.request.Request(target_url, data=body, method='POST')
    req.add_header('Content-Type', original_request.content_type or 'application/json')
    req.add_header('Accept', 'text/event-stream, application/json')

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        content_type = resp.headers.get('Content-Type', 'application/json')

        if 'text/event-stream' in content_type:
            # SSE 流式转发
            def generate():
                try:
                    while True:
                        chunk = resp.read(4096)
                        if not chunk:
                            break
                        yield chunk
                finally:
                    resp.close()

            flask_resp = Response(generate(), status=200, content_type=content_type)
            flask_resp.headers['Access-Control-Allow-Origin'] = '*'
            flask_resp.headers['Cache-Control'] = 'no-cache'
            return flask_resp
        else:
            response_body = resp.read()
            resp.close()
            flask_resp = Response(response_body, status=200, content_type=content_type)
            flask_resp.headers['Access-Control-Allow-Origin'] = '*'
            return flask_resp
    except urllib.error.HTTPError as e:
        error_body = e.read() if e.fp else b''
        flask_resp = Response(error_body, status=e.code,
                              content_type=e.headers.get('Content-Type', 'application/json'))
        flask_resp.headers['Access-Control-Allow-Origin'] = '*'
        return flask_resp


def _proxy_delete(target_url: str, original_request):
    """代理 DELETE 请求（MCP 会话关闭）"""
    req = urllib.request.Request(target_url, method='DELETE')
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            flask_resp = Response(body, status=resp.status, content_type='application/json')
            flask_resp.headers['Access-Control-Allow-Origin'] = '*'
            return flask_resp
    except urllib.error.HTTPError as e:
        error_body = e.read() if e.fp else b''
        flask_resp = Response(error_body, status=e.code,
                              content_type=e.headers.get('Content-Type', 'application/json'))
        flask_resp.headers['Access-Control-Allow-Origin'] = '*'
        return flask_resp


# ═══════════════════════════════════════════════════════════════════════════════
# 数据库表初始化
# ═══════════════════════════════════════════════════════════════════════════════

def init_mcp_tables():
    """初始化 MCP 相关数据库表"""
    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mcp_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                connection_id TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (connection_id) REFERENCES connections(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mcp_tokens_token ON mcp_tokens(token)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mcp_tokens_user ON mcp_tokens(user_id)')
