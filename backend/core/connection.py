"""
Arthas 连接管理 - 整合 Agent、Port-Forward、HTTP Client

架构：
  PodConnection (基础层)
    └─ ArthasConnection (扩展层)
"""
import logging
import socket
import subprocess
import threading
import time
from typing import Optional, Tuple

log = logging.getLogger(__name__)

# 端口分配起始值
PF_BASE_PORT = 32000
PF_MAX_PORT = 32767  # IANA dynamic/private ports upper bound


class ArthasConnection:
    """
    管理单个 Pod 的完整 Arthas 连接:
      1. Pod 连接验证（PodConnection 能力）
      2. ArthasAgentManager → 确保 Pod 内 agent 运行
      3. kubectl port-forward → 本地端口
      4. ArthasHttpClient   → HTTP API 可用
    
    注意：
      为了保持向后兼容，ArthasConnection 不直接继承 PodConnection，
      而是组合使用 PodConnection 实例。
      这样可以在不破坏现有 API 的情况下实现双层连接架构。
    """

    _port_counter = PF_BASE_PORT
    _used_ports: set = set()
    _port_lock = threading.Lock()  # 端口分配线程安全锁

    def __init__(self, executor, target):
        from .arthas_agent import ArthasAgentManager
        from .arthas_client import ArthasHttpClient
        from .pod_connection import PodConnection

        self.executor = executor
        self.target = target
        
        # 创建底层 Pod 连接
        self.pod_conn = PodConnection(executor, target)
        
        # Arthas 相关组件
        self.agent_mgr = ArthasAgentManager(executor, target)
        self.client: Optional[ArthasHttpClient] = None
        self.http_client = None  # 兼容旧代码
        self._pf_proc: Optional[subprocess.Popen] = None
        self.local_port: int = 0
        self.java_pid: Optional[int] = None
        self.arthas_version: Optional[str] = None  # Arthas 版本号
        self.arthas_address: Optional[str] = None   # Arthas HTTP 地址
        
        # 连接状态标记
        self._pod_connected = False  # Pod 连接是否成功
        self._arthas_ready = False   # Arthas 是否就绪

    # ── Port allocation ────────────────────────────────────────────────────────

    @classmethod
    def _alloc_port(cls) -> int:
        """分配端口，线程安全，优先复用已释放的端口"""
        with cls._port_lock:
            for port in range(PF_BASE_PORT + 1, PF_MAX_PORT + 1):
                if port not in cls._used_ports:
                    cls._used_ports.add(port)
                    return port
        raise RuntimeError(f"Port range exhausted: {PF_MAX_PORT} maximum reached. "
                           "Restart service or increase PF_MAX_PORT.")

    @classmethod
    def _release_port(cls, port: int):
        """释放端口，允许后续复用"""
        with cls._port_lock:
            cls._used_ports.discard(port)

    # ── Port-forward helpers ───────────────────────────────────────────────────

    def _stop_port_forward(self):
        if self._pf_proc:
            proc = self._pf_proc
            self._pf_proc = None  # 先置空防止重入
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # 超时后强制杀死
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                    log.warning("port-forward process killed after timeout")
                except Exception as e:
                    log.warning("port-forward kill failed: %s", e)
            except Exception as e:
                log.warning("port-forward terminate failed: %s", e)

    def _start_port_forward(self) -> Tuple[bool, str]:
        self._stop_port_forward()
        self.local_port = self._alloc_port()
        self._pf_proc = self.executor.start_port_forward(
            self.target.namespace,
            self.target.pod_name,
            self.local_port,
            self.target.arthas_http_port,
        )

        # Wait for TCP port to accept connections (up to 15s)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.local_port), timeout=1):
                    return True, f"port-forward 就绪: 本地:{self.local_port} → Pod:{self.target.arthas_http_port}"
            except OSError:
                time.sleep(0.5)

        return False, f"port-forward 超时，本地端口 {self.local_port} 无法连接"

    # ── Public API ─────────────────────────────────────────────────────────────
    
    def connect_pod(self, timeout: int = 10) -> Tuple[bool, str]:
        """
        第一步：仅建立 Pod 连接（不启动 Arthas）
        
        返回:
            (success, message)
        """
        ok, msg = self.pod_conn.connect(timeout)
        if ok:
            self._pod_connected = True
        return ok, msg
    
    def connect_arthas(self, timeout: int = 30) -> Tuple[bool, str]:
        """
        第二步：启动 Arthas 诊断环境
        
        前提：Pod 连接已成功建立
        
        返回:
            (success, message)
        """
        if not self._pod_connected:
            return False, "Pod 连接未建立，请先调用 connect_pod()"
        
        # 短路：Arthas 已经就绪
        if self._arthas_ready and self.client and self.client.ping(retries=1, delay=0):
            log.info("Arthas already ready (port=%d) — reusing", self.local_port)
            if not self.arthas_version and hasattr(self.client, '_last_version') and self.client._last_version:
                self.arthas_version = self.client._last_version
            if not self.arthas_version:
                self._fetch_version()
            return True, f"Arthas 已就绪，复用 (port {self.local_port})"
        
        # 若 client 已失效但 port-forward 还在，先停掉
        if self._pf_proc:
            self._stop_port_forward()
            self.client = None
        
        # Step 1: 确保 agent 在 Pod 内运行
        ok, agent_msg = self.agent_mgr.ensure_agent_running()
        if not ok:
            return False, agent_msg
        self.java_pid = self.agent_mgr._pid
        log.info("Agent ready: %s", agent_msg)
        
        # Step 2: 建立 port-forward
        ok, pf_msg = self._start_port_forward()
        if not ok:
            return False, pf_msg
        log.info("Port-forward: %s", pf_msg)
        
        # Step 3: 等待 HTTP API 就绪
        from .arthas_client import ArthasHttpClient
        client = ArthasHttpClient(self.local_port)
        if client.ping(retries=8, delay=2.0):
            self.client = client
            self.http_client = client  # 兼容
            self.arthas_address = f"http://127.0.0.1:{self.local_port}"
            # Step 4: 获取 Arthas 版本信息（优先用 ping 缓存）
            if hasattr(client, '_last_version') and client._last_version:
                self.arthas_version = client._last_version
                log.info("Arthas version (from ping cache): %s", self.arthas_version)
            else:
                self._fetch_version()
            version_suffix = f"  Arthas {self.arthas_version}" if self.arthas_version else ""
            
            self._arthas_ready = True
            return True, f"Arthas 诊断环境就绪{version_suffix} (port {self.local_port}, pid {self.java_pid})"
        else:
            return False, "Arthas HTTP API 未响应"
    
    def connect(self, timeout: int = 30) -> Tuple[bool, str]:
        """
        建立完整的 Arthas 连接（向后兼容）
        
        内部调用：connect_pod() + connect_arthas()
        
        返回:
            (success, message)
        """
        # 第一步：Pod 连接
        ok, msg = self.connect_pod(timeout=10)
        if not ok:
            return False, msg
        
        # 第二步：Arthas 连接
        return self.connect_arthas(timeout=timeout - 10)

    def _fetch_version(self):
        """获取 Arthas 版本号"""
        if not self.client:
            return
        try:
            version = self.client.get_version(retries=2, delay=1.0)
            if version:
                self.arthas_version = version
                log.info("Arthas version: %s", version)
                return
            # 兜底：用 exec_once 手动解析
            resp = self.client.exec_once("version", timeout_ms=5000)
            if resp.get("state") in ("SUCCEEDED", "succeeded"):
                body = resp.get("body", {})
                # body 可能是 dict 或 JSON 字符串
                if isinstance(body, str):
                    try:
                        import json
                        body = json.loads(body)
                    except Exception:
                        body = {}
                if isinstance(body, dict):
                    for r in body.get("results", []):
                        v = r.get("version", "")
                        if v:
                            self.arthas_version = str(v)
                            log.info("Arthas version: %s", v)
                            return
                # 从 message 字段提取
                raw = str(resp.get("body", "")) + str(resp.get("message", ""))
                import re
                m = re.search(r'(\d+\.\d+\.\d+[\.\-\w]*)', raw)
                if m:
                    self.arthas_version = m.group(1)
                    log.info("Arthas version (from regex): %s", m.group(1))
        except Exception as e:
            log.debug("fetch version failed: %s", e)

    def is_alive(self) -> bool:
        """检查 Arthas 连接是否存活"""
        if not self._arthas_ready:
            return False
        if not self.client:
            return False
        return self.client.ping(retries=1, delay=0)
    
    def is_pod_alive(self) -> bool:
        """检查 Pod 连接是否存活"""
        return self.pod_conn.is_alive()

    def disconnect(self):
        """断开连接（同时断开 Pod 和 Arthas）"""
        # 断开 Arthas
        if self.local_port:
            self._release_port(self.local_port)
        self._stop_port_forward()
        self.client = None
        self.local_port = 0
        self._arthas_ready = False
        
        # 断开 Pod
        self.pod_conn.disconnect()
        self._pod_connected = False
    
    def disconnect_arthas(self):
        """仅断开 Arthas，保持 Pod 连接"""
        if self.local_port:
            self._release_port(self.local_port)
        self._stop_port_forward()
        self.client = None
        self.local_port = 0
        self._arthas_ready = False
        log.info("Arthas disconnected, Pod connection kept alive")
    
    # ── 属性代理（向后兼容）────────────────────────────────────────
    
    @property
    def runtime_info(self):
        """获取运行时信息（代理到 pod_conn）"""
        return self.pod_conn.runtime_info
    
    @property
    def is_java(self) -> bool:
        """是否为 Java 应用"""
        return self.pod_conn.is_java
    
    @property
    def pod_phase(self) -> str:
        """获取 Pod 状态"""
        return self.pod_conn.pod_phase