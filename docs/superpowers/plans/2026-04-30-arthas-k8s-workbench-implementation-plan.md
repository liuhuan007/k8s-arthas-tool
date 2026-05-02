# Arthas on Kubernetes 智能运维调试平台任务拆分实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 PRD v4.1 拆解为可迭代、可测试、可交付的工程任务，按 P0/P1/P2 分阶段推进当前 Flask + SQLite + kubectl + 原生前端项目。

**Architecture:** 当前阶段保持轻量单体架构：Flask REST API + SQLite + kubectl executor + 原生 JS SPA。优先稳定连接上下文、诊断闭环、工具链和任务中心；Tunnel、审批流、批量诊断、AI 报告作为后续演进。

**Tech Stack:** Python 3.10+、Flask、SQLite、flask-login、kubectl、Arthas HTTP API、原生 JavaScript/CSS、pytest。

---

## 0. 拆分原则

1. **先 P0 后 P1/P2**：先完成当前 MVP 可用闭环，再做增强和生态扩展。
2. **先测试再实现**：每个任务先补失败测试，再写最小实现。
3. **不大重写前端**：保留原生 JS，不引入 React/Ant Design。
4. **不引入重中间件**：保留 SQLite，不强推 PostgreSQL、Redis、MQ。
5. **连接上下文优先**：所有诊断能力必须挂在明确 connection_id 下。
6. **安全能力渐进式落地**：先审计和确认，再脱敏、审批、互斥。

---

# Phase P0：MVP 稳定化与诊断闭环

## Epic P0-1：连接管理独立模块

**目标：** 把连接从侧栏/按钮/状态条的分散状态收敛为“连接列表 + 连接详情 + 当前连接上下文条”。

### Task P0-1.1：补齐连接列表数据契约测试

**Files:**
- Test: `tests/test_connection_management_contract.py`
- Reference: `api/pod_apis.py`
- Reference: `static/js/components/connections.js`

**Step 1: Write failing tests**

测试 `/api/pod/connections` 返回结构必须包含：

```python
def test_pod_connections_response_contract_contains_level_runtime_and_mcp():
    source = Path('api/pod_apis.py').read_text(encoding='utf-8')
    for field in [
        'connection_id', 'cluster_name', 'namespace', 'pod_name',
        'container', 'level', 'runtime', 'runtime_version',
        'alive', 'local_port', 'java_pid', 'arthas_version',
        'arthas_address', 'mcp_available'
    ]:
        assert field in source
```

**Step 2: Run test to verify it fails/passes**

Run:

```bash
python -m pytest tests/test_connection_management_contract.py -q
```

**Expected:** 当前若字段缺失则失败。

**Step 3: Minimal implementation**

在 `api/pod_apis.py:list_pod_connections()` 中补齐缺失字段，确保字段名与前端一致。

**Step 4: Verify**

```bash
python -m pytest tests/test_connection_management_contract.py -q
python -m pytest tests -q
```

---

### Task P0-1.2：连接详情页 UI 骨架

**Files:**
- Modify: `static/index.html`
- Modify: `static/js/app-ui.js`
- Modify: `static/css/app.css`
- Test: `tests/test_connection_detail_frontend.py`

**Step 1: Write failing tests**

断言页面存在连接详情容器和能力入口：

```python
def test_connection_detail_panel_exists():
    index = Path('static/index.html').read_text(encoding='utf-8')
    assert 'panel-connection-detail' in index
    assert 'connectionDetailBasic' in index
    assert 'connectionDetailCapabilities' in index
```

**Step 2: Implement UI skeleton**

在 `index.html` 新增 panel：

- 基本信息区：cluster / namespace / pod / container。
- 状态区：level / alive / runtime / java_pid。
- 操作区：Pod 连接、升级 Arthas、健康检查、断开。
- 能力入口区：Pod 监控、终端、文件、性能诊断、Arthas 命令、采样工具。

**Step 3: JS render function**

在 `app-ui.js` 新增：

```js
function renderConnectionDetail(conn) { ... }
function openConnectionDetail(connectionId) { ... }
```

**Step 4: Verify**

```bash
python -m pytest tests/test_connection_detail_frontend.py -q
```

---

### Task P0-1.3：当前连接上下文条轻量化

