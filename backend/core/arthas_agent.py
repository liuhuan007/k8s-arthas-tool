"""
Arthas Agent 管理 - Pod 内 Arthas 启动/检测
"""
import logging
import time
from typing import List, Tuple, Optional

log = logging.getLogger(__name__)

# 默认配置
ARTHAS_DEFAULT_JAR = "/app/arthas/arthas-boot.jar"
ARTHAS_HTTP_PORT = 8563
ARTHAS_TELNET_PORT = 3658


class ArthasAgentManager:
    """
    负责在 Pod 内启动 / 检测 Arthas agent。
    仅与 Pod 内部交互，不感知本地端口。
    """

    def __init__(self, executor, target):
        self.ex = executor
        self.t = target
        self._pid: Optional[int] = None

    def _exec(self, cmd: str, timeout: int = 30):
        return self.ex.exec_pod(
            self.t.namespace, self.t.pod_name, self.t.container, cmd, timeout)

    # ── Java PID discovery ────────────────────────────────────────────────────

    def find_java_pid(self, force: bool = False) -> Optional[int]:
        if self._pid and not force:
            return self._pid

        rc, out, _ = self._exec(
            "jps -l 2>/dev/null || ps -ef 2>/dev/null | grep java | grep -v grep")
        if rc != 0 or not out.strip():
            return None

        skip_keywords = ["arthas", "arthas-boot", "Jps", "jps"]
        for line in out.strip().splitlines():
            parts = line.strip().split(None, 1)
            if not parts or not parts[0].isdigit():
                continue
            pid = int(parts[0])
            desc = parts[1].lower() if len(parts) > 1 else ""
            if any(k.lower() in desc for k in skip_keywords):
                continue
            self._pid = pid
            return pid
        return None

    # ── Arthas agent check / start ────────────────────────────────────────────

    def _http_reachable(self) -> bool:
        """Pod 内 Arthas HTTP 端口是否在响应"""
        rc, out, _ = self._exec(
            f"curl -sf --max-time 3 http://127.0.0.1:{self.t.arthas_http_port}/api "
            f"-o /dev/null -w '%{{http_code}}' 2>/dev/null",
            timeout=6,
        )
        return rc == 0 and out.strip() in ("200", "400", "404")

    def _find_arthas_pids(self) -> List[int]:
        """返回 Pod 内所有 arthas-boot 进程的 PID 列表"""
        rc, out, _ = self._exec(
            "ps -ef 2>/dev/null | grep -i 'arthas-boot\\|arthas.jar' | grep -v grep || true",
            timeout=8,
        )
        pids = []
        if rc == 0 and out.strip():
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    pids.append(int(parts[1]))
        return pids

    def _kill_stale_arthas(self, pids: List[int]) -> str:
        """清理残留 arthas-boot 进程"""
        if not pids:
            return ""
        pid_str = " ".join(str(p) for p in pids)
        self._exec(
            f"kill {pid_str} 2>/dev/null; sleep 1; "
            f"kill -9 {pid_str} 2>/dev/null; true",
            timeout=8,
        )
        log.info("Killed stale arthas pids: %s", pid_str)
        return f"已清理残留进程 {pid_str}"

    def _resolve_jar(self) -> bool:
        """确认 JAR 路径可用；找不到时按优先级探测备选路径"""
        rc, _, _ = self._exec(f"test -f '{self.t.arthas_jar}'", timeout=5)
        if rc == 0:
            return True
        for fallback in [
            "/app/arthas/arthas-boot.jar",
            "/opt/arthas/arthas-boot.jar",
            "/arthas/arthas-boot.jar",
            "/home/admin/arthas-boot.jar",
            "/root/arthas/arthas-boot.jar",
        ]:
            rc2, _, _ = self._exec(f"test -f '{fallback}'", timeout=5)
            if rc2 == 0:
                log.info("Auto-detected Arthas JAR: %s", fallback)
                self.t.arthas_jar = fallback
                return True
        log.warning("未找到 Arthas JAR: %s，请使用工具链分发", self.t.arthas_jar)
        return False

    def _detect_mcp_support(self, http_port: int) -> str:
        """检测当前 Arthas 是否支持 MCP，如果支持则返回启动参数"""
        # 简单策略：始终尝试启用 MCP 端点
        # Arthas < 4.1.8 会忽略未知 -D 参数，不会影响启动
        # Arthas >= 4.1.8 会自动在 HTTP 端口上暴露 /mcp 路径
        return f" -Darthas.mcpEndpoint=/mcp"

    def _check_mcp_available(self, http_port: int) -> bool:
        """检查 Pod 内 Arthas MCP 端点是否可用"""
        rc, out, _ = self._exec(
            f"curl -sf --max-time 3 http://127.0.0.1:{http_port}/mcp "
            f"-o /dev/null -w '%{{http_code}}' 2>/dev/null",
            timeout=6,
        )
        return rc == 0 and out.strip() in ("200", "400", "404")

    def ensure_agent_running(self) -> Tuple[bool, str]:
        """确保 Arthas agent 在 Pod 内运行"""
        port = self.t.arthas_http_port

        # 情况 A: HTTP 已响应，直接复用
        if self._http_reachable():
            log.info("Arthas HTTP already reachable on port %d — reusing", port)
            # 复用时也要获取 java_pid
            if not self._pid:
                self.find_java_pid()
            return True, f"Arthas 已在运行，直接复用 (port {port})"

        # 情况 B: HTTP 不通，先清理残留进程
        stale_pids = self._find_arthas_pids()
        cleanup_msg = ""
        if stale_pids:
            cleanup_msg = self._kill_stale_arthas(stale_pids)
            log.info(cleanup_msg)
            time.sleep(1)

        # 情况 C: 找目标 Java PID
        pid = self.find_java_pid()
        if not pid:
            return False, "未找到 Java 进程，请确认 JVM 已启动"

        # 情况 D: 确认 JAR
        if not self._resolve_jar():
            return False, (
                f"Arthas JAR 不存在: {self.t.arthas_jar}\n"
                "请在左侧配置正确路径，或在 Pod 内安装 Arthas:\n"
                "  curl -Lo /app/arthas/arthas-boot.jar "
                "https://arthas.aliyun.com/arthas-boot.jar"
            )

        # 情况 E: 启动
        # 检查是否支持 MCP（Arthas 4.1.8+），通过探测是否有 mcpEndpoint 配置项
        mcp_config = self._detect_mcp_support(port)
        start_cmd = (
            f"nohup java"
            f" -Darthas.httpPort={port}"
            f" -Darthas.telnetPort={self.t.arthas_telnet_port}"
            f" -Darthas.ip=127.0.0.1"
            f"{mcp_config}"
            f" -jar {self.t.arthas_jar}"
            f" {pid}"
            f" > /tmp/arthas_start.log 2>&1 </dev/null &"
            f" echo started_pid=$!"
        )
        rc_s, out_s, _ = self._exec(start_cmd, timeout=15)
        log.info("Arthas start: rc=%d pid=%d jar=%s out=%s cleanup=%s",
                 rc_s, pid, self.t.arthas_jar, out_s.strip(), cleanup_msg)

        # 轮询等待 HTTP 就绪（max 40s）
        for i in range(40):
            time.sleep(1)
            if self._http_reachable():
                msg = f"Arthas 启动成功 (target PID={pid}, 耗时 {i+1}s)"
                if cleanup_msg:
                    msg += f"  [{cleanup_msg}]"
                return True, msg

        _, log_tail, _ = self._exec(
            "tail -25 /tmp/arthas_start.log 2>/dev/null", timeout=5)
        return False, (
            f"Arthas 启动超时（40s）\n"
            f"JAR: {self.t.arthas_jar}  target PID: {pid}\n"
            f"启动日志:\n{log_tail[:600]}"
        )