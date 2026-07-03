# K8s Arthas 智能诊断平台 — JVM 诊断 Agent 平台设计

> 面向 Java 服务的 Kubernetes 在线 JVM 诊断平台，通过 Arthas 能力、诊断 Skill、MCP 工具边界和专家 Agent，完成从问题描述到诊断报告的闭环。

**文档版本**: v1.0
**创建日期**: 2026-06-26
**状态**: 设计草案
**优先级**: **P0/P1**
**归档位置**: `docs/specs/15-jvm-diagnosis-agent-platform.md`

---

## 0. 定位收敛

### 0.1 平台定位

本系统不是通用 Agent 平台，也不是泛 Skill 市场，而是 **Arthas 驱动的 Java/JVM 在线诊断平台**。

Agent、Skill、MCP、提示词、应用画像和服务记忆都必须服务于一个核心目标：

> 帮助 Java 开发和 SRE 在 Kubernetes 环境中更快定位 JVM 性能问题，并沉淀每个 Java 服务自己的诊断知识。

### 0.2 核心用户

| 用户 | 核心诉求 |
|---|---|
| Java 后端开发 | 定位慢接口、CPU 高、线程阻塞、类加载异常、线上行为差异 |
| SRE / 运维 | 快速判断 Pod / JVM / 资源 / 网络 / GC 是否异常 |
| 性能工程师 | 复盘性能问题，沉淀诊断路径和优化建议 |
| 团队负责人 | 将专家经验沉淀为可复用 Skill 和服务级知识资产 |

### 0.3 不做什么

| 不做 | 原因 |
|---|---|
| 泛用数字人平台 | 会稀释 Arthas/JVM 诊断定位 |
| 任意 MCP 工具市场 | 风险不可控，且和 JVM 诊断主线无关 |
| 任意命令自由执行 Agent | 容易绕过权限、审计和风险确认 |
| 通用低代码编排平台 | 当前价值不在编排复杂度，而在 JVM 诊断经验产品化 |

### 0.4 要做什么

| 要做 | 说明 |
|---|---|
| JVM 诊断专家 Agent | 从问题描述理解症状，推荐诊断 Skill，生成报告 |
| Arthas Skill Library | 将 Arthas 命令、诊断步骤、解释规则沉淀为 Skill |
| MCP 工具边界 | 只暴露受控 JVM 诊断工具，统一权限、审计、超时和风险确认 |
| Java Service Memory | 按 `service_name` 沉淀每个 Java 服务的诊断画像、历史问题和有效路径 |
| 诊断报告闭环 | 每次诊断记录过程、证据、结论、建议和可沉淀记忆 |

---

## 1. 总体架构

### 1.1 架构图

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              交互层                                          │
│  诊断中心 / Agent Chat / Skill 管理 / MCP 管理 / 服务记忆                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           JVM 诊断专家 Agent 层                              │
│  症状理解 │ 服务识别 │ 记忆检索 │ Skill 推荐 │ 报告生成 │ 记忆候选提取          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             诊断能力层                                       │
│  JVM Diagnosis Skill Library │ Workflow Engine │ Agent Tool Gateway          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             工具执行层                                       │
│  Arthas Executor │ MCP Tools │ Pod/Kubectl Context │ Profiler / Dump          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据层                                          │
│  task_logs │ data/memory │ diagnosis_cases │ case_matches │ config files          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 与现有系统关系

| 现有模块 | 在本设计中的角色 |
|---|---|
| 连接中心 | 提供 Pod / Arthas 连接、PID、端口转发、连接快照 |
| 诊断中心 | Agent 入口、Skill 推荐、诊断执行、报告展示 |
| Skill Registry | 管理 JVM 诊断 Skill 的导入、校验、发布、版本 |
| Workflow Engine | 执行诊断 Skill 步骤，记录步骤结果 |
| Agent Tool Gateway | Agent 调用 Arthas/MCP/诊断能力的唯一受控边界 |
| MCP Proxy / MCP Server | 暴露受控 JVM 诊断工具，不暴露任意命令能力 |
| `task_logs` | 统一记录每次诊断运行、过程、结果和报告 |

---

## 2. 核心抽象

### 2.1 Java Service

平台的业务核心对象不应只停留在 Pod 或连接，而应提升到 **Java Service**。

`service_name` 是诊断记忆和知识沉淀的主键，建议取值优先级：

1. 用户手动绑定的服务名。
2. Kubernetes `app` / `app.kubernetes.io/name` / `service` 标签。
3. Deployment / StatefulSet 名称。
4. Pod 名称裁剪后的工作负载名。

### 2.2 Application Profile

应用画像描述一个 Java 服务的稳定上下文。

| 类型 | 示例 |
|---|---|
| 基础标识 | `service_name`、cluster、namespace、labels |
| 运行时 | JDK 版本、Spring Boot 版本、GC 类型、JVM 参数 |
| 代码结构 | 主包名前缀、核心 Controller、Service、DAO、Mapper |
| 关键组件 | 线程池名称、数据源、Redis、MQ、HTTP 客户端 |
| 业务入口 | 常见慢接口、核心任务、定时任务、消息消费入口 |
| 推荐能力 | 该服务常用的 JVM Diagnosis Skill 集合 |

### 2.3 JVM Diagnosis Skill

Skill 是 JVM 诊断经验的产品化单元，不只是 Arthas 命令模板。

每个 Skill 至少包含：

| 字段 | 说明 |
|---|---|
| `name` | Skill 名称 |
| `symptom_type` | 适用症状，如 CPU、memory、gc、slow_request |
| `level` | 诊断层级，越高越复杂 |
| `risk_level` | 风险等级 |
| `prerequisites` | 连接、PID、确认项 |
| `parameters_schema` | 用户或 Agent 需要提供的参数 |
| `steps` | Arthas/MCP/分析步骤 |
| `analysis_prompt` | 结果解释提示词 |
| `result_schema` | 结构化报告输出格式 |

### 2.4 MCP Tool

MCP 在本系统中是工具协议层，不是能力中心。所有 MCP Tool 必须通过平台注册、授权和审计。

P0 只暴露 JVM 诊断白名单工具：

| Tool | 说明 |
|---|---|
| `arthas.execute_command` | 执行白名单 Arthas 命令 |
| `jvm.get_dashboard` | 获取 JVM 运行概览 |
| `jvm.get_top_threads` | 获取 CPU 高线程 |
| `jvm.trace_method` | trace 指定方法 |
| `jvm.watch_expression` | watch 指定表达式 |
| `pod.get_metrics` | 获取 Pod CPU / 内存 / 进程快照 |
| `diagnosis.run_skill` | 执行已发布 JVM Diagnosis Skill |

### 2.5 Service Memory

服务记忆是按 `service_name` 沉淀的诊断知识，包括画像、历史、经验和反馈。

记忆不是让 Agent 自由写入长期知识，而是分层受控进化：

| 层级 | 内容 | 写入方式 | 是否参与后续推荐 |
|---|---|---|---|
| 临时记忆 | 当前会话、当前诊断上下文 | 自动 | 仅当前会话 |
| 候选记忆 | Agent 从报告中提取的经验 | 自动生成 | 低权重，可展示待确认 |
| 稳定记忆 | 多次验证或人工确认的知识 | 人工确认或置信度达标 | 高权重参与推荐 |

