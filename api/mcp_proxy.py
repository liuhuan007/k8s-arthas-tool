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
from backend.core.arthas_executor import ArthasCommandExecutor

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
    conn_entry = _get_connection_entry(connection_id)
    if not conn_entry:
        return jsonify({"error": "连接不存在或无权访问"}), 404

    # DB-only 连接：允许创建 token，但提示连接未活跃
    if conn_entry.get('db_only'):
        conn_alive = False
    else:
        conn = conn_entry.get('conn')
        try:
            conn_alive = conn.is_alive() if conn else False
        except Exception:
            conn_alive = False

    if not conn_alive:
        # DB-only 或连接已断开：仍允许创建 token，标记为待激活
        pass

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
def list_availableconnections():
    """列出当前用户可绑定 MCP Token 的活跃 Arthas 连接。

    MCP 代理依赖 Arthas HTTP/MCP port-forward，因此这里优先返回当前内存中
    属于当前用户、仍存活且具备本地端口的 Arthas 连接；
    内存为空时回退到数据库（兼容重启后连接未恢复的场景）。
    """
    from backend.app_context import connections, connections_lock

    available = []
    with connections_lock:
        for conn_id, entry in connections.items():
            if entry.get('user_id') != current_user.id:
                continue

            conn = entry.get('conn')
            if not conn:
                continue

            try:
                alive = conn.is_alive()
            except Exception:
                alive = False

            local_port = getattr(conn, 'local_port', None)
            if not alive or not local_port:
                continue

            target = getattr(conn, 'target', None)
            available.append({
                "id": conn_id,
                "alive": True,
                "pod_exists": True,
                "local_port": local_port,
                "cluster": getattr(target, 'cluster_name', '') if target else '',
                "cluster_name": getattr(target, 'cluster_name', '') if target else '',
                "namespace": getattr(target, 'namespace', '') if target else '',
                "pod": getattr(target, 'pod_name', '') if target else '',
                "pod_name": getattr(target, 'pod_name', '') if target else '',
                "status": "connected",
                "level": "arthas",
                "java_pid": getattr(conn, 'java_pid', None),
                "arthas_version": getattr(conn, 'arthas_version', None),
                "arthas_address": getattr(conn, 'arthas_address', None),
                "mcp_available": entry.get('mcp_available', False),
            })

    # 内存为空时回退到数据库
    if not available:
        try:
            from models.db import db
            if current_user.is_admin:
                rows = db.fetch_all(
                    "SELECT id, cluster_name, namespace, pod_name, local_port, "
                    "java_pid, arthas_version, user_id FROM connections "
                    "WHERE level = 'arthas' AND status = 'ready' AND local_port IS NOT NULL"
                )
            else:
                rows = db.fetch_all(
                    "SELECT id, cluster_name, namespace, pod_name, local_port, "
                    "java_pid, arthas_version, user_id FROM connections "
                    "WHERE level = 'arthas' AND status = 'ready' AND local_port IS NOT NULL "
                    "AND user_id = ?",
                    (current_user.id,)
                )
            for row in (rows or []):
                available.append({
                    "id": row['id'],
                    "alive": False,
                    "pod_exists": True,
                    "local_port": row.get('local_port'),
                    "cluster": row.get('cluster_name', ''),
                    "cluster_name": row.get('cluster_name', ''),
                    "namespace": row.get('namespace', ''),
                    "pod": row.get('pod_name', ''),
                    "pod_name": row.get('pod_name', ''),
                    "status": "db_only",
                    "level": "arthas",
                    "java_pid": row.get('java_pid'),
                    "arthas_version": row.get('arthas_version'),
                    "arthas_address": None,
                    "mcp_available": False,
                })
        except Exception:
            pass

    return jsonify({"connections": available})


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _get_connection_entry(connection_id: str):
    """从内存中获取连接条目，验证归属；内存无则回退到数据库"""
    from backend.app_context import connections, connections_lock
    with connections_lock:
        entry = connections.get(connection_id)
        if entry and entry.get('user_id') == current_user.id:
            return entry

    # 内存无，回退数据库
    try:
        from models.db import db
        if current_user.is_admin:
            row = db.fetch_one(
                "SELECT id, cluster_name, namespace, pod_name, local_port, user_id "
                "FROM connections WHERE id = ? AND level = 'arthas'",
                (connection_id,)
            )
        else:
            row = db.fetch_one(
                "SELECT id, cluster_name, namespace, pod_name, local_port, user_id "
                "FROM connections WHERE id = ? AND level = 'arthas' AND user_id = ?",
                (connection_id, current_user.id)
            )
        if row:
            return {
                "conn": None,
                "user_id": row['user_id'],
                "db_only": True,
                "cluster": row.get('cluster_name', ''),
                "namespace": row.get('namespace', ''),
                "pod": row.get('pod_name', ''),
                "local_port": row.get('local_port'),
            }
    except Exception:
        pass
    return None


