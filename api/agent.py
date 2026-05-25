#!/usr/bin/env python3
"""Agent Chat API 路由

本模块提供 AI Agent 对话的 API 路由：
- POST /api/agent/send_message  发送消息到 AI Agent（流式 SSE）

该端点是 ai_chat.py /api/ai/chat 的前端友好包装：
- 接受 agent-chat.js 的消息格式（单条 message + session_id）
- 自动获取异常检测事件作为上下文
- 维护会话消息历史
- 委托给 ai_chat.py 的流式对话逻辑

Author: Phase 7 T07
Created: 2026-05-26
"""

import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_login import login_required, current_user

from models.db import db

log = logging.getLogger(__name__)

agent_bp = Blueprint('agent', __name__)

# 会话消息缓存（内存中，重启丢失，符合会话语义）
_sessions: dict = {}  # session_id -> {'messages': [...], 'user_id': int, 'created_at': str}


@agent_bp.route('/api/agent/send_message', methods=['POST'])
@login_required
def send_message():
    """发送消息到 AI Agent（流式 SSE）

    请求体：
    {
        "message": "用户消息",
        "session_id": "可选，会话 ID",
        "connection_id": "可选，连接 ID",
        "stream": true
    }

    响应：SSE 流，与 /api/ai/chat 格式一致
    """
    d = request.json or {}
    message = (d.get('message') or '').strip()
    session_id = d.get('session_id') or ''
    connection_id = d.get('connection_id') or ''
    stream = d.get('stream', True)

    if not message:
        return jsonify({"error": "消息不能为空"}), 400

    # 获取或创建会话
    if not session_id:
        import secrets
        session_id = secrets.token_hex(8)

    session = _get_or_create_session(session_id, current_user.id)

    # 获取异常事件上下文
    anomaly_context = _fetch_anomaly_context(connection_id)

    # 将用户消息加入会话历史
    session['messages'].append({
        'role': 'user',
        'content': message,
    })

    # 限制历史长度（保留最近 20 条消息）
    if len(session['messages']) > 20:
        session['messages'] = session['messages'][-20:]

    # 构建带异常上下文的消息列表
    full_messages = _build_messages_with_anomaly(session['messages'], anomaly_context)

    # 复用 ai_chat 的核心逻辑
    from api.ai_chat import _get_connection_info, _stream_chat, _sync_chat, DEFAULT_SYSTEM_PROMPT

    # 获取 AI 配置
    config = db.fetch_one('SELECT * FROM ai_config WHERE user_id = ?', (current_user.id,))
    if not config:
        return jsonify({"error": "请先配置 AI 模型（点击设置图标）"}), 400

    is_ollama = config.get('provider') == 'ollama' or 'ollama' in (config.get('base_url') or '').lower() or 'localhost:11434' in (config.get('base_url') or '')
    if not config.get('api_key') and not is_ollama:
        return jsonify({"error": "请先配置 AI 模型 API Key（点击设置图标）"}), 400

    # 构建系统提示词
    conn_info = _get_connection_info(connection_id)
    system_msg = config.get('system_prompt') or DEFAULT_SYSTEM_PROMPT
    if conn_info:
        system_msg += f"\n\n当前诊断环境:\n{conn_info}"
    if anomaly_context:
        system_msg += f"\n\n{anomaly_context}"

    # 插入系统提示词
    messages_for_llm = [{"role": "system", "content": system_msg}] + full_messages

    # 调用流式对话
    if stream:
        resp = _stream_chat(config, messages_for_llm, connection_id)

        # 获取原始异常事件数据（用于前端渲染可点击卡片）
        anomaly_events = _fetch_anomaly_events_list(connection_id)

        # 包装响应以捕获 AI 回复并存入会话历史
        return _wrap_stream_response(resp, session, session_id, anomaly_events)
    else:
        # 非流式：直接调用
        result = _sync_chat(config, messages_for_llm, connection_id)
        # 尝试从结果中提取 AI 回复
        try:
            data = result.get_json() if hasattr(result, 'get_json') else None
            if data and data.get('message'):
                session['messages'].append({
                    'role': 'assistant',
                    'content': data['message'].get('content', ''),
                })
        except Exception:
            pass
        return result


def _get_or_create_session(session_id: str, user_id: int) -> dict:
    """获取或创建会话"""
    if session_id not in _sessions:
        _sessions[session_id] = {
            'messages': [],
            'user_id': user_id,
            'created_at': datetime.now().isoformat(),
        }
    return _sessions[session_id]


