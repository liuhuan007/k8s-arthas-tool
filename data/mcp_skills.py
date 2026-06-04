#!/usr/bin/env python3
"""MCP Skill Definitions for Skill Registry integration.

Defines three MCP capabilities (kubectl_exec/arthas_command/pod_metrics) as
Skill Registry entries. These are inserted into the skill_registry table
alongside the existing BUILTIN_SKILLS in diagnosis_capabilities.py.

The handler_key field maps each skill to MCPSkillHandler for execution.
The handler field points to the bridge function that WorkflowEngine calls.

Author: Phase 7 T03
"""

import json

# MCP skills follow the same schema as BUILTIN_SKILLS in
# backend/core/diagnosis_capabilities.py. They are inserted into the
# skill_registry table via _seed_mcp_skills().

MCP_SKILLS = [
    {
        "name": "mcp-kubectl-exec",
        "version": "1.0.0",
        "description": "在 Pod 内执行命令（通过 MCP 协议暴露给 AI Agent）",
        "category": "mcp",
        "level": 1,
        "risk_level": "medium",
        "estimated_duration": 30,
        "source": "builtin",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        }),
        "handler": "services.mcp_skill_handler.execute_mcp_skill",
        "handler_key": "mcp.kubectl_exec",
    },
    {
        "name": "mcp-arthas-command",
        "version": "1.0.0",
        "description": "执行 Arthas 诊断命令（通过 MCP 协议暴露给 AI Agent）",
        "category": "mcp",
        "level": 1,
        "risk_level": "medium",
        "estimated_duration": 60,
        "source": "builtin",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Arthas 命令"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        }),
        "handler": "services.mcp_skill_handler.execute_mcp_skill",
        "handler_key": "mcp.arthas_command",
    },
    {
        "name": "mcp-pod-metrics",
        "version": "1.0.0",
        "description": "获取 Pod 资源使用指标（通过 MCP 协议暴露给 AI Agent）",
        "category": "mcp",
        "level": 0,
        "risk_level": "low",
        "estimated_duration": 15,
        "source": "builtin",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "metrics_type": {"type": "string", "enum": ["cpu", "memory", "network", "all"], "default": "all"},
            },
        }),
        "handler": "services.mcp_skill_handler.execute_mcp_skill",
        "handler_key": "mcp.get_pod_metrics",
    },
]
