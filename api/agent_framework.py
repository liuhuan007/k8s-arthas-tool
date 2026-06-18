"""Agent Framework API — 多专业 Agent 对话端点"""
from __future__ import annotations
import json
import asyncio
import logging
from flask import Blueprint, request, jsonify, Response
from api.auth import login_required

log = logging.getLogger(__name__)

agent_fw_bp = Blueprint('agent_framework', __name__, url_prefix='/api/agent-fw')

_registry = None
_router = None


def init_agent_framework(registry, router):
    global _registry, _router
    _registry = registry
    _router = router


@agent_fw_bp.route('/list', methods=['GET'])
@login_required
def list_agents():
    """获取可用 Agent 列表"""
    return jsonify({"agents": _registry.list_agents()})


@agent_fw_bp.route('/chat', methods=['POST'])
@login_required
def agent_chat():
    """Agent 对话 — 同步模式"""
    data = request.get_json(force=True)
    user_input = data.get("message", "").strip()
    agent_name = data.get("agent")
    mode = data.get("mode", "auto")

    if not user_input:
        return jsonify({"error": "请输入消息"}), 400

    # 选择 Agent
    if agent_name and _registry.get(agent_name):
        agent = _registry.get(agent_name)
    else:
        agent_name = _router.route(user_input)
        agent = _registry.get(agent_name)

    if not agent:
        return jsonify({"error": "无可用 Agent"}), 500

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(agent.run(user_input, mode=mode))
    finally:
        loop.close()

    return jsonify({
        "ok": True,
        "agent": agent.display_name,
        "answer": result.answer,
        "steps": [
            {"tool": s.tool_name, "args": s.tool_args, "result": s.result[:500]}
            for s in result.steps
        ],
        "mode": result.mode,
    })


@agent_fw_bp.route('/stream', methods=['POST'])
@login_required
def agent_stream():
    """Agent 对话 — SSE 流式模式"""
    data = request.get_json(force=True)
    user_input = data.get("message", "").strip()
    agent_name = data.get("agent")
    mode = data.get("mode", "auto")

    if not user_input:
        return jsonify({"error": "请输入消息"}), 400

    if agent_name and _registry.get(agent_name):
        agent = _registry.get(agent_name)
    else:
        agent_name = _router.route(user_input)
        agent = _registry.get(agent_name)

    if not agent:
        return jsonify({"error": "无可用 Agent"}), 500

    def generate():
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(agent.run(user_input, mode=mode))
        finally:
            loop.close()

        event = json.dumps({
            "type": "answer",
            "content": result.answer,
            "agent": agent.display_name,
            "steps": [
                {"tool": s.tool_name, "result": s.result[:300]}
                for s in result.steps
            ],
        }, ensure_ascii=False)
        yield f"data: {event}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype='text/event-stream')