---

## 3. JVM 诊断闭环

### 3.1 标准流程

```text
用户描述问题
  ↓
识别 service_name 和当前 Arthas 连接
  ↓
加载服务画像与历史记忆
  ↓
Agent 判断症状类型
  ↓
推荐 JVM Diagnosis Skill
  ↓
用户确认风险和参数
  ↓
通过 Agent Tool Gateway 执行 Skill / MCP Tool / Arthas 命令
  ↓
写入 task_logs 和步骤结果
  ↓
Agent 汇总证据并生成诊断报告
  ↓
提取 memory_candidates
  ↓
用户确认或后续多次命中后沉淀为稳定记忆
```

### 3.2 CPU 高示例

当用户输入：

```text
order-service CPU 又高了，帮我看下。
```

Agent 行为：

1. 识别 `service_name=order-service`。
2. 查询该服务历史 CPU 高记忆。
3. 发现历史上 `OrderCalculateService.calculate()` 多次造成 CPU 高。
4. 推荐优先执行 `cpu-high-thread-stack-trace` Skill。
5. 先执行 `dashboard` 和 `thread -n 5`。
6. 如果命中相同线程栈，再建议 trace 相关方法。
7. 生成报告，并产生候选记忆。

报告示例：

```json
{
  "service_name": "order-service",
  "symptom_type": "cpu_high",
  "root_cause": "CPU 主要消耗在 OrderCalculateService.calculate() 的规则循环中",
  "evidence": [
    "thread -n 5 显示 worker-17 CPU 占用 86%",
    "stack 显示热点方法为 com.example.order.OrderCalculateService.calculate",
    "历史记忆显示该方法曾在大促流量下出现相同问题"
  ],
  "recommendation": "优先检查规则数量和缓存命中率，必要时对 calculate() 增加短时 trace"
}
```

---

## 4. 服务诊断记忆设计（文件优先简化版）

### 4.1 P0 决策：先用本地文件，不新增记忆表

服务记忆先参考 Claude / WorkBuddy 的本地上下文机制：用可读、可审查、可手工编辑的 Markdown/YAML 文件沉淀服务知识，而不是一开始就设计复杂的 `service_memory_items` 表。

P0 只做三件事：

1. 按 `service_name` 建立本地记忆目录。
2. Agent 诊断前加载该服务的画像、记忆和 Playbook。
3. 诊断结束后生成候选记忆文件，等待用户确认后再合并到稳定记忆。

不在 P0 新增：

- `service_memory_items` 表。
- 复杂置信度演化表。
- 记忆证据关系表。
- 自动晋升稳定记忆的后台任务。

`service_profiles` 也先不作为强制新增表。P0 可将服务画像写入文件；后续如果需要搜索、统计和多用户并发编辑，再把文件内容索引到数据库。

### 4.2 本地目录结构

记忆根目录统一放在 `data/memory/`。用户提到的 `memery` 按语义修正为 `memory`，避免把拼写错误固化到工程目录。

```text
data/
└── memory/
    ├── README.md
    ├── index.json
    ├── services/
    │   └── {cluster_name}/
    │       └── {namespace}/
    │           └── {service_name}/
    │               ├── SERVICE.md
    │               ├── PROFILE.yaml
    │               ├── MEMORY.md
    │               ├── PLAYBOOKS.md
    │               ├── CANDIDATES.md
    │               ├── FEEDBACK.md
    │               └── evidence/
    │                   └── {run_id}.json
    └── shared/
        ├── JVM-BASELINE.md
        └── COMMON-CASES.md
```

目录职责：

| 文件 | 作用 | 写入方式 |
|---|---|---|
| `SERVICE.md` | 服务说明、负责人、业务边界、常见入口 | 人工维护为主 |
| `PROFILE.yaml` | 可机器读取的服务画像，如 cluster、namespace、workload、labels、JDK、GC、包名前缀 | 探测生成草稿，人工确认 |
| `MEMORY.md` | 已确认的稳定服务记忆 | 用户确认后追加或编辑 |
| `PLAYBOOKS.md` | 该服务验证过的诊断路径和推荐 Skill | 人工维护 + Agent 建议 |
| `CANDIDATES.md` | Agent 从诊断报告中提取的候选记忆 | 自动追加，默认不参与推荐 |
| `FEEDBACK.md` | 用户确认、否定、修正记录 | UI 或人工追加 |
| `evidence/{run_id}.json` | 某次诊断的证据索引，引用 `task_logs.id`、案例、Skill、关键输出摘要 | 自动生成 |
| `shared/*.md` | 跨服务通用 JVM 知识和案例模板 | 团队维护 |

### 4.3 文件内容约定

`PROFILE.yaml` 示例：

```yaml
service_name: order-service
cluster_name: prod-k8s
namespace: order
workload_kind: deployment
workload_name: order-service
labels:
  app: order-service
package_prefixes:
  - com.example.order
runtime:
  jdk: "17"
  framework: "Spring Boot"
  gc: "G1"
source: detected
confidence: 70
updated_at: "2026-06-27T10:00:00+08:00"
```

`MEMORY.md` 只保存稳定记忆，格式尽量简单：

```markdown
# order-service Memory

## CPU 高：规则计算热点

- status: confirmed
- symptom_type: cpu_high
- evidence_runs: [run_20260626_001, run_20260618_004]
- evidence_cases: [case_cpu_rule_loop]
- related_skills: [cpu-high-thread-stack-trace]
- updated_at: 2026-06-27

历史上 CPU 高多次集中在 `OrderCalculateService.calculate()`。
优先执行 `thread -n 5`，再对相关方法做短时 `trace`。
```

`CANDIDATES.md` 保存待确认内容，不直接进入 Agent 高权重上下文：

```markdown
# Candidate Memory

## 2026-06-27 run_20260627_001

- symptom_type: slow_request
- confidence: 45
- evidence_runs: [run_20260627_001]
- suggested_action: confirm-or-reject

Agent 观察到慢请求可能与 `pricing-worker` 线程池排队有关，需要人工确认。
```

`evidence/{run_id}.json` 只保存索引和摘要，不保存大文本输出：

```json
{
  "run_id": "run_20260627_001",
  "task_log_id": "run_20260627_001",
  "service_name": "order-service",
  "pod_name": "order-service-7cc5",
  "skill_ids": ["cpu-high-thread-stack-trace"],
  "case_ids": ["case_cpu_rule_loop"],
  "summary": "thread -n 5 命中 order-worker CPU 热点",
  "artifact_paths": ["data/profiler/thread-order-service-202606271000.txt"]
}
```

### 4.4 读取与写入规则

Agent 每次诊断前按固定顺序加载：

1. `data/memory/services/{cluster}/{namespace}/{service}/PROFILE.yaml`
2. `data/memory/services/{cluster}/{namespace}/{service}/MEMORY.md`
3. `data/memory/services/{cluster}/{namespace}/{service}/PLAYBOOKS.md`
4. `data/memory/shared/JVM-BASELINE.md`
5. 与症状相关的 `diagnosis_cases` / `case_matches` 查询结果

