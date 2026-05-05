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
        """查找 Java 进程 PID
        
        ✅ 关键修复: 增加 PID 验证,避免返回已失效的 PID
        """
        if self._pid and not force:
            # ✅ 验证 PID 是否还在运行
            rc, _, _ = self._exec(f"kill -0 {self._pid} 2>/dev/null", timeout=3)
            if rc == 0:
                return self._pid
            else:
                log.warning("[PID Cache] Cached PID %d is stale, will rediscover", self._pid)
                self._pid = None  # 清空缓存

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
        # ✅ 优化: 优先检查缓存的 PID 是否存在
        if self._pid:
            rc, _, _ = self._exec(f"test -d /proc/{self._pid} 2>/dev/null", timeout=3)
            if rc == 0:
                # 验证 cmdline 是否包含 arthas-boot
                rc2, cmdline, _ = self._exec(f"cat /proc/{self._pid}/cmdline 2>/dev/null | tr '\\0' ' '", timeout=3)
                if rc2 == 0 and 'arthas-boot' in cmdline:
                    log.info("[_find_arthas_pids] 缓存 PID %d 有效", self._pid)
                    return [self._pid]
                else:
                    log.warning("[_find_arthas_pids] 缓存 PID %d 不是 arthas-boot", self._pid)
                    self._pid = None  # 清空缓存
        
        # ✅ 优化的 /proc 查找: 使用 find 命令,更快
        rc, out, err = self._exec(
            "find /proc -maxdepth 2 -name cmdline -exec sh -c "
            "'cat \"$1\" 2>/dev/null | tr \"\\0\" \" \" | grep -q arthas-boot && "
            "basename $(dirname \"$1\")' _ {} \\; 2>/dev/null || true",
            timeout=8,
        )
        
        log.info("[_find_arthas_pids] /proc 查找输出: rc=%s, out=%s", rc, repr(out[:200]) if out else '')
        
        pids = []
        if rc == 0 and out.strip():
            for line in out.strip().splitlines():
                pid_str = line.strip()
                if pid_str.isdigit():
                    pids.append(int(pid_str))
        
        log.info("[_find_arthas_pids] 解析到 PID 列表: %s", pids)
        
        # ✅ 修复: 使用 /proc/[pid]/stat 验证进程是否真实运行
        valid_pids = []
        for pid in pids:
            # 检查 /proc/[pid]/stat 是否存在(比 test -d 更可靠)
            rc2, stat_out, _ = self._exec(f"cat /proc/{pid}/stat 2>/dev/null | head -1", timeout=3)
            if rc2 == 0 and stat_out.strip():
                valid_pids.append(pid)
                log.info("[_find_arthas_pids] PID %d 验证成功: %s", pid, stat_out.strip()[:100])
            else:
                log.warning("[Arthas] PID %d 已不存在(cmdline残留),跳过", pid)
        
        log.info("[_find_arthas_pids] 有效 PID 列表: %s", valid_pids)
        return valid_pids

    def _kill_stale_arthas(self, pids: List[int]) -> str:
        """清理残留 arthas-boot 进程"""
        if not pids:
            return ""
        
        pid_str = " ".join(str(p) for p in pids)
        log.info("[Arthas] 清理残留进程: %s", pid_str)
        
        # ✅ 分阶段清理: 先 SIGTERM, 再 SIGKILL
        self._exec(
            f"kill {pid_str} 2>/dev/null; sleep 2; "
            f"kill -9 {pid_str} 2>/dev/null; sleep 1; true",
            timeout=10,
        )
        
        # ✅ 验证清理结果
        remaining = self._find_arthas_pids()
        if remaining:
            log.warning("[Arthas] 清理后仍有残留进程: %s", remaining)
            return f"已清理残留进程 {pid_str}, 但仍残留 {remaining}"
        else:
            log.info("[Arthas] 清理成功,无残留进程")
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

        # 情况 A: HTTP 已响应，尝试验证进程是否存在
        if self._http_reachable():
            log.info("[Agent Reuse] HTTP reachable, checking process (port %s)", port)
            # 查找 Arthas 进程
            arthas_pids = self._find_arthas_pids()
            if arthas_pids:
                # ✅ 进程存在,更新 PID 并复用
                if self._pid and self._pid not in arthas_pids:
                    log.warning("[Agent Reuse] Expected PID %d not found, updating to %d",
                               self._pid, arthas_pids[0])
                    self._pid = arthas_pids[0]
                elif not self._pid:
                    self._pid = arthas_pids[0]
                log.info("[Agent Reuse] Arthas PID %d found, reusing agent", self._pid)
                return True, f"Arthas 已在运行，直接复用 (port {port}, pid {self._pid})"
            else:
                # ✅ 进程不存在,说明是僵尸端口,需要重新安装
                log.warning("[Agent Reuse] HTTP reachable but NO Arthas process found, zombie port detected")
                log.info("[Agent Reuse] Returning REINSTALL_NEEDED to trigger cleanup")
                # 返回特殊标记,让上层 ArthasConnection 清理端口转发并重安装
                return False, "REINSTALL_NEEDED"

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
            f" -Xmx128m -Xms64m"  # ✅ 关键修复: 限制 Arthas 内存,防止 OOM
            f" -XX:+UseSerialGC"  # 使用轻量级 GC
            f" -Darthas.httpPort={port}"
            f" -Darthas.telnetPort={self.t.arthas_telnet_port}"
            f" -Darthas.ip=127.0.0.1"
            f"{mcp_config}"
            f" -jar {self.t.arthas_jar}"
            f" {pid}"
            f" > /tmp/arthas_start.log 2>&1 </dev/null &"
            f" echo started_pid=$!"
        )
        log.info("[Arthas Start] 执行启动命令: %s", start_cmd)
        rc_s, out_s, err_s = self._exec(start_cmd, timeout=15)
        log.info("[Arthas Start] 执行结果: rc=%d, pid=%d, jar=%s, out=%s, err=%s, cleanup=%s",
                 rc_s, pid, self.t.arthas_jar, out_s.strip(), err_s.strip(), cleanup_msg)

        # 轮询等待 HTTP 就绪（max 40s）
        log.info("[Arthas Start] 开始轮询 HTTP 就绪...")
        for i in range(40):
            time.sleep(1)
            if self._http_reachable():
                log.info("[Arthas Start] HTTP 就绪,耗时 %ds", i+1)
                # ✅ 关键修复: 保存 java_pid
                self._pid = pid
                msg = f"Arthas 启动成功 (target PID={pid}, 耗时 {i+1}s)"
                if cleanup_msg:
                    msg += f"  [{cleanup_msg}]"
                return True, msg
            if (i + 1) % 10 == 0:
                log.info("[Arthas Start] 等待中... %ds/40s", i+1)

        _, log_tail, _ = self._exec(
            "tail -25 /tmp/arthas_start.log 2>/dev/null", timeout=5)
        log.error("[Arthas Start] 启动超时,日志:\n%s", log_tail[:600])
        return False, (
            f"Arthas 启动超时（40s）\n"
            f"JAR: {self.t.arthas_jar}  target PID: {pid}\n"
            f"启动日志:\n{log_tail[:600]}"
        )