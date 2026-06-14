# 任务中心实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 任务中心负责 run 生命周期、日志、调度、清理、产物索引，不直接执行 kubectl、不直接维护 port-forward、不直接执行 Arthas HTTP 细节。

**Architecture:** 任务中心作为执行记录和调度中心，与连接中心、诊断中心、工具箱明确边界。统一执行日志以 `task_logs` 作为权威表，支持即时诊断和定时任务。

**Tech Stack:** Python, Flask, SQLite, pytest

---

## 1. 目标

任务中心负责 run 生命周期、日志、调度、清理、产物索引，不直接执行 kubectl、不直接维护 port-forward、不直接执行 Arthas HTTP 细节。

## 2. 架构决策

### 2.1 数据模型决策

| 主题 | 决策 |
|---|---|
| 统一执行日志 | 以 `task_logs` 作为新执行日志权威表 |
| `task_runs` 处理 | 视为旧兼容表或待迁移概念，不再扩大新增写入 |
| 即时诊断 | 不创建 `task_definitions`，直接创建 `task_logs` |
| 定时/手动任务 | 可保留 `task_definitions` 作为定义层，但执行记录进入 `task_logs` |
| Arthas 命令历史 | 单条命令仍可写 `arthas_commands`，但必须能通过 `run_id`/`correlation_id` 关联到 `task_logs` |
| 历史可追溯 | 执行开始即固化连接快照、能力快照、参数快照、渲染命令和能力版本 |

### 2.2 执行边界决策

| 组件 | 应负责 | 不应负责 |
|---|---|---|
| 任务中心 | run 生命周期、日志、调度、清理、产物索引 | 直接执行 kubectl、直接维护 port-forward、直接执行 Arthas HTTP 细节 |
| 诊断中心 | 能力目录、参数表单、即时执行、场景编排、历史与报告 | 成为新的连接中心或万能工具市场 |
| 连接中心 | 连接状态、连接快照、健康探测、连接复用 | 长任务业务逻辑、诊断模板解析 |
| 执行器 | Pod / Arthas 原语执行、命令超时、连接保护 | UI 状态、能力管理、调度策略 |
| 前端 `DiagnosisContext` | 当前连接上下文、运行中任务索引、真实 `run_id` 轮询 | 生成替代后端的伪运行 ID、连接切换时默认取消所有后端任务 |

### 2.3 API 决策

| 场景 | 目标 API | 落库 |
|---|---|---|
| 能力目录 | `GET /api/tasks/capabilities` | `diagnosis_capabilities` |
| 能力详情 | `GET /api/tasks/capabilities/{id}` | `diagnosis_capabilities` + 扩展信息 |
| 能力管理 | `POST/PUT/DELETE /api/tasks/capabilities` | `diagnosis_capabilities`，软删除/禁用优先 |
| 即时诊断 | `POST /api/tasks/diagnosis/execute` | `task_logs(execution_mode='immediate')` |
| 状态查询 | `GET /api/tasks/diagnosis/executions/{run_id}/status` | `task_logs` |
| 取消执行 | `POST /api/tasks/diagnosis/runs/{run_id}/cancel` | `task_logs.status='cancelled'` + 执行器中断标记 |
| 诊断历史 | `GET /api/tasks/diagnosis/history` | `task_logs` |
| 任务执行历史 | `GET /api/tasks/runs` | 目标改为读 `task_logs`，兼容旧 `task_runs` |

## 3. 当前落地状态

### 3.1 已落地或基本具备

