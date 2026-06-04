#!/usr/bin/env python3
"""AI Skill Definitions for Skill Registry integration.

Defines three AI capabilities (diagnose, chat, analyze_performance) as
Skill Registry entries. These are inserted into skill_registry on first run
alongside the existing PROFILER_SKILLS.

The handler_key field maps each skill to AISkillHandler for execution.
The handler field points to the bridge function that WorkflowEngine calls.

Author: Phase 7 T02
"""

import json

AI_SKILLS = [
    {
        "name": "ai-assisted-diagnosis",
        "version": "1.0.0",
        "description": "使用 AI 分析诊断结果，给出根因分析和修复建议",
        "category": "ai",
        "level": 3,
        "risk_level": "low",
        "estimated_duration": 60,
        "source": "builtin",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "symptoms": {"type": "string", "description": "问题描述"},
                "diagnosis_result": {"type": "object", "description": "诊断结果数据"},
                "connection_context": {"type": "object", "description": "连接上下文"},
            },
            "required": ["symptoms"],
        }),
        "handler": "services.ai_skill_handler.execute_ai_skill",
        "handler_key": "ai.diagnose",
    },
    {
        "name": "ai-chat",
        "version": "1.0.0",
        "description": "与 AI 助手对话，讨论技术问题",
        "category": "ai",
        "level": 3,
        "risk_level": "low",
        "estimated_duration": 30,
        "source": "builtin",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "用户消息"},
                "context": {"type": "object", "description": "对话上下文"},
            },
            "required": ["message"],
        }),
        "handler": "services.ai_skill_handler.execute_ai_skill",
        "handler_key": "ai.chat",
    },
    {
        "name": "ai-performance-analysis",
        "version": "1.0.0",
        "description": "使用 AI 分析性能采样数据（CPU/内存/线程）",
        "category": "ai",
        "level": 3,
        "risk_level": "low",
        "estimated_duration": 120,
        "source": "builtin",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "profile_data": {"type": "object", "description": "性能采样数据"},
                "analysis_type": {"type": "string", "enum": ["cpu", "memory", "thread"], "description": "分析类型"},
            },
            "required": ["profile_data", "analysis_type"],
        }),
        "handler": "services.ai_skill_handler.execute_ai_skill",
        "handler_key": "ai.analyze_performance",
    },
]