def _get_connection_obj(connection_id: str):
    """从内存中获取 ArthasConnection 对象"""
    from backend.app_context import connections, connections_lock
    with connections_lock:
        entry = connections.get(connection_id)
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


# ═══════════════════════════════════════════════════════════════════════════════
# 性能诊断 MCP Tools 定义（本地处理，不转发到 Arthas MCP Server）
# ═══════════════════════════════════════════════════════════════════════════════

# 性能诊断工具定义（MCP Tool Schema）
PERF_MCP_TOOLS = [
    {
        "name": "arthas_trace_method",
        "description": "快速追踪方法调用链耗时。返回归一化耗时数据，适合定位慢方法根因。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "class_pattern": {"type": "string", "description": "类名模式，如 com.example.service.*"},
                "method_pattern": {"type": "string", "description": "方法名，支持 * 通配"},
                "skip_jdk": {"type": "boolean", "default": True, "description": "跳过 JDK 自身方法"},
                "max_depth": {"type": "integer", "default": 3},
                "sample_count": {"type": "integer", "default": 5}
            },
            "required": ["class_pattern", "method_pattern"]
        }
    },
    {
        "name": "arthas_get_dashboard",
        "description": "获取当前 JVM 实时指标快照（内存/GC/线程/cpu），返回归一化 JSON。",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "arthas_analyze_threads",
        "description": "线程快照 + 阻塞分析。返回所有线程状态、BLOCKED 线程列表和可能的死锁信息。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer", "default": 10},
                "check_deadlock": {"type": "boolean", "default": True}
            }
        }
    },
    {
        "name": "arthas_diagnose_performance",
        "description": "一键性能诊断核心入口。自动组合 trace + dashboard + thread 采样 → 规则预筛 → 结构化报告。直接返回根因、影响范围、优化建议。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["method_slow", "oom", "thread_block", "general"], "default": "general"},
                "class_pattern": {"type": "string"},
                "method_pattern": {"type": "string"}
            }
        }
    },
]


def _handle_perf_mcp_tool(token_entry: dict, tool_name: str, arguments: dict) -> dict:
    """在 Python 层本地处理性能诊断工具调用"""
    connection_id = token_entry['connection_id']

    # 获取连接
    conn = _get_connection_obj(connection_id)
    if not conn or not conn.is_alive():
        return {
            "content": [{"type": "text", "text": f"错误: Arthas 连接不可用，请先在 Web 界面连接目标 Pod"}]
        }

    try:
        from api.performance_diagnose import _run_diagnosis
        from backend.core.rule_engine import RuleEngine, extract_metrics_from_diagnosis
    except ImportError:
        pass

    try:
        # 分发到对应的诊断函数
        if tool_name == "arthas_trace_method":
            result = _exec_trace_method(conn, arguments)
        elif tool_name == "arthas_get_dashboard":
            result = _exec_dashboard(conn)
        elif tool_name == "arthas_analyze_threads":
            result = _exec_thread_analysis(conn, arguments.get('top_n', 10), arguments.get('check_deadlock', True))
        elif tool_name == "arthas_diagnose_performance":
            result = _run_diagnosis(
                conn,
                arguments.get('target', 'general'),
                arguments.get('class_pattern', ''),
                arguments.get('method_pattern', '')
            )
        else:
            result = {"error": f"未知工具: {tool_name}"}

        import json
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Perf MCP tool error: %s", e, exc_info=True)
        return {
            "content": [{"type": "text", "text": f"工具执行失败: {str(e)}"}]
        }


