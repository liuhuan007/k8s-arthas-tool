# K8s Arthas 智能诊断平台 — Skill Registry + Workflow Engine + Agent Tool Gateway

> 系统核心抽象层，定义诊断能力的注册、执行和安全暴露

**文档版本**: v3.0
**创建日期**: 2026-05-24
**状态**: 设计完成
**优先级**: **P0**

---

## 0. P0范围定义

### 0.1 各模块P0范围

| 模块 | P0范围 | 说明 |
|------|--------|------|
| **Skill Registry** | 导入、校验、发布到capabilities | 管理态核心 |
| **Workflow Engine** | DSL步骤执行、错误处理、执行记录 | 执行态核心 |
| **Agent Tool Gateway** | 受控工具注册、参数校验、审计 | Agent接入核心 |
| **Skill管理中心** | 内置/自定义/导入Skill管理 | 管理界面 |

### 0.2 P0必须实现的API

| API | 说明 |
|-----|------|
| `POST /api/skills/registry/import` | 导入Skill |
| `POST /api/skills/registry/{id}/publish` | 发布Skill |
| `POST /api/skills/orchestrator/execute` | 执行Skill |
| `POST /api/agent/tools/{tool_name}/execute` | Agent调用工具 |

---

## 目录

1. [核心抽象概述](#1-核心抽象概述)
2. [Skill管理中心](#2-skill管理中心)
3. [Skill Registry（技能注册中心）](#3-skill-registry技能注册中心)
4. [Workflow Engine（工作流引擎）](#4-workflow-engine工作流引擎)
5. [Agent Tool Gateway（Agent工具网关）](#5-agent-tool-gatewayagent工具网关)
6. [三者协作关系](#6-三者协作关系)
7. [数据模型](#7-数据模型)
8. [API设计](#8-api设计)
9. [实施计划](#9-实施计划)

---

## 1. 核心抽象概述

### 1.1 三个核心问题

| 问题 | 解决方案 | 核心抽象 |
|------|---------|---------|
| 系统怎么和Agent结合？ | 通过受控工具暴露系统能力 | **Agent Tool Gateway** |
| 诊断能力如何管理？ | 导入、校验、版本化、发布 | **Skill Registry** |
| DSL流程怎么执行？ | DSL步骤编排 + 执行引擎 | **Workflow Engine** |

### 1.2 架构定位

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    Agent层                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    CodeBuddy Agent SDK                                  │   │
│  │                         │                                               │   │
│  │                         ▼                                               │   │
│  │               ┌─────────────────────┐                                   │   │
│  │               │  Agent Tool Gateway │  ← 只能调用受控工具               │   │
│  │               └─────────────────────┘                                   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                            │
│                                    ▼                                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                   执行层                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                      Workflow Engine                                     │   │
│  │                    (DSL步骤执行 + 错误处理)                               │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                            │
│                                    ▼                                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                   注册层                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                       Skill Registry                                    │   │
│  │              (导入 + 校验 + 版本化 + 发布到 capabilities)                │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                            │
│                                    ▼                                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                   存储层                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │              diagnosis_capabilities (扁平主表)                           │   │
│  │              task_logs (执行日志)                                        │   │
│  │              audit_logs (审计日志)                                       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Skill管理中心

### 2.1 设计目标

Skill管理中心提供完整的Skill生命周期管理，支持三种来源的Skill统一管理。

### 2.2 Skill来源

| 来源 | 说明 | 适用场景 | 管理权限 |
|------|------|---------|---------|
| **内置Skill** | 系统随版本发布 | JVM Dashboard、CPU飙高、线程死锁 | 系统预置，不可删除 |
| **管理员自定义Skill** | 管理员在UI上传/编辑 | 企业内部诊断流程 | 管理员可增删改 |
| **外部导入Skill** | 从Git/目录/压缩包导入 | 团队共享、版本迁移 | 管理员可导入 |

### 2.3 Skill生命周期

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Skill 生命周期状态机                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐             │
│   │  草稿    │────▶│  校验中  │────▶│  测试中  │────▶│  已发布  │             │
│   │ (Draft)  │     │(Validat) │     │(Testing) │     │(Published)│             │
│   └──────────┘     └──────────┘     └──────────┘     └──────────┘             │
│        │               │                │                  │                     │
│        │               │                │                  │                     │
│        ▼               ▼                ▼                  ▼                     │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐       ┌──────────┐              │
│   │  已删除  │   │  校验失败│   │  测试失败│       │  已归档  │              │
│   │(Deleted) │   │(Failed)  │   │(Failed)  │       │(Archived)│              │
│   └──────────┘   └──────────┘   └──────────┘       └──────────┘              │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Skill来源管理

#### 2.4.1 内置Skill

```python
# 内置Skill定义（随代码发布）
BUILTIN_SKILLS = [
    {
        "name": "jvm-dashboard",
        "version": "1.0.0",
        "source": "builtin",
        "category": "quick",
        "level": 1,
        "description": "查看JVM运行概况",
        "arthas_command": "dashboard -n 1",
        "risk_level": "low"
    },
    {
        "name": "cpu-high-diagnosis",
        "version": "1.0.0",
        "source": "builtin",
        "category": "performance",
        "level": 2,
        "description": "排查CPU飙高问题",
        "dsl": "steps: [...]",  # 执行DSL
        "risk_level": "medium"
    },
    # ... 更多内置Skill
]
```

#### 2.4.2 管理员自定义Skill

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ⚙️ Skill管理中心 - 管理员自定义Skill                                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📋 Skill列表                                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 来源    │ 名称           │ 版本   │ 状态    │ 操作            │   │   │
│  │  ├─────────────────────────────────────────────────────────────────┤   │   │
│  │  │ 内置   │ JVM Dashboard  │ 1.0.0  │ 已发布 │ [查看]          │   │   │
│  │  │ 内置   │ CPU飙高诊断    │ 1.0.0  │ 已发布 │ [查看]          │   │   │
│  │  │ 自定义 │ 企业OOM诊断    │ 1.0.0  │ 已发布 │ [编辑][删除]    │   │   │
│  │  │ 导入   │ 团队性能分析   │ 2.0.0  │ 草稿   │ [编辑][发布]    │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  [+ 新建Skill]  [导入Skill]  [批量导入]                                  │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.4.3 外部导入Skill

```python
class SkillImporter:
    """Skill导入器"""
    
    def import_from_file(self, file_path: str) -> Skill:
        """从文件导入"""
        content = Path(file_path).read_text()
        return self._parse_skill(content)
    
    def import_from_directory(self, dir_path: str) -> List[Skill]:
        """从目录批量导入"""
        skills = []
        for file in Path(dir_path).glob("*.md"):
            skill = self.import_from_file(str(file))
            if skill:
                skills.append(skill)
        return skills
    
    def import_from_git(self, repo_url: str, branch: str = "main") -> List[Skill]:
        """从Git仓库导入"""
        # 克隆仓库
        # 扫描skills目录
        # 导入所有Skill
        pass
    
    def import_from_zip(self, zip_path: str) -> List[Skill]:
        """从压缩包导入"""
        # 解压到临时目录
        # 扫描skills目录
        # 导入所有Skill
        pass
```

### 2.5 Skill管理界面

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ⚙️ Skill管理中心                                                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────┐  ┌─────────────────────────────────────────────────────┐  │
│  │  📂 来源筛选     │  │                                                     │  │
│  │  [全部]         │  │  📋 Skill列表                                       │  │
│  │  [内置]         │  │  ┌─────────────────────────────────────────────┐   │  │
│  │  [自定义]       │  │  │ 来源 │ 名称          │ 版本  │ 状态  │ 操作 │   │  │
│  │  [导入]         │  │  ├─────────────────────────────────────────────┤   │  │
│  │                 │  │  │ 内置 │ JVM Dashboard │ 1.0.0 │ 已发布 │ [查看]│  │  │
│  │  📊 状态筛选    │  │  │ 内置 │ CPU飙高诊断   │ 1.0.0 │ 已发布 │ [查看]│  │  │
│  │  [全部]         │  │  │ 自定义│ 企业OOM诊断   │ 1.0.0 │ 已发布 │ [编辑]│  │  │
│  │  [草稿]         │  │  │ 导入 │ 团队性能分析  │ 2.0.0 │ 草稿   │ [发布]│  │  │
│  │  [已发布]       │  │  └─────────────────────────────────────────────┘   │  │
│  │  [已归档]       │  │                                                     │  │
│  │                 │  │  [+ 新建Skill]  [导入Skill]  [批量导入]            │  │
│  └─────────────────┘  └─────────────────────────────────────────────────────┘  │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  📊 统计信息                                                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │ 总数     │  │ 内置     │  │ 自定义   │  │ 导入     │  │ 草稿     │ │   │
│  │  │   25     │  │   14     │  │    6     │  │    5     │  │    3     │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.6 Skill编辑器

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ✏️ Skill编辑器 - 企业OOM诊断                                    [保存] [发布]  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  基本信息                                                               │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  名称: [企业OOM诊断                                          ]  │   │   │
│  │  │  描述: [排查JVM Metaspace OOM问题                            ]  │   │   │
│  │  │  分类: [性能诊断 ▼]  层级: [Level 2 ▼]  风险: [中风险 ▼]      │   │   │
│  │  │  来源: 自定义  版本: 1.0.0                                     │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  执行DSL                                                                │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  steps:                                                         │   │   │
│  │  │    - id: step1                                                  │   │   │
│  │  │      name: 获取JVM状态                                          │   │   │
│  │  │      command: "dashboard -n 1"                                  │   │   │
│  │  │      timeout: 10                                                │   │   │
│  │  │    - id: step2                                                  │   │   │
│  │  │      name: 检查Metaspace                                        │   │   │
│  │  │      command: "memory"                                          │   │   │
│  │  │      timeout: 10                                                │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  参数定义                                                                │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │   │
│  │  │  {                                                               │   │   │
│  │  │    "type": "object",                                            │   │   │
│  │  │    "properties": {                                              │   │   │
│  │  │      "class": {"type": "string", "description": "目标类名"}     │   │   │
│  │  │    }                                                            │   │   │
│  │  │  }                                                               │   │   │
│  │  └─────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  [校验DSL]  [测试执行]  [保存草稿]  [发布]                              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Skill Registry（技能注册中心）

### 2.1 职责

| 职责 | 说明 |
|------|------|
| **导入** | 从Markdown/YAML文件导入Skill定义 |
| **校验** | 验证Skill格式、参数、命令合法性 |
| **版本化** | 管理Skill版本，支持回滚 |
| **发布** | 将Skill发布到diagnosis_capabilities表 |
| **分类** | 按类型/层级/风险等级分类管理 |

### 2.2 Skill定义格式

```yaml
---
name: cpu-high-diagnosis
version: 1.0.0
description: 排查JVM/应用CPU飙高问题
category: performance
level: 2
risk_level: medium
estimated_duration: 60
tags: [cpu, performance, thread]
author: admin
---

# CPU飙高诊断

## 诊断步骤

### 步骤1: 获取JVM整体状态
**命令**: `dashboard -n 1`
**风险等级**: low
**超时**: 10s
**大模型分析**: 分析JVM整体状态，识别异常指标

### 步骤2: 获取CPU占用最高的线程
**命令**: `thread -n 5`
**风险等级**: low
**超时**: 10s
**大模型分析**: 分析线程堆栈，识别热点代码

### 步骤3: 检测死锁
**命令**: `thread -b`
**风险等级**: low
**超时**: 5s
**大模型分析**: 检测死锁情况

### 步骤4: 追踪慢方法（条件执行）
**条件**: 步骤2发现高CPU线程
**命令**: `stack ${class} ${method}`
**风险等级**: medium
**超时**: 30s
**大模型分析**: 定位热点方法

## 参数定义

```json
{
  "type": "object",
  "properties": {
    "class": {
      "type": "string",
      "description": "热点类名（可选）"
    },
    "method": {
      "type": "string",
      "description": "热点方法名（可选）",
      "default": "*"
    }
  }
}
```

## 大模型提示词

```
你是一个Java应用性能诊断专家。请分析以下CPU飙高诊断结果：
{diagnosis_data}
```
```

### 2.3 Arthas官方Skills导入（P0）

> **设计目标**：支持导入Arthas官方skills，通过Agent SDK直接执行。

#### 2.3.1 核心设计

**Arthas官方skills就是为Agent设计的prompt/guideline，可以直接使用，无需转换为DSL。**

```
用户选择Arthas Skill (cpu-high/SKILL.md)
    │
    ▼
Agent Tool Gateway获取skill内容
    │
    └── 返回Markdown内容给Agent
            │
            ▼
Agent SDK解析Markdown并执行
    │
    ├── Agent理解诊断步骤
    │
    ├── Agent调用工具执行命令
    │       │
    │       └── execute_capability('dashboard', connection_id)
    │
    ├── Agent收集执行结果
    │
    ├── Agent根据结果判断下一步
    │       │
    │       ├── 如果需要继续 → 调用下一个工具
    │       └── 如果信息足够 → 生成诊断结论
    │
    └── Agent生成诊断报告
```

#### 2.3.2 Agent Tool Gateway实现

```python
# Agent Tool Gateway提供skill内容
@tool("get_arthas_skill", "Get Arthas skill content for diagnosis", {
    "skill_name": str
})
async def get_arthas_skill(args: dict) -> dict:
    """获取Arthas skill内容（给Agent使用）"""
    
    skill_name = args['skill_name']
    
    # 从文件系统或数据库读取skill内容
    skill_content = load_arthas_skill(skill_name)
    
    return {
        "skill_name": skill_name,
        "content": skill_content,  # Markdown格式，Agent直接解析
        "available_tools": [
            "execute_capability",
            "get_pod_status",
            "get_pod_metrics"
        ]
    }
```

#### 2.3.3 Arthas官方Skills示例

```yaml
---
name: cpu-high
description: CPU飙高排查
---

## 适用场景
机器CPU飙高、应用响应变慢、负载异常升高

## 核心步骤
1. `dashboard -n 1` 查看CPU/线程/GC概况
2. `thread -n 5` 定位最忙线程及堆栈
3. 根据堆栈判断方向（CPU密集计算 / 锁竞争 / GC 等）
4. 按需使用 `stack` / `trace` / `watch` 进一步确认热点方法调用路径
5. 输出诊断结论（现象、证据、初步结论、下一步建议）

## 注意事项
- watch/trace必须设置-n参数
- 避免对线上应用造成压力
```

#### 2.3.4 Agent执行示例

```
用户：帮我诊断这个Pod的CPU问题
    │
    ▼
Agent：我来使用cpu-high skill进行诊断
    │
    ├── 步骤1: 调用execute_capability('dashboard', connection_id)
    │       │
    │       └── 返回：CPU使用率85%，线程pool-1-thread-3占用高
    │
    ├── 步骤2: 调用execute_capability('thread -n 5', connection_id)
    │       │
    │       └── 返回：线程堆栈，热点在Service.process()
    │
    ├── 步骤3: 调用execute_capability('stack ${class} ${method}', ...)
    │       │
    │       └── 返回：Service.process()调用链路
    │
    └── 步骤4: Agent分析并生成诊断报告
            │
            └── 输出：
                - 问题现象：CPU使用率85%
                - 根本原因：Service.process()循环逻辑
                - 证据链：dashboard→thread→stack
                - 优化建议：优化循环逻辑，使用异步处理
```

#### 2.3.5 导入方式

| 方式 | 说明 | 适用场景 |
|------|------|---------|
| **文件导入** | 上传Markdown文件 | 管理员手动导入 |
| **Git同步** | 从Arthas仓库同步 | 自动更新 |
| **内置Skills** | 预置常用skills | 开箱即用 |

### 2.4 校验规则

| 校验项 | 规则 | 失败处理 |
|--------|------|---------|
| **格式校验** | YAML前置元数据完整 | 拒绝导入 |
| **命令白名单** | Arthas命令必须在白名单内 | 拒绝导入 |
| **参数校验** | 参数schema符合JSON Schema | 拒绝导入 |
| **风险评估** | 高风险命令必须有确认步骤 | 警告提示 |
| **版本冲突** | 同名Skill版本号不能重复 | 自动递增版本 |

### 2.4 Arthas命令白名单

```python
# 允许的Arthas命令（低风险）
ALLOWED_COMMANDS_LOW_RISK = [
    "dashboard", "thread", "jvm", "sysprop", "sysenv",
    "vmoption", "memory", "heap", "gc", "logger",
    "sc", "sm", "jad", "classloader", "perfcounter"
]

# 允许的Arthas命令（中风险）
ALLOWED_COMMANDS_MEDIUM_RISK = [
    "trace", "watch", "stack", "monitor", "tt",
    "profiler", "heapdump"
]

# 禁止的Arthas命令（高风险）
FORBIDDEN_COMMANDS = [
    "redefine", "retransform",  # 修改代码
    "ognl", "ognl -x 100",     # 可能执行任意代码
    "reset",                    # 重置增强
    "shutdown"                  # 关闭Agent
]
```

### 2.5 Skill生命周期

```
草稿(Draft) → 校验(Validated) → 测试(Testing) → 发布(Published) → 归档(Archived)
                  │                    │                │
                  └── 校验失败 ──┘    └── 测试失败 ──┘  └── 下线 ──┘
```

---

## 3. Workflow Engine（技能编排器）

### 3.1 职责

| 职责 | 说明 |
|------|------|
| **步骤编排** | 按DSL定义执行多步骤诊断流程 |
| **条件分支** | 支持if/else条件执行 |
| **参数传递** | 步骤间参数传递 |
| **错误处理** | 步骤失败时的重试/跳过/终止策略 |
| **执行记录** | 所有执行写入task_logs和audit_logs |

### 3.2 执行DSL格式

```yaml
# Skill执行DSL
steps:
  - id: step1
    name: 获取JVM状态
    command: "dashboard -n 1"
    timeout: 10
    on_success: next
    on_failure: abort
    
  - id: step2
    name: 获取CPU线程
    command: "thread -n 5"
    timeout: 10
    on_success: next
    on_failure: abort
    
  - id: step3
    name: 检测死锁
    command: "thread -b"
    timeout: 5
    on_success: next
    on_failure: skip
    
  - id: step4
    name: 追踪慢方法
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

### 3.3 执行引擎

```python
class SkillOrchestrator:
    """技能编排器 - 执行诊断流程"""
    
    def __init__(self, skill_id: int, connection_id: str, params: dict):
        self.skill_id = skill_id
        self.connection_id = connection_id
        self.params = params
        self.context = {}  # 步骤间共享上下文
        self.results = []  # 执行结果
        
    async def execute(self) -> SkillExecutionResult:
        """执行诊断流程"""
        
        # 1. 加载Skill定义
        skill = self._load_skill(self.skill_id)
        
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
```

### 3.4 执行记录

```python
# 每个步骤执行后记录到task_logs
def _log_to_task_logs(self, step: SkillStep, result: StepResult):
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
        'created_at': datetime.now()
    })

# 同时记录到audit_logs
def _log_to_audit_logs(self, step: SkillStep, result: StepResult):
    AuditService.log_diagnosis_execution(
        skill_id=self.skill_id,
        step_name=step.name,
        command=step.command,
        status=result.status,
        user_id=current_user.id
    )
```

---

## 4. Agent Tool Gateway（Agent工具网关）

### 4.1 职责

| 职责 | 说明 |
|------|------|
| **工具注册** | 注册Agent可调用的受控工具 |
| **权限控制** | 控制Agent可以调用哪些工具 |
| **参数校验** | 校验工具调用参数 |
| **执行代理** | 代理执行工具调用 |
| **审计记录** | 记录所有Agent工具调用 |

### 4.2 受控工具清单

| 工具名 | 说明 | 参数 | 风险 |
|--------|------|------|------|
| `execute_capability` | 执行预定义诊断能力 | capability_id, params | 受控 |
| `get_pod_status` | 获取Pod状态 | connection_id | 只读 |
| `get_pod_metrics` | 获取Pod指标 | connection_id | 只读 |
| `list_capabilities` | 列出可用能力 | category, level | 只读 |
| `get_diagnosis_history` | 获取诊断历史 | connection_id | 只读 |
| `analyze_output` | 分析命令输出 | output, context | 只读 |

### 4.3 禁止的工具

| 工具名 | 原因 |
|--------|------|
| `execute_kubectl` | 任意kubectl命令，安全风险 |
| `execute_arthas_command` | 任意Arthas命令，安全风险 |
| `execute_shell` | 任意Shell命令，安全风险 |
| `modify_connection` | 修改连接状态，超出范围 |
| `delete_pod` | 删除Pod，高风险操作 |

### 4.4 Gateway实现

```python
class AgentToolGateway:
    """Agent工具网关 - 控制Agent可调用的工具"""
    
    # 注册的受控工具
    REGISTERED_TOOLS = {
        'execute_capability': {
            'handler': self._execute_capability,
            'params_schema': {...},
            'risk_level': 'medium',
            'requires_confirmation': True
        },
        'get_pod_status': {
            'handler': self._get_pod_status,
            'params_schema': {...},
            'risk_level': 'low',
            'requires_confirmation': False
        },
        # ... 其他工具
    }
    
    def register_tool(self, name: str, handler: callable, schema: dict, risk: str):
        """注册工具"""
        self.REGISTERED_TOOLS[name] = {
            'handler': handler,
            'params_schema': schema,
            'risk_level': risk
        }
    
    async def execute_tool(self, tool_name: str, params: dict, user_id: int) -> dict:
        """执行工具调用"""
        
        # 1. 检查工具是否注册
        if tool_name not in self.REGISTERED_TOOLS:
            return {'error': f'Tool {tool_name} not registered'}
        
        tool = self.REGISTERED_TOOLS[tool_name]
        
        # 2. 参数校验
        if not self._validate_params(params, tool['params_schema']):
            return {'error': 'Invalid parameters'}
        
        # 3. 权限检查
        if not self._check_permission(tool_name, user_id):
            return {'error': 'Permission denied'}
        
        # 4. 执行工具
        result = await tool['handler'](params)
        
        # 5. 记录审计日志
        AuditService.log_agent_tool_call(
            tool_name=tool_name,
            params=params,
            result=result,
            user_id=user_id
        )
        
        return result
    
    async def _execute_capability(self, params: dict) -> dict:
        """执行诊断能力"""
        return await SkillOrchestrator(
            skill_id=params['capability_id'],
            connection_id=params['connection_id'],
            params=params.get('params', {})
        ).execute()
```

### 4.5 与Agent SDK集成

```python
# 通过Agent SDK的MCP配置注册工具
from codebuddy_agent_sdk import CodeBuddyAgentOptions

options = CodeBuddyAgentOptions(
    model="deepseek-v3.1",
    permission_mode="default",  # P0: 不使用bypassPermissions
    mcp_servers={
        "diagnosis": {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "services.agent.tool_gateway"],
        }
    }
)

# Agent只能调用注册的工具
# 不能执行任意命令
```

---

## 5. 三者协作关系

### 5.1 三种执行流程

#### 5.1.1 人工/前端执行流程

```
用户
    │
    │  1. POST /api/diagnosis/capabilities/{id}/execute
    ▼
diagnosis_capabilities (生产执行态)
    │
    │  2. 获取capability定义
    ▼
Workflow Engine (P0)
    │
    │  3. 解析DSL
    │  4. 执行步骤
    ▼
step executor (Arthas/kubectl)
    │
    │  5. 执行命令
    ▼
存储层
    │
    │  6. 记录task_logs (run级)
    │  7. 记录step_logs (step级)
    │  8. 记录audit_logs
    ▼
返回结果给前端
```

#### 5.1.2 Agent执行流程（P2）

```
Agent SDK
    │
    │  1. 调用工具: execute_capability
    ▼
Agent Tool Gateway (P2)
    │
    │  2. 校验工具注册
    │  3. 校验参数
    │  4. 权限检查
    ▼
execute_capability(capability_id, connection_id, params)
    │
    │  5. 获取capability定义
    ▼
Workflow Engine
    │
    │  6. 解析DSL
    │  7. 执行步骤
    ▼
step executor (Arthas/kubectl)
    │
    │  8. 执行命令
    ▼
存储层
    │
    │  9. 记录task_logs
    │  10. 记录step_logs
    │  11. 记录audit_logs
    ▼
返回结果给Agent
    │
    │  12. Agent继续分析
    ▼
返回给用户
```

#### 5.1.3 Skill管理流程

```
管理员
    │
    │  1. 创建/编辑Skill
    ▼
Skill Registry (P0/P1)
    │
    │  2. 校验Skill格式
    │  3. 校验命令白名单
    │  4. 校验参数schema
    ▼
Skill草稿 (status=draft)
    │
    │  5. 测试Skill
    ▼
Skill测试中 (status=testing)
    │
    │  6. 发布Skill
    ▼
diagnosis_capabilities (生产执行态)
    │
    │  7. 同步到生产表
    ▼
可供用户/Agent调用
```

### 5.2 组件边界

| 组件 | 职责 | 不做什么 |
|------|------|---------|
| **Skill Registry** | Skill导入、校验、版本、发布 | 不执行Skill |
| **Workflow Engine** | 执行已发布capability的DSL | 不管理Skill生命周期 |
| **Agent Tool Gateway** | 让Agent以受控方式调用capability | 不执行Skill、不管理Skill |
| **diagnosis_capabilities** | 存储生产执行态能力 | 不存储管理态Skill |
| **task_logs** | 记录run级执行日志 | 不记录step级细节 |
| **step_logs** | 记录step级执行日志 | 不记录run级汇总 |

---

## 6. 数据模型

### 6.1 Skill Registry表

```sql
-- 技能注册表（草稿箱）
CREATE TABLE skill_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT,
    category TEXT,  -- performance/stability/security
    level INTEGER,  -- 1/2/3/4
    risk_level TEXT,  -- low/medium/high
    dsl TEXT,  -- 执行DSL (YAML/JSON)
    parameters_schema TEXT,  -- 参数schema
    llm_prompt TEXT,  -- 大模型提示词
    retry_policy TEXT,  -- 重试策略JSON（新增）
    status TEXT DEFAULT 'draft',  -- draft/validated/testing/published/archived
    created_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
);
```

> **新增字段说明**：`retry_policy` 存储重试策略配置，格式如下：
> ```json
> {
>   "mode": "resume",  // resume: 从失败步骤继续 | restart: 重新开始
>   "max_retries": 3,
>   "retryable_step_types": ["arthas_command", "llm_analysis", "get_pod_status"],
>   "non_retryable_step_types": ["redefine", "mc"]
> }
> ```

### 6.3 Skill DSL幂等性设计（P0）

> **问题修复**：明确Skill DSL执行的幂等性和重试策略。

#### 6.3.1 步骤幂等性分类

| step_type | 幂等性 | 说明 | 重试建议 |
|-----------|--------|------|---------|
| `arthas_command` (只读) | ✅ 幂等 | dashboard、thread、jmap等 | 安全重试 |
| `arthas_command` (有副作用) | ❌ 非幂等 | redefine、mc等 | 需要确认 |
| `llm_analysis` | ✅ 幂等 | 纯分析，不执行 | 安全重试 |
| `get_pod_status` | ✅ 幂等 | 只读操作 | 安全重试 |
| `get_pod_metrics` | ✅ 幂等 | 只读操作 | 安全重试 |

#### 6.3.2 重试策略配置

```yaml
# Skill定义中的retry_policy
retry_policy:
  # 重试模式
  mode: "resume"  # resume: 从失败步骤继续 | restart: 重新开始
  
  # 最大重试次数
  max_retries: 3
  
  # 可重试的步骤类型
  retryable_step_types:
    - arthas_command  # 只读命令
    - llm_analysis
    - get_pod_status
    - get_pod_metrics
  
  # 不可重试的步骤类型（有副作用）
  non_retryable_step_types:
    - redefine  # 热更新代码
    - mc        # 编译代码
```

#### 6.3.3 重试执行流程

```
步骤执行失败
    │
    ▼
检查retry_policy
    │
    ├── mode = "restart"
    │       │
    │       └── 重新执行整个Skill
    │
    └── mode = "resume"
            │
            ▼
        检查失败步骤是否可重试
            │
            ├── 可重试
            │       │
            │       ├── 重试次数 < max_retries
            │       │       │
            │       │       └── 重试失败步骤
            │       │
            │       └── 重试次数 >= max_retries
            │               │
            │               └── 标记为失败，停止执行
            │
            └── 不可重试
                    │
                    └── 标记为失败，停止执行
```

#### 6.3.4 步骤状态持久化

每个步骤的执行状态写入`step_logs`表，支持断点续传：

```sql
-- step_logs表（支持重试）
CREATE TABLE step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    step_name TEXT,
    step_type TEXT,
    command TEXT,
    output TEXT,
    status TEXT DEFAULT 'pending',  -- pending/running/success/failed/skipped
    retry_count INTEGER DEFAULT 0,  -- 当前重试次数
    duration_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES task_logs(id)
);
```

### 6.2 与diagnosis_capabilities的关系

```
skill_registry (草稿箱)
    │
    │  发布(Publish)
    ▼
diagnosis_capabilities (生产表)
    │
    │  执行
    ▼
task_logs (执行日志)
```

---

## 7. API设计

### 7.1 Skill Registry API

```
# 导入Skill
POST /api/skills/registry/import
Content-Type: multipart/form-data
Body: file (Markdown/YAML文件)

# 校验Skill
POST /api/skills/registry/{id}/validate

# 发布Skill
POST /api/skills/registry/{id}/publish

# 列出草稿
GET /api/skills/registry?status=draft

# 获取Skill详情
GET /api/skills/registry/{id}
```

### 7.2 Workflow Engine API

```
# 执行Skill
POST /api/skills/orchestrator/execute
Body: {
  "skill_id": 1,
  "connection_id": "conn_123",
  "params": {...}
}

# 查询执行状态
GET /api/skills/orchestrator/runs/{run_id}/status

# 取消执行
POST /api/skills/orchestrator/runs/{run_id}/cancel
```

### 7.3 Agent Tool Gateway API

```
# 列出可用工具
GET /api/agent/tools

# 执行工具（Agent调用）
POST /api/agent/tools/{tool_name}/execute
Body: {
  "params": {...},
  "connection_id": "conn_123"
}

# 查询工具调用历史
GET /api/agent/tools/history
```

---

## 8. 实施计划

### 8.1 P0范围

| 模块 | P0范围 | 不包含 |
|------|--------|--------|
| **Skill Registry** | 导入、校验、发布到capabilities | 版本管理、草稿箱 |
| **Workflow Engine** | 基础步骤执行、错误处理 | 条件分支、参数传递 |
| **Agent Tool Gateway** | 受控工具注册、参数校验 | 权限组、动态注册 |

### 8.2 实施顺序

```
Phase 1: Skill Registry基础
├── 导入功能
├── 校验功能
└── 发布到capabilities

Phase 2: Workflow Engine基础
├── DSL解析
├── 步骤执行
└── 执行记录

Phase 3: Agent Tool Gateway基础
├── 工具注册
├── 参数校验
└── 审计记录

Phase 4: 增强功能（P1/P2）
├── 版本管理
├── 条件分支
├── 权限组
└── 动态注册
```

---

**文档结束**
