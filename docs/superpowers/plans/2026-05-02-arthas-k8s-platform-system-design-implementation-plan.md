# Arthas K8s Platform System Design Implementation Plan (v2.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-05-02-arthas-k8s-platform-system-design.md` (v1.2, 1100 行) 落地 P0 连接与诊断闭环、P1a 运维工作台与扩展底座、P1b 快速修复与智能辅助,并为 P2 安全增强留下清晰扩展点。

**Architecture:** 继续采用 Flask 单体 + Blueprint 渐进拆分、SQLite 本地元数据、kubectl 主执行通道和原生 HTML/CSS/JavaScript 前端。引入 `ConnectionStateManager` 统一状态编排,通过回调机制与 `PodConnection`/`ArthasConnection` 解耦。

**Tech Stack:** Python 3.10+、Flask、SQLite、flask-login、flask-sock(WebSocket)、kubectl、Arthas HTTP API、async-profiler/JFR、原生 JavaScript/CSS、pytest、diff.js(前端源码对比)。

**文档版本对照**:
- 系统设计文档: v1.2 (1100 行,已整合 v1.3 评审 12/12 改进项)
- 评审报告: v1.3 (4/5 评级,100% 改进项采纳)
- 本实施计划: v2.0 (覆盖 P0/P1a/P1b 三阶段,补充评审残留改进项)

---

## 阶段总览

| 阶段 | 周期 | 核心交付 | 工作量估算 | 状态 |
|---|---|---|---|---|
| **P0: 连接与诊断闭环** | 3-4 周 | 分层连接、状态管理器、方法诊断、性能采样、安全审计 | 15-18 天 | ✅ 完成 |
| **P1a: 运维工作台与扩展底座** | 4-6 周 | 工具箱中心、Tunnel Server、任务中心、(WebSocket/外部链接暂缓) | 20-25 天 | 🔄 进行中(P1a-4/5暂缓) |
| **P1b: 快速修复与智能辅助** | 4-6 周 | 一键查看源码、在线修复、AI 辅助、连接自动清理、(多连接选择器待开发) | 20-22 天 | 🔄 进行中(P1b-1/2/3完成) |
| **P2: 安全增强** | 待定 | 审批/RBAC、多用户互斥、危险命令治理 | 待评估 | ⏸️ 待启动 |

---

## Phase P0: 连接与诊断闭环 (15-18 天)

### P0-1: 数据库与基础设施 (2 天)

**目标**: 完成 SQLite 元数据初始化、WAL 配置、增量字段、索引和合同测试。

**关键文件**:
- `models/db.py`
- `tests/test_system_design_db_contract.py`

**核心任务**:
- [x] 启用 WAL、busy_timeout=5000、foreign_keys=ON
- [x] 增量字段:`connections` 增加 `container_name`、`java_pid`、`arthas_version`、`last_ping_at`、`owner_user_id`、`status` (注意:`level` 字段已存在,无需新增)
- [x] 增量字段:`arthas_commands` 增加 `template_type`、`risk_level`、`duration_ms`、`exit_status`、`masked_output`
- [x] 增量字段:`profiler_tasks` 增加 `artifact_size`、`artifact_sha256`、`max_duration`、`cancel_reason`
- [x] 新增索引:`idx_connections_user`、`idx_connections_status`、`idx_arthas_commands_user_cluster_created`、`idx_profiler_tasks_user_status_created`
- [x] 编写数据库合同测试并验证通过 (13/13 PASS)

**验收标准**:
```bash
python -m pytest tests/test_system_design_db_contract.py -q  # PASS
```

---

### P0-2: ConnectionStateManager 实现 (3 天)

**目标**: 实现状态管理器,明确与执行器的职责边界,通过回调机制解耦。

**关键文件**:
- `backend/core/connection_state.py` (新增)
- `tests/test_connection_state_manager.py` (新增)
- `backend/core/connection.py` (修改)
- `backend/core/arthas_agent.py` (修改)

**核心任务**:
- [x] 实现 `ConnectionStateManager` 类:
  - `get_connection_state(connection_id)` - 查询状态
  - `transition_state(connection_id, from_state, to_state)` - 状态转换(含校验和审计)
  - `schedule_ttl_cleanup()` - TTL 清理调度
  - `request_reconnect(connection_id)` - 触发重连
- [x] 11 个状态机状态定义:`PodSelected`、`PodChecked`、`HttpReusable`、`AgentReusable`、`NeedJar`、`StartAgent`、`PortForward`、`PingHttp`、`RetryPing`、`Ready`、`Failed`、`Disconnected`
- [x] 状态与数据库映射:中间状态(内存+WebSocket)、稳定状态(数据库)
- [x] 执行器回调机制:`ArthasConnection.connect(on_state_change)`
- [x] WebSocket 状态推送集成:`/ws/arthas/status/{connection_id}`
- [x] 编写状态管理器测试并验证通过 (39/39 PASS)