**Files:**
- Modify: `static/js/components/conn-status-bar.js`
- Modify: `static/js/components/connection-guard.js`
- Test: `tests/test_connection_status_bar.py`

**Requirements:**

- 只展示当前连接、层级、runtime 摘要、查看详情按钮。
- 不承担删除、升级、批量操作。

**Acceptance:**

- [ ] 无连接显示“未选择连接”。
- [ ] Pod 连接显示 `Pod` 层级和基础能力。
- [ ] Arthas 连接显示 `Arthas` 层级和版本。
- [ ] 点击“查看详情”进入连接详情页。

---

## Epic P0-2：Arthas Agent 生命周期稳定化

### Task P0-2.1：启动/复用/失败原因标准化

**Files:**
- Modify: `backend/core/arthas_agent.py`
- Modify: `backend/core/connection.py`
- Modify: `api/pod_apis.py`
- Test: `tests/test_arthas_lifecycle_contract.py`

**Requirements:**

- 已有 HTTP 响应时复用。
- HTTP 不通但残留进程存在时清理残留。
- 未找到 Java PID 时明确提示。
- 未找到 JAR 时提示工具链分发入口。
- 启动超时时返回 `/tmp/arthas_start.log` 尾部。

**Test cases:**

```python
def test_arthas_agent_reuse_message_exists():
    source = Path('backend/core/arthas_agent.py').read_text(encoding='utf-8')
    assert 'Arthas 已在运行，直接复用' in source
    assert 'tail -25 /tmp/arthas_start.log' in source
```

---

### Task P0-2.2：Agent 自动卸载策略（保守版）

**Files:**
- Modify: `api/pod_apis.py`
- Modify: `backend/core/connection.py`
- Test: `tests/test_arthas_detach_policy.py`

**Scope:**

P0 不做强制自动 shutdown，先做可配置策略：

- 默认只断开 port-forward，不 kill Pod 内 Arthas。
- 提供“断开并卸载 Arthas”显式按钮。
- 操作必须审计。

**Acceptance:**

- [ ] 普通断开不会杀 Arthas。
- [ ] 显式卸载会执行 shutdown/kill。
- [ ] 卸载前提示可能影响其他用户。

---

## Epic P0-3：Pod 监控与控制面板

### Task P0-3.1：Pod 监控真实环境验收补强

**Files:**
- Modify: `backend/pod_monitor.py`
- Modify: `static/js/app-ui.js`
- Test: `tests/test_pod_monitor_and_arthas.py`

**Requirements:**

- 兼容 `ps aux`、`ps -ef`、BusyBox ps。
- 空数据展示可操作原因。
- API 返回结构保持 `container_metrics.processes`。

**Acceptance:**

- [ ] Running Pod 有进程数据。
- [ ] 非 Running Pod 显示状态原因。
- [ ] 容器内无 ps 时显示命令不可用。

---

### Task P0-3.2：Arthas dashboard 控制面板结构化

**Files:**
- Modify: `api/performance_diagnose.py` or create `api/arthas_dashboard.py`
- Modify: `static/js/app-ui.js`
- Test: `tests/test_dashboard_panel.py`

**Requirements:**

- 执行 `dashboard -n 1`。
- 解析 threads、memoryInfo、gcInfos、runtimeInfo。
- UI 展示 JVM、线程、内存、GC 摘要。

**Acceptance:**

- [ ] Arthas 连接后可刷新 dashboard。
- [ ] dashboard 超时不阻塞页面。
- [ ] 高 CPU/高 Old 区/Full GC 有颜色提示。

---

## Epic P0-4：线程诊断和方法诊断场景化

### Task P0-4.1：线程诊断页结构化

**Files:**
- Modify: `api/performance_diagnose.py`
- Modify: `static/js/components/diagnose.js`
- Test: `tests/test_thread_diagnosis.py`

**Requirements:**

- 支持 `thread -n <N>`。
- 支持 `thread -b` 死锁检测。
- 展示线程名、ID、状态、CPU、堆栈摘要。

**Acceptance:**

- [ ] 支持热点线程列表。
- [ ] 支持死锁提示。
- [ ] 点击线程显示完整堆栈。

---

### Task P0-4.2：watch / trace 场景化入口

**Files:**
- Modify: `static/js/components/diagnose.js`
- Modify: `api/performance_diagnose.py`
- Test: `tests/test_method_diagnosis_templates.py`

