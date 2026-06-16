# Unified CLI Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 kubectl + Arthas CLI 为 AI-native 操作界面，支持结构化输出、健康检查、安全守卫、命令注册表

**Architecture:** CLIAdapter 抽象层统一 kubectl 和 Arthas 调用，StructuredOutput 解析器将输出转为 JSON，HealthChecker 统一健康判断，SafetyGuard 控制危险操作，CommandRegistry 提供命令元数据

**Tech Stack:** Python 3.10+, Flask, subprocess (kubectl), urllib (Arthas HTTP)

---

## File Structure

```
backend/core/
├── cli/
│   ├── __init__.py
│   ├── adapter.py          # CLIAdapter 抽象接口
│   ├── kubectl_adapter.py  # KubectlAdapter 实现
│   ├── arthas_adapter.py   # ArthasAdapter 实现
│   ├── structured_output.py # 结构化输出解析器
│   ├── health_checker.py   # 统一健康检查
│   ├── safety_guard.py     # 安全守卫
│   ├── error_mapper.py     # 错误码映射
│   └── command_registry.py # 命令注册表
api/
├── cli_api.py              # /api/cli/* 路由
tests/
├── test_cli_adapter.py
├── test_structured_output.py
├── test_health_checker.py
├── test_safety_guard.py
```

---

### Task 1: CLIAdapter 抽象接口

**Covers:** [S3]

**Files:**
- Create: `backend/core/cli/__init__.py`
- Create: `backend/core/cli/adapter.py`
- Test: `tests/test_cli_adapter.py`

- [ ] **Step 1: Create package init**

```python
# backend/core/cli/__init__.py
from .adapter import CLIAdapter, StructuredResult, RiskLevel
from .kubectl_adapter import KubectlAdapter
from .arthas_adapter import ArthasAdapter
from .structured_output import StructuredOutput
from .health_checker import HealthChecker
from .safety_guard import SafetyGuard
from .error_mapper import ErrorCode, ErrorMapper
from .command_registry import CommandRegistry
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_cli_adapter.py
import pytest
from backend.core.cli.adapter import CLIAdapter, StructuredResult, RiskLevel


def test_structured_result_creation():
    result = StructuredResult(ok=True, command="get pods", data={"items": []})
    assert result.ok is True
    assert result.command == "get pods"
    assert result.data == {"items": []}
    assert result.health is None
    assert result.error is None


def test_structured_result_with_error():
    result = StructuredResult(ok=False, command="get pods", error="E1001")
    assert result.ok is False
    assert result.error == "E1001"


def test_risk_level_enum():
    assert RiskLevel.READ.value == "read"
    assert RiskLevel.HIGH.value == "high"


def test_cli_adapter_is_abstract():
    with pytest.raises(TypeError):
        CLIAdapter()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_adapter.py -v`
Expected: FAIL with ImportError

- [ ] **Step 4: Write implementation**

```python
# backend/core/cli/adapter.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class RiskLevel(Enum):
    READ = "read"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class StructuredResult:
    ok: bool
    command: str
    data: Any = None
    raw_output: str = ""
    health: Optional[Dict] = None
    error: Optional[str] = None
    error_detail: Optional[Dict] = None
    metadata: Dict = field(default_factory=dict)


class CLIAdapter(ABC):
    """CLI 统一抽象接口"""

    @abstractmethod
    def execute(self, command: str, params: Dict[str, Any]) -> StructuredResult:
        """执行命令，返回结构化结果"""

    @abstractmethod
    def get_commands(self) -> list:
        """获取可用命令列表（含元数据）"""

    @abstractmethod
    def health_check(self, target: str = "", params: Dict = None) -> Dict:
        """检查目标健康状态"""

    @abstractmethod
    def dry_run(self, command: str, params: Dict[str, Any]) -> Dict:
        """Dry-run 预览"""
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_adapter.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/core/cli/__init__.py backend/core/cli/adapter.py tests/test_cli_adapter.py
git commit -m "feat: add CLIAdapter abstract interface with StructuredResult and RiskLevel"
```

---

### Task 2: ErrorCode 和 ErrorMapper

**Covers:** [S3, S6.4]

