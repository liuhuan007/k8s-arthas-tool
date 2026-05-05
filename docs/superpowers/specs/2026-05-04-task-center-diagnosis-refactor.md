# 任务中心重构设计文档

> 全新架构设计，支持 Arthas 在线诊断能力

**文档版本**: v2.0  
**创建日期**: 2026-05-04  
**状态**: 设计中  
**关联文档**: [Arthas K8s 平台系统设计](./2026-05-02-arthas-k8s-platform-system-design.md)

---

## 1. 设计目标

### 1.1 核心诉求

- **以在线诊断为核心**：利用 Arthas 强大的性能分析工具（trace/watch/profiler/dashboard）进行问题诊断
- **全新架构设计**：采用 Capability（能力）+ Extension（扩展）设计模式，不兼容旧系统
- **即时诊断直接执行**：用户选择能力 + 填写参数 → 直接执行，无需创建任务定义
- **定时任务保留定义**：定时任务需要保存执行配置，使用 `task_definitions`
- **统一日志表**：所有执行日志统一使用 `task_logs`，通过 `execution_mode` 区分
- **分层能力组织**：快捷工具 → 诊断模板 → 场景方案 → 智能诊断

### 1.2 解决的问题

| 问题 | 现状 | 重构后 |
|------|------|--------|
| 工具箱职责混乱 | 既管工具包分发，又展示用户案例 | 工具包管理 + 诊断能力分层 |
| 预制模板来源不明 | 15 个案例硬编码在 `_USER_CASE_CAPABILITIES` | 结构化存储于 `diagnosis_capabilities`，管理员后台配置 |
| 诊断能力割裂 | `performance_diagnose.py` 未被任务中心复用 | 通过 `handler` 字段统一调用 |
| 任务中心能力弱 | 只能执行 Python/Shell 脚本 | 支持 Arthas HTTP API 调用 |
| 执行流程冗余 | 需要创建 task_definition 才能执行 | 即时诊断直接执行，跳过 task_definition |

### 1.3 执行模式设计

系统支持两种执行模式：

**即时诊断（方案 A）**：
```
diagnosis_capabilities (能力模板)
    ↓ 用户选择 + 填写参数
task_logs (执行日志，execution_mode='immediate')
    ↓ 1:N
arthas_command_logs (命令日志)
```

**定时任务（方案 C）**：
```
task_definitions (任务定义，保存执行配置)
    ↓ 定时触发
task_logs (执行日志，execution_mode='scheduled')
    ↓ 1:N
arthas_command_logs (命令日志)
```

**通用任务（脚本/Pod/Node）**：
```
task_definitions (任务定义)
    ↓ 手动/定时触发
task_logs (执行日志，execution_mode='manual' | 'scheduled')
```

---

## 2. 数据模型设计

### 2.1 核心表清单

系统采用 **1 张核心表 + 4 张扩展表** 的架构：

| 表名 | 用途 | 核心字段 | 说明 |
|------|------|---------|------|
| **diagnosis_capabilities** | 诊断能力元数据 | name, type, category, level, parameters_schema | 核心表，统一管理 |
| **script_templates** | 脚本模板扩展 | capability_id, runtime, script_body | 扩展表 1（复用现有表） |
| **arthas_command_templates** | Arthas 命令模板扩展 | capability_id, arthas_command | 扩展表 2（新建） |
| **diagnosis_scenario_steps** | 场景方案步骤扩展 | capability_id, step_order, command | 扩展表 3（新建） |
| **ai_diagnosis_handlers** | AI 诊断处理器扩展 | capability_id, handler | 扩展表 4（新建） |

### 2.2 核心表结构

#### diagnosis_capabilities（诊断能力元数据表）

```sql
CREATE TABLE diagnosis_capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,           -- 能力名称，如 "CPU 性能分析"
    type TEXT NOT NULL,                  -- script | arthas_command | diagnosis_scenario | ai_diagnosis
    category TEXT NOT NULL,              -- quick | tool | scenario | ai
    level INTEGER NOT NULL DEFAULT 1,    -- 1=快捷工具 2=诊断模板 3=场景方案 4=智能诊断
    risk_level TEXT DEFAULT 'low',       -- low | medium | high
    parameters_schema TEXT DEFAULT '{}', -- JSON 数组，定义参数格式和校验规则
    description TEXT,                    -- 能力描述
    estimated_duration INTEGER DEFAULT 10, -- 预计执行时长（秒）
    created_by INTEGER,                  -- 创建人
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- 索引
CREATE INDEX idx_diag_caps_type ON diagnosis_capabilities(type);
CREATE INDEX idx_diag_caps_category_level ON diagnosis_capabilities(category, level);
```

### 2.3 扩展表结构

#### script_templates（脚本模板扩展 - 复用现有表）

```sql
-- 原有字段保留：runtime, script_body, parameters_schema, tool_package_id
-- 新增关联字段
ALTER TABLE script_templates ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id);

-- 说明：
-- 1. capability_id 为 NULL 时，表示独立脚本（不关联诊断能力）
-- 2. capability_id 不为 NULL 时，type 必须为 'script'
```

#### arthas_command_templates（Arthas 命令模板扩展）

```sql
CREATE TABLE arthas_command_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL UNIQUE,   -- 一对一关联
    arthas_command TEXT NOT NULL,            -- Arthas 命令模板，支持 ${param} 占位符
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE
);
```

#### diagnosis_scenario_steps（场景方案步骤扩展）

```sql
CREATE TABLE diagnosis_scenario_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL,        -- 一对多关联
    step_order INTEGER NOT NULL,           -- 步骤顺序，从 1 开始
    command TEXT NOT NULL,                 -- Arthas 命令模板
    desc TEXT,                             -- 步骤说明
    timeout_ms INTEGER DEFAULT 60000,      -- 超时时间（毫秒）
    fail_fast INTEGER DEFAULT 1,           -- 1=失败后停止，0=继续执行
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE,
    UNIQUE(capability_id, step_order)      -- 同一能力下步骤顺序唯一
);
```

#### ai_diagnosis_handlers（AI 诊断处理器扩展）

```sql
CREATE TABLE ai_diagnosis_handlers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL UNIQUE,   -- 一对一关联
    handler TEXT NOT NULL,                   -- 处理器路径，如 "performance_diagnose.run_diagnosis"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE,
    CHECK(handler LIKE 'performance_diagnose.%')  -- 限制模块路径
);
```

```
diagnosis_capabilities（核心表）
├── 统一元数据：name, type, category, level, risk_level, parameters_schema
└── 通过 type 区分：script | arthas_command | diagnosis_scenario | ai_diagnosis

script_templates（扩展表 1 - 复用现有表）
├── capability_id → diagnosis_capabilities.id
└── 专属字段：runtime, script_body, tool_package_id

arthas_command_templates（扩展表 2 - 新建）
├── capability_id → diagnosis_capabilities.id
└── 专属字段：arthas_command

diagnosis_scenario_steps（扩展表 3 - 新建）
├── capability_id → diagnosis_capabilities.id
└── 专属字段：step_order, command, desc, timeout_ms, fail_fast

ai_diagnosis_handlers（扩展表 4 - 新建）
├── capability_id → diagnosis_capabilities.id
└── 专属字段：handler
```

### 3.2 数据库迁移脚本

```sql
-- ═══════════════════════════════════════════════════════════
-- 核心表：diagnosis_capabilities（诊断能力元数据）
-- ═══════════════════════════════════════════════════════════

CREATE TABLE diagnosis_capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,           -- 能力名称，如 "CPU 性能分析"
    type TEXT NOT NULL,                  -- script | arthas_command | diagnosis_scenario | ai_diagnosis
    category TEXT NOT NULL,              -- quick | tool | scenario | ai
    level INTEGER NOT NULL DEFAULT 1,    -- 1=快捷工具 2=诊断模板 3=场景方案 4=智能诊断
    risk_level TEXT DEFAULT 'low',       -- low | medium | high
    parameters_schema TEXT DEFAULT '{}', -- JSON 数组，定义参数格式和校验规则
    description TEXT,                    -- 能力描述
    estimated_duration INTEGER DEFAULT 10, -- 预计执行时长（秒）
    created_by INTEGER,                  -- 创建人
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

-- 索引
CREATE INDEX idx_diag_caps_type ON diagnosis_capabilities(type);
CREATE INDEX idx_diag_caps_category_level ON diagnosis_capabilities(category, level);

-- ═══════════════════════════════════════════════════════════
-- 统一执行日志表：task_logs（重命名原 task_runs）
-- ═══════════════════════════════════════════════════════════

-- 重命名表
ALTER TABLE task_runs RENAME TO task_logs;

-- 新增字段
ALTER TABLE task_logs ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id);
ALTER TABLE task_logs ADD COLUMN execution_type TEXT;  -- diagnosis | script | pod_exec | node_exec

-- 修改字段约束
-- task_id 改为 NULLABLE（即时诊断时为空）
-- execution_mode 改为 immediate | scheduled | manual

-- 索引
CREATE INDEX idx_task_logs_capability_id ON task_logs(capability_id);
CREATE INDEX idx_task_logs_execution_mode ON task_logs(execution_mode);

-- 说明：
-- 1. 即时诊断：task_id=NULL, capability_id≠NULL, execution_mode='immediate'
-- 2. 定时任务：task_id≠NULL, capability_id 可选, execution_mode='scheduled'
-- 3. 通用任务：task_id≠NULL, capability_id=NULL, execution_mode='manual'|'scheduled'
```
-- ═══════════════════════════════════════════════════════════
-- 扩展表 1：script_templates（脚本模板 - 复用现有表）
-- ═══════════════════════════════════════════════════════════

-- 新增关联字段
ALTER TABLE script_templates ADD COLUMN capability_id INTEGER REFERENCES diagnosis_capabilities(id);

-- 说明：
-- 1. 原有字段保留：runtime, script_body, parameters_schema, tool_package_id
-- 2. capability_id 为 NULL 时，表示独立脚本（不关联诊断能力）
-- 3. capability_id 不为 NULL 时，type 必须为 'script'

-- ═══════════════════════════════════════════════════════════
-- 扩展表 2：arthas_command_templates（Arthas 命令模板）
-- ═══════════════════════════════════════════════════════════

CREATE TABLE arthas_command_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL UNIQUE,   -- 一对一关联
    arthas_command TEXT NOT NULL,            -- Arthas 命令模板，支持 ${param} 占位符
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE
);

-- 示例数据：
-- INSERT INTO diagnosis_capabilities (name, type, category, level, risk_level, parameters_schema) 
-- VALUES ('Trace 方法调用', 'arthas_command', 'tool', 2, 'low', '[{"name":"class","required":true}]');
-- INSERT INTO arthas_command_templates (capability_id, arthas_command) 
-- VALUES (last_insert_rowid(), 'trace ${class} ${method} -n 10 ''#cost > .5''');

-- ═══════════════════════════════════════════════════════════
-- 扩展表 3：diagnosis_scenario_steps（场景方案步骤）
-- ═══════════════════════════════════════════════════════════

CREATE TABLE diagnosis_scenario_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL,        -- 一对多关联
    step_order INTEGER NOT NULL,           -- 步骤顺序，从 1 开始
    command TEXT NOT NULL,                 -- Arthas 命令模板
    desc TEXT,                             -- 步骤说明
    timeout_ms INTEGER DEFAULT 60000,      -- 超时时间（毫秒）
    fail_fast INTEGER DEFAULT 1,           -- 1=失败后停止，0=继续执行
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE,
    UNIQUE(capability_id, step_order)      -- 同一能力下步骤顺序唯一
);

-- 示例数据：
-- INSERT INTO diagnosis_capabilities (name, type, category, level, risk_level) 
-- VALUES ('CPU 性能分析场景', 'diagnosis_scenario', 'scenario', 3, 'medium');
-- INSERT INTO diagnosis_scenario_steps (capability_id, step_order, command, desc) 
-- VALUES 
--   (last_insert_rowid(), 1, 'dashboard -n 1', '查看 JVM 整体状态'),
--   (last_insert_rowid(), 2, 'thread -n 10', '查看最忙的 10 个线程'),
--   (last_insert_rowid(), 3, 'profiler start --event cpu', '开始 CPU 采样');

-- ═══════════════════════════════════════════════════════════
-- 扩展表 4：ai_diagnosis_handlers（AI 诊断处理器）
-- ═══════════════════════════════════════════════════════════

CREATE TABLE ai_diagnosis_handlers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL UNIQUE,   -- 一对一关联
    handler TEXT NOT NULL,                   -- 处理器路径，如 "performance_diagnose.run_diagnosis"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id) ON DELETE CASCADE,
    CHECK(handler LIKE 'performance_diagnose.%')  -- 限制模块路径
);

-- 示例数据：
-- INSERT INTO diagnosis_capabilities (name, type, category, level, risk_level) 
-- VALUES ('CPU 性能瓶颈分析', 'ai_diagnosis', 'ai', 4, 'low');
-- INSERT INTO ai_diagnosis_handlers (capability_id, handler) 
-- VALUES (last_insert_rowid(), 'performance_diagnose.run_cpu_diagnosis');
```

### 3.3 表关系图

```
diagnosis_capabilities (核心表)
│
├── type='script' ──────→ script_templates (扩展表 1)
│                         └── capability_id → id
│
├── type='arthas_command' ─→ arthas_command_templates (扩展表 2)
│                            └── capability_id → id (一对一)
│
├── type='diagnosis_scenario' ─→ diagnosis_scenario_steps (扩展表 3)
│                                 └── capability_id → id (一对多)
│
└── type='ai_diagnosis' ────→ ai_diagnosis_handlers (扩展表 4)
                               └── capability_id → id (一对一)


task_definitions (任务定义)
└── capability_id → diagnosis_capabilities.id

task_runs (任务执行记录)
└── task_id → task_definitions.id
```

### 3.4 数据初始化策略

```python
# api/task_center.py

# 说明：
# 1. 所有诊断能力通过管理员后台配置（diagnosis_capabilities 表）
# 2. 本阶段只搭建框架和流程，不预制数据
# 3. 后续可根据实际诊断场景，逐步添加场景化解决方案

def init_diagnosis_capabilities():
    """初始化诊断能力表结构"""
    # 数据库迁移脚本已在 3.2 节定义
    pass
```

#### 新增预制诊断能力

```python
# 说明：以下为示例数据结构，实际由管理员在后台配置
# 本阶段不预制数据，只定义结构规范

# ═══════════════════════════════════════════════════════════
# 第一层：快捷工具（level=1, category=quick）
# ═══════════════════════════════════════════════════════════

QUICK_TOOLS_EXAMPLE = [
    {
        'capability': {
            'name': 'JVM Dashboard',
            'type': 'arthas_command',
            'category': 'quick',
            'level': 1,
            'risk_level': 'low',
            'estimated_duration': 5,
            'description': '查看 JVM 运行概况：线程、内存、GC、运行时信息',
        },
        'extension': {
            'arthas_command': 'dashboard -n 1',
        }
    },
    {
        'capability': {
            'name': '线程快照',
            'type': 'arthas_command',
            'category': 'quick',
            'level': 1,
            'risk_level': 'low',
            'estimated_duration': 10,
            'description': '查看最忙的前 N 个线程及堆栈',
        },
        'extension': {
            'arthas_command': 'thread -n 5',
        }
    },
    # ... 其他快捷工具由管理员配置
]

# ═══════════════════════════════════════════════════════════
# 第二层：诊断模板（level=2, category=tool）
# ═══════════════════════════════════════════════════════════

DIAGNOSIS_TOOLS_EXAMPLE = [
    {
        'capability': {
            'name': 'Trace 调用链分析',
            'type': 'arthas_command',
            'category': 'tool',
            'level': 2,
            'risk_level': 'medium',
            'estimated_duration': 30,
            'description': '追踪方法调用链路，定位慢方法',
            'parameters_schema': json.dumps([
                {'name': 'class', 'label': '类名', 'required': True, 'pattern': '^[A-Za-z_$][\\w.$*]*$'},
                {'name': 'method', 'label': '方法名', 'default': '*', 'pattern': '^[\\w.*]*$'}
            ]),
        },
        'extension': {
            'arthas_command': "trace ${class} ${method} -n 10 '#cost > .5'",
        }
    },
    # ... 其他诊断模板由管理员配置
]

# ═══════════════════════════════════════════════════════════
# 第三层：场景方案（level=3, category=scenario）
# ═══════════════════════════════════════════════════════════