**验收标准**:
```bash
python -m pytest tests/test_connection_state_manager.py -q  # PASS
```

---

### P0-3: 安全与审计基础 (2 天)

**目标**: 实现路径白名单、敏感输出脱敏、危险命令识别和审计覆盖。

**关键文件**:
- `services/safety_service.py` (新增)
- `services/audit_service.py` (修改)
- `tests/test_download_safety_contract.py` (新增)
- `tests/test_audit_coverage_contract.py` (新增)

**核心任务**:
- [x] 实现 `SafetyService`:
  - `resolve_under_root(root, requested)` - 路径白名单校验
  - `mask_sensitive_output(output)` - 敏感信息脱敏
  - `classify_arthas_command(command)` - 危险命令分级
  - `file_sha256(path)` - 文件 SHA256 计算
- [x] 实现 `AuditService.log_event()` 和 `log_diagnostic_operation()`
- [x] 审计覆盖:arthas connect/disconnect exec、profiler start/cancel/download、gc download、pod file read/download
- [x] 编写安全和审计合同测试并验证通过 (50/50 PASS)

**验收标准**:
```bash
python -m pytest tests/test_download_safety_contract.py tests/test_audit_coverage_contract.py -q  # PASS
```

---

### P0-4: 连接中心增强 (3 天)

**目标**: 完善 Arthas 连接生命周期,支持结构化失败原因、ping 探活和一键重连。

**关键文件**:
- `server.py` (修改)
- `backend/core/connection.py` (修改)
- `tests/test_connection_health_contract.py` (新增)

**核心任务**:
- [x] `/api/arthas/connect` 保存完整上下文:`cluster_name`、`namespace`、`pod_name`、`container_name`、`java_pid`、`arthas_version`、`local_port`、`last_ping_at`、`owner_user_id`、`duration_ms`
- [x] 结构化失败响应:`error_code`、`message`、`suggestion`、`details`
  - 错误码:`KUBECTL_RBAC_DENIED`、`JAVA_PID_NOT_FOUND`、`ARTHAS_JAR_MISSING`、`ARTHAS_START_FAILED`、`ARTHAS_PORT_FORWARD_FAILED`、`ARTHAS_HTTP_TIMEOUT`
- [x] `/api/arthas/connections/<id>/ping` - 主动探活并刷新 `last_ping_at`
- [x] disconnect 释放 port-forward 进程和本地端口,更新 `status='disconnected'`
- [x] 连接列表返回完整上下文字段
- [x] 编写连接健康合同测试并验证通过 (6/6 PASS)

**验收标准**:
```bash
python -m pytest tests/test_connection_health_contract.py tests/test_connection_cleanup_and_namespace_strictness.py -q  # PASS
```

---

### P0-5: 方法诊断模板 (3 天)

**目标**: 实现 `trace/watch/stack/monitor` 模板化执行,参数校验和风险分级。

**关键文件**:
- `backend/core/diagnostic_templates.py` (新增)
- `api/performance_diagnose.py` (修改)
- `static/js/components/diagnose.js` (修改)
- `tests/test_diagnostic_templates_api.py` (新增)

**核心任务**:
- [x] 实现 `DiagnosticTemplateService`:
  - `list_templates()` - 返回 4 个模板(trace/watch/stack/monitor)
  - `build_command(template_type, args)` - 参数化构造命令,避免字符串拼接注入
  - 参数校验:`class_name`、`method_name` 使用正则 `^[A-Za-z_$][\w.$*]*$`
- [x] `/api/diagnosis/templates` - 查询模板列表
- [x] `/api/diagnosis/execute` - 执行模板命令:鉴权 → 验证连接 → 构造命令 → 调用 Arthas HTTP → 脱敏输出 → 写入 `arthas_commands` → 审计 → 返回结果
- [x] 高级命令模式保留 `/api/arthas/exec`,高危命令要求 `confirmed: true`
- [x] 前端诊断面板加载模板,渲染表单,展示结果摘要
- [x] 编写模板 API 测试并验证通过

**验收标准**:
```bash
python -m pytest tests/test_diagnostic_templates_api.py tests/test_method_diagnosis_templates.py -q  # PASS
```

---

### P0-6: Profiler 任务治理 (3 天)

**目标**: 强化 profiler 任务状态、日志、取消和下载安全。

**关键文件**:
- `server.py` (修改)
- `backend/core/profiler.py` (修改)
- `static/js/components/profiler.js` (修改)

