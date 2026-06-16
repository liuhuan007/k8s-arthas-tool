# K8s Arthas Tool — 下一代 AI 运维底座架构设计

> CLI + Skill + LLM = AI-native 运维操作界面

**文档版本**: v2.0
**创建日期**: 2026-06-14
**状态**: 设计完成
**实施状态**: Phase 1-3 已完成
**完成日期**: 2026-06-15

---

## [S1] 问题背景：从"聊天助手"到"诊断引擎"

### 1.1 当前架构的局限

```
当前模式：
  用户: "帮我看看 CPU 为什么高"
  AI:   "好的，我来执行 thread -n 3..."  → 单次问答，无流程
  问题: AI 不知道该先查什么、后查什么、怎么判断
```

### 1.2 行业趋势（参考阿里云 CMS CLI + Agent Skill）

阿里云的实践证明了三层架构的有效性：

| 层次 | 职责 | 对应我们的系统 |
|------|------|---------------|
| **CLI 层** | 统一命令入口，AI 可调用 | kubectl + Arthas HTTP API |
| **Skill 层** | 业务工作流，AI 可执行 | Skill Registry + Workflow Engine |
| **LLM 层** | 意图理解，流程编排 | AI Chat + Function Calling |

**关键认知**：CLI 不是"给人用的命令行"，而是"给 AI Agent 用的标准操作界面"。

### 1.3 我们有两个 CLI 需要统一

| CLI | 覆盖领域 | 当前状态 |
|-----|---------|---------|
| **kubectl** | K8s 资源管理、Pod 生命周期、事件、日志 | 已封装但未结构化 |
| **Arthas** | Java 诊断：线程、方法追踪、JVM 指标、堆分析 | HTTP API 已可用 |

两者都需要：结构化输出、错误标准化、健康检查、安全守卫、命令元数据。

## [S2] 设计目标

### 2.1 核心目标

| 目标 | 描述 | 度量 |
|------|------|------|
| **AI 可消费** | 所有命令输出有结构化 JSON 模式 | Token 消耗降低 60% |
| **错误可机读** | 100% 错误有结构化 error code | AI 可自动决策修复 |
| **健康可判断** | Pod/Node/JVM 有统一健康模型 | 一次调用获取完整健康状态 |
| **操作可控制** | 危险操作有 dry-run + 确认 | 零误操作 |
| **命令可发现** | AI 能通过元数据找到正确命令 | 命令注册表 100% 覆盖 |

### 2.2 与阿里云 CMS CLI 的对齐

参考阿里云的做法，我们的 CLI 需要：

1. **`--help` 丰富化**：每个命令包含描述、参数说明、示例、约束
2. **紧凑输出**：`-o text` 输出紧凑格式，降低 Token 消耗
3. **结构化错误**：JSON 错误码，支持 AI 自动决策
4. **幂等操作**：支持 dry-run 模式

## [S3] 统一架构设计

### 3.1 四层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      自然语言入口层                               │
│  "帮我诊断这个 Pod 的 CPU 问题"                                   │
│  "这个接口最近变慢了，帮我排查"                                    │
│  "告警：Pod CrashLoopBackOff"                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 意图识别 + 场景匹配
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Skill 编排层                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ CPU 高排查    │  │ 接口慢排查   │  │ Pod 异常排查  │         │
│  │ Skill        │  │ Skill        │  │ Skill        │         │
│  │              │  │              │  │              │         │
│  │ kubectl:top  │  │ kubectl:logs │  │ kubectl:desc │         │ │
│  │ Arthas:thread│  │ Arthas:trace │  │ Arthas:dashboard     │ │
│  │ Arthas:dash  │  │ Arthas:watch │  │ Arthas:heapdump     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 按步骤执行
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLI 执行层（统一抽象）                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  CLIAdapter（统一接口）                    │   │
│  │  execute(command, params) → StructuredResult             │   │
│  └────────────┬────────────────────────┬───────────────────┘   │
│               │                        │                        │
│    ┌──────────▼──────────┐  ┌──────────▼──────────┐           │
│    │   KubectlAdapter    │  │   ArthasAdapter     │           │
│    │   kubectl exec      │  │   Arthas HTTP API   │           │
│    │   kubectl get       │  │   thread/dashboard  │           │
│    │   kubectl describe  │  │   trace/watch/jad   │           │
│    └─────────────────────┘  └─────────────────────┘           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    安全与治理层                                   │
│  SafetyGuard（风险分级）  AuditLog（审计日志）  HealthChecker    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 核心抽象：CLIAdapter