SCENARIOS_EXAMPLE = [
    {
        'capability': {
            'name': '接口响应慢诊断',
            'type': 'diagnosis_scenario',
            'category': 'scenario',
            'level': 3,
            'risk_level': 'medium',
            'estimated_duration': 120,
            'description': '通过 trace → watch → profiler 组合定位接口慢的根因',
            'parameters_schema': json.dumps([
                {'name': 'controller', 'label': 'Controller 类名', 'required': True},
                {'name': 'method', 'label': '方法名', 'default': '*'}
            ]),
        },
        'extension': {
            'steps': [
                {'step_order': 1, 'command': "trace ${controller} ${method} -n 10 '#cost > .5'", 'desc': '定位慢方法'},
                {'step_order': 2, 'command': "watch ${slow_class} ${slow_method} '{params,returnObj}' -n 3", 'desc': '观察入参返回值'},
                {'step_order': 3, 'command': 'profiler start --event cpu --duration 30', 'desc': 'CPU 采样分析'}
            ]
        }
    },
    # ... 其他场景方案由管理员配置
]

# ═══════════════════════════════════════════════════════════
# 第四层：智能诊断（level=4, category=ai）
# ═══════════════════════════════════════════════════════════

AI_DIAGNOSIS_EXAMPLE = [
    {
        'capability': {
            'name': '一键性能诊断',
            'type': 'ai_diagnosis',
            'category': 'ai',
            'level': 4,
            'risk_level': 'low',
            'estimated_duration': 60,
            'description': '自动采集 dashboard + thread + trace，通过规则引擎和 LLM 生成诊断报告',
        },
        'extension': {
            'handler': 'performance_diagnose.run_diagnosis',
        }
    },
]
```

---

## 4. 后端架构设计

### 4.1 统一 Arthas 命令执行器

**问题**：当前系统有 4 个地方在执行 Arthas 命令，逻辑重复：
- `server.py` - 命令控制台
- `api/performance_diagnose.py` - 性能诊断
- `api/ai_chat.py` - AI 助手
- `api/task_center.py` - 任务中心（新增）

**解决方案**：创建 `backend/core/arthas_executor.py` 统一执行器

```python
# backend/core/arthas_executor.py

class ArthasCommandExecutor:
    """统一的 Arthas 命令执行器"""
    
    @staticmethod
    def execute(connection, command, timeout_ms=None, skip_audit=False, skip_history=False, confirmed=False):
        """执行单条 Arthas 命令
        
        功能：
        1. 高危命令检查（redefine/heapdump/profiler 等）
        2. 自动超时配置（根据命令类型）
        3. 执行命令（调用 http_client.exec_once）
        4. 脱敏处理（SafetyService）
        5. 记录命令历史（arthas_commands 表）
        6. 记录审计日志（audit_logs 表）
        """
        pass
    
    @staticmethod
    def execute_batch(connection, commands, timeout_ms=None, fail_fast=True):
        """批量执行 Arthas 命令（场景方案使用）
        
        功能：
        1. 逐步执行命令列表
        2. 支持 fail_fast（某步失败后停止）
        3. 记录总体审计日志
        """
        pass
```

**命令分类与超时配置**：

```python
_COMMAND_TIMEOUT_CONFIG = {
    # 快捷查询类（5-15秒）
    'dashboard': 15000,
    'thread': 30000,
    
    # 方法诊断类（30-60秒）
    'trace': 60000,
    'watch': 60000,
    
    # 采样与Dump（60-120秒）
    'profiler': 120000,
    'heapdump': 120000,
}

_HIGH_RISK_COMMANDS = {
    'redefine',      # 类重新定义
    'retransform',   # 类热替换
    'heapdump',      # 堆Dump
    'profiler',      # 性能采样
    'logger',        # 日志级别修改
}
```

**改造现有模块**：

```python
# server.py - 命令控制台（改造前）
result = conn.http_client.exec_once(command)
_save_arthas_command(conn_id, command, ...)

# server.py - 命令控制台（改造后）
from backend.core.arthas_executor import ArthasCommandExecutor
result = ArthasCommandExecutor.execute(conn, command)

# api/performance_diagnose.py（改造前）
dash_resp = connection.http_client.exec_once("dashboard -n 1")
thread_resp = connection.http_client.exec_once("thread -n 15")

# api/performance_diagnose.py（改造后）
dash_resp = ArthasCommandExecutor.execute(connection, "dashboard -n 1")
thread_resp = ArthasCommandExecutor.execute(connection, "thread -n 15")
```

**优势**：
- ✅ 统一执行逻辑，一处修改全局生效
- ✅ 统一脱敏、审计、命令历史记录
- ✅ 任务中心直接复用，不重复实现
- ✅ 自动超时配置，无需手动指定

### 4.2 任务执行引擎

```python
# api/task_center.py

def execute_task_run(task_def, connection=None):
    """执行诊断任务"""
    
    # 1. 获取能力定义
    capability_id = task_def.get('capability_id')
    if not capability_id:
        raise ValueError('任务未关联能力定义')
    
    capability = db.fetch_one('SELECT * FROM diagnosis_capabilities WHERE id = ?', (capability_id,))
    if not capability:
        raise ValueError('能力定义不存在')
    
    # 2. 根据 type 加载扩展数据
    capability_type = capability['type']
    extension = load_extension(capability_type, capability_id)
    
    # 3. 根据 type 选择执行器
    if capability_type == 'script':
        return execute_script(extension, task_def)
    
    elif capability_type == 'arthas_command':
        return execute_arthas_command(capability, extension, task_def, connection)
    
    elif capability_type == 'diagnosis_scenario':
        return execute_scenario(capability, extension, task_def, connection)
    
    elif capability_type == 'ai_diagnosis':
        return execute_ai_diagnosis(capability, extension, task_def, connection)


def load_extension(capability_type: str, capability_id: int) -> dict:
    """根据能力类型加载扩展数据"""
    
    if capability_type == 'script':
        return db.fetch_one('SELECT * FROM script_templates WHERE capability_id = ?', (capability_id,))
    
    elif capability_type == 'arthas_command':
        return db.fetch_one('SELECT * FROM arthas_command_templates WHERE capability_id = ?', (capability_id,))
    
    elif capability_type == 'diagnosis_scenario':
        steps = db.fetch_all(
            'SELECT * FROM diagnosis_scenario_steps WHERE capability_id = ? ORDER BY step_order',
            (capability_id,)
        )
        return {'steps': steps}
    
    elif capability_type == 'ai_diagnosis':
        return db.fetch_one('SELECT * FROM ai_diagnosis_handlers WHERE capability_id = ?', (capability_id,))
    
    else:
        raise ValueError(f"不支持的能力类型: {capability_type}")
```

### 4.3 Arthas 命令执行器（复用统一执行器）

**说明**：本节描述如何在任务中心复用已实现的 `ArthasCommandExecutor`（见 4.1 节）。

```python
# api/task_center.py

from backend.core.arthas_executor import ArthasCommandExecutor

def execute_arthas_command(capability, extension, task_def, connection):
    """执行 Arthas 诊断命令（level 1/2）
    
    职责：
    1. 参数校验（基于 capability.parameters_schema）
    2. 命令构建（参数替换）
    3. 调用统一执行器（ArthasCommandExecutor.execute）
    4. 记录任务执行结果（task_runs 表）
    """
    
    # 1. 参数校验
    params = json.loads(task_def.get('params_json', '{}'))
    error = validate_parameters(capability.get('parameters_schema'), params)
    if error:
        raise ValueError(error)
    
    # 2. 构建命令
    command = build_command(extension['arthas_command'], params)
    
    # 3. 调用统一执行器 ✅（复用 4.1 节的实现）
    result = ArthasCommandExecutor.execute(
        connection,
        command,
        confirmed=task_def.get('confirmed', False),
        skip_audit=False,  # 统一执行器会自动记录审计日志
        skip_history=False,  # 统一执行器会自动记录命令历史
    )
    
    # 4. 检查是否需要二次确认
    if result.get('state') == 'REQUIRE_CONFIRM':
        return {
            'require_confirm': True,
            'message': result.get('message'),
            'command': command,
            'risk_level': result.get('risk_level'),
        }
    
    # 5. 记录到 task_runs
    run_id = str(uuid4())
    db.insert('task_runs', {
        'id': run_id,
        'task_id': task_def['id'],
        'user_id': task_def.get('created_by'),
        'status': 'success' if result.get('state') in ('SUCCEEDED', 'succeeded') else 'failed',
        'execution_mode': 'connection',
        'target_json': json.dumps({
            'connection_id': connection.id,
            'cluster_name': connection.cluster_name,
            'namespace': connection.namespace,
            'pod_name': connection.pod_name,
        }),
        'stdout': json.dumps(result, ensure_ascii=False),
        'duration_ms': result.get('duration_ms', 0),
        'started_at': datetime.now(),
        'finished_at': datetime.now(),
    })
    
    return {'ok': True, 'output': result, 'run_id': run_id}
```

**关键改进**：
- ✅ 复用 `ArthasCommandExecutor.execute()`，不重复实现命令执行逻辑
- ✅ 自动脱敏、审计、命令历史记录（由统一执行器处理）
- ✅ 自动超时配置（根据命令类型）
- ✅ 高危命令二次确认（统一执行器返回 `REQUIRE_CONFIRM` 状态）

### 4.4 场景方案执行器（复用统一批量执行器）

**说明**：本节描述如何在任务中心复用已实现的 `ArthasCommandExecutor.execute_batch()`（见 4.1 节）。

```python
# api/task_center.py

from backend.core.arthas_executor import ArthasCommandExecutor

def execute_scenario(capability, extension, task_def, connection):
    """执行场景方案（level 3 - 多步骤）
    
    职责：
    1. 参数校验（基于 capability.parameters_schema）
    2. 解析步骤（extension.steps）
    3. 构建命令列表
    4. 调用统一批量执行器（ArthasCommandExecutor.execute_batch）
    5. 记录任务执行结果（task_runs 表）
    """
    
    # 1. 参数校验
    params = json.loads(task_def.get('params_json', '{}'))
    error = validate_parameters(capability.get('parameters_schema'), params)
    if error:
        raise ValueError(error)
    
    # 2. 解析步骤
    steps = extension.get('steps', [])
    if not steps:
        raise ValueError('场景方案未配置步骤')
    
    # 3. 构建命令列表
    commands = []
    for step in steps:
        command = build_command(step['command'], params)
        commands.append({
            'command': command,
            'desc': step.get('desc', ''),
            'timeout_ms': step.get('timeout_ms'),
        })
    
    # 4. 调用统一批量执行器 ✅（复用 4.1 节的实现）
    step_results = ArthasCommandExecutor.execute_batch(
        connection,
        commands,
        fail_fast=True,  # 默认失败后停止
    )
    
    # 5. 判断整体状态
    all_success = all(r['success'] for r in step_results)
    status = 'success' if all_success else 'partial'
    
    # 6. 记录到 task_runs
    run_id = str(uuid4())
    db.insert('task_runs', {
        'id': run_id,
        'task_id': task_def['id'],
        'user_id': task_def.get('created_by'),
        'status': status,
        'execution_mode': 'connection',
        'target_json': json.dumps({
            'connection_id': connection.id,
            'cluster_name': connection.cluster_name,
        }),
        'stdout': json.dumps(step_results, ensure_ascii=False),
        'result_json': json.dumps({
            'scenario_name': capability['name'],
            'total_steps': len(steps),
            'completed_steps': len(step_results),
            'steps': step_results,
        }),
        'duration_ms': sum(r.get('result', {}).get('duration_ms', 0) for r in step_results),
        'started_at': datetime.now(),
        'finished_at': datetime.now(),
    })
    
    return {'ok': True, 'steps': step_results, 'run_id': run_id}
```

**关键改进**：
- ✅ 复用 `ArthasCommandExecutor.execute_batch()`，不重复实现批量执行逻辑
- ✅ 自动记录批量审计日志（由统一执行器处理）
- ✅ 自动 `fail_fast` 控制（某步失败后停止）
- ✅ 步骤间数据传递：P2 增强（见第 13 节后续演进）

### 4.5 智能诊断执行器（白名单机制）

**说明**：智能诊断通过动态加载处理器实现，但为了安全，必须使用白名单机制。

```python
# api/task_center.py

# 诊断处理器白名单（防止任意代码执行）
_DIAGNOSIS_HANDLER_WHITELIST = {
    'performance_diagnose.run_diagnosis': None,  # 运行时动态导入
}

def _load_handler(handler_path: str):
    """安全加载诊断处理器（白名单机制）"""
    
    # 1. 白名单校验
    if handler_path not in _DIAGNOSIS_HANDLER_WHITELIST:
        raise ValueError(f"不允许的诊断处理器: {handler_path}")
    
    # 2. 缓存检查
    if _DIAGNOSIS_HANDLER_WHITELIST[handler_path] is not None:
        return _DIAGNOSIS_HANDLER_WHITELIST[handler_path]
    
    # 3. 动态加载（仅允许 api.* 模块）
    if not handler_path.startswith('performance_diagnose.'):
        raise ValueError(f"不允许的模块路径: {handler_path}")
    
    module_path, func_name = handler_path.rsplit('.', 1)
    module = __import__(f'api.{module_path}', fromlist=[func_name])
    handler_func = getattr(module, func_name)
    
    # 4. 缓存
    _DIAGNOSIS_HANDLER_WHITELIST[handler_path] = handler_func
    return handler_func


def execute_ai_diagnosis(capability, extension, task_def, connection):
    """执行智能诊断（level 4）
    
    职责：
    1. 加载处理器（白名单校验）
    2. 执行诊断
    3. 记录任务执行结果（task_runs 表）
    """
    
    # 1. 解析处理器路径
    handler_path = extension.get('handler', '')
    if not handler_path:
        raise ValueError('智能诊断未配置 handler')
    
    # 2. 安全加载处理器（白名单机制）✅
    handler_func = _load_handler(handler_path)
    
    # 3. 执行诊断
    params = json.loads(task_def.get('params_json', '{}'))
    diagnosis = handler_func(
        connection=connection,
        target=params.get('class_pattern', '*'),
        class_pattern=params.get('class_pattern', '*'),
        method_pattern=params.get('method_pattern', '*'),
    )
    
    # 4. 记录到 task_runs
    run_id = str(uuid4())
    db.insert('task_runs', {
        'id': run_id,
        'task_id': task_def['id'],
        'user_id': task_def.get('created_by'),
        'status': 'success',
        'execution_mode': 'connection',
        'target_json': json.dumps({
            'connection_id': connection.id,
        }),
        'stdout': json.dumps(diagnosis, ensure_ascii=False),
        'result_json': json.dumps({
            'diagnosis': diagnosis,
            'type': 'ai_diagnosis',
        }),
        'started_at': datetime.now(),
        'finished_at': datetime.now(),
    })
    
    return {'ok': True, 'diagnosis': diagnosis, 'run_id': run_id}
```

**安全机制**：
- ✅ 白名单校验：只允许预定义的处理器
- ✅ 模块路径限制：只允许 `api.performance_diagnose.*`
- ✅ 缓存机制：避免重复导入
- ✅ 运行时校验：防止 `handler` 字段被恶意修改

### 4.6 参数校验引擎（增强版）

```python
def validate_parameters(schema_str, params):
    """校验参数（基于 JSON Schema）
    
    支持的校验规则：
    1. 必填项检查（required）
    2. 类型检查（type: string/integer）
    3. 长度限制（max_length）
    4. 正则校验（pattern）
    5. 枚举值校验（enum）
    6. 数值范围（min/max）
    """
    
    if not schema_str or schema_str == '{}':
        return None
    
    schema = json.loads(schema_str)
    
    for field in schema:
        field_name = field['name']
        value = params.get(field_name)
        
        # 1. 必填项检查
        if field.get('required') and field_name not in params:
            return f"缺少必填参数: {field.get('label', field_name)}"
        
        if value is None:
            continue
        
        # 2. 类型检查
        field_type = field.get('type', 'string')
        if field_type == 'string' and not isinstance(value, str):
            return f"参数 {field.get('label', field_name)} 必须是字符串"
        elif field_type == 'integer' and not isinstance(value, int):
            return f"参数 {field.get('label', field_name)} 必须是整数"
        
        # 3. 长度限制
        if isinstance(value, str):
            max_length = field.get('max_length', 200)
            if len(value) > max_length:
                return f"参数 {field.get('label', field_name)} 长度不能超过 {max_length}"
        
        # 4. 正则校验
        if 'pattern' in field:
            import re
            if not re.match(field['pattern'], str(value)):
                return f"参数 {field.get('label', field_name)} 格式不合法"
        
        # 5. 枚举值校验
        if 'enum' in field and value not in field['enum']:
            return f"参数 {field.get('label', field_name)} 必须是 {field['enum']} 之一"
        
        # 6. 数值范围
        if field_type == 'integer':
            if 'min' in field and value < field['min']:
                return f"参数 {field.get('label', field_name)} 不能小于 {field['min']}"
            if 'max' in field and value > field['max']:
                return f"参数 {field.get('label', field_name)} 不能大于 {field['max']}"
    
    return None


