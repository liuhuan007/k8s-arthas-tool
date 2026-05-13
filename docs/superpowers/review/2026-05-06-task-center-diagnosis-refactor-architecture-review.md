# 任务中心诊断重构架构评审报告

| 项目 | 内容 |
|---|---|
| 评审文档 | `docs/superpowers/specs/2026-05-04-task-center-diagnosis-refactor.md` |
| 评审日期 | 2026-05-06 |
| 评审视角 | 架构设计、现有工程兼容性、并发可靠性、产品交互闭环 |
| 总体评级 | ⭐⭐⭐⭐（4/5）：方向正确，但需要收敛状态边界和执行模型 |

---

## 1. 总体结论

该设计把任务中心从“脚本执行器”升级为“诊断能力目录 + 即时执行 + 场景编排”的方向是正确的，能够解决现有工具箱、任务中心、在线诊断割裂的问题。核心价值在于：用户不再先创建任务定义，而是基于 Arthas 能力模板直接执行诊断，并把执行记录沉淀为可审计日志。

当前主要风险不是功能方向，而是边界过宽：设计同时引入能力模型、执行器、日志表、连接状态、权限模型、版本管理、前端上下文和 AI handler，容易让任务中心再次变成“万能中心”。建议先把 P0 收敛为：能力目录、即时执行、执行日志、连接快照、结果渲染；把权限组、能力版本市场、复杂并发治理和 AI 自动诊断放到 P1/P2。

---

## 2. 关键优点

- **产品目标明确**：以 Arthas 在线诊断为核心，支持快捷工具、诊断模板、场景方案和智能诊断分层。
- **能力模型有扩展性**：`diagnosis_capabilities` 作为元数据核心表，扩展表按能力类型拆分，避免所有字段堆在一张宽表。
- **即时诊断体验合理**：跳过 `task_definitions` 的思路符合排障场景，降低“先建任务再执行”的操作成本。
- **参数 Schema 有价值**：通过统一参数定义驱动表单、校验和命令模板渲染，便于后续管理员配置能力。
- **前端模块化方向正确**：能力列表、参数表单、执行进度、结果渲染拆分，优于继续堆叠单个大 JS 文件。

---

## 3. 高优先级问题

### 3.1 P0：执行日志模型与现有 `task_runs` 不一致

**问题**：文档开头定义所有执行日志统一使用 `task_logs`，并引入 `arthas_command_logs`；但当前工程和数据库参考已经存在 `task_runs/task_artifacts/arthas_commands`。同时文档又在后续示例中出现 `task_runs`，导致执行记录到底落在哪张表不清晰。

**影响**：实现时可能出现三套日志：旧 `task_runs`、新 `task_logs`、Arthas 原有 `arthas_commands`，查询、清理、审计和前端历史都会分裂。

**建议**：
- P0 优先复用 `task_runs` 作为任务中心统一运行记录，新增 `run_type='diagnosis'`、`capability_id`、`connection_snapshot_json`、`result_json`、`log_path`。
- Arthas 单条命令继续写 `arthas_commands`；场景方案的步骤命令通过 `task_runs.id` 或 `correlation_id` 串联。
- 如果坚持新建 `task_logs`，必须在设计中给出从 `task_runs` 到 `task_logs` 的迁移、兼容查询和清理策略。

### 3.2 P0：即时诊断 API 与“跳过任务定义”目标矛盾

**问题**：设计目标强调即时诊断直接执行、无需创建任务定义，但 API 章节示例仍使用 `POST /api/tasks/definitions` 并返回 `task_id`。

**影响**：前端和后端会继续围绕 task definition 建模，无法真正简化即时诊断流程。

**建议**：拆成两条路径：

| 场景 | API | 落库 |
|---|---|---|
| 即时诊断 | `POST /api/diagnosis/capabilities/<id>/execute` | 创建 `task_runs` 运行记录，不创建 `task_definitions` |
| 定时/复用任务 | `POST /api/tasks/definitions` | 创建 `task_definitions`，调度时创建 `task_runs` |
| 场景方案 | `POST /api/diagnosis/scenarios/<id>/execute` | 创建一个父 `task_runs`，步骤写子步骤日志或 `arthas_commands` |

### 3.3 P0：状态管理器职责边界需要收敛

