"""
MCP Standard API — Flask HTTP Bridge

提供 HTTP 端点，让远程 AI 客户端通过标准 HTTP 调用 MCP Tools。
内部调用 services/mcp_server.py 的 execute_tool()。

端点:
  GET  /api/mcp/v1/tools              列出所有 MCP Tools
  POST /api/mcp/v1/tools/<name>/call  调用指定 Tool
"""
import json
import logging
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from services.mcp_server import TOOLS, execute_tool

log = logging.getLogger(__name__)

mcp_std_bp = Blueprint('mcp_standard', __name__)


@mcp_std_bp.route('/api/mcp/v1/tools', methods=['GET'])
def list_tools():
    """列出所有可用 MCP Tools（无需认证，供 AI 客户端发现工具）"""
    return jsonify({
        "tools": [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for t in TOOLS
        ],
        "count": len(TOOLS),
        "server": "arthas-diagnosis",
    })


@mcp_std_bp.route('/api/mcp/v1/tools/<tool_name>/call', methods=['POST'])
@login_required
def call_tool(tool_name):
    """调用指定 MCP Tool

    请求体: { "connection_id": "...", ...其他参数 }
    响应:   { "result": "..." }
    """
    import asyncio

    # 验证工具名
    valid_names = {t["name"] for t in TOOLS}
    if tool_name not in valid_names:
        return jsonify({"error": f"未知工具: {tool_name}"}), 404

    d = request.json or {}
    if not d.get("connection_id"):
        return jsonify({"error": "connection_id 必填"}), 400

    try:
        result = asyncio.run(execute_tool(tool_name, d))
        return jsonify({"result": result, "tool": tool_name})
    except Exception as e:
        log.error("MCP tool '%s' 调用失败: %s", tool_name, e, exc_info=True)
        return jsonify({"error": str(e), "tool": tool_name}), 500


@mcp_std_bp.route('/api/mcp/v1/execute', methods=['POST'])
@login_required
def execute_batch():
    """批量执行多个 MCP Tool

    请求体: { "connection_id": "...", "commands": [{"tool": "...", "args": {...}}, ...] }
    """
    import asyncio

    d = request.json or {}
    conn_id = d.get("connection_id", "")
    commands = d.get("commands", [])

    if not conn_id:
        return jsonify({"error": "connection_id 必填"}), 400
    if not commands:
        return jsonify({"error": "commands 必填"}), 400

    results = []
    for cmd in commands[:10]:  # 最多 10 个
        tool_name = cmd.get("tool", "")
        args = {**cmd.get("args", {}), "connection_id": conn_id}
        try:
            r = asyncio.run(execute_tool(tool_name, args))
            results.append({"tool": tool_name, "result": r, "ok": True})
        except Exception as e:
            results.append({"tool": tool_name, "error": str(e), "ok": False})

    return jsonify({"results": results, "count": len(results)})