def build_command(command_template, params, previous_output=None):
    """构建 Arthas 命令（参数替换）
    
    支持的替换语法：
    1. ${param} - 直接替换
    2. ${param:-default} - 带默认值替换
    3. ${last_output} - 引用上一步输出（P2 增强）
    """
    
    command = command_template
    
    # 1. 替换 ${param} 占位符
    for key, value in params.items():
        command = command.replace(f'${{{key}}}', str(value))
    
    # 2. 处理默认值 ${param:-default}
    import re
    pattern = r'\$\{(\w+):-([^}]*)\}'
    def replace_default(match):
        key = match.group(1)
        default = match.group(2)
        return params.get(key, default)
    
    command = re.sub(pattern, replace_default, command)
    
    # 3. 引用上一步输出（场景方案使用，P2 增强）
    if previous_output:
        last_output = previous_output[-1].get('output', {})
        command = command.replace('${last_output}', json.dumps(last_output))
    
    return command
```

**参数 Schema 示例**：
```json
[
  {
    "name": "class",
    "label": "类名",
    "type": "string",
    "required": true,
    "max_length": 200,
    "pattern": "^[A-Za-z_$][\\w.$*]*$",
    "description": "支持通配符，如 com.example.*Service"
  },
  {
    "name": "method",
    "label": "方法名",
    "type": "string",
    "default": "*",
    "max_length": 100,
    "pattern": "^[\\w.*]*$"
  },
  {
    "name": "duration",
    "label": "采样时长（秒）",
    "type": "integer",
    "required": true,
    "min": 10,
    "max": 300
  }
]
```

---

## 5. API 设计

### 5.1 能力目录查询

```
GET /api/tasks/capabilities?type=arthas_command&category=tool&level=2
```

**查询参数：**
- `type`: script | arthas_command | diagnosis_scenario | ai_diagnosis
- `category`: quick | tool | scenario | ai
- `level`: 1 | 2 | 3 | 4

**响应示例：**
```json
{
  "capabilities": [
    {
      "id": 6,
      "name": "Trace 调用链分析",
      "type": "arthas_command",
      "category": "tool",
      "level": 2,
      "risk_level": "medium",
      "parameters_schema": [{"name": "class", "required": true}],
      "estimated_duration": 30,
      "description": "追踪方法调用链路，定位慢方法",
      "extension": {
        "arthas_command": "trace ${class} ${method} -n 10 '#cost > .5'"
      }
    }
  ],
  "count": 1
}
```

**实现逻辑：**
```python
@app.route('/api/tasks/capabilities')
def list_capabilities():
    """查询诊断能力目录（关联查询扩展表）"""
    
    # 1. 查询核心表
    capabilities = db.fetch_all(
        'SELECT * FROM diagnosis_capabilities WHERE type = ? AND category = ? AND level = ?',
        (type, category, level)
    )
    
    # 2. 加载扩展数据
    for cap in capabilities:
        cap['extension'] = load_extension(cap['type'], cap['id'])
    
    return jsonify({'capabilities': capabilities, 'count': len(capabilities)})
```

### 5.2 执行诊断能力

```
POST /api/tasks/definitions
```

**请求体：**
```json
{
  "name": "Trace 调用链分析 - 2026-05-04",
  "capability_id": 6,
  "execution_mode": "connection",
  "connection_id": "cluster1/default/my-pod-abc123",
  "params_json": "{\"class\": \"com.example.OrderService\", \"method\": \"createOrder\"}",
  "timeout_seconds": 60
}
```

**响应：**
```json
{
  "ok": true,
  "task_id": 123,
  "message": "任务已创建"
}
```

### 5.3 查询任务执行结果

```
GET /api/tasks/runs/<run_id>
```

**响应：**
```json
{
  "id": "uuid-123",
  "task_id": 123,
  "status": "success",
  "execution_mode": "connection",
  "target_json": {
    "connection_id": "cluster1/default/my-pod-abc123",
    "cluster_name": "cluster1",
    "namespace": "default",
    "pod_name": "my-pod-abc123"
  },
  "stdout": "{...}",
  "result_json": "{...}",
  "duration_ms": 2500,
  "started_at": "2026-05-04T10:00:00",
  "finished_at": "2026-05-04T10:00:02"
}
```

---

## 6. 前端交互设计

### 6.1 工具链中心改造

**布局结构：**
```
┌─────────────────────────────────────────────────────────┐
│  工具链中心                                               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌───────────────┐  ┌──────────────────────────────┐   │
│  │  工具包管理    │  │  诊断能力目录                  │   │
│  │               │  │  ┌────┐ ┌────┐ ┌────┐       │   │
│  │  - arthas.jar │  │  │快捷│ │模板│ │场景│       │   │
│  │  - profiler   │  │  └────┘ └────┘ └────┘       │   │
│  │  - 校验/分发  │  │                               │   │
│  └───────────────┘  │  [能力卡片列表]                │   │
│                     │  - JVM Dashboard               │   │
│                     │  - Trace 调用链分析 [执行]      │   │
│                     │  - 接口响应慢诊断 [执行]        │   │
│                     └──────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 6.2 能力卡片展示

```javascript
function renderDiagnosisCapabilities(capabilities) {
  const el = document.getElementById('diagnosisCapList');
  
  if (!capabilities.length) {
    el.innerHTML = '<div class="sb-empty">暂无诊断能力</div>';
    return;
  }
  
  el.innerHTML = capabilities.map(cap => {
    const riskBadge = getRiskBadge(cap.risk_level);
    const levelBadge = getLevelBadge(cap.level);
    const hasParams = cap.parameters_schema && cap.parameters_schema !== '{}';
    
    return `
      <div class="capability-card">
        <div class="capability-header">
          <h4>${escapeHtml(cap.name)}</h4>
          <div class="badges">
            ${levelBadge}
            ${riskBadge}
          </div>
        </div>
        
        <p class="capability-desc">${escapeHtml(cap.description || '')}</p>
        
        <div class="capability-meta">
          <span>⏱ 预计 ${cap.estimated_duration || 10}s</span>
          <span>📂 ${getCategoryLabel(cap.category)}</span>
        </div>
        
        <div class="capability-actions">
          ${hasParams 
            ? `<button class="btn btn-g" onclick="showCapabilityForm(${cap.id})">配置参数</button>`
            : `<button class="btn btn-p" onclick="executeCapability(${cap.id})">执行诊断</button>`
          }
          ${cap.related_capabilities?.length 
            ? `<button class="btn btn-g" onclick="showRelatedCapabilities(${cap.id})">关联推荐</button>` 
            : ''
          }
        </div>
      </div>
    `;
  }).join('');
}

function getRiskBadge(riskLevel) {
  const map = {
    'low': '<span class="badge green">低风险</span>',
    'medium': '<span class="badge yellow">中风险</span>',
    'high': '<span class="badge red">高风险</span>',
  };
  return map[riskLevel] || '';
}

function getLevelBadge(level) {
  const map = {
    1: '<span class="badge blue">快捷工具</span>',
    2: '<span class="badge blue">诊断模板</span>',
    3: '<span class="badge purple">场景方案</span>',
    4: '<span class="badge orange">智能诊断</span>',
  };
  return map[level] || '';
}
```

### 6.3 参数表单动态生成

```javascript
async function showCapabilityForm(capabilityId) {
  # 1. 获取能力详情
  const cap = await safeGet(`/tasks/templates/${capabilityId}`);
      
  // 2. 动态生成表单
  const schema = JSON.parse(cap.parameters_schema || '[]');
  const formHtml = schema.map(field => {
    const required = field.required ? '<span class="required">*</span>' : '';
    const placeholder = field.default ? `placeholder="默认: ${field.default}"` : '';
    
    return `
      <div class="form-group">
        <label>${field.label}${required}</label>
        <input 
          type="text" 
          name="${field.name}" 
          ${placeholder}
          pattern="${field.pattern || ''}"
          required="${field.required || false}"
        />
      </div>
    `;
  }).join('');
  
  // 3. 显示模态框
  showModal(`
    <h3>执行: ${cap.name}</h3>
    <p>${cap.description}</p>
    <form id="capabilityForm">
      ${formHtml}
    </form>
    <div class="modal-actions">
      <button class="btn btn-g" onclick="closeModal()">取消</button>
      <button class="btn btn-p" onclick="submitCapabilityForm(${cap.id})">执行诊断</button>
    </div>
  `);
}

async function submitCapabilityForm(capabilityId) {
  // 1. 收集参数
  const form = document.getElementById('capabilityForm');
  const formData = new FormData(form);
  const params = Object.fromEntries(formData.entries());
  
  // 2. 创建任务
  const taskDef = {
    name: `${capabilityId} - ${new Date().toLocaleString()}`,
    template_id: capabilityId,
    execution_mode: 'connection',
    connection_id: getCurrentConnectionId(),
    params_json: JSON.stringify(params),
    timeout_seconds: 60,
  };
  
  const result = await safePost('/tasks/definitions', taskDef);
  
  if (result.ok) {
    toast('任务已创建', 'ok');
    closeModal();
    
    // 3. 跳转到任务中心查看执行结果
    openTaskCenter();
  }
}
```

### 6.4 场景方案执行流程

```javascript
async function executeScenario(capabilityId) {
  // 1. 获取场景方案详情
  const cap = await safeGet(`/tasks/templates/${capabilityId}`);
  const steps = JSON.parse(cap.steps_json || '[]');
  
  // 2. 显示执行进度
  showModal(`
    <h3>执行场景方案: ${cap.name}</h3>
    <div id="scenarioProgress">
      ${steps.map(step => `
        <div class="step-item" id="step-${step.step}">
          <span class="step-status">⏳ 等待中</span>
          <span class="step-desc">${step.desc}</span>
        </div>
      `).join('')}
    </div>
    <div id="scenarioOutput" class="output-box"></div>
  `);
  
  // 3. 创建任务
  const taskDef = {
    name: `${cap.name} - ${new Date().toLocaleString()}`,
    template_id: capabilityId,
    execution_mode: 'connection',
    connection_id: getCurrentConnectionId(),
    params_json: JSON.stringify(collectParams()),
    timeout_seconds: cap.estimated_duration * 2,
  };
  
  const result = await safePost('/tasks/definitions', taskDef);
  
  // 4. 轮询任务状态
  pollTaskStatus(result.task_id);
}

function pollTaskStatus(taskId, options = {}) {
  const maxPolls = options.maxPolls || 300;  // 最多轮询 300 次（10 分钟）
  const pollInterval = options.pollInterval || 2000;
  let pollCount = 0;
  
  const interval = setInterval(async () => {
    pollCount++;
    
    // 超时保护
    if (pollCount >= maxPolls) {
      clearInterval(interval);
      toast('任务执行超时', 'error');
      return;
    }
    
    try {
      const run = await safeGet(`/tasks/runs/${taskId}`);
      
      if (run.status === 'success' || run.status === 'failed') {
        clearInterval(interval);
        renderScenarioResult(run);
      } else {
        updateScenarioProgress(run);
      }
    } catch (error) {
      console.error('轮询失败:', error);
      // 网络异常时继续轮询，不中断
    }
  }, pollInterval);
  
  return () => clearInterval(interval);  // 返回取消函数
}
```

---

## 7. 典型诊断场景

### 7.1 接口响应慢诊断

**场景定义（script_templates 记录，由管理员配置）：**
```json
{
  "name": "接口响应慢诊断",
  "capability_type": "diagnosis_scenario",
  "category": "scenario",
  "level": 3,
  "steps_json": [
    {"step": 1, "command": "trace ${controller} ${method} -n 10 '#cost > .5'", "desc": "定位慢方法"},
    {"step": 2, "command": "watch ${slow_class} ${slow_method} '{params,returnObj}' -n 3", "desc": "观察入参返回值"},
    {"step": 3, "command": "profiler start --event cpu --duration 30", "desc": "CPU 采样分析"}
  ],
  "parameters_schema": [
    {"name": "controller", "label": "Controller 类名", "required": true},
    {"name": "method", "label": "方法名", "default": "*"}
  ],
  "risk_level": "medium",
  "estimated_duration": 120
}
```

**执行流程：**
1. 用户选择"接口响应慢诊断"
2. 弹出参数表单：输入 Controller 类名（如 `com.example.OrderController`）
3. 系统依次执行 3 个步骤：
   - Step 1: `trace com.example.OrderController * -n 10 '#cost > .5'` → 定位到 `createOrder` 方法耗时 2s
   - Step 2: `watch com.example.OrderService createOrder '{params,returnObj}' -n 3` → 观察入参发现订单数据量大
   - Step 3: `profiler start --event cpu --duration 30` → 生成火焰图，发现 SQL 查询占 80% CPU
4. 输出诊断报告：慢方法 → 入参异常 → CPU 热点

### 7.2 CPU 100% 排查

**场景定义：**
```json
{
  "name": "CPU 100% 排查",
  "capability_type": "diagnosis_scenario",
  "category": "scenario",
  "level": 3,
  "steps_json": [
    {"step": 1, "command": "thread -n 5", "desc": "查看最忙的 5 个线程"},
    {"step": 2, "command": "thread ${thread_id}", "desc": "查看热点线程堆栈"},
    {"step": 3, "command": "profiler start --event cpu --duration 30", "desc": "CPU 采样分析"}
  ],
  "parameters_schema": [
    {"name": "thread_id", "label": "线程 ID（可选）", "default": ""}
  ],
  "risk_level": "low",
  "estimated_duration": 60
}
```

### 7.3 一键性能诊断

**智能诊断定义：**
```json
{
  "name": "一键性能诊断",
  "capability_type": "ai_diagnosis",
  "category": "ai",
  "level": 4,
  "handler": "performance_diagnose.run_diagnosis",
  "risk_level": "low",
  "estimated_duration": 60,
  "description": "自动采集 dashboard + thread + trace，通过规则引擎和 LLM 生成诊断报告"
}
```

**执行流程：**
1. 用户点击"一键性能诊断"
2. 系统调用 `api/performance_diagnose._run_diagnosis()`
3. 自动采集：
   - dashboard 快照
   - thread dump
   - trace 调用链
4. 规则引擎分析：
   - CPU 使用率 > 80%？
   - 线程数 > 500？
   - GC 频率过高？
5. LLM 生成诊断报告（如果配置了 AI 模型）
6. 输出结构化诊断结果

---

## 8. 定时任务调度设计

### 8.1 核心问题与解决方案

#### 问题 1：定时诊断任务的连接问题

**矛盾**：定时任务执行时，用户的 Arthas 连接可能已断开。

**解决方案**：定时任务不支持 Arthas 连接模式，只支持以下两种模式：

| 执行模式 | 说明 | 定时任务支持 | 示例 |
|---------|------|------------|------|
| `node` | Node 本机执行 | ✅ 支持 | 定时清理日志、定时备份 |
| `pod` | Pod 内执行 | ✅ 支持 | 定时采集 JVM 指标 |
| `connection` | Arthas 连接执行 | ❌ 不支持 | trace/watch/profiler（需用户在线） |

**原因**：
- Arthas 连接依赖 port-forward 进程，用户断开后进程退出
- 定时任务无法自动重建 port-forward（需要用户交互）
- 如果强制支持，需要后台常驻 port-forward，增加资源开销

#### 问题 2：定时任务的适用场景

**适合定时的诊断任务**：
- ✅ 定时采集 thread dump（每天凌晨 2 点）
- ✅ 定时采集 JVM 指标（每隔 1 小时）
- ✅ 定时清理 profiler_output 目录（每天凌晨 3 点）
- ✅ 定时执行健康检查脚本（每隔 5 分钟）

**不适合定时的诊断任务**：
- ❌ trace 特定接口（需要用户提供类名）
- ❌ watch 方法入参（需要用户观察实时数据）
- ❌ profiler 采样分析（需要用户触发）

