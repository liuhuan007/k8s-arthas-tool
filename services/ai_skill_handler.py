#!/usr/bin/env python3
"""AI Skill Handler - Bridge between Skill Registry and AI modules.

This module provides the handler function invoked by the task_center when
an AI skill is executed. It translates skill parameters into LLM API calls,
reusing the user's existing AI configuration (ai_config table).

The handler function signature matches the profiler_skill_handler pattern:
    func(params: dict, connection_id: str) -> Any

Supported handler_keys:
    - ai.diagnose:  AI-assisted diagnosis with root cause analysis
    - ai.chat:      General AI conversation
    - ai.analyze_performance:  AI analysis of performance profiling data

Each handler reads the user's AI config from ai_config, constructs an
appropriate system prompt, calls the LLM via OpenAI-compatible API, and
returns a structured result dict.

The LLM call logic mirrors api/ai_chat.py's _call_llm() pattern but
runs synchronously in a background thread (no Flask request context).

Author: Phase 7 T02
"""

import json
import logging
import urllib.request
from datetime import datetime
from typing import Any, Dict

log = logging.getLogger(__name__)

# Maps handler_key to handler method
_AI_HANDLER_MAP: Dict[str, str] = {
    "ai.diagnose": "_diagnose",
    "ai.chat": "_chat",
    "ai.analyze_performance": "_analyze_performance",
}

# System prompts for each skill type
_DIAGNOSE_SYSTEM_PROMPT = """你是一个 Java 应用性能诊断专家。请根据提供的诊断数据，给出：
1. 根因分析（最可能的原因）
2. 影响范围评估
3. 具体修复建议（可操作的步骤）
4. 预防措施

使用中文回复，格式清晰。"""

_CHAT_SYSTEM_PROMPT = """你是一个 Java 应用性能诊断专家，帮助用户分析 Kubernetes Pod 中的 Java 应用问题。
请用中文回复，技术术语可保留英文。"""

_ANALYZE_SYSTEM_PROMPT = """你是一个 Java 性能分析专家。请分析提供的性能采样数据，给出：
1. 性能瓶颈识别
2. 关键指标解读
3. 优化建议
4. 进一步诊断建议

使用中文回复，数据引用要准确。"""


def execute_ai_skill(params: Dict[str, Any], connection_id: str) -> Any:
    """Execute an AI skill via LLM API.

    This function is called by task_center._execute_ai_diagnosis() when a
    capability with handler_key starting with 'ai.' is dispatched. It reads
    the user's AI config, constructs a prompt, and calls the LLM.

    Args:
        params: Skill parameters dict. Must contain:
            - user_id (int): User ID for loading AI config
            - handler_key (str): Identifies the AI skill type
            - Skill-specific parameters (symptoms, message, profile_data, etc.)
        connection_id: Connection identifier (format: cluster/namespace/pod)

    Returns:
        dict: Execution result with keys:
            - ok (bool): Whether execution succeeded
            - result (str): AI response content
            - handler_key (str): The AI skill type that was executed
    """
    handler_key = params.get("handler_key", "ai.diagnose")
    user_id = params.get("user_id")

    method_name = _AI_HANDLER_MAP.get(handler_key)
    if not method_name:
        return {
            "ok": False,
            "error": f"Unknown AI handler_key: {handler_key}",
        }

    log.info(
        "Executing AI skill: handler_key=%s, connection_id=%s, user_id=%s",
        handler_key, connection_id, user_id,
    )

    # Load user's AI config
    config = _load_ai_config(user_id)
    if not config:
        return {
            "ok": False,
            "error": "未配置 AI 模型，请先在 AI 设置中配置大模型",
        }

    handler_method = globals().get(method_name) or locals().get(method_name)
    if not handler_method:
        # Fallback: resolve via class-level dispatch (not needed for module functions,
        # but kept for safety)
        return {
            "ok": False,
            "error": f"Handler method not found: {method_name}",
        }

    try:
        return handler_method(config, params, connection_id)
    except Exception as e:
        log.error("AI skill execution failed: %s", e, exc_info=True)
        return {
            "ok": False,
            "error": str(e),
            "handler_key": handler_key,
        }


