#!/usr/bin/env python3
"""
Pod Monitor Backend
通过 kubectl 采集 Pod 完整监控信息：
  - Pod 基本信息（metadata / spec / status）
  - 容器资源用量（kubectl top, /proc/meminfo, /sys/fs/cgroup）
  - 容器内进程（ps aux）
  - 网络信息（/proc/net/dev）
  - 磁盘信息（df -h）
  - Pod Events（kubectl describe 解析）
  - 容器日志（kubectl logs）
  - 实时指标历史（内存中环形缓冲）
"""

import subprocess, json, re, time, threading
from datetime import datetime, timezone
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Deque

# ── 时序指标缓冲（最近 60 个采样点）────────────────────────────────────────────
_metrics_history = {}  # type: Dict[str, Deque]  # key="{cluster}/{ns}/{pod}" -> deque of snapshots
_metrics_lock = threading.Lock()
MAX_HISTORY = 60   # 保留最近 60 个点
POLL_INTERVAL = 15  # 秒


class KubectlRunner:
    def __init__(self, kubeconfig: str = "", context: str = ""):
        self.kubeconfig = kubeconfig
        self.context = context

    def _base(self):
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd += ["--kubeconfig", self.kubeconfig]
        if self.context:
            cmd += ["--context", self.context]
        return cmd

    def run(self, *args, ns: str = "", timeout: int = 20, input_data: str = None):
        cmd = self._base()
        if ns:
            cmd += ["-n", ns]
        cmd += list(args)
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout,
                input=input_data
            )
            return r.returncode, r.stdout.strip(), r.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", f"超时({timeout}s)"
        except FileNotFoundError:
            return -1, "", "kubectl 未找到"

    def exec_pod(self, ns: str, pod: str, container: str, cmd_str: str, timeout: int = 10):
        args = ["exec", pod, "-n", ns]
        if container:
            args += ["-c", container]
        args += ["--", "sh", "-c", cmd_str]
        return self.run(*args, timeout=timeout)

    def cp_from_pod(self, ns: str, pod: str, container: str,
                    pod_path: str, local_path: str):
        """
        从 Pod 内下载文件到本地。三级降级策略：
          1. kubectl cp <pod>:<src> <local> -n <ns>   (flags after positional args)
          2. kubectl exec -- cat <file>               (绕开 cp 参数解析问题)
          3. kubectl exec -- base64 <file>            (二进制文件兜底)
        """
        import subprocess as _sp, base64 as _b64, os as _os
        import logging as _log
        _logger = _log.getLogger(__name__)

        if not pod:
            return -1, "", "pod_name 不能为空"
        if not pod_path:
            return -1, "", "pod_path 不能为空"

        # ── 方法1: kubectl cp（-n/-c 放在 src/dest 之后）────────────────────────
        # 正确格式: kubectl cp <pod>:<src> <local> -n <ns> [-c <container>]
        cmd1 = self._base() + ["cp", f"{pod}:{pod_path}", local_path, "-n", ns]
        if container:
            cmd1 += ["-c", container]
        _logger.info("kubectl cp: %s", " ".join(cmd1))
        try:
            r1 = _sp.run(cmd1, capture_output=True, text=True, timeout=120)
            if r1.returncode == 0 and _os.path.exists(local_path):
                return 0, "", ""
            err1 = r1.stderr.strip() or r1.stdout.strip()
        except Exception as e1:
            err1 = str(e1)

        _logger.warning("kubectl cp failed (%s), trying exec+cat", err1)

        # ── 方法2: kubectl exec -- cat（绕开 cp 参数解析）─────────────────────
        exec_cat = self._base() + ["-n", ns, "exec", pod]
        if container:
            exec_cat += ["-c", container]
        exec_cat += ["--", "cat", pod_path]
        _logger.info("exec+cat: %s", " ".join(exec_cat))
        try:
            r2 = _sp.run(exec_cat, capture_output=True, timeout=120)
            if r2.returncode == 0 and r2.stdout:
                with open(local_path, "wb") as fout:
                    fout.write(r2.stdout)
                return 0, "", ""
            err2 = r2.stderr.decode(errors="replace").strip()
        except Exception as e2:
            err2 = str(e2)

        _logger.warning("exec+cat failed (%s), trying base64", err2)

        # ── 方法3: base64 编码传输（二进制文件兜底）──────────────────────────
        exec_b64 = self._base() + ["-n", ns, "exec", pod]
        if container:
            exec_b64 += ["-c", container]
        exec_b64 += ["--", "sh", "-c", f"base64 '{pod_path}'"]
        try:
            r3 = _sp.run(exec_b64, capture_output=True, text=True, timeout=120)
            if r3.returncode == 0 and r3.stdout.strip():
                with open(local_path, "wb") as fout:
                    fout.write(_b64.b64decode(r3.stdout.replace("\n", "").strip()))
                return 0, "", ""
            err3 = r3.stderr.strip()
        except Exception as e3:
            err3 = str(e3)

        return -1, "", (
            f"所有下载方式均失败\n"
            f"kubectl cp: {err1}\n"
            f"exec+cat:   {err2}\n"
            f"base64:     {err3}"
        )

    def get_pod_json(self, ns: str, pod: str) -> Optional[dict]:
        rc, out, err = self.run("get", "pod", pod, "-o", "json", ns=ns)
        if rc != 0:
            return None
        try:
            return json.loads(out)
        except Exception:
            return None

    def get_pod_metrics(self, ns: str, pod: str) -> Optional[dict]:
        """kubectl top pod（需要 metrics-server）"""
        rc, out, err = self.run("top", "pod", pod, "--no-headers", ns=ns, timeout=15)
        if rc != 0:
            return None
        # 格式: NAME  CPU(cores)  MEMORY(bytes)
        parts = out.split()
        if len(parts) < 3:
            return None
        return {"cpu_raw": parts[1], "memory_raw": parts[2]}

    def get_pod_events(self, ns: str, pod: str) -> list:
        rc, out, err = self.run(
            "get", "events",
            "--field-selector", f"involvedObject.name={pod}",
            "--sort-by=.lastTimestamp",
            "-o", "json",
            ns=ns, timeout=15
        )
        if rc != 0:
            return []
        try:
            data = json.loads(out)
            events = []
            for item in data.get("items", []):
                events.append({
                    "type": item.get("type", ""),
                    "reason": item.get("reason", ""),
                    "message": item.get("message", ""),
                    "count": item.get("count", 1),
                    "first_time": item.get("firstTimestamp", ""),
                    "last_time": item.get("lastTimestamp", ""),
                    "source": item.get("source", {}).get("component", ""),
                })
            return list(reversed(events))  # 最新在前
        except Exception:
            return []

    def get_logs(self, ns: str, pod: str, container: str = "",
                 tail: int = 100, since: str = "") -> str:
        args = ["logs", pod, "-n", ns, f"--tail={tail}"]
        if container:
            args += ["-c", container]
        if since:
            args += [f"--since={since}"]
        rc, out, err = self.run(*args, timeout=30)
        return out if rc == 0 else err

    def get_previous_logs(self, ns: str, pod: str, container: str = "", tail: int = 50) -> str:
        args = ["logs", pod, "-n", ns, "--previous", f"--tail={tail}"]
        if container:
            args += ["-c", container]
        rc, out, err = self.run(*args, timeout=20)
        return out if rc == 0 else ""