| 模块 | 状态 | 代码位置 |
|---|---|---|
| `task_logs` 扩展字段 | 已有较完整迁移逻辑 | `models/db.py` |
| `task_logs` 核心索引 | 已有 `execution_mode`、`execution_type`、`run_type`、`status` 等索引 | `models/db.py` |
| 诊断能力种子数据 | 已有 quick/tool/scenario/ai 能力初始化 | `backend/core/diagnosis_capabilities.py` |
| 能力查询 | 已有列表和详情接口 | `api/task_center.py` |
| 参数校验 | 已接入 `ParameterValidator` | `api/task_center.py` |
| 即时诊断执行 | 已有 `POST /api/tasks/diagnosis/execute` | `api/task_center.py` |
| 执行开始创建日志 | 已有 `_create_task_log_for_diagnosis()` | `api/task_center.py` |
| 快照字段写入 | 已写连接快照、能力快照、参数、渲染命令 | `api/task_center.py` |
| 状态查询 | 已有按 `run_id` 查询接口 | `api/task_center.py` |
| 诊断历史 | 已有按 `task_logs` 查询 | `api/task_center.py` |
| 定时任务基础 | 已有 `task_schedules` 和后台轮询 | `api/task_center.py` |
| 前端能力卡片 | 已有加载、过滤、执行能力逻辑 | `static/js/components/diagnosis.js` |
| 前端运行上下文 | 已有 `DiagnosisContext` 与真实 `run_id` 兼容逻辑 | `static/js/core/diagnosis-context.js` |

### 3.2 仍需纠偏

| 问题 | 影响 | 优先级 |
|---|---|---|
| 通用任务仍写 `task_runs` | 与统一 `task_logs` 决策冲突，历史查询分裂 | P0 |
| 部分接口仍查询 `task_runs` | 若表已迁移为 `task_logs`，存在运行时错误风险 | P0 |
| 能力 CRUD 缺少 POST/PUT/DELETE | 管理员无法维护能力生命周期 | P0 |
| `_execute_scenario()` 调用与函数签名不一致 | 场景方案异步执行会触发参数错误 | P0 |
| 取消接口主要是改状态 | 无法可靠中断已提交线程或场景后续步骤 | P0 |
| 连接校验只按 Arthas Ready 处理 | Pod 级能力与 Arthas 能力缺少分层校验 | P0 |
| 场景方案失败策略不完整 | 只能近似 fail-fast，缺 `on_failure`/`required`/`timeout` 标准语义 | P1 |
| handler 字段存在配置污染风险 | AI 诊断 handler 不宜直接变成任意 import 路径 | P1 |
| 前端统一诊断中心入口未完全产品化 | 仍像能力卡片组件，缺子导航、运行中面板、历史/报告整合 | P1 |
| 多连接选择器能力过滤不足 | 用户可能选错连接层级或运行中切换上下文导致误解 | P1 |

## 4. P0 范围

P0 只做能形成稳定闭环的内容：

1. 统一 `task_logs` 执行语义
2. 修复诊断执行 API 的场景方案、状态、取消、连接校验问题
3. 补齐能力管理最小 CRUD
4. 将新增通用任务和调度执行记录迁移到 `task_logs`
5. 前端使用真实 `run_id` 完成执行、轮询、取消、历史展示

P0 明确不做：

- 完整 LLM RCA 报告
- 异常自动检测与告警中心
- 案例库与知识推荐
- 工具市场与拖拽编排
- WebSocket 实时输出
- 用户组级复杂能力权限
- 在线修复的全自动业务验证与自动回滚

## 5. 实施计划

## Phase A：统一执行日志语义

### A1. 固化 `task_logs` 为权威运行表

**目标**：新增执行入口只写 `task_logs`，不再扩大 `task_runs`。

行动：
- 梳理所有 `task_runs` 读写点
- 对新增执行路径改写为 `task_logs`
- 对旧历史查询增加兼容读取，避免历史数据不可见
- 保留旧输出目录命名可以暂不改，但数据库语义必须收敛

重点文件：
- `api/task_center.py`
- `models/db.py`
- `static/js/components/task-center.js`

验收：
- [ ] 新增即时诊断写入 `task_logs`
- [ ] 新增手动任务执行写入 `task_logs(execution_mode='manual')`
- [ ] 新增调度任务执行写入 `task_logs(execution_mode='scheduled')`
- [ ] `GET /api/tasks/runs` 可返回 `task_logs` 运行记录
- [ ] 旧 `task_runs` 记录仍可兼容查看

### A2. 统一 `run_id / execution_id / task_logs.id`

**目标**：前后端只认一个服务端真实运行 ID。

规则：
```text
task_logs.id == run_id == execution_id
```