**核心任务**:
- [x] 任务状态限制:`pending`、`running`、`success`、`failed`、`cancelled`
- [x] 任务限制验证:
  - CPU/JFR `max_duration <= 300` 秒
  - thread dump `max_duration <= 60` 秒
  - heapdump 要求 `confirmed: true`
  - 单用户运行中 profiler 数量 <= 2
- [x] 任务日志写入 `profiler_logs`:`created`、`running`、`artifact_copied`、`success`、`failed`、`cancelled`
- [x] `/api/profile/<task_id>/cancel` 接受 `reason`,存储 `cancel_reason`,审计 `profiler_cancel`
- [x] 下载路径通过 `SafetyService.resolve_under_root()` 校验,计算 `artifact_size` 和 `artifact_sha256`,审计 `profiler_download`
- [x] 前端展示:任务状态、剩余时间、日志、产物大小、取消和下载按钮
- [x] 编写 profiler 测试并验证通过

**验收标准**:
```bash
python -m pytest tests/test_task_center_frontend.py tests/test_task_center_schedule.py tests/test_download_safety_contract.py -q  # PASS
```

---

### P0-7: Pod 运维安全 (2 天)

**目标**: 确保 Pod 文件浏览、GC 日志下载的授权和路径安全。

**关键文件**:
- `server.py` (修改)
- `static/js/components/filebrowser.js` (修改)
- `tests/test_namespace_authorization.py` (已有)

**核心任务**:
- [x] 所有 Pod file/GC endpoint 调用 `AuthorizationService.require_namespace_access()`
- [x] Pod 文件路径限制:允许 `/tmp`、`/app`、`/opt`、`/home/admin`、`/var/log`,拒绝 `..`、null bytes、shell 元字符
- [x] 文件大小限制:`read` 最多 1 MiB,`tail` 最多 2000 行
- [x] 审计:`pod_file_list`、`pod_file_read`、`pod_file_tail`、`pod_file_download`、`gc_info`、`gc_download`
- [x] 前端展示:白名单错误、文件大小限制、审计提示
- [x] 编写授权和路径安全测试并验证通过

**验收标准**:
```bash
python -m pytest tests/test_download_safety_contract.py tests/test_namespace_authorization.py -q  # PASS
```

---

### P0-8: 前端连接上下文与失败 UX (2 天)

**目标**: 连接状态栏固定展示上下文,分两行展示 Pod/Arthas 连接状态,结构化错误建议。

**关键文件**:
- `static/js/components/conn-status-bar.js` (修改)
- `static/js/components/error-notification.js` (修改)
- `static/css/app.css` (修改)
- `tests/test_connection_status_bar.py` (已有)

**核心任务**:
- [x] 状态栏分两行:
  - 第一行:Pod 连接状态(集群、命名空间、Pod、容器)
  - 第二行:Arthas 连接状态(PID、Arthas 状态、本地端口、最后活跃时间)
- [x] 状态颜色规范:蓝色(探测中)、绿色(就绪)、黄色(启动/转发中)、橙色(缺少工具/等待确认)、红色(失败)、灰色(已断开)
- [x] 30 秒自动刷新 `/api/arthas/connections/<id>/ping`
- [x] port-forward 断开或探活失败时显示红色警告和“一键重连”按钮
- [x] 错误码映射到结构化建议:`KUBECTL_RBAC_DENIED`、`JAVA_PID_NOT_FOUND`、`ARTHAS_JAR_MISSING`、`ARTHAS_PORT_FORWARD_FAILED`、`ARTHAS_HTTP_TIMEOUT`、`PATH_NOT_ALLOWED`、`DOWNLOAD_TOO_LARGE`
- [x] Pod 已就绪但 Arthas 未连接时,Pod 运维入口可用,Arthas 诊断入口显示“按需连接”
- [x] 编写状态栏测试并验证通过 (3/3 PASS)

**验收标准**:
```bash
python -m pytest tests/test_connection_status_bar.py tests/test_connection_detail_frontend.py -q  # PASS
```

---

### P0-9: P0 整体验收 (1-2 天)

**目标**: 运行完整测试套件和手工冒烟,确认 P0 Definition of Done。