写入规则：

| 场景 | 写入位置 | 是否参与下次推荐 |
|---|---|---|
| 服务画像探测 | `PROFILE.yaml` 草稿字段 | 低权重，需确认 |
| 诊断证据索引 | `evidence/{run_id}.json` | 只作为追溯证据 |
| Agent 提取经验 | `CANDIDATES.md` | 默认不参与或低权重参与 |
| 用户确认有效 | 合并到 `MEMORY.md` | 是 |
| 用户否定 | 写入 `FEEDBACK.md` | 作为反例，避免重复建议 |
| 多服务通用模式 | 提议进入 `diagnosis_cases` | 人工审核后生效 |

### 4.5 与现有表关系

| 现有对象 | P0 使用方式 |
|---|---|
| `task_logs` | 仍是诊断运行事实来源；文件中的 `evidence_runs` 引用它。 |
| `step_logs` | 仍记录每一步命令、输出摘要和状态。 |
| `diagnosis_cases` | 继续作为通用案例库，不直接绑定服务。 |
| `case_matches` | 记录某次运行命中了哪个通用案例。 |
| `connections` | 只表示当前 Pod/Arthas 连接，不承载长期记忆。 |
| `skill_registry` / `diagnosis_capabilities` | 继续管理 Skill 定义和发布态能力。 |

P0 不新增 `service_memory_items`。如后续需要全文检索、多用户协作、批量审核和统计报表，再在 P1 引入轻量索引表，例如 `memory_file_index`，只保存文件路径、服务名、状态、更新时间和摘要，不重复存储完整记忆正文。

### 4.6 为什么这样更简单

- 文件天然可读，管理员可以直接审阅和修正。
- 文件天然可版本化，后续可以接 GitOps 或导入导出。
- Agent 上下文加载更直接，不需要复杂 ORM 和迁移。
- SQLite 只保留运行事实和审计，避免把长期知识和运行日志混在一起。
- 未来要做搜索和统计时，再把文件建立索引即可，不需要一开始把模型设计过满。
---

## 5. JVM Diagnosis Skill Library

### 5.1 Skill 分类

| 分类 | 典型问题 | 关键 Arthas 能力 |
|---|---|---|
| CPU | CPU 飙高、线程热点 | `dashboard`、`thread`、`stack`、`trace` |
| 慢请求 | 接口耗时高、调用链变慢 | `trace`、`watch`、`tt` |
| 内存 | 内存上涨、泄漏、OOM | `memory`、`heapdump`、`vmtool` |
| GC | Full GC、频繁 Minor GC、停顿高 | `jvm`、GC log、`vmoption` |
| 线程 | 死锁、阻塞、线程池耗尽 | `thread -b`、`thread --state`、`stack` |
| 类加载 | 类冲突、方法不生效 | `sc`、`sm`、`jad`、`classloader` |
| 配置 | JVM 参数、系统属性异常 | `sysprop`、`sysenv`、`vmoption` |
| 热修复 | redefine 前后验证 | `jad`、`mc`、`redefine` |

### 5.2 Skill 标准格式

```yaml
name: cpu-high-thread-stack-trace
display_name: CPU 高线程定位
category: cpu
symptom_type: cpu_high
level: 2
risk_level: low
requires:
  connection_level: arthas
  java_pid: true
parameters_schema:
  type: object
  properties:
    top_n:
      type: integer
      default: 5
    trace_class:
      type: string
    trace_method:
      type: string
steps:
  - id: dashboard
    tool: arthas.execute_command
    args:
      command: dashboard
  - id: top_threads
    tool: jvm.get_top_threads
    args:
      top_n: "${top_n}"
  - id: trace_method
    when: "${trace_class} && ${trace_method}"
    tool: jvm.trace_method
    args:
      class_name: "${trace_class}"
      method_name: "${trace_method}"
analysis_prompt: |
  请根据 dashboard、thread、stack/trace 输出判断 CPU 热点线程、热点方法和可能根因。
result_schema:
  root_cause: string
  evidence: array
  recommendation: string
memory_extraction:
  enabled: true
  candidate_types:
    - root_cause
    - solution
    - preference
```

### 5.3 Skill 导入与维护

| 来源 | 支持方式 |
|---|---|
| 内置 Skill | 随代码发布，默认可用 |
| 本地导入 | 支持 `SKILL.md`、`skill.yaml`、`skill.json` |
| GitHub / 市场 | 进入草稿，校验后发布 |
| Arthas 官方经验 | 作为 prompt/guideline 导入，再映射为受控步骤 |

格式兼容关系：

| 格式 | 典型来源 | 平台处理方式 | 是否可直接执行 |
|---|---|---|---|
| 平台标准 Skill DSL | 内置 Skill、管理员自定义 Skill | 解析 `steps`、`parameters_schema`、`risk_level`，发布到 `diagnosis_capabilities` 后由 Workflow Engine 执行 | 是，执行路径最稳定 |
| `SKILL.md` + YAML Frontmatter | GitHub 导入、Arthas 官方 Skills、团队知识库 | 保留 Markdown 指令作为 Agent guideline，同时抽取元数据进入 `skill_registry` | 不能绕过 Tool Gateway；Agent 读取说明后仍只能调用白名单工具 |
| `skill.yaml` / `skill.json` | 本地导入、市场源同步 | 按平台标准字段校验，缺失字段进入草稿补全 | 校验通过并发布后可执行 |
| 纯 Markdown 经验文档 | 团队复盘、排障手册 | 作为候选 Skill 或案例素材导入，需要人工补齐元数据、风险等级和工具边界 | 否 |

兼容策略：

- `SKILL.md` 不强制转换成平台 DSL；它可以作为 Agent 可读的诊断指南存在。
- 当 `SKILL.md` 中包含明确的 Arthas 命令步骤时，平台可以生成“映射建议”，但发布前必须由管理员确认参数 Schema、风险等级和超时限制。
- 从 GitHub 导入的 Skill 先进入 `draft`，默认不对 Agent 暴露；只有通过格式校验、命令白名单校验和风险审查后，才可发布为 JVM Diagnosis Skill。
- Agent 使用外部 `SKILL.md` 时，只能读取指南内容并调用 `diagnosis.run_skill` 或白名单 MCP Tool，不能按 Markdown 中的自由文本直接执行任意命令。
- 平台标准 DSL 是“可执行形态”，`SKILL.md` 是“专家经验形态”；二者通过 `skill_registry.source_type`、`definition_format`、`metadata_json` 关联，避免把经验文档和可执行编排混成一个概念。

导入流程：

1. 导入到 `skill_registry` 草稿。
2. 校验格式、参数 Schema、命令白名单、风险等级。
3. 预览执行步骤和报告结构。
4. 发布到诊断能力或 JVM Skill Library。
5. 绑定到具体 Java Service 或全局可用。

---

## 6. MCP 工具边界

### 6.1 设计原则