def _fetch_anomaly_context(connection_id: str) -> str:
    """获取异常事件上下文（供 AI 分析使用）"""
    if not connection_id:
        return ''

    try:
        from services.anomaly_detector import get_anomaly_detector
        detector = get_anomaly_detector()

        parts = connection_id.split('/')
        cluster = parts[0] if len(parts) > 0 else ''
        namespace = parts[1] if len(parts) > 1 else ''
        pod = parts[2] if len(parts) > 2 else ''

        result = detector.get_events(
            cluster=cluster,
            namespace=namespace,
            pod=pod,
            page=1,
            page_size=10,  # 只取最近 10 条，避免上下文过长
        )

        events = result.get('events', [])
        if not events:
            return ''

        # 格式化异常事件为文本
        lines = ['[异常检测] 最近的异常事件（供分析参考）:']
        for evt in events:
            severity = evt.get('severity', 'unknown')
            rule_name = evt.get('rule_name', '未知规则')
            message = evt.get('message', '')
            created_at = evt.get('created_at', '')
            metric_value = evt.get('metric_value', '')
            threshold = evt.get('threshold', '')

            line = f"- [{severity.upper()}] {created_at} {rule_name}"
            if message:
                line += f": {message}"
            if metric_value and threshold:
                line += f" (指标值={metric_value}, 阈值={threshold})"
            lines.append(line)

        return '\n'.join(lines)

    except Exception as e:
        log.debug("获取异常上下文失败: %s", e)
        return ''


def _fetch_anomaly_events_list(connection_id: str) -> list:
    """获取异常事件列表（结构化数据，供前端渲染可点击卡片）"""
    if not connection_id:
        return []

    try:
        from services.anomaly_detector import get_anomaly_detector
        detector = get_anomaly_detector()

        parts = connection_id.split('/')
        cluster = parts[0] if len(parts) > 0 else ''
        namespace = parts[1] if len(parts) > 1 else ''
        pod = parts[2] if len(parts) > 2 else ''

        result = detector.get_events(
            cluster=cluster,
            namespace=namespace,
            pod=pod,
            page=1,
            page_size=10,
        )

        events = result.get('events', [])
        return [
            {
                'id': evt.get('id'),
                'severity': evt.get('severity', 'unknown'),
                'rule_name': evt.get('rule_name', ''),
                'message': evt.get('message', ''),
                'created_at': evt.get('created_at', ''),
                'metric_value': evt.get('metric_value', ''),
                'threshold': evt.get('threshold', ''),
            }
            for evt in events
        ]

    except Exception as e:
        log.debug("获取异常事件列表失败: %s", e)
        return []


def _build_messages_with_anomaly(messages: list, anomaly_context: str) -> list:
    """构建带异常上下文的消息列表

    如果有异常上下文，在最后一条用户消息中附加上下文信息。
    这样 AI 在回复时会参考异常事件。
    """
    if not anomaly_context:
        return list(messages)

    # 在最后一条用户消息前附加异常上下文
    result = []
    for i, msg in enumerate(messages):
        if msg['role'] == 'user' and i == len(messages) - 1:
            result.append({
                'role': 'user',
                'content': f"{anomaly_context}\n\n用户问题: {msg['content']}",
            })
        else:
            result.append(msg)

    return result


def _wrap_stream_response(resp, session: dict, session_id: str, anomaly_events: list = None):
    """包装流式响应，捕获 AI 回复并存入会话历史

    如果有异常事件，在流开始前先发送 anomaly_events SSE 事件。
    """
    original_generate = resp.response

    def wrapped_generate():
        # 先发送异常事件（供前端渲染可点击卡片）
        if anomaly_events:
            evt_data = json.dumps({
                'type': 'anomaly_events',
                'events': anomaly_events,
            }, ensure_ascii=False)
            yield f"data: {evt_data}\n\n"

        full_content = ''
        for chunk in original_generate:
            # 解码 chunk
            if isinstance(chunk, bytes):
                chunk_str = chunk.decode('utf-8', errors='replace')
            else:
                chunk_str = str(chunk)

            # 尝试从 SSE 数据中提取内容
            for line in chunk_str.split('\n'):
                if line.startswith('data: '):
                    data_str = line[6:].strip()
                    if not data_str:
                        continue
                    try:
                        data = json.loads(data_str)
                        if data.get('type') == 'content':
                            full_content += data.get('content', '')
                        elif data.get('type') == 'done':
                            # 流结束，保存 AI 回复到会话
                            if full_content:
                                session['messages'].append({
                                    'role': 'assistant',
                                    'content': full_content,
                                })
                    except (json.JSONDecodeError, Exception):
                        pass

            yield chunk

    return Response(
        stream_with_context(wrapped_generate()),
        content_type=resp.content_type,
        headers=dict(resp.headers),
    )


@agent_bp.route('/api/agent/sessions/<session_id>', methods=['DELETE'])
@login_required
def clear_session(session_id: str):
    """清空会话历史"""
    if session_id in _sessions:
        del _sessions[session_id]
    return jsonify({"ok": True})


@agent_bp.route('/api/agent/sessions', methods=['GET'])
@login_required
def list_sessions():
    """列出当前用户的会话"""
    sessions = []
    for sid, session in _sessions.items():
        if session.get('user_id') == current_user.id:
            sessions.append({
                'session_id': sid,
                'message_count': len(session.get('messages', [])),
                'created_at': session.get('created_at', ''),
            })
    return jsonify({"sessions": sessions})
