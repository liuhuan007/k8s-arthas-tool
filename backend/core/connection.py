"""
Arthas 连接管理 - 整合 Agent、Port-Forward、HTTP Client
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
      1. ArthasAgentManager → 确保 Pod 内 agent 运行
      2. kubectl port-forward → 本地端口
      3. ArthasHttpClient   → HTTP API 可用
    """

    _port_counter = PF_BASE_PORT
    _used_ports: set = set()
    _port_lock = threading.Lock()  # 端口分配线程安全锁

    def __init__(self, executor, target):
        from .arthas_agent import ArthasAgentManager
        from .arthas_client import ArthasHttpClient

        self.executor = executor
        self.target = target
        self.agent_mgr = ArthasAgentManager(executor, target)
        self.client: Optional[ArthasHttpClient] = None
        self.http_client = None  # 兼容旧代码
        self._pf_proc: Optional[subprocess.Popen] = None
        self.local_port: int = 0
        self.java_pid: Optional[int] = None
        self.arthas_version: Optional[str] = None  # Arthas 版本号
        self.arthas_address: Optional[str] = None   # Arthas HTTP 地址

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

    def connect(self) -> Tuple[bool, str]:
        """建立完整的 Arthas 连接，防止重复操作"""
        # 短路 1: 当前 client 仍然存活
        if self.client and self.client.ping(retries=1, delay=0):
            log.info("ArthasConnection already alive (port=%d) — reusing", self.local_port)
            # 尝试获取版本信息（如果尚未获取）
            if not self.arthas_version:
                self._fetch_version()
            return True, f"已连接，复用 (port {self.local_port})"

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
            # Step 4: 获取 Arthas 版本信息
            self._fetch_version()
            version_suffix = f"  Arthas {self.arthas_version}" if self.arthas_version else ""
            return True, f"连接成功 · {agent_msg} · {pf_msg}{version_suffix}"

        # 诊断：收集启动日志
        _, log_tail, _ = self.executor.exec_pod(
            self.target.namespace, self.target.pod_name, self.target.container,
            "tail -15 /tmp/arthas_start.log 2>/dev/null", timeout=5)
        self._stop_port_forward()
        return False, (
            f"port-forward TCP 就绪，但 Arthas HTTP API 未响应\n"
            f"可能原因: JVM attach 耗时长 / 端口冲突 / JVM 版本不兼容\n"
            f"启动日志:\n{log_tail[:400]}"
        )

    def _fetch_version(self):
        """获取 Arthas 版本号"""
        if not self.client:
            return
        try:
            resp = self.client.exec_once("version", timeout_ms=5000)
            if resp.get("state") in ("SUCCEEDED", "succeeded"):
                for r in resp.get("body", {}).get("results", []):
                    v = r.get("version", "")
                    if v:
                        self.arthas_version = v
                        log.info("Arthas version: %s", v)
                        return
            # 兜底：从 message 字段提取
            raw = str(resp.get("body", ""))
            import re
            m = re.search(r'(\d+\.\d+\.\d+[\.\-\w]*)', raw)
            if m:
                self.arthas_version = m.group(1)
        except Exception as e:
            log.debug("fetch version failed: %s", e)

    def is_alive(self) -> bool:
        if not self.client:
            return False
        return self.client.ping(retries=1, delay=0)

    def disconnect(self):
        if self.local_port:
            self._release_port(self.local_port)
        self._stop_port_forward()
        self.client = None
        self.local_port = 0