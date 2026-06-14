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
from typing import Optional, Dict, Deque, List

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
                cmd, capture_output=True,
                timeout=timeout,
                input=input_data.encode('utf-8') if input_data else None
            )
            # Pod 终端输出统一为 UTF-8；Windows 下 text=True 会使用系统默认编码（GBK）导致中文乱码
            stdout = r.stdout.decode('utf-8', errors='replace').strip() if r.stdout else ''
            stderr = r.stderr.decode('utf-8', errors='replace').strip() if r.stderr else ''
            return r.returncode, stdout, stderr
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
            r1 = _sp.run(cmd1, capture_output=True, timeout=120)
            if r1.returncode == 0 and _os.path.exists(local_path):
                return 0, "", ""
            err1 = r1.stderr.decode('utf-8', errors='replace').strip() or r1.stdout.decode('utf-8', errors='replace').strip()
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
            err2 = r2.stderr.decode('utf-8', errors='replace').strip()
        except Exception as e2:
            err2 = str(e2)

        _logger.warning("exec+cat failed (%s), trying base64", err2)

        # ── 方法3: base64 编码传输（二进制文件兜底）──────────────────────────
        exec_b64 = self._base() + ["-n", ns, "exec", pod]
        if container:
            exec_b64 += ["-c", container]
        exec_b64 += ["--", "sh", "-c", f"base64 '{pod_path}'"]
        try:
            r3 = _sp.run(exec_b64, capture_output=True, timeout=120)
            b64_text = r3.stdout.decode('ascii', errors='replace') if r3.stdout else ''
            b64_err = r3.stderr.decode('utf-8', errors='replace').strip() if r3.stderr else ''
            if r3.returncode == 0 and b64_text.strip():
                with open(local_path, "wb") as fout:
                    fout.write(_b64.b64decode(b64_text.replace("\n", "").strip()))
                return 0, "", ""
            err3 = b64_err
        except Exception as e3:
            err3 = str(e3)

        return -1, "", (
            f"所有下载方式均失败\n"
            f"kubectl cp: {err1}\n"
            f"exec+cat:   {err2}\n"
            f"base64:     {err3}"
        )

    def get_pod_json(self, ns: str, pod: str):  # type: (str, str) -> Optional[dict]
        rc, out, err = self.run("get", "pod", pod, "-o", "json", ns=ns)
        if rc != 0:
            return None
        try:
            return json.loads(out)
        except Exception:
            return None

    def get_pod_metrics(self, ns: str, pod: str):  # type: (str, str) -> Optional[dict]
        """kubectl top pod（需要 metrics-server）"""
        rc, out, err = self.run("top", "pod", pod, "--no-headers", ns=ns, timeout=15)
        if rc != 0:
            return None
        # 格式: NAME  CPU(cores)  MEMORY(bytes)
        parts = out.split()
        if len(parts) < 3:
            return None
        return {"cpu_raw": parts[1], "memory_raw": parts[2]}

    def get_pod_events(self, ns: str, pod: str):  # type: (str, str) -> list
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
    """在容器内执行命令采集精细指标（并发 3 次 exec，减少总耗时）"""
    import concurrent.futures
    result = {}

    # ps 多级降级脚本：ps aux → ps -ef → ps -A → /proc 扫描
    # 即使 ps 存在但输出为空，也会走 /proc 兜底
    ps_fallback_script = (
        "_ps_out=$(ps aux 2>/dev/null); "
        "[ -z \"$_ps_out\" ] && _ps_out=$(ps -ef 2>/dev/null); "
        "[ -z \"$_ps_out\" ] && _ps_out=$(ps -A 2>/dev/null); "
        "if [ -n \"$_ps_out\" ]; then "
        "echo \"$_ps_out\"; "
        "else "
        "echo 'USER       PID %CPU %MEM    STAT COMMAND'; "
        "for p in /proc/[0-9]*/stat; do "
        "pid=$(echo $p | grep -o '[0-9]*'); "
        "if [ -r \"$p\" ]; then "
        "comm=$(cat /proc/$pid/cmdline 2>/dev/null | tr '\\0' ' ' | head -c 80); "
        "if [ -z \"$comm\" ]; then comm=$(cat \"$p\" 2>/dev/null | awk '{print $2}' | tr -d '()'); fi; "
        "echo \"root $pid 0.0 0.0 S $comm\"; "
        "fi; done; "
        "fi"
    )

    def _exec1():
        """内存 + CPU + 磁盘 + FD"""
        rc, out, err = runner.exec_pod(ns, pod, container,
            "echo '===MEM==='; "
            "cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null "
            "|| cat /sys/fs/cgroup/memory.current 2>/dev/null || true; "
            "echo '===MEMLIMIT==='; "
            "cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null "
            "|| cat /sys/fs/cgroup/memory.max 2>/dev/null || true; "
            "echo '===CPUSTAT==='; "
            "cat /sys/fs/cgroup/cpu/cpu.stat 2>/dev/null "
            "|| cat /sys/fs/cgroup/cpu.stat 2>/dev/null | head -5 || true; "
            "echo '===DISK==='; "
            "df -hP 2>/dev/null | grep -v '^Filesystem' || true; "
            "echo '===DISKROOT==='; "
            "df -hP / 2>/dev/null | tail -1 || true; "
            "echo '===FD==='; "
            "ls /proc/1/fd 2>/dev/null | wc -l || echo 0",
            timeout=10)
        if rc != 0:
            import logging as _log
            _log.getLogger(__name__).warning(
                "collect_container_metrics: exec1 (mem+cpu+disk) failed rc=%d err=%s pod=%s/%s",
                rc, err[:200] if err else '', ns, pod)
        return rc, out

    def _exec2():
        """进程列表 + 网络"""
        rc, out, err = runner.exec_pod(ns, pod, container,
            f"echo '===PS==='; {ps_fallback_script}; echo '===NET==='; cat /proc/net/dev 2>/dev/null || true",
            timeout=15)
        if rc != 0:
            import logging as _log
            _log.getLogger(__name__).warning(
                "collect_container_metrics: exec2 (ps+net) failed rc=%d err=%s pod=%s/%s",
                rc, err[:200] if err else '', ns, pod)
        return rc, out

    def _exec3():
        """挂载详情"""
        rc, out, _ = runner.exec_pod(ns, pod, container,
            "if [ -r /proc/self/mountinfo ]; then cat /proc/self/mountinfo; else mount 2>/dev/null; fi || echo ''",
            timeout=8)
        return rc, out

    # 并发执行 3 次 exec
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f1 = ex.submit(_exec1)
        f2 = ex.submit(_exec2)
        f3 = ex.submit(_exec3)
        rc1, out1 = f1.result()
        rc2, out2 = f2.result()
        rc3, out3 = f3.result()

    # ── 兜底：如果 exec2 (ps+net) 失败，尝试单独采集 ───────────────────────
    if rc2 != 0:
        import logging as _log
        _log.getLogger(__name__).info("exec2 fallback: trying standalone ps and /proc/net")
        # 单独采集 ps（含 /proc 兜底）
        rc_ps, out_ps, _ = runner.exec_pod(ns, pod, container,
            f"echo '===PS==='; {ps_fallback_script}; echo '===NET==='",
            timeout=10)
        if rc_ps == 0 and out_ps.strip():
            out2 = "===PS===\n" + out_ps + "\n===NET===\n"
            rc2 = 0
            # 单独采集网络
            rc_net, out_net, _ = runner.exec_pod(ns, pod, container,
                "cat /proc/net/dev 2>/dev/null || echo ''", timeout=5)
            if rc_net == 0 and out_net.strip():
                out2 += out_net

    # ── 解析第一次 exec：内存 + CPU + 磁盘 + FD ───────────────────────────
    if rc1 == 0 and out1:
        sections = out1.split('===MEM===')
        body = sections[-1] if len(sections) > 1 else out1

        # 内存 usage
        mem_parts = body.split('===MEMLIMIT===')
        mem_usage_str = mem_parts[0].strip().splitlines()
        if mem_usage_str:
            val = mem_usage_str[0].strip()
            if val.isdigit():
                result["cgroup_mem_usage_bytes"] = int(val)

        # 内存 limit
        if len(mem_parts) > 1:
            limit_parts = mem_parts[1].split('===CPUSTAT===')
            mem_limit_str = limit_parts[0].strip().splitlines()
            if mem_limit_str:
                val = mem_limit_str[0].strip()
                if val.isdigit() and int(val) < 2**60:
                    result["cgroup_mem_limit_bytes"] = int(val)

            # CPU stat
            if len(limit_parts) > 1:
                cpu_parts = limit_parts[1].split('===DISK===')
                for line in cpu_parts[0].strip().splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[0] in ("throttled_time", "nr_throttled", "nr_periods"):
                        try:
                            result[f"cpu_{parts[0]}"] = int(parts[1])
                        except Exception:
                            pass

                # 磁盘（所有挂载点）
                if len(cpu_parts) > 1:
                    disk_parts = cpu_parts[1].split('===DISKROOT===')
                    disk_text = disk_parts[0]
                    diskroot_text = disk_parts[1] if len(disk_parts) > 1 else ''

                    # 多挂载点列表（从右往左解析，兼容 NFS 长路径/含空格）
                    disk_mounts = []
                    df_lines = disk_text.strip().splitlines()
                    for dl in df_lines:
                        dp = dl.split()
                        if len(dp) >= 6:
                            try:
                                mount = dp[-1]
                                use_pct = dp[-2]
                                avail = dp[-3]
                                used = dp[-4]
                                size = dp[-5]
                                filesystem = ' '.join(dp[:-5])
                                pct_val = int(use_pct.replace('%', ''))
                            except (ValueError, TypeError, IndexError):
                                continue
                            disk_mounts.append({
                                "filesystem": filesystem,
                                "size": size,
                                "used": used,
                                "avail": avail,
                                "use_pct": use_pct,
                                "use_pct_val": pct_val,
                                "mount": mount,
                                "fs_type": "",
                                "mount_source": "",
                                "mount_options": "",
                            })
                    result["disk_mounts"] = disk_mounts

                    # 根分区摘要（兼容旧字段）
                    fd_parts = diskroot_text.split('===FD===')
                    root_text = fd_parts[0]
                    fd_text = fd_parts[1] if len(fd_parts) > 1 else ''

                    if root_text.strip():
                        root_line = root_text.strip().splitlines()
                        if root_line:
                            parts = root_line[0].split()
                            if len(parts) >= 5:
                                result["disk_total"] = parts[1]
                                result["disk_used"] = parts[2]
                                result["disk_avail"] = parts[3]
                                result["disk_use_pct"] = parts[4]
                    elif disk_mounts:
                        root_m = next((m for m in disk_mounts if m["mount"] == "/"), disk_mounts[0])
                        result["disk_total"] = root_m["size"]
                        result["disk_used"] = root_m["used"]
                        result["disk_avail"] = root_m["avail"]
                        result["disk_use_pct"] = root_m["use_pct"]

                    # FD
                    if fd_text.strip():
                        fd_val = fd_text.strip().splitlines()[0].strip()
                        try:
                            result["open_fds"] = int(fd_val)
                        except Exception:
                            pass

    # ── 解析第二次 exec：进程列表 + 网络 ───────────────────────────────────
    if rc2 == 0 and out2:
        sections = out2.split('===PS===')
        body = sections[-1] if len(sections) > 1 else out2

        ps_parts = body.split('===NET===')

        # 进程列表
        ps_output = ps_parts[0].strip()
        if ps_output:
            lines = ps_output.splitlines()
            processes = []
            # 检测 ps 输出格式：标准 ps aux 有 11 列，BusyBox ps 只有 4-5 列
            # 判断首行是否为表头：同时检查关键字 + 第二列不是纯数字（PID）
            header = lines[0] if lines else ''
            header_parts = header.split()
            second_is_pid = len(header_parts) >= 2 and header_parts[1].isdigit()
            is_full_ps = ('STAT' in header or 'VSZ' in header or 'TTY' in header) and not second_is_pid
            start_idx = 1 if is_full_ps else 0  # 标准 ps 有 header 行需跳过

            for line in lines[start_idx:51]:  # skip header for full ps, max 50
                parts = line.split(None, 10)
                if len(parts) < 2:
                    continue
                # 统一按列数分级解析，不再依赖 is_full_ps 门控
                if len(parts) >= 11:
                    # 标准 ps aux 格式: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
                    processes.append({
                        "user": parts[0], "pid": parts[1], "cpu": parts[2], "mem": parts[3],
                        "stat": parts[7], "cmd": parts[10][:80],
                    })
                elif len(parts) >= 9:
                    # 缺少某些列的标准 ps
                    processes.append({
                        "user": parts[0], "pid": parts[1], "cpu": parts[2], "mem": parts[3],
                        "stat": parts[7] if len(parts) > 7 else '?', "cmd": parts[-1][:80],
                    })
                elif len(parts) >= 5:
                    # BusyBox ps 或自定义格式: USER PID %CPU %MEM STAT COMMAND (或类似)
                    # 或简化 /proc 解析: USER PID %CPU %MEM STAT COMMAND
                    processes.append({
                        "user": parts[0],
                        "pid": parts[1],
                        "cpu": parts[2] if len(parts) > 2 else '0',
                        "mem": parts[3] if len(parts) > 3 else '0',
                        "stat": parts[4] if len(parts) > 4 else '?',
                        "cmd": parts[5][:80] if len(parts) > 5 else (parts[4][:80] if len(parts) > 4 else '?'),
                    })
                elif len(parts) >= 3:
                    # BusyBox 极简格式: PID USER TIME COMMAND
                    # 尝试识别 PID（数字）在哪个位置
                    pid_idx = 0
                    for i, p in enumerate(parts):
                        if p.isdigit():
                            pid_idx = i
                            break
                    processes.append({
                        "user": parts[0] if pid_idx != 0 else '?',
                        "pid": parts[pid_idx],
                        "cpu": '0',
                        "mem": '0',
                        "stat": '?',
                        "cmd": parts[-1][:80],
                    })
            try:
                processes.sort(key=lambda p: float(p.get('cpu', '0').replace(',', '.')), reverse=True)
            except (ValueError, TypeError):
                pass
            result["processes"] = processes
            if not processes:
                result["processes_error"] = f"ps 输出为空或解析失败 (raw_len={len(ps_output)}, lines={len(lines)})"
    else:
        # exec 失败或无输出
        result["processes"] = []
        result["processes_error"] = f"容器内命令执行失败 (rc={rc2})" if rc2 != 0 else "无输出"

    # 网络（独立于进程解析，不因 ps 失败而跳过）
    if rc2 == 0 and out2:
        ps_parts_net = out2.split('===NET===') if '===NET===' in out2 else []
        net_output = ps_parts_net[-1].strip() if ps_parts_net else ''
        if net_output:
            net_ifaces = []
            for line in net_output.splitlines()[2:]:
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

    # ── 解析第三次 exec：挂载详情 ──────────────────────────────────────────
    if result.get("disk_mounts") and rc3 == 0 and out3 and out3.strip():
        mount_details = {}
        for ml in out3.strip().splitlines():
            ml = ml.strip()
            if not ml:
                continue
            # mountinfo 格式: 36 35 0:40 / /code rw,relatime - nfs4 10.0.0.1:/data /code rw,noacl
            mi_match = re.match(
                r'^\d+\s+\d+\s+\d+:\d+\s+\S+\s+(\S+)\s+(\S+)\s+.*?-\s+(\S+)\s+(\S+)\s+(.*)',
                ml
            )
            if mi_match:
                mnt_point = mi_match.group(1)
                mount_details[mnt_point] = {
                    "fs_type": mi_match.group(3),
                    "source": mi_match.group(4),
                    "options": mi_match.group(2),
                }
                continue
            # mount 命令格式: source on /mnt type nfs (rw,addr=10.0.0.1)
            mt_match = re.match(r'^(\S+)\s+on\s+(\S+)\s+type\s+(\S+)\s+\((.+)\)', ml)
            if mt_match:
                mnt_point = mt_match.group(2)
                mount_details[mnt_point] = {
                    "fs_type": mt_match.group(3),
                    "source": mt_match.group(1),
                    "options": mt_match.group(4),
                }

        # 将挂载详情合并到 disk_mounts
        for dm in result["disk_mounts"]:
            detail = mount_details.get(dm["mount"])
            if detail:
                dm["fs_type"] = detail.get("fs_type", "")
                dm["mount_source"] = detail.get("source", "")
                dm["mount_options"] = detail.get("options", "")

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
    优化：并发执行 kubectl 调用，合并容器内 exec 命令
    """
    import concurrent.futures
    ts = datetime.now().isoformat()

    # 1. Pod JSON（必须先获取，确定 target_container）
    pod_json = runner.get_pod_json(ns, pod)
    if pod_json is None:
        return {"error": "Pod 不存在或无法访问", "timestamp": ts}

    pod_info = parse_pod_info(pod_json)

    # 确定要监控的容器
    target_container = container
    if not target_container and pod_info["containers"]:
        target_container = pod_info["containers"][0]["name"]

    # 2. 并发采集 top metrics / 容器内部指标 / 事件
    top_metrics = {}
    container_metrics = {}
    events = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_top = executor.submit(runner.get_pod_metrics, ns, pod)
        future_events = executor.submit(runner.get_pod_events, ns, pod)

        # 容器内部指标仅 Running 状态才采集
        future_metrics = None
        if pod_info["phase"] == "Running":
            future_metrics = executor.submit(
                collect_container_metrics, runner, ns, pod, target_container)

        top_raw = future_top.result()
        if top_raw:
            top_metrics = parse_top_metrics(top_raw["cpu_raw"] + " " + top_raw["memory_raw"])

        events = future_events.result()

        if future_metrics:
            container_metrics = future_metrics.result()

    return {
        "timestamp": ts,
        "pod_info": pod_info,
        "top_metrics": top_metrics,
        "container_metrics": container_metrics,
        "processes": container_metrics.get("processes", []),  # 顶层兼容：前端 renderProcs 优先读 snap.processes
        "processes_error": container_metrics.get("processes_error", "" if container_metrics.get("processes") else ("Pod 未 Running，跳过容器内采集" if pod_info.get("phase") != "Running" else "")),
        "events": events[:20],
        "target_container": target_container,
    }


# ── 后台轮询（存入历史缓冲）──────────────────────────────────────────────────────

_poll_threads = {}  # type: Dict[str, threading.Thread]  # key -> thread
_poll_stop = {}     # type: Dict[str, bool]  # key -> bool


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


def get_metrics_history(cluster: str, ns: str, pod: str):  # type: (str, str, str) -> list
    key = f"{cluster}/{ns}/{pod}"
    with _metrics_lock:
        return list(_metrics_history.get(key, []))