**Requirements:**

- UI 表单：class_pattern、method_pattern、sample_count、cost_threshold。
- 生成安全命令，限制次数。
- 结果写入历史记录。

**Acceptance:**

- [ ] trace 命令自动带 `-n` 和 cost 条件。
- [ ] watch 命令默认限制观测次数。
- [ ] 参数为空时提示用户。

---

### Task P0-4.3：在线反编译 jad 工作台

**Files:**
- Modify: `api/performance_diagnose.py`
- Modify: `static/js/components/diagnose.js`
- Test: `tests/test_jad_workbench.py`

**Requirements:**

- 输入 class name 执行 `jad --source-only`。
- 展示源码、classloader、location。
- 支持复制源码或保存为任务附件。

---

## Epic P0-5：工具链中心与任务中心收敛（不包含升级能力）

> 本 Epic 只做工具链、任务、审计和权限收敛；不加入“工具自动升级/Arthas 版本升级/Tunnel 升级”等升级能力。Arthas JAR 分发只作为“安装/补齐工具”能力，不做版本升级闭环。

### Task P0-5.1：工具包分发结果标准化

**Files:**
- Modify: `api/task_center.py`
- Modify: `static/js/app-ui.js`
- Test: `tests/test_task_center_toolchain.py`

**Requirements:**

- 分发返回 install_path、sha256、pod 校验结果。
- UI 展示最近分发状态。
- 失败时展示 kubectl stderr。
- 不实现工具升级流程，只记录当前分发文件和校验结果。

---

### Task P0-5.2：内置诊断模板补齐 P0 清单

**Files:**
- Modify: `api/task_center.py`
- Test: `tests/test_task_center_toolchain.py`

**Templates:**

- CPU 高负载一键诊断。
- Trace 调用链耗时分析。
- Watch 方法现场观测。
- 在线反编译 jad。
- CPU 火焰图。
- Arthas jad/retransform 热更新工作流。
- Pod Python 文件下载服务。

---

### Task P0-5.3：任务执行与审计打通

**Files:**
- Modify: `api/task_center.py`
- Modify: `services/audit_service.py`
- Test: `tests/test_task_audit.py`

**Requirements:**

- 每次任务执行写 audit_logs。
- 记录 user_id、目标 Pod、任务名、执行模式、状态。

---

## Epic P0-6：安全与审计基线

### Task P0-6.1：敏感命令确认机制

**Files:**
- Modify: `static/js/app-ui.js`
- Modify: `api/performance_diagnose.py`
- Modify: `server.py`
- Test: `tests/test_sensitive_command_confirm.py`

**Sensitive commands:**

- retransform
- redefine
- reset
- shutdown
- heapdump
- logger 修改级别
- vmoption 修改参数

**Acceptance:**

- [ ] 前端弹确认。
- [ ] 后端要求 confirm=true。
- [ ] 未确认返回 400。

---

### Task P0-6.2：审计字段补强

**Files:**
- Modify: `services/audit_service.py`
- Modify: `models/db.py` or schema init location
- Test: `tests/test_audit_contract.py`

**Fields:**

- action
- resource_type
- target_pod
- command
- result_summary
- source_ip
- created_at

---

## Epic P0-7：Namespace 级账号授权

**目标：** 在现有 user_clusters 集群授权基础上，新增 namespace 级授权，明确“哪个账号可以操作哪个集群下的哪些 namespace”。所有 Pod 列表、Pod 连接、工具分发、任务执行、Pod 诊断、日志/文件/终端操作都必须校验 namespace 权限。

### Task P0-7.1：设计并迁移用户 Namespace 授权表

**Files:**
- Modify: `models/db.py:110-120`
- Test: `tests/test_namespace_authorization.py`

**Step 1: Write the failing test**

