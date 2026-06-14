# K8s Arthas Tool — kubectl CLI 适配 AI 优化设计

> 让 kubectl 成为 AI Agent 可靠的"眼睛和手"

**文档版本**: v1.0
**创建日期**: 2026-06-14
**状态**: 设计完成

---

## [S1] 问题背景

当前 kubectl 调用存在以下问题：

1. **输出非结构化**：`kubectl describe`、`kubectl top` 等命令输出人类可读但 AI 难以解析
2. **错误处理不统一**：超时、权限不足、资源不存在等错误混杂在 stderr 中
3. **健康状态未标准化**：Pod/Node/Service 的健康判断逻辑分散在各处
4. **危险操作无保护**：`kubectl delete`、`kubectl exec` 等操作无确认机制
5. **命令元数据缺失**：AI 不知道什么场景该用什么 kubectl 命令

## [S2] 设计目标

| 目标 | 度量标准 |
|------|---------|
| AI 可消费的输出 | 所有 kubectl 输出有 JSON 模式 |
| 错误可机读 | 100% 错误有结构化 error code |
| 健康状态标准化 | Pod/Node/Service 有统一健康模型 |
| 危险操作可控 | 删除/重启等操作有 dry-run + 确认机制 |
| 命令可发现 | AI 能通过元数据找到正确的 kubectl 命令 |

## [S3] 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    AI Agent 层                           │
│  "帮我查看 Pod 状态" → 意图识别 → 选择命令 → 执行       │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              KubectlAIWrapper（新增）                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ StructuredOutput│ │ HealthChecker │  │ SafetyGuard  │ │
│  │ 结构化输出     │  │ 健康检查     │  │ 安全守卫     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│  ┌──────────────┐  ┌──────────────┐                    │
│  │ CommandRegistry│ │ ErrorMapper  │                    │
│  │ 命令注册表     │  │ 错误映射     │                    │
│  └──────────────┘  └──────────────┘                    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              KubectlExecutor（现有）                      │
│  _run() → subprocess → kubectl CLI                      │
└─────────────────────────────────────────────────────────┘
```

### 3.2 核心组件

#### 组件 1：StructuredOutput — 结构化输出

将 kubectl 人类可读输出转换为 AI 可消费的 JSON：

```python
class StructuredOutput:
    """将 kubectl 输出转换为结构化 JSON"""

    @staticmethod
    def parse_pod_status(raw_output: str, fmt: str = "wide") -> dict:
        """解析 kubectl get pods -o wide 输出"""
        # 输入: "nginx-7c5ddbdf54-abc12   1/1     Running   0          2d   10.244.1.5   node1   <none>"
        # 输出: {
        #   "name": "nginx-7c5ddbdf54-abc12",
        #   "ready": "1/1",
        #   "status": "Running",
        #   "restarts": 0,
        #   "age": "2d",
        #   "ip": "10.244.1.5",
        #   "node": "node1",
        #   "health": "healthy"
        # }

    @staticmethod
    def parse_describe_pod(raw_output: str) -> dict:
        """解析 kubectl describe pod 输出"""
        # 提取: Events, Conditions, Containers, Restarts, 资源使用

    @staticmethod
    def parse_top_nodes(raw_output: str) -> list:
        """解析 kubectl top nodes 输出"""

    @staticmethod
    def parse_top_pods(raw_output: str) -> list:
        """解析 kubectl top pods 输出"""
```

#### 组件 2：HealthChecker — 健康状态标准化

统一 Pod/Node/Service 健康模型：

```python
class HealthStatus:
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

class HealthChecker:
    """统一健康状态判断"""

    @staticmethod
    def check_pod(pod_json: dict) -> dict:
        """
        Pod 健康判断规则：
        - Running + Ready=True + Restarts<3 → healthy
        - Running + Ready=False → degraded
        - CrashLoopBackOff / OOMKilled / Error → unhealthy
        - Pending / Unknown → unknown
        返回: {"status": "healthy", "reason": "", "conditions": [...]}
        """

    @staticmethod
    def check_node(node_json: dict) -> dict:
        """
        Node 健康判断规则：
        - Ready=True + NotScheduling → healthy
        - Ready=False → unhealthy
        - MemoryPressure=True / DiskPressure=True → degraded
        """

    @staticmethod
    def check_service(svc_json: dict, endpoints: list) -> dict:
        """
        Service 健康判断规则：
        - 有 endpoints 且至少一个 Ready → healthy
        - 无 endpoints → unhealthy
        - 部分 endpoints Ready → degraded
        """