- Agent 不能直接调用任意 MCP Server。
- MCP Tool 必须先注册到平台，再暴露给 Agent。
- MCP Tool 必须声明参数 Schema、风险等级、超时、连接要求。
- 高风险工具必须要求用户确认。
- 所有调用必须写 `audit_logs` 和 `task_logs` 或步骤日志。

### 6.2 Tool Gateway 执行链

```text
Agent 请求调用工具
  ↓
Agent Tool Gateway
  ↓
校验 tool 是否注册
  ↓
校验 user / service / connection 权限
  ↓
校验参数 Schema
  ↓
检查风险确认
  ↓
调用 MCP Tool / Arthas Executor / Workflow Engine
  ↓
记录审计和诊断步骤
  ↓
返回结构化结果给 Agent
```

### 6.3 服务级 MCP 绑定与自动重连

当前系统的 `mcp_tokens` 以 `connection_id` 绑定 Pod/Arthas 连接，这对一次性调试是够用的，但不适合作为 Agent 的长期能力边界：Pod 重启、滚动发布或副本切换后，`connection_id={cluster}/{namespace}/{pod}` 会变化，MCP 配置就会失效。

新的设计口径应从“绑定 Pod”提升为“绑定 Java Service”：

```text
MCP Token / Agent Session
  → service_name + cluster_name + namespace
  → Service Resolver 查找当前可用 Pod
  → Connection Manager 建立或复用 Arthas 连接
  → Tool Gateway 执行 MCP Tool
  → task_logs 记录本次实际 connection_id / pod_name
```

绑定层级：

| 层级 | 适用场景 | 生命周期 | 说明 |
|---|---|---|---|
| `connection` | 临时调试某个 Pod | Pod 生命周期 | 兼容现有 `mcp_tokens.connection_id`，适合一次性工具调用。 |
| `service` | Agent 长期诊断某个 Java 服务 | 服务生命周期 | 推荐形态；Pod 变化后自动解析新 Pod 并重建连接。 |
| `namespace` / `cluster` | 管理员工具或批量巡检 | 环境生命周期 | P1/P2 再开放，需要更强权限和审计。 |

数据模型建议：

| 对象 | 设计建议 | 说明 |
|---|---|---|
| `mcp_tokens.connection_id` | 保留兼容 | 继续支持现有基于连接的 MCP 访问。 |
| `mcp_tokens.scope_type` | 新增规划字段 | `connection/service/namespace/cluster`，默认 `connection`。 |
| `mcp_tokens.service_name` | 新增规划字段 | 当 `scope_type='service'` 时作为服务级绑定主键之一。 |
| `mcp_tokens.cluster_name` / `namespace` | 新增规划字段 | 限定服务所在环境，避免同名服务串权。 |
| `mcp_tokens.connection_id` | 服务级绑定时可为空 | 执行时由 Service Resolver 动态解析并写入运行日志。 |
| `PROFILE.yaml` | 作为服务解析权威画像 | 保存 workload、labels、namespace、cluster 等稳定信息；P1 可索引到数据库。 |

自动重连策略：

1. MCP 调用进入 Tool Gateway 时，如果 token 是 `service` 作用域，先根据 `service_name + cluster_name + namespace` 读取 `data/memory/.../PROFILE.yaml`，必要时结合实时 Kubernetes labels 校验。
2. Service Resolver 根据 workload/labels 选择当前 Ready Pod，优先选择已有健康 Arthas 连接的 Pod。
3. 如果没有健康连接，Connection Manager 自动建立 Pod/Arthas 连接，短路复用已有端口转发和 Arthas Agent。
4. 如果 Pod 已重启或连接失效，标记旧连接为不可用，重新发现新 Pod，并把新 `connection_id` 写入本次 `task_logs.target_json`。
5. Agent 和 MCP 客户端侧不需要重新配置；它们面对的是稳定的服务级 MCP 能力。

约束：

- 服务级 MCP 不能扩大权限；最终仍受用户授权、集群/namespace 授权、Tool 白名单和风险确认约束。
- 自动重连只允许在同一个 `service_name + cluster_name + namespace` 范围内发生，不能跨服务自动漂移。
- 多副本服务需要明确 Pod 选择策略：默认选择 Ready 且 Arthas 可达的 Pod；诊断报告必须记录实际 Pod。
- 高风险工具即使服务级自动重连成功，也必须重新做风险确认。
- P0 可先保留 `mcp_tokens.connection_id` 并在设计上补充服务级解析；真正迁移字段应在后续数据库迁移计划中单独评审。

### 6.4 风险分级

| 风险 | 示例 | 策略 |
|---|---|---|
| low | `dashboard`、`thread`、`jvm` | 可直接执行 |
| medium | `trace`、`watch`、`tt` | 需要超时和采样限制 |
| high | `heapdump`、`vmtool`、`redefine` | 需要用户确认和影响提示 |
| forbidden | `shutdown`、任意 shell、未注册 MCP | 禁止 Agent 调用 |

---

## 7. Agent 配置包与自进化机制

### 7.1 设计目标

参考 OpenOcta / Claw 这类产品中将 Agent 行为拆成多份配置文件的做法，本平台也应把 JVM 诊断 Agent 的身份、启动流程、工具边界、记忆策略、用户偏好和自进化规则配置化。

但本平台必须保持定位收敛：配置文件不是为了做泛 Agent，而是为了让 **Arthas JVM 诊断专家越用越懂每个 Java 服务**。

配置化目标：

- Agent 行为可解释：能看清它为什么这样诊断。
- Agent 能力可维护：工具、Skill、MCP、Prompt 都能版本化。
- Agent 记忆可进化：经验从候选到稳定，有审核、有证据、有回滚。
- Agent 安全可控：高风险 Arthas/MCP 操作不能绕过配置边界。
- Agent 可迁移：一套服务诊断配置可以导入/导出到其他环境。

### 7.2 配置包目录

建议新增 **Agent 配置包** 概念，按平台级、Agent 级、服务级三层组织。

```text
config/
└── agents/
    ├── platform/
    │   ├── BOOT.md
    │   ├── CONFIG.md
    │   ├── TOOLS.md
    │   └── MEMORY_POLICY.md
    ├── jvm-diagnosis/
    │   ├── IDENTITY.md
    │   ├── SOUL.md
    │   ├── BOOTSTRAP.md
    │   ├── SKILLS.md
    │   ├── MCP.md
    │   ├── HEARTBEAT.md
    │   └── USER.md
data/
└── memory/
    └── services/
        └── {cluster_name}/
            └── {namespace}/
                └── {service_name}/
                    ├── SERVICE.md
                    ├── PROFILE.yaml
                    ├── MEMORY.md
                    ├── PLAYBOOKS.md
                    ├── CANDIDATES.md
                    ├── FEEDBACK.md
                    └── evidence/
```

说明：

- `platform/` 是平台全局约束，所有 Agent 共享。
- `jvm-diagnosis/` 是 JVM 诊断专家 Agent 的行为配置。
- `data/memory/services/{cluster_name}/{namespace}/{service_name}/` 是服务级诊断画像和记忆配置的 P0 权威位置，可直接被 Agent 加载，也可作为 GitOps 配置导入。

### 7.3 配置文件职责

