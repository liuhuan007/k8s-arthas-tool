# 数据模型评审报告

> **评审日期**: 2026-05-24
> **评审范围**: docs/superpowers/specs/06-data-model.md
> **评审状态**: 完成

---

## 目录

1. [评审概述](#1-评审概述)
2. [skill_registry表分析](#2-skill_registry表分析)
3. [task_logs表分析](#3-task_logs表分析)
4. [step_logs表分析](#4-step_logs表分析)
5. [diagnosis_capabilities表分析](#5-diagnosis_capabilities表分析)
6. [多余字段清单](#6-多余字段清单)
7. [优化建议](#7-优化建议)
8. [优化后的表结构](#8-优化后的表结构)

---

## 1. 评审概述

### 1.1 评审目标

- 识别数据模型设计中的不合理之处
- 识别现有表设计中的多余字段
- 提出优化建议

### 1.2 评审标准

| 标准 | 说明 |
|------|------|
| **必要性** | 字段是否必须存在于该表中 |
| **冗余性** | 字段是否与其他字段或表重复 |
| **一致性** | 字段命名和类型是否一致 |
| **可维护性** | 字段是否易于理解和维护 |

---

## 2. skill_registry表分析

### 2.1 当前表结构

```sql
CREATE TABLE skill_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    category TEXT,
    level INTEGER,
    risk_level TEXT,
    estimated_duration INTEGER,
    source TEXT,
    status TEXT DEFAULT 'draft',
    definition_body TEXT,      -- ⚠️ 可能多余
    definition_path TEXT,      -- ⚠️ 可能多余
    dsl TEXT,
    parameters_schema TEXT,
    llm_prompt TEXT,
    arthas_command TEXT,
    handler TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
);
```

### 2.2 问题分析

| 字段 | 问题 | 建议 |
|------|------|------|
| `definition_body` | 与 `dsl`、`arthas_command`、`handler` 重复 | **删除** - 定义内容已分散到具体字段 |
| `definition_path` | 导入后路径不再需要 | **删除** - 导入后应解析到具体字段 |
| `llm_prompt` | 与 `handler` 可能有重叠 | **保留** - prompt是静态配置，handler是执行逻辑 |
| `handler` | 与 `llm_prompt` 可能有重叠 | **保留** - 两者职责不同 |

### 2.3 优化建议

**删除字段**：
- `definition_body` - 定义内容已分散到dsl/arthas_command/handler
- `definition_path` - 导入后应解析到具体字段，不需要保留路径

**保留字段**：
- `dsl` - 场景方案的执行步骤
- `arthas_command` - 快捷工具/诊断模板的命令
- `handler` - AI诊断的处理器
- `llm_prompt` - 大模型提示词
- `parameters_schema` - 参数定义

---

## 3. task_logs表分析

### 3.1 当前表结构

```sql
CREATE TABLE task_logs (
    id TEXT PRIMARY KEY,
    task_id INTEGER,
    capability_id INTEGER,
    user_id INTEGER,
    execution_mode TEXT,
    execution_type TEXT,
    capability_name TEXT,        -- ⚠️ 冗余
    rendered_command TEXT,       -- ⚠️ 可能多余
    run_type TEXT,               -- ⚠️ 与execution_type重叠
    anomaly_event_id INTEGER,
    connection_snapshot_json TEXT,
    capability_snapshot_json TEXT,
    ai_analysis_result TEXT,
    capability_version INTEGER,
    target_json TEXT,
    params_json TEXT,
    status TEXT,
    stdout TEXT,
    stderr TEXT,
    exit_code INTEGER,
    result_json TEXT,
    error_message TEXT,
    duration_ms INTEGER,
    log_path TEXT,               -- ⚠️ 可能多余
    retention_days INTEGER,      -- ⚠️ 可能多余
    is_archived INTEGER,         -- ⚠️ 可能多余
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP
);
```

### 3.2 问题分析

| 字段 | 问题 | 建议 |
|------|------|------|
| `capability_name` | 与 `capability_snapshot_json` 重复 | **删除** - 快照中已包含名称 |
| `rendered_command` | 与 `stdout`/`stderr` 重叠 | **删除** - 命令输出已在stdout中 |
| `run_type` | 与 `execution_type` 重叠 | **合并** - 统一使用 `execution_type` |
| `log_path` | P0阶段不需要 | **删除** - P0阶段直接存储在数据库 |
| `retention_days` | 归档逻辑应在应用层 | **删除** - 归档策略由应用层控制 |
| `is_archived` | 归档逻辑应在应用层 | **删除** - 归档策略由应用层控制 |
| `target_json` | 与 `connection_snapshot_json` 重叠 | **合并** - 统一使用快照字段 |

### 3.3 优化建议

**删除字段**：
- `capability_name` - 冗余，快照中已包含
- `rendered_command` - 冗余，命令输出在stdout中
- `log_path` - P0阶段不需要
- `retention_days` - 归档逻辑在应用层
- `is_archived` - 归档逻辑在应用层
- `target_json` - 与快照字段重叠

**合并字段**：
- `run_type` → 合并到 `execution_type`

**保留字段**：
- `id` - 主键
- `task_id` - 关联定时任务
- `capability_id` - 关联诊断能力
- `user_id` - 执行用户
- `execution_mode` - 执行模式（immediate/scheduled/manual）
- `execution_type` - 执行类型（diagnosis/script/pod_exec）
- `connection_snapshot_json` - 连接快照
- `capability_snapshot_json` - 能力快照
- `ai_analysis_result` - AI分析结果
- `capability_version` - 能力版本
- `params_json` - 执行参数
- `status` - 执行状态
- `stdout` - 标准输出
- `stderr` - 标准错误
- `exit_code` - 退出码
- `result_json` - 结构化结果
- `error_message` - 错误信息
- `duration_ms` - 执行时长
- `started_at` - 开始时间
- `finished_at` - 结束时间
- `created_at` - 创建时间

---

## 4. step_logs表分析

### 4.1 当前表结构

```sql
CREATE TABLE step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    step_name TEXT,
    step_type TEXT,
    command TEXT,
    output TEXT,
    status TEXT DEFAULT 'pending',
    duration_ms INTEGER,
    error_message TEXT,
    llm_analysis TEXT,          -- ⚠️ 可能多余
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 问题分析

| 字段 | 问题 | 建议 |
|------|------|------|
| `llm_analysis` | 不是每个step都有LLM分析 | **删除** - LLM分析结果存储在task_logs中 |
| `step_name` | 与 `step_type` 可能有重叠 | **保留** - step_name是用户可读的名称 |

### 4.3 优化建议

**删除字段**：
- `llm_analysis` - LLM分析结果存储在task_logs.ai_analysis_result中

**保留字段**：
- `id` - 主键
- `run_id` - 关联task_logs
- `step_number` - 步骤序号
- `step_name` - 步骤名称（用户可读）
- `step_type` - 步骤类型（arthas_command/llm_analysis/get_pod_status）
- `command` - 执行的命令
- `output` - 命令输出
- `status` - 执行状态
- `duration_ms` - 执行时长
- `error_message` - 错误信息
- `created_at` - 创建时间

---

## 5. diagnosis_capabilities表分析

### 5.1 当前表结构

```sql
CREATE TABLE diagnosis_capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    arthas_command TEXT,
    parameters_schema TEXT,
    risk_level TEXT DEFAULT 'low',
    estimated_duration INTEGER DEFAULT 10,
    prerequisites TEXT DEFAULT '[]',
    related_capabilities TEXT DEFAULT '[]',
    steps_json TEXT,
    handler TEXT,
    confirm_required INTEGER DEFAULT 0,
    visibility TEXT DEFAULT 'public',   -- ⚠️ P0阶段不需要
    version INTEGER DEFAULT 1,         -- ⚠️ P0阶段不需要
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 问题分析

| 字段 | 问题 | 建议 |
|------|------|------|
| `visibility` | P0阶段不需要权限控制 | **删除** - P0阶段所有能力公开 |
| `version` | 与skill_registry的版本管理重复 | **删除** - 版本管理在skill_registry中 |
| `prerequisites` | P0阶段不需要前置条件 | **保留** - 未来扩展用 |
| `related_capabilities` | P0阶段不需要关联能力 | **保留** - 未来扩展用 |

### 5.3 优化建议

**删除字段**：
- `visibility` - P0阶段不需要
- `version` - 版本管理在skill_registry中

**保留字段**：
- `id` - 主键
- `name` - 能力名称
- `category` - 能力分类
- `level` - 能力层级
- `description` - 能力描述
- `arthas_command` - Arthas命令
- `parameters_schema` - 参数Schema
- `risk_level` - 风险等级
- `estimated_duration` - 预计时长
- `prerequisites` - 前置条件（未来扩展）
- `related_capabilities` - 关联能力（未来扩展）
- `steps_json` - 场景方案步骤
- `handler` - AI处理器
- `confirm_required` - 是否需要确认
- `created_by` - 创建人
- `created_at` - 创建时间
- `updated_at` - 更新时间

---

## 6. 多余字段清单

### 6.1 总体清单

| 表 | 字段 | 问题类型 | 建议 |
|----|------|---------|------|
| **skill_registry** | `definition_body` | 冗余 | 删除 |
| **skill_registry** | `definition_path` | 冗余 | 删除 |
| **task_logs** | `capability_name` | 冗余 | 删除 |
| **task_logs** | `rendered_command` | 冗余 | 删除 |
| **task_logs** | `run_type` | 重叠 | 合并到execution_type |
| **task_logs** | `log_path` | P0不需要 | 删除 |
| **task_logs** | `retention_days` | 应用层逻辑 | 删除 |
| **task_logs** | `is_archived` | 应用层逻辑 | 删除 |
| **task_logs** | `target_json` | 重叠 | 合并到快照字段 |
| **step_logs** | `llm_analysis` | 冗余 | 删除 |
| **diagnosis_capabilities** | `visibility` | P0不需要 | 删除 |
| **diagnosis_capabilities** | `version` | 冗余 | 删除 |

### 6.2 统计

- **删除字段**: 12个
- **合并字段**: 2个（run_type→execution_type, target_json→快照字段）

---

## 7. 优化建议

### 7.1 删除多余字段

**skill_registry表**：
- 删除 `definition_body` - 定义内容已分散到dsl/arthas_command/handler
- 删除 `definition_path` - 导入后应解析到具体字段

**task_logs表**：
- 删除 `capability_name` - 冗余，快照中已包含
- 删除 `rendered_command` - 冗余，命令输出在stdout中
- 删除 `log_path` - P0阶段不需要
- 删除 `retention_days` - 归档逻辑在应用层
- 删除 `is_archived` - 归档逻辑在应用层
- 删除 `target_json` - 与快照字段重叠

**step_logs表**：
- 删除 `llm_analysis` - LLM分析结果存储在task_logs中

**diagnosis_capabilities表**：
- 删除 `visibility` - P0阶段不需要
- 删除 `version` - 版本管理在skill_registry中

### 7.2 合并字段

**task_logs表**：
- `run_type` → 合并到 `execution_type`

### 7.3 新增字段

**task_logs表**：
- 新增 `progress` (REAL) - 执行进度（0.0-1.0）
- 新增 `current_step` (INTEGER) - 当前步骤号

---

## 8. 优化后的表结构

### 8.1 skill_registry表（优化后）

```sql
CREATE TABLE skill_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    category TEXT,
    level INTEGER,
    risk_level TEXT,
    estimated_duration INTEGER,
    source TEXT,
    status TEXT DEFAULT 'draft',
    dsl TEXT,
    parameters_schema TEXT,
    llm_prompt TEXT,
    arthas_command TEXT,
    handler TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
);
```

### 8.2 task_logs表（优化后）

```sql
CREATE TABLE task_logs (
    id TEXT PRIMARY KEY,
    task_id INTEGER,
    capability_id INTEGER,
    user_id INTEGER,
    execution_mode TEXT NOT NULL,
    execution_type TEXT NOT NULL,
    connection_snapshot_json TEXT,
    capability_snapshot_json TEXT,
    ai_analysis_result TEXT,
    capability_version INTEGER,
    params_json TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    progress REAL DEFAULT 0.0,
    current_step INTEGER,
    stdout TEXT,
    stderr TEXT,
    exit_code INTEGER,
    result_json TEXT,
    error_message TEXT,
    duration_ms INTEGER,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_task_logs_capability_id ON task_logs(capability_id);
CREATE INDEX idx_task_logs_execution_mode ON task_logs(execution_mode);
CREATE INDEX idx_task_logs_execution_type ON task_logs(execution_type);
CREATE INDEX idx_task_logs_status ON task_logs(status);
CREATE INDEX idx_task_logs_created_at ON task_logs(created_at);
```

### 8.3 step_logs表（优化后）

```sql
CREATE TABLE step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    step_name TEXT,
    step_type TEXT,
    command TEXT,
    output TEXT,
    status TEXT DEFAULT 'pending',
    duration_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES task_logs(id)
);

CREATE INDEX idx_step_logs_run_id ON step_logs(run_id);
```

### 8.4 diagnosis_capabilities表（优化后）

```sql
CREATE TABLE diagnosis_capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    arthas_command TEXT,
    parameters_schema TEXT DEFAULT '{}',
    risk_level TEXT DEFAULT 'low',
    estimated_duration INTEGER DEFAULT 10,
    prerequisites TEXT DEFAULT '[]',
    related_capabilities TEXT DEFAULT '[]',
    steps_json TEXT,
    handler TEXT,
    confirm_required INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_diag_caps_category_level ON diagnosis_capabilities(category, level);
```

---

## 9. 字段对比表

### 9.1 skill_registry表

| 字段 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| `definition_body` | ✅ | ❌ | 删除 |
| `definition_path` | ✅ | ❌ | 删除 |
| 其他字段 | ✅ | ✅ | 保持 |

### 9.2 task_logs表

| 字段 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| `capability_name` | ✅ | ❌ | 删除 |
| `rendered_command` | ✅ | ❌ | 删除 |
| `run_type` | ✅ | ❌ | 合并到execution_type |
| `target_json` | ✅ | ❌ | 删除 |
| `log_path` | ✅ | ❌ | 删除 |
| `retention_days` | ✅ | ❌ | 删除 |
| `is_archived` | ✅ | ❌ | 删除 |
| `progress` | ❌ | ✅ | 新增 |
| `current_step` | ❌ | ✅ | 新增 |
| 其他字段 | ✅ | ✅ | 保持 |

### 9.3 step_logs表

| 字段 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| `llm_analysis` | ✅ | ❌ | 删除 |
| 其他字段 | ✅ | ✅ | 保持 |

### 9.4 diagnosis_capabilities表

| 字段 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| `visibility` | ✅ | ❌ | 删除 |
| `version` | ✅ | ❌ | 删除 |
| 其他字段 | ✅ | ✅ | 保持 |

---

## 10. 优化效果

### 10.1 字段数量变化

| 表 | 优化前 | 优化后 | 减少 |
|----|--------|--------|------|
| skill_registry | 18 | 16 | 2 |
| task_logs | 28 | 23 | 5 |
| step_logs | 11 | 10 | 1 |
| diagnosis_capabilities | 17 | 15 | 2 |
| **总计** | **74** | **64** | **10** |

### 10.2 改进效果

- **减少冗余**: 删除12个多余字段
- **提高一致性**: 合并2个重叠字段
- **简化逻辑**: 删除应用层逻辑字段
- **提高可维护性**: 字段职责更清晰

---

**评审完成时间**: 2026-05-24 15:55
**评审人**: AI数据模型评审助手
