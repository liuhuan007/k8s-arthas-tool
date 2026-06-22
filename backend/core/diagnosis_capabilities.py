#!/usr/bin/env python3
"""诊断能力目录 - 预制能力清单与数据初始化"""
import json
import logging
from typing import List, Dict, Any

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# 预制能力清单(按层级组织)
# ═══════════════════════════════════════════════════════════════════════════════

QUICK_TOOLS = [
    {
        "name": "JVM Dashboard",
        "category": "quick",
        "level": 1,
        "description": "查看 JVM 运行概况:线程、内存、GC、运行时信息",
        "arthas_command": "dashboard -n 1",
        "risk_level": "low",
        "estimated_duration": 5,
        "related_capabilities": "[2, 3]",
    },
    {
        "name": "线程清单",
        "category": "quick",
        "level": 1,
        "description": "查看 CPU 占用 Top N 线程",
        "arthas_command": "thread -n 15",
        "risk_level": "low",
        "estimated_duration": 5,
        "related_capabilities": "[3, 8]",
    },
    {
        "name": "死锁检测",
        "category": "quick",
        "level": 1,
        "description": "检测线程死锁",
        "arthas_command": "thread -b",
        "risk_level": "low",
        "estimated_duration": 5,
        "related_capabilities": "[2, 8]",
    },
    {
        "name": "查看 VM 参数",
        "category": "quick",
        "level": 1,
        "description": "查看 JVM 启动参数和 VM options",
        "arthas_command": "vmoption",
        "risk_level": "low",
        "estimated_duration": 5,
    },
    {
        "name": "查看类信息",
        "category": "quick",
        "level": 1,
        "description": "查看类的详细信息(ClassLoader、代码来源等)",
        "arthas_command": "sc -d ${class}",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"}
        ]),
        "risk_level": "low",
        "estimated_duration": 5,
        "related_capabilities": "[6]",
    },
]

DIAGNOSIS_TOOLS = [
    {
        "name": "Trace 调用链分析",
        "category": "tool",
        "level": 2,
        "description": "追踪方法调用链路,定位慢方法",
        "arthas_command": "trace ${class} ${method} -n 10 '#cost > .5'",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
        "risk_level": "medium",
        "estimated_duration": 30,
        "related_capabilities": "[7, 11]",
    },
    {
        "name": "Watch 方法观测",
        "category": "tool",
        "level": 2,
        "description": "观测方法入参、返回值、异常信息",
        "arthas_command": "watch ${class} ${method} '{params,returnObj,throwExp}' -x 3 -n 5",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
        "risk_level": "medium",
        "estimated_duration": 20,
        "related_capabilities": "[6, 11]",
    },
    {
        "name": "Stack 调用栈定位",
        "category": "tool",
        "level": 2,
        "description": "查看方法调用栈,定位调用来源",
        "arthas_command": "stack ${class} ${method} -n 5",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
        "risk_level": "low",
        "estimated_duration": 15,
        "related_capabilities": "[6, 7]",
    },
    {
        "name": "Jad 反编译",
        "category": "tool",
        "level": 2,
        "description": "反编译查看运行时源码,确认线上代码版本",
        "arthas_command": "jad --source-only ${class}",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"}
        ]),
        "risk_level": "low",
        "estimated_duration": 10,
        "related_capabilities": "[10]",  # 热更新工作台
    },
    {
        "name": "Monitor 方法统计",
        "category": "tool",
        "level": 2,
        "description": "统计方法调用成功率、耗时",
        "arthas_command": "monitor ${class} ${method} -c 5",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
        "risk_level": "low",
        "estimated_duration": 30,
    },
]