| 文件 | 层级 | 作用 |
|---|---|---|
| `BOOT.md` | 平台 | Agent 启动时必须加载的全局规则，如审计、权限、风险确认 |
| `CONFIG.md` | 平台 | 模型、超时、最大步骤数、工具调用限制、记忆阈值 |
| `TOOLS.md` | 平台 | 允许暴露给 Agent 的 Tool / MCP 白名单 |
| `MEMORY_POLICY.md` | 平台 | 候选记忆、稳定记忆、置信度、过期和回滚规则 |
| `IDENTITY.md` | Agent | JVM 诊断专家身份、边界和语气 |
| `SOUL.md` | Agent | 诊断理念：先证据、后结论；先低风险、后高风险 |
| `BOOTSTRAP.md` | Agent | 一次诊断会话的启动流程 |
| `SKILLS.md` | Agent | 可用 JVM Diagnosis Skill 分类与选择规则 |
| `MCP.md` | Agent | 可用 MCP 工具、风险等级、参数要求 |
| `HEARTBEAT.md` | Agent | 长诊断任务、定时观察、记忆复盘的周期策略 |
| `USER.md` | Agent | 用户偏好，如报告格式、语言、风险确认偏好 |
| `SERVICE.md` | 服务 | 服务说明、业务边界、负责人、常见场景 |
| `PROFILE.yaml` | 服务 | 可机器读取的服务画像，P0 直接落本地文件，P1 可建立索引表 |
| `MEMORY.md` | 服务 | 已确认的稳定服务记忆，P0 直接落本地文件 |
| `CANDIDATES.md` | 服务 | Agent 自动提取的候选记忆，需用户确认后才能合并到 `MEMORY.md` |
| `PLAYBOOKS.md` | 服务 | 针对该服务验证过的诊断路径 |
| `FEEDBACK.md` | 服务 | 用户确认、否定、修正记录 |

### 7.4 文件与数据库关系

P0 采用“文件保存长期记忆，数据库保存运行事实”的关系：

| 信息 | P0 权威位置 | 数据库用途 |
|---|---|---|
| 服务画像 | `data/memory/.../PROFILE.yaml` | P1 可建立索引，便于检索和权限过滤 |
| 服务记忆 | `data/memory/.../MEMORY.md` / `CANDIDATES.md` | P1 可建立 `memory_file_index`，不重复保存正文 |
| 诊断证据 | `task_logs` / `step_logs` / `evidence/{run_id}.json` | 数据库是运行事实权威，文件保存摘要索引 |
| 通用案例 | `diagnosis_cases` | 内置案例和团队经验模板 |
| Skill | `skill_registry` / `diagnosis_capabilities` | 导入 Skill 定义和文档 |
| MCP 白名单 | MCP 管理表 / Tool Gateway 注册表 | 声明默认工具边界 |
| Prompt | 配置文件 + 数据库版本 | 可审计、可回滚、可差异比较 |

运行时优先级：

```text
data/memory 服务级文件
  > Agent 级默认配置
  > 平台级默认配置
  > 数据库索引缓存
```

设计原则：

- `MEMORY.md` 和 `PROFILE.yaml` 是服务长期上下文的 P0 权威来源。
- 数据库负责运行事实、审计、用户权限和可选索引，不负责保存完整长期记忆正文。
- 文件可读、可评审、可导入导出、可版本控制。
- Agent 自动生成内容只能追加到 `CANDIDATES.md`，不能直接覆盖 `MEMORY.md`。

### 7.5 自进化闭环

系统自进化不是让 Agent 自由修改自身，而是通过受控循环不断优化服务诊断能力。

```text
诊断运行 task_logs
  ↓
Agent 生成诊断报告
  ↓
提取 memory_candidates
  ↓
追加到 data/memory/.../CANDIDATES.md
  ↓
用户确认 / 后续多次命中 / 反馈修正
  ↓
人工或审核流程合并到 MEMORY.md
  ↓
后续诊断加载 confirmed memory
```

自进化对象：

| 对象 | 进化方式 | 约束 |
|---|---|---|
| 服务画像 | 从连接、Pod 标签、JVM 探测中补全 `PROFILE.yaml` 草稿字段 | 低置信度字段需要人工确认 |
| 服务记忆 | 从诊断报告中提取候选记忆并追加到 `CANDIDATES.md` | 不能直接进入 `MEMORY.md` |
| Skill 偏好 | 根据服务上 Skill 成功/失败统计调整排序 | 不自动禁用 Skill |
| Prompt 片段 | 根据用户反馈生成修订建议 | 只生成建议，不自动改平台 Prompt |
| 通用案例 | 多服务反复验证后提升为 `diagnosis_cases` | 需要人工审核 |

### 7.6 记忆审核与回滚

每条自进化结果必须保留证据链：

- 来源 `run_id`。
- 使用的 Skill / MCP Tool。
- 关键 Arthas 输出摘要。
- Agent 诊断结论。
- 用户反馈。
- 置信度变化原因。

记忆状态机：

```text
candidate → confirmed → expired
     │           │
     └────────→ rejected
```

回滚要求：

- confirmed 记忆修改必须保留文件 diff 或追加修订记录。
- rejected 记忆不删除，保留为反例，避免 Agent 重复学习错误结论。
- `MEMORY.md` 只包含 confirmed 记忆。
- `FEEDBACK.md` 保留用户修正历史。

### 7.7 配置文件示例

`config/agents/jvm-diagnosis/IDENTITY.md`：

```markdown
# JVM Diagnosis Agent Identity

你是 Arthas JVM 诊断专家，服务于 Kubernetes 中运行的 Java 服务。

你的任务不是泛化聊天，而是：
- 根据用户描述识别 JVM 问题症状。
- 结合当前 service_name 的服务画像和历史记忆。
- 推荐低风险优先的 JVM Diagnosis Skill。
- 通过受控 Tool Gateway 执行 Arthas/MCP 工具。
- 基于证据生成诊断报告。

禁止：
- 绕过 Skill 或 Tool Gateway 自行执行任意命令。
- 在无证据时直接下根因结论。
- 自动执行 heapdump、redefine 等高风险操作。
```

`data/memory/services/prod-k8s/order/order-service/PROFILE.yaml`：

```yaml
service_name: order-service
cluster_name: prod-k8s
namespace: order
workload_kind: deployment
workload_name: order-service
package_prefixes:
  - com.example.order
runtime:
  jdk: "17"
  framework: "Spring Boot"
  gc: "G1"
components:
  thread_pools:
    - order-worker
    - pricing-worker
entrypoints:
  http:
    - /api/orders/create
    - /api/orders/calculate
source: manual
confidence: 90
```

`data/memory/services/prod-k8s/order/order-service/MEMORY.md`：

```markdown
# order-service Confirmed Diagnosis Memory

## CPU 高：规则计算热点

- symptom_type: cpu_high
- confidence: 85
- evidence_runs: [run_20260626_001, run_20260618_004]
- related_skills: [cpu-high-thread-stack-trace]

历史上 CPU 高多次集中在 `OrderCalculateService.calculate()`。
优先执行 `thread -n 5` 和相关方法短时 `trace`。
```

---