### 8.2 数据库扩展

```sql
-- 扩展 task_schedules 表
ALTER TABLE task_schedules ADD COLUMN cron_expression TEXT;
-- Cron 表达式，如 "0 2 * * *" (每天凌晨 2 点)

ALTER TABLE task_schedules ADD COLUMN max_executions INTEGER DEFAULT 0;
-- 最大执行次数（0 = 无限次）

ALTER TABLE task_schedules ADD COLUMN execution_count INTEGER DEFAULT 0;
-- 已执行次数

ALTER TABLE task_schedules ADD COLUMN timezone TEXT DEFAULT 'Asia/Shanghai';
-- 时区

ALTER TABLE task_schedules ADD COLUMN notify_on_failure INTEGER DEFAULT 1;
-- 失败时是否通知（1=是，0=否）

-- 添加索引
CREATE INDEX idx_task_schedules_status_next_run 
ON task_schedules(status, next_run_at);
```

### 8.3 Cron 表达式规范

**支持的标准 Cron 格式**：

```
┌───────────── 分钟 (0 - 59)
│ ┌───────────── 小时 (0 - 23)
│ │ ┌───────────── 日期 (1 - 31)
│ │ │ ┌───────────── 月份 (1 - 12)
│ │ │ │ ┌───────────── 星期 (0 - 6) (Sunday=0)
│ │ │ │ │
* * * * *
```

**常用示例**：

| Cron 表达式 | 说明 | 适用场景 |
|------------|------|---------|
| `0 2 * * *` | 每天凌晨 2 点 | 定时 thread dump |
| `0 */2 * * *` | 每隔 2 小时 | 定时 JVM 指标采集 |
| `*/5 * * * *` | 每隔 5 分钟 | 定时健康检查 |
| `0 0 * * 0` | 每周日凌晨 0 点 | 定时清理日志 |
| `0 0 1 * *` | 每月 1 号凌晨 0 点 | 定时备份数据 |

**验证规则**：
```python
import croniter
from datetime import datetime

def validate_cron_expression(cron_expr: str) -> bool:
    """验证 Cron 表达式合法性"""
    try:
        # 尝试解析 Cron 表达式
        cron = croniter.croniter(cron_expr, datetime.now())
        # 计算下次执行时间
        next_run = cron.get_next(datetime)
        return True
    except (ValueError, TypeError) as e:
        return False
```

### 8.4 调度器实现

```python
# api/task_center.py

import croniter
from datetime import datetime
import pytz

def calculate_next_run(schedule: dict) -> Optional[datetime]:
    """计算下次执行时间"""
    
    schedule_type = schedule.get('schedule_type', 'interval')
    timezone = pytz.timezone(schedule.get('timezone', 'Asia/Shanghai'))
    now = datetime.now(timezone)
    
    if schedule_type == 'cron' and schedule.get('cron_expression'):
        # Cron 表达式
        cron = croniter.croniter(
            schedule['cron_expression'],
            now
        )
        return cron.get_next(datetime)
    
    elif schedule_type == 'interval':
        # 固定间隔
        last_run = schedule.get('last_run_at') or now
        if isinstance(last_run, str):
            last_run = datetime.fromisoformat(last_run)
        return last_run + timedelta(seconds=schedule['interval_seconds'])
    
    elif schedule_type == 'once':
        # 一次性任务
        scheduled_at = schedule.get('scheduled_at')
        if isinstance(scheduled_at, str):
            scheduled_at = datetime.fromisoformat(scheduled_at)
        return scheduled_at
    
    return None


def run_scheduler():
    """调度器主循环"""
    global _SCHEDULER_STARTED
    
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        _SCHEDULER_STARTED = True
    
    log.info("Task scheduler started")
    
    while True:
        try:
            now = datetime.now()
            
            # 查询待执行的任务
            schedules = db.fetch_all('''
                SELECT * FROM task_schedules 
                WHERE status = 'active' 
                AND next_run_at <= ?
                AND (max_executions = 0 OR execution_count < max_executions)
                ORDER BY next_run_at ASC
            ''', (now,))
            
            for schedule in schedules:
                # 检查任务定义的执行模式
                task_def = db.fetch_one(
                    'SELECT * FROM task_definitions WHERE id = ?',
                    (schedule['task_id'],)
                )
                
                if not task_def:
                    log.warning("Task definition not found: %s", schedule['task_id'])
                    continue
                
                # 检查执行模式
                execution_mode = task_def.get('execution_mode', 'node')
                if execution_mode == 'connection':
                    log.warning(
                        "Scheduled task %s uses 'connection' mode, skipping. "
                        "Scheduled tasks only support 'node' and 'pod' modes.",
                        schedule['id']
                    )
                    # 更新下次执行时间
                    next_run = calculate_next_run(schedule)
                    db.execute('''
                        UPDATE task_schedules SET next_run_at = ? WHERE id = ?
                    ''', (next_run, schedule['id']))
                    continue
                
                # 执行任务
                try:
                    execute_task_definition(task_def['id'])
                    
                    # 更新执行记录
                    execution_count = schedule.get('execution_count', 0) + 1
                    next_run = calculate_next_run(schedule)
                    
                    db.execute('''
                        UPDATE task_schedules 
                        SET execution_count = ?,
                            last_run_at = ?,
                            next_run_at = ?
                        WHERE id = ?
                    ''', (execution_count, now, next_run, schedule['id']))
                    
                    log.info(
                        "Scheduled task %s executed successfully (count=%d)",
                        schedule['id'], execution_count
                    )
                    
                except Exception as e:
                    log.error("Scheduled task %s failed: %s", schedule['id'], e, exc_info=True)
                    
                    # 失败通知
                    if schedule.get('notify_on_failure', 1):
                        notify_task_failure(schedule, e)
                    
                    # 仍然更新下次执行时间
                    next_run = calculate_next_run(schedule)
                    db.execute('''
                        UPDATE task_schedules SET next_run_at = ? WHERE id = ?
                    ''', (next_run, schedule['id']))
            
            time.sleep(_SCHEDULER_POLL_SECONDS)
            
        except Exception as e:
            log.error("Scheduler loop error: %s", e, exc_info=True)
            time.sleep(_SCHEDULER_POLL_SECONDS)


def notify_task_failure(schedule: dict, error: Exception):
    """通知任务失败（后续可扩展为邮件、钉钉、企业微信等）"""
    log.warning(
        "Scheduled task %s failed: %s. User ID: %s",
        schedule['id'], error, schedule.get('user_id')
    )
    # TODO: 实现邮件/钉钉/企业微信通知
```

### 8.5 API 设计

#### 创建定时任务

```
POST /api/tasks/schedules
```

**请求体**：
```json
{
  "task_id": 123,
  "name": "每天凌晨 2 点采集 thread dump",
  "schedule_type": "cron",
  "cron_expression": "0 2 * * *",
  "timezone": "Asia/Shanghai",
  "max_executions": 0,
  "notify_on_failure": true
}
```

**响应**：
```json
{
  "ok": true,
  "schedule_id": 456,
  "next_run_at": "2026-05-05T02:00:00+08:00"
}
```

#### 查询定时任务列表

```
GET /api/tasks/schedules?status=active&page=1&size=20
```

**响应**：
```json
{
  "schedules": [
    {
      "id": 456,
      "task_id": 123,
      "name": "每天凌晨 2 点采集 thread dump",
      "schedule_type": "cron",
      "cron_expression": "0 2 * * *",
      "timezone": "Asia/Shanghai",
      "status": "active",
      "execution_count": 5,
      "max_executions": 0,
      "last_run_at": "2026-05-04T02:00:00+08:00",
      "next_run_at": "2026-05-05T02:00:00+08:00",
      "notify_on_failure": true
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

#### 暂停/恢复定时任务

```
POST /api/tasks/schedules/<schedule_id>/toggle
```

**请求体**：
```json
{
  "status": "paused"  // 或 "active"
}
```

### 8.6 前端交互设计

#### 创建定时任务表单

```html
<div class="form-group">
  <label>调度类型</label>
  <select id="scheduleType" onchange="toggleScheduleInput()">
    <option value="interval">固定间隔</option>
    <option value="cron">Cron 表达式</option>
    <option value="once">一次性</option>
  </select>
</div>

<div id="intervalInput">
  <label>间隔（秒）</label>
  <input type="number" id="intervalSeconds" value="3600" min="60" />
</div>

<div id="cronInput" style="display:none">
  <label>Cron 表达式</label>
  <input type="text" id="cronExpression" placeholder="0 2 * * *" />
  <small>示例: 0 2 * * * (每天凌晨 2 点)</small>
  
  <div class="cron-presets">
    <button onclick="setCron('0 2 * * *')">每天凌晨 2 点</button>
    <button onclick="setCron('0 */2 * * *')">每隔 2 小时</button>
    <button onclick="setCron('*/5 * * * *')">每隔 5 分钟</button>
    <button onclick="setCron('0 0 * * 0')">每周日</button>
  </div>
</div>

<div id="onceInput" style="display:none">
  <label>执行时间</label>
  <input type="datetime-local" id="scheduledAt" />
</div>

<div class="form-group">
  <label>最大执行次数（0 = 无限次）</label>
  <input type="number" id="maxExecutions" value="0" min="0" />
</div>

<div class="form-group">
  <label>
    <input type="checkbox" id="notifyOnFailure" checked />
    失败时通知
  </label>