# ── Pod 信息解析 ────────────────────────────────────────────────────────────────

def parse_pod_info(pod_json: dict) -> dict:
    """从 kubectl get pod -o json 解析完整 Pod 信息"""
    meta = pod_json.get("metadata", {})
    spec = pod_json.get("spec", {})
    status = pod_json.get("status", {})

    # 计算年龄
    creation = meta.get("creationTimestamp", "")
    age_str = ""
    age_seconds = 0
    if creation:
        try:
            from datetime import datetime, timezone
            created = datetime.fromisoformat(creation.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = now - created
            age_seconds = int(delta.total_seconds())
            age_str = format_duration(age_seconds)
        except Exception:
            pass

    # 容器状态
    container_statuses = {cs["name"]: cs for cs in status.get("containerStatuses", [])}
    init_container_statuses = {cs["name"]: cs for cs in status.get("initContainerStatuses", [])}

    containers = []
    for c in spec.get("containers", []):
        cs = container_statuses.get(c["name"], {})
        state_info = cs.get("state", {})
        state_key = list(state_info.keys())[0] if state_info else "waiting"
        state_detail = state_info.get(state_key, {})

        # 资源限制
        resources = c.get("resources", {})
        limits = resources.get("limits", {})
        requests = resources.get("requests", {})

        containers.append({
            "name": c["name"],
            "image": c.get("image", ""),
            "image_pull_policy": c.get("imagePullPolicy", ""),
            "state": state_key,
            "state_reason": state_detail.get("reason", ""),
            "state_message": state_detail.get("message", ""),
            "ready": cs.get("ready", False),
            "restart_count": cs.get("restartCount", 0),
            "started": cs.get("started", False),
            "container_id": cs.get("containerID", ""),
            "ports": c.get("ports", []),
            "env": [{"name": e.get("name"), "value": e.get("value", e.get("valueFrom", {}))}
                    for e in c.get("env", [])[:20]],
            "volume_mounts": c.get("volumeMounts", []),
            "limits_cpu": limits.get("cpu", ""),
            "limits_mem": limits.get("memory", ""),
            "requests_cpu": requests.get("cpu", ""),
            "requests_mem": requests.get("memory", ""),
            "liveness_probe": bool(c.get("livenessProbe")),
            "readiness_probe": bool(c.get("readinessProbe")),
        })

    # 条件
    conditions = []
    for cond in status.get("conditions", []):
        conditions.append({
            "type": cond.get("type", ""),
            "status": cond.get("status", ""),
            "reason": cond.get("reason", ""),
            "last_transition": cond.get("lastTransitionTime", ""),
        })

    # 卷
    volumes = []
    for v in spec.get("volumes", []):
        vtype = "unknown"
        for t in ["configMap", "secret", "persistentVolumeClaim", "emptyDir",
                  "hostPath", "projected", "downwardAPI"]:
            if t in v:
                vtype = t
                break
        volumes.append({"name": v["name"], "type": vtype})

    return {
        "name": meta.get("name", ""),
        "namespace": meta.get("namespace", ""),
        "uid": meta.get("uid", ""),
        "labels": meta.get("labels", {}),
        "annotations": {k: v for k, v in meta.get("annotations", {}).items()
                        if "kubectl.kubernetes.io" not in k},
        "creation_timestamp": creation,
        "age": age_str,
        "age_seconds": age_seconds,
        "node_name": spec.get("nodeName", ""),
        "service_account": spec.get("serviceAccountName", ""),
        "restart_policy": spec.get("restartPolicy", ""),
        "phase": status.get("phase", ""),
        "pod_ip": status.get("podIP", ""),
        "host_ip": status.get("hostIP", ""),
        "qos_class": status.get("qosClass", ""),
        "containers": containers,
        "conditions": conditions,
        "volumes": volumes,
        "node_selector": spec.get("nodeSelector", {}),
        "tolerations": spec.get("tolerations", []),
        "service_account_name": spec.get("serviceAccountName", ""),
    }


def parse_top_metrics(raw: str) -> dict:
    """解析 kubectl top pod --no-headers 输出"""
    if not raw:
        return {}
    parts = raw.split()
    if len(parts) < 3:
        return {}

    def parse_cpu(s):
        if s.endswith("m"):
            return float(s[:-1])  # millicores
        try:
            return float(s) * 1000
        except Exception:
            return 0

    def parse_mem(s):
        s = s.upper()
        if s.endswith("KI"):
            return int(s[:-2]) * 1024
        if s.endswith("MI"):
            return int(s[:-2]) * 1024 * 1024
        if s.endswith("GI"):
            return int(s[:-2]) * 1024 * 1024 * 1024
        if s.endswith("K"):
            return int(s[:-1]) * 1000
        if s.endswith("M"):
            return int(s[:-1]) * 1000 * 1000
        if s.endswith("G"):
            return int(s[:-1]) * 1000 * 1000 * 1000
        try:
            return int(s)
        except Exception:
            return 0

    return {
        "cpu_millicores": parse_cpu(parts[1]),
        "cpu_raw": parts[1],
        "memory_bytes": parse_mem(parts[2]),
        "memory_raw": parts[2],
    }


# ── 容器内部指标（通过 kubectl exec）──────────────────────────────────────────

def collect_container_metrics(runner: KubectlRunner, ns: str, pod: str, container: str) -> dict:
    """在容器内执行命令采集精细指标"""
    result = {}

    # 内存详情（/proc/meminfo 或 cgroup）
    rc, out, _ = runner.exec_pod(ns, pod, container,
        "cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null || "
        "cat /sys/fs/cgroup/memory.current 2>/dev/null || echo ''")
    if rc == 0 and out.strip().isdigit():
        result["cgroup_mem_usage_bytes"] = int(out.strip())

    rc2, out2, _ = runner.exec_pod(ns, pod, container,
        "cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || "
        "cat /sys/fs/cgroup/memory.max 2>/dev/null || echo ''")
    if rc2 == 0 and out2.strip().isdigit() and int(out2.strip()) < 2**60:
        result["cgroup_mem_limit_bytes"] = int(out2.strip())

    # CPU 节流（cgroup）
    rc3, out3, _ = runner.exec_pod(ns, pod, container,
        "cat /sys/fs/cgroup/cpu/cpu.stat 2>/dev/null || "
        "cat /sys/fs/cgroup/cpu.stat 2>/dev/null | head -5 || echo ''")
    if rc3 == 0 and out3:
        for line in out3.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] in ("throttled_time", "nr_throttled", "nr_periods"):
                try:
                    result[f"cpu_{parts[0]}"] = int(parts[1])
                except Exception:
                    pass

    # 磁盘使用（df）
    rc4, out4, _ = runner.exec_pod(ns, pod, container,
        "df -h / 2>/dev/null | tail -1 || echo ''", timeout=8)
    if rc4 == 0 and out4:
        parts = out4.split()
        if len(parts) >= 5:
            result["disk_total"] = parts[1]
            result["disk_used"] = parts[2]
            result["disk_avail"] = parts[3]
            result["disk_use_pct"] = parts[4]

    # 进程列表（top 15 by CPU）
    rc5, out5, _ = runner.exec_pod(ns, pod, container,
        "ps aux --sort=-%cpu 2>/dev/null | head -16 || ps aux 2>/dev/null | head -16 || echo ''",
        timeout=8)
    if rc5 == 0 and out5:
        lines = out5.strip().splitlines()
        processes = []
        for line in lines[1:15]:  # skip header
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append({
                    "pid": parts[1], "cpu": parts[2], "mem": parts[3],
                    "stat": parts[7], "cmd": parts[10][:60],
                })
        result["processes"] = processes

    # 网络接口统计
    rc6, out6, _ = runner.exec_pod(ns, pod, container,
        "cat /proc/net/dev 2>/dev/null || echo ''", timeout=8)
    if rc6 == 0 and out6:
        net_ifaces = []
        for line in out6.splitlines()[2:]:
            line = line.strip()
            if not line or "lo:" in line:
                continue
            parts = line.split()
            if len(parts) >= 10:
                iface = parts[0].rstrip(":")
                try:
                    net_ifaces.append({
                        "iface": iface,
                        "rx_bytes": int(parts[1]),
                        "rx_packets": int(parts[2]),
                        "rx_errors": int(parts[3]),
                        "tx_bytes": int(parts[9]),
                        "tx_packets": int(parts[10]),
                        "tx_errors": int(parts[11]),
                    })
                except Exception:
                    pass
        result["network"] = net_ifaces

    # 打开文件描述符数量
    rc7, out7, _ = runner.exec_pod(ns, pod, container,
        "ls /proc/1/fd 2>/dev/null | wc -l || echo 0", timeout=5)
    if rc7 == 0:
        try:
            result["open_fds"] = int(out7.strip())
        except Exception:
            pass

    return result


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds//60}m{seconds%60}s"
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h{m}m"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d}d{h}h"