## 8. Prompt 与 Agent 策略

### 8.1 Prompt 组成

Agent 运行时 Prompt 由以下部分组成：

```text
平台级系统提示词
  + JVM 诊断专家人设
  + Agent 配置包（IDENTITY / SOUL / BOOTSTRAP）
  + 当前 Java Service Profile
  + 当前服务 confirmed memory
  + 用户问题
  + 可用 JVM Skill 列表
  + 可用 MCP Tool 白名单
  + 风险和审计规则
```

### 8.2 Agent 行为约束

Agent 必须遵守：

1. 先判断症状和服务上下文，再推荐 Skill。
2. 优先使用已发布 Skill，不直接拼接任意 Arthas 命令。
3. 必须通过 Agent Tool Gateway 调用工具。
4. 高风险操作必须解释影响并等待确认。
5. 报告必须引用证据，不得只给主观结论。
6. 记忆写入只能产生候选记忆，不能直接生成稳定记忆。
7. 自进化只能生成候选记忆、配置修订建议或案例提升建议，不能自动改写稳定配置。

### 8.3 Agent 输出格式

诊断报告建议统一结构：

```json
{
  "service_name": "string",
  "symptom_type": "cpu_high|slow_request|memory|gc|thread|classloading|unknown",
  "summary": "string",
  "root_cause": "string",
  "confidence": 0,
  "evidence": [
    {
      "source": "arthas.thread",
      "content": "string",
      "run_step_id": "string"
    }
  ],
  "recommendations": ["string"],
  "next_actions": ["string"],
  "memory_candidates": [
    {
      "memory_type": "root_cause|solution|preference|anti_pattern",
      "title": "string",
      "content": "string",
      "confidence": 30
    }
  ]
}
```

---

## 9. 产品页面设计

### 9.1 诊断中心

诊断中心是主入口：

- 当前服务。
- 用户问题输入框。
- Agent 推荐 Skill。
- 能力就绪状态。
- 风险确认。
- 执行过程。
- 诊断报告。
- 是否沉淀候选记忆。

#### 9.1.1 AI 助手入口重构原则

现有“AI 助手”如果继续按 `Arthas / K8s / 通用问答 / Skill` 分组让用户手动选择，会和新的平台定位冲突。用户真正关心的是“某个 Java 服务现在出了什么问题”，不是先判断该点 K8s 还是 Arthas。

因此 P0 应将“AI 助手”重命名并收敛为 **JVM 诊断 Agent**：

| 当前形态 | 目标形态 |
|---|---|
| 用户打开“AI 助手”后还要选 Arthas / K8s 能力组 | 用户选择或输入 `service_name`，Agent 自动加载服务上下文 |
| 工具按技术栈暴露给用户 | 工具按诊断意图由 Agent 内部路由 |
| Pod / Arthas 连接是用户前置操作 | 连接状态是 Agent 的能力就绪状态，需要时引导升级或自动解析 |
| AI 聊天和诊断中心割裂 | 诊断中心内置 Agent Chat、Skill 推荐、证据采集和报告闭环 |

#### 9.1.2 交互模型：服务优先，而不是工具优先

诊断中心首屏建议采用三段式：

1. **服务上下文栏**：选择 `cluster + namespace + service_name`，展示当前解析到的 Pod、Java 进程、Arthas 状态、MCP 状态和记忆加载状态。
2. **问题输入区**：用户直接描述现象，例如“order-service CPU 又高了”“最近 Full GC 变多”“接口 /submit 变慢”。
3. **Agent 执行区**：Agent 自动拆解意图，展示将要使用的 Skill、Arthas 命令、MCP Tool 和风险等级。

用户不需要选择“Arthas 组”或“K8s 组”。这些只作为 Agent 内部能力层：

| 用户意图 | Agent 内部路由 |
|---|---|
| CPU 高、线程阻塞、死锁 | JVM Diagnosis Skill + Arthas `thread/dashboard/profiler` |
| 内存上涨、OOM、对象异常 | JVM Diagnosis Skill + Arthas `heapdump/vmtool/memory` |
| Pod 不稳定、重启、资源限制 | K8s 观察能力 + Pod 事件/日志/资源指标 |
| 需要外部工具或扩展上下文 | 白名单 MCP Tool |
| 不确定问题类型 | 先做低风险快照，再推荐下一步诊断路径 |

#### 9.1.3 能力就绪状态替代手动分组

页面不再把能力做成多个入口让用户挑，而是在当前服务下展示能力状态：

| 状态项 | 展示含义 | 用户动作 |
|---|---|---|
| 服务画像 | 已识别 / 待确认 / 缺失 | 可确认或编辑 `PROFILE.yaml` |
| Pod 解析 | 当前 Ready Pod / 多副本待选择 / 未找到 | 可让 Agent 自动选择或手动指定 |
| Arthas | 已就绪 / 可升级 / 启动中 / 失败 | 高风险操作前确认 |
| MCP | 服务级可用 / 仅连接级可用 / 不可用 | 可进入 MCP 管理绑定服务级 Token |
| 记忆 | 已加载 / 仅候选 / 无记忆 | 可查看 `MEMORY.md` 和 `CANDIDATES.md` |
| Skill | 推荐可用 / 需参数 / 风险确认 | 可执行、跳过或调整参数 |

这个状态条是“诊断座舱”，不是导航分组。它告诉用户 Agent 现在能做什么、缺什么、下一步如何补齐。

#### 9.1.4 Agent 执行策略

Agent 的默认行为应是：

1. 先识别或确认 `service_name`。
2. 加载 `PROFILE.yaml`、`MEMORY.md`、`PLAYBOOKS.md` 和历史案例。
3. 根据用户问题判断症状类型。
4. 选择 Skill 和 MCP/Arthas 工具。
5. 如果缺少 Arthas 连接，先尝试基于服务解析当前 Pod，并引导用户确认启动 Arthas。
6. 执行低风险采集；中高风险命令必须先展示影响和确认。
7. 输出诊断报告，并生成候选记忆。

这意味着“AI 助手”不是一个独立聊天抽屉，而是诊断流程的智能编排层。抽屉可以保留，但语义应变成“当前服务的诊断 Agent 侧栏”，上下文自动跟随当前服务。

### 9.2 服务记忆中心

按 `service_name` 管理：

- 服务画像。
- 诊断历史。
- `MEMORY.md` 稳定记忆。
- `CANDIDATES.md` 候选记忆待确认。
- `PROFILE.yaml` / `PLAYBOOKS.md` 文件导入、导出和预览。
- `evidence/{run_id}.json` 证据索引。
- 推荐 Skill。
- 历史案例。

### 9.3 Skill 管理中心

聚焦 JVM 诊断 Skill：

- Skill 分类筛选。
- 本地导入。
- 市场导入。
- 校验。
- 发布。
- 绑定服务。
- 更新和回滚。

### 9.4 MCP 管理中心

聚焦诊断工具边界：

- MCP Server 配置。
- Tool 发现。
- Tool 白名单。
- 权限绑定。
- 服务级 MCP 绑定：按 `service_name + cluster_name + namespace` 绑定，而不是只绑定一次性 Pod。
- 自动重连状态：展示当前解析到的 Pod、Arthas 连接健康状态和最近一次重连时间。
- 健康检查。
- 调用审计。

