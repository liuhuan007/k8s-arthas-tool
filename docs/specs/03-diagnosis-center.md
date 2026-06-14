# K8s Arthas 智能诊断平台 — 诊断中心设计


**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [核心定位](#1-核心定位)
2. [架构分层](#2-架构分层)
3. [诊断能力模型](#3-诊断能力模型)
4. [Skill系统设计](#4-skill系统设计)
5. [统一Arthas命令执行器](#5-统一arthas命令执行器)
6. [执行引擎](#6-执行引擎)
7. [异常检测引擎](#7-异常检测引擎)
8. [根因分析引擎（RCA）](#8-根因分析引擎rca)
9. [知识推荐引擎](#9-知识推荐引擎)
10. [LLM分析引擎](#10-llm分析引擎)
11. [诊断报告](#11-诊断报告)

---

## 1. 核心定位

诊断中心 v2.0 是**统一的 Arthas 在线诊断平台**，整合所有诊断能力：

```
v1.0（分散）              v2.0（统一诊断中心）        v3.0（自治系统）
                                                                        
console + diag +        ──→    诊断中心（统一入口）  ──→    自主诊断决策
diagnosis-cap                      ├─ 快捷工具
                                   ├─ 诊断模板
                                   ├─ 场景方案
                                   ├─ AI 诊断
                                   ├─ 异常告警
                                   └─ 执行历史
```

---

## 2. 架构分层

```
┌─────────────────────────────────────────────────────────┐
│                     交互层                                │
│  诊断中心（统一入口）: 能力卡片/参数表单/告警/历史/报告     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                     智能层                                │
│  异常检测引擎 │ 根因分析引擎 │ 知识推荐引擎                 │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                     能力层                                │
│  诊断能力平台: 能力注册中心 │ 统一执行引擎 │ 执行日志管理    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                     数据层                                │
│  诊断案例库 │ 解决方案库 │ 指标历史库                       │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 诊断能力模型

系统采用 **1 张扁平主表** 的架构，通过 `category` 字段区分能力类型。扩展表（`arthas_command_templates`、`diagnosis_scenario_steps`、`ai_diagnosis_handlers`）已预建但当前未作为主要数据源——能力特定数据（`arthas_command`、`steps_json`、`handler`）直接存储在主表中，种子数据也直接写入主表。

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| **diagnosis_capabilities** | 诊断能力元数据（主表） | name, category, level, arthas_command, steps_json, handler, parameters_schema |
| **script_templates** | 脚本模板扩展（预留） | capability_id, runtime, script_body |
| **arthas_command_templates** | Arthas 命令模板扩展（预留） | capability_id, arthas_command |
| **diagnosis_scenario_steps** | 场景方案步骤扩展（预留） | capability_id, step_order, command, timeout_ms |
| **ai_diagnosis_handlers** | AI 诊断处理器扩展（预留） | capability_id, handler |

**能力类型与执行模式**（基于 `category` 字段）：

| 能力类型 | `category` | 执行方式 | 层级 |
|---------|------------|---------|------|
| 快捷工具 | `quick` | 单条命令直接执行 | Level 1 |
| 诊断模板 | `tool` | 参数化命令模板 | Level 2 |
| 场景方案 | `scenario` | 多步骤批量执行 | Level 3 |
| 智能诊断 | `ai` | 处理器动态加载 | Level 4 |

---

## 4. Skill系统设计

### 4.1 Skill概念模型

Skill是系统的核心诊断能力单元，每个Skill定义了一个完整的诊断流程，包括：
- **元数据**：名称、描述、分类、风险等级、预计耗时
- **参数定义**：输入参数的JSON Schema
- **执行DSL**：步骤编排定义（支持条件分支、参数传递）
- **大模型提示词**：用于分析命令输出的提示词模板
- **输出格式**：诊断结果的结构化格式

### 4.2 Skill来源

| 来源 | 说明 | 适用场景 | 管理权限 |
|------|------|---------|---------|
| **内置Skill** | 系统随版本发布 | JVM Dashboard、CPU飙高、线程死锁 | 系统预置，不可删除 |
| **管理员自定义Skill** | 管理员在UI上传/编辑 | 企业内部诊断流程 | 管理员可增删改 |
| **外部导入Skill** | 从Git/目录/压缩包导入 | 团队共享、版本迁移 | 管理员可导入 |

### 4.3 Skill生命周期

```
草稿(Draft) → 校验中(Validating) → 测试中(Testing) → 已发布(Published) → 已归档(Archived)
```

### 4.4 Skill DSL格式

> **详细定义见** `12-skill-registry-workflow-engine-gateway.md` §2.2。
> 本节仅列出 DSL 基本结构供快速参考。

```yaml
# Skill执行DSL（详细格式见 12- §2.2）
steps:
  - id: step1
    name: 获取JVM状态
    type: arthas_command
    command: "dashboard -n 1"
    timeout: 10
    on_success: next
    on_failure: abort
    
  - id: step2
    name: 获取CPU线程
    type: arthas_command
    command: "thread -n 5"
    timeout: 10
    on_success: next
    on_failure: abort
    
  - id: step3
    name: 检测死锁
    type: arthas_command
    command: "thread -b"
    timeout: 5
    on_success: next
    on_failure: skip
    
  - id: step4
    name: 追踪慢方法
    type: arthas_command
    command: "stack ${class} ${method}"
    timeout: 30
    condition: "step2.output contains 'RUNNABLE'"
    on_success: next
    on_failure: skip
    
  - id: step5
    name: 生成报告
    type: llm_analysis
    prompt: "分析以上诊断结果"
    on_success: complete
    on_failure: abort
```

### 4.5 Skill → diagnosis_capability → task_logs 关系

```
┌─────────────────────────────────────────────────────────────────┐
│  Skill Registry (草稿箱)                                         │
│  ├── 内置Skill (系统预置)                                        │
│  ├── 管理员自定义Skill                                           │
│  └── 外部导入Skill                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 发布(Publish)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  diagnosis_capabilities (生产表)                                 │
│  ├── name, category, level, risk_level                         │
│  ├── arthas_command (快捷工具/诊断模板)                          │
│  ├── steps_json (场景方案DSL)                                   │
│  ├── handler (AI诊断处理器)                                     │
│  └── parameters_schema                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 执行
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  task_logs (执行日志)                                            │
│  ├── capability_id → diagnosis_capabilities.id                 │
│  ├── snapshot_json (执行时的能力快照)                            │
│  ├── steps_output (步骤输出)                                    │
│  └── llm_analysis (大模型分析结果)                              │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Skill定义格式

> **详细定义见** `12-skill-registry-workflow-engine-gateway.md` §2.2。
> 本节仅列出基本格式供快速参考。

采用YAML前置元数据 + Markdown内容的格式，兼容Arthas现有Skill格式：

```yaml
---
name: cpu-high-diagnosis
description: 排查JVM/应用CPU飙高问题
category: performance
level: 1
risk_level: low
estimated_duration: 30
author: arthas-k8s-tool
version: 1.0.0
tags: [cpu, performance, thread]
---

# CPU飙高诊断

## 诊断流程

### 步骤1: 获取JVM整体状态
**命令**: `dashboard -n 1`
**风险等级**: low
**预计耗时**: 5s
**大模型分析**: 分析JVM整体状态，识别异常指标

### 步骤2: 获取CPU占用最高的线程
**命令**: `thread -n 5`
**风险等级**: low
**预计耗时**: 5s
**大模型分析**: 分析线程堆栈，识别热点代码

### 步骤3: 检测死锁
**命令**: `thread -b`
**风险等级**: low
**预计耗时**: 3s
**大模型分析**: 分析死锁情况，提供解决方案

### 步骤4: 根据堆栈分析方向
**条件分支**:
- 如果堆栈显示计算密集: `stack ${class} ${method}`
- 如果堆栈显示锁竞争: `thread -n 3 --state BLOCKED`
- 如果堆栈显示GC问题: `gc -h`

## 参数定义

```json
{
  "type": "object",
  "properties": {
    "class": {
      "type": "string",
      "description": "热点类名（可选，用于进一步分析）",
      "pattern": "^[A-Za-z_$][\\w.$*]*$"
    },
    "method": {
      "type": "string",
      "description": "热点方法名（可选，默认为*）",
      "default": "*",
      "pattern": "^[\\w.*]*$"
    }
  },
  "required": []
}
```

## 大模型提示词模板

```
你是一个Java应用性能诊断专家。请分析以下CPU飙高诊断结果：

## 诊断数据
{diagnosis_data}

## 请提供以下分析：

### 1. 问题概述
- CPU使用率异常的具体表现
- 影响范围和严重程度

### 2. 根本原因分析
- 热点线程识别
- 热点方法定位
- 问题类型判断（计算密集/锁竞争/GC问题）

### 3. 优化建议
- 代码层面优化
- 架构层面优化
- 配置层面优化

### 4. 下一步诊断方向
- 需要进一步排查的问题
- 建议的监控指标
```

## 输出格式

```json
{
  "summary": "CPU使用率异常，主要消耗在com.example.Service.process方法",
  "root_cause": "计算密集型问题，循环逻辑导致CPU占用过高",
  "severity": "medium",
  "evidence": [
    {
      "step": 1,
      "command": "dashboard -n 1",
      "key_finding": "CPU使用率85%"
    },
    {
      "step": 2,
      "command": "thread -n 5",
      "key_finding": "pool-1-thread-3线程CPU占用85%"
    }
  ],
  "suggestions": [
    "检查Service.process()中的循环逻辑",
    "考虑使用异步处理或增加线程池大小"
  ],
  "next_steps": [
    "使用trace命令进一步分析方法调用链路",
    "监控线程池使用情况"
  ]
}
```
```

### 4.3 Skill分类体系

| 分类 | 说明 | 风险等级 | 示例 |
|------|------|----------|------|
| **quick** | 快速诊断工具 | low | JVM Dashboard、线程清单、死锁检测 |
| **tool** | 诊断工具 | medium | Trace调用链分析、Watch方法观测、Stack调用栈定位 |
| **analysis** | 深度分析 | high | 内存泄漏分析、GC日志分析、性能剖析 |
| **spring** | Spring框架诊断 | medium | Spring配置诊断、Bean依赖分析 |
| **database** | 数据库诊断 | medium | 连接池诊断、慢查询分析 |
| **cache** | 缓存诊断 | low | 缓存命中率分析、缓存策略评估 |

### 4.4 Skill加载机制

```python
class SkillLoader:
    def __init__(self, skills_dir: str):
        self.skills_dir = skills_dir
        self.skills_cache = {}
    
    def load_all_skills(self) -> List[Skill]:
        """加载所有技能"""
        skills = []
        for skill_file in Path(self.skills_dir).glob("*/SKILL.md"):
            skill = self._load_skill(skill_file)
            if skill:
                skills.append(skill)
                self.skills_cache[skill.id] = skill
        return skills
    
    def _load_skill(self, skill_file: Path) -> Optional[Skill]:
        """加载单个技能"""
        content = skill_file.read_text(encoding='utf-8')
        
        # 解析YAML前置元数据
        if content.startswith('---'):
            yaml_end = content.find('---', 3)
            if yaml_end != -1:
                yaml_content = content[3:yaml_end].strip()
                markdown_content = content[yaml_end+3:].strip()
                
                metadata = yaml.safe_load(yaml_content)
                return Skill(
                    id=metadata.get('name'),
                    name=metadata.get('name'),
                    description=metadata.get('description'),
                    category=metadata.get('category', 'quick'),
                    level=metadata.get('level', 1),
                    risk_level=metadata.get('risk_level', 'low'),
                    estimated_duration=metadata.get('estimated_duration', 30),
                    content=markdown_content,
                    file_path=str(skill_file)
                )
        return None
    
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """获取指定技能"""
        return self.skills_cache.get(skill_id)
    
    def search_skills(self, query: str) -> List[Skill]:
        """搜索技能"""
        results = []
        for skill in self.skills_cache.values():
            if (query.lower() in skill.name.lower() or 
                query.lower() in skill.description.lower()):
                results.append(skill)
        return results
```

### 4.6 Workflow Engine（技能编排器）

Workflow Engine负责Skill的步骤执行、分支、上下文、快照、失败策略：

```python
class SkillOrchestrator:
    """技能编排器 - 执行诊断流程"""
    
    def __init__(self, skill_id: int, connection_id: str, params: dict):
        self.skill_id = skill_id
        self.connection_id = connection_id
        self.params = params
        self.context = {}  # 步骤间共享上下文
        self.results = []  # 执行结果
        self.snapshot = None  # 执行时的能力快照
        
    async def execute(self) -> SkillExecutionResult:
        """执行诊断流程"""
        
        # 1. 加载Skill定义并创建快照
        skill = self._load_skill(self.skill_id)
        self.snapshot = self._create_snapshot(skill)
        
        # 2. 解析执行DSL
        steps = self._parse_dsl(skill.dsl)
        
        # 3. 逐步执行
        for step in steps:
            # 检查条件
            if step.condition and not self._evaluate_condition(step.condition):
                continue
            
            # 执行步骤
            result = await self._execute_step(step)
            self.results.append(result)
            
            # 记录到task_logs
            self._log_to_task_logs(step, result)
            
            # 记录到audit_logs
            self._log_to_audit_logs(step, result)
            
            # 处理错误
            if result.status == 'failed':
                if step.on_failure == 'abort':
                    break
                elif step.on_failure == 'skip':
                    continue
        
        # 4. 生成最终报告
        return self._generate_report()
    
    def _create_snapshot(self, skill: Skill) -> dict:
        """创建执行时的能力快照"""
        return {
            'skill_id': skill.id,
            'skill_name': skill.name,
            'skill_version': skill.version,
            'dsl': skill.dsl,
            'parameters_schema': skill.parameters_schema,
            'snapshot_at': datetime.now().isoformat()
        }
    
    async def _execute_step(self, step: SkillStep) -> StepResult:
        """执行单个步骤"""
        
        if step.type == 'arthas_command':
            # 执行Arthas命令
            return await self._execute_arthas_command(step)
        elif step.type == 'llm_analysis':
            # 大模型分析
            return await self._execute_llm_analysis(step)
        elif step.type == 'kubectl':
            # 执行kubectl命令
            return await self._execute_kubectl(step)
        else:
            raise ValueError(f"Unknown step type: {step.type}")
    
    def _log_to_task_logs(self, step: SkillStep, result: StepResult):
        """记录到task_logs"""
        db.insert('task_logs', {
            'id': generate_uuid(),
            'capability_id': self.skill_id,
            'connection_id': self.connection_id,
            'execution_type': 'diagnosis',
            'status': result.status,
            'command': step.command,
            'output': result.output,
            'duration_ms': result.duration_ms,
            'step_number': step.number,
            'snapshot_json': json.dumps(self.snapshot),
            'created_at': datetime.now()
        })
```

### 4.7 Skill Loader（升级版）

```python
class SkillLoader:
    """Skill加载器 - 从多种来源加载Skill"""
    
    def __init__(self, skills_dir: str):
        self.skills_dir = skills_dir
        self.skills_cache = {}
    
    def load_all_skills(self) -> List[Skill]:
        """加载所有技能"""
        skills = []
        
        # 1. 加载内置Skill
        builtin_skills = self._load_builtin_skills()
        skills.extend(builtin_skills)
        
        # 2. 加载自定义Skill（从数据库）
        custom_skills = self._load_custom_skills()
        skills.extend(custom_skills)
        
        # 3. 加载导入Skill（从文件系统）
        imported_skills = self._load_imported_skills()
        skills.extend(imported_skills)
        
        return skills
    
    def _load_builtin_skills(self) -> List[Skill]:
        """加载内置Skill"""
        # 从代码中预定义的Skill
        return [Skill.from_dict(s) for s in BUILTIN_SKILLS]
    
    def _load_custom_skills(self) -> List[Skill]:
        """加载管理员自定义Skill"""
        # 从数据库skill_registry表加载
        rows = db.fetch_all(
            "SELECT * FROM skill_registry WHERE source = 'custom' AND status = 'published'"
        )
        return [Skill.from_row(row) for row in rows]
    
    def _load_imported_skills(self) -> List[Skill]:
        """加载导入Skill"""
        # 从文件系统加载
        skills = []
        for skill_file in Path(self.skills_dir).glob("*/SKILL.md"):
            skill = self._load_skill_from_file(skill_file)
            if skill:
                skills.append(skill)
        return skills
```

---

## 5. 统一Arthas命令执行器

当前系统有 4 个地方在执行 Arthas 命令（server.py / performance_diagnose.py / ai_chat.py / task_center.py），逻辑重复。统一为 `ArthasCommandExecutor`：

```python
class ArthasCommandExecutor:
    """统一的 Arthas 命令执行器"""

    @staticmethod
    def execute(connection, command, timeout_ms=None, skip_audit=False, 
                skip_history=False, confirmed=False):
        """执行单条 Arthas 命令
        
        功能：高危命令检查 → 自动超时 → 执行 → 脱敏 → 命令历史 → 审计日志
        """

    @staticmethod
    def execute_batch(connection, commands, timeout_ms=None, fail_fast=True):
        """批量执行（场景方案使用）"""
```

**命令分类与超时配置**：

| 类别 | 命令示例 | 默认超时 |
|------|---------|---------|
| 快捷查询 | dashboard, thread | 15-30s |
| 方法诊断 | trace, watch | 60s |
| 采样与 Dump | profiler, heapdump | 120s |

**高危命令**：`redefine`、`retransform`、`heapdump`、`profiler`、`logger`

---

## 6. 执行引擎

诊断中心发起任何诊断执行时，必须创建 `task_logs` 运行记录，写入 `run_type`、`capability_id`、`anomaly_event_id`、`connection_snapshot_json` 和 `ai_analysis_result`。

```python
def execute_task_run(task_def, connection=None):
    """统一执行入口"""
    capability = load_capability(task_def['capability_id'])
    category = capability['category']

    if category in ('quick', 'tool'):
        return execute_arthas_command(capability, task_def, connection)
    elif category == 'scenario':
        return execute_scenario(capability, task_def, connection)
    elif category == 'ai':
        return execute_ai_diagnosis(capability, task_def, connection)
```

### 6.1 场景方案执行（异步 + HTTP 轮询）

场景方案采用异步执行 + HTTP 轮询机制（非 WebSocket），因为当前系统无 WebSocket 基础设施：

```python
class ScenarioExecutor:
    def execute_async(self, capability_id, params, user_id, connection):
        """异步执行，返回 execution_id，前端通过轮询查询进度"""
        execution_id = str(uuid4())
        # 创建 task_logs 记录
        # 启动后台线程执行
        return {'ok': True, 'execution_id': execution_id}
```

前端每 2 秒轮询 `GET /api/diagnosis/executions/{execution_id}/status`，获取进度和结果。

### 6.2 AI 诊断处理器（数据库驱动注册表）

**架构评审改进**：原硬编码白名单改为数据库驱动的处理器注册表，新增能力无需修改代码。

```python
class HandlerRegistry:
    """诊断处理器注册表（数据库驱动）"""

    @classmethod
    def execute(cls, handler_path, **kwargs):
        registry = cls.load_handlers()  # 从 ai_diagnosis_handlers 表加载
        # 1. 检查是否注册
        # 2. 检查是否启用
        # 3. 模块路径限制（仅允许 performance_diagnose 模块）
        # 4. 动态加载
        # 5. 执行
```

---

## 7. 异常检测引擎

### 7.1 检测策略

```python
DETECTION_STRATEGIES = {
    'threshold': '阈值检测（CPU > 80%）',
    'baseline': '基线偏离（当前 vs 历史）',
    'trend': '趋势预测（容量预警）',
    'pattern': '模式识别（GC 频繁）',
}
```

### 7.2 异常规则表

```sql
CREATE TABLE anomaly_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    metric TEXT NOT NULL,                -- cpu/memory/gc/thread
    operator TEXT NOT NULL,              -- >/</>=/<=/==
    threshold REAL NOT NULL,
    duration_seconds INTEGER DEFAULT 60,
    cooldown_seconds INTEGER DEFAULT 300, -- 静默期：同一规则触发后多长时间不重复告警
    severity TEXT DEFAULT 'warning',     -- info/warning/critical
    enabled INTEGER DEFAULT 1,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE anomaly_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    pod_id TEXT NOT NULL,
    metric_value REAL NOT NULL,
    threshold REAL NOT NULL,
    severity TEXT NOT NULL,
    status TEXT DEFAULT 'open',          -- open/diagnosing/resolved/ignored
    root_event_id INTEGER,               -- 去重关联
    diagnosis_id TEXT,
    started_at TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY (rule_id) REFERENCES anomaly_rules(id)
);

CREATE TABLE metric_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pod_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    time_window TEXT NOT NULL,           -- 1h/6h/24h/7d
    avg_value REAL,
    p50_value REAL, p95_value REAL, p99_value REAL,
    stddev REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pod_id, metric, time_window)
);
```

### 7.3 预制异常规则

```sql
INSERT INTO anomaly_rules (name, metric, operator, threshold, duration_seconds, severity, description) VALUES
('CPU 使用率过高', 'cpu', '>', 80, 300, 'critical', 'CPU 使用率超过 80% 持续 5 分钟'),
('Old 区内存过高', 'old_gen_mb', '>', 800, 180, 'warning', 'Old 区内存超过 800MB 持续 3 分钟'),
('BLOCKED 线程过多', 'blocked_threads', '>=', 3, 60, 'critical', 'BLOCKED 线程数 >= 3 持续 1 分钟'),
('FGC 频繁', 'fgc_count_per_min', '>', 2, 120, 'warning', 'Full GC 频率超过 2 次/分钟 持续 2 分钟'),
('响应时间过长', 'response_time_ms', '>', 2000, 60, 'warning', '接口响应时间超过 2s 持续 1 分钟');
```

### 7.4 异常检测渐进实现策略

| 阶段 | 检测策略 | 说明 |
|------|---------|------|
| **P0** | 阈值检测 | 简单可靠，覆盖80%常见场景 |
| **P1** | 基线偏离 | 需要数据积累，初期用预制基线 |
| **P2** | 趋势预测 + 模式识别 | 复杂度高，后期实现 |

**P0预制规则**：

```python
# P0阶段的预制规则（覆盖常见场景）
P0_RULES = [
    {"metric": "cpu", "operator": ">", "threshold": 80, "duration": 300, "severity": "critical"},
    {"metric": "memory", "operator": ">", "threshold": 90, "duration": 180, "severity": "warning"},
    {"metric": "blocked_threads", "operator": ">=", "threshold": 3, "duration": 60, "severity": "critical"},
    {"metric": "fgc_count", "operator": ">", "threshold": 2, "duration": 120, "severity": "warning"},
    {"metric": "response_time", "operator": ">", "threshold": 2000, "duration": 60, "severity": "warning"},
]
```

**基线学习初期处理**：

```python
class MetricBaselineManager:
    """指标基线管理器"""
    
    def __init__(self):
        self.min_data_points = 10  # 最少数据点数
    
    def get_baseline(self, pod_id: str, metric: str, time_window: str) -> dict:
        """获取基线"""
        
        # 1. 查询数据库中的基线
        baseline = db.fetch_one(
            "SELECT * FROM metric_baselines WHERE pod_id = ? AND metric = ? AND time_window = ?",
            (pod_id, metric, time_window)
        )
        
        if baseline and baseline['data_points'] >= self.min_data_points:
            # 有足够数据，使用真实基线
            return baseline
        
        # 2. 数据不足，使用预制基线
        return self._get_default_baseline(metric, time_window)
    
    def _get_default_baseline(self, metric: str, time_window: str) -> dict:
        """获取预制基线（数据不足时使用）"""
        defaults = {
            'cpu': {'avg': 30, 'p95': 60, 'p99': 80},
            'memory': {'avg': 60, 'p95': 80, 'p99': 90},
            'response_time': {'avg': 200, 'p95': 500, 'p99': 1000},
        }
        return defaults.get(metric, {'avg': 0, 'p95': 0, 'p99': 0})
```

---

## 8. 根因分析引擎（RCA）

```python
class RootCauseAnalyzer:
    async def analyze(pod_id, anomalies, context) -> DiagnosisResult:
        # 1. 根据异常类型选择诊断能力
        capabilities = select_capabilities(anomalies)
        # 2. 执行诊断能力
        diagnosis_data = execute_diagnosis(pod_id, capabilities)
        # 3. 规则预筛
        rule_result = rule_engine.evaluate(diagnosis_data)
        # 4. 检索历史案例
        similar_cases = find_similar_cases(anomalies, diagnosis_data)
        # 5. LLM 推理（三级降级策略）
        llm_result = llm_analyze(anomalies, diagnosis_data, rule_result, similar_cases)
        # 6. 生成诊断报告
        return generate_report(llm_result, similar_cases)
```

**异常→能力映射**：

| 异常类型 | 推荐诊断能力 |
|---------|-------------|
| high_cpu | thread_analysis, profiler_cpu |
| high_memory | heap_analysis, gc_analysis |
| thread_blocked | thread_deadlock, thread_dump |
| slow_api | trace_analysis, profiler_cpu |
| gc_frequent | gc_analysis, heap_histogram |

---

## 9. 知识推荐引擎

### 9.1 案例库

```sql
CREATE TABLE diagnosis_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    problem_description TEXT NOT NULL,
    symptoms_json TEXT NOT NULL,
    root_cause TEXT,
    solution TEXT,
    diagnosis_capability_ids TEXT,
    execution_log_ids TEXT,
    confidence REAL,
    verified INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    tags TEXT,
    status TEXT DEFAULT 'draft',  -- draft/validated/verified/outdated
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE solution_playbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    problem_pattern TEXT NOT NULL,
    description TEXT,
    steps_json TEXT NOT NULL,
    estimated_time_minutes INTEGER,
    risk_level TEXT DEFAULT 'medium',
    success_rate REAL,
    requires_restart INTEGER DEFAULT 0,
    rollback_plan TEXT,
    tags TEXT,
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

### 9.2 冷启动策略

**问题**：系统初期案例库为空，如何处理？

**解决方案**：预制标准案例库

| 场景 | 案例数量 | 来源 |
|------|---------|------|
| CPU高 | 5个 | 常见原因：循环、正则、排序 |
| 内存泄漏 | 5个 | 常见原因：缓存、连接、线程池 |
| 死锁 | 3个 | 常见原因：锁顺序、嵌套锁 |
| 慢查询 | 3个 | 常见原因：缺索引、全表扫描 |
| GC频繁 | 3个 | 常见原因：大对象、内存泄漏 |

**预制案例格式**：

```json
{
  "title": "Service.process()循环导致CPU高",
  "problem_description": "CPU使用率85%，主要消耗在Service.process()方法",
  "symptoms_json": ["cpu_high", "thread_runnable", "method_hot"],
  "root_cause": "Service.process()中的循环逻辑导致CPU占用过高",
  "solution": "1. 检查循环逻辑 2. 使用异步处理 3. 添加性能监控",
  "tags": ["cpu", "performance", "loop"],
  "verified": 1,
  "success_rate": 0.95
}
```

### 9.3 案例生命周期

```
草稿(Draft) → 待验证(Pending) → 已验证(Verified) → 已过时(Outdated)
     ↑              ↓
     └── 用户反馈 ──┘
```

**用户反馈机制**：

```python
class CaseFeedback:
    """案例反馈"""
    
    def submit_feedback(self, case_id: int, feedback_type: str, comment: str):
        """提交反馈"""
        # feedback_type: 'helpful' / 'not_helpful' / 'incorrect' / 'outdated'
        
        db.insert('case_feedback', {
            'case_id': case_id,
            'feedback_type': feedback_type,
            'comment': comment,
            'user_id': current_user.id,
            'created_at': datetime.now()
        })
        
        # 更新案例统计
        if feedback_type == 'helpful':
            db.execute(
                "UPDATE diagnosis_cases SET success_count = success_count + 1 WHERE id = ?",
                (case_id,)
            )
        elif feedback_type == 'not_helpful':
            db.execute(
                "UPDATE diagnosis_cases SET failure_count = failure_count + 1 WHERE id = ?",
                (case_id,)
            )
        
        # 如果失败率过高，标记为待验证
        self._check_case_quality(case_id)
    
    def _check_case_quality(self, case_id: int):
        """检查案例质量"""
        case = db.fetch_one(
            "SELECT * FROM diagnosis_cases WHERE id = ?",
            (case_id,)
        )
        
        if case:
            total = case['success_count'] + case['failure_count']
            if total > 10:
                success_rate = case['success_count'] / total
                if success_rate < 0.6:
                    # 成功率过低，标记为待验证
                    db.execute(
                        "UPDATE diagnosis_cases SET status = 'pending' WHERE id = ?",
                        (case_id,)
                    )
```

### 9.4 案例匹配算法

匹配策略：症状匹配（40%）+ 标签匹配（20%）+ 时间衰减（10%）+ 成功率（30%）。

使用 SQLite FTS5 做初筛，限制候选集大小后再内存精排。

**症状匹配实现**：

```python
class CaseMatcher:
    """案例匹配器"""
    
    def match_cases(self, symptoms: List[str], limit: int = 5) -> List[dict]:
        """匹配相似案例"""
        
        # 1. FTS5初筛
        query = " OR ".join(symptoms)
        candidates = db.fetch_all(
            "SELECT * FROM diagnosis_cases WHERE symptoms_json MATCH ? AND status = 'verified'",
            (query,)
        )
        
        # 2. 内存精排
        scored_cases = []
        for case in candidates:
            score = self._calculate_score(case, symptoms)
            scored_cases.append((score, case))
        
        # 3. 按分数排序
        scored_cases.sort(key=lambda x: x[0], reverse=True)
        
        return [case for _, case in scored_cases[:limit]]
    
    def _calculate_score(self, case: dict, symptoms: List[str]) -> float:
        """计算匹配分数"""
        
        # 症状匹配（40%）
        case_symptoms = json.loads(case['symptoms_json'])
        symptom_match = len(set(symptoms) & set(case_symptoms)) / len(set(symptoms) | set(case_symptoms))
        
        # 标签匹配（20%）
        case_tags = set(case['tags'].split(',')) if case['tags'] else set()
        symptom_tags = set(symptoms)
        tag_match = len(case_tags & symptom_tags) / len(case_tags | symptom_tags) if case_tags else 0
        
        # 时间衰减（10%）
        days_since_created = (datetime.now() - datetime.fromisoformat(case['created_at'])).days
        time_decay = max(0, 1 - days_since_created / 365)  # 1年内衰减
        
        # 成功率（30%）
        total = case['success_count'] + case['failure_count']
        success_rate = case['success_count'] / total if total > 0 else 0.5
        
        # 综合分数
        score = (symptom_match * 0.4 + 
                 tag_match * 0.2 + 
                 time_decay * 0.1 + 
                 success_rate * 0.3)
        
        return score
```

---

## 10. LLM分析引擎

### 10.1 三级降级策略

| 场景 | 行为 | 超时时间 | 置信度调整 |
|------|------|---------|-----------|
| **LLM正常** | 完整AI诊断报告（根因 + 证据 + 建议 + 相似案例） | - | 1.0 |
| **LLM超时** | 规则引擎结果 + 文本摘要 | 10-60秒 | 0.8 |
| **LLM不可用** | 纯规则引擎结果 + 历史案例推荐 | - | 0.6 |

### 10.2 分层超时配置

| 诊断场景 | 超时时间 | 说明 |
|---------|---------|------|
| **简单摘要** | 10秒 | 快速分析，结果简洁 |
| **复杂根因分析** | 30秒 | 深度分析，需要更多推理 |
| **多轮对话** | 60秒 | 交互式诊断，需要上下文 |

### 10.3 降级标识

```json
{
  "diagnosis_result": {
    "summary": "CPU使用率异常，主要消耗在Service.process()方法",
    "root_cause": "计算密集型问题",
    "severity": "medium",
    "evidence": [...],
    "suggestions": [...]
  },
  "degradation_level": "llm_timeout",
  "degradation_reason": "LLM调用超时，使用规则引擎结果",
  "confidence_adjustment": 0.8,
  "fallback_strategy": "rule_engine"
}
```

**降级级别说明**：

| 级别 | 说明 | 用户提示 |
|------|------|---------|
| `none` | LLM正常 | 无提示 |
| `llm_timeout` | LLM超时 | "AI分析超时，使用规则引擎结果" |
| `llm_unavailable` | LLM不可用 | "AI服务不可用，使用规则引擎结果" |
| `rule_engine_fallback` | 规则引擎兜底 | "使用规则引擎分析" |

### 10.4 规则引擎覆盖范围

**P0阶段规则引擎覆盖80%常见场景**：

| 场景 | 规则 | 准确率 |
|------|------|--------|
| CPU高 | cpu > 80% 持续5分钟 | 95% |
| 内存高 | memory > 90% 持续3分钟 | 90% |
| 死锁 | blocked_threads >= 3 | 95% |
| GC频繁 | fgc_count > 2/分钟 | 85% |
| 响应慢 | response_time > 2000ms | 80% |

**规则引擎无法处理的场景**：
- 新的异常类型（需要LLM分析）
- 复杂的多因素问题（需要LLM推理）
- 业务逻辑问题（需要LLM理解）

**降级策略**：当规则引擎无法处理时，返回"无法自动诊断，建议人工排查"。

### 10.5 用户体验一致性

**三种降级场景下，前端展示格式一致**：

```
┌─────────────────────────────────────────────────────────┐
│  诊断报告 - CPU飙高诊断                                   │
├─────────────────────────────────────────────────────────┤
│  📋 报告摘要                                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Pod: my-app-pod-xxx                            │   │
│  │  诊断时间: 2026-05-24 15:00                      │   │
│  │  降级级别: ⚠️ LLM超时，使用规则引擎结果          │   │
│  │  置信度: 80%                                     │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  🔍 根因分析                                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │  问题类型: 计算密集型                             │   │
│  │  根本原因: Service.process()循环逻辑导致CPU占用高 │   │
│  │  严重程度: 中等                                   │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  💡 优化建议                                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │  1. 检查Service.process()中的循环逻辑            │   │
│  │  2. 考虑使用异步处理或增加线程池大小              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  📚 相似案例（来自历史）                                   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  - 2026-05-10: 类似CPU问题（已解决）              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [导出PDF] [导出Markdown] [归档案例]                     │
└─────────────────────────────────────────────────────────┘
```

### 10.2 AI 工具调用安全边界

| 调用来源 | 允许能力 | 约束 |
|---------|---------|------|
| AI RCA | 只读诊断能力、短时 trace/watch/thread/dashboard | 必须绑定 run_id 和连接快照 |
| AI 对话 | 能力目录中的允许列表能力 | 用户确认后执行 |
| MCP | MCP token 绑定连接和用户权限内的能力 | 不能绕过诊断中心直接调用 |
| 在线修复建议 | 只生成建议和验证清单 | redefine 必须由用户二次确认 |

LLM 输出必须按 JSON Schema 解析，解析失败时降级为文本摘要。AI 只能通过能力 ID 或 handler key 调用诊断能力，**不允许让 LLM 直接生成任意 Arthas 命令后执行**。

---

## 11. 诊断报告

```
┌─────────────────────────────────────────────────────────┐
│  诊断报告                                                 │
│  Pod: udc-7cc5-abc123 | 2026-05-04 10:30                │
├─────────────────────────────────────────────────────────┤
│  🔍 根因定位                                              │
│  OrderService.createOrder() 方法慢                        │
│  平均耗时: 1.2s（正常 200ms）                              │
│  根因: 数据库慢查询（user_orders 表缺索引）                 │
│  置信度: 87%                                              │
│                                                         │
│  📈 影响面                                                │
│  直接影响: 订单创建接口                                    │
│  间接影响: 支付流程、库存扣减                               │
│                                                         │
│  💡 修复建议                                              │
│  1. 为 user_orders.user_id 添加索引 [生成 SQL] [执行]     │
│  2. 优化 SQL: SELECT * → SELECT id, status               │
│                                                         │
│  📚 相似案例                                              │
│  - 2026-04-20: payment 表缺索引（已解决）                  │
│                                                         │
│  [导出 PDF] [导出 Markdown] [归档案例]                     │
└─────────────────────────────────────────────────────────┘
```