def _exec_trace_method(conn, args: dict) -> dict:
    """执行 trace 命令"""
    import re
    class_pattern = args.get('class_pattern', '')
    method_pattern = args.get('method_pattern', '*')
    skip_jdk = args.get('skip_jdk', True)
    sample_count = args.get('sample_count', 5)

    if not class_pattern:
        return {"error": "class_pattern 不能为空"}

    skip_flag = '--skipJDKMethod true' if skip_jdk else ''
    cmd = f"trace {class_pattern} {method_pattern} -n {sample_count} '{skip_flag} #cost > .1'"
    result = ArthasCommandExecutor.execute(conn, cmd, timeout_ms=30000)

    body = result.get('body', [])
    trace_lines = []
    if isinstance(body, list):
        for line in body:
            cost_match = re.findall(r'#(\d+)\s+[^\[]+\[(\d+(?:\.\d+)?)(ms|us|s)\]', str(line))
            for seq, val, unit in cost_match:
                ms_val = float(val) * (1000 if unit == 's' else (1 if unit == 'ms' else 0.001))
                trace_lines.append({"seq": seq, "cost_ms": round(ms_val, 3), "unit": unit})

    trace_lines.sort(key=lambda x: x['cost_ms'], reverse=True)
    return {
        "command": cmd,
        "slow_methods": trace_lines[:10],
        "total_sampled": len(trace_lines),
        "summary": f"采样 {len(trace_lines)} 次，最高耗时 {trace_lines[0]['cost_ms']:.2f}ms" if trace_lines else "未采样到数据"
    }


def _exec_dashboard(conn) -> dict:
    """执行 dashboard 命令"""
    import re
    result = ArthasCommandExecutor.execute(conn, "dashboard -n 1", timeout_ms=15000)
    body = result.get('body', [])
    raw = '\n'.join(str(l) for l in (body if isinstance(body, list) else [body]))

    metrics = {}
    cpu = re.search(r'cpu\s*=\s*(\d+(?:\.\d+)?)\s*%', raw, re.I)
    if cpu:
        metrics['cpu_percent'] = round(float(cpu.group(1)), 2)

    mem = re.findall(r'(Old|Young|Eden|Survivor|heap)[^\d]*(\d+(?:\.\d+)?)\s*(MB|GB)', raw, re.I)
    if mem:
        metrics['memory'] = [{"area": a, "value": float(v), "unit": u} for a, v, u in mem[:6]]

    gc = re.findall(r'(YGC|FGC|GCT)[^\d]*(\d+)', raw, re.I)
    if gc:
        metrics['gc'] = [{"type": t.upper(), "count": int(c)} for t, c in gc[:4]]

    return {"metrics": metrics, "raw_snippet": raw[:2000], "timestamp": conn.target.pod_name}