```

#### 组件 3：SafetyGuard — 安全守卫

危险操作保护机制：

```python
class SafetyGuard:
    """危险操作保护"""

    # 危险操作分级
    RISK_LEVELS = {
        "read":    ["get", "describe", "logs", "exec", "top", "cluster-info"],
        "low":     ["port-forward", "cp"],
        "medium":  ["scale", "restart"],
        "high":    ["delete", "exec rm", "exec kill"],
    }

    @staticmethod
    def check_risk(command: str) -> dict:
        """
        检查命令风险等级
        返回: {"level": "high", "requires_confirm": True, "dry_run_supported": True}
        """

    @staticmethod
    def dry_run(base_cmd: list, args: list) -> dict:
        """
        Dry-run 模式：只打印将要执行的命令，不实际执行
        返回: {"command": "kubectl delete pod nginx", "dry_run": True}
        """

    @staticmethod
    def validate_before_execute(command: str, context: dict) -> dict:
        """
        执行前校验：
        - Pod 是否存在
        - Namespace 是否正确
        - 是否有权限
        返回: {"ok": True, "warnings": [...]}
        """
```

#### 组件 4：CommandRegistry — 命令注册表

AI 可查询的命令元数据：

```python
COMMAND_CATALOG = {
    "pod_status": {
        "command": "kubectl get pods -o wide",
        "description": "获取 Pod 列表和状态",
        "when_to_use": ["查看 Pod 运行状态", "检查 Pod 是否正常"],
        "risk_level": "read",
        "output_format": "table",
        "structured_parser": "parse_pod_status",
        "examples": [
            "查看所有 Pod: kubectl get pods -o wide",
            "查看指定 Pod: kubectl get pod <name> -o wide",
            "按标签过滤: kubectl get pods -l app=nginx"
        ]
    },
    "pod_describe": {
        "command": "kubectl describe pod <name>",
        "description": "获取 Pod 详细信息（Events、Conditions、资源）",
        "when_to_use": ["Pod 异常时查看详情", "排查 Pod 启动失败"],
        "risk_level": "read",
        "output_format": "text",
        "structured_parser": "parse_describe_pod",
        "examples": ["kubectl describe pod nginx-xxx"]
    },
    "pod_logs": {
        "command": "kubectl logs <name> [--previous]",
        "description": "获取 Pod 容器日志",
        "when_to_use": ["查看应用日志", "排查 CrashLoopBackOff"],
        "risk_level": "read",
        "output_format": "text",
        "examples": [
            "查看当前日志: kubectl logs <pod>",
            "查看上一次崩溃日志: kubectl logs <pod> --previous",
            "查看指定容器: kubectl logs <pod> -c <container>"
        ]
    },
    "pod_exec": {
        "command": "kubectl exec -it <pod> -- <command>",
        "description": "在 Pod 内执行命令",
        "when_to_use": ["检查文件", "执行诊断命令", "检查进程"],
        "risk_level": "low",
        "requires_confirmation": False,
        "examples": ["kubectl exec -it nginx-xxx -- sh"]
    },
    "pod_delete": {
        "command": "kubectl delete pod <name>",
        "description": "删除 Pod（会触发重建）",
        "when_to_use": ["Pod 卡死需要重启", "清理异常 Pod"],
        "risk_level": "high",
        "requires_confirmation": True,
        "dry_run_supported": True,
        "examples": ["kubectl delete pod nginx-xxx", "kubectl delete pod nginx-xxx --dry-run=client"]
    },
    "node_status": {
        "command": "kubectl get nodes -o wide",
        "description": "获取 Node 列表和状态",
        "when_to_use": ["查看节点状态", "检查节点资源"],
        "risk_level": "read",
    },
    "cluster_info": {
        "command": "kubectl cluster-info",
        "description": "获取集群基本信息",
        "when_to_use": ["检查集群连通性", "确认集群版本"],
        "risk_level": "read",
    },
    "events": {
        "command": "kubectl get events --sort-by='.lastTimestamp'",
        "description": "获取集群事件",
        "when_to_use": ["排查问题时间线", "查看告警事件"],
        "risk_level": "read",
    },
    "resource_usage": {
        "command": "kubectl top pods / kubectl top nodes",
        "description": "获取资源使用情况",
        "when_to_use": ["查看 CPU/内存使用", "检查资源是否超限"],
        "risk_level": "read",
    },
    "port_forward": {
        "command": "kubectl port-forward <pod> <local>:<remote>",
        "description": "端口转发",
        "when_to_use": ["访问 Pod 内服务", "调试网络问题"],
        "risk_level": "low",
    },
}
```

#### 组件 5：ErrorMapper — 错误映射

统一错误码和错误信息：

```python
class ErrorCode:
    # 连接类
    KUBECTL_NOT_FOUND = "E1001"
    CLUSTER_UNREACHABLE = "E1002"
    AUTH_FAILED = "E1003"
    CONTEXT_NOT_FOUND = "E1004"

    # 资源类
    POD_NOT_FOUND = "E2001"
    POD_NOT_RUNNING = "E2002"
    POD_CRASHLOOP = "E2003"
    POD_OOMKILLED = "E2004"
    NAMESPACE_NOT_FOUND = "E2005"
    NODE_NOT_READY = "E2006"

    # 执行类
    EXEC_FAILED = "E3001"
    EXEC_TIMEOUT = "E3002"
    PORT_FORWARD_FAILED = "E3003"
    CP_FAILED = "E3004"

    # 权限类
    PERMISSION_DENIED = "E4001"
    RBAC_INSUFFICIENT = "E4002"