```python
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = (ROOT / 'models' / 'db.py').read_text(encoding='utf-8')


def test_user_namespace_permissions_table_exists():
    assert 'user_namespaces' in DB
    assert 'user_id INTEGER NOT NULL' in DB
    assert 'cluster_id TEXT NOT NULL' in DB
    assert 'namespace TEXT NOT NULL' in DB
    assert 'UNIQUE(user_id, cluster_id, namespace)' in DB
```

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest tests/test_namespace_authorization.py::test_user_namespace_permissions_table_exists -q
```

Expected: FAIL because `user_namespaces` table does not exist.

**Step 3: Minimal implementation**

在 `models/db.py` 初始化中新增：

```sql
CREATE TABLE IF NOT EXISTS user_namespaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    cluster_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, cluster_id, namespace)
)
```

约定：
- admin 默认拥有所有 namespace。
- 普通用户必须有 `user_namespaces` 授权才可操作 namespace。
- 可保留 `user_clusters` 作为集群可见性粗粒度授权，但实际 Pod 操作以 namespace 授权为准。

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_namespace_authorization.py -q
```

---

### Task P0-7.2：新增 Namespace 授权 API

**Files:**
- Modify: `api/users.py:112-175`
- Test: `tests/test_namespace_authorization.py`

**Step 1: Write failing tests**

```python
def test_user_namespace_api_routes_exist():
    users = Path('api/users.py').read_text(encoding='utf-8')
    assert "/user-namespaces/<int:user_id>" in users
    assert "/user-namespaces" in users
    assert "assign_namespace" in users
    assert "remove_namespace" in users
```

**Step 2: Minimal API design**

新增接口：

| API | 方法 | 权限 | 说明 |
|---|---|---|---|
| `/api/user-namespaces/<user_id>` | GET | admin 或本人 | 查看用户 namespace 授权 |
| `/api/user-namespaces` | POST | admin | 给账号授权 namespace |
| `/api/user-namespaces/<assignment_id>` | DELETE | admin | 删除授权 |
| `/api/user-namespaces/by-user-cluster-namespace` | DELETE | admin | 按 user_id + cluster_id + namespace 删除 |

POST body:

```json
{
  "user_id": 2,
  "cluster_id": "prod-cluster",
  "namespace": "order-prod"
}
```

**Step 3: Implementation notes**

- 校验 `user_id`、`cluster_id`、`namespace` 必填。
- `namespace` 允许 `*` 作为当前 cluster 下全部 namespace 授权（可选，但建议支持）。
- 重复授权返回 400：`该 namespace 授权已存在`。

---

### Task P0-7.3：统一 Namespace 权限校验函数

**Files:**
- Create or Modify: `services/authorization_service.py`
- Modify: `api/clusters.py`
- Modify: `api/pod_apis.py`
- Modify: `api/task_center.py`
- Modify: `server.py`
- Test: `tests/test_namespace_authorization.py`

**Step 1: Write failing tests**

```python
def test_authorization_service_contract_exists():
    source = Path('services/authorization_service.py').read_text(encoding='utf-8')
    assert 'class AuthorizationService' in source
    assert 'can_access_cluster' in source
    assert 'can_access_namespace' in source
    assert 'filter_namespaces' in source
```

**Step 2: Minimal implementation**

新增服务：

```python
class AuthorizationService:
    @staticmethod
    def can_access_cluster(user, cluster_id: str) -> bool:
        if user.is_admin:
            return True
        # 兼容旧 user_clusters
        ...

    @staticmethod
    def can_access_namespace(user, cluster_id: str, namespace: str) -> bool:
        if user.is_admin:
            return True
        # user_namespaces 中 cluster_id + namespace 或 namespace='*'
        ...

    @staticmethod
    def filter_namespaces(user, cluster_id: str, namespaces: list[str]) -> list[str]:
        if user.is_admin:
            return namespaces
        ...
```

**Step 3: Integration rules**

必须接入以下入口：

- `api/clusters.py:list_namespaces()`：普通用户只返回已授权 namespace。
- `api/clusters.py:list_pods()`：请求 namespace 前校验权限。
- `api/pod_apis.py:pod_connect()`：建立 Pod 连接前校验 namespace。
- `api/pod_apis.py:pod_diagnose()`：诊断前校验连接所属 namespace。
- `api/task_center.py` Pod 目标执行/分发：执行前校验 namespace。
- `server.py` 旧 `/api/arthas/connect`、monitor、logs、terminal/file 入口：逐步接入校验。

**Step 4: Error message**

无权限统一返回：

```json
{"error": "无权访问该 namespace"}
```

HTTP status: `403`。

---

### Task P0-7.4：用户管理页面支持 Namespace 授权配置

**Files:**
- Modify: `static/user-management.html`
- Modify: `static/js/user-management.js`
- Modify: `static/css/app.css`
- Test: `tests/test_namespace_authorization_frontend.py`