---

## 10. API 设计

### 10.1 服务画像 API

| API | 说明 |
|---|---|
| `GET /api/services/profiles` | 查询服务画像列表 |
| `POST /api/services/profiles` | 创建服务画像 |
| `GET /api/services/profiles/{service_name}` | 查询服务画像 |
| `PUT /api/services/profiles/{service_name}` | 更新服务画像 |
| `POST /api/services/profiles/{service_name}/detect` | 从连接和 Pod 自动探测画像 |
| `POST /api/services/profiles/{service_name}/import-config` | 从服务配置包导入画像 |
| `GET /api/services/profiles/{service_name}/export-config` | 导出服务配置包 |

### 10.2 服务记忆 API

| API | 说明 |
|---|---|
| `GET /api/services/{service_name}/memory/files` | 查询 `data/memory` 下该服务的文件列表和摘要 |
| `GET /api/services/{service_name}/memory/file?name=MEMORY.md` | 读取指定记忆文件 |
| `PUT /api/services/{service_name}/memory/file?name=MEMORY.md` | 保存人工编辑后的记忆文件 |
| `POST /api/services/{service_name}/memory/candidates` | 将 Agent 生成的候选记忆追加到 `CANDIDATES.md` |
| `POST /api/services/{service_name}/memory/candidates/confirm` | 将候选记忆合并到 `MEMORY.md`，并记录 `FEEDBACK.md` |
| `POST /api/services/{service_name}/memory/candidates/reject` | 否定候选记忆，写入 `FEEDBACK.md` |
| `GET /api/services/{service_name}/cases` | 查询历史案例 |
| `GET /api/services/{service_name}/memory/evidence/{run_id}` | 读取某次诊断的证据索引 |

### 10.3 Agent 诊断 API

| API | 说明 |
|---|---|
| `POST /api/diagnosis/agent/start` | 开始 Agent 诊断 |
| `POST /api/diagnosis/agent/{session_id}/message` | 继续对话 |
| `POST /api/diagnosis/agent/{session_id}/run-skill` | 执行推荐 Skill |
| `GET /api/diagnosis/agent/{session_id}/report` | 获取诊断报告 |
| `POST /api/diagnosis/agent/{session_id}/memory-review` | 提交记忆确认结果 |

`POST /api/diagnosis/agent/start` 的请求语义应服务优先：

```json
{
  "service_name": "order-service",
  "cluster_name": "prod-k8s",
  "namespace": "order",
  "user_problem": "CPU 又高了，帮我定位",
  "intent": "auto",
  "connection_id": "optional-current-connection",
  "preferred_pod_name": "optional-current-pod"
}
```

- `service_name + cluster_name + namespace` 是长期上下文主键。
- `connection_id` 只作为本次已有连接的加速提示，不作为长期记忆主键。
- `intent=auto` 表示由 Agent 内部选择 Arthas、K8s、Skill 或 MCP 能力。
- 响应必须返回能力就绪状态，而不是要求前端先选择能力组。

### 10.4 Agent 配置 API

| API | 说明 |
|---|---|
| `GET /api/agents/config-packs` | 查询 Agent 配置包 |
| `GET /api/agents/config-packs/{agent_name}` | 查询指定 Agent 配置 |
| `POST /api/agents/config-packs/{agent_name}/validate` | 校验配置包 |
| `POST /api/agents/config-packs/{agent_name}/import` | 导入配置包为草稿 |
| `GET /api/agents/config-packs/{agent_name}/export` | 导出配置包 |

### 10.5 Skill / MCP 复用现有 API

优先复用现有接口：

- `/api/skills/registry/*`
- `/api/skills/orchestrator/*`
- `/api/skills/agent/tools/*`
- `/api/mcp/*`

不足部分只做 JVM 诊断语义扩展，不另起一套泛化平台 API。

### 10.6 服务级 MCP 扩展 API（规划）

| API | 说明 |
|---|---|
| `POST /api/mcp/tokens` | 创建 MCP Token；P0 兼容 `connection` 作用域，规划支持 `service` 作用域 |
| `GET /api/mcp/tokens/{id}/resolve` | 查看当前 token 解析到的服务、Pod、连接和健康状态 |
| `POST /api/services/{service_name}/mcp-bindings` | 为服务创建 MCP 绑定，写入 `scope_type='service'`、`cluster_name`、`namespace` |
| `GET /api/services/{service_name}/mcp-bindings` | 查看服务级 MCP 绑定和最近调用状态 |
| `POST /api/services/{service_name}/connections/resolve` | 根据服务画像解析当前 Ready Pod，并建立或复用 Arthas 连接 |

请求参数建议：

```json
{
  "scope_type": "service",
  "service_name": "order-service",
  "cluster_name": "prod-k8s",
  "namespace": "order",
  "allowed_tools": ["jvm.get_dashboard", "jvm.get_top_threads", "diagnosis.run_skill"],
  "expires_in_days": 30
}
```

响应必须包含本次实际解析结果：

```json
{
  "service_name": "order-service",
  "resolved_connection_id": "prod-k8s/order/order-service-7cc5",
  "resolved_pod_name": "order-service-7cc5",
  "connection_status": "healthy",
  "reconnected": false
}
```

---

## 11. P0 / P1 / P2 范围

### 11.1 P0：闭环最小可用

| 模块 | P0 内容 |
|---|---|
| 服务识别 | 从连接、Pod 标签、用户输入识别 `service_name` |
| 服务画像 | 使用 `data/memory/.../PROFILE.yaml` 创建和编辑 Java Service Profile |
| 服务记忆 | 使用 `MEMORY.md`、`CANDIDATES.md`、`FEEDBACK.md` 支持候选、确认、否定和按服务加载 |
| JVM Skill | 建立 CPU、慢请求、线程、GC 的基础 Skill |
| Agent | 基于问题描述推荐 Skill 并生成报告 |
| MCP | 只暴露白名单 JVM 诊断工具；保留 `connection` 绑定兼容，同时明确服务级绑定与自动重连设计 |
| 记录 | 诊断过程和报告进入 `task_logs` |
| 配置包 | 定义平台级、Agent 级、服务级配置结构，支持服务画像导入/导出 |

### 11.2 P1：诊断效果增强

- 更多 Skill：内存、类加载、JVM 参数、热修复验证。
- 服务记忆文件索引、全文检索和轻量置信度统计。
- 历史案例相似度检索。
- Skill 成功率和服务级偏好统计。
- 应用画像自动补全。
- 记忆候选批量审核。
- `data/memory` 文件 diff 审核、GitOps 同步和 `memory_file_index` 索引表。
- 服务级 MCP Token 字段迁移、绑定管理 UI 和自动重连健康视图。

### 11.3 P2：自治诊断能力

- 多 Agent 协同诊断。
- 事件触发自动诊断。
- 异常检测与服务记忆联动。
- 诊断知识跨服务迁移。
- 团队级知识库和经验复盘。
- Agent 基于反馈生成配置修订建议，但仍需人工审核发布。

---