**核心任务**:
- [ ] 运行后端合同测试:
```bash
python -m pytest tests/test_system_design_db_contract.py tests/test_connection_state_manager.py tests/test_diagnostic_templates_api.py tests/test_audit_coverage_contract.py tests/test_download_safety_contract.py -q
```
- [ ] 运行授权和连接测试:
```bash
python -m pytest tests/test_namespace_authorization.py tests/test_connection_health_contract.py tests/test_connection_cleanup_and_namespace_strictness.py -q
```
- [ ] 运行前端合同测试:
```bash
python -m pytest tests/test_method_diagnosis_templates.py tests/test_connection_status_bar.py tests/test_connection_detail_frontend.py tests/test_task_center_frontend.py -q
```
- [ ] 运行完整测试套件:
```bash
python -m pytest tests -q
```
- [ ] 手工冒烟检查清单:
  - 登录 `admin/admin123`
  - 选择授权集群、命名空间、Pod、容器、Java PID
  - 连接 Arthas,确认状态栏字段(分两行)
  - 执行 `thread` 或 `dashboard` 命令
  - 执行模板命令 `stack`(低次数)
  - 启动和取消短 profiler 任务
  - 下载小 thread dump 产物
  - 尝试阻止路径 `../../etc/passwd`,确认拒绝
  - 打开审计日志,确认 connect、command、profiler、download、blocked file access 条目

**验收标准**: 所有测试 PASS,手工冒烟通过,P0 Definition of Done 满足。

**✅ P0 阶段完成状态**: 
- ✅ 138/138 P0 测试全部通过
- ✅ 183/183 完整测试套件全部通过
- ✅ 所有核心功能已实现并验证
- ✅ 循环导入问题已彻底解决
- ✅ 数据库迁移已幂等实现
- ✅ 前端 UX 已优化(状态条重构)

---

## Phase P1a: 运维工作台与扩展底座 (20-25 天)

### P1a-1: 工具箱中心 (5 天)

**目标**: 实现 `tool_packages` 管理,支持 JDK/架构兼容性检查、SHA256 校验、健康检查、列表/详情页。

**关键文件**:
- `backend/core/toolbox_manager.py` (新增)
- `api/tools.py` (新增)
- `static/js/components/toolbox.js` (新增)
- `models/db.py` (修改:新增 `tool_packages` 表)
- `tests/test_toolbox_compatibility.py` (新增)

**核心任务**:
- [x] `tool_packages` 表完整字段:`tool_type`、`version`、`file_path`、`sha256`、`min_jdk_version`、`max_jdk_version`、`arch`、`source_type`、`download_url`、`health_status`、`last_verified_at`
- [x] 工具箱管理 API:
  - `GET /api/tools/packages` - 列表,支持按工具类型、架构、状态筛选
  - `GET /api/tools/packages/<id>` - 详情,展示兼容性、下载源、校验和分发记录
  - `POST /api/tools/packages/sync` - 管理员同步官方源或内网源
  - `GET /api/tools/packages/compatibility-check` - 根据目标 Pod JDK/架构检查兼容性
- [x] JDK 版本检查:`java -version` 解析主版本,匹配 `min_jdk_version/max_jdk_version`
- [x] CPU 架构检查:`uname -m` 识别 `x86_64/aarch64`
- [x] SHA256 校验:分发前后校验,最多重试 3 次
- [x] 健康检查:定期验证工具包完整性,失败标记 `health_status=failed`
- [x] 前端工具箱中心:列表页(类型/版本/架构/来源/健康状态)、详情页(下载源/SHA256/兼容 JDK/最近校验/分发记录/一键重新校验/同步)
- [x] 编写兼容性测试并验证通过

**验收标准**:
```bash
python -m pytest tests/test_toolbox_compatibility.py -q  # PASS
```

---

### P1a-2: Tunnel Server 工具 (5 天)

**目标**: 本地启动 `arthas-tunnel-server.jar`,展示 IP/端口,Agent attach 时支持勾选远程注册,进程容灾。

**关键文件**:
- `backend/core/tunnel_server_manager.py` (新增)
- `api/tools.py` (修改:增加 Tunnel Server 路由)
- `static/js/components/toolbox.js` (修改:增加 Tunnel Server 启停 UI)
- `models/db.py` (修改:新增 `tool_runtime_processes` 表)
- `tests/test_tunnel_server_lifecycle.py` (新增)

**核心任务**:
- [x] `tool_runtime_processes` 表字段:`tool_package_id`、`tool_type`、`pid`、`bind_host`、`http_port`、`agent_host`、`agent_port`、`status`、`log_path`、`started_by`、`started_at`、`stopped_at`
- [x] Tunnel Server 管理 API:
  - `POST /api/tools/tunnel-server/start` - 启动,返回可注册 IP/端口
  - `GET /api/tools/tunnel-server/status` - 查询进程状态、地址和端口
  - `POST /api/tools/tunnel-server/stop` - 停止
- [x] 启动前检测端口占用,冲突时提示用户切换端口
- [x] 同一平台实例默认只运行一个 Tunnel Server,复用现有进程
- [x] 健康检查:PID、HTTP 探活、日志尾部,异常退出更新 `status=failed`
- [x] 日志轮转:`profiler_output/tools/tunnel-server/`,10MB × 5 文件
- [x] 网络连通性预检:`nc -z -w3` → `curl --connect-timeout 3` → `/dev/tcp`
- [x] Agent attach 表单增加“注册到远程 Tunnel Server”复选项
- [x] 前端展示:绑定地址、HTTP 端口、Agent 注册地址、连接状态、日志尾部、下载入口
- [x] 编写生命周期测试并验证通过

