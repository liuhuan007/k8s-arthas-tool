#!/usr/bin/env python3
"""诊断工作流 Skill 定义

Top 10 诊断场景的 Skill 定义，用于 AI Agent 自动化诊断流程。
每个 Skill 定义了完整的诊断步骤，包括 CLI 命令、健康检查、LLM 分析。

Author: CLI Architecture Phase
"""

import json

DIAGNOSIS_SKILLS = [
    # ── 1. CPU 高排查 ──────────────────────────────────────────
    {
        "name": "cpu-high-diagnosis",
        "version": "1.0.0",
        "description": "CPU 使用率过高诊断流程",
        "category": "diagnosis",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 120,
        "source": "builtin",
        "triggers": {
            "user_input": ["CPU.*高", "CPU.*飙", "CPU.*100%", "CPU.*满"],
            "alert": ["cpu_usage > 80%"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "pod_name": {"type": "string", "description": "Pod 名称（可选）"},
            },
        }),
        "workflow": json.dumps([
            {
                "id": "check_pod_status",
                "cli": "kubectl",
                "command": "get_pods",
                "params": {"namespace": "{namespace}"},
                "description": "检查 Pod 运行状态",
            },
            {
                "id": "thread_analysis",
                "cli": "arthas",
                "command": "thread",
                "params": {"top_n": 5},
                "description": "分析 CPU 占用最高的线程",
                "condition": "check_pod_status.health == 'healthy'",
            },
            {
                "id": "jvm_baseline",
                "cli": "arthas",
                "command": "dashboard",
                "params": {"n": 1},
                "description": "获取 JVM 基线指标",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze",
                "input": ["thread_analysis", "jvm_baseline"],
                "prompt": "分析 CPU 高的根因，给出优化建议",
                "description": "AI 分析诊断结果",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 2. 接口慢排查 ──────────────────────────────────────────
    {
        "name": "api-slow-diagnosis",
        "version": "1.0.0",
        "description": "接口响应慢诊断流程",
        "category": "diagnosis",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 120,
        "source": "builtin",
        "triggers": {
            "user_input": ["接口.*慢", "响应.*慢", "延迟.*高", "超时"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "class_pattern": {"type": "string", "description": "类名模式"},
                "method_pattern": {"type": "string", "description": "方法名"},
            },
            "required": ["class_pattern", "method_pattern"],
        }),
        "workflow": json.dumps([
            {
                "id": "check_connection",
                "cli": "arthas",
                "command": "dashboard",
                "params": {"n": 1},
                "description": "检查 Arthas 连接和 JVM 状态",
            },
            {
                "id": "trace_method",
                "cli": "arthas",
                "command": "trace",
                "params": {
                    "class_pattern": "{class_pattern}",
                    "method_pattern": "{method_pattern}",
                    "sample_count": 10,
                },
                "description": "追踪方法调用链耗时",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze",
                "input": ["check_connection", "trace_method"],
                "prompt": "分析接口慢的根因，定位耗时最长的方法调用",
                "description": "AI 分析诊断结果",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 3. Pod 异常排查 ──────────────────────────────────────────
    {
        "name": "pod-crash-diagnosis",
        "version": "1.0.0",
        "description": "Pod CrashLoopBackOff 诊断流程",
        "category": "diagnosis",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 90,
        "source": "builtin",
        "triggers": {
            "user_input": ["Pod.*异常", "Pod.*Crash", "Pod.*重启", "Pod.*OOM"],
            "alert": ["pod_status != Running"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "pod_name": {"type": "string", "description": "Pod 名称"},
            },
            "required": ["namespace", "pod_name"],
        }),
        "workflow": json.dumps([
            {
                "id": "describe_pod",
                "cli": "kubectl",
                "command": "describe_pod",
                "params": {"namespace": "{namespace}", "name": "{pod_name}"},
                "description": "获取 Pod 详细信息和事件",
            },
            {
                "id": "get_logs",
                "cli": "kubectl",
                "command": "get_pod_logs",
                "params": {"namespace": "{namespace}", "name": "{pod_name}", "previous": True},
                "description": "获取上一次崩溃日志",
            },
            {
                "id": "get_events",
                "cli": "kubectl",
                "command": "get_events",
                "params": {"namespace": "{namespace}"},
                "description": "获取 Pod 相关事件",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze",
                "input": ["describe_pod", "get_logs", "get_events"],
                "prompt": "分析 Pod 崩溃原因，给出修复建议",
                "description": "AI 分析诊断结果",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 4. 内存泄漏排查 ──────────────────────────────────────────
    {
        "name": "memory-leak-diagnosis",
        "version": "1.0.0",
        "description": "内存泄漏诊断流程",
        "category": "diagnosis",
        "level": 2,
        "risk_level": "medium",
        "estimated_duration": 180,
        "source": "builtin",
        "triggers": {
            "user_input": ["内存.*泄漏", "OOM", "内存.*满", "Heap.*满"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "pod_name": {"type": "string", "description": "Pod 名称"},
            },
            "required": ["namespace", "pod_name"],
        }),
        "workflow": json.dumps([
            {
                "id": "check_memory",
                "cli": "kubectl",
                "command": "top_pods",
                "params": {"namespace": "{namespace}"},
                "description": "检查 Pod 内存使用",
            },
            {
                "id": "jvm_dashboard",
                "cli": "arthas",
                "command": "dashboard",
                "params": {"n": 1},
                "description": "获取 JVM 内存指标",
            },
            {
                "id": "analyze_objects",
                "cli": "arthas",
                "command": "sc",
                "params": {"class_pattern": "*"},
                "description": "搜索类加载信息",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze",
                "input": ["check_memory", "jvm_dashboard", "analyze_objects"],
                "prompt": "分析内存泄漏风险，给出排查建议",
                "description": "AI 分析诊断结果",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 5. 线程死锁检测 ──────────────────────────────────────────
    {
        "name": "deadlock-diagnosis",
        "version": "1.0.0",
        "description": "线程死锁检测诊断流程",
        "category": "diagnosis",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 60,
        "source": "builtin",
        "triggers": {
            "user_input": ["死锁", "线程.*阻塞", "线程.*卡住", "BLOCKED"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "pod_name": {"type": "string", "description": "Pod 名称"},
            },
        }),
        "workflow": json.dumps([
            {
                "id": "check_threads",
                "cli": "arthas",
                "command": "thread",
                "params": {"top_n": 10},
                "description": "获取线程快照",
            },
            {
                "id": "detect_deadlock",
                "cli": "arthas",
                "command": "thread_deadlock",
                "params": {},
                "description": "检测死锁线程",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze",
                "input": ["check_threads", "detect_deadlock"],
                "prompt": "分析线程死锁原因，给出解决方案",
                "description": "AI 分析诊断结果",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 6. GC 问题排查 ──────────────────────────────────────────
    {
        "name": "gc-diagnosis",
        "version": "1.0.0",
        "description": "GC 问题诊断流程",
        "category": "diagnosis",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 90,
        "source": "builtin",
        "triggers": {
            "user_input": ["GC.*频繁", "Full GC", "GC.*暂停", "GC.*长"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "pod_name": {"type": "string", "description": "Pod 名称"},
            },
        }),
        "workflow": json.dumps([
            {
                "id": "jvm_dashboard",
                "cli": "arthas",
                "command": "dashboard",
                "params": {"n": 3},
                "description": "获取 JVM 指标（含 GC 统计）",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze",
                "input": ["jvm_dashboard"],
                "prompt": "分析 GC 问题，给出优化建议",
                "description": "AI 分析诊断结果",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 7. 类冲突排查 ──────────────────────────────────────────
    {
        "name": "class-conflict-diagnosis",
        "version": "1.0.0",
        "description": "类冲突诊断流程",
        "category": "diagnosis",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 60,
        "source": "builtin",
        "triggers": {
            "user_input": ["类.*冲突", "ClassNotFound", "ClassCastException", "类.*加载"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "class_pattern": {"type": "string", "description": "类名模式"},
            },
            "required": ["class_pattern"],
        }),
        "workflow": json.dumps([
            {
                "id": "search_class",
                "cli": "arthas",
                "command": "sc",
                "params": {"class_pattern": "{class_pattern}"},
                "description": "搜索类加载信息",
            },
            {
                "id": "decompile_class",
                "cli": "arthas",
                "command": "jad",
                "params": {"class_pattern": "{class_pattern}"},
                "description": "反编译类源码",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze",
                "input": ["search_class", "decompile_class"],
                "prompt": "分析类冲突原因，给出解决方案",
                "description": "AI 分析诊断结果",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 8. 连接问题排查 ──────────────────────────────────────────
    {
        "name": "connection-diagnosis",
        "version": "1.0.0",
        "description": "Pod 连接问题诊断流程",
        "category": "diagnosis",
        "level": 1,
        "risk_level": "low",
        "estimated_duration": 60,
        "source": "builtin",
        "triggers": {
            "user_input": ["连接.*失败", "连不上", "无法.*连接", "Connection.*refused"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "pod_name": {"type": "string", "description": "Pod 名称"},
            },
        }),
        "workflow": json.dumps([
            {
                "id": "check_pod",
                "cli": "kubectl",
                "command": "get_pods",
                "params": {"namespace": "{namespace}"},
                "description": "检查 Pod 状态",
            },
            {
                "id": "check_events",
                "cli": "kubectl",
                "command": "get_events",
                "params": {"namespace": "{namespace}"},
                "description": "获取 Pod 事件",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze",
                "input": ["check_pod", "check_events"],
                "prompt": "分析连接问题原因，给出解决方案",
                "description": "AI 分析诊断结果",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 9. 性能采样分析 ──────────────────────────────────────────
    {
        "name": "profiling-analysis",
        "version": "1.0.0",
        "description": "性能采样数据分析流程",
        "category": "diagnosis",
        "level": 2,
        "risk_level": "medium",
        "estimated_duration": 120,
        "source": "builtin",
        "triggers": {
            "user_input": ["性能.*分析", "采样.*分析", "CPU.*热点", "火焰图"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "analysis_type": {
                    "type": "string",
                    "enum": ["cpu", "memory", "thread"],
                    "description": "分析类型",
                },
            },
            "required": ["analysis_type"],
        }),
        "workflow": json.dumps([
            {
                "id": "jvm_dashboard",
                "cli": "arthas",
                "command": "dashboard",
                "params": {"n": 1},
                "description": "获取 JVM 基线指标",
            },
            {
                "id": "thread_snapshot",
                "cli": "arthas",
                "command": "thread",
                "params": {"top_n": 10},
                "description": "获取线程快照",
            },
            {
                "id": "llm_analysis",
                "cli": "llm",
                "command": "analyze_performance",
                "input": ["jvm_dashboard", "thread_snapshot"],
                "params": {"analysis_type": "{analysis_type}"},
                "prompt": "分析性能数据，给出优化建议",
                "description": "AI 分析性能数据",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },

    # ── 10. 综合健康检查 ──────────────────────────────────────────
    {
        "name": "health-check",
        "version": "1.0.0",
        "description": "Pod 综合健康检查流程",
        "category": "diagnosis",
        "level": 1,
        "risk_level": "low",
        "estimated_duration": 60,
        "source": "builtin",
        "triggers": {
            "user_input": ["健康.*检查", "Pod.*状态", "检查.*状态"],
        },
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Kubernetes namespace"},
                "pod_name": {"type": "string", "description": "Pod 名称（可选）"},
            },
            "required": ["namespace"],
        }),
        "workflow": json.dumps([
            {
                "id": "check_pods",
                "cli": "kubectl",
                "command": "get_pods",
                "params": {"namespace": "{namespace}"},
                "description": "获取 Pod 列表和状态",
            },
            {
                "id": "check_resources",
                "cli": "kubectl",
                "command": "top_pods",
                "params": {"namespace": "{namespace}"},
                "description": "获取 Pod 资源使用",
            },
            {
                "id": "check_events",
                "cli": "kubectl",
                "command": "get_events",
                "params": {"namespace": "{namespace}"},
                "description": "获取 Pod 事件",
            },
            {
                "id": "llm_summary",
                "cli": "llm",
                "command": "analyze",
                "input": ["check_pods", "check_resources", "check_events"],
                "prompt": "总结 Pod 健康状态，给出异常预警",
                "description": "AI 生成健康报告",
            },
        ]),
        "handler": "services.skill_workflow.execute_workflow",
    },
]