class ErrorMapper:
    """将 kubectl stderr 映射为结构化错误"""

    @staticmethod
    def map_error(stderr: str, returncode: int) -> dict:
        """
        返回: {
            "code": "E2001",
            "message": "Pod not found",
            "detail": "pod 'nginx-xxx' not found in namespace 'default'",
            "suggestion": "请检查 Pod 名称是否正确，或确认 Pod 所在的 namespace",
            "retryable": False
        }
        """
```

## [S4] API 设计

### 4.1 新增 API 端点

```
GET  /api/kubectl/commands          # 命令注册表（AI 可查询）
POST /api/kubectl/execute           # 结构化执行 kubectl 命令
POST /api/kubectl/health-check      # 统一健康检查
POST /api/kubectl/dry-run           # Dry-run 预览
GET  /api/kubectl/errors            # 错误码参考
```

### 4.2 请求/响应格式

**POST /api/kubectl/execute**

```json
// Request
{
  "command": "get pods",
  "namespace": "default",
  "output": "structured",  // "raw" | "structured"
  "context": "my-cluster"
}

// Response (structured)
{
  "ok": true,
  "command": "kubectl get pods -n default -o wide",
  "data": [
    {
      "name": "nginx-7c5ddbdf54-abc12",
      "ready": "1/1",
      "status": "Running",
      "restarts": 0,
      "age": "2d",
      "ip": "10.244.1.5",
      "node": "node1",
      "health": "healthy"
    }
  ],
  "health_summary": {
    "total": 5,
    "healthy": 4,
    "unhealthy": 1
  }
}
```

**POST /api/kubectl/health-check**

```json
// Request
{
  "resource": "pod",           // "pod" | "node" | "service"
  "name": "nginx-xxx",         // 可选，不传则检查所有
  "namespace": "default"
}

// Response
{
  "ok": true,
  "resource": "pod",
  "namespace": "default",
  "items": [
    {
      "name": "nginx-xxx",
      "health": "healthy",
      "status": "Running",
      "conditions": ["Ready=True", "Initialized=True"],
      "issues": []
    },
    {
      "name": "redis-yyy",
      "health": "unhealthy",
      "status": "CrashLoopBackOff",
      "conditions": ["Ready=False"],
      "issues": ["CrashLoopBackOff: restart count 5", "Last exit code: 137 (OOMKilled)"]
    }
  ],
  "summary": {
    "total": 10,
    "healthy": 8,
    "degraded": 1,
    "unhealthy": 1
  }
}
```

**POST /api/kubectl/dry-run**

```json
// Request
{
  "command": "delete pod nginx-xxx",
  "namespace": "default"
}

// Response
{
  "ok": true,
  "dry_run": true,
  "command": "kubectl delete pod nginx-xxx -n default --dry-run=client",
  "risk_level": "high",
  "requires_confirmation": true,
  "impact": "Pod nginx-xxx will be deleted and recreated by Deployment",
  "safe_alternative": "kubectl rollout restart deployment/nginx"
}
```

## [S5] 实施计划

### Phase 1：基础结构化（1 周）

- [ ] 实现 `StructuredOutput`：解析 `get pods -o wide`、`describe pod`、`top nodes`、`top pods`
- [ ] 实现 `ErrorMapper`：映射 Top 10 常见错误
- [ ] 添加 `/api/kubectl/execute` 端点（structured 模式）

### Phase 2：健康检查（1 周）

- [ ] 实现 `HealthChecker`：Pod/Node/Service 健康判断
- [ ] 添加 `/api/kubectl/health-check` 端点
- [ ] 集成到 AI 对话上下文

### Phase 3：安全守卫（0.5 周）

- [ ] 实现 `SafetyGuard`：风险分级 + dry-run
- [ ] 添加 `/api/kubectl/dry-run` 端点
- [ ] 高危操作增加确认机制

### Phase 4：命令注册表（0.5 周）

- [ ] 实现 `CommandRegistry`：Top 15 kubectl 命令元数据
- [ ] 添加 `/api/kubectl/commands` 端点
- [ ] AI 对话中自动注入可用命令列表

## [S6] 与现有系统的整合

```
现有流程：
  AI Chat → Function Calling → _exec_arthas() → kubectl exec → Arthas API

升级后流程：
  AI Chat → 意图识别 → CommandRegistry 选择命令 → SafetyGuard 校验
       → KubectlExecutor 执行 → StructuredOutput 解析 → HealthChecker 判断
       → 返回结构化结果 → LLM 分析
```

## [S7] 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| kubectl 输出格式变化 | 使用 `-o json` 为主，文本解析为辅 |
| 性能影响 | 结构化解析在 Python 层，不增加 kubectl 调用次数 |
| 兼容性 | 新增组件不修改现有 KubectlExecutor |
| 安全性 | 危险操作必须经过 SafetyGuard 校验 |