行动：
- 后端执行入口创建 `run_id` 后立即插入 `task_logs`
- 所有响应统一返回 `run_id` 与 `execution_id`，且两者相同
- 前端允许临时本地 ID，但必须在后端响应后替换为真实 `run_id`
- 取消、轮询、历史详情只能使用真实 `run_id`

验收：
- [ ] quick/tool 同步执行返回真实 `run_id`
- [ ] scenario/ai 异步执行返回真实 `run_id`
- [ ] 前端运行中列表展示后端 `run_id`
- [ ] 取消请求命中同一条 `task_logs`

### A3. 执行开始即写入快照

**目标**：历史记录不受后续连接、能力、参数变化影响。

必须写入：
- `connection_snapshot_json`
- `capability_snapshot_json`
- `params_json`
- `capability_name`
- `capability_version`
- `rendered_command`
- `target_json`

验收：
- [ ] 能力禁用或修改后，历史记录仍能还原当时能力定义
- [ ] 连接删除或状态变化后，历史记录仍能看到当时连接信息
- [ ] 历史详情能看到实际执行命令或场景步骤命令

---

## Phase B：修正诊断执行闭环

### B1. 修复场景方案执行签名

当前 `_run_diagnosis_execution()` 调用：

```python
_execute_scenario(capability, extension, params, active_conn, run_id=run_id)
```

但 `_execute_scenario()` 当前签名未接收 `run_id`。应修正为：

```python
def _execute_scenario(capability, extension, params, connection, run_id=None):
    ...
```

并在每一步执行前检查取消状态：

```python
if run_id and _is_task_log_cancelled(run_id):
    break
```

验收：
- [ ] scenario 能成功进入后台线程
- [ ] 取消 scenario 后不会继续执行后续步骤
- [ ] result 中包含已完成步骤、取消状态和耗时

### B2. 分层连接校验

**目标**：不同能力按层级选择不同连接要求。

| 能力类型 | 连接要求 | 行为 |
|---|---|---|
| Pod 文件/日志/脚本 | `level=pod` 或 `level=arthas` | Arthas 连接可作为 Pod 上下文复用 |
| Arthas 命令 | `level=arthas` 且 HTTP Ready | Pod-only 连接提示升级 |
| profiler/JFR/dump | `level=arthas`、PID 已确认 | 展示风险与预计耗时 |
| redefine/热更新 | `level=arthas`、PID、类名、SHA256、二次确认 | 必须强确认 |

行动：
- 将 `_ensure_arthas_connection_ready()` 扩展为能力感知校验
- 根据 `capability.category`、`capability.level`、`risk_level` 决定连接要求
- 返回前端可理解的错误码和引导动作：`connect_pod`、`upgrade_arthas`、`confirm_risk`

验收：
- [ ] Pod 级能力不强制 Arthas Ready
- [ ] Arthas 能力不会误用 Pod-only 连接
- [ ] 无可用连接时前端展示建立连接或升级入口

### B3. 取消语义升级

**P0 目标**：至少做到步骤级中断和状态一致。

行动：
- `cancel` 将 `pending/running` 更新为 `cancelled`
- 场景方案每步前检查 `task_logs.status`
- 执行完成回写时必须先检查是否已取消，避免覆盖 `cancelled`
- `DiagnosisExecutorPool` 维护 `run_id → future/cancel_token` 的结构预留

**P1 目标**：主动取消 future 或执行器 cancel token。

验收：
- [ ] 取消后状态不会被后续成功结果覆盖
- [ ] 场景方案取消后停止后续步骤
- [ ] 前端取消按钮状态与后端一致

---

## Phase C：能力管理最小闭环

### C1. 管理员 CRUD

目标 API：
- `POST /api/tasks/capabilities`
- `PUT /api/tasks/capabilities/{id}`
- `DELETE /api/tasks/capabilities/{id}`

规则：
- 仅 admin 可创建、更新、禁用内置能力
- 删除优先实现为软删除或 `status='disabled'`
- 禁止物理删除已被 `task_logs.capability_id` 引用的能力
- 每次更新能力时递增 `version`

能力字段最小集：