def _diagnose(config: Dict[str, Any], params: Dict[str, Any],
              connection_id: str) -> Dict[str, Any]:
    """AI 辅助诊断：分析症状和诊断结果，给出根因分析和修复建议。"""
    symptoms = params.get("symptoms", "")
    diagnosis_result = params.get("diagnosis_result", {})
    connection_context = params.get("connection_context", {})

    # Build user message
    user_content = f"问题描述: {symptoms}"
    if diagnosis_result:
        result_text = json.dumps(diagnosis_result, ensure_ascii=False)[:3000]
        user_content += f"\n\n诊断数据:\n{result_text}"
    if connection_context:
        ctx_text = json.dumps(connection_context, ensure_ascii=False)[:500]
        user_content += f"\n\n环境信息:\n{ctx_text}"

    messages = [
        {"role": "system", "content": _DIAGNOSE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    return _call_llm_and_wrap(config, messages, "ai.diagnose")


def _chat(config: Dict[str, Any], params: Dict[str, Any],
          connection_id: str) -> Dict[str, Any]:
    """AI 对话：与 AI 助手对话，讨论技术问题。"""
    message = params.get("message", "")
    context = params.get("context", {})

    system_prompt = _CHAT_SYSTEM_PROMPT
    if context:
        ctx_text = json.dumps(context, ensure_ascii=False)[:500]
        system_prompt += f"\n\n当前上下文:\n{ctx_text}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    return _call_llm_and_wrap(config, messages, "ai.chat")


def _analyze_performance(config: Dict[str, Any], params: Dict[str, Any],
                         connection_id: str) -> Dict[str, Any]:
    """AI 性能分析：分析性能采样数据（CPU/内存/线程）。"""
    profile_data = params.get("profile_data", {})
    analysis_type = params.get("analysis_type", "cpu")

    # Build analysis-specific prompt
    type_prompts = {
        "cpu": "请重点分析 CPU 使用模式、热点方法和可能的 CPU 密集型操作。",
        "memory": "请重点分析内存分配模式、潜在泄漏和 GC 压力。",
        "thread": "请重点分析线程状态、阻塞链和并发问题。",
    }
    type_hint = type_prompts.get(analysis_type, type_prompts["cpu"])

    data_text = json.dumps(profile_data, ensure_ascii=False)[:5000]
    user_content = f"分析类型: {analysis_type}\n\n{type_hint}\n\n性能数据:\n{data_text}"

    messages = [
        {"role": "system", "content": _ANALYZE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    return _call_llm_and_wrap(config, messages, "ai.analyze_performance")


# ═══════════════════════════════════════════════════════════════════════════════
# LLM API helpers (mirrors api/ai_chat.py pattern, no Flask context required)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_ai_config(user_id: int) -> Dict[str, Any]:
    """Load user's AI config from database."""
    if not user_id:
        return None
    try:
        from models.db import db
        return db.fetch_one('SELECT * FROM ai_config WHERE user_id = ?', (user_id,))
    except Exception as e:
        log.error("Failed to load AI config for user %s: %s", user_id, e)
        return None


def _call_llm_and_wrap(config: Dict[str, Any], messages: list,
                       handler_key: str) -> Dict[str, Any]:
    """Call LLM API and wrap the result in a standard response dict.

    This mirrors the _call_llm() + _sync_chat() pattern from api/ai_chat.py
    but runs synchronously (no Flask request context, no tool calling).
    """
    try:
        content = _call_llm(config, messages)
        return {
            "ok": True,
            "result": content,
            "handler_key": handler_key,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        log.error("LLM call failed for %s: %s", handler_key, e, exc_info=True)
        return {
            "ok": False,
            "error": f"AI 模型调用失败: {str(e)}",
            "handler_key": handler_key,
        }


def _call_llm(config: Dict[str, Any], messages: list) -> str:
    """Call OpenAI-compatible LLM API (synchronous, no tools).

    Mirrors api/ai_chat.py::_call_llm() but without tool support,
    suitable for background thread execution.

    Args:
        config: AI config dict from ai_config table
        messages: Chat messages list

    Returns:
        str: Assistant response content

    Raises:
        Exception: On API call failure
    """
    base_url = (config.get('base_url') or '').rstrip('/')
    url = f"{base_url}/chat/completions"

    payload = {
        "model": config['model'],
        "messages": messages,
        "stream": False,
    }

    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')

    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    if config.get('api_key'):
        req.add_header('Authorization', f"Bearer {config['api_key']}")

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode('utf-8'))

    choices = result.get('choices', [])
    if not choices:
        raise ValueError("模型未返回任何结果")

    return choices[0].get('message', {}).get('content', '')