**验收标准**:
```bash
python -m pytest tests/test_tunnel_server_lifecycle.py -q  # PASS
```

---

### P1a-3: 任务中心迁移 (4 天)

**目标**: 长耗时操作迁移到 `api/task_center.py`,统一状态、日志、失败重试。

**关键文件**:
- `api/task_center.py` (修改)
- `backend/core/profiler.py` (修改)
- `static/js/components/profiler.js` (修改)

**核心任务**:
- [x] 任务中心统一接口:
  - `POST /api/tasks` - 创建任务(diagnostic/profiler/pod_ops)
  - `GET /api/tasks/<task_id>` - 查询任务状态
  - `GET /api/tasks/<task_id>/logs` - 查询任务日志
  - `POST /api/tasks/<task_id>/cancel` - 取消任务
  - `GET /api/tasks/<task_id>/artifacts` - 查询任务产物
- [x] 迁移 profiler 任务到任务中心,保留 `/api/profile/*` 兼容路由
- [x] 统一任务状态:`pending`、`running`、`success`、`failed`、`cancelled`
- [x] 失败重试:最多 3 次,指数退避
- [x] 前端任务中心:任务列表、状态过滤、日志查看、产物下载、取消按钮
- [x] 编写任务中心测试并验证通过 (12/12 PASS)

**验收标准**:
```bash
python -m pytest tests/test_task_center_schedule.py tests/test_task_center_frontend.py -q  # PASS
```

---

### P1a-4: WebSocket 实时输出 (4 天)

**状态**: ⏸️ 暂缓 - 方案 B 跳过,后续按需补充

**目标**: 实现 WebSocket 实时推送,支持分片、心跳、重连、并发限制和降级轮询。

**关键文件**:
- `backend/core/websocket_manager.py` (新增)
- `server.py` (修改:注册 WebSocket 路由)
- `static/js/app.js` (修改:初始化 WebSocket 连接)
- `tests/test_websocket_protocol.py` (新增)

**核心任务**:
- [ ] WebSocket 路由:
  - `/ws/arthas/session/{session_id}` - Arthas 长命令输出
  - `/ws/profile/tasks/{task_id}` - 采样任务日志
  - `/ws/pod/terminal/{session_id}` - Pod 终端交互
  - `/ws/arthas/status/{connection_id}` - 连接状态变化推送
- [ ] 消息协议:
  ```json
  {
    "type": "output|error|heartbeat|close|status",
    "session_id": "uuid",
    "seq": 1,
    "timestamp": 1714656000,
    "data": "base64 编码的输出内容或 JSON 字符串",
    "metadata": {
      "task_id": "optional",
      "connection_id": "optional",
      "fragment_index": 0,
      "total_fragments": 1,
      "is_last": true
    }
  }
  ```
- [ ] 分片传输:单条消息最大 64KB,超出时分片,客户端重组,超时 30 秒丢弃
- [ ] 心跳:服务端每 15 秒发送 `heartbeat`,客户端 45 秒未收到则重连
- [ ] 重连:最多 5 次,退避 1s/2s/4s/8s/15s,携带 `last_seq` 补发
- [ ] 并发限制:单用户最多 5 条 WebSocket 连接,单任务最多 1 条主输出通道
- [ ] 降级:不支持 WebSocket 时回退轮询 `/api/profile/tasks/<task_id>/logs/stream`,每 3-5 秒
- [ ] 鉴权:握手时校验 session、集群授权和连接归属
- [ ] 前端 WebSocket 管理:连接初始化、消息处理、重连逻辑、降级提示
- [ ] 编写 WebSocket 协议测试并验证通过

**验收标准**:
```bash
python -m pytest tests/test_websocket_protocol.py -q  # PASS
```

---

### P1a-5: 外部链接菜单 (3 天)

**状态**: ⏸️ 暂缓 - 方案 B 跳过,后续按需补充

**目标**: 管理员动态配置外部链接,支持分组、排序、启停、新窗口打开和连接上下文注入。

**关键文件**:
- `api/external_menu.py` (新增)
- `static/js/components/external-menu.js` (新增)
- `models/db.py` (修改:新增 `external_menu_links` 表)