| 字段 | P0 要求 |
|---|---|
| `name` | 必填 |
| `category` | 必填，`quick/tool/scenario/ai` |
| `level` | 必填，能力层级 |
| `parameters_schema` | 必填或默认 `{}` |
| `status` | `active/disabled` |
| `is_builtin` | 区分内置和自定义 |
| `sort_order` | 控制展示排序 |
| `visibility` | P0 简化为 `public/private` |
| `version` | 更新递增 |

### C2. handler 安全

AI 能力不应让数据库直接保存任意可 import 路径。目标改为：

```text
handler_key = "slow_request_analysis"
registry[handler_key] = actual_callable
```

验收：
- [ ] 数据库只保存 `handler_key`
- [ ] 代码白名单注册表负责映射 handler
- [ ] 未注册 handler 返回明确错误，不执行任意导入

---

## Phase D：通用任务与定时任务迁移

### D1. 通用任务写入 `task_logs`

当前通用任务仍存在明显 `task_runs` 读写。目标：

```text
task_definitions → task_logs(execution_mode='manual')
```

字段映射：

| 旧语义 | 新字段 |
|---|---|
| `task_runs.id` | `task_logs.id` |
| `task_runs.task_id` | `task_logs.task_id` |
| 脚本/命令类型 | `task_logs.execution_type='script'` |
| 手动运行 | `task_logs.execution_mode='manual'` |
| 运行状态 | `task_logs.status` |
| 输出结果 | `task_logs.result_json` 或 `log_path` |

### D2. 定时任务写入 `task_logs`

目标：

```text
task_definitions → task_schedules → task_logs(execution_mode='scheduled')
```

约束：
- 定时任务 P0 不支持依赖用户本地 port-forward 的 Arthas 连接模式
- 定时任务只支持 node/pod 可稳定执行的脚本或健康检查
- 调度失败也必须写 `task_logs`，便于审计

验收：
- [ ] 手动运行任务新增记录进入 `task_logs`
- [ ] 调度运行任务新增记录进入 `task_logs`
- [ ] 调度失败有失败日志和错误信息
- [ ] 前端任务中心历史来自统一日志视图

---

## Phase E：前端诊断中心产品化

### E1. 统一入口

目标菜单：

```text
诊断中心
├── 快捷诊断
├── Arthas 工具
├── 场景方案
├── 智能诊断
├── 运行中
├── 历史记录
└── 能力管理（admin）
```

行动：
- 侧边栏保留一个诊断中心主入口
- 旧入口保留兼容函数，但不作为主产品路径
- `diagnosis.js` 从能力卡片组件升级为诊断中心控制器

### E2. 多连接选择器

规则：
- 只有一个符合条件连接时自动选中，但展示连接摘要
- 多个符合条件连接时弹出选择器
- 无符合条件连接时展示建立 Pod 连接或升级 Arthas 连接入口
- 执行开始后连接选择随 `run_id` 固化
- 前端当前连接切换只影响后续新建诊断，不自动取消已运行任务

### E3. 运行中与历史面板

运行中面板必须展示：
- `run_id`
- 能力名称与版本
- 连接快照摘要
- 当前状态
- 开始时间与耗时
- 取消按钮
- 轮询错误提示

历史详情必须展示：
- 连接快照
- 能力快照
- 参数
- 实际命令
- 步骤结果
- 结果/错误
- 耗时
- 状态

验收：
- [ ] 诊断中心子菜单切换正常
- [ ] 无连接时不能误执行
- [ ] 执行中任务使用真实 `run_id`
- [ ] 取消按钮命中真实后端记录
- [ ] 历史详情可追溯快照与实际命令

---

## 6. 推荐实施顺序

1. **修复 P0 运行错误**
   - 修复 `_execute_scenario(..., run_id=...)` 签名不一致
   - 场景步骤前检查取消状态
2. **收敛 `task_logs`/`task_runs` 双轨**
   - 新增写入统一进入 `task_logs`
   - 查询接口兼容旧数据
3. **补齐诊断执行状态闭环**
   - 校验连接层级
   - 统一 `run_id`
   - 取消状态不被覆盖