def bytes_to_human(b: int) -> str:
    if b < 1024:
        return f"{b}B"
    if b < 1024**2:
        return f"{b/1024:.1f}Ki"
    if b < 1024**3:
        return f"{b/1024**2:.1f}Mi"
    return f"{b/1024**3:.2f}Gi"


# ── 综合采集入口 ────────────────────────────────────────────────────────────────

def collect_pod_snapshot(runner: KubectlRunner, ns: str, pod: str,
                         container: str = "") -> dict:
    """
    完整采集 Pod 监控快照，返回标准化数据结构
    用于首次加载 + 定期轮询
    """
    ts = datetime.now().isoformat()

    # 1. Pod JSON
    pod_json = runner.get_pod_json(ns, pod)
    if pod_json is None:
        return {"error": "Pod 不存在或无法访问", "timestamp": ts}

    pod_info = parse_pod_info(pod_json)

    # 确定要监控的容器
    target_container = container
    if not target_container and pod_info["containers"]:
        target_container = pod_info["containers"][0]["name"]

    # 2. kubectl top pod（可能没有 metrics-server，允许失败）
    top_raw = runner.get_pod_metrics(ns, pod)
    top_metrics = parse_top_metrics(top_raw["cpu_raw"] + " " + top_raw["memory_raw"]) if top_raw else {}

    # 3. 容器内部指标
    container_metrics = {}
    if pod_info["phase"] == "Running":
        container_metrics = collect_container_metrics(runner, ns, pod, target_container)

    # 4. 事件
    events = runner.get_pod_events(ns, pod)

    return {
        "timestamp": ts,
        "pod_info": pod_info,
        "top_metrics": top_metrics,
        "container_metrics": container_metrics,
        "events": events[:20],
        "target_container": target_container,
    }


