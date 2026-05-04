"""
Pod 连接管理 - 轻量级 Pod 连接（无需 Arthas）

提供基础的 Pod 访问能力：
  - Pod 状态检测
  - 权限验证
  - 运行时环境检测（Java/Node.js/Python/Go）
  - 文件操作
  - 日志查看
  - 命令执行

与 ArthasConnection 的关系：
  PodConnection 是基础层，ArthasConnection 继承此类并添加 Arthas 能力
"""
import logging
import re
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class RuntimeInfo:
    """运行时环境信息"""
    runtime_type: str  # java, node, python, go, unknown
    version: Optional[str] = None
    processes: List[Dict] = None
    
    def __post_init__(self):
        if self.processes is None:
            self.processes = []


class PodConnection:
    """
    轻量级 Pod 连接 - 仅需 kubectl 能力
    
    使用场景：
      - 查看 Pod 监控指标
      - 浏览/下载 Pod 内文件
      - 查看容器日志
      - 执行命令
      - 非 Java 应用的基础运维
    
    不依赖：
      - Arthas Agent
      - Port-Forward
      - Java 进程
    """
    
    def __init__(self, executor, target):
        """
        初始化 Pod 连接
        
        Args:
            executor: KubectlExecutor 实例
            target: PodTarget 实例
        """
        self.executor = executor
        self.target = target
        self._healthy = False
        self._runtime_info: Optional[RuntimeInfo] = None
        self._pod_phase: str = ""
    
    # ── 连接生命周期 ─────────────────────────────────────────────
    
    def connect(self, timeout: int = 10) -> Tuple[bool, str]:
        """
        建立 Pod 连接
        
        流程：
          1. 验证 Pod 存在且状态正常
          2. 检查 exec 权限
          3. 检测运行时环境
        
        Returns:
            (success: bool, message: str)
        """
        try:
            # Step 1: 检查 Pod 状态
            ok, msg = self._check_pod_status(timeout)
            if not ok:
                return False, msg
            
            # Step 2: 验证 exec 权限
            ok, msg = self._check_exec_permission(timeout)
            if not ok:
                return False, msg
            
            # Step 3: 检测运行时环境
            self._runtime_info = self._detect_runtime(timeout)
            
            self._healthy = True
            runtime_desc = self._runtime_info.runtime_type if self._runtime_info else "unknown"
            version = self._runtime_info.version if self._runtime_info else ""
            
            msg = f"Pod 连接成功"
            if version:
                msg += f" ({runtime_desc} {version})"
            else:
                msg += f" ({runtime_desc})"
            
            log.info("Pod connected: %s/%s - %s", 
                    self.target.namespace, self.target.pod_name, msg)
            return True, msg
            
        except Exception as e:
            log.error("Pod connection failed: %s", e, exc_info=True)
            return False, f"连接失败: {str(e)}"
    
    def disconnect(self):
        """断开 Pod 连接"""
        self._healthy = False
        self._runtime_info = None
        self._pod_phase = ""
        log.info("Pod disconnected: %s/%s", 
                self.target.namespace, self.target.pod_name)
    
    def is_alive(self) -> bool:
        """检查连接是否存活"""
        if not self._healthy:
            return False
        
        # 快速检查 Pod 状态
        try:
            phase = self._get_pod_phase(timeout=5)
            return phase == "Running"
        except Exception:
            return False
    
    # ── Pod 状态检测 ─────────────────────────────────────────────
    
    def _check_pod_status(self, timeout: int = 10) -> Tuple[bool, str]:
        """检查 Pod 是否存在且状态正常"""
        phase = self._get_pod_phase(timeout)
        
        if not phase:
            return False, "Pod 不存在或无法访问"
        
        self._pod_phase = phase
        
        if phase == "Running":
            return True, "Pod 状态正常"
        elif phase in ("Pending", "ContainerCreating"):
            return False, f"Pod 正在启动中 (状态: {phase})"
        elif phase == "CrashLoopBackOff":
            return False, "Pod 启动失败 (CrashLoopBackOff)"
        elif phase == "Error":
            return False, "Pod 状态异常 (Error)"
        elif phase == "Terminating":
            return False, "Pod 正在终止"
        else:
            return False, f"Pod 状态异常: {phase}"
    
    def _get_pod_phase(self, timeout: int = 5) -> str:
        """获取 Pod 当前状态"""
        rc, out, _ = self.executor._run(
            ["get", "pod", self.target.pod_name, "-n", self.target.namespace,
             "-o", "jsonpath={.status.phase}"],
            timeout=timeout
        )
        return out.strip() if rc == 0 else ""
    
    # ── 权限验证 ─────────────────────────────────────────────────
    
    def _check_exec_permission(self, timeout: int = 5) -> Tuple[bool, str]:
        """验证是否有 exec 权限"""
        # 尝试执行简单命令验证权限
        rc, out, err = self.executor.exec_pod(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            "echo 'exec_ok'",
            timeout=timeout
        )
        
        if rc != 0:
            if "forbidden" in err.lower() or "unauthorized" in err.lower():
                return False, "缺少 pods/exec 权限，请联系管理员配置 RBAC"
            return False, f"exec 权限验证失败: {err or out}"
        
        if "exec_ok" not in out:
            return False, "exec 权限验证异常"
        
        return True, "exec 权限验证通过"
    
    # ── 运行时环境检测 ───────────────────────────────────────────
    
    def _detect_runtime(self, timeout: int = 10) -> RuntimeInfo:
        """
        检测 Pod 内的运行时环境
        
        检测顺序：
          1. Java 进程 (jps -l)
          2. Node.js 进程 (node --version)
          3. Python 进程 (python --version)
          4. Go 进程 (特征识别)
        """
        # 1. 检测 Java (优先)
        log.info("[_detect_runtime] 开始检测 Java...")
        java_info = self._detect_java(min(timeout, 5))
        if java_info:
            log.info("[_detect_runtime] 检测到 Java: %s", java_info.runtime_type)
            return java_info
        
        # 2. 检测 Node.js
        log.info("[_detect_runtime] 开始检测 Node.js...")
        node_info = self._detect_node(min(timeout, 3))
        if node_info:
            log.info("[_detect_runtime] 检测到 Node.js: %s", node_info.runtime_type)
            return node_info
        
        # 3. 检测 Python
        log.info("[_detect_runtime] 开始检测 Python...")
        python_info = self._detect_python(min(timeout, 3))
        if python_info:
            log.info("[_detect_runtime] 检测到 Python: %s", python_info.runtime_type)
            return python_info
        
        # 4. 检测 Go
        log.info("[_detect_runtime] 开始检测 Go...")
        go_info = self._detect_go(min(timeout, 3))
        if go_info:
            log.info("[_detect_runtime] 检测到 Go: %s", go_info.runtime_type)
            return go_info
        
        log.info("[_detect_runtime] 未检测到已知运行时,返回 unknown")
        # 未知运行时
        return RuntimeInfo(runtime_type="unknown")
    
    def _detect_java(self, timeout: int = 8) -> Optional[RuntimeInfo]:
        """检测 Java 运行时"""
        rc, out, _ = self.executor.exec_pod(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            "jps -l 2>/dev/null || ps -ef 2>/dev/null | grep java | grep -v grep",
            timeout=timeout
        )
        
        if rc != 0 or not out.strip():
            return None
        
        # 解析 Java 进程
        java_processes = []
        skip_keywords = {"arthas", "arthas-boot", "as-boot", "jps", "sun.tools.jps"}
        
        for line in out.strip().splitlines():
            parts = line.strip().split(None, 1)
            if not parts or not parts[0].isdigit():
                continue
            
            pid = parts[0]
            desc = parts[1] if len(parts) > 1 else "java"
            
            # 过滤 Arthas 相关进程
            if any(kw in desc.lower() for kw in skip_keywords):
                continue
            
            java_processes.append({"pid": pid, "description": desc})
        
        if not java_processes:
            return None
        
        # 获取 Java 版本
        version = self._get_java_version(timeout)
        
        runtime_info = RuntimeInfo(
            runtime_type="java",
            version=version,
            processes=java_processes
        )
        
        log.info("[_detect_java] Created RuntimeInfo: runtime_type=%s, version=%s, processes=%d",
                runtime_info.runtime_type, runtime_info.version, len(runtime_info.processes))
        
        return runtime_info
    
    def _get_java_version(self, timeout: int = 5) -> Optional[str]:
        """获取 Java 版本"""
        rc, out, _ = self.executor.exec_pod(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            "java -version 2>&1 | head -1",
            timeout=timeout
        )
        
        if rc == 0 and out:
            # 解析版本字符串: openjdk version "11.0.11" 2021-04-20
            match = re.search(r'version\s+"([^"]+)"', out)
            if match:
                return match.group(1)
        
        return None
    
    def _detect_node(self, timeout: int = 5) -> Optional[RuntimeInfo]:
        """检测 Node.js 运行时"""
        rc, out, _ = self.executor.exec_pod(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            "node --version 2>/dev/null",
            timeout=timeout
        )
        
        if rc == 0 and out.strip():
            version = out.strip()  # v14.17.0
            return RuntimeInfo(runtime_type="node", version=version)
        
        # 备选：检查进程
        rc, out, _ = self.executor.exec_pod(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            "ps -ef 2>/dev/null | grep node | grep -v grep | head -5",
            timeout=timeout
        )
        
        if rc == 0 and out.strip():
            processes = []
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    processes.append({"pid": parts[1], "description": " ".join(parts[2:])})
            
            if processes:
                return RuntimeInfo(runtime_type="node", processes=processes)
        
        return None
    
    def _detect_python(self, timeout: int = 5) -> Optional[RuntimeInfo]:
        """检测 Python 运行时"""
        for cmd in ["python3 --version 2>&1", "python --version 2>&1"]:
            rc, out, _ = self.executor.exec_pod(
                self.target.namespace,
                self.target.pod_name,
                self.target.container,
                cmd,
                timeout=timeout
            )
            
            if rc == 0 and out.strip():
                # Python 3.8.10
                version = out.strip().split()[-1] if out.strip() else None
                return RuntimeInfo(runtime_type="python", version=version)
        
        # 备选：检查进程
        rc, out, _ = self.executor.exec_pod(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            "ps -ef 2>/dev/null | grep python | grep -v grep | head -5",
            timeout=timeout
        )
        
        if rc == 0 and out.strip():
            processes = []
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    processes.append({"pid": parts[1], "description": " ".join(parts[2:])})
            
            if processes:
                return RuntimeInfo(runtime_type="python", processes=processes)
        
        return None
    
    def _detect_go(self, timeout: int = 5) -> Optional[RuntimeInfo]:
        """检测 Go 运行时（基于进程名特征）"""
        rc, out, _ = self.executor.exec_pod(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            "ps -ef 2>/dev/null | grep -E '/[^/]+$' | grep -v grep | head -10",
            timeout=timeout
        )
        
        if rc != 0 or not out.strip():
            return None
        
        # Go 编译的二进制通常没有明显特征，只能通过排除法
        processes = []
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                cmd = " ".join(parts[2:])
                # 排除已知运行时
                if any(x in cmd.lower() for x in ['java', 'node', 'python', 'ruby']):
                    continue
                processes.append({"pid": parts[1], "description": cmd})
        
        if processes:
            return RuntimeInfo(runtime_type="go", processes=processes)
        
        return None
    
    # ── 属性访问 ─────────────────────────────────────────────────
    
    @property
    def runtime_info(self) -> Optional[RuntimeInfo]:
        """获取运行时信息"""
        return self._runtime_info
    
    @property
    def pod_phase(self) -> str:
        """获取 Pod 状态"""
        return self._pod_phase
    
    @property
    def is_java(self) -> bool:
        """是否为 Java 应用"""
        return self._runtime_info and self._runtime_info.runtime_type == "java"
    
    @property
    def has_java_process(self) -> bool:
        """是否有 Java 进程"""
        return self.is_java and len(self._runtime_info.processes) > 0
    
    # ── 工具方法 ─────────────────────────────────────────────────
    
    def exec_command(self, command: str, timeout: int = 30) -> Tuple[int, str, str]:
        """
        在 Pod 内执行命令
        
        Args:
            command: 要执行的命令
            timeout: 超时时间（秒）
        
        Returns:
            (return_code, stdout, stderr)
        """
        if not self._healthy:
            raise RuntimeError("Pod 未连接")
        
        return self.executor.exec_pod(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            command,
            timeout=timeout
        )
    
    def get_logs(self, tail: int = 200, since: str = "") -> str:
        """
        获取容器日志
        
        Args:
            tail: 最后 N 行
            since: 时间范围 (e.g., "1h", "30m")
        
        Returns:
            日志内容
        """
        if not self._healthy:
            raise RuntimeError("Pod 未连接")
        
        return self.executor.get_logs(
            self.target.namespace,
            self.target.pod_name,
            self.target.container,
            tail=tail,
            since=since
        )
    
    def __repr__(self):
        status = "connected" if self._healthy else "disconnected"
        runtime = self._runtime_info.runtime_type if self._runtime_info else "unknown"
        return (f"PodConnection({self.target.cluster_name}/"
                f"{self.target.namespace}/{self.target.pod_name}, "
                f"status={status}, runtime={runtime})")