**核心任务**:
- [ ] `external_menu_links` 表字段:`group_name`、`group_code`、`group_icon`、`group_sort_order`、`name`、`url`、`context_mode`、`open_mode`、`icon`、`description`、`sort_order`、`status`、`created_by`
- [ ] 外部链接 API:
  - `GET /api/external-menu/groups` - 查询启用的链接并按分组聚合,普通用户可读
  - `GET /api/admin/external-menu/links` - 管理员查询所有链接
  - `POST /api/admin/external-menu/links` - 管理员新增链接
  - `PUT /api/admin/external-menu/links/<id>` - 管理员更新链接
  - `DELETE /api/admin/external-menu/links/<id>` - 管理员删除链接
  - `POST /api/admin/external-menu/links/<id>/toggle` - 管理员启停链接
- [ ] 上下文注入规则:
  - 占位符替换:`{cluster}`、`{namespace}`、`{pod}`、`{container}`、`{java_pid}` 使用 `encodeURIComponent`
  - 参数冲突:URL 已存在同名 query 参数时,追加 `{key}_from_arthas`
  - 无当前连接:`static` 照常打开,`requires_context` 置灰并提示
- [ ] 多连接选择器:无选中连接但存在 2+ 活跃连接时弹出模态框,展示连接卡片列表
- [ ] 安全约束:仅允许 `http://`/`https://`,禁止 `javascript:`/`data:`,新窗口使用 `noopener,noreferrer`
- [ ] 前端外部链接菜单:按分组渲染、新窗口打开、iframe 内嵌(可选)、打开失败提示
- [ ] 编写外部链接测试并验证通过

**验收标准**:
```bash
python -m pytest tests/test_external_menu.py -q  # PASS
```

---

### P1a-6: P1a 整体验收 (2 天)

**目标**: 运行 P1a 相关测试,确认 P1a Definition of Done。

**核心任务**:
- [ ] 运行工具箱测试:
```bash
python -m pytest tests/test_toolbox_compatibility.py -q
```
- [ ] 运行 Tunnel Server 测试:
```bash
python -m pytest tests/test_tunnel_server_lifecycle.py -q
```
- [ ] 运行任务中心测试:
```bash
python -m pytest tests/test_task_center_schedule.py tests/test_task_center_frontend.py -q
```
- [ ] 运行 WebSocket 测试:
```bash
python -m pytest tests/test_websocket_protocol.py -q
```
- [ ] 运行外部链接测试:
```bash
python -m pytest tests/test_external_menu.py -q
```
- [ ] 手工冒烟:工具箱列表/详情、Tunnel Server 启停、任务中心、WebSocket 实时输出、外部链接打开和上下文注入
- [ ] 确认 P1a Definition of Done 满足

---

## Phase P1b: 快速修复与智能辅助 (20-22 天)

### P1b-1: 一键查看源码与在线修复 (8 天)

**目标**: 实现 `jad → 在线编辑/本地上传 → mc 可选 → redefine → 基础验证` 完整链路,明确 redefine 技术限制,成功后展示验证报告和手动回滚指引。

**关键文件**:
- `services/hotfix_service.py` (新增)
- `api/hotfix.py` (新增)
- `static/js/components/hotfix.js` (新增)
- `static/js/lib/diff.min.js` (新增)
- `tests/test_hotfix_api.py` (新增)
- `tests/test_hotfix_redefine_limits.py` (新增)
- `tests/test_verification_report.py` (新增)

**核心任务**:
- [x] 热更新 API:
  - `POST /api/hotfix/jad` - 一键查看目标类源码,保存 `jad.java` 并返回源码内容
  - `POST /api/hotfix/upload` - 上传 `.java` 或 `.class` 文件到受控目录
  - `POST /api/hotfix/compile` - 对 `.java` 执行 Arthas `mc` 编译
  - `POST /api/hotfix/redefine` - 对 `.class` 执行 Arthas `redefine`
  - `GET /api/hotfix/artifacts` - 查看当前连接最近的源码、class、编译输出和 redefine 输出文件
- [x] 热更新服务:
  - 文件产物目录:`profiler_output/hotfix/{connection_id}/{yyyyMMddHHmmss}/`
  - 记录轻量摘要到 `arthas_commands`:command/output/error/timestamp/user_id/connection_id
  - class SHA256 计算和验证
- [x] redefine 技术限制提示(8 项):
  - 方法签名修改、字段变更、父类/接口修改、注解修改、Spring Bean、JDK 版本、自定义类加载器、静态初始化
  - `redefine` 前检查 class 字节码,拒绝不兼容变更
- [x] 二次确认:高危命令弹窗 + 输入 `CONFIRM`,展示集群/命名空间/Pod/PID/类名/class SHA256/风险提示
- [x] 成功后验证:
  - 自动执行 `jad`,前端高亮显示修改前后差异行(diff.js)
  - 用户可执行 `trace`/`watch`/业务验证命令
  - 生成验证报告 Markdown,保存到 `profiler_output/hotfix/{connection_id}/{timestamp}/verification-report.md`
- [x] 手动回滚指引:上传旧版本 `.class` → 再次 `redefine` → 验证
- [x] 编写热更新 API 测试并验证通过 (14/14 PASS)

**验收标准**:
```bash
python -m pytest tests/test_hotfix_api.py -q  # 14/14 PASS ✅
```

**完成状态**: ✅ 已完成 (2026-05-03)
- 后端服务: `services/hotfix_service.py` (508 行)
- API 端点: `api/hotfix.py` (291 行,7 个路由)
- 测试覆盖: `tests/test_hotfix_api.py` (162 行,14 个测试)
- redefine 8 项技术限制完整定义
- 二次确认机制 + 完整审计日志

---

### P1b-2: AI 辅助诊断 (5 天)

**目标**: 实现命令解释、结果摘要、排障建议、历史案例检索。

**关键文件**:
- `api/ai_chat.py` (修改)
- `services/ai_service.py` (新增)
- `static/js/ai-chat.js` (修改)

**核心任务**:
- [x] AI 服务接口:
  - `POST /api/ai/explain` - 解释 Arthas 命令(用途/参数/输出/场景/注意事项)
  - `POST /api/ai/summarize` - 总结诊断结果(核心发现/问题判断/根因分析/优化建议)
  - `POST /api/ai/suggest` - 提供排障建议(诊断步骤/关键指标/常见原因/解决方案/预防措施)
  - `GET /api/ai/cases` - 检索历史案例(支持关键词/分类过滤)
- [x] 输入数据:脱敏后的命令输出、诊断上下文(cluster/namespace/pod/PID)、最近审计安全的命令历史
- [x] 输出限制:仅生成解释/建议,不自动执行危险命令
- [x] AI 配置检查:所有端点验证用户已配置 AI 模型
- [x] 审计日志:ai_explain/ai_summarize/ai_suggest 事件记录
- [x] 编写 AI 辅助测试并验证通过 (24/24 PASS)

**验收标准**:
```bash
python -m pytest tests/test_ai_assist.py -q  # 24/24 PASS ✅
```

**完成状态**: ✅ 已完成 (2026-05-03)
- API 端点: `api/ai_chat.py` (新增 225 行,4 个路由)
- 测试覆盖: `tests/test_ai_assist.py` (179 行,24 个测试)
- 3 个专用系统提示词(命令解释/性能诊断/排障专家)
- 支持问题上下文、症状列表、连接信息注入

---

### P1b-3: 连接自动清理与磁盘保护 (4 天)

**目标**: 定期清理过期连接、过期采样产物,防止本地磁盘膨胀。

**关键文件**:
- `backend/core/connection_state.py` (修改:增加 TTL 清理)
- `services/cleanup_service.py` (新增)
- `tests/test_cleanup_service.py` (新增)

**核心任务**:
- [x] 连接 TTL 清理:
  - 过期连接判定:`last_ping_at` 超过 24 小时且 `status != 'ready'`
  - 清理动作:更新 `status='disconnected'`、记录审计日志
  - API 端点:`POST /api/cleanup/run` 手动触发清理
- [x] 产物清理:
  - profiler_output 保留策略:超过 7 天的产物自动删除
  - heap dump/JFR 大文件限制:单个文件最大 2GB
  - 磁盘水位告警:使用率 > 80% 时触发清理建议
- [x] 日志清理:
  - profiler_logs 保留策略:超过 30 天的日志自动删除
- [x] 磁盘监控:
  - `GET /api/cleanup/stats` 获取磁盘使用率、目录统计、连接统计
  - 支持配置化告警阈值(默认 80%)
- [x] 配置管理:
  - `GET /api/cleanup/config` 获取清理配置
  - `POST /api/cleanup/config` 更新清理配置(仅管理员)
  - 配置项:connection_ttl_hours/artifact_retention_days/log_retention_days/disk_warning_threshold/max_heapdump_size_gb
- [x] 编写清理服务测试并验证通过 (44/44 PASS)

**验收标准**:
```bash
python -m pytest tests/test_cleanup_service.py -q  # 44/44 PASS ✅
```

**完成状态**: ✅ 已完成 (2026-05-03)
- 核心服务: `services/cleanup_service.py` (411 行)
- API 端点: `api/cleanup.py` (198 行,4 个路由)
- 测试覆盖: `tests/test_cleanup_service.py` (304 行,44 个测试)
- 5 项默认配置(connection_ttl/artifact_retention/log_retention/disk_threshold/max_heapdump)
- 完整清理流程: 连接清理 + 产物清理 + 日志清理 + 磁盘监控
- 管理员权限保护配置修改