**Requirements:**

- 管理员在用户管理页选择用户。
- 展示该用户已有 cluster 和 namespace 授权。
- 支持新增授权：cluster + namespace。
- 支持删除授权。
- 可选支持 namespace=`*` 表示该集群所有 namespace。

**Acceptance:**

- [ ] UI 有 `userNamespaceList`。
- [ ] JS 有 `loadUserNamespaces(userId)`。
- [ ] JS 有 `assignUserNamespace()`。
- [ ] JS 有 `removeUserNamespace(...)`。

---

### Task P0-7.5：Namespace 授权审计

**Files:**
- Modify: `api/users.py`
- Modify: `services/audit_service.py`
- Test: `tests/test_namespace_authorization.py`

**Requirements:**

- 授权 namespace 记录审计：`namespace_permission_granted`。
- 删除授权记录审计：`namespace_permission_revoked`。
- 审计内容包含 operator、target_user、cluster_id、namespace。

---


# Phase P1：增强体验与金融级安全能力

## Epic P1-1：方法 monitor / stack 支持

### Task P1-1.1：stack 方法追溯

**Files:**
- Modify: `api/performance_diagnose.py`
- Modify: `static/js/components/diagnose.js`
- Test: `tests/test_stack_diagnosis.py`

**Command:**

```text
stack <class_pattern> <method_pattern> -n <count>
```

---

### Task P1-1.2：monitor 方法统计

**Files:**
- Modify: `api/performance_diagnose.py`
- Modify: `static/js/components/diagnose.js`
- Test: `tests/test_monitor_diagnosis.py`

**Command:**

```text
monitor <class_pattern> <method_pattern> -c <cycle>
```

**Safety:** 必须限制周期和总时长。

---

## Epic P1-2：诊断模板保存与复用

### Task P1-2.1：用户自定义诊断模板

**Files:**
- Modify: `api/task_center.py`
- Modify: `static/js/app-ui.js`
- Test: `tests/test_diagnosis_template_crud.py`

**Requirements:**

- 用户可保存 trace/watch/stack/monitor 配置。
- 模板可一键填充表单。
- 模板按 user_id 隔离。

---

## Epic P1-3：热修复审批和回滚

### Task P1-3.1：class 快照表和 API

**Files:**
- Modify: `models/db.py` or database init
- Create: `api/hotfix.py`
- Test: `tests/test_hotfix_snapshots.py`

**Requirements:**

- dump class 保存到 `profiler_output` 或 dedicated snapshots 目录。
- 保存 class_name、connection_id、file_path、method_signatures。

---

### Task P1-3.2：审批流 MVP

**Files:**
- Create/Modify: `api/hotfix.py`
- Modify: `static/js/app-ui.js`
- Test: `tests/test_hotfix_approval.py`

**States:**

- pending_approval
- approved
- rejected
- applied
- rolled_back

---

### Task P1-3.3：redefine/retransform 回滚

**Files:**
- Modify: `api/hotfix.py`
- Modify: `backend/core/arthas_client.py`
- Test: `tests/test_hotfix_rollback.py`

**Acceptance:**

- [ ] 执行前必须有快照。
- [ ] 失败时保留日志。
- [ ] 可一键回滚。

---

## Epic P1-4：历史趋势和诊断报告

### Task P1-4.1：JVM metrics 时序表

**Files:**
- Modify: DB init
- Create/Modify: `api/metrics.py`
- Test: `tests/test_jvm_metrics.py`

**Metrics:**

- cpu_percent
- heap_used_mb
- heap_max_mb
- gc_count
- thread_count

---

### Task P1-4.2：诊断结果导出

**Files:**
- Modify: `api/performance_diagnose.py`
- Modify: `static/js/components/diagnose.js`
- Test: `tests/test_diagnosis_export.py`

**Formats:**

- JSON
- Markdown
- HTML snippet

---

### Task P1-4.3：AI 诊断报告生成

**Files:**
- Modify: `api/ai_chat.py`
- Modify: `api/performance_diagnose.py`
- Test: `tests/test_ai_diagnosis_report.py`

**Requirements:**

- 输入 dashboard/thread/trace/watch 摘要。
- 输出结论、根因、建议、风险。
- 不能自动执行危险操作。

---