def _exec_thread_analysis(conn, top_n: int, check_deadlock: bool) -> dict:
    """执行线程分析"""
    thread_resp = ArthasCommandExecutor.execute(conn, f"thread -n {top_n}", timeout_ms=20000)
    threads = []
    body = thread_resp.get('body', {})
    if isinstance(body, dict):
        for r in body.get('results', []):
            busy = r.get('busyThreads') or r.get('threads') or []
            for th in (busy if isinstance(busy, list) else []):
                threads.append({
                    "name": th.get('name', '?'),
                    "id": th.get('id', 0),
                    "state": th.get('state', '?'),
                    "cpu": th.get('cpu', 0),
                    "deltaTime": th.get('deltaTime', 0),
                })

    deadlock_info = None
    if check_deadlock:
        try:
            dl_resp = ArthasCommandExecutor.execute(conn, "thread -b", timeout_ms=15000)
            dl_body = dl_resp.get('body', {}) if isinstance(dl_resp, dict) else {}
            bt = dl_body.get('blockingThread')
            if bt and isinstance(bt, dict) and bt.get('threadName'):
                deadlock_info = json.dumps(dl_resp, ensure_ascii=False)[:500]
        except Exception:
            pass

    blocked = [t for t in threads if t['state'] == 'BLOCKED']
    return {
        "summary": {"total": len(threads), "blocked": len(blocked), "deadlock": deadlock_info is not None},
        "top_threads": threads[:top_n],
        "blocked_threads": blocked[:5],
        "deadlock_info": deadlock_info
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 代理 POST 请求（拦截性能诊断工具）
# ═══════════════════════════════════════════════════════════════════════════════

def _proxy_post(target_url: str, original_request):
    """代理 POST 请求（MCP JSON-RPC），支持 SSE 流式响应，拦截性能诊断工具本地处理"""
    body = original_request.get_data()
    import json as _json

    # ── 尝试拦截性能诊断工具调用 ────────────────────────────────
    try:
        rpc_req = _json.loads(body.decode('utf-8'))
        method = rpc_req.get('method', '')
        params = rpc_req.get('params', {})

        # 拦截 tools/call 类型的请求
        if method in ('tools/call', 'tools/call/stream', 'mcp_tools_call'):
            tool_calls = []
            # 支持不同格式的 tool_calls
            if 'tool_calls' in params:
                tool_calls = params['tool_calls']
            elif 'name' in params:
                tool_calls = [params]
            elif isinstance(params, list):
                tool_calls = params

            for tc in tool_calls:
                tool_name = tc.get('name', '') or tc.get('function', {}).get('name', '')
                arguments = tc.get('input', {}) or tc.get('arguments', {}) or {}

                if tool_name in [t['name'] for t in PERF_MCP_TOOLS]:
                    # 获取连接信息（从 mcp_proxy 调用上下文获取）
                    # 这里通过 token 来获取，简化处理：直接用 connection_id
                    token_val = original_request.view_args.get('token', '') if hasattr(original_request, 'view_args') else ''
                    if token_val:
                        token_entry = db.fetch_one('SELECT * FROM mcp_tokens WHERE token = ?', (token_val,))
                    else:
                        token_entry = None

                    if not token_entry:
                        result = {"content": [{"type": "text", "text": "错误: 无法获取连接信息"}]}
                    else:
                        result = _handle_perf_mcp_tool(token_entry, tool_name, arguments)

                    resp_data = {
                        "jsonrpc": "2.0",
                        "result": result,
                        "id": rpc_req.get('id')
                    }
                    return Response(
                        _json.dumps(resp_data, ensure_ascii=False),
                        status=200,
                        content_type='application/json'
                    )

        # 拦截 tools/list 请求：追加性能诊断工具
        if method == 'tools/list':
            perf_result = {
                "tools": PERF_MCP_TOOLS
            }
            # 转发到 Arthas 获取原生工具列表，然后合并
            req = urllib.request.Request(target_url, data=body, method='POST')
            req.add_header('Content-Type', original_request.content_type or 'application/json')
            req.add_header('Accept', 'application/json, text/event-stream')
            try:
                resp = urllib.request.urlopen(req, timeout=30)
                resp_body = resp.read()
                resp.close()
                # 合并工具列表
                try:
                    orig_result = _json.loads(resp_body)
                    if 'result' in orig_result and 'tools' in orig_result['result']:
                        orig_tools = orig_result['result']['tools']
                        merged_tools = orig_tools + PERF_MCP_TOOLS
                        orig_result['result']['tools'] = merged_tools
                        resp_body = _json.dumps(orig_result, ensure_ascii=False)
                except Exception:
                    pass
                flask_resp = Response(resp_body, status=200, content_type='application/json')
                flask_resp.headers['Access-Control-Allow-Origin'] = '*'
                return flask_resp
            except Exception:
                # Arthas MCP 不可用时，返回本地工具
                resp_data = {"jsonrpc": "2.0", "result": perf_result, "id": rpc_req.get('id')}
                return Response(
                    _json.dumps(resp_data, ensure_ascii=False),
                    status=200,
                    content_type='application/json'
                )

    except Exception:
        pass  # 非 JSON 格式或解析失败，走正常代理路径

    # ── 正常代理到 Arthas MCP Server ────────────────────────────

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
