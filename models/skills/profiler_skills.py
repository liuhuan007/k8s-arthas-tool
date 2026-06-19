#!/usr/bin/env python3
"""Profiler Skill Definitions for Skill Registry integration.

Defines the four profiler capabilities (CPU/JFR/ThreadDump/HeapDump) as
Skill Registry entries. These are imported into skill_registry on first run
alongside the existing BUILTIN_SKILLS in diagnosis_capabilities.py.

The handler_key field maps each skill to ProfilerSkillHandler for execution.
The handler field points to the bridge function that WorkflowEngine calls.

Author: Phase 7 T01
"""

import json

# Profiler skills follow the same schema as BUILTIN_SKILLS in
# backend/core/diagnosis_capabilities.py. They are inserted into the
# skill_registry table via _seed_profiler_skills().

PROFILER_SKILLS = [
    {
        "name": "cpu-profiler",
        "version": "1.0.0",
        "description": "使用 async-profiler 对 Java 进程进行 CPU 采样分析，生成火焰图",
        "category": "tool",
        "level": 2,
        "risk_level": "medium",
        "estimated_duration": 60,
        "source": "builtin",
        "arthas_command": "profiler start --event cpu --duration ${duration}",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "duration": {"type": "integer", "default": 30, "description": "采样时长(秒)"},
                "frequency": {"type": "integer", "default": 99, "description": "采样频率(Hz)"},
                "format": {"type": "string", "enum": ["html", "jfr", "collapsed"], "default": "html", "description": "输出格式"},
            },
        }),
        "handler": "services.profiler_skill_handler.execute_profiler_skill",
        "handler_key": "profiler.cpu",
    },
    {
        "name": "jfr-recording",
        "version": "1.0.0",
        "description": "使用 Java Flight Recorder 进行低开销持续记录，需要 JDK 8u262+ 或 JDK 11+",
        "category": "tool",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 120,
        "source": "builtin",
        "arthas_command": "jfr start -n arthas-jfr -s ${settings} -d ${duration}s",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "duration": {"type": "integer", "default": 60, "description": "录制时长(秒)"},
                "settings": {"type": "string", "default": "profile", "description": "JFR 配置(profile/default)"},
            },
        }),
        "handler": "services.profiler_skill_handler.execute_profiler_skill",
        "handler_key": "profiler.jfr",
    },
    {
        "name": "thread-dump",
        "version": "1.0.0",
        "description": "获取 Java 线程转储快照，包含线程状态、堆栈和死锁检测",
        "category": "quick",
        "level": 1,
        "risk_level": "low",
        "estimated_duration": 10,
        "source": "builtin",
        "arthas_command": "thread -n 9999",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "include_locks": {"type": "boolean", "default": True, "description": "是否包含锁信息"},
            },
        }),
        "handler": "services.profiler_skill_handler.execute_profiler_skill",
        "handler_key": "profiler.threaddump",
    },
    {
        "name": "heap-dump",
        "version": "1.0.0",
        "description": "获取 Java 堆转储快照，可用于内存泄漏分析（注意: 会触发 Full GC）",
        "category": "tool",
        "level": 2,
        "risk_level": "medium",
        "estimated_duration": 120,
        "source": "builtin",
        "arthas_command": "heapdump ${live_only_flag} /tmp/heapdump.hprof",
        "parameters_schema": json.dumps({
            "type": "object",
            "properties": {
                "live_only": {"type": "boolean", "default": True, "description": "仅导出存活对象(触发Full GC)"},
            },
        }),
        "handler": "services.profiler_skill_handler.execute_profiler_skill",
        "handler_key": "profiler.heapdump",
    },
]