SCENARIOS = [
    {
        "name": "接口响应慢诊断",
        "category": "scenario",
        "level": 3,
        "description": "通过 trace → watch → profiler 组合定位接口慢的根因",
        "steps_json": json.dumps([
            {"step": 1, "command": "trace ${controller} ${method} -n 10 '#cost > .5'", "desc": "定位慢方法"},
            {"step": 2, "command": "watch ${slow_class} ${slow_method} '{params,returnObj}' -n 3", "desc": "观察入参返回值"},
            {"step": 3, "command": "profiler start --event cpu --duration 30", "desc": "CPU 采样分析"}
        ]),
        "parameters_schema": json.dumps([
            {"name": "controller", "label": "Controller 类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
        "risk_level": "medium",
        "estimated_duration": 120,
        "related_capabilities": "[6, 7, 12]",
    },
    {
        "name": "CPU 100% 排查",
        "category": "scenario",
        "level": 3,
        "description": "通过 thread -n → profiler → 线程堆栈定位 CPU 飙升根因",
        "steps_json": json.dumps([
            {"step": 1, "command": "thread -n 5", "desc": "查看热线程"},
            {"step": 2, "command": "profiler start --event cpu --duration 60", "desc": "生成火焰图"},
            {"step": 3, "command": "thread ${tid}", "desc": "查看热点线程堆栈"}
        ]),
        "risk_level": "low",
        "estimated_duration": 90,
        "related_capabilities": "[2, 12]",
    },
    {
        "name": "OOM 内存泄漏排查",
        "category": "scenario",
        "level": 3,
        "description": "通过 dashboard → heapdump → GC 日志观察定位内存泄漏",
        "steps_json": json.dumps([
            {"step": 1, "command": "dashboard -n 1", "desc": "查看内存分布"},
            {"step": 2, "command": "heapdump /tmp/heapdump-${yyyyMMddHHmmss}.hprof", "desc": "生成堆快照"},
            {"step": 3, "command": "vmoption PrintGC true", "desc": "开启 GC 日志观察"}
        ]),
        "risk_level": "high",
        "estimated_duration": 180,
        "confirm_required": 1,
        "related_capabilities": "[1, 4]",
    },
]

AI_DIAGNOSIS = [
    {
        "name": "一键性能诊断",
        "category": "ai",
        "level": 4,
        "description": "自动采集 dashboard + thread + trace,通过规则引擎和 LLM 生成诊断报告",
        "handler": "performance_diagnose.run_diagnosis",
        "risk_level": "low",
        "estimated_duration": 60,
        "related_capabilities": "[6, 7, 12]",
    },
]


def _seed_capabilities(conn):
    """初始化诊断能力目录数据"""
    cursor = conn.cursor()
    
    # 检查是否已初始化
    cursor.execute("SELECT COUNT(*) FROM diagnosis_capabilities")
    if cursor.fetchone()[0] > 0:
        log.info("诊断能力目录已存在,跳过初始化")
        return
    
    log.info("开始初始化诊断能力目录...")
    
    all_capabilities = QUICK_TOOLS + DIAGNOSIS_TOOLS + SCENARIOS + AI_DIAGNOSIS
    
    for cap in all_capabilities:
        cursor.execute(
            '''
            INSERT INTO diagnosis_capabilities (
                name, category, level, description, arthas_command,
                parameters_schema, risk_level, estimated_duration,
                prerequisites, related_capabilities, github_issue,
                steps_json, handler, confirm_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                cap['name'],
                cap['category'],
                cap.get('level', 1),
                cap.get('description', ''),
                cap.get('arthas_command'),
                cap.get('parameters_schema', '{}'),
                cap.get('risk_level', 'low'),
                cap.get('estimated_duration', 10),
                cap.get('prerequisites', '[]'),
                cap.get('related_capabilities', '[]'),
                cap.get('github_issue'),
                cap.get('steps_json'),
                cap.get('handler'),
                cap.get('confirm_required', 0),
            )
        )
    
    log.info(f"诊断能力目录初始化完成,共插入 {len(all_capabilities)} 个能力")


def init_capabilities_table(conn):
    """创建诊断能力表并初始化数据"""
    cursor = conn.cursor()
    
    # 创建表(如果不存在)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS diagnosis_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            level INTEGER DEFAULT 1,
            description TEXT,
            arthas_command TEXT,
            parameters_schema TEXT DEFAULT '{}',
            risk_level TEXT DEFAULT 'low',
            estimated_duration INTEGER DEFAULT 10,
            prerequisites TEXT DEFAULT '[]',
            related_capabilities TEXT DEFAULT '[]',
            github_issue TEXT,
            steps_json TEXT,
            handler TEXT,
            confirm_required INTEGER DEFAULT 0,
            visibility TEXT DEFAULT 'public',  -- public/private/group
            version INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')
    
    # ✅ Phase 5: 权限模型 - 用户组关联表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS capability_user_groups (
            capability_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (capability_id, group_id),
            FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE
        )
    ''')
    
    # 初始化数据
    _seed_capabilities(conn)


# ═══════════════════════════════════════════════════════════════════════════════
# ✅ Phase 5: 权限模型
# ═══════════════════════════════════════════════════════════════════════════════

def check_capability_permission(capability_id, user_id, user_role='user'):
    """检查用户是否有权限执行诊断能力"""
    from models.db import db

    # 1. 管理员无限制
    if user_role == 'admin':
        return True

    capability = db.fetch_one(
        'SELECT id, visibility, created_by FROM diagnosis_capabilities WHERE id = ?',
        (capability_id,)
    )

    if not capability:
        return False

    # 2. 公开能力
    if capability['visibility'] == 'public':
        return True

    # 3. 私有能力
    if capability['visibility'] == 'private':
        return capability['created_by'] == user_id

    # 4. 用户组能力
    if capability['visibility'] == 'group':
        user_groups = db.fetch_all(
            'SELECT group_id FROM user_group_members WHERE user_id = ?',
            (user_id,)
        )
        group_ids = [g['group_id'] for g in user_groups]

        allowed_groups = db.fetch_all(
            'SELECT group_id FROM capability_user_groups WHERE capability_id = ?',
            (capability_id,)
        )
        allowed_group_ids = [g['group_id'] for g in allowed_groups]

        return any(gid in allowed_group_ids for gid in group_ids)

    return False


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 0: Skill Registry 预制数据
# ═══════════════════════════════════════════════════════════════════════════════

BUILTIN_SKILLS = [
    # 快捷工具（Level 1）
    {
        "name": "jvm-dashboard",
        "version": "1.0.0",
        "description": "查看 JVM 运行概况:线程、内存、GC、运行时信息",
        "category": "quick",
        "level": 1,
        "risk_level": "low",
        "estimated_duration": 5,
        "source": "builtin",
        "arthas_command": "dashboard -n 1",
    },
    {
        "name": "thread-list",
        "version": "1.0.0",
        "description": "查看 CPU 占用 Top N 线程",
        "category": "quick",
        "level": 1,
        "risk_level": "low",
        "estimated_duration": 5,
        "source": "builtin",
        "arthas_command": "thread -n 15",
    },
    {
        "name": "deadlock-detect",
        "version": "1.0.0",
        "description": "检测线程死锁",
        "category": "quick",
        "level": 1,
        "risk_level": "low",
        "estimated_duration": 5,
        "source": "builtin",
        "arthas_command": "thread -b",
    },
    {
        "name": "vmoption",
        "version": "1.0.0",
        "description": "查看 JVM 启动参数和 VM options",
        "category": "quick",
        "level": 1,
        "risk_level": "low",
        "estimated_duration": 5,
        "source": "builtin",
        "arthas_command": "vmoption",
    },
    {
        "name": "class-info",
        "version": "1.0.0",
        "description": "查看类的详细信息(ClassLoader、代码来源等)",
        "category": "quick",
        "level": 1,
        "risk_level": "low",
        "estimated_duration": 5,
        "source": "builtin",
        "arthas_command": "sc -d ${class}",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"}
        ]),
    },
    # 诊断模板（Level 2）
    {
        "name": "trace-analysis",
        "version": "1.0.0",
        "description": "追踪方法调用链路,定位慢方法",
        "category": "tool",
        "level": 2,
        "risk_level": "medium",
        "estimated_duration": 30,
        "source": "builtin",
        "arthas_command": "trace ${class} ${method} -n 10 '#cost > .5'",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
    },
    {
        "name": "watch-method",
        "version": "1.0.0",
        "description": "观测方法入参、返回值、异常信息",
        "category": "tool",
        "level": 2,
        "risk_level": "medium",
        "estimated_duration": 20,
        "source": "builtin",
        "arthas_command": "watch ${class} ${method} '{params,returnObj,throwExp}' -x 3 -n 5",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
    },
    {
        "name": "stack-trace",
        "version": "1.0.0",
        "description": "查看方法调用栈,定位调用来源",
        "category": "tool",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 15,
        "source": "builtin",
        "arthas_command": "stack ${class} ${method} -n 5",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
    },
    {
        "name": "jad-decompile",
        "version": "1.0.0",
        "description": "反编译查看运行时源码,确认线上代码版本",
        "category": "tool",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 10,
        "source": "builtin",
        "arthas_command": "jad --source-only ${class}",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"}
        ]),
    },
    {
        "name": "monitor-method",
        "version": "1.0.0",
        "description": "统计方法调用成功率、耗时",
        "category": "tool",
        "level": 2,
        "risk_level": "low",
        "estimated_duration": 30,
        "source": "builtin",
        "arthas_command": "monitor ${class} ${method} -c 5",
        "parameters_schema": json.dumps([
            {"name": "class", "label": "类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
    },
    # 场景方案（Level 3）
    {
        "name": "slow-api-diagnosis",
        "version": "1.0.0",
        "description": "通过 trace → watch → profiler 组合定位接口慢的根因",
        "category": "scenario",
        "level": 3,
        "risk_level": "medium",
        "estimated_duration": 120,
        "source": "builtin",
        "dsl": json.dumps({
            "steps": [
                {"step": 1, "command": "trace ${controller} ${method} -n 10 '#cost > .5'", "desc": "定位慢方法"},
                {"step": 2, "command": "watch ${slow_class} ${slow_method} '{params,returnObj}' -n 3", "desc": "观察入参返回值"},
                {"step": 3, "command": "profiler start --event cpu --duration 30", "desc": "CPU 采样分析"}
            ]
        }),
        "parameters_schema": json.dumps([
            {"name": "controller", "label": "Controller 类名", "required": True, "pattern": "^[A-Za-z_$][\\w.$*]*$"},
            {"name": "method", "label": "方法名", "default": "*", "pattern": "^[\\w.*]*$"}
        ]),
    },
    {
        "name": "cpu-high-diagnosis",
        "version": "1.0.0",
        "description": "通过 thread -n → profiler → 线程堆栈定位 CPU 飙升根因",
        "category": "scenario",
        "level": 3,
        "risk_level": "low",
        "estimated_duration": 90,
        "source": "builtin",
        "dsl": json.dumps({
            "steps": [
                {"step": 1, "command": "thread -n 5", "desc": "查看热线程"},
                {"step": 2, "command": "profiler start --event cpu --duration 60", "desc": "生成火焰图"},
                {"step": 3, "command": "thread ${tid}", "desc": "查看热点线程堆栈"}
            ]
        }),
    },
    {
        "name": "oom-diagnosis",
        "version": "1.0.0",
        "description": "通过 dashboard → heapdump → GC 日志观察定位内存泄漏",
        "category": "scenario",
        "level": 3,
        "risk_level": "high",
        "estimated_duration": 180,
        "source": "builtin",
        "dsl": json.dumps({
            "steps": [
                {"step": 1, "command": "dashboard -n 1", "desc": "查看内存分布"},
                {"step": 2, "command": "heapdump /tmp/heapdump.hprof", "desc": "生成堆快照"},
                {"step": 3, "command": "vmoption PrintGC true", "desc": "开启 GC 日志观察"}
            ]
        }),
    },
    # AI 诊断（Level 4）
    {
        "name": "auto-diagnosis",
        "version": "1.0.0",
        "description": "自动采集 dashboard + thread + trace,通过规则引擎和 LLM 生成诊断报告",
        "category": "ai",
        "level": 4,
        "risk_level": "low",
        "estimated_duration": 60,
        "source": "builtin",
        "handler": "performance_diagnose.run_diagnosis",
    },
]


def _seed_skills(cursor, skills, source="builtin"):
    """通用 skill 种子函数"""
    inserted = 0
    for skill in skills:
        cursor.execute(
            "SELECT id FROM skill_registry WHERE name = ?", (skill["name"],)
        )
        if cursor.fetchone() is not None:
            continue
        cursor.execute(
            '''
            INSERT INTO skill_registry (
                name, version, description, category, level, risk_level,
                estimated_duration, source, status, dsl, parameters_schema,
                llm_prompt, arthas_command, handler, created_by, marketplace_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                skill["name"],
                skill["version"],
                skill.get("description", ""),
                skill["category"],
                skill.get("level", 1),
                skill.get("risk_level", "low"),
                skill.get("estimated_duration", 10),
                source,
                "published",
                skill.get("dsl"),
                skill.get("parameters_schema", "{}"),
                skill.get("llm_prompt"),
                skill.get("arthas_command"),
                skill.get("handler"),
                None,
                None,
            )
        )
        inserted += 1
    return inserted


def init_skill_registry(conn):
    """初始化 skill_registry 表"""
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM skill_registry")
    if cursor.fetchone()[0] == 0:
        n = _seed_skills(cursor, BUILTIN_SKILLS, "builtin")
        log.info("Builtin skills seeded: %d", n)

    from models.skills.profiler_skills import PROFILER_SKILLS
    n = _seed_skills(cursor, PROFILER_SKILLS, "builtin")
    if n:
        log.info("Profiler skills 已插入 skill_registry: %d 个", n)

    from models.skills.ai_skills import AI_SKILLS
    n = _seed_skills(cursor, AI_SKILLS, "builtin")
    if n:
        log.info("AI skills 已插入 skill_registry: %d 个", n)

    from models.skills.mcp_skills import MCP_SKILLS
    n = _seed_skills(cursor, MCP_SKILLS, "builtin")
    if n:
        log.info("MCP skills 已插入 skill_registry: %d 个", n)
