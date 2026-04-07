"""
Kubectl 封装 - 底层 kubectl 操作
"""
import json
import subprocess
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)


class KubectlExecutor:
    """封装所有 kubectl 操作。不包含业务逻辑。"""

    def __init__(self, kubeconfig: str, context: str = ""):
        self.kubeconfig = kubeconfig
        self.context = context

    # ── internal ──────────────────────────────────────────────────────────────

    def _base_cmd(self) -> list:
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd += ["--kubeconfig", self.kubeconfig]
        if self.context:
            cmd += ["--context", self.context]
        return cmd

    def _run(self, args: List, timeout: int = 30) -> Tuple[int, str, str]:
        cmd = self._base_cmd() + args
        log.debug("kubectl: %s", " ".join(cmd))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"kubectl 超时 ({timeout}s)"
        except FileNotFoundError:
            return -1, "", "kubectl 未找到，请确认已安装并在 PATH 中"

    # ── cluster queries ────────────────────────────────────────────────────────

    def get_namespaces(self) -> List[str]:
        rc, out, _ = self._run(
            ["get", "ns", "-o", "jsonpath={.items[*].metadata.name}"], timeout=15)
        return out.strip().split() if rc == 0 and out.strip() else []

    def get_pods(self, namespace: str) -> List[Dict]:
        rc, out, _ = self._run(
            ["-n", namespace, "get", "pods", "-o", "json"], timeout=20)
        if rc != 0:
            return []
        try:
            items = json.loads(out).get("items", [])
            return [{
                "name":       i["metadata"]["name"],
                "phase":      i.get("status", {}).get("phase", "?"),
                "containers": [c["name"] for c in i.get("spec", {}).get("containers", [])],
                "ready":      any(
                    c.get("type") == "Ready" and c.get("status") == "True"
                    for c in i.get("status", {}).get("conditions", [])
                ),
            } for i in items]
        except Exception:
            return []

    def get_contexts(self) -> List[str]:
        rc, out, _ = self._run(["config", "get-contexts", "-o", "name"])
        return [x.strip() for x in out.strip().splitlines() if x.strip()] if rc == 0 else []

    def get_current_context(self) -> str:
        rc, out, _ = self._run(["config", "current-context"])
        return out.strip() if rc == 0 else ""

    def get_pod_phase(self, namespace: str, pod: str) -> str:
        rc, out, _ = self._run(
            ["-n", namespace, "get", "pod", pod,
             "-o", "jsonpath={.status.phase}"], timeout=10)
        return out.strip() if rc == 0 else ""

    def get_pod_json(self, namespace: str, pod: str) -> Optional[dict]:
        rc, out, _ = self._run(
            ["-n", namespace, "get", "pod", pod, "-o", "json"], timeout=15)
        try:
            return json.loads(out) if rc == 0 else None
        except Exception:
            return None

    def cluster_info(self) -> Tuple[bool, str]:
        rc, out, err = self._run(
            ["cluster-info", "--request-timeout=5s"], timeout=10)
        return rc == 0, (out or err).strip()[:400]

    # ── pod exec ──────────────────────────────────────────────────────────────

    def exec_pod(self, namespace: str, pod: str, container: str,
                 shell_cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
        args = ["-n", namespace, "exec", pod]
        if container:
            args += ["-c", container]
        args += ["--", "sh", "-c", shell_cmd]
        return self._run(args, timeout=timeout)

    # ── port-forward ──────────────────────────────────────────────────────────

    def start_port_forward(self, namespace: str, pod: str,
                           local_port: int, remote_port: int) -> subprocess.Popen:
        cmd = self._base_cmd() + [
            "-n", namespace, "port-forward", pod,
            f"{local_port}:{remote_port}",
        ]
        log.info("port-forward: %s", " ".join(cmd))
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    # ── file transfer ─────────────────────────────────────────────────────────

    def cp_from_pod(self, namespace: str, pod: str, container: str,
                    pod_path: str, local_path: str) -> Tuple[int, str, str]:
        """三级降级策略下载 Pod 内文件"""
        import base64 as _b64
        import os as _os
        import subprocess as _sp

        if not pod or not pod_path:
            return -1, "", "pod 和 pod_path 不能为空"

        # 方法1: kubectl cp
        cmd1 = self._base_cmd() + ["cp", f"{pod}:{pod_path}", local_path, "-n", namespace]
        if container:
            cmd1 += ["-c", container]
        log.info("kubectl cp: %s", " ".join(cmd1))
        try:
            r1 = _sp.run(cmd1, capture_output=True, text=True, timeout=120)
            if r1.returncode == 0 and _os.path.exists(local_path):
                return 0, "", ""
            err1 = r1.stderr.strip() or r1.stdout.strip()
        except Exception as e1:
            err1 = str(e1)

        log.warning("kubectl cp failed (%s), fallback to exec+cat", err1)

        # 方法2: kubectl exec -- cat
        cmd2 = self._base_cmd() + ["-n", namespace, "exec", pod]
        if container:
            cmd2 += ["-c", container]
        cmd2 += ["--", "cat", pod_path]
        try:
            r2 = _sp.run(cmd2, capture_output=True, timeout=120)
            if r2.returncode == 0 and r2.stdout:
                with open(local_path, "wb") as f:
                    f.write(r2.stdout)
                return 0, "", ""
            err2 = r2.stderr.decode(errors="replace").strip()
        except Exception as e2:
            err2 = str(e2)

        log.warning("exec+cat failed (%s), fallback to base64", err2)

        # 方法3: base64 兜底
        cmd3 = self._base_cmd() + ["-n", namespace, "exec", pod]
        if container:
            cmd3 += ["-c", container]
        escaped_path = pod_path.replace("'", "'\\''")
        cmd3 += ["--", "sh", "-c", f"base64 '{escaped_path}'"]
        try:
            r3 = _sp.run(cmd3, capture_output=True, text=True, timeout=120)
            if r3.returncode == 0 and r3.stdout.strip():
                with open(local_path, "wb") as f:
                    f.write(_b64.b64decode(r3.stdout.replace("\n", "").strip()))
                return 0, "", ""
            err3 = r3.stderr.strip()
        except Exception as e3:
            err3 = str(e3)

        return -1, "", f"所有下载方式均失败\nkubectl cp: {err1}\ncat: {err2}\nbase64: {err3}"

    def get_events(self, namespace: str, pod: str) -> List[Dict]:
        rc, out, _ = self._run([
            "-n", namespace, "get", "events",
            "--field-selector", f"involvedObject.name={pod}",
            "--sort-by=.lastTimestamp", "-o", "json",
        ], timeout=15)
        if rc != 0:
            return []
        try:
            events = []
            for item in json.loads(out).get("items", []):
                events.append({
                    "type":       item.get("type", ""),
                    "reason":     item.get("reason", ""),
                    "message":    item.get("message", ""),
                    "count":      item.get("count", 1),
                    "last_time":  item.get("lastTimestamp", ""),
                    "source":     item.get("source", {}).get("component", ""),
                })
            return list(reversed(events))
        except Exception:
            return []

    def get_logs(self, namespace: str, pod: str, container: str = "",
                 tail: int = 200, since: str = "") -> str:
        args = ["-n", namespace, "logs", pod, f"--tail={tail}"]
        if container:
            args += ["-c", container]
        if since:
            args += [f"--since={since}"]
        rc, out, err = self._run(args, timeout=30)
        return out if rc == 0 else f"# Error: {err}"

    # ── Pod metrics (for monitoring) ─────────────────────────────────────────────

    def get_pod_metrics(self, namespace: str, pod: str) -> Optional[Dict]:
        """kubectl top pod（需要 metrics-server）"""
        rc, out, err = self._run(
            ["-n", namespace, "top", "pod", pod, "--no-headers"],
            timeout=15)
        if rc != 0:
            return None
        # 格式: NAME  CPU(cores)  MEMORY(bytes)
        parts = out.split()
        if len(parts) < 3:
            return None
        return {"cpu_raw": parts[1], "memory_raw": parts[2]}

    def get_pod_events(self, namespace: str, pod: str) -> List[Dict]:
        """获取 Pod 事件（兼容 pod_monitor 调用）"""
        return self.get_events(namespace, pod)