# Phase P2：生态扩展

## Epic P2-1：Arthas Tunnel Server 模式

### Task P2-1.1：Tunnel 配置模型

**Files:**
- Modify: cluster config storage
- Modify: `api/clusters.py`
- Test: `tests/test_tunnel_config.py`

**Requirements:**

- cluster 支持 tunnel_url。
- 可选择 port-forward 或 tunnel 模式。

---

### Task P2-1.2：Tunnel Agent 注册和通信

**Files:**
- Modify: `backend/core/arthas_agent.py`
- Modify: `backend/core/arthas_client.py`
- Test: `tests/test_tunnel_mode.py`

**Scope:** 先做接口抽象，不强制完整实现。

---

## Epic P2-2：批量诊断

### Task P2-2.1：Deployment Pod 批量选择

**Files:**
- Modify: `api/clusters.py`
- Modify: `static/js/app-ui.js`
- Test: `tests/test_batch_pod_selection.py`

---

### Task P2-2.2：批量 trace/watch 聚合结果

**Files:**
- Create/Modify: `api/batch_diagnose.py`
- Modify: frontend diagnose UI
- Test: `tests/test_batch_diagnose.py`

**Acceptance:**

- [ ] 同一命令发到多个 Pod。
- [ ] 结果按 Pod 聚合。
- [ ] 异常耗时实例高亮。

---

## Epic P2-3：外部系统集成

### Task P2-3.1：TAPD/工单集成设计

**Files:**
- Create: `docs/integrations/tapd-hotfix-approval.md`

**Scope:** 先做设计文档，不实现。

---

### Task P2-3.2：IDE 插件协议设计

**Files:**
- Create: `docs/integrations/ide-plugin-protocol.md`

**Scope:** 定义连接、诊断模板、结果跳转协议。

---

# 推荐执行顺序

## Sprint 1：连接上下文稳定化

1. P0-1.1 连接列表数据契约测试
2. P0-1.2 连接详情页 UI 骨架
3. P0-1.3 当前连接上下文条轻量化
4. P0-2.1 启动/复用/失败原因标准化

## Sprint 2：核心诊断闭环

1. P0-3.2 dashboard 控制面板结构化
2. P0-4.1 线程诊断页结构化
3. P0-4.2 watch / trace 场景化入口
4. P0-4.3 jad 工作台

## Sprint 3：工具链 + 任务 + 审计 + Namespace 授权

> 本 Sprint 不加入升级能力；重点是工具链/任务稳定性、审计闭环，以及账号到 namespace 的精细授权。

1. P0-7.1 设计并迁移用户 Namespace 授权表
2. P0-7.2 新增 Namespace 授权 API
3. P0-7.3 统一 Namespace 权限校验函数
4. P0-7.4 用户管理页面支持 Namespace 授权配置
5. P0-7.5 Namespace 授权审计
6. P0-5.1 工具包分发结果标准化（不做升级能力）
7. P0-5.2 内置诊断模板补齐
8. P0-5.3 任务执行与审计打通
9. P0-6.1 敏感命令确认机制
10. P0-6.2 审计字段补强

## Sprint 4：P1 安全和报告能力

1. P1-1.1 stack
2. P1-1.2 monitor
3. P1-2.1 用户自定义诊断模板
4. P1-4.2 诊断结果导出
5. P1-4.3 AI 诊断报告

---

# Definition of Done

每个任务完成必须满足：

- [ ] 有对应测试，且先失败后通过。
- [ ] `python -m pytest tests -q` 通过。
- [ ] 关键 Python 文件 `py_compile` 通过。
- [ ] 前端 inline handler 已挂到 `window`（如需 onclick）。
- [ ] 所有 API 错误返回可读中文提示。
- [ ] 涉及诊断命令的操作写审计日志。
- [ ] 涉及危险命令有确认或审批设计。
- [ ] 更新 `docs/superpowers/specs/2026-05-02-arthas-k8s-platform-system-design.md` 或相关文档（如行为变化）。

---

# 执行选项

**1. Subagent-Driven（当前会话）**  
按 Sprint 拆小任务执行，每个任务完成后审查和跑测试。

**2. Parallel Session（单独会话）**  
新会话使用 `executing-plans` 技能，按本文档逐项实施。

建议从 **Sprint 1 / P0-1.1** 开始。