4. **补齐能力 CRUD**
   - admin 创建/更新/禁用能力
   - 更新能力版本与快照策略
5. **迁移通用任务与调度日志**
   - 手动任务、定时任务执行记录进入 `task_logs`
6. **前端统一诊断中心**
   - 子导航、连接选择、运行中、历史、能力管理
7. **回归验证**
   - 后端 API、前端流程、权限隔离、历史追溯

## 7. 涉及文件清单

| 文件 | 类型 | 计划动作 |
|---|---|---|
| `models/db.py` | 数据库 | 确认 `task_logs` 迁移幂等、补齐兼容视图或索引、避免新旧表混乱 |
| `api/task_center.py` | 后端 API | 修复场景方案签名、取消语义、能力 CRUD、通用任务迁移、状态查询一致性 |
| `backend/core/diagnosis_executor_pool.py` | 执行池 | 接入 `run_id → future/cancel_token`，提供主动中断预留 |
| `backend/core/connection_aware_executor.py` | 连接保护 | 连接断开时更新真实 `task_logs`，避免孤儿运行态 |
| `backend/core/diagnosis_capabilities.py` | 能力目录 | 补齐生命周期字段和 handler_key 安全注册策略 |
| `static/js/core/diagnosis-context.js` | 前端状态 | 使用真实 `run_id`，连接切换不默认取消运行中任务 |
| `static/js/components/diagnosis.js` | 前端控制器 | 升级为统一诊断中心入口，接入轮询、取消、历史详情 |
| `static/js/components/task-center.js` | 前端任务中心 | 从 `task_runs` 历史迁移到 `task_logs` 统一历史 |
| `static/js/app-ui.js` | 页面切换 | 接入 `diagnosis-center` 主入口 |
| `static/css/app.css` | 样式 | 增加诊断中心子导航、运行中面板、历史详情样式 |

## 8. 风险与处理策略

| 风险 | 等级 | 策略 |
|---|---|---|
| `task_runs` 与 `task_logs` 双轨导致查询不一致 | 高 | 新写入统一 `task_logs`，旧数据兼容读取，逐步迁移 |
| 场景方案取消无法中断已发出的 Arthas HTTP 请求 | 中 | P0 做步骤级中断，P1 接入 future/cancel token |
| 能力删除破坏历史 | 高 | 禁止硬删除已引用能力，使用禁用或软删除 |
| 连接切换影响运行中任务 | 中 | run 固化连接快照，连接切换只影响新任务 |
| 同步改异步影响旧前端 | 中 | quick/tool 保留同步结果，同时统一返回 `run_id` |
| handler 配置污染 | 中 | 使用 `handler_key` + 代码白名单注册表 |
| 定时任务依赖用户 port-forward | 高 | P0 定时任务不支持 Arthas 连接模式，只支持稳定 pod/node 执行 |

## 9. 最小闭环验收标准

本轮完成后必须达到：

1. 用户从统一诊断中心选择连接和能力
2. 点击执行后立即生成真实 `task_logs.id/run_id`
3. 前端按真实 `run_id` 展示运行中状态并轮询
4. 后端完成后更新同一条 `task_logs`
5. 用户可取消运行中的场景方案，后续步骤停止
6. 历史记录可追溯连接快照、能力快照、参数、实际命令、结果、耗时和状态
7. 管理员可创建、更新、禁用能力
8. 普通用户只能执行和查看自己有权限的能力与运行记录
9. 手动任务和定时任务的新执行记录进入 `task_logs`
10. 前端主路径不再让用户在多个诊断入口之间迷路

## 10. 后续 P1/P2

### P1

- 场景方案标准失败策略：`on_failure='stop|continue|skip_remaining'`
- 步骤级输出映射：`output_mapping_json`
- 能力版本历史 UI
- 多连接选择器完整产品化
- future/cancel token 主动取消
- 在线修复 L0/L1 技术验证

### P2

- 异常自动检测规则与告警中心
- LLM RCA 报告
- 案例库和知识推荐
- AI 对话工具全量纳入能力平台
- MCP 全量通过诊断能力平台执行
- WebSocket 实时输出
- 工具市场和拖拽编排