**问题**：文档提出前端 `DiagnosisContext` 和后端连接生命周期，但没有明确状态管理器与现有执行器的协作边界。若 `ConnectionStateManager` 同时负责连接探测、port-forward、Arthas 命令执行、任务取消和 DB 写入，会与 `KubectlExecutor`、`ArthasConnection`、任务执行器重复实现，并产生竞态。

**建议边界**：

| 组件 | 应负责 | 不应负责 |
|---|---|---|
| `ConnectionStateManager` | 状态编排、状态转换校验、连接快照、健康探测调度、事件发布 | 直接执行 kubectl、直接执行 Arthas 命令、长任务业务逻辑 |
| `KubectlExecutor` | `exec/cp/port-forward` 原语和超时封装 | 业务状态流转、诊断模板解析 |
| `ArthasConnection` / `ArthasHttpClient` | Arthas HTTP 调用、session/command/profiler 封装 | 任务排队、前端上下文管理 |
| `DiagnosisExecutor` | 能力解析、参数校验、执行编排、结果归档 | 维护全局连接列表、直接管理 port-forward 生命周期 |
| `TaskRunRepository` | `task_runs`/产物/日志短事务写入 | 执行命令、决定状态机下一跳 |

**竞态控制建议**：
- 执行开始时生成不可变 `connection_snapshot_json`，包含 `connection_id/cluster/namespace/pod/container/java_pid/local_port/status_version`。
- 每次执行前校验 `status_version` 或 `last_ping_at`，避免用户切换连接后旧请求误用新连接。
- 后端执行以 `run_id` 为幂等键，状态只允许 `pending → running → success/failed/cancelled` 单向转换。
- 连接状态变化通过事件通知执行器；执行器决定当前 run 是否失败、重试或继续，不由状态管理器直接取消业务任务。

### 3.4 P0：前端连接切换不应默认取消所有执行

**问题**：`DiagnosisContext.onConnectionChange` 示例中，连接切换会取消所有正在执行的诊断。这个交互对多连接排障不友好，用户切到另一个 Pod 查看信息时，原 Pod 的采样或 trace 不应被前端上下文直接取消。

**建议**：
- 前端“当前选中连接”只影响新建诊断的默认目标，不等同于服务端运行任务的生命周期。
- 运行中的诊断与 `run_id + connection_snapshot_json` 绑定，切换连接后继续在执行面板中展示。
- 只有用户点击“取消执行”或服务端连接失效，才取消 run。
- 多连接下顶部显示“当前连接”和“运行中诊断”两个区域，避免用户误以为切换连接会停止后台任务。

---

## 4. 产品交互待补充

### 4.1 多连接选择器

建议在执行诊断前按能力类型过滤连接，而不是让用户从所有连接里猜：

| 能力类型 | 连接要求 | 选择器行为 |
|---|---|---|
| Pod 文件/日志/脚本 | `level=pod` 或 `level=arthas` | 显示 Pod 可用连接；Arthas 连接也可作为 Pod 上下文使用 |
| Arthas 命令 | `level=arthas` 且 HTTP Ready | 只显示 Arthas Ready 连接；Pod-only 连接展示“升级为 Arthas 连接”按钮 |
| profiler/JFR/dump | `level=arthas`、PID 已确认、风险确认通过 | 显示风险标识和预计耗时 |
| 在线修复/redefine | `level=arthas`、PID、类名、class SHA256、二次确认 | 强制选择目标连接并展示不可折叠确认区 |

交互规则：
- 只有一个符合条件的连接时自动选中，但仍展示连接摘要。
- 多个符合条件连接时弹出选择器，展示集群、命名空间、Pod、容器、PID、状态、最后活跃时间。
- 无符合条件连接时，显示建立 Pod 连接或升级 Arthas 连接的快捷入口。
- 连接选择结果随 `run_id` 固化，执行过程中前端切换当前连接不影响该 run。

### 4.2 热更新验证自动化程度

在线修复不建议一开始做“全自动业务验证”，但需要明确 P1 的自动化边界：