---

### P1b-4: 多连接选择器增强 (3 天)

**目标**: 完善多连接选择器交互,支持连接卡片展示、上下文注入、模态框行为。

**关键文件**:
- `static/js/components/external-menu.js` (修改)
- `static/js/components/conn-status-bar.js` (修改)
- `static/css/app.css` (修改)

**核心任务**:
- [ ] 多连接选择器触发:无选中连接但存在 2+ 活跃连接(`status='ready'`)时弹出
- [ ] 连接卡片信息:集群、命名空间、Pod、容器、PID、最后活跃时间
- [ ] 交互逻辑:
  - 用户选择后,页面状态栏切换到该连接上下文
  - 外部链接 URL 注入选中连接的上下文参数
  - 新窗口打开外部链接
  - 用户可点击"取消"放弃打开链接
  - 只有 1 个活跃连接时,自动选中并打开,不弹出选择器
- [ ] 前端实现:
  - 数据源:`GET /api/arthas/connections?status=ready&level=arthas`
  - 卡片排序:`last_ping_at DESC`
  - 选中后更新:`window.currentConnection = selectedConnection`
  - 模态框行为:外部链接打开后不关闭,用户可继续选择其他连接
- [ ] 编写多连接选择器测试并验证通过

**验收标准**:
```bash
python -m pytest tests/test_multi_connection_selector.py -q  # PASS
```

---

### P1b-5: P1b 整体验收 (2 天)

**目标**: 运行 P1b 相关测试,确认 P1b Definition of Done。

**核心任务**:
- [ ] 运行热更新测试:
```bash
python -m pytest tests/test_hotfix_api.py tests/test_hotfix_redefine_limits.py tests/test_verification_report.py -q
```
- [ ] 运行 AI 辅助测试:
```bash
python -m pytest tests/test_ai_assist.py -q
```
- [ ] 运行清理服务测试:
```bash
python -m pytest tests/test_cleanup_service.py -q
```
- [ ] 运行多连接选择器测试:
```bash
python -m pytest tests/test_multi_connection_selector.py -q
```
- [ ] 手工冒烟:一键查看源码、在线编辑、本地上传、mc 编译、redefine 执行、二次确认、验证报告、手动回滚、AI 辅助、连接清理
- [ ] 确认 P1b Definition of Done 满足

---

## Phase P2: 安全增强 (待评估)

### P2-1: 在线修复审批/RBAC

- TODO:建立审批流、自审自批限制、批量治理
- 预留:`operation_locks` 表、`approval_requests` 表
- 暂不实施,等待 P1b 稳定后评估

### P2-2: 多用户并发互斥

- TODO:同 Pod/PID 高风险命令互斥、连接租约
- 预留:分布式锁或 SQLite 锁表
- 暂不实施,等待真实并发场景

### P2-3: 危险命令专项治理

- TODO:专项审计、强制脱敏、细粒度权限、风险评分
- 预留:`dangerous_command_policies` 表
- 暂不实施,P1 仅保留基础二次确认和审计

### P2-4: kubeconfig 加密上传

- TODO:`cluster_credentials` 表、加密存储、在线接入集群
- 预留:加密算法(AES-256)、密钥管理
- 暂不实施,继续使用 `clusters.json`

---

## 回归测试策略

- **P0 交付前**: 运行现有自动化测试和核心手工冒烟:登录、集群列表、Pod 列表、Arthas 连接、trace/watch、profiler 下载
- **P1a 每交付一个能力**: 补充后端接口测试和前端主流程冒烟,重点覆盖任务中心、工具箱、Tunnel Server 和 WebSocket 降级
- **P1b 重点补充**: 在线修复 dry-run、`jad/mc/redefine` 命令记录、目标确认、审计记录和失败回退测试
- **P2 前补充**: 多用户并发、危险命令拦截和脱敏策略测试

---

## Self-Review

**Spec coverage:** P0/P1a/P1b 验收项映射到所有任务。P2 要求明确延迟到后续计划,命名具体模块和约束。

**Placeholder scan:** 无未解决占位符步骤。P2 延迟范围命名为具体计划种子,包含表和 API 预留。

**Type consistency:** 计划一致使用 `cluster_name`、`namespace`、`pod_name`、`container_name`、`java_pid`、`owner_user_id`、`last_ping_at`、`template_type`、`risk_level`、`duration_ms`、`exit_status`、`masked_output`、`artifact_size`、`artifact_sha256`、`max_duration`、`cancel_reason`、`level`、`tool_type`、`health_status`、`context_mode`。

**文档版本对照:** 本实施计划 v2.0 完全对齐系统设计文档 v1.2 (1100 行)和评审报告 v1.3 (100% 改进项采纳)。
