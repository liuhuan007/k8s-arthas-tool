# K8s Arthas 智能诊断平台 — 安全与审计


**文档版本**: v1.0
**创建日期**: 2026-05-23
**状态**: 设计完成

---

## 目录

1. [权限模型](#1-权限模型)
2. [危险命令分级](#2-危险命令分级)
3. [二次确认交互](#3-二次确认交互)
4. [敏感信息脱敏](#4-敏感信息脱敏)
5. [审计事件](#5-审计事件)
6. [外部链接安全](#6-外部链接安全)
7. [并发控制与生命周期管理](#7-并发控制与生命周期管理)

---

## 1. 权限模型

| 角色 | 权限范围 |
|------|---------|
| `admin` | 用户管理、集群管理、全部数据、审计查看、能力管理 |
| `user` | 仅访问授权集群和自身操作记录 |

---

## 2. 危险命令分级

| 风险等级 | 命令示例 | P0/P1 策略 |
|---------|---------|-----------|
| 高危 | redefine, heapdump, vmtool, 无限制 watch | 二次确认、影响面提示、超时、审计 |
| 中危 | 无条件 trace、展开深度 > 3 的 watch | 次数/时长限制、参数校验、审计 |
| 低危 | thread, dashboard, jad, 只读文件查看 | 基础审计、授权校验 |

---

## 3. 二次确认交互

| 风险等级 | 确认方式 | 有效期 |
|---------|---------|--------|
| 高危 | 弹窗 + 输入 CONFIRM | 2 分钟 |
| 中危 | 弹窗 + 勾选"我了解影响范围" | 5 分钟 |
| 低危 | 无需确认 | - |

---

## 4. 敏感信息脱敏

- 后端通过 `SensitiveDataMasker` 统一处理命令输出
- 默认脱敏规则：Bearer Token、password、token、secret、authorization
- 结构化输出优先做结构化脱敏，无法解析时退回正则脱敏
- 脱敏失败不阻断诊断，但前端显示警告

---

## 5. 审计事件

### 5.1 基础审计事件

- 登录、登出、创建/禁用用户、分配集群
- Arthas connect/disconnect/exec 操作
- profiler start/stop/cancel/download
- Pod exec、文件读取/下载
- redefine 执行（含 class SHA256、执行人、审计信息）

### 5.2 Agent + 自定义Skill安全审计规则

#### 5.2.1 Agent工具调用审计

| 事件 | 审计内容 | 风险等级 |
|------|---------|---------|
| `agent.tool.call` | 工具名、参数、结果、用户ID | 中 |
| `agent.tool.denied` | 工具名、拒绝原因、用户ID | 高 |
| `agent.tool.error` | 工具名、错误信息、用户ID | 中 |

#### 5.2.2 Skill管理审计

| 事件 | 审计内容 | 风险等级 |
|------|---------|---------|
| `skill.create` | Skill名称、版本、创建人 | 低 |
| `skill.update` | Skill名称、版本、变更内容 | 中 |
| `skill.publish` | Skill名称、版本、发布人 | 高 |
| `skill.delete` | Skill名称、版本、删除人 | 高 |
| `skill.import` | 导入来源、Skill数量、导入人 | 中 |

#### 5.2.3 Skill执行审计

| 事件 | 审计内容 | 风险等级 |
|------|---------|---------|
| `skill.execute.start` | Skill ID、连接ID、参数、用户ID | 中 |
| `skill.execute.step` | 步骤号、命令、输出、状态 | 中 |
| `skill.execute.complete` | 执行结果、耗时、成功/失败 | 低 |
| `skill.execute.error` | 错误信息、步骤号、用户ID | 高 |

#### 5.2.4 审计日志格式

```json
{
  "event": "agent.tool.call",
  "timestamp": "2026-05-24T13:00:00Z",
  "user_id": 123,
  "user_name": "admin",
  "tool_name": "execute_capability",
  "params": {
    "capability_id": 456,
    "connection_id": "conn-xxx"
  },
  "result": {
    "status": "success",
    "run_id": "run-xxx"
  },
  "risk_level": "medium",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0..."
}
```

#### 5.2.5 安全约束

| 约束 | 说明 |
|------|------|
| **Agent禁止任意命令** | Agent不能调用execute_kubectl、execute_arthas_command等 |
| **DSL禁止任意命令** | Skill DSL中的step_type只允许白名单类型 |
| **权限校验** | 所有Agent工具调用必须经过权限校验 |
| **审计完整** | 所有Agent工具调用必须写入audit_logs |
| **风险评估** | 高风险操作必须有二次确认 |

### 5.3 Agent + 自定义Skill安全边界

#### 5.3.1 自定义Skill安全规则

| 规则 | 说明 |
|------|------|
| **DSL不可信输入** | Skill DSL是用户输入，必须校验 |
| **发布前校验** | 校验step_type、命令白名单、参数schema、风险等级 |
| **权限控制** | draft/testing只能owner/admin dry-run，published才能同步到diagnosis_capabilities |
| **版本管理** | 发布后生成新版本，旧版本保留 |

```python
class SkillSecurityValidator:
    """Skill安全校验器"""
    
    def validate_before_publish(self, skill: Skill) -> tuple[bool, List[str]]:
        """发布前校验"""
        errors = []
        
        # 1. 校验DSL中的step_type
        for step in skill.dsl_steps:
            if step.type not in ALLOWED_STEP_TYPES:
                errors.append(f"禁止的step_type: {step.type}")
        
        # 2. 校验命令白名单
        for step in skill.dsl_steps:
            if step.type == 'arthas_command':
                if not self.whitelist.is_command_allowed(step.command):
                    errors.append(f"命令不在白名单: {step.command}")
        
        # 3. 校验参数schema
        if skill.parameters_schema:
            if not self._validate_json_schema(skill.parameters_schema):
                errors.append("参数schema格式错误")
        
        # 4. 校验风险等级
        if skill.risk_level == 'high':
            if not skill.requires_confirmation:
                errors.append("高风险Skill必须要求二次确认")
        
        return len(errors) == 0, errors
```

#### 5.3.2 Agent安全规则

| 规则 | 说明 |
|------|------|
| **Agent只能调用Gateway受控工具** | Agent不能直接调用kubectl/Arthas/shell |
| **每次tool call重新鉴权** | Agent不能持有持久权限 |
| **不能直接持有高危工具** | Agent不能持有kubectl/Arthas/shell工具 |
| **高危能力绑定确认** | 必须绑定user + connection + capability_version + params_hash |
| **LLM输出默认脱敏** | 发送给LLM的输出先脱敏 |

```python
class AgentSecurityPolicy:
    """Agent安全策略"""
    
    def __init__(self):
        self.allowed_tools = [
            'execute_capability',
            'get_pod_status',
            'get_pod_metrics',
            'list_capabilities',
            'analyze_output'
        ]
        self.forbidden_tools = [
            'execute_kubectl',
            'execute_arthas_command',
            'execute_shell',
            'modify_connection',
            'delete_pod'
        ]
    
    def validate_tool_call(self, tool_name: str, user_id: int, 
                          connection_id: str, params: dict) -> tuple[bool, str]:
        """校验工具调用"""
        
        # 1. 检查工具是否在白名单
        if tool_name not in self.allowed_tools:
            return False, f"工具 {tool_name} 不在白名单"
        
        # 2. 检查工具是否被禁止
        if tool_name in self.forbidden_tools:
            return False, f"工具 {tool_name} 被禁止"
        
        # 3. 检查用户权限
        if not self._check_user_permission(user_id, tool_name):
            return False, "用户无权限"
        
        # 4. 检查连接权限
        if not self._check_connection_permission(user_id, connection_id):
            return False, "无权访问此连接"
        
        # 5. 高危能力需要二次确认
        if tool_name == 'execute_capability':
            capability_id = params.get('capability_id')
            if self._is_high_risk(capability_id):
                confirmation_hash = self._generate_confirmation_hash(
                    user_id, connection_id, capability_id, params
                )
                if not self._check_confirmation(confirmation_hash):
                    return False, "高危能力需要二次确认"
        
        return True, ""
    
    def _is_high_risk(self, capability_id: int) -> bool:
        """检查是否高危能力"""
        capability = db.fetch_one(
            "SELECT risk_level FROM diagnosis_capabilities WHERE id = ?",
            (capability_id,)
        )
        return capability and capability['risk_level'] == 'high'
```

#### 5.3.3 审计关联

每个run和step需要可关联到：
- **user**：执行用户
- **connection_snapshot**：执行时的连接快照
- **capability_snapshot**：执行时的能力快照
- **params_hash**：参数哈希（用于高危能力确认）

```sql
-- task_logs表必须包含的审计字段
ALTER TABLE task_logs ADD COLUMN user_id INTEGER;
ALTER TABLE task_logs ADD COLUMN connection_snapshot_json TEXT;
ALTER TABLE task_logs ADD COLUMN capability_snapshot_json TEXT;
ALTER TABLE task_logs ADD COLUMN params_hash TEXT;

-- step_logs表必须包含的审计字段
ALTER TABLE step_logs ADD COLUMN user_id INTEGER;
ALTER TABLE step_logs ADD COLUMN connection_id TEXT;
```

---

## 6. 外部链接安全

- URL 仅允许 http/https 协议
- 打开新窗口使用 `noopener,noreferrer`
- iframe 内嵌默认关闭
- 管理员可配置上下文参数注入（`{cluster}`、`{namespace}`、`{pod}`）

---

## 7. 并发控制与生命周期管理

### 7.1 并发控制模型（P0）

多用户同时执行诊断能力时，需防止系统过载和 Pod 命令冲突：

```python
class DiagnosisExecutorPool:
    """诊断执行器线程池（并发控制）"""

    def __init__(self):
        self.global_pool = ThreadPoolExecutor(max_workers=10)  # 最多 10 个并发诊断
        self.pod_locks = defaultdict(threading.Lock)  # Pod 级别锁

    def execute(self, connection, capability, params, user_id):
        # 1. 检查全局并发数
        if self.global_pool._work_queue.qsize() >= 10:
            raise ConcurrencyError('系统繁忙，请稍后重试')
        # 2. 获取 Pod 级别锁
        pod_key = f"{connection.cluster_name}/{connection.namespace}/{connection.pod_name}"
        pod_lock = self.pod_locks[pod_key]
        if not pod_lock.acquire(blocking=False):
            raise ConcurrencyError(f'Pod {pod_key} 正在被诊断，请稍后')
        # 3. 提交到线程池
        ...
```

| 决策点 | 方案 | 理由 |
|--------|------|------|
| 全局并发数 | 10 | Arthas HTTP API 单 Pod 并发能力有限 |
| Pod 级别锁 | 互斥锁 | 防止多用户同时操作同一 Pod 导致命令冲突 |
| 超时控制 | 单步骤 60s | 防止慢命令阻塞线程池 |

### 7.2 连接生命周期管理（P0）

诊断执行过程中连接断开的处理：

```python
class ConnectionAwareExecutor:
    def execute_with_connection_guard(self, connection, capability, params):
        execution_id = str(uuid4())

        def on_connection_lost():
            db.update('task_logs', {
                'status': 'failed',
                'error_message': 'Arthas 连接已断开',
                'finished_at': datetime.now(),
            }, {'id': execution_id})
            if capability['category'] == 'scenario':
                self._rollback_scenario_steps(execution_id)

        ConnectionManager.register_listener(connection.id, on_connection_lost)
        try:
            return self._execute(connection, capability, params)
        finally:
            ConnectionManager.unregister_listener(connection.id, on_connection_lost)
```

前端连接断开时弹出对话框，引导用户重新建立连接。

### 7.3 能力版本管理（P1）

管理员修改诊断能力后，历史执行记录可追溯：

```sql
ALTER TABLE diagnosis_capabilities ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE task_logs ADD COLUMN capability_version INTEGER;
```

### 7.4 权限模型与数据隔离（P0）

```sql
-- 能力可见性控制
ALTER TABLE diagnosis_capabilities ADD COLUMN visibility TEXT DEFAULT 'public';
-- public: 所有用户可见 | private: 仅创建者可见 | group: 特定用户组可见
```

权限隔离规则：

| 维度 | admin | user |
|------|-------|------|
| 诊断能力 | 全部可见 + 可管理 | 按 visibility 和集群授权过滤 |
| 执行记录 | 全部可查 | 仅自身记录 |
| 异常事件 | 全部可查 | 仅自身集群 |
| 案例库 | 全部可管理 | 仅 verified 案例 |