统一 kubectl 和 Arthas 的调用接口：

```python
class CLIAdapter(ABC):
    """CLI 统一抽象接口"""

    @abstractmethod
    def execute(self, command: str, params: dict) -> StructuredResult:
        """执行命令，返回结构化结果"""

    @abstractmethod
    def get_commands(self) -> list:
        """获取可用命令列表（含元数据）"""

    @abstractmethod
    def health_check(self, target: str) -> HealthStatus:
        """检查目标健康状态"""

    @abstractmethod
    def dry_run(self, command: str, params: dict) -> DryRunResult:
        """Dry-run 预览"""

class StructuredResult:
    """结构化执行结果"""
    ok: bool
    command: str           # 实际执行的命令
    data: dict             # 结构化数据
    raw_output: str        # 原始输出（可选）
    health: HealthStatus   # 健康状态
    error: ErrorCode       # 错误码（如果失败）
    metadata: dict         # 执行耗时、重试次数等
```

## [S4] kubectl CLI 适配设计

### 4.1 KubectlAdapter 实现

```python
class KubectlAdapter(CLIAdapter):
    """kubectl AI 适配器"""

    def execute(self, command: str, params: dict) -> StructuredResult:
        """
        执行 kubectl 命令

        command: "get_pods" | "describe_pod" | "get_events" | ...
        params: {"namespace": "default", "name": "nginx", "label": "app=nginx"}
        """
        # 1. 从 CommandRegistry 获取命令模板
        cmd_template = KUBECTL_COMMANDS[command]

        # 2. SafetyGuard 校验
        risk = SafetyGuard.check_risk(cmd_template)
        if risk["requires_confirm"]:
            return StructuredResult(ok=False, error=ErrorCode.REQUIRES_CONFIRMATION)

        # 3. 构建命令
        cmd = self._build_command(cmd_template, params)

        # 4. 执行
        rc, stdout, stderr = self._run(cmd)

        # 5. 结构化解析
        if rc == 0:
            data = StructuredOutput.parse(stdout, command)
            health = HealthChecker.check(data, command)
            return StructuredResult(ok=True, data=data, health=health)
        else:
            error = ErrorMapper.map(stderr, rc)
            return StructuredResult(ok=False, error=error)
```

### 4.2 kubectl 命令注册表

```python
KUBECTL_COMMANDS = {
    # ── Pod 生命周期 ──────────────────────────────────────
    "get_pods": {
        "command": "get pods -o wide",
        "description": "获取 Pod 列表和状态",
        "when_to_use": ["查看 Pod 运行状态", "检查 Pod 是否正常"],
        "risk_level": "read",
        "structured_parser": "parse_pod_list",
        "health_checker": "check_pod_health",
    },
    "describe_pod": {
        "command": "describe pod {name}",
        "description": "获取 Pod 详细信息（Events、Conditions、资源）",
        "when_to_use": ["Pod 异常时查看详情", "排查 Pod 启动失败"],
        "risk_level": "read",
        "structured_parser": "parse_pod_describe",
    },
    "get_pod_logs": {
        "command": "logs {name} [--previous] [-c {container}]",
        "description": "获取 Pod 容器日志",
        "when_to_use": ["查看应用日志", "排查 CrashLoopBackOff"],
        "risk_level": "read",
    },
    "exec_in_pod": {
        "command": "exec {name} -- {shell_cmd}",
        "description": "在 Pod 内执行命令",
        "when_to_use": ["检查文件", "执行诊断命令", "检查进程"],
        "risk_level": "low",
    },
    "delete_pod": {
        "command": "delete pod {name}",
        "description": "删除 Pod（会触发重建）",
        "when_to_use": ["Pod 卡死需要重启", "清理异常 Pod"],
        "risk_level": "high",
        "requires_confirmation": True,
        "dry_run_supported": True,
        "safe_alternative": "kubectl rollout restart deployment/{deployment}",
    },

    # ── 资源监控 ──────────────────────────────────────────
    "top_pods": {
        "command": "top pods --no-headers",
        "description": "获取 Pod CPU/内存使用",
        "when_to_use": ["查看资源使用", "检查是否超限"],
        "risk_level": "read",
        "structured_parser": "parse_top_pods",
    },
    "top_nodes": {
        "command": "top nodes --no-headers",
        "description": "获取 Node CPU/内存使用",
        "when_to_use": ["查看节点资源", "检查节点负载"],
        "risk_level": "read",
        "structured_parser": "parse_top_nodes",
    },

    # ── 事件与状态 ────────────────────────────────────────
    "get_events": {
        "command": "get events --sort-by='.lastTimestamp' --field-selector involvedObject.name={name}",
        "description": "获取资源相关事件",
        "when_to_use": ["排查问题时间线", "查看告警事件"],
        "risk_level": "read",
        "structured_parser": "parse_events",
    },
    "get_nodes": {
        "command": "get nodes -o wide",
        "description": "获取 Node 列表和状态",
        "when_to_use": ["查看节点状态", "检查节点资源"],
        "risk_level": "read",
    },
    "cluster_info": {
        "command": "cluster-info",
        "description": "获取集群基本信息",
        "when_to_use": ["检查集群连通性", "确认集群版本"],
        "risk_level": "read",
    },
}
```

## [S5] Arthas CLI 适配设计

### 5.1 ArthasAdapter 实现

```python
class ArthasAdapter(CLIAdapter):
    """Arthas HTTP API 适配器（AI 友好封装）"""

    def execute(self, command: str, params: dict) -> StructuredResult:
        """
        执行 Arthas 命令

        command: "thread" | "dashboard" | "trace" | "jad" | ...
        params: {"n": 5, "class_pattern": "com.example.*", ...}
        """
        # 1. 从 CommandRegistry 获取命令模板
        cmd_template = ARTHAS_COMMANDS[command]

        # 2. 构建 Arthas 命令字符串
        arthas_cmd = self._build_arthas_command(cmd_template, params)

        # 3. 通过 HTTP API 执行
        result = self.http_client.execute(arthas_cmd)

        # 4. 结构化解析
        data = StructuredOutput.parse_arthas(result, command)
        health = HealthChecker.check_jvm(data, command)

        return StructuredResult(ok=True, data=data, health=health)
```

### 5.2 Arthas 命令注册表

```python
ARTHAS_COMMANDS = {
    # ── 线程分析 ──────────────────────────────────────────
    "thread": {
        "command": "thread -n {top_n}",
        "description": "获取线程快照，按 CPU 使用排序",
        "when_to_use": ["CPU 飙高排查", "线程阻塞分析"],
        "risk_level": "read",
        "structured_parser": "parse_thread_output",
        "help": {
            "params": {"top_n": "返回前 N 个线程，默认 5"},
            "examples": ["thread -n 5", "thread -b (检测死锁)"],
            "output": "线程 ID、名称、状态、CPU 使用率、堆栈"
        }
    },
    "thread_deadlock": {
        "command": "thread -b",
        "description": "检测死锁线程",
        "when_to_use": ["怀疑死锁", "线程长时间阻塞"],
        "risk_level": "read",
    },

    # ── JVM 指标 ──────────────────────────────────────────
    "dashboard": {
        "command": "dashboard -n 1",
        "description": "获取 JVM 实时指标快照（内存/GC/CPU/线程）",
        "when_to_use": ["快速评估 JVM 状态", "查看内存使用", "检查 GC 情况"],
        "risk_level": "read",
        "structured_parser": "parse_dashboard_output",
        "help": {
            "output": "内存区域使用、GC 统计、CPU 使用率、线程统计"
        }
    },

    # ── 方法追踪 ──────────────────────────────────────────
    "trace": {
        "command": "trace {class_pattern} {method_pattern} -n {sample_count}",
        "description": "追踪方法调用链耗时",
        "when_to_use": ["接口慢排查", "方法耗时分析", "调用链定位"],
        "risk_level": "read",
        "structured_parser": "parse_trace_output",
        "help": {
            "params": {
                "class_pattern": "类名模式，如 com.example.service.*",
                "method_pattern": "方法名，支持 * 通配",
                "sample_count": "采样次数，默认 5"
            },
            "examples": [
                "trace com.example.service.UserService saveUser",
                "trace com.example.controller.* * -n 10"
            ]
        }
    },
    "watch": {
        "command": "watch {class_pattern} {method_pattern} '{params_and_return}' -e -x 2",
        "description": "观测方法入参和返回值",
        "when_to_use": ["方法参数查看", "异常捕获", "返回值分析"],
        "risk_level": "read",
    },
    "jad": {
        "command": "jad {class_pattern}",
        "description": "反编译类源码",
        "when_to_use": ["查看类实现", "确认代码版本", "排查类冲突"],
        "risk_level": "read",
    },

    # ── 堆分析 ────────────────────────────────────────────
    "heapdump": {
        "command": "heapdump --live {path}",
        "description": "导出堆转储（大文件，需谨慎）",
        "when_to_use": ["OOM 排查", "内存泄漏分析"],
        "risk_level": "high",
        "requires_confirmation": True,
        "dry_run_supported": True,
    },

    # ── 性能采样 ──────────────────────────────────────────
    "profiler": {
        "command": "profiler start --event {event} --duration {duration}",
        "description": "启动 async-profiler 性能采样",
        "when_to_use": ["CPU 热点分析", "内存分配分析"],
        "risk_level": "medium",
        "requires_confirmation": True,
    },

    # ── 类搜索 ────────────────────────────────────────────
    "sc": {
        "command": "sc -d {class_pattern}",
        "description": "搜索类加载信息",
        "when_to_use": ["确认类是否存在", "查看类加载器", "排查类冲突"],
        "risk_level": "read",
    },
    "sm": {
        "command": "sm {class_pattern} {method_pattern}",
        "description": "搜索方法",
        "when_to_use": ["确认方法是否存在", "查看方法签名"],
        "risk_level": "read",
    },
}
```

## [S6] 统一基础设施

### 6.1 StructuredOutput — 结构化输出

统一解析 kubectl 和 Arthas 的输出：

```python
class StructuredOutput:
    """统一结构化解析器"""

    # kubectl 解析器
    @staticmethod
    def parse_pod_list(raw: str) -> list: ...
    @staticmethod
    def parse_pod_describe(raw: str) -> dict: ...
    @staticmethod
    def parse_top_pods(raw: str) -> list: ...
    @staticmethod
    def parse_top_nodes(raw: str) -> list: ...
    @staticmethod
    def parse_events(raw: str) -> list: ...

    # Arthas 解析器
    @staticmethod
    def parse_thread_output(raw: str) -> dict: ...
    @staticmethod
    def parse_dashboard_output(raw: str) -> dict: ...
    @staticmethod
    def parse_trace_output(raw: str) -> dict: ...
    @staticmethod
    def parse_jad_output(raw: str) -> dict: ...
```

### 6.2 HealthChecker — 统一健康模型

```python
class HealthChecker:
    """统一健康状态判断"""

    # K8s 资源健康
    @staticmethod
    def check_pod(pod_json: dict) -> HealthStatus: ...
    @staticmethod
    def check_node(node_json: dict) -> HealthStatus: ...
    @staticmethod
    def check_service(svc_json: dict, endpoints: list) -> HealthStatus: ...

    # JVM 健康
    @staticmethod
    def check_jvm(dashboard_data: dict) -> HealthStatus:
        """
        JVM 健康判断规则：
        - CPU < 70% + Memory < 80% + GC < 5s → healthy
        - CPU 70-90% 或 Memory 80-90% → degraded
        - CPU > 90% 或 Memory > 90% 或 FullGC > 10s → unhealthy
        """

    @staticmethod
    def check_thread(thread_data: dict) -> HealthStatus:
        """
        线程健康判断规则：
        - 无 BLOCKED 线程 + 总数 < 500 → healthy
        - 有 BLOCKED 线程 → degraded
        - 死锁检测到 → unhealthy
        """
```

### 6.3 SafetyGuard — 安全守卫

```python
class SafetyGuard:
    """统一安全守卫"""

    RISK_LEVELS = {
        # kubectl
        "kubectl:get":    "read",
        "kubectl:describe": "read",
        "kubectl:logs":   "read",
        "kubectl:exec":   "low",
        "kubectl:port-forward": "low",
        "kubectl:delete": "high",
        "kubectl:scale":  "medium",

        # Arthas
        "arthas:thread":  "read",
        "arthas:dashboard": "read",
        "arthas:trace":   "read",
        "arthas:jad":     "read",
        "arthas:sc":      "read",
        "arthas:sm":      "read",
        "arthas:watch":   "read",
        "arthas:heapdump": "high",
        "arthas:profiler": "medium",
    }

    @staticmethod
    def check_risk(cli: str, command: str) -> RiskLevel: ...
    @staticmethod
    def dry_run(cli: str, command: str, params: dict) -> DryRunResult: ...
    @staticmethod
    def validate_before_execute(cli: str, command: str, params: dict) -> ValidationResult: ...
```

### 6.4 ErrorMapper — 统一错误码

```python
class ErrorCode:
    # 通用
    TIMEOUT = "E0001"
    CONNECTION_FAILED = "E0002"
    PERMISSION_DENIED = "E0003"
    REQUIRES_CONFIRMATION = "E0004"

    # K8s
    POD_NOT_FOUND = "E1001"
    POD_NOT_RUNNING = "E1002"
    POD_CRASHLOOP = "E1003"
    POD_OOMKILLED = "E1004"
    NAMESPACE_NOT_FOUND = "E1005"
    NODE_NOT_READY = "E1006"
    CLUSTER_UNREACHABLE = "E1007"

    # Arthas
    ARTHAS_NOT_CONNECTED = "E2001"
    ARTHAS_COMMAND_FAILED = "E2002"
    ARTHAS_TIMEOUT = "E2003"
    CLASS_NOT_FOUND = "E2004"
    METHOD_NOT_FOUND = "E2005"
```

## [S7] API 设计

### 7.1 统一 CLI API

```
# 命令发现
GET  /api/cli/commands                          # 所有可用命令
GET  /api/cli/commands/{cli}                     # 指定 CLI 的命令
GET  /api/cli/commands/{cli}/{command}/help      # 命令帮助信息

# 命令执行
POST /api/cli/execute                           # 统一执行入口
POST /api/cli/dry-run                           # Dry-run 预览

# 健康检查
POST /api/cli/health-check                      # 统一健康检查

# 错误参考
GET  /api/cli/errors                            # 所有错误码
```

### 7.2 请求/响应格式

**POST /api/cli/execute**

```json
// Request
{
  "cli": "kubectl",                              // "kubectl" | "arthas"
  "command": "get_pods",
  "params": {
    "namespace": "default",
    "label": "app=nginx"
  },
  "output": "structured"                         // "raw" | "structured"
}

// Response
{
  "ok": true,
  "cli": "kubectl",
  "command": "get pods -n default -l app=nginx -o wide",
  "data": [...],
  "health": {
    "status": "healthy",
    "summary": {"total": 5, "healthy": 4, "unhealthy": 1}
  },
  "metadata": {
    "duration_ms": 120,
    "token_estimate": 150
  }
}
```

**POST /api/cli/health-check**

```json
// Request
{
  "cli": "kubectl",
  "resource": "pod",
  "namespace": "default",
  "name": "nginx-xxx"                            // 可选
}

// Response
{
  "ok": true,
  "items": [
    {
      "name": "nginx-xxx",
      "health": "healthy",
      "status": "Running",
      "conditions": ["Ready=True"],
      "issues": []
    }
  ],
  "summary": {"total": 10, "healthy": 8, "degraded": 1, "unhealthy": 1}
}
```

## [S8] 与 Skill 层的整合

### 8.1 Skill 如何使用 CLI

```yaml
name: cpu-high-diagnosis
description: "CPU 使用率过高诊断流程"

steps:
  # Step 1: kubectl 检查 Pod 状态
  - id: check_pod
    cli: kubectl
    command: get_pods
    params:
      namespace: "{namespace}"
      label: "app={app_name}"
    parse: check_pod_health

  # Step 2: Arthas 线程分析
  - id: thread_analysis
    cli: arthas
    command: thread
    params:
      top_n: 5
    condition: "check_pod.health == 'healthy'"

  # Step 3: Arthas dashboard
  - id: jvm_baseline
    cli: arthas
    command: dashboard
    params:
      n: 1
    condition: "thread_analysis.cpu_threads > 0"

  # Step 4: LLM 分析
  - id: llm_analysis
    cli: llm
    command: analyze
    input: [thread_analysis, jvm_baseline]
    prompt_template: "cpu_analysis_prompt"
```

### 8.2 AI Agent 如何使用 CLI

```
用户: "帮我诊断这个 Pod 的 CPU 问题"

AI Agent:
  1. 意图识别 → "CPU 高诊断" → 匹配 Skill: cpu-high-diagnosis
  2. 获取 Skill 定义 → 加载步骤列表
  3. Step 1: POST /api/cli/execute {"cli":"kubectl","command":"get_pods",...}
  4. Step 2: POST /api/cli/execute {"cli":"arthas","command":"thread",...}
  5. Step 3: POST /api/cli/execute {"cli":"arthas","command":"dashboard",...}
  6. Step 4: 汇总结果 → LLM 生成诊断报告
  7. 返回给用户
```

## [S9] 实施计划

### Phase 1：CLI 统一抽象（1 周）

- [ ] 定义 `CLIAdapter` 抽象接口
- [ ] 实现 `KubectlAdapter`（封装现有 KubectlExecutor）
- [ ] 实现 `ArthasAdapter`（封装现有 ArthasHttpClient）
- [ ] 实现 `StructuredOutput` 解析器（Top 10 命令）

### Phase 2：安全与治理（1 周）

- [ ] 实现 `SafetyGuard`（风险分级 + dry-run）
- [ ] 实现 `ErrorMapper`（统一错误码）
- [ ] 实现 `HealthChecker`（Pod/Node/JVM 健康判断）
- [ ] 添加审计日志

### Phase 3：命令注册表（0.5 周）

- [ ] 实现 `CommandRegistry`（kubectl 15 命令 + Arthas 15 命令）
- [ ] 添加 `/api/cli/commands` API
- [ ] AI 对话中自动注入命令列表

### Phase 4：API 网关（0.5 周）

- [ ] 实现 `/api/cli/execute` 统一执行入口
- [ ] 实现 `/api/cli/health-check` 统一健康检查
- [ ] 实现 `/api/cli/dry-run` 安全预览

### Phase 5：Skill 集成（1 周）

- [ ] 改造现有 Skill 支持 CLI adapter
- [ ] 实现 5 个核心诊断 Skill
- [ ] AI 对话集成 Skill 编排

## [S10] 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| kubectl 输出格式变化 | 优先使用 `-o json`，文本解析为辅 |
| Arthas HTTP API 不稳定 | 增加重试和降级机制 |
| 性能影响 | 结构化解析在 Python 层，不增加 CLI 调用次数 |
| 兼容性 | 新增组件不修改现有 KubectlExecutor/ArthasHttpClient |
| 安全性 | 危险操作必须经过 SafetyGuard 校验 |
| Token 消耗 | 紧凑输出 + 结构化 JSON 降低 60% Token |