| 层级 | 自动化内容 | P1 是否做 |
|---|---|---|
| L0 手动确认 | redefine 前展示目标、类名、SHA256、风险提示 | 必做 |
| L1 技术验证 | redefine 后自动执行 `jad`，确认运行时代码已变化；记录 class SHA256 和 redefine 输出 | 必做 |
| L2 诊断验证 | 用户选择一条 trace/watch/thread 模板，自动执行一次短验证 | 建议做 |
| L3 业务验证 | 调用业务接口、比对业务结果、自动回滚 | P2，不纳入当前闭环 |

成功页建议固定展示：技术验证结果、可选诊断验证入口、手动上传旧 class 回滚指引、产物目录和审计记录。失败页展示失败阶段：`jad`、上传、`mc`、`redefine`、验证，并给出可重试入口。

---

## 5. 中优先级问题

### 5.1 P1：能力模型字段需要补齐生命周期

建议 `diagnosis_capabilities` 增加或规划：`status`、`visibility`、`version`、`is_builtin`、`sort_order`、`updated_by`。其中 P0 至少需要 `status/is_builtin/sort_order`，否则管理员后台无法安全禁用、排序和区分内置能力。

### 5.2 P1：handler 字段不建议直接存可导入路径

文档中 `handler` 使用模块路径加载，即使有白名单，长期也容易被配置污染。建议改成注册表 ID：

```text
handler_key = "slow_request_analysis"
registry[handler_key] = api.performance_diagnose.slow_request_analysis
```

数据库只保存 `handler_key`，代码中维护白名单映射，降低任意 import 风险。

### 5.3 P1：场景方案需要定义失败策略

场景方案由多步骤组成，必须明确：某一步失败后是停止、跳过、继续还是转人工。建议步骤表增加 `on_failure='stop|continue|skip_remaining'`、`timeout_seconds`、`required`、`output_mapping_json`。

### 5.4 P1：权限模型不宜一次引入用户组

当前系统已有 `admin/user`、`user_clusters`、`user_namespaces` 等基础授权。文档把用户组和能力可见性列为 P0 会扩大改造面。建议 P0 先做：内置能力全员可见、自定义能力仅创建人和 admin 可见；P1 再做 group 可见性。

---

## 6. 架构决策建议

### ADR-001：任务中心不直接拥有连接执行能力

- **决策**：任务中心负责 run 生命周期、日志、调度和产物；具体 Pod/Arthas 操作委托现有执行器。
- **原因**：避免重复实现 kubectl、port-forward 和 Arthas HTTP 调用，减少竞态。
- **代价**：需要定义清晰的执行器接口和连接快照结构。

### ADR-002：即时诊断复用运行记录，不创建任务定义

- **决策**：即时诊断创建 `task_runs`，定时任务创建 `task_definitions + task_runs`。
- **原因**：符合线上排障即时性，同时保留定时任务可复用配置。
- **代价**：历史查询需要同时支持“有 task_definition”和“无 task_definition”的 run。

### ADR-003：前端当前连接与运行中任务解耦

- **决策**：连接切换只影响后续新建诊断，不自动取消已运行诊断。
- **原因**：多连接排障是高频场景，运行任务应该以服务端 `run_id` 为准。
- **代价**：前端需要运行中任务列表和连接快照展示。

---

## 7. 推荐调整优先级

| 优先级 | 调整项 | 说明 |
|---|---|---|
| P0 | 统一 `task_runs/task_logs` 口径 | 先决定复用还是迁移，避免实现分裂 |
| P0 | 明确即时诊断 API | 增加 execute API，不再伪装为创建任务定义 |
| P0 | 补状态管理器职责边界 | 避免与现有执行器重复和竞态 |
| P0 | 多连接选择器最小闭环 | 执行前明确目标连接，run 绑定连接快照 |
| P1 | 热更新 L1/L2 验证 | 自动技术验证 + 可选诊断验证 |
| P1 | 能力生命周期字段 | `status/is_builtin/sort_order/version` |
| P1 | 场景方案失败策略 | 多步骤编排可控可审计 |
| P2 | 用户组可见性和能力市场 | 放到基础闭环稳定后再做 |

---

## 8. 评审结论

设计可以继续推进，但建议先按 P0 四件事收敛：统一运行日志模型、明确即时执行 API、定义状态管理器边界、多连接选择器与连接快照。只有这四点稳定后，诊断能力目录、场景方案和在线修复才能避免在实现阶段变成多套状态、多套日志和多套执行入口。