</div>
```

#### 定时任务列表展示

```javascript
function renderTaskSchedules(schedules) {
  const el = document.getElementById('schedulesList');
  
  if (!schedules.length) {
    el.innerHTML = '<div class="sb-empty">暂无定时任务</div>';
    return;
  }
  
  el.innerHTML = schedules.map(s => {
    const statusClass = s.status === 'active' ? 'running' : 'stopped';
    const statusText = s.status === 'active' ? '运行中' : '已暂停';
    
    return `
      <div class="schedule-item">
        <div class="schedule-info">
          <h4>${escapeHtml(s.name)}</h4>
          <div class="schedule-meta">
            <span>类型: ${s.schedule_type === 'cron' ? 'Cron' : '间隔'}</span>
            ${s.schedule_type === 'cron' 
              ? `<span>Cron: ${escapeHtml(s.cron_expression)}</span>`
              : `<span>间隔: ${s.interval_seconds}s</span>`
            }
            <span>已执行: ${s.execution_count} 次</span>
            <span>下次执行: ${formatTime(s.next_run_at)}</span>
          </div>
        </div>
        <div class="schedule-actions">
          <span class="task-status ${statusClass}">${statusText}</span>
          <button class="btn btn-g" onclick="toggleSchedule(${s.id}, '${s.status === 'active' ? 'paused' : 'active'}')">
            ${s.status === 'active' ? '暂停' : '恢复'}
          </button>
          <button class="btn btn-g danger-text" onclick="deleteSchedule(${s.id})">删除</button>
        </div>
      </div>
    `;
  }).join('');
}
```

### 8.7 典型定时任务场景

#### 场景 1：每天凌晨 2 点采集 thread dump

**任务定义**：
```json
{
  "name": "定时 thread dump",
  "execution_mode": "pod",
  "runtime": "shell",
  "script_body": "jstack $JAVA_PID > /tmp/thread-dump-$(date +%Y%m%d-%H%M%S).txt",
  "timeout_seconds": 30,
  "target_json": "{\"cluster_name\": \"prod\", \"namespace\": \"default\", \"pod_name\": \"my-app\"}"
}
```

**定时调度**：
```json
{
  "task_id": 123,
  "name": "每天凌晨 2 点采集 thread dump",
  "schedule_type": "cron",
  "cron_expression": "0 2 * * *",
  "timezone": "Asia/Shanghai",
  "max_executions": 0
}
```

#### 场景 2：每隔 5 分钟执行健康检查

**任务定义**：
```json
{
  "name": "Pod 健康检查",
  "execution_mode": "pod",
  "runtime": "shell",
  "script_body": "curl -f http://localhost:8080/health || exit 1",
  "timeout_seconds": 10,
  "target_json": "{\"cluster_name\": \"prod\", \"namespace\": \"default\", \"pod_name\": \"my-app\"}"
}
```

**定时调度**：
```json
{
  "task_id": 124,
  "name": "每隔 5 分钟执行健康检查",
  "schedule_type": "cron",
  "cron_expression": "*/5 * * * *",
  "timezone": "Asia/Shanghai",
  "max_executions": 0,
  "notify_on_failure": true
}
```

#### 场景 3：每周日凌晨清理日志

**任务定义**：
```json
{
  "name": "清理 profiler_output 目录",
  "execution_mode": "node",
  "runtime": "shell",
  "script_body": "find /app/profiler_output -name '*.hprof' -mtime +7 -delete",
  "timeout_seconds": 60
}
```

**定时调度**：
```json
{
  "task_id": 125,
  "name": "每周日凌晨清理 7 天前的 heapdump",
  "schedule_type": "cron",
  "cron_expression": "0 0 * * 0",
  "timezone": "Asia/Shanghai",
  "max_executions": 0
}
```

---

## 7. 历史记录与审计设计

### 7.1 涉及的数据表

系统采用 **3 张表** 协同记录诊断执行历史，职责清晰：

| 表名 | 用途 | 记录内容 | 保留策略 |
|------|------|---------|----------|
| **diagnosis_execution_logs** | 诊断执行记录 | 每次诊断的完整执行过程 | 永久保留（可归档） |
| **arthas_command_history** | Arthas 命令历史 | 单条 Arthas 命令执行记录 | 永久保留（可归档） |
| **audit_logs** | 审计日志 | 安全审计、合规追溯 | 永久保留（法规要求） |

### 7.2 表结构设计

#### diagnosis_execution_logs（诊断执行记录表）

```sql
CREATE TABLE diagnosis_execution_logs (
    id TEXT PRIMARY KEY,                     -- 执行记录 ID (UUID)
    capability_id INTEGER NOT NULL,          -- 关联的诊断能力
    capability_name TEXT NOT NULL,           -- 能力名称（冗余，防止能力被删除后丢失）
    capability_type TEXT NOT NULL,           -- script | arthas_command | diagnosis_scenario | ai_diagnosis
    capability_version INTEGER,              -- 能力版本号（用于追溯执行时的版本）
    
    user_id INTEGER NOT NULL,                -- 执行人
    execution_mode TEXT NOT NULL,            -- connection | pod | node
    
    -- 目标信息
    cluster_name TEXT,                       -- 集群名称
    namespace TEXT,                          -- 命名空间
    pod_name TEXT,                           -- Pod 名称
    container_name TEXT,                     -- 容器名称
    connection_id TEXT,                      -- 连接 ID（仅 connection 模式）
    
    -- 执行参数
    params_json TEXT DEFAULT '{}',           -- 执行时的参数（JSON）
    rendered_command TEXT,                   -- 参数替换后的实际执行命令
    
    -- 执行结果
    status TEXT NOT NULL,                    -- pending | running | success | failed | cancelled
    result_json TEXT,                        -- 执行结果（结构化）
    error_message TEXT,                      -- 错误信息
    duration_ms INTEGER,                     -- 执行时长（毫秒）
    
    -- 时间戳
    started_at TIMESTAMP,                    -- 开始时间
    finished_at TIMESTAMP,                   -- 结束时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 索引
CREATE INDEX idx_exec_logs_capability ON diagnosis_execution_logs(capability_id);
CREATE INDEX idx_exec_logs_user ON diagnosis_execution_logs(user_id);
CREATE INDEX idx_exec_logs_status ON diagnosis_execution_logs(status);
CREATE INDEX idx_exec_logs_started_at ON diagnosis_execution_logs(started_at);
CREATE INDEX idx_exec_logs_cluster_ns_pod ON diagnosis_execution_logs(cluster_name, namespace, pod_name);
```

**架构师说明**：
1. **表名选择**：`diagnosis_execution_logs` 比 `task_runs` 更清晰，明确表达“诊断执行记录”语义
2. **能力版本追溯**：`capability_version` 字段记录执行时的能力版本，支持历史回溯
3. **命令冗余**：`rendered_command` 记录参数替换后的实际命令，防止能力模板被修改后丢失执行上下文
4. **目标信息冗余**：`cluster_name/namespace/pod_name` 冗余存储，防止连接记录被删除后丢失目标信息

#### arthas_command_history（Arthas 命令历史表）

```sql
CREATE TABLE arthas_command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_log_id TEXT NOT NULL,          -- 关联诊断执行记录
    step_order INTEGER,                      -- 步骤顺序（场景方案多步骤时使用）
    
    -- 命令信息
    command TEXT NOT NULL,                   -- Arthas 命令
    command_type TEXT,                       -- trace | watch | profiler | thread | ...
    
    -- 执行结果
    status TEXT NOT NULL,                    -- success | failed
    output_json TEXT,                        -- 命令输出（结构化）
    error_message TEXT,                      -- 错误信息
    duration_ms INTEGER,                     -- 执行时长（毫秒）
    
    -- 时间戳
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (execution_log_id) REFERENCES diagnosis_execution_logs(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_cmd_history_execution ON arthas_command_history(execution_log_id);
CREATE INDEX idx_cmd_history_command_type ON arthas_command_history(command_type);
CREATE INDEX idx_cmd_history_executed_at ON arthas_command_history(executed_at);
```

**架构师说明**：
1. **表名选择**：`arthas_command_history` 比 `arthas_commands` 更清晰，明确表达“命令历史”语义
2. **关联执行记录**：`execution_log_id` 关联到 `diagnosis_execution_logs`，支持追溯完整执行过程
3. **步骤顺序**：`step_order` 支持场景方案的多步骤命令追溯
4. **命令类型**：`command_type` 支持按命令类型统计分析（如：trace 执行了多少次）

#### audit_logs（审计日志表 - 复用现有表）

```sql
-- 现有表结构（假设已存在）
-- 记录所有敏感操作，用于安全审计和合规追溯

-- 诊断相关的审计日志示例：
{
    "action": "execute_diagnosis",
    "resource_type": "diagnosis_capability",
    "resource_id": "6",
    "user_id": 1,
    "details": {
        "capability_name": "Trace 调用链分析",
        "capability_type": "arthas_command",
        "execution_log_id": "uuid-123",
        "command": "trace com.example.OrderService createOrder -n 10 '#cost > .5'",
        "risk_level": "medium",
        "cluster_name": "cluster1",
        "namespace": "default",
        "pod_name": "my-pod-abc123"
    },
    "created_at": "2026-05-04T10:00:00"
}
```

### 7.3 表关系图

```
diagnosis_capabilities (能力定义)
│
└── diagnosis_execution_logs (执行记录)
    │
    ├── arthas_command_history (命令历史)  -- 一对一或一对多
    │
    └── audit_logs (审计日志)  -- 一对多（多条审计记录对应一次执行）
```

### 7.4 写入时机

| 表名 | 写入时机 | 写入频率 |
|------|---------|----------|
| **diagnosis_execution_logs** | 任务开始执行时创建，执行完成后更新 | 每次执行 1 条 |
| **arthas_command_history** | 每条 Arthas 命令执行后 | 每次执行 N 条（N = 命令数） |
| **audit_logs** | 高危命令执行前/后 | 每次高危命令 1-2 条 |

### 7.5 查询场景

#### 场景 1：查询某用户的诊断历史

```sql
SELECT 
    el.id, 
    el.capability_name,
    el.status,
    el.duration_ms,
    el.started_at,
    el.cluster_name,
    el.namespace,
    el.pod_name
FROM diagnosis_execution_logs el
WHERE el.user_id = ?
ORDER BY el.started_at DESC
LIMIT 50;
```

#### 场景 2：查询某次执行的完整命令历史

```sql
SELECT 
    ch.step_order,
    ch.command,
    ch.command_type,
    ch.status,
    ch.duration_ms,
    ch.executed_at
FROM arthas_command_history ch
WHERE ch.execution_log_id = 'uuid-123'
ORDER BY ch.step_order;
```

#### 场景 3：查询某 Pod 的诊断历史

```sql
SELECT 
    el.id,
    el.capability_name,
    el.status,
    el.started_at,
    el.params_json
FROM diagnosis_execution_logs el
WHERE el.cluster_name = 'cluster1'
  AND el.namespace = 'default'
  AND el.pod_name = 'my-pod-abc123'
ORDER BY el.started_at DESC;
```

#### 场景 4：统计某能力类型的执行次数

```sql
SELECT 
    el.capability_type,
    COUNT(*) as execution_count,
    AVG(el.duration_ms) as avg_duration_ms,
    SUM(CASE WHEN el.status = 'success' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate
FROM diagnosis_execution_logs el
WHERE el.started_at >= datetime('now', '-30 days')
GROUP BY el.capability_type;
```

### 7.6 数据归档策略

```sql
-- 归档 90 天前的执行记录
CREATE TABLE diagnosis_execution_logs_archive AS
SELECT * FROM diagnosis_execution_logs
WHERE started_at < datetime('now', '-90 days');

-- 删除已归档的记录
DELETE FROM diagnosis_execution_logs
WHERE started_at < datetime('now', '-90 days');

-- 注意：审计日志（audit_logs）不应归档，需永久保留
```

---

## 9. 安全与风险控制

### 9.1 风险分级

| 风险等级 | 定义 | 示例 | 控制措施 |
|---------|------|------|---------|
| **low** | 只读操作，无副作用 | dashboard, thread, vmoption | 直接执行 |
| **medium** | 可能影响性能，但可恢复 | trace, watch, profiler | 执行前提示预计耗时 |
| **high** | 可能影响业务，需谨慎 | redefine, logger --level, vmoption 修改 | 二次确认 + 审计日志 |

### 9.2 高危命令二次确认

```javascript
async function executeCapability(capabilityId) {
  const cap = await safeGet(`/tasks/templates/${capabilityId}`);
  
  // 高危能力需要二次确认
  if (cap.risk_level === 'high') {
    const confirmed = confirm(
      `⚠️ 此操作为高危操作\n\n` +
      `能力名称: ${cap.name}\n` +
      `风险等级: 高风险\n` +
      `预计耗时: ${cap.estimated_duration}s\n\n` +
      `是否继续？`
    );
    
    if (!confirmed) {
      return;
    }
  }
  
  // 执行...
}
```

### 9.3 输出脱敏

```python
# services/safety_service.py
def mask_sensitive_output(output: str) -> str:
    """脱敏敏感信息"""
    
    # 密码脱敏
    output = re.sub(r'(password|pwd|passwd)["\s:=]+\S+', r'\1=***', output, flags=re.IGNORECASE)
    
    # Token 脱敏
    output = re.sub(r'(token|access_token|api_key)["\s:=]+\S{10,}', r'\1=***', output, flags=re.IGNORECASE)
    
    # 身份证号脱敏
    output = re.sub(r'\d{6}(\d{8})\d{4}', r'******\1****', output)
    
    # 手机号脱敏
    output = re.sub(r'1\d{2}\d{4}\d{4}', r'1\d{2}****\d{4}', output)
    
    return output
```

### 9.4 审计日志

所有诊断能力执行都记录到 `audit_logs` 表：

```python
AuditService.log_event(
    action='execute_diagnosis',
    resource_type='diagnosis_capability',
    resource_id=str(capability['id']),
    details=json.dumps({
        'capability_name': capability['name'],
        'capability_type': capability['type'],
        'execution_log_id': run_id,
        'command': rendered_command,
        'risk_level': capability['risk_level'],
        'cluster_name': connection.cluster_name,
        'namespace': connection.namespace,
        'pod_name': connection.pod_name,
    })
)
```

---

## 10. 实施计划

### Phase 1：数据库迁移与框架搭建（1天）

**任务清单：**
- [ ] 在 `script_templates` 表增加 8 个新字段
- [ ] 添加索引优化查询
- [ ] 移除 `_USER_CASE_CAPABILITIES` 硬编码逻辑
- [ ] 搭建诊断能力框架（空框架，不预制数据）
- [ ] 编写迁移测试

**验收标准：**
```bash
python -m pytest tests/test_task_center_migration.py -q  # PASS
```

**说明：**
- 本阶段只搭建框架和流程
- 所有工具包通过后台上传管理
- 诊断能力由管理员在后台配置
- 后续根据实际诊断场景，逐步添加场景化解决方案

### Phase 2：后端执行器（3天）

**任务清单：**
- [x] 创建 `ArthasCommandExecutor` 统一执行器（已完成，14/14 测试通过）
- [ ] 实现 `execute_arthas_command()` 单步执行（复用统一执行器）
- [ ] 实现 `execute_scenario()` 多步执行（复用 `execute_batch()`）
- [ ] 实现 `execute_ai_diagnosis()` 智能诊断（白名单机制）
- [ ] 实现增强版参数校验引擎 `validate_parameters()`
- [ ] 实现命令构建器 `build_command()`
- [ ] 集成 SafetyService 脱敏（由统一执行器处理）
- [ ] 集成 AuditService 审计（由统一执行器处理）
- [ ] 编写执行器测试

**验收标准：**
```bash
python -m pytest tests/test_task_center_executor.py -q  # PASS
```

### Phase 3：前端改造（3天）

**任务清单：**
- [ ] 改造 `loadToolchainCenter()` 加载诊断能力
- [ ] 实现 `renderDiagnosisCapabilities()` 能力卡片
- [ ] 实现参数表单动态生成
- [ ] 实现场景方案执行进度展示
- [ ] 实现高危能力二次确认
- [ ] 改造任务创建表单
- [ ] 编写前端测试

**验收标准：**
```bash
python -m pytest tests/test_task_center_frontend.py -q  # PASS
```

### Phase 4：集成测试（2天）

**任务清单：**
- [ ] 测试快捷工具执行
- [ ] 测试诊断模板执行
- [ ] 测试场景方案多步执行
- [ ] 测试智能诊断
- [ ] 测试定时诊断任务
- [ ] 测试输出脱敏
- [ ] 测试审计日志

**验收标准：**
```bash
python -m pytest tests/test_task_center_integration.py -q  # PASS
```

---

## 11. 关键优势

| 优势 | 说明 |
|------|------|
| ✅ 不新建表 | 复用现有 5 张表，降低复杂度 |
| ✅ 向后兼容 | 现有 Python/Shell 脚本任务不受影响 |
| ✅ 统一调度 | 诊断任务和脚本任务共用 `task_schedules` |
| ✅ 统一历史 | 诊断执行记录存入 `task_runs`，可追溯 |
| ✅ 易于扩展 | 新增诊断能力只需插入 `script_templates` |
| ✅ 分层组织 | 快捷工具 → 诊断模板 → 场景方案 → 智能诊断 |
| ✅ 安全可控 | 风险分级、二次确认、输出脱敏、审计日志 |

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|----------|
| `script_templates` 表字段膨胀 | 可维护性下降 | 通过 `type` 区分用途，按需查询字段 |
| 场景方案步骤失败 | 用户体验差 | 支持 `fail_fast` 配置，失败时提示用户 |
| Arthas 命令执行超时 | 任务卡住 | 设置 `timeout_seconds`，超时自动取消 |
| 高危命令误用 | 线上故障 | 二次确认 + 审计日志 + 管理员审批（P2） |
| 前端参数表单复杂 | 用户学习成本高 | 提供默认值 + 参数说明 + 示例 |
| 智能诊断处理器被恶意修改 | 任意代码执行 | 白名单机制 + 模块路径限制 |
| 定时任务连接已断开 | 任务执行失败 | 禁止 `connection` 模式的定时任务 |
| 场景方案步骤间数据传递复杂 | 实现难度高 | Phase 1 只支持简单多步骤，P2 增强 |
| 参数校验不严格 | 注入攻击 | 增强版校验（类型、长度、正则、枚举、范围） |

---

## 13. 后续演进（P2 TODO）

### 13.1 场景方案增强

- [ ] 支持场景方案步骤间参数传递（如 Step 1 输出作为 Step 2 输入）
  - 示例：`thread -n 5` → 提取线程 ID → `thread ${thread_id}`
  - 语法：`output_vars: {"thread_id": "output.body.results[0].threadId"}`
- [ ] 支持条件分支（如 Step 1 失败则执行 Step 2A，成功则执行 Step 2B）
- [ ] 支持循环（如遍历所有慢方法执行 watch）
- [ ] 支持步骤超时独立配置

### 13.2 诊断能力增强

- [ ] 支持诊断能力组合编排（可视化拖拽）
- [ ] 支持诊断模板版本管理
- [ ] 支持诊断报告导出（PDF/Markdown）
- [ ] 支持诊断能力市场（社区共享）
- [ ] 支持诊断能力执行统计（成功率、平均耗时）

### 13.3 安全与审批

- [ ] 支持审批流（高危命令需管理员审批）
- [ ] 支持命令执行频率限制（防止滥用）
- [ ] 支持命令执行配额（如每天最多执行 100 次 trace）

### 13.4 定时任务增强

- [ ] 支持定时 Arthas 诊断任务（需要后台常驻 port-forward）
- [ ] 支持失败自动重试（最多 3 次）
- [ ] 支持失败通知（邮件、钉钉、企业微信）
- [ ] 支持执行历史统计（成功率、平均耗时）
- [ ] **支持连接健康检查 + 自动重连**
- [ ] **支持 task_logs 定时清理机制**

### 13.6 定时任务连接管理

#### 13.6.1 连接健康检查

**问题**：定时任务执行时，Arthas 连接可能已过期（Pod 重启、网络断开等）

**解决方案**：

```python
# backend/core/task_scheduler.py

class TaskScheduler:
    """定时任务调度器"""
    
    async def execute_scheduled_task(self, schedule_id: int):
        """执行定时任务（带连接健康检查）"""
        
        # 1. 获取调度配置
        schedule = db.fetch_one(
            'SELECT * FROM task_schedules WHERE id = ?',
            (schedule_id,)
        )
        
        # 2. 获取或创建连接
        connection = await self.get_or_create_connection(schedule)
        
        # 3. 检查连接健康
        if not await self.is_connection_healthy(connection, schedule):
            connection = await self.reconnect(connection, schedule)
        
        # 4. 执行任务（带重试）
        retry_policy = json.loads(schedule['retry_policy'])
        last_error = None
        
        for attempt in range(retry_policy['max_retries']):
            try:
                result = await self.execute_task(schedule['task_id'], connection)
                
                # 5. 记录成功日志
                self.log_success(schedule, result)
                return result
                
            except Exception as e:
                last_error = e
                
                if attempt < retry_policy['max_retries'] - 1:
                    # 指数退避延迟
                    delay = self.calculate_delay(retry_policy, attempt)
                    await asyncio.sleep(delay)
                    
                    # 重新检查连接
                    if not await self.is_connection_healthy(connection, schedule):
                        connection = await self.reconnect(connection, schedule)
        
        # 6. 所有重试失败，触发告警
        await self.alert_on_failure(schedule, last_error)
        self.log_failure(schedule, last_error)
        raise last_error
    
    async def is_connection_healthy(self, connection, schedule) -> bool:
        """检查连接是否健康"""
        
        # 1. 检查连接是否过期
        ttl = schedule.get('connection_ttl', 300)
        if connection.created_at + timedelta(seconds=ttl) < datetime.now():
            return False
        
        # 2. 检查 Arthas 是否可达
        try:
            response = await connection.http_client.ping()
            return response.get('state') == 'SUCCEEDED'
        except Exception:
            return False
    
    async def reconnect(self, connection, schedule):
        """重新建立连接"""
        # 1. 关闭旧连接
        await connection.close()
        
        # 2. 重新建立 port-forward
        new_connection = await self.create_connection(schedule)
        
        # 3. 启动 Arthas agent
        await new_connection.start_arthas()
        
        return new_connection
    
    def calculate_delay(self, retry_policy: dict, attempt: int) -> float:
        """计算重试延迟（指数退避）"""
        backoff = retry_policy.get('backoff', 'exponential')
        initial_delay = retry_policy.get('initial_delay_ms', 1000) / 1000
        max_delay = retry_policy.get('max_delay_ms', 30000) / 1000
        
        if backoff == 'exponential':
            delay = initial_delay * (2 ** attempt)
        else:  # fixed
            delay = initial_delay
        
        return min(delay, max_delay)
    
    async def alert_on_failure(self, schedule, error: Exception):
        """失败告警"""
        channels = json.loads(schedule.get('alert_channels', '["email"]'))
        
        for channel in channels:
            if channel == 'email':
                await self.send_email_alert(schedule, error)
            elif channel == 'dingtalk':
                await self.send_dingtalk_alert(schedule, error)
            elif channel == 'wechat':
                await self.send_wechat_alert(schedule, error)
```

#### 13.6.2 task_logs 定时清理机制

**问题**：`task_logs` 表数据快速增长，影响查询性能

**解决方案**：定时清理 + 冷热分离

```python
# services/task_logs_cleanup_service.py

class TaskLogsCleanupService:
    """task_logs 定时清理服务"""
    
    async def cleanup_expired_logs(self):
        """清理过期的 task_logs"""
        
        # 1. 查询过期日志（超过 retention_days）
        expired_logs = db.fetch_all(
            """
            SELECT id FROM task_logs 
            WHERE is_archived = 0 
              AND finished_at < datetime('now', '-' || retention_days || ' days')
            """
        )
        
        if not expired_logs:
            return
        
        # 2. 归档到历史表（可选）
        for log in expired_logs:
            await self.archive_log(log['id'])
        
        # 3. 删除过期日志
        db.execute(
            """
            DELETE FROM task_logs 
            WHERE is_archived = 0 
              AND finished_at < datetime('now', '-' || retention_days || ' days')
            """
        )
        
        # 4. 清理关联数据（task_artifacts 级联删除）
        db.execute(
            """
            DELETE FROM task_artifacts 
            WHERE run_id NOT IN (SELECT id FROM task_logs)
            """
        )
        
        # 5. 清理孤立的 arthas_command_logs（独立清理）
        db.execute(
            """
            DELETE FROM arthas_command_logs 
            WHERE connection_id NOT IN (SELECT id FROM connections)
              AND timestamp < datetime('now', '-30 days')
            """
        )
    
    async def archive_log(self, log_id: str):
        """归档日志到历史表"""
        
        # 1. 复制到历史表
        db.execute(
            """
            INSERT INTO task_logs_archive 
            SELECT * FROM task_logs WHERE id = ?
            """,
            (log_id,)
        )
        
        # 2. 标记为已归档
        db.execute(
            'UPDATE task_logs SET is_archived = 1 WHERE id = ?',
            (log_id,)
        )
    
    async def cleanup_old_archives(self, days: int = 365):
        """清理超过 1 年的归档数据"""
        
        db.execute(
            """
            DELETE FROM task_logs_archive 
            WHERE finished_at < datetime('now', '-' || ? || ' days')
            """,
            (days,)
        )
```

**定时调度配置**：
```python
# server.py

from apscheduler.schedulers.background import BackgroundScheduler
from services.task_logs_cleanup_service import TaskLogsCleanupService

scheduler = BackgroundScheduler()

# 每天凌晨 3 点清理过期日志
scheduler.add_job(
    TaskLogsCleanupService().cleanup_expired_logs,
    'cron',
    hour=3,
    minute=0,
    id='cleanup_task_logs'
)

# 每月 1 号清理旧归档
scheduler.add_job(
    TaskLogsCleanupService().cleanup_old_archives,
    'cron',
    day=1,
    hour=4,
    minute=0,
    id='cleanup_old_archives'
)

scheduler.start()
```

**清理策略**：

| 数据类型 | 保留时间 | 清理方式 | 执行频率 |
|---------|---------|---------|----------|
| **task_logs（活跃）** | 30 天 | 归档到 task_logs_archive | 每天凌晨 3 点 |
| **task_logs_archive（归档）** | 365 天 | 永久删除 | 每月 1 号 |
| **arthas_command_logs** | 跟随 task_logs | 独立清理（通过 connection_id 关联） | 每天凌晨 3 点 |
| **task_artifacts** | 跟随 task_logs | 级联删除 | 每天凌晨 3 点 |
| **audit_logs** | **永久保留** | 不清理 | - |

**注意事项**：
- `audit_logs` 不清理（法规要求）
- 归档前备份重要数据
- 清理操作记录到系统日志
- 支持手动触发清理（管理员后台）

### 13.5 前端体验优化

- [ ] 实现场景方案执行进度实时展示（WebSocket 推送）
- [ ] 实现诊断结果可视化（火焰图、调用链图）
- [ ] 实现参数表单智能提示（类名自动补全）
- [ ] 实现诊断模板收藏功能

---

## 附录 A：数据库表清单与数据字典

### A.1 表变更清单

#### 本次新增的表（5 张）

| 序号 | 表名 | 用途 | 优先级 |
|------|------|------|--------|
| 1 | **diagnosis_capabilities** | 诊断能力元数据（核心表） | P0 |
| 2 | **arthas_command_templates** | Arthas 命令模板扩展 | P0 |
| 3 | **diagnosis_scenario_steps** | 场景方案步骤扩展 | P0 |
| 4 | **ai_diagnosis_handlers** | AI 诊断处理器扩展 | P0 |
| 5 | **audit_logs** | 审计日志（如不存在则新建） | P0 |

#### 本次修改的表（3 张）

| 序号 | 表名 | 修改内容 | 说明 |
|------|------|---------|------|
| 1 | **script_templates** | 新增 `capability_id` 字段 | 关联到 diagnosis_capabilities |
| 2 | **arthas_commands** | 重命名为 `arthas_command_logs` + 扩展字段 | 统一日志表命名规范 |
| 3 | **task_logs** | 重命名（原 task_runs）+ 扩展字段 | 统一日志表命名规范 |

#### 重命名的表（2 张）

| 原表名 | 新表名 | 用途 | 说明 |
|--------|--------|------|------|
| **arthas_commands** | **arthas_command_logs** | Arthas 命令执行日志 | 统一日志表命名规范（_logs 后缀） |
| **task_runs** | **task_logs** | 任务执行日志 | 统一日志表命名规范（_logs 后缀） |

#### 保留的表（4 张）

| 序号 | 表名 | 用途 | 说明 |
|------|------|------|------|
| 1 | **task_definitions** | 任务定义 | 保留，仅用于定时任务/通用任务 |
| 2 | **task_artifacts** | 任务产物 | 保留，任务输出文件 |
| 3 | **task_schedules** | 定时调度 | 保留，定时任务配置 |
| 4 | **tool_packages** | 工具包管理 | 保留，工具包分发 |

#### 可以删除的表（1 张）

| 表名 | 原因 |
|------|------|
| **diagnosis_logs** | 功能与 task_logs 重叠，统一使用 task_logs |

---

### A.2 完整表清单（11 张）

| 分类 | 表名 | 用途 | 变更类型 |
|------|------|------|----------|
| **诊断能力** | diagnosis_capabilities | 诊断能力元数据 | 新增 |
| **诊断能力** | script_templates | 脚本模板扩展 | 修改（新增 capability_id） |
| **诊断能力** | arthas_command_templates | Arthas 命令模板扩展 | 新增 |
| **诊断能力** | diagnosis_scenario_steps | 场景方案步骤扩展 | 新增 |
| **诊断能力** | ai_diagnosis_handlers | AI 诊断处理器扩展 | 新增 |
| **任务管理** | task_definitions | 任务定义 | 保留（仅用于定时任务/通用任务） |
| **任务管理** | task_logs | 任务执行日志 | 重命名（原 task_runs） |
| **任务管理** | task_artifacts | 任务产物 | 保留 |
| **任务管理** | task_schedules | 定时调度 | 保留（扩展字段） |
| **任务管理** | tool_packages | 工具包管理 | 保留 |
| **执行日志** | arthas_command_logs | Arthas 命令执行日志 | 重命名（原 arthas_commands） |
| **安全审计** | audit_logs | 审计日志 | 保留/新建 |

**说明**：
- `task_logs` 统一记录所有执行日志（即时诊断、定时任务、通用任务）
- 即时诊断：直接写入 `task_logs`，`task_id` 为 NULL，`capability_id` 不为 NULL
- 定时任务：通过 `task_definitions` 创建，`task_id` 不为 NULL

---

### A.3 数据字典

#### A.3.1 diagnosis_capabilities（诊断能力元数据表）

**用途**：存储所有诊断能力的统一元数据

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 能力 ID |
| name | TEXT | NOT NULL UNIQUE | - | 能力名称，如 "CPU 性能分析" |
| type | TEXT | NOT NULL | - | 能力类型：script \| arthas_command \| diagnosis_scenario \| ai_diagnosis |
| category | TEXT | NOT NULL | - | 分类：quick \| tool \| scenario \| ai |
| level | INTEGER | NOT NULL | 1 | 层级：1=快捷工具 2=诊断模板 3=场景方案 4=智能诊断 |
| risk_level | TEXT | - | 'low' | 风险等级：low \| medium \| high |
| parameters_schema | TEXT | - | '{}' | 参数 Schema（JSON 数组），定义参数格式和校验规则 |
| description | TEXT | - | NULL | 能力描述 |
| estimated_duration | INTEGER | - | 10 | 预计执行时长（秒） |
| created_by | INTEGER | FOREIGN KEY → users(id) | NULL | 创建人 ID |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 更新时间 |

**索引**：
- `idx_diag_caps_type` ON (type)
- `idx_diag_caps_category_level` ON (category, level)

---

#### A.3.2 script_templates（脚本模板扩展表）

**用途**：存储脚本类型诊断能力的专属字段（复用现有表）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 模板 ID |
| name | TEXT | NOT NULL | - | 模板名称 |
| runtime | TEXT | NOT NULL | 'python' | 运行时：python \| shell |
| script_body | TEXT | NOT NULL | - | 脚本内容 |
| default_timeout | INTEGER | - | 60 | 默认超时时间（秒） |
| description | TEXT | - | NULL | 模板描述 |
| parameters_schema | TEXT | - | '{}' | 参数 Schema（JSON） |
| tool_package_id | INTEGER | FOREIGN KEY → tool_packages(id) | NULL | 关联工具包 ID |
| **capability_id** | INTEGER | FOREIGN KEY → diagnosis_capabilities(id) | NULL | **新增：关联诊断能力 ID** |
| created_by | INTEGER | FOREIGN KEY → users(id) | NULL | 创建人 ID |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 更新时间 |

**说明**：
- `capability_id` 为 NULL 时，表示独立脚本（不关联诊断能力）
- `capability_id` 不为 NULL 时，`diagnosis_capabilities.type` 必须为 'script'

---

#### A.3.3 arthas_command_templates（Arthas 命令模板扩展表）

**用途**：存储 Arthas 官网命令模板（扩展表）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 模板 ID |
| capability_id | INTEGER | NOT NULL UNIQUE, FK → diagnosis_capabilities(id) | - | 关联诊断能力 ID（一对一） |
| command_name | TEXT | NOT NULL | - | 命令名称（如：trace, watch, profiler, thread） |
| command_category | TEXT | - | NULL | 命令分类：diagnostic \| profiling \| monitoring \| jit \| classloader |
| arthas_command | TEXT | NOT NULL | - | Arthas 命令模板，支持 `${param}` 占位符 |
| syntax | TEXT | - | NULL | 命令语法（官网文档） |
| description | TEXT | - | NULL | 命令描述 |
| params_json | TEXT | - | '[]' | 参数定义（JSON 数组） |
| options_json | TEXT | - | '[]' | 选项定义（JSON 数组） |
| examples | TEXT | - | NULL | 使用示例（多行文本） |
| doc_url | TEXT | - | NULL | 官网文档链接 |
| min_version | TEXT | - | NULL | 最低 Arthas 版本要求 |
| tags | TEXT | - | NULL | 标签（逗号分隔） |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 更新时间 |

**索引**：
- `idx_arthas_cmd_templates_command_name` ON (command_name)
- `idx_arthas_cmd_templates_category` ON (command_category)

**外键约束**：`ON DELETE CASCADE`（capability_id）

**示例数据**：
```json
{
  "command_name": "trace",
  "command_category": "diagnostic",
  "arthas_command": "trace ${class} ${method} -n ${times} --skipJDKMethod ${skip}",
  "syntax": "trace class method [condition] [-n times] [--skipJDKMethod]",
  "params_json": [
    {"name": "class", "type": "string", "required": true, "description": "类名表达式匹配"},
    {"name": "method", "type": "string", "required": true, "description": "方法名表达式匹配"},
    {"name": "times", "type": "integer", "default": 100, "description": "执行次数"},
    {"name": "skip", "type": "boolean", "default": false, "description": "跳过 JDK 方法"}
  ],
  "examples": "trace com.example.UserService *User\ntrace *Service * --skipJDKMethod true",
  "doc_url": "https://arthas.aliyun.com/doc/trace.html"
}
```

---

#### A.3.4 diagnosis_scenario_steps（场景方案步骤扩展表）

**用途**：存储场景方案类型诊断能力的多步骤定义

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 步骤 ID |
| capability_id | INTEGER | NOT NULL, FK → diagnosis_capabilities(id) | - | 关联诊断能力 ID（一对多） |
| step_order | INTEGER | NOT NULL | - | 步骤顺序，从 1 开始 |
| command | TEXT | NOT NULL | - | Arthas 命令模板 |
| desc | TEXT | - | NULL | 步骤说明 |
| timeout_ms | INTEGER | - | 60000 | 超时时间（毫秒） |
| fail_fast | INTEGER | - | 1 | 1=失败后停止，0=继续执行 |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |

**唯一约束**：`UNIQUE(capability_id, step_order)`
**外键约束**：`ON DELETE CASCADE`

---

#### A.3.5 ai_diagnosis_handlers（AI 诊断处理器扩展表）

**用途**：存储智能诊断类型诊断能力的处理器路径

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 记录 ID |
| capability_id | INTEGER | NOT NULL UNIQUE, FK → diagnosis_capabilities(id) | - | 关联诊断能力 ID（一对一） |
| handler | TEXT | NOT NULL | - | 处理器路径，如 "performance_diagnose.run_diagnosis" |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |

**检查约束**：`CHECK(handler LIKE 'performance_diagnose.%')`（限制模块路径）
**外键约束**：`ON DELETE CASCADE`

---

#### A.3.7 arthas_command_logs（Arthas 命令执行日志表）

**用途**：记录单条 Arthas 命令的执行历史（重命名 + 扩展字段）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 记录 ID |
| connection_id | TEXT | NOT NULL, FK → connections(id) | - | 关联连接 ID（保留，兼容旧系统） |
| user_id | INTEGER | FOREIGN KEY → users(id) | NULL | 执行人 ID |
| command | TEXT | NOT NULL | - | Arthas 命令 |
| output | TEXT | - | NULL | 命令输出（保留，兼容旧系统） |
| error | TEXT | - | NULL | 错误信息（保留，兼容旧系统） |
| timestamp | TIMESTAMP | - | CURRENT_TIMESTAMP | 执行时间（保留，兼容旧系统） |
| **template_id** | INTEGER | FK → arthas_command_templates(id) | NULL | **新增：关联 Arthas 命令模板 ID** |
| **step_order** | INTEGER | - | NULL | **新增：步骤顺序（场景方案多步骤时使用）** |
| **command_type** | TEXT | - | NULL | **新增：命令类型：trace \| watch \| profiler \| thread \| ...** |
| **duration_ms** | INTEGER | - | NULL | **新增：执行时长（毫秒）** |

**索引**：
- `idx_arthas_commands_user_cluster_created` ON (user_id, connection_id, timestamp)（现有）
- `idx_arthas_command_logs_template` ON (template_id)（新增）
- `idx_arthas_command_logs_command_type` ON (command_type)（新增）

**外键约束**：`ON DELETE CASCADE`（connection_id），`ON DELETE SET NULL`（template_id）

**说明**：
- 保留旧字段（connection_id, output, error, timestamp）兼容旧系统
- 新增字段（template_id, step_order, command_type, duration_ms）支持新架构
- **独立记录**：arthas_command_logs 不关联 task_logs，各自独立
- **template_id** 关联到 arthas_command_templates，记录使用的是哪个 Arthas 官网命令模板

---

#### A.3.8 tool_packages（工具包管理表）

**用途**：管理工具包（如 Arthas JAR、Profiler 工具等）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 工具包 ID |
| name | TEXT | NOT NULL UNIQUE | - | 工具包名称 |
| description | TEXT | - | NULL | 工具包描述 |
| source_type | TEXT | - | 'local' | 来源类型：local \| url |
| source_url | TEXT | - | NULL | 下载 URL |
| version | TEXT | - | NULL | 版本号 |
| checksum | TEXT | - | NULL | 校验和 |
| tool_type | TEXT | - | 'generic' | 工具类型：arthas \| profiler \| generic |
| file_path | TEXT | - | NULL | 文件路径 |
| file_name | TEXT | - | NULL | 文件名 |
| file_size | INTEGER | - | 0 | 文件大小（字节） |
| sha256 | TEXT | - | NULL | SHA256 校验值 |
| install_path | TEXT | - | NULL | 安装路径 |
| is_builtin | INTEGER | - | 0 | 是否内置：0=否 1=是 |
| last_verified_at | TIMESTAMP | - | NULL | 最后验证时间 |
| status | TEXT | - | 'active' | 状态：active \| inactive |
| created_by | INTEGER | FOREIGN KEY → users(id) | NULL | 创建人 ID |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 更新时间 |

---

#### A.3.9 task_definitions（任务定义表）

**用途**：定义可执行的任务（通用任务系统，重新设计字段）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 任务定义 ID |
| name | TEXT | NOT NULL | - | 任务名称 |
| execution_mode | TEXT | NOT NULL | 'node' | 执行模式：node \| pod \| connection |
| capability_id | INTEGER | FK → diagnosis_capabilities(id) | NULL | 关联诊断能力 ID（诊断任务时使用） |
| template_id | INTEGER | FOREIGN KEY → script_templates(id) | NULL | 关联脚本模板 ID（脚本任务时使用） |
| runtime | TEXT | - | NULL | 运行时：python \| shell（脚本任务时使用） |
| script_body | TEXT | - | NULL | 脚本内容（内联脚本） |
| timeout_seconds | INTEGER | - | 60 | 超时时间（秒） |
| params_json | TEXT | - | '{}' | 参数（JSON） |
| target_json | TEXT | - | '{}' | 目标配置（JSON） |
| status | TEXT | - | 'active' | 状态：active \| inactive |
| created_by | INTEGER | FOREIGN KEY → users(id) | NULL | 创建人 ID |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 更新时间 |

**外键约束**：`ON DELETE SET NULL`（template_id, created_by），`ON DELETE SET NULL`（capability_id）

**说明**：
- 通用任务系统，支持多种任务类型：
  - **诊断任务**：使用 `capability_id` 关联诊断能力
  - **脚本任务**：使用 `template_id` 关联脚本模板
  - **Pod/Node 任务**：使用 `script_body` 内联脚本
- 保留原有字段，兼容脚本任务、Pod 执行、Node 执行等场景

---

#### A.3.10 task_logs（任务执行日志表）

**用途**：统一记录所有执行日志（即时诊断、定时任务、通用任务）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | TEXT | PRIMARY KEY | - | 执行日志 ID (UUID) |
| task_id | INTEGER | FK → task_definitions(id) | NULL | 任务定义 ID（即时诊断时为 NULL） |
| capability_id | INTEGER | FK → diagnosis_capabilities(id) | NULL | 关联诊断能力 ID（即时诊断时不为 NULL） |
| user_id | INTEGER | FOREIGN KEY → users(id) | NULL | 执行人 ID |
| execution_mode | TEXT | NOT NULL | - | 执行模式：immediate \| scheduled \| manual |
| execution_type | TEXT | NOT NULL | - | 执行类型：diagnosis \| script \| pod_exec \| node_exec |
| target_json | TEXT | - | '{}' | 目标配置（JSON） |
| params_json | TEXT | - | '{}' | 执行参数（JSON） |
| status | TEXT | NOT NULL | 'pending' | 状态：pending \| running \| success \| failed \| cancelled |
| stdout | TEXT | - | NULL | 标准输出（脚本任务时使用） |
| stderr | TEXT | - | NULL | 标准错误（脚本任务时使用） |
| exit_code | INTEGER | - | NULL | 退出码（脚本任务时使用） |
| result_json | TEXT | - | NULL | 执行结果（结构化，诊断任务时使用） |
| error_message | TEXT | - | NULL | 错误信息 |
| duration_ms | INTEGER | - | NULL | 执行时长（毫秒） |
| work_dir | TEXT | - | NULL | 工作目录（脚本任务时使用） |
| started_at | TIMESTAMP | - | NULL | 开始时间 |
| finished_at | TIMESTAMP | - | NULL | 结束时间 |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |
| **retention_days** | INTEGER | - | 30 | **保留天数，超时后自动清理** |
| **is_archived** | INTEGER | - | 0 | **是否已归档：0=否 1=是** |

**索引**：
- `idx_task_logs_task_id` ON (task_id)
- `idx_task_logs_capability_id` ON (capability_id)
- `idx_task_logs_user_id` ON (user_id)
- `idx_task_logs_execution_mode` ON (execution_mode)
- `idx_task_logs_status` ON (status)
- `idx_task_logs_started_at` ON (started_at)

**外键约束**：`ON DELETE SET NULL`（task_id），`ON DELETE SET NULL`（capability_id）

**说明**：
- **即时诊断**：`task_id=NULL`，`capability_id≠NULL`，`execution_mode='immediate'`
- **定时任务**：`task_id≠NULL`，`capability_id` 可选，`execution_mode='scheduled'`
- **通用任务**：`task_id≠NULL`，`capability_id=NULL`，`execution_mode='manual'\|'scheduled'`

---

#### A.3.11 diagnosis_task_artifacts（诊断任务产物表）

**用途**：记录诊断任务执行产生的文件产物（重命名）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 产物 ID |
| run_id | TEXT | NOT NULL, FK → task_logs(id) | - | 关联执行日志 ID |
| name | TEXT | NOT NULL | - | 产物名称 |
| path | TEXT | NOT NULL | - | 文件路径 |
| size | INTEGER | - | 0 | 文件大小（字节） |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |

**外键约束**：`ON DELETE CASCADE`

---

#### A.3.12 diagnosis_task_schedules（诊断任务调度表）

**用途**：定义诊断任务定时调度配置（重命名）

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 调度配置 ID |
| task_id | INTEGER | NOT NULL, FK → task_definitions(id) | - | 任务定义 ID |
| user_id | INTEGER | FOREIGN KEY → users(id) | NULL | 创建人 ID |
| name | TEXT | NOT NULL | - | 调度名称 |
| schedule_type | TEXT | NOT NULL | 'interval' | 调度类型：interval \| cron |
| interval_seconds | INTEGER | - | NULL | 间隔秒数（schedule_type='interval' 时使用） |
| cron_expression | TEXT | - | NULL | Cron 表达式（schedule_type='cron' 时使用） |
| max_executions | INTEGER | - | 0 | 最大执行次数（0=无限制） |
| execution_count | INTEGER | - | 0 | 已执行次数 |
| timezone | TEXT | - | 'Asia/Shanghai' | 时区 |
| notify_on_failure | INTEGER | - | 1 | 失败时通知：0=否 1=是 |
| **connection_ttl** | INTEGER | - | 300 | **连接有效期（秒），超时后重新建立连接** |
| **retry_policy** | TEXT | - | '{"max_retries": 3, "backoff": "exponential", "initial_delay_ms": 1000}' | **重试策略（JSON）** |
| **alert_channels** | TEXT | - | '["email"]' | **告警通道：email \| dingtalk \| wechat** |
| status | TEXT | - | 'active' | 状态：active \| paused \| stopped |
| last_run_at | TIMESTAMP | - | NULL | 上次执行时间 |
| next_run_at | TIMESTAMP | - | NULL | 下次执行时间 |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 更新时间 |

**索引**：
- `idx_task_schedules_task_id` ON (task_id)
- `idx_task_schedules_status` ON (status)
- `idx_task_schedules_next_run_at` ON (next_run_at)

**外键约束**：`ON DELETE CASCADE`（task_id）

**retry_policy 示例**：
```json
{
  "max_retries": 3,
  "backoff": "exponential",
  "initial_delay_ms": 1000,
  "max_delay_ms": 30000
}
```

**说明**：
- **连接管理**：`connection_ttl` 控制连接有效期，超时后自动重连
- **重试策略**：支持指数退避（exponential）和固定延迟（fixed）
- **告警通道**：支持邮件、钉钉、企业微信

---

#### A.3.13 audit_logs（审计日志表）

**用途**：记录所有敏感操作，用于安全审计和合规追溯

| 字段名 | 类型 | 约束 | 默认值 | 说明 |
|--------|------|------|--------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | - | 日志 ID |
| user_id | INTEGER | NOT NULL, FK → users(id) | - | 操作用户 ID |
| action | TEXT | NOT NULL | - | 操作类型，如 "execute_diagnosis" |
| resource_type | TEXT | - | NULL | 资源类型，如 "diagnosis_capability" |
| resource_id | TEXT | - | NULL | 资源 ID |
| details | TEXT | - | NULL | 操作详情（JSON） |
| ip_address | TEXT | - | NULL | IP 地址 |
| user_agent | TEXT | - | NULL | 用户代理 |
| created_at | TIMESTAMP | - | CURRENT_TIMESTAMP | 创建时间 |

**说明**：审计日志不应归档，需永久保留（法规要求）

---

### A.4 表关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                        诊断能力模块                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  diagnosis_capabilities (核心表)                                │
│  ├── type='script' ──────→ script_templates (扩展表 1)         │
│  ├── type='arthas_command' ─→ arthas_command_templates (扩展 2)│
│  ├── type='diagnosis_scenario' ─→ diagnosis_scenario_steps     │
│  └── type='ai_diagnosis' ────→ ai_diagnosis_handlers           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ↓ (即时诊断直接执行)
┌─────────────────────────────────────────────────────────────────┐
│                        任务管理模块（通用）                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  task_logs (统一执行日志)                                       │
│       │                                                         │
│       ├── execution_mode='immediate' (即时诊断)                │
│       │   └── capability_id → diagnosis_capabilities            │
│       │                                                         │
│       ├── execution_mode='scheduled' (定时任务)                │
│       │   └── task_id → task_definitions                        │
│       │                                                         │
│       └── execution_mode='manual' (通用任务)                   │
│           └── task_id → task_definitions                        │
│                                                                 │
│  arthas_command_logs (Arthas 命令日志 - 独立记录)               │
│       └── connection_id → connections (通过连接关联)            │
│                                                                 │
│  task_schedules ──→ task_definitions                            │
│  task_artifacts ──→ task_logs                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        工具包管理模块                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  tool_packages ──→ script_templates                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        安全审计模块                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  audit_logs (审计日志 - 记录所有敏感操作)                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 13. 模块架构与前端交互设计

### 13.1 三个模块职责划分

系统采用 **三模块分离** 架构，职责清晰、数据解耦：

| 模块 | 核心职责 | 数据源 | 执行方式 | 典型场景 |
|------|---------|--------|---------|----------|
| **任务中心** | 任务生命周期管理 | `task_definitions` + `task_logs` | 手动/定时 | 定时巡检、脚本执行 |
| **诊断能力** | Arthas 在线诊断 | `diagnosis_capabilities` | **即时执行** | 性能分析、问题排查 |
| **工具箱** | 工具包分发管理 | `tool_packages` + `script_templates` | 手动分发 | 工具上传、版本管理 |

**架构关系**：
```
┌─────────────────────────────────────────────────────┐
│                   前端交互层                          │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ 任务中心  │  │  诊断能力     │  │   工具箱      │  │
│  │ (任务管理)│  │ (在线诊断)    │  │ (工具包管理)   │  │
│  └──────────┘  └──────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│                   统一执行层                          │
│         ArthasCommandExecutor (异步+线程池)           │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│                   数据模型层                          │
│  ┌──────────────────┐  ┌──────────────────────┐     │
│  │ diagnosis_       │  │ task_definitions     │     │
│  │ capabilities     │  │ task_logs            │     │
│  │ + 4 扩展表       │  │ task_schedules       │     │
│  └──────────────────┘  └──────────────────────┘     │
│  ┌──────────────────┐                                │
│  │ tool_packages    │                                │
│  │ script_templates │                                │
│  └──────────────────┘                                │
└─────────────────────────────────────────────────────┘
```

---

### 13.2 诊断能力模块（核心）

#### 13.2.1 能力分层架构

系统采用 **4 层分级** 组织诊断能力，由简到繁：

```
诊断能力（4 层分级）
│
├── Level 1: 快捷工具（快捷入口，零配置）
│   ├── JVM Dashboard
│   ├── 线程快照
│   └── GC 统计
│
├── Level 2: 诊断模板（需填写参数）
│   ├── Trace 调用链分析
│   ├── Watch 方法监控
│   └── Profiler CPU 分析
│
├── Level 3: 场景方案（多步骤编排）
│   ├── 接口响应慢诊断（trace → watch → profiler）
│   └── CPU 飙升排查（dashboard → thread → profiler）
│
└── Level 4: 智能诊断（AI 分析）
    ├── CPU 性能瓶颈分析
    └── 内存泄漏检测
```

**分层设计原则**：
- **Level 1**：一键执行，零配置，适合日常巡检
- **Level 2**：需要用户输入关键参数（类名、方法名等），适合精准诊断
- **Level 3**：多步骤自动编排，支持跨步数据传递（`${stepN.field}`），适合复杂场景
- **Level 4**：AI 驱动，自动分析多维度数据生成诊断报告，适合根因分析

#### 13.2.2 前端交互设计

**页面布局**：
```
┌──────────────────────────────────────────────┐
│  🔍 搜索能力                    [筛选] [排序]  │
├──────────────────────────────────────────────┤
│                                              │
│  📌 快捷工具（Level 1）                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│  │Dashboard│ │线程快照  │ │GC 统计  │  ← 点击即执行
│  │  5s     │ │  10s    │ │  8s     │        │
│  └─────────┘ └─────────┘ └─────────┘        │
│                                              │
│  🔧 诊断模板（Level 2）                       │
│  ┌──────────────────────────────────┐        │
│  │ Trace 调用链分析          [执行]  │  ← 点击弹出参数表单
│  │ 追踪方法调用链路，定位慢方法      │        │
│  │ ⏱ 30s | 🏷️ 中风险               │        │
│  └──────────────────────────────────┘        │
│                                              │
│  📋 场景方案（Level 3）                       │
│  ┌──────────────────────────────────┐        │
│  │ 接口响应慢诊断            [执行]  │  ← 点击显示步骤预览
│  │ Step1: trace → Step2: watch → ...│        │
│  │ ⏱ 120s | 🏷️ 中风险              │        │
│  └──────────────────────────────────┘        │
│                                              │
│  🤖 智能诊断（Level 4）                       │
│  ┌──────────────────────────────────┐        │
│  │ CPU 性能瓶颈分析          [执行]  │  ← 点击调用 AI 处理器
│  │ 基于多维度数据自动分析瓶颈        │        │
│  │ ⏱ 60s | 🏷️ 低风险               │        │
│  └──────────────────────────────────┘        │
└──────────────────────────────────────────────┘
```

**交互流程**：

```
快捷工具（Level 1）：
用户点击卡片 → 直接执行 → 显示结果

诊断模板（Level 2）：
用户点击"执行" → 弹出参数表单 → 填写参数 → 校验 → 执行 → 显示结果

场景方案（Level 3）：
用户点击"执行" → 显示步骤预览 → 确认 → 执行 → 实时进度展示 → 显示结果

智能诊断（Level 4）：
用户点击"执行" → 调用 AI 处理器 → 分析中... → 生成诊断报告
```

#### 13.2.3 关键交互优化点

**1. 参数表单动态生成**

根据 `parameters_schema` JSON 配置动态渲染表单：

```json
{
  "parameters_schema": [
    {"name": "class", "label": "类名", "type": "text", "required": true, "pattern": "^[\\w.]+$"},
    {"name": "method", "label": "方法名", "type": "text", "default": "*"},
    {"name": "threshold", "label": "阈值(ms)", "type": "number", "min": 1, "max": 10000}
  ]
}
```

**表单渲染规则**：
- `type=text` → `<input type="text">`
- `type=number` → `<input type="number" min="1" max="10000">`
- `type=select` → `<select>` 下拉框
- `required=true` → 必填项标记 `*`
- `pattern` → 客户端正则校验

**2. 场景方案执行进度实时展示**

```
执行中...
┌─────────────────────────────────────┐
│ Step 1/3: Trace 方法调用    ✅ 完成  │  ← 绿色勾选
│ Step 2/3: Watch 方法监控    🔄 执行中│  ← 旋转图标
│ Step 3/3: Profiler CPU 分析 ⏸️ 等待  │  ← 灰色暂停
└─────────────────────────────────────┘

[取消执行] [查看日志]
```

**实现方式**：
- **HTTP 轮询**（每2秒查询执行状态，当前系统无 WebSocket 基础设施）
- 前端实时更新进度条
- 支持中途取消（`fail_fast` 控制）

**3. 步骤预览面板（执行前确认）**

场景方案执行前展示完整命令预览，防止参数替换错误：

```
┌─────────────────────────────────────────────┐
│ 场景方案：接口响应慢诊断                      │
├─────────────────────────────────────────────┤
│ Step 1/3: Trace 方法调用                     │
│   命令: trace com.example.OrderService      │
│         createOrder -n 10 '#cost > .5'       │
│   超时: 30s  |  失败策略: 停止执行            │
├─────────────────────────────────────────────┤
│ Step 2/3: Watch 方法参数                     │
│   命令: watch com.example.OrderService      │
│         createOrder '{params, returnObj}'    │
│   超时: 20s  |  失败策略: 继续执行            │
├─────────────────────────────────────────────┤
│ Step 3/3: Profiler CPU 分析                  │
│   命令: profiler start --event cpu           │
│         --duration 30                        │
│   超时: 60s  |  失败策略: 停止执行            │
├─────────────────────────────────────────────┤
│ [取消] [确认执行]                            │
└─────────────────────────────────────────────┘
```

**4. 全局执行指示器**

顶部导航栏显示正在执行的诊断任务数，支持快速定位：

```javascript
// 全局执行指示器（顶部导航栏）
class ExecutionIndicator {
  static render() {
    const activeCount = DiagnosisContext.getActiveCount();
    if (activeCount === 0) return '';
    
    return `
      <div class="execution-indicator" onclick="showActiveExecutions()">
        <span class="spinner"></span>
        ${activeCount} 个诊断执行中
      </div>
    `;
  }
}
```

**5. 诊断结果渲染规范**

根据能力类型自动选择渲染模式：

| 能力类型 | 渲染模式 | 展示方式 |
|---------|---------|----------|
| Arthas Trace | `table` | 结构化表格（线程/方法/耗时） |
| Profiler 报告 | `file_link` | 文件下载链接 |
| AI 诊断 | `markdown` | Markdown 渲染 |
| 场景方案 | `multi_step` | 多步骤结果展示 |
| 其他命令 | `text` | 原始文本 |

```javascript
class DiagnosisResultRenderer {
  static render(result) {
    switch (result.render_mode) {
      case 'table':
        return this.renderTraceTable(result.structured_data);
      case 'file_link':
        return this.renderFileLinks(result.structured_data);
      case 'markdown':
        return `<div class="markdown-body">${marked.parse(result.raw_output)}</div>`;
      case 'multi_step':
        return this.renderMultiStep(result.structured_data);
      default:
        return `<pre>${escapeHtml(result.raw_output)}</pre>`;
    }
  }
}
```

---

### 13.3 任务中心模块

#### 13.3.1 核心能力

```
任务中心
│
├── 任务定义管理（task_definitions）
│   ├── 创建任务（脚本/Pod/Node/诊断能力）
│   ├── 定时调度（Cron 表达式）
│   └── 任务配置保存
│
├── 执行日志查询（task_logs）
│   ├── 按任务/时间/状态过滤
│   ├── 查看执行详情
│   └── 下载产物（profiler 报告等）
│
└── 定时任务管理（task_schedules）
    ├── 启用/禁用
    ├── 连接健康检查
    └── 失败告警
```

#### 13.3.2 前端交互设计

**页面布局**：
```
┌──────────────────────────────────────────────┐
│  任务中心                                      │
│  [新建任务] [执行日志] [定时任务]              │
├──────────────────────────────────────────────┤
│                                              │
│  任务列表                                     │
│  ┌──────────────────────────────────────┐    │
│  │ 任务名称      类型    状态   操作     │    │
│  ├──────────────────────────────────────┤    │
│  │ CPU 巡检      诊断    ✅     [详情]   │    │
│  │ 日志清理      脚本    ⏸️     [编辑]   │    │
│  │ 内存监控      定时    ⏰     [禁用]   │    │
│  └──────────────────────────────────────┘    │
│                                              │
│  执行日志（最近 24 小时）                      │
│  ┌──────────────────────────────────────┐    │
│  │ 时间          任务        状态  耗时   │    │
│  ├──────────────────────────────────────┤    │
│  │ 10:30:25   CPU 巡检    ✅    35s     │    │
│  │ 09:15:10   日志清理    ❌    12s     │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

**新建任务流程**：
```
1. 选择任务类型：脚本 / Pod 命令 / 诊断能力
2. 填写任务配置：
   - 脚本：上传文件 / 输入代码
   - Pod 命令：选择 Pod + 输入命令
   - 诊断能力：选择能力 + 填写参数
3. 设置调度策略：
   - 手动执行
   - 定时执行（Cron 表达式）
4. 保存任务
```

**定时任务健康状态展示**：
```
┌─────────────────────────────────────┐
│ 定时任务：CPU 巡检                    │
│ 下次执行：明天 02:00                  │
│                                      │
│ 连接状态：                            │
│ Pod: udc-7cc5-abc123                │
│ 健康度：✅ 正常 (TTL: 300s)          │
│ 上次检查：10:25:30                   │
│                                      │
│ 重试策略：指数退避 (最大 3 次)        │
│ 告警通道：📧 邮件                     │
└─────────────────────────────────────┘
```

---

### 13.4 工具箱模块

#### 13.4.1 核心能力

```
工具箱
│
├── 工具包管理（tool_packages）
│   ├── 上传工具包（zip）
│   ├── 版本管理
│   └── 分发到 Pod
│
├── 脚本模板（script_templates）
│   ├── 创建脚本模板
│   ├── 关联诊断能力（capability_id）
│   └── 参数化配置
│
└── 工具使用记录
    ├── 下载统计
    └── 执行记录
```

#### 13.4.2 前端交互设计

**页面布局**：
```
┌──────────────────────────────────────────────┐
│  工具箱                                        │
│  [上传工具包] [新建脚本模板]                   │
├──────────────────────────────────────────────┤
│                                              │
│  工具包列表                                   │
│  ┌──────────────────────────────────────┐    │
│  │ 名称        版本   大小    操作       │    │
│  ├──────────────────────────────────────┤    │
│  │ Arthas 工具  3.7.1  50MB  [分发]     │    │
│  │ Profiler    2.0.0   8MB  [分发]      │    │
│  └──────────────────────────────────────┘    │
│                                              │
│  脚本模板                                     │
│  ┌──────────────────────────────────────┐    │
│  │ 名称          运行时    关联能力      │    │
│  ├──────────────────────────────────────┤    │
│  │ CPU 分析脚本  Python   CPU 性能分析   │    │
│  │ 日志收集      Shell    -             │    │
│  └──────────────────────────────────────┘    │
└──────────────────────────────────────────────┘
```

---

### 13.5 数据流转关系

```
用户操作
  ↓
前端组件（diagnosis.js / task-center.js / toolbox.js）
  ↓
API 调用（/api/diagnosis/execute / /api/tasks/* / /api/toolbox/*）
  ↓
后端处理
  ├─ 诊断能力 → diagnosis_capabilities → ArthasCommandExecutor → task_logs
  ├─ 任务中心 → task_definitions → TaskScheduler → task_logs
  └─ 工具箱 → tool_packages → script_templates → task_logs
  ↓
统一执行日志（task_logs）
  ↓
前端展示（执行历史 / 日志查询 / 产物下载）
```

**关键设计**：
- ✅ 三模块前端独立，后端通过 `task_logs` 统一聚合
- ✅ 诊断能力即时执行，无需创建 `task_definition`
- ✅ 所有执行记录统一存储，支持跨模块查询

---

### 13.5.1 并发控制模型（P0 关键）

**问题**：多用户同时执行诊断能力时，需防止系统过载和 Pod 命令冲突。

**架构设计**：

```python
# backend/diagnosis_executor.py

class DiagnosisExecutorPool:
    """诊断执行器线程池（并发控制）"""
    
    def __init__(self):
        # 全局线程池（限制并发执行数）
        self.global_pool = ThreadPoolExecutor(
            max_workers=10,  # 最多10个并发诊断
            thread_name_prefix='diagnosis-'
        )
        
        # Pod 级别锁（防止同一 Pod 被并发诊断）
        self.pod_locks = defaultdict(threading.Lock)
    
    def execute(self, connection, capability, params, user_id):
        """提交诊断任务（带并发控制）"""
        
        # 1. 检查全局并发数
        if self.global_pool._work_queue.qsize() >= 10:
            raise ConcurrencyError('系统繁忙，请稍后重试')
        
        # 2. 获取 Pod 级别锁
        pod_key = f"{connection.cluster_name}/{connection.namespace}/{connection.pod_name}"
        pod_lock = self.pod_locks[pod_key]
        
        if not pod_lock.acquire(blocking=False):
            raise ConcurrencyError(f'Pod {pod_key} 正在被诊断，请稍后')
        
        try:
            # 3. 提交到线程池
            future = self.global_pool.submit(
                self._execute_with_lock,
                connection, capability, params, user_id, pod_lock
            )
            return {'ok': True, 'future': future}
        except Exception as e:
            pod_lock.release()
            raise
```

**关键设计决策**：
| 决策点 | 方案 | 理由 |
|--------|------|------|
| 全局并发数 | 10 | Arthas HTTP API 单 Pod 并发能力有限 |
| Pod 级别锁 | 互斥锁 | 防止多用户同时操作同一 Pod 导致命令冲突 |
| 超时控制 | 单步骤 60s | 防止慢命令阻塞线程池 |

---

### 13.5.2 连接生命周期管理（P0 关键）

**问题**：诊断执行过程中连接断开如何处理？

**架构设计**：

```python
class ConnectionAwareExecutor:
    """连接感知执行器"""
    
    def execute_with_connection_guard(self, connection, capability, params):
        """带连接保护的诊断执行"""
        
        execution_id = str(uuid4())
        
        # 1. 注册连接监听器
        def on_connection_lost():
            """连接断开回调"""
            db.update('task_logs', {
                'status': 'failed',
                'error_message': 'Arthas 连接已断开',
                'finished_at': datetime.now(),
            }, {'id': execution_id})
            
            # 如果是场景方案，清理已执行的命令
            if capability['type'] == 'diagnosis_scenario':
                self._rollback_scenario_steps(execution_id)
        
        ConnectionManager.register_listener(connection.id, on_connection_lost)
        
        try:
            # 2. 执行诊断
            result = self._execute(connection, capability, params)
            return result
        finally:
            # 3. 移除监听器
            ConnectionManager.unregister_listener(connection.id, on_connection_lost)
```

**前端交互设计**：

```javascript
// 连接断开时的用户体验
class DiagnosisExecutor {
  async execute(capabilityId, params) {
    try {
      return await api.executeDiagnosis(capabilityId, params);
    } catch (e) {
      if (e.message.includes('连接已断开')) {
        this.showConnectionLostDialog({
          title: 'Arthas 连接已断开',
          message: '诊断执行过程中连接中断，请重新建立连接后重试',
          action: '重新连接',
          onAction: () => switchTab('connections')
        });
      }
      throw e;
    }
  }
}
```

---

### 13.5.3 能力版本管理（P1）

**问题**：管理员修改诊断能力后，历史执行记录如何追溯？

**数据模型**：

```sql
-- 增加版本号字段
ALTER TABLE diagnosis_capabilities ADD COLUMN version INTEGER DEFAULT 1;

-- 执行记录关联版本号
ALTER TABLE task_logs ADD COLUMN capability_version INTEGER;

-- 版本历史表
CREATE TABLE capability_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    parameters_schema TEXT,
    extension_snapshot TEXT,  -- 扩展表数据快照
    changed_by INTEGER,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id),
    UNIQUE(capability_id, version)
);
```

**版本管理流程**：

```python
class CapabilityVersionManager:
    """能力版本管理器"""
    
    def update_capability(self, capability_id, new_data):
        """更新能力（自动创建版本快照）"""
        
        # 1. 获取当前版本
        current = db.get('diagnosis_capabilities', capability_id)
        current_version = current['version']
        
        # 2. 创建版本快照
        db.insert('capability_versions', {
            'capability_id': capability_id,
            'version': current_version,
            'parameters_schema': current['parameters_schema'],
            'extension_snapshot': self._capture_extension_snapshot(capability_id),
            'changed_by': session['user_id'],
        })
        
        # 3. 更新能力（版本号 +1）
        db.update('diagnosis_capabilities', {
            **new_data,
            'version': current_version + 1,
        }, {'id': capability_id})
```

---

### 13.5.4 权限模型与数据隔离（P0 关键）

**问题**：用户 A 创建的诊断能力，用户 B 能否执行？

**数据模型**：

```sql
-- 能力可见性控制
ALTER TABLE diagnosis_capabilities ADD COLUMN visibility TEXT DEFAULT 'public';
-- public: 所有用户可见
-- private: 仅创建者可见
-- group: 特定用户组可见

-- 用户组关联表
CREATE TABLE capability_user_groups (
    capability_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (capability_id, group_id),
    FOREIGN KEY (capability_id) REFERENCES diagnosis_capabilities(id),
    FOREIGN KEY (group_id) REFERENCES user_groups(id)
);
```

**权限检查逻辑**：

```python
def check_capability_permission(capability_id, user_id):
    """检查用户是否有权限执行诊断能力"""
    
    capability = db.get('diagnosis_capabilities', capability_id)
    
    # 1. 管理员无限制
    if is_admin(user_id):
        return True
    
    # 2. 公开能力
    if capability['visibility'] == 'public':
        return True
    
    # 3. 私有能力
    if capability['visibility'] == 'private':
        return capability['created_by'] == user_id
    
    # 4. 用户组能力
    if capability['visibility'] == 'group':
        user_groups = db.query(
            'SELECT group_id FROM user_group_members WHERE user_id = ?',
            (user_id,)
        )
        group_ids = [g['group_id'] for g in user_groups]
        
        allowed_groups = db.query(
            'SELECT group_id FROM capability_user_groups WHERE capability_id = ?',
            (capability_id,)
        )
        allowed_group_ids = [g['group_id'] for g in allowed_groups]
        
        return any(gid in allowed_group_ids for gid in group_ids)
    
    return False
```

---

### 13.5.5 前端状态管理（DiagnosisContext）

**问题**：三个模块独立，但存在共享状态（当前连接、执行状态）。

**架构设计**：

```javascript
// static/js/core/diagnosis-context.js

const DiagnosisContext = {
  currentConnection: null,
  activeExecutions: new Map(),  // executionId → {status, capabilityId, startTime}
  listeners: new Set(),
  
  // 连接变化处理
  onConnectionChange(newConn) {
    const oldConn = this.currentConnection;
    
    // 连接切换，取消所有正在执行的诊断
    if (newConn?.id !== oldConn?.id) {
      this.activeExecutions.forEach((exec, id) => {
        if (exec.status === 'running') {
          this.cancelExecution(id);
        }
      });
      this.activeExecutions.clear();
    }
    
    this.currentConnection = newConn;
  },
  
  // 注册执行任务
  registerExecution(executionId, capabilityId) {
    this.activeExecutions.set(executionId, {
      status: 'running',
      capabilityId,
      startTime: Date.now(),
    });
  },
  
  // 获取活跃执行数
  getActiveCount() {
    return Array.from(this.activeExecutions.values())
      .filter(e => e.status === 'running').length;
  }
};

window.DiagnosisContext = DiagnosisContext;
```

---

### 13.6 实施优先级

| 阶段 | 模块 | 优先级 | 工期 | 核心交付 | 关键架构改进 |
|------|------|--------|------|----------|---------------|
| Phase 0-2 | 诊断能力（后端） | P0 | 8 天 | 数据库迁移 + 能力框架 + 执行器 | **统一 task_logs + 并发控制 + 连接生命周期** |
| Phase 3-4 | 诊断能力（前端） | P0 | 7 天 | 能力卡片 + 参数表单 + 场景方案 | **HTTP 轮询 + DiagnosisContext + 结果渲染规范** |
| Phase 5 | 权限模型 | P0 | 3 天 | visibility + 用户组控制 | **数据隔离 + 能力权限检查** |
| Phase 6 | 任务中心增强 | P1 | 5 天 | 连接健康检查 + 定时清理 | 查询逻辑统一 |
| Phase 7 | 能力版本管理 | P1 | 3 天 | 版本快照 + 历史追溯 | capability_versions 表 |
| Phase 8 | 工具箱重构 | P2 | 待定 | 工具包管理 + 脚本模板 | 无 |

**核心原则**：
1. **先完成诊断能力（P0）**：系统核心价值所在
2. **再构建基础设施（P0）**：并发控制/连接管理/权限模型
3. **再优化任务中心（P1）**：增强调度能力
4. **最后重构工具箱（P2）**：与诊断能力解耦

---

**文档结束**