# ── 后台轮询（存入历史缓冲）──────────────────────────────────────────────────────

_poll_threads: dict = {}  # key -> thread
_poll_stop: dict = {}     # key -> bool


def start_metrics_polling(runner: KubectlRunner, cluster: str,
                           ns: str, pod: str, container: str = ""):
    key = f"{cluster}/{ns}/{pod}"
    _poll_stop[key] = False

    with _metrics_lock:
        if key not in _metrics_history:
            _metrics_history[key] = deque(maxlen=MAX_HISTORY)

    def _poll():
        while not _poll_stop.get(key, True):
            try:
                # 轻量采集：只采集 top + container 内部指标（不重复拉 pod JSON）
                ts = datetime.now().isoformat()
                top_raw = runner.get_pod_metrics(ns, pod)
                top = parse_top_metrics(top_raw["cpu_raw"] + " " + top_raw["memory_raw"]) if top_raw else {}

                # 快速内存/CPU 指标
                cg_mem = {}
                rc, out, _ = runner.exec_pod(ns, pod, container,
                    "cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null || "
                    "cat /sys/fs/cgroup/memory.current 2>/dev/null || echo ''", timeout=5)
                if rc == 0 and out.strip().isdigit():
                    cg_mem["usage"] = int(out.strip())

                point = {
                    "ts": ts,
                    "cpu_m": top.get("cpu_millicores", 0),
                    "mem_bytes": top.get("memory_bytes", 0) or cg_mem.get("usage", 0),
                    "cpu_raw": top.get("cpu_raw", ""),
                    "mem_raw": top.get("memory_raw", ""),
                }
                with _metrics_lock:
                    _metrics_history[key].append(point)
            except Exception:
                pass
            time.sleep(POLL_INTERVAL)

    t = threading.Thread(target=_poll, daemon=True, name=f"poll-{key}")
    t.start()
    _poll_threads[key] = t


def stop_metrics_polling(cluster: str, ns: str, pod: str):
    key = f"{cluster}/{ns}/{pod}"
    _poll_stop[key] = True


def get_metrics_history(cluster: str, ns: str, pod: str) -> list:
    key = f"{cluster}/{ns}/{pod}"
    with _metrics_lock:
        return list(_metrics_history.get(key, []))