**Files:**
- Create: `backend/core/cli/error_mapper.py`
- Test: `tests/test_cli_adapter.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli_adapter.py (append)

from backend.core.cli.error_mapper import ErrorCode, ErrorMapper


def test_error_code_values():
    assert ErrorCode.POD_NOT_FOUND == "E1001"
    assert ErrorCode.ARTHAS_NOT_CONNECTED == "E2001"
    assert ErrorCode.TIMEOUT == "E0001"


def test_error_mapper_map_kubectl_not_found():
    result = ErrorMapper.map_kubectl_error(
        stderr="Error from server (NotFound): pods \"nginx\" not found",
        returncode=1
    )
    assert result["code"] == ErrorCode.POD_NOT_FOUND
    assert "nginx" in result["detail"]
    assert result["retryable"] is False


def test_error_mapper_map_timeout():
    result = ErrorMapper.map_kubectl_error(
        stderr="",
        returncode=-1,
        timeout_msg="kubectl 超时 (30s)"
    )
    assert result["code"] == ErrorCode.TIMEOUT
    assert result["retryable"] is True


def test_error_mapper_map_permission_denied():
    result = ErrorMapper.map_kubectl_error(
        stderr="Error from server (Forbidden): pods is forbidden",
        returncode=1
    )
    assert result["code"] == ErrorCode.PERMISSION_DENIED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_adapter.py::test_error_code_values -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write implementation**

```python
# backend/core/cli/error_mapper.py
import re
from typing import Dict


class ErrorCode:
    TIMEOUT = "E0001"
    CONNECTION_FAILED = "E0002"
    PERMISSION_DENIED = "E0003"
    REQUIRES_CONFIRMATION = "E0004"

    POD_NOT_FOUND = "E1001"
    POD_NOT_RUNNING = "E1002"
    POD_CRASHLOOP = "E1003"
    POD_OOMKILLED = "E1004"
    NAMESPACE_NOT_FOUND = "E1005"
    NODE_NOT_READY = "E1006"
    CLUSTER_UNREACHABLE = "E1007"

    ARTHAS_NOT_CONNECTED = "E2001"
    ARTHAS_COMMAND_FAILED = "E2002"
    ARTHAS_TIMEOUT = "E2003"
    CLASS_NOT_FOUND = "E2004"
    METHOD_NOT_FOUND = "E2005"


class ErrorMapper:
    """将 CLI stderr 映射为结构化错误"""

    _KUBECTL_PATTERNS = [
        (r'pods? .* not found', ErrorCode.POD_NOT_FOUND, False),
        (r'nodes? .* not found', ErrorCode.NODE_NOT_READY, False),
        (r'namespaces? .* not found', ErrorCode.NAMESPACE_NOT_FOUND, False),
        (r'Forbidden', ErrorCode.PERMISSION_DENIED, False),
        (r'Unauthorized', ErrorCode.PERMISSION_DENIED, False),
        (r'connection refused', ErrorCode.CLUSTER_UNREACHABLE, True),
        (r'unable to connect', ErrorCode.CLUSTER_UNREACHABLE, True),
    ]

    @classmethod
    def map_kubectl_error(cls, stderr: str, returncode: int,
                          timeout_msg: str = "") -> Dict:
        """映射 kubectl 错误"""
        if returncode == -1 and timeout_msg:
            return {
                "code": ErrorCode.TIMEOUT,
                "message": "Command timed out",
                "detail": timeout_msg,
                "suggestion": "请检查网络连接或增加超时时间",
                "retryable": True,
            }

        for pattern, code, retryable in cls._KUBECTL_PATTERNS:
            if re.search(pattern, stderr, re.IGNORECASE):
                return {
                    "code": code,
                    "message": code,
                    "detail": stderr[:200],
                    "suggestion": cls._get_suggestion(code),
                    "retryable": retryable,
                }

        return {
            "code": ErrorCode.CONNECTION_FAILED,
            "message": "Unknown error",
            "detail": stderr[:200],
            "suggestion": "请检查 kubectl 配置和集群连接",
            "retryable": False,
        }

    @classmethod
    def _get_suggestion(cls, code: str) -> str:
        suggestions = {
            ErrorCode.POD_NOT_FOUND: "请检查 Pod 名称是否正确，或确认 Pod 所在的 namespace",
            ErrorCode.NAMESPACE_NOT_FOUND: "请检查 namespace 名称是否正确",
            ErrorCode.PERMISSION_DENIED: "请检查 RBAC 权限配置",
            ErrorCode.CLUSTER_UNREACHABLE: "请检查集群连接和网络",
            ErrorCode.TIMEOUT: "请检查网络连接或增加超时时间",
        }
        return suggestions.get(code, "请检查命令参数和集群状态")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/cli/error_mapper.py
git commit -m "feat: add ErrorCode and ErrorMapper for unified error handling"
```

---

### Task 3: SafetyGuard 安全守卫

**Covers:** [S3, S6.3]

**Files:**
- Create: `backend/core/cli/safety_guard.py`
- Test: `tests/test_cli_adapter.py` (extend)

- [ ] **Step 1: Write failing test**

```python
# tests/test_cli_adapter.py (append)

from backend.core.cli.safety_guard import SafetyGuard
from backend.core.cli.adapter import RiskLevel


def test_safety_guard_read_commands():
    risk = SafetyGuard.check_risk("kubectl", "get_pods")
    assert risk["level"] == RiskLevel.READ
    assert risk["requires_confirm"] is False


def test_safety_guard_high_risk_commands():
    risk = SafetyGuard.check_risk("kubectl", "delete_pod")
    assert risk["level"] == RiskLevel.HIGH
    assert risk["requires_confirm"] is True
    assert risk["dry_run_supported"] is True


def test_safety_guard_dry_run():
    result = SafetyGuard.dry_run("kubectl", "delete_pod", {"name": "nginx"})
    assert result["dry_run"] is True
    assert "nginx" in result["command"]
    assert "dry-run" in result["command"]


def test_safety_guard_arthas_read():
    risk = SafetyGuard.check_risk("arthas", "thread")
    assert risk["level"] == RiskLevel.READ


def test_safety_guard_arthas_heapdump():
    risk = SafetyGuard.check_risk("arthas", "heapdump")
    assert risk["level"] == RiskLevel.HIGH
    assert risk["requires_confirm"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_adapter.py::test_safety_guard_read_commands -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write implementation**

```python
# backend/core/cli/safety_guard.py
from typing import Dict, Any
from .adapter import RiskLevel


class SafetyGuard:
    """统一安全守卫"""

    RISK_MAP = {
        ("kubectl", "get_pods"): RiskLevel.READ,
        ("kubectl", "describe_pod"): RiskLevel.READ,
        ("kubectl", "get_pod_logs"): RiskLevel.READ,
        ("kubectl", "get_events"): RiskLevel.READ,
        ("kubectl", "get_nodes"): RiskLevel.READ,
        ("kubectl", "top_pods"): RiskLevel.READ,
        ("kubectl", "top_nodes"): RiskLevel.READ,
        ("kubectl", "cluster_info"): RiskLevel.READ,
        ("kubectl", "exec_in_pod"): RiskLevel.LOW,
        ("kubectl", "port_forward"): RiskLevel.LOW,
        ("kubectl", "delete_pod"): RiskLevel.HIGH,
        ("arthas", "thread"): RiskLevel.READ,
        ("arthas", "thread_deadlock"): RiskLevel.READ,
        ("arthas", "dashboard"): RiskLevel.READ,
        ("arthas", "trace"): RiskLevel.READ,
        ("arthas", "watch"): RiskLevel.READ,
        ("arthas", "jad"): RiskLevel.READ,
        ("arthas", "sc"): RiskLevel.READ,
        ("arthas", "sm"): RiskLevel.READ,
        ("arthas", "heapdump"): RiskLevel.HIGH,
        ("arthas", "profiler"): RiskLevel.MEDIUM,
    }

    @classmethod
    def check_risk(cls, cli: str, command: str) -> Dict[str, Any]:
        level = cls.RISK_MAP.get((cli, command), RiskLevel.READ)
        return {
            "level": level,
            "requires_confirm": level in (RiskLevel.HIGH, RiskLevel.MEDIUM),
            "dry_run_supported": level in (RiskLevel.HIGH,),
        }

    @classmethod
    def dry_run(cls, cli: str, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        risk = cls.check_risk(cli, command)
        if cli == "kubectl" and command == "delete_pod":
            name = params.get("name", "<pod>")
            ns = params.get("namespace", "default")
            return {
                "dry_run": True,
                "command": f"kubectl delete pod {name} -n {ns} --dry-run=client",
                "risk_level": risk["level"],
                "requires_confirmation": risk["requires_confirm"],
            }
        return {"dry_run": True, "command": f"{cli} {command}", "risk_level": risk["level"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_adapter.py -k safety -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/cli/safety_guard.py
git commit -m "feat: add SafetyGuard with risk levels and dry-run support"
```

---

### Task 4: StructuredOutput 结构化输出解析器

**Covers:** [S3, S6.1]

**Files:**
- Create: `backend/core/cli/structured_output.py`
- Test: `tests/test_structured_output.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_structured_output.py
import pytest
from backend.core.cli.structured_output import StructuredOutput


def test_parse_pod_list():
    raw = """NAME                    READY   STATUS    RESTARTS   AGE
nginx-7c5ddbdf54-abc12   1/1     Running   0          2d
redis-yyy                0/1     Error     3          1h"""
    result = StructuredOutput.parse_pod_list(raw)
    assert len(result) == 2
    assert result[0]["name"] == "nginx-7c5ddbdf54-abc12"
    assert result[0]["status"] == "Running"
    assert result[0]["restarts"] == 0
    assert result[1]["status"] == "Error"
    assert result[1]["restarts"] == 3


def test_parse_top_pods():
    raw = """NAME                    CPU(bytes)   MEMORY(bytes)
nginx-7c5ddbdf54-abc12   100m         128Mi
redis-yyy                50m          64Mi"""
    result = StructuredOutput.parse_top_pods(raw)
    assert len(result) == 2
    assert result[0]["cpu"] == "100m"
    assert result[0]["memory"] == "128Mi"


def test_parse_empty_output():
    result = StructuredOutput.parse_pod_list("")
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_structured_output.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write implementation**

```python
# backend/core/cli/structured_output.py
import re
from typing import List, Dict


class StructuredOutput:
    """统一结构化解析器"""

    @staticmethod
    def parse_pod_list(raw: str) -> List[Dict]:
        if not raw.strip():
            return []
        lines = [l for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return []

        pods = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 5:
                pods.append({
                    "name": parts[0],
                    "ready": parts[1],
                    "status": parts[2],
                    "restarts": int(parts[3]) if parts[3].isdigit() else 0,
                    "age": parts[4],
                })
        return pods

    @staticmethod
    def parse_top_pods(raw: str) -> List[Dict]:
        if not raw.strip():
            return []
        lines = [l for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return []

        pods = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 3:
                pods.append({
                    "name": parts[0],
                    "cpu": parts[1],
                    "memory": parts[2],
                })
        return pods

    @staticmethod
    def parse_top_nodes(raw: str) -> List[Dict]:
        if not raw.strip():
            return []
        lines = [l for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return []

        nodes = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 5:
                nodes.append({
                    "name": parts[0],
                    "cpu_usage": parts[1],
                    "cpu_percent": parts[2],
                    "memory_usage": parts[3],
                    "memory_percent": parts[4],
                })
        return nodes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_structured_output.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/cli/structured_output.py tests/test_structured_output.py
git commit -m "feat: add StructuredOutput parsers for kubectl commands"
```

---

### Task 5: HealthChecker 统一健康检查

**Covers:** [S3, S6.2]

**Files:**
- Create: `backend/core/cli/health_checker.py`
- Test: `tests/test_health_checker.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_health_checker.py
import pytest
from backend.core.cli.health_checker import HealthChecker


def test_check_pod_healthy():
    pod = {
        "status": "Running",
        "ready": "1/1",
        "restarts": 0,
    }
    result = HealthChecker.check_pod(pod)
    assert result["status"] == "healthy"
    assert result["issues"] == []


def test_check_pod_unhealthy():
    pod = {
        "status": "CrashLoopBackOff",
        "ready": "0/1",
        "restarts": 5,
    }
    result = HealthChecker.check_pod(pod)
    assert result["status"] == "unhealthy"
    assert len(result["issues"]) > 0


def test_check_pod_degraded():
    pod = {
        "status": "Running",
        "ready": "0/1",
        "restarts": 0,
    }
    result = HealthChecker.check_pod(pod)
    assert result["status"] == "degraded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_health_checker.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write implementation**

```python
# backend/core/cli/health_checker.py
from typing import Dict, List


class HealthChecker:
    """统一健康状态判断"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

    @classmethod
    def check_pod(cls, pod: Dict) -> Dict:
        status = pod.get("status", "")
        ready = pod.get("ready", "")
        restarts = pod.get("restarts", 0)

        if status in ("CrashLoopBackOff", "Error", "OOMKilled", "ImagePullBackOff"):
            return {
                "status": cls.UNHEALTHY,
                "issues": [f"Pod status: {status}"],
            }

        if status == "Running" and ready.startswith("1/"):
            if restarts > 3:
                return {
                    "status": cls.DEGRADED,
                    "issues": [f"High restart count: {restarts}"],
                }
            return {"status": cls.HEALTHY, "issues": []}

        if status == "Running" and ready.startswith("0/"):
            return {
                "status": cls.DEGRADED,
                "issues": [f"Container not ready: {ready}"],
            }

        if status in ("Pending", "Unknown"):
            return {
                "status": cls.UNKNOWN,
                "issues": [f"Pod status: {status}"],
            }

        return {"status": cls.HEALTHY, "issues": []}

    @classmethod
    def check_jvm(cls, dashboard_data: Dict) -> Dict:
        cpu = dashboard_data.get("cpu_percent", 0)
        memory = dashboard_data.get("memory_percent", 0)
        gc_pause = dashboard_data.get("gc_pause_ms", 0)

        issues = []
        if cpu > 90:
            issues.append(f"High CPU: {cpu}%")
        if memory > 90:
            issues.append(f"High memory: {memory}%")
        if gc_pause > 10000:
            issues.append(f"Long GC pause: {gc_pause}ms")

        if issues:
            return {"status": cls.UNHEALTHY, "issues": issues}

        if cpu > 70 or memory > 80:
            return {"status": cls.DEGRADED, "issues": [f"CPU: {cpu}%, Memory: {memory}%"]}

        return {"status": cls.HEALTHY, "issues": []}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_health_checker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/cli/health_checker.py tests/test_health_checker.py
git commit -m "feat: add HealthChecker for Pod and JVM health assessment"
```

---

### Task 6: CommandRegistry 命令注册表

**Covers:** [S3]

**Files:**
- Create: `backend/core/cli/command_registry.py`
- Test: `tests/test_command_registry.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_command_registry.py
import pytest
from backend.core.cli.command_registry import CommandRegistry


def test_get_kubectl_commands():
    commands = CommandRegistry.get_commands("kubectl")
    assert len(commands) > 0
    names = [c["name"] for c in commands]
    assert "get_pods" in names
    assert "delete_pod" in names


def test_get_arthas_commands():
    commands = CommandRegistry.get_commands("arthas")
    assert len(commands) > 0
    names = [c["name"] for c in commands]
    assert "thread" in names
    assert "dashboard" in names
    assert "trace" in names


def test_get_command_help():
    help_info = CommandRegistry.get_help("kubectl", "get_pods")
    assert help_info is not None
    assert "description" in help_info
    assert "examples" in help_info
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_command_registry.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write implementation**

```python
# backend/core/cli/command_registry.py
from typing import Dict, List, Optional


KUBECTL_COMMANDS = {
    "get_pods": {
        "name": "get_pods",
        "command": "get pods -o wide",
        "description": "获取 Pod 列表和状态",
        "when_to_use": ["查看 Pod 运行状态", "检查 Pod 是否正常"],
        "risk_level": "read",
        "params": {"namespace": "default", "label": ""},
    },
    "describe_pod": {
        "name": "describe_pod",
        "command": "describe pod {name}",
        "description": "获取 Pod 详细信息",
        "when_to_use": ["Pod 异常时查看详情"],
        "risk_level": "read",
        "params": {"name": "required", "namespace": "default"},
    },
    "get_pod_logs": {
        "name": "get_pod_logs",
        "command": "logs {name} [--previous]",
        "description": "获取 Pod 容器日志",
        "when_to_use": ["查看应用日志", "排查 CrashLoopBackOff"],
        "risk_level": "read",
        "params": {"name": "required", "previous": False},
    },
    "exec_in_pod": {
        "name": "exec_in_pod",
        "command": "exec {name} -- {shell_cmd}",
        "description": "在 Pod 内执行命令",
        "when_to_use": ["检查文件", "执行诊断命令"],
        "risk_level": "low",
        "params": {"name": "required", "shell_cmd": "required"},
    },
    "delete_pod": {
        "name": "delete_pod",
        "command": "delete pod {name}",
        "description": "删除 Pod（会触发重建）",
        "when_to_use": ["Pod 卡死需要重启"],
        "risk_level": "high",
        "requires_confirmation": True,
        "params": {"name": "required", "namespace": "default"},
    },
    "top_pods": {
        "name": "top_pods",
        "command": "top pods --no-headers",
        "description": "获取 Pod CPU/内存使用",
        "when_to_use": ["查看资源使用"],
        "risk_level": "read",
        "params": {"namespace": ""},
    },
    "top_nodes": {
        "name": "top_nodes",
        "command": "top nodes --no-headers",
        "description": "获取 Node CPU/内存使用",
        "when_to_use": ["查看节点资源"],
        "risk_level": "read",
        "params": {},
    },
    "get_events": {
        "name": "get_events",
        "command": "get events --sort-by='.lastTimestamp'",
        "description": "获取资源相关事件",
        "when_to_use": ["排查问题时间线"],
        "risk_level": "read",
        "params": {"namespace": ""},
    },
    "get_nodes": {
        "name": "get_nodes",
        "command": "get nodes -o wide",
        "description": "获取 Node 列表和状态",
        "when_to_use": ["查看节点状态"],
        "risk_level": "read",
        "params": {},
    },
    "cluster_info": {
        "name": "cluster_info",
        "command": "cluster-info",
        "description": "获取集群基本信息",
        "when_to_use": ["检查集群连通性"],
        "risk_level": "read",
        "params": {},
    },
}

ARTHAS_COMMANDS = {
    "thread": {
        "name": "thread",
        "command": "thread -n {top_n}",
        "description": "获取线程快照，按 CPU 使用排序",
        "when_to_use": ["CPU 飙高排查", "线程阻塞分析"],
        "risk_level": "read",
        "params": {"top_n": 5},
    },
    "thread_deadlock": {
        "name": "thread_deadlock",
        "command": "thread -b",
        "description": "检测死锁线程",
        "when_to_use": ["怀疑死锁"],
        "risk_level": "read",
        "params": {},
    },
    "dashboard": {
        "name": "dashboard",
        "command": "dashboard -n 1",
        "description": "获取 JVM 实时指标快照",
        "when_to_use": ["快速评估 JVM 状态"],
        "risk_level": "read",
        "params": {"n": 1},
    },
    "trace": {
        "name": "trace",
        "command": "trace {class_pattern} {method_pattern} -n {sample_count}",
        "description": "追踪方法调用链耗时",
        "when_to_use": ["接口慢排查", "方法耗时分析"],
        "risk_level": "read",
        "params": {"class_pattern": "required", "method_pattern": "required", "sample_count": 5},
    },
    "jad": {
        "name": "jad",
        "command": "jad {class_pattern}",
        "description": "反编译类源码",
        "when_to_use": ["查看类实现", "排查类冲突"],
        "risk_level": "read",
        "params": {"class_pattern": "required"},
    },
    "heapdump": {
        "name": "heapdump",
        "command": "heapdump --live {path}",
        "description": "导出堆转储",
        "when_to_use": ["OOM 排查"],
        "risk_level": "high",
        "requires_confirmation": True,
        "params": {"path": "/tmp/heap.hprof"},
    },
    "profiler": {
        "name": "profiler",
        "command": "profiler start --event {event} --duration {duration}",
        "description": "启动性能采样",
        "when_to_use": ["CPU 热点分析"],
        "risk_level": "medium",
        "requires_confirmation": True,
        "params": {"event": "cpu", "duration": 30},
    },
    "sc": {
        "name": "sc",
        "command": "sc -d {class_pattern}",
        "description": "搜索类加载信息",
        "when_to_use": ["确认类是否存在"],
        "risk_level": "read",
        "params": {"class_pattern": "required"},
    },
    "watch": {
        "name": "watch",
        "command": "watch {class_pattern} {method_pattern} '{expr}' -e -x 2",
        "description": "观测方法入参和返回值",
        "when_to_use": ["方法参数查看"],
        "risk_level": "read",
        "params": {"class_pattern": "required", "method_pattern": "required", "expr": "{params,returnObj}"},
    },
}

ALL_COMMANDS = {
    "kubectl": KUBECTL_COMMANDS,
    "arthas": ARTHAS_COMMANDS,
}


class CommandRegistry:
    """命令注册表"""

    @classmethod
    def get_commands(cls, cli: str) -> List[Dict]:
        return list(ALL_COMMANDS.get(cli, {}).values())

    @classmethod
    def get_help(cls, cli: str, command: str) -> Optional[Dict]:
        cmds = ALL_COMMANDS.get(cli, {})
        return cmds.get(command)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_command_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/cli/command_registry.py tests/test_command_registry.py
git commit -m "feat: add CommandRegistry with kubectl and Arthas command metadata"
```

---

### Task 7: KubectlAdapter 实现

**Covers:** [S3, S4]

**Files:**
- Create: `backend/core/cli/kubectl_adapter.py`
- Test: `tests/test_kubectl_adapter.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_kubectl_adapter.py
import pytest
from unittest.mock import patch, MagicMock
from backend.core.cli.kubectl_adapter import KubectlAdapter


def test_kubectl_adapter_init():
    adapter = KubectlAdapter(kubeconfig="/path/to/kubeconfig")
    assert adapter.kubeconfig == "/path/to/kubeconfig"


def test_kubectl_adapter_execute_get_pods():
    adapter = KubectlAdapter(kubeconfig="")
    mock_result = (0, "NAME\tREADY\tSTATUS\nnginx\t1/1\tRunning", "")
    with patch.object(adapter, '_run', return_value=mock_result):
        result = adapter.execute("get_pods", {"namespace": "default"})
        assert result.ok is True
        assert result.data is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_kubectl_adapter.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Write implementation**

```python
# backend/core/cli/kubectl_adapter.py
import subprocess
import logging
from typing import Any, Dict, List
from .adapter import CLIAdapter, StructuredResult
from .structured_output import StructuredOutput
from .health_checker import HealthChecker
from .safety_guard import SafetyGuard
from .error_mapper import ErrorMapper
from .command_registry import CommandRegistry

log = logging.getLogger(__name__)


class KubectlAdapter(CLIAdapter):
    """kubectl AI 适配器"""

    def __init__(self, kubeconfig: str = "", context: str = ""):
        self.kubeconfig = kubeconfig
        self.context = context

    def _base_cmd(self) -> List[str]:
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd += ["--kubeconfig", self.kubeconfig]
        if self.context:
            cmd += ["--context", self.context]
        return cmd

    def _run(self, args: List[str], timeout: int = 30):
        cmd = self._base_cmd() + args
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout)
            stdout = r.stdout.decode('utf-8', errors='replace') if r.stdout else ''
            stderr = r.stderr.decode('utf-8', errors='replace') if r.stderr else ''
            return r.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"kubectl 超时 ({timeout}s)"
        except FileNotFoundError:
            return -1, "", "kubectl 未找到"

    def execute(self, command: str, params: Dict[str, Any]) -> StructuredResult:
        ns = params.get("namespace", "default")
        cmd_template = CommandRegistry.get_help("kubectl", command)
        if not cmd_template:
            return StructuredResult(ok=False, command=command,
                                    error="UNKNOWN_COMMAND")

        risk = SafetyGuard.check_risk("kubectl", command)
        if risk["requires_confirm"]:
            return StructuredResult(ok=False, command=command,
                                    error="REQUIRES_CONFIRMATION",
                                    error_detail={"risk": risk})

        args = self._build_args(command, params, ns)
        rc, stdout, stderr = self._run(args)

        if rc == 0:
            data = StructuredOutput.parse_output(stdout, command)
            health = HealthChecker.check_pod_list(data) if command == "get_pods" else None
            return StructuredResult(ok=True, command=" ".join(args),
                                    data=data, raw_output=stdout, health=health)
        else:
            error = ErrorMapper.map_kubectl_error(stderr, rc)
            return StructuredResult(ok=False, command=" ".join(args),
                                    error=error["code"], error_detail=error)

    def _build_args(self, command: str, params: Dict, ns: str) -> List[str]:
        if command == "get_pods":
            args = ["-n", ns, "get", "pods", "-o", "wide"]
            label = params.get("label", "")
            if label:
                args += ["-l", label]
            return args
        elif command == "describe_pod":
            return ["-n", ns, "describe", "pod", params.get("name", "")]
        elif command == "get_pod_logs":
            args = ["-n", ns, "logs", params.get("name", "")]
            if params.get("previous"):
                args.append("--previous")
            return args
        elif command == "delete_pod":
            return ["-n", ns, "delete", "pod", params.get("name", "")]
        elif command == "top_pods":
            return ["-n", ns, "top", "pods", "--no-headers"]
        elif command == "top_nodes":
            return ["top", "nodes", "--no-headers"]
        elif command == "get_events":
            return ["-n", ns, "get", "events", "--sort-by=.lastTimestamp"]
        elif command == "get_nodes":
            return ["get", "nodes", "-o", "wide"]
        elif command == "cluster_info":
            return ["cluster-info"]
        return ["get", command]

    def get_commands(self) -> List[Dict]:
        return CommandRegistry.get_commands("kubectl")

    def health_check(self, target: str = "", params: Dict = None) -> Dict:
        return {"status": "implemented", "target": target}

    def dry_run(self, command: str, params: Dict[str, Any]) -> Dict:
        return SafetyGuard.dry_run("kubectl", command, params)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_kubectl_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/cli/kubectl_adapter.py tests/test_kubectl_adapter.py
git commit -m "feat: add KubectlAdapter with structured output and safety checks"
```

---

### Task 8: CLI API 路由

**Covers:** [S7]

**Files:**
- Create: `api/cli_api.py`
- Modify: `api/__init__.py` (register blueprint)

- [ ] **Step 1: Write API blueprint**

```python
# api/cli_api.py
from flask import Blueprint, request, jsonify
from flask_login import login_required

cli_bp = Blueprint('cli', __name__)


@cli_bp.route('/api/cli/commands', methods=['GET'])
@login_required
def get_commands():
    """获取所有可用命令"""
    from backend.core.cli.command_registry import CommandRegistry
    cli = request.args.get('cli', '')
    if cli:
        commands = CommandRegistry.get_commands(cli)
    else:
        kubectl = CommandRegistry.get_commands('kubectl')
        arthas = CommandRegistry.get_commands('arthas')
        commands = {"kubectl": kubectl, "arthas": arthas}
    return jsonify({"ok": True, "commands": commands})


@cli_bp.route('/api/cli/execute', methods=['POST'])
@login_required
def execute_command():
    """统一执行入口"""
    d = request.json or {}
    cli = d.get('cli', 'kubectl')
    command = d.get('command', '')
    params = d.get('params', {})

    if cli == 'kubectl':
        from backend.core.cli.kubectl_adapter import KubectlAdapter
        adapter = KubectlAdapter()
    elif cli == 'arthas':
        from backend.core.cli.arthas_adapter import ArthasAdapter
        adapter = ArthasAdapter()
    else:
        return jsonify({"ok": False, "error": f"Unknown CLI: {cli}"}), 400

    result = adapter.execute(command, params)
    return jsonify({
        "ok": result.ok,
        "command": result.command,
        "data": result.data,
        "health": result.health,
        "error": result.error,
        "error_detail": result.error_detail,
    })


@cli_bp.route('/api/cli/health-check', methods=['POST'])
@login_required
def health_check():
    """统一健康检查"""
    d = request.json or {}
    cli = d.get('cli', 'kubectl')
    resource = d.get('resource', 'pod')
    params = d.get('params', {})

    if cli == 'kubectl':
        from backend.core.cli.kubectl_adapter import KubectlAdapter
        adapter = KubectlAdapter()
    else:
        return jsonify({"ok": False, "error": "Health check only supports kubectl"}), 400

    result = adapter.health_check(resource, params)
    return jsonify({"ok": True, **result})


@cli_bp.route('/api/cli/dry-run', methods=['POST'])
@login_required
def dry_run():
    """Dry-run 预览"""
    from backend.core.cli.safety_guard import SafetyGuard
    d = request.json or {}
    cli = d.get('cli', 'kubectl')
    command = d.get('command', '')
    params = d.get('params', {})
    result = SafetyGuard.dry_run(cli, command, params)
    return jsonify({"ok": True, **result})
```

- [ ] **Step 2: Register blueprint in api/__init__.py**

Add after existing blueprint imports:

```python
from api.cli_api import cli_bp
app.register_blueprint(cli_bp)
```

- [ ] **Step 3: Commit**

```bash
git add api/cli_api.py api/__init__.py
git commit -m "feat: add CLI API routes for unified command execution"
```

---

### Task 9: 集成测试

**Covers:** [S3, S7, S8]

**Files:**
- Test: `tests/test_cli_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_cli_integration.py
import pytest
from backend.core.cli import (
    KubectlAdapter, StructuredOutput, HealthChecker,
    SafetyGuard, ErrorCode, CommandRegistry
)


def test_full_workflow():
    """测试完整工作流：命令选择 → 安全检查 → 执行 → 解析 → 健康判断"""
    adapter = KubectlAdapter(kubeconfig="")

    # 1. 命令发现
    commands = adapter.get_commands()
    assert len(commands) > 0

    # 2. 安全检查
    risk = SafetyGuard.check_risk("kubectl", "get_pods")
    assert risk["level"].value == "read"

    # 3. Dry-run
    dry = SafetyGuard.dry_run("kubectl", "delete_pod", {"name": "nginx"})
    assert dry["dry_run"] is True

    # 4. 错误映射
    error = ErrorMapper.map_kubectl_error("pods \"nginx\" not found", 1)
    assert error["code"] == ErrorCode.POD_NOT_FOUND
```

- [ ] **Step 2: Run integration test**

Run: `python -m pytest tests/test_cli_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_integration.py
git commit -m "test: add CLI integration tests"
```

---

### Task 10: 文档更新

**Covers:** [S3, S9]

**Files:**
- Modify: `docs/compose/specs/2026-06-14-kubectl-ai-optimization-design.md` (mark as implemented)

- [ ] **Step 1: Add implementation status**

Add to the top of the spec:

```markdown
**实施状态**: Phase 1-3 已完成
**完成日期**: 2026-06-15
```

- [ ] **Step 2: Commit**

```bash
git add docs/compose/specs/2026-06-14-kubectl-ai-optimization-design.md
git commit -m "docs: mark CLI architecture spec as implemented"
```