## 12. 关键架构决策

### ADR-001：平台对象从 Pod 提升到 Java Service

- **决策**：以 `service_name` 作为诊断知识沉淀主键。
- **原因**：Pod 会重建，连接是临时的，服务才是长期知识资产。
- **代价**：需要处理 service_name 识别、同名服务、跨 namespace 场景。

### ADR-002：Agent 不能直接执行任意命令

- **决策**：Agent 只能调用已注册 Skill 或白名单 MCP Tool。
- **原因**：线上 JVM 诊断有风险，必须控制权限、参数、超时、审计。
- **代价**：需要维护 Tool Gateway 和 Skill 白名单。

### ADR-003：服务记忆采用文件优先，而不是 P0 新增记忆表

- **决策**：P0 将服务画像和服务记忆保存在 `data/memory/` 下的 Markdown/YAML 文件中；Agent 只能追加 `CANDIDATES.md`，稳定记忆由用户确认后合入 `MEMORY.md`。
- **原因**：文件机制更接近 Claude / WorkBuddy 的上下文管理方式，可读、可审查、可手工修正，不需要一开始设计复杂表结构和迁移。
- **代价**：P0 的检索和统计能力有限；P1 如需要全文检索和批量管理，再补 `memory_file_index` 这类轻量索引表。

### ADR-004：Skill 聚焦 JVM 诊断，不做泛能力市场

- **决策**：Skill Registry 在本平台中优先承载 JVM Diagnosis Skill。
- **原因**：平台定位是 Arthas/JVM 诊断，泛化会降低产品聚焦度。
- **代价**：外部 Skill 导入需要做分类和风险过滤。

### ADR-005：引入 Agent 配置包和本地记忆目录，但自进化必须受控

- **决策**：借鉴配置文件拆分方式，将 Agent 身份、启动流程、工具边界、记忆策略配置化；服务级画像和记忆落在 `data/memory/`。
- **原因**：配置文件可读、可评审、可导入导出，有利于系统越用越聪明。
- **约束**：Agent 只能生成候选记忆和配置修订建议，不能自动改写 `MEMORY.md`、`PROFILE.yaml` 等稳定文件。

### ADR-006：MCP 能力从 Pod 绑定升级为服务级绑定

- **决策**：长期 MCP 能力以 `service_name + cluster_name + namespace` 作为稳定绑定对象，运行时动态解析当前 Pod 和 Arthas 连接；保留 `connection_id` 绑定作为临时调试兼容路径。
- **原因**：Pod 会因滚动发布、重启、扩缩容而变化，基于 Pod 的 MCP Token 会频繁失效；服务才是 Agent 记忆、Skill 偏好和诊断能力的长期对象。
- **代价**：需要 Service Resolver、连接健康检查、自动重连和实际 Pod 审计记录。
- **约束**：自动重连不能跨服务漂移，不能扩大用户权限，诊断报告必须记录本次实际连接和 Pod。

### ADR-007：AI 助手不再按工具分组暴露

- **决策**：将泛化“AI 助手”收敛为“JVM 诊断 Agent”，入口按服务组织，不再要求用户手动选择 Arthas / K8s / MCP / Skill 分组。
- **原因**：平台核心对象已经从 Pod/连接提升为 Java Service；用户问题是服务症状，工具选择应由 Agent 根据意图、服务画像和能力就绪状态内部路由。
- **代价**：前端需要从工具 Tab 思维调整为服务上下文座舱；后端需要返回统一的能力就绪状态和推荐执行计划。
- **约束**：工具仍不能被 Agent 任意调用，所有 Arthas、K8s、MCP 和 Skill 执行必须通过 Tool Gateway、权限校验、风险确认和审计。

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Agent 幻觉导致错误结论 | 误导用户 | 报告必须引用 Arthas/MCP 证据，标注置信度 |
| 记忆污染 | 后续推荐越来越错 | 候选/稳定分层，用户确认，低置信度不参与推荐 |
| 任意命令风险 | 线上服务受影响 | Tool Gateway 白名单、风险确认、超时限制 |
| 服务名识别错误 | 记忆写错服务 | 用户可手动绑定，写入时显示 service_name 确认 |
| Skill 过度复杂 | 维护困难 | P0 只做高频 JVM 场景，复杂编排放 P1/P2 |
| MCP Server 不稳定 | Agent 调用失败 | 健康检查、超时、降级到 Arthas HTTP API |
| 服务级 MCP 自动重连连错 Pod | 证据污染或误操作其他服务 | 只能在同一 `service_name + cluster_name + namespace` 内解析，报告记录实际 Pod，必要时要求用户确认 |
| 自进化失控 | 错误记忆或错误配置被长期使用 | 候选/稳定分层、人工确认、版本化、可回滚 |
| 记忆文件与数据库索引不一致 | Agent 行为不可预测 | P0 以 `data/memory` 文件为记忆权威；数据库索引可重建，不保存完整记忆正文 |

---

## 14. 验收标准

P0 完成后应满足：

- [ ] 用户可按 `service_name` 创建和查看 `PROFILE.yaml` 服务画像。
- [ ] 当前 Arthas 连接可绑定或识别到一个 Java Service。
- [ ] 用户描述 JVM 问题后，Agent 能推荐合适的 JVM Diagnosis Skill。
- [ ] Agent 执行 Skill 必须通过 Agent Tool Gateway。
- [ ] MCP 只暴露白名单 JVM 诊断工具。
- [ ] MCP 设计明确区分 `connection` 临时绑定和 `service` 长期绑定；服务级调用必须记录实际解析到的 Pod 和连接。
- [ ] 每次诊断生成结构化报告并写入 `task_logs`。
- [ ] 诊断结束后可将候选记忆追加到 `CANDIDATES.md`。
- [ ] 用户可确认或否定候选记忆；确认后合并到 `MEMORY.md`。
- [ ] 后续同服务诊断会加载 `MEMORY.md` 中的 confirmed 记忆。
- [ ] 所有高风险操作需要用户确认并记录审计日志。
- [ ] JVM 诊断 Agent 有明确配置包结构。
- [ ] 服务画像和服务记忆可在 `data/memory/` 下导入、导出和审阅。
- [ ] 自进化结果只能进入 `CANDIDATES.md` 或配置修订建议，不能自动覆盖 `MEMORY.md` / `PROFILE.yaml`。

---

## 15. 与其他文档关系

| 文档 | 关系 |
|---|---|
| `docs/specs/03-diagnosis-center.md` | 本文进一步收敛诊断中心的 Agent 化和服务记忆方向 |
| `docs/specs/11-agent-integration-architecture.md` | 本文限定 Agent 集成服务于 JVM 诊断，不做泛 Agent 平台 |
| `docs/specs/12-skill-registry-workflow-engine-gateway.md` | 本文限定 Skill Registry 聚焦 JVM Diagnosis Skill |
| `docs/specs/06-data-model.md` | 后续只需补充 `data/memory` 文件索引和可选 `memory_file_index`，不在 P0 新增复杂记忆表 |
| `docs/specs/07-api-design.md` | 后续需要补充服务画像文件、记忆文件、Agent 诊断 API |
