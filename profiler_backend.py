#!/usr/bin/env python3
"""
K8s Arthas Diagnostic Tool - Core Backend
架构分层:
  Layer 1: KubectlExecutor     - kubectl 原语封装
  Layer 2: ArthasAgentManager  - Pod 内 Arthas agent 生命周期
  Layer 3: ArthasHttpClient    - Arthas HTTP API 调用
  Layer 4: ArthasConnection    - 完整连接管理（agent + port-forward + client）
  Layer 5: ProfilerWorkflow    - 采样业务编排
官方文档: https://arthas.aliyun.com/en/doc/http-api.html
"""
import subprocess, socket, time, os, json, logging, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

ARTHAS_DEFAULT_JAR  = "/app/arthas/arthas-boot.jar"
ARTHAS_HTTP_PORT    = 8563   # 官方默认
ARTHAS_TELNET_PORT  = 3658   # 官方默认
PF_BASE_PORT        = 39200  # 本地 port-forward 起始端口

# ═══════════════════════════════════════════════════════════════════════════════
# Thread Dump HTML 模板（独立函数，与主业务逻辑完全分离）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_threaddump_html(
    pod_name: str,
    namespace: str,
    ts: str,
    thread_count: int,
    running_count: int,
    waiting_count: int,
    blocked_count: int,
    deadlock_count: int,
    threads_data: list,
    raw_html: str,       # HTML-escaped 原始文本（用于 Raw Text 视图）
    json_threads: str,   # JSON 序列化后的线程数组字符串
) -> str:
    """
    生成线程 Dump 的 HTML 报告。
    纯数据转换函数，不依赖任何实例状态，可独立测试。
    """
    import html as _html

    ts_fmt = f"{ts[:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:]}"
    deadlock_badge = (
        f"<div class=\"stat\" style=\"border-color:#f7768e\">"
        f"<b style=\"color:#f7768e\">{deadlock_count}</b>DEADLOCK</div>"
        if deadlock_count else ""
    )

    # ── Pre-build all variable parts to avoid backslash-in-f-string issues ──
    # Python f-string does not allow backslash inside {} expressions.
    # Single quotes in onclick attributes MUST use &apos; or be placed outside f-string.
    p_name_esc = _html.escape(pod_name)
    ns_esc     = _html.escape(namespace)

    # Toolbar buttons — use double-quoted onclick attrs, single-quoted JS args via &apos;
    btn_all = f'<button class="tbtn on" onclick="filt(&apos;all&apos;,this)">All ({thread_count})</button>'
    btn_r   = f'<button class="tbtn" onclick="filt(&apos;r&apos;,this)">🟢 RUNNABLE ({running_count})</button>'
    btn_w   = f'<button class="tbtn" onclick="filt(&apos;w&apos;,this)">🟠 WAITING ({waiting_count})</button>'
    btn_b   = f'<button class="tbtn" onclick="filt(&apos;b&apos;,this)">🔴 BLOCKED ({blocked_count})</button>'
    summary = f"共 {thread_count} 个线程 · RUNNABLE={running_count} · WAITING(含TIMED)={waiting_count} · BLOCKED={blocked_count}"

    # JS innerHTML toggle — use double-quote string in JS to avoid single-quote conflict

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>Thread Dump — {p_name_esc}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#1a1b26;color:#a9b1d6;font-family:'JetBrains Mono','Fira Code','Consolas',monospace;font-size:13px;line-height:1.6}}
.header{{background:#16161e;border-bottom:1px solid #292e42;padding:14px 20px;position:sticky;top:0;z-index:100}}
.h-title{{font-size:15px;font-weight:700;color:#c0caf5;margin-bottom:6px}}
.h-meta{{font-size:11px;color:#565f89;margin-bottom:8px}}
.stats{{display:flex;gap:10px;flex-wrap:wrap}}
.stat{{background:#1a1b26;border:1px solid #292e42;border-radius:5px;padding:4px 12px;font-size:11px;color:#9aa5ce}}
.stat b{{font-size:15px;display:block}}
.stat.s-run b{{color:#9ece6a}}.stat.s-blk b{{color:#f7768e}}.stat.s-wai b{{color:#ff9e64}}.stat.s-all b{{color:#7aa2f7}}
.toolbar{{background:#16161e;border-bottom:1px solid #292e42;padding:7px 20px;display:flex;gap:7px;align-items:center;flex-wrap:wrap;position:sticky;top:61px;z-index:99}}
.tbtn{{background:#24283b;border:1px solid #292e42;border-radius:4px;color:#9aa5ce;padding:3px 10px;font-size:11px;cursor:pointer;font-family:inherit;transition:all .12s}}
.tbtn:hover{{background:#292e42;color:#c0caf5}}.tbtn.on{{background:#2d3f6c;border-color:#7aa2f7;color:#7aa2f7}}
#qsearch{{background:#1a1b26;border:1px solid #3b4261;border-radius:4px;color:#a9b1d6;padding:3px 10px;font-size:11px;font-family:inherit;width:220px;outline:none}}
#qsearch:focus{{border-color:#7aa2f7}}
.mcnt{{font-size:11px;color:#565f89;min-width:80px}}
.tog{{font-size:11px;color:#565f89;cursor:pointer;text-decoration:underline;padding:0 3px}}.tog:hover{{color:#9aa5ce}}
.content{{padding:12px 20px 60px}}
.tb{{margin-bottom:1px;border-radius:3px;border-left:3px solid #292e42}}
.tb.r{{border-left-color:#9ece6a}}.tb.b{{border-left-color:#f7768e;background:rgba(247,118,142,.03)}}
.tb.w{{border-left-color:#ff9e64;background:rgba(255,158,100,.02)}}.tb.tw{{border-left-color:#e0af68}}
.tb.hid{{display:none}}
.th{{cursor:pointer;padding:4px 8px;border-radius:2px;display:flex;align-items:baseline;gap:6px;font-size:12px;user-select:none}}
.th:hover{{background:rgba(255,255,255,.04)}}
.th-name{{color:#c0caf5;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:420px}}
.th-id{{color:#565f89;font-size:11px;white-space:nowrap}}
.th-cpu{{color:#9ece6a;font-size:10px;background:rgba(158,206,106,.1);border-radius:3px;padding:0 5px}}
.th-dt{{color:#ff9e64;font-size:10px}}
.th-state{{margin-left:auto;font-size:10px;border-radius:3px;padding:1px 6px;font-weight:600;flex-shrink:0}}
.th-state.r{{color:#9ece6a;background:rgba(158,206,106,.1)}}.th-state.b{{color:#f7768e;background:rgba(247,118,142,.1)}}
.th-state.w,.th-state.tw{{color:#ff9e64;background:rgba(255,158,100,.1)}}.th-state.o{{color:#9aa5ce;background:rgba(154,165,206,.1)}}
.th-arrow{{color:#565f89;font-size:9px;transition:transform .12s;flex-shrink:0;width:12px}}
.tb.open .th-arrow{{transform:rotate(90deg)}}
.tbody{{display:none;padding:0 8px 6px 16px;font-size:12px}}.tb.open .tbody{{display:block}}
.tm{{color:#565f89;font-size:11px;padding:2px 0}}
.tf{{color:#565f89;padding:1px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tf .pkg{{color:#3b4261}}.tf .cls{{color:#7dcfff}}.tf .mth{{color:#73daca}}.tf .loc{{color:#e0af68}}.tf .nat{{color:#ff9e64}}
.lw{{color:#f7768e;font-size:11px;padding:2px 0}}
.sum{{background:#24283b;border-radius:4px;padding:6px 12px;font-size:11px;color:#565f89;margin-bottom:8px}}
pre.raw{{white-space:pre-wrap;word-break:break-all;padding:8px;font-size:11px;color:#565f89;display:none;line-height:1.5}}
</style></head><body>
<div class="header">
  <div class="h-title">🧵 Thread Dump &nbsp;<span style="font-weight:400;color:#565f89;font-size:12px">— {p_name_esc}</span></div>
  <div class="h-meta">Namespace: {ns_esc} &nbsp;·&nbsp; Time: {ts_fmt} &nbsp;·&nbsp; Command: thread -n 9999</div>
  <div class="stats">
    <div class="stat s-all"><b>{thread_count}</b>Total</div>
    <div class="stat s-run"><b>{running_count}</b>RUNNABLE</div>
    <div class="stat s-wai"><b>{waiting_count}</b>WAITING</div>
    <div class="stat s-blk"><b>{blocked_count}</b>BLOCKED</div>
    {deadlock_badge}
  </div>
</div>
<div class="toolbar">
  {btn_all}
  {btn_r}
  {btn_w}
  {btn_b}
  <span style="margin-left:auto"></span>
  <input id="qsearch" placeholder="Filter thread / class..." oninput="qsrch(this.value)">
  <span class="mcnt" id="mcnt"></span>
  <button class="tbtn" onclick="togRaw()" id="rawBtn">Raw Text</button>
  <span class="tog" onclick="togAll(true)">Expand all</span>
  <span class="tog" onclick="togAll(false)">Collapse all</span>
</div>
<div class="content">
  <div class="sum">{summary}</div>
  <div id="blocks"></div>
  <pre class="raw" id="raw">{raw_html}</pre>
</div>
<script>
const THREADS={json_threads};
function sc(s){{return s==='RUNNABLE'?'r':s==='BLOCKED'?'b':s==='WAITING'?'w':s==='TIMED_WAITING'?'tw':'o'}}
function sl(s){{return s==='TIMED_WAITING'?'T_WAIT':s||'?'}}
function fmtF(f){{
  var ln=f.lineNumber,cls=f.className||'',mth=f.methodName||'',fn=f.fileName||'';
  var p=cls.split('.'),cn=p.pop(),pkg=p.join('.');
  var loc=ln===-2?'<span class="nat">Native Method</span>':fn?'<span class="loc">'+fn+':'+ln+'</span>':'<span class="loc">Unknown</span>';
  return '<div class="tf"><span class="pkg">'+(pkg?pkg+'.':'')+'</span><span class="cls">'+cn+'</span>.<span class="mth">'+mth+'</span>('+loc+')</div>';
}}
var C=document.getElementById('blocks');
THREADS.forEach(function(th){{
  var s=th.state||'',c=sc(s);
  var dm=th.daemon?' <span style="color:#565f89;font-size:10px">[D]</span>':'';
  var nat=th.inNative?' <span style="color:#ff9e64;font-size:10px">[native]</span>':'';
  var cpu=th.cpu!=null&&th.cpu>0?'<span class="th-cpu">'+th.cpu+'%</span>':'';
  var dt=th.deltaTime>0?'<span class="th-dt">+'+th.deltaTime+'ms</span>':'';
  var lw=th.lockName?'<div class="lw">⏸ waiting on <span style="color:#f7768e">'+th.lockName+'</span></div>':'';
  var frames=(th.stackTrace||[]).map(fmtF).join('');
  var meta=[th.group?'group='+th.group:'','prio='+th.priority,th.blockedCount>0?'blocked='+th.blockedCount:'',th.time!=null?'time='+th.time+'ms':''].filter(Boolean).join(' · ');
  var key=(th.name+' '+(th.stackTrace||[]).map(function(f){{return f.className+'.'+f.methodName}}).join(' ')).toLowerCase();
  var el=document.createElement('div');
  el.className='tb '+c;el.dataset.c=c;el.dataset.key=key;
  el.innerHTML=
    '<div class="th" onclick="this.parentElement.classList.toggle(&quot;open&quot;)">'+
    '<span class="th-arrow">►</span>'+
    '<span class="th-name">'+th.name+'</span>'+dm+nat+
    '<span class="th-id">Id='+th.id+'</span>'+cpu+dt+
    '<span class="th-state '+c+'">'+sl(s)+'</span></div>'+
    '<div class="tbody"><div class="tm">'+meta+'</div>'+lw+frames+'</div>';
  if(c==='b') el.classList.add('open');
  C.appendChild(el);
}});
function filt(s,btn){{
  document.querySelectorAll('.tbtn').forEach(function(b){{b.classList.remove('on')}});
  if(btn) btn.classList.add('on');
  document.querySelectorAll('.tb').forEach(function(el){{
    var ec=el.dataset.c;
    var show=s==='all'||ec===s||(s==='w'&&(ec==='w'||ec==='tw'));
    el.classList.toggle('hid',!show);
  }});
  qsrch(document.getElementById('qsearch').value);
}}
function qsrch(q){{
  q=q.toLowerCase().trim();var n=0;
  document.querySelectorAll('.tb:not(.hid)').forEach(function(el){{
    var m=!q||el.dataset.key.includes(q);
    el.style.opacity=m?'1':'0.15';if(m&&q)n++;
  }});
  document.getElementById('mcnt').textContent=q?n+' matched':'';
}}
function togRaw(){{
  var raw=document.getElementById('raw'),btn=document.getElementById('rawBtn');
  var blk=document.getElementById('blocks'),show=raw.style.display!=='block';
  raw.style.display=show?'block':'none';blk.style.display=show?'none':'';
  btn.textContent=show?'Structured':'Raw Text';btn.classList.toggle('on',show);
}}
function togAll(o){{
  document.querySelectorAll('.tb').forEach(function(el){{if(o)el.classList.add('open');else el.classList.remove('open')}});
}}
</script></body></html>"""




# ═══════════════════════════════════════════════════════════════════════════════
# Layer 0: Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ClusterConfig:
    name: str
    kubeconfig: str
    context: str = ""

@dataclass
class PodTarget:
    cluster_name: str
    namespace: str
    pod_name: str
    container: str        = ""
    arthas_jar: str       = ARTHAS_DEFAULT_JAR
    arthas_http_port: int = ARTHAS_HTTP_PORT
    arthas_telnet_port: int = ARTHAS_TELNET_PORT


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1: KubectlExecutor  —  all kubectl primitives
# ═══════════════════════════════════════════════════════════════════════════════

class KubectlExecutor:
    """封装所有 kubectl 操作。不包含业务逻辑。"""

    def __init__(self, kubeconfig: str, context: str = ""):
        self.kubeconfig = kubeconfig
        self.context    = context

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
            start_new_session=True,   # detach so SIGINT doesn't kill it
        )

    # ── file transfer ─────────────────────────────────────────────────────────

    def cp_from_pod(self, namespace: str, pod: str, container: str,
                    pod_path: str, local_path: str) -> Tuple[int, str, str]:
        """
        三级降级策略下载 Pod 内文件:
          1. kubectl cp <pod>:<src> <local> -n <ns>   flags 后置
          2. kubectl exec -- cat 管道               绕开 cp 参数解析
          3. kubectl exec -- base64                  二进制兜底
        """
        import base64 as _b64, os as _os
        import subprocess as _sp

        if not pod or not pod_path:
            return -1, "", "pod 和 pod_path 不能为空"

        # ── 方法1: kubectl cp（flags 在 src/dest 之后）──────────────────────────
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

        # ── 方法2: kubectl exec -- cat ──────────────────────────────────────────
        cmd2 = self._base_cmd() + ["-n", namespace, "exec", pod]
        if container:
            cmd2 += ["-c", container]
        cmd2 += ["--", "cat", pod_path]
        try:
            # capture_output=True (binary), do NOT use text=True for .jfr/.hprof
            r2 = _sp.run(cmd2, capture_output=True, timeout=120)
            if r2.returncode == 0 and r2.stdout:
                with open(local_path, "wb") as f:
                    f.write(r2.stdout)
                return 0, "", ""
            err2 = r2.stderr.decode(errors="replace").strip()
        except Exception as e2:
            err2 = str(e2)

        log.warning("exec+cat failed (%s), fallback to base64", err2)

        # ── 方法3: base64 兜底 ───────────────────────────────────────────────────
        cmd3 = self._base_cmd() + ["-n", namespace, "exec", pod]
        if container:
            cmd3 += ["-c", container]
        cmd3 += ["--", "sh", "-c", f"base64 '{pod_path}'"]
        try:
            r3 = _sp.run(cmd3, capture_output=True, text=True, timeout=120)
            if r3.returncode == 0 and r3.stdout.strip():
                with open(local_path, "wb") as f:
                    f.write(_b64.b64decode(r3.stdout.replace("\n", "").strip()))
                return 0, "", ""
            err3 = r3.stderr.strip()
        except Exception as e3:
            err3 = str(e3)

        return -1, "", (
            f"所有下载方式均失败\n"
            f"kubectl cp: {err1}\ncat: {err2}\nbase64: {err3}"
        )

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
        return out if rc == 0 else err

    def get_top_pod(self, namespace: str, pod: str) -> Optional[dict]:
        """kubectl top pod (需要 metrics-server)"""
        rc, out, _ = self._run(
            ["-n", namespace, "top", "pod", pod, "--no-headers"], timeout=15)
        if rc != 0 or not out.strip():
            return None
        parts = out.split()
        if len(parts) < 3:
            return None
        def parse_cpu(s):
            return float(s[:-1]) if s.endswith("m") else float(s) * 1000
        def parse_mem(s):
            s = s.upper()
            for suf, mul in [("KI",1024),("MI",1024**2),("GI",1024**3),
                              ("K",1000),("M",1000**2),("G",1000**3)]:
                if s.endswith(suf):
                    return int(s[:-len(suf)]) * mul
            return int(s) if s.isdigit() else 0
        return {
            "cpu_raw": parts[1],
            "memory_raw": parts[2],
            "cpu_millicores": parse_cpu(parts[1]),
            "memory_bytes": parse_mem(parts[2]),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 2: ArthasAgentManager  —  manage Arthas agent lifecycle inside Pod
# ═══════════════════════════════════════════════════════════════════════════════

class ArthasAgentManager:
    """
    负责在 Pod 内启动 / 检测 Arthas agent。
    仅与 Pod 内部交互，不感知本地端口。
    """

    def __init__(self, executor: KubectlExecutor, target: PodTarget):
        self.ex  = executor
        self.t   = target
        self._pid: Optional[int] = None

    def _exec(self, cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
        return self.ex.exec_pod(
            self.t.namespace, self.t.pod_name, self.t.container, cmd, timeout)

    # ── Java PID discovery ────────────────────────────────────────────────────

    def find_java_pid(self, force: bool = False) -> Optional[int]:
        if self._pid and not force:
            return self._pid

        # Try jps first, fall back to ps
        rc, out, _ = self._exec(
            "jps -l 2>/dev/null || ps -ef 2>/dev/null | grep java | grep -v grep")
        if rc != 0 or not out.strip():
            return None

        skip_keywords = ["arthas", "arthas-boot", "Jps", "jps"]
        for line in out.strip().splitlines():
            parts = line.strip().split(None, 1)
            if not parts or not parts[0].isdigit():
                continue
            pid  = int(parts[0])
            desc = parts[1].lower() if len(parts) > 1 else ""
            if any(k.lower() in desc for k in skip_keywords):
                continue
            self._pid = pid
            return pid
        return None

    # ── Arthas agent check / start ────────────────────────────────────────────

    def _http_reachable(self) -> bool:
        """Pod 内 Arthas HTTP 端口是否在响应（任何 HTTP 状态码均视为服务已启动）。"""
        rc, out, _ = self._exec(
            f"curl -sf --max-time 3 http://127.0.0.1:{self.t.arthas_http_port}/api "
            f"-o /dev/null -w '%{{http_code}}' 2>/dev/null",
            timeout=6,
        )
        return rc == 0 and out.strip() in ("200", "400", "404")

    def _find_arthas_pids(self) -> List[int]:
        """
        返回 Pod 内所有 arthas-boot 进程的 PID 列表。
        用于检查是否有残留进程，决策是否 kill 再重启。
        """
        rc, out, _ = self._exec(
            "ps -ef 2>/dev/null | grep -i 'arthas-boot\\|arthas.jar' | grep -v grep || true",
            timeout=8,
        )
        pids = []
        if rc == 0 and out.strip():
            for line in out.strip().splitlines():
                parts = line.split()
                # ps -ef 格式: UID PID PPID ...
                if len(parts) >= 2 and parts[1].isdigit():
                    pids.append(int(parts[1]))
        return pids

    def _kill_stale_arthas(self, pids: List[int]) -> str:
        """
        清理残留 arthas-boot 进程。
        只清理引导进程，不影响被 attach 的目标 Java 应用进程。
        """
        if not pids:
            return ""
        pid_str = " ".join(str(p) for p in pids)
        # 先 SIGTERM，等 1s，再 SIGKILL
        self._exec(
            f"kill {pid_str} 2>/dev/null; sleep 1; "
            f"kill -9 {pid_str} 2>/dev/null; true",
            timeout=8,
        )
        log.info("Killed stale arthas pids: %s", pid_str)
        return f"已清理残留进程 {pid_str}"

    def _resolve_jar(self) -> bool:
        """确认 JAR 路径可用；找不到时按优先级探测备选路径。"""
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
        return False

    def ensure_agent_running(self) -> Tuple[bool, str]:
        """
        确保 Arthas agent 在 Pod 内运行，严格防止重复启动。

        决策树（按顺序）:
        ┌─ HTTP 可达？
        │   └── YES → 直接复用，什么都不做
        │   └── NO
        │        ├─ 有残留 arthas-boot 进程？→ kill 全部（防止重复 attach）
        │        ├─ 找目标 Java PID（排除 arthas 自身）
        │        ├─ 确认 JAR 路径（自动探测备选）
        │        └─ nohup 启动，最多等 40s 直到 HTTP 就绪
        """
        port = self.t.arthas_http_port

        # ── 情况 A: HTTP 已响应，直接复用 ─────────────────────────────────────
        if self._http_reachable():
            log.info("Arthas HTTP already reachable on port %d — reusing", port)
            return True, f"Arthas 已在运行，直接复用 (port {port})"

        # ── 情况 B: HTTP 不通，先清理残留进程 ────────────────────────────────
        stale_pids = self._find_arthas_pids()
        cleanup_msg = ""
        if stale_pids:
            cleanup_msg = self._kill_stale_arthas(stale_pids)
            log.info(cleanup_msg)
            time.sleep(1)   # 等进程彻底退出

        # ── 情况 C: 找目标 Java PID ───────────────────────────────────────────
        pid = self.find_java_pid()
        if not pid:
            return False, "未找到 Java 进程，请确认 JVM 已启动"

        # ── 情况 D: 确认 JAR ─────────────────────────────────────────────────
        if not self._resolve_jar():
            return False, (
                f"Arthas JAR 不存在: {self.t.arthas_jar}\n"
                "请在左侧配置正确路径，或在 Pod 内安装 Arthas:\n"
                "  curl -Lo /app/arthas/arthas-boot.jar "
                "https://arthas.aliyun.com/arthas-boot.jar"
            )

        # ── 情况 E: 启动 ─────────────────────────────────────────────────────
        #
        # 官方正确用法（arthas-boot.jar 参数规范）：
        #   java -Darthas.httpPort=N -Darthas.telnetPort=N -jar arthas-boot.jar <TARGET_PID>
        #
        # ⚠  不要用 --http-port / --telnet-port
        #    这些是 arthas-core.jar 的参数，arthas-boot.jar 不识别，会打印 help 退出
        #    参考：https://arthas.aliyun.com/en/doc/arthas-properties.html
        #
        start_cmd = (
            f"nohup java"
            f" -Darthas.httpPort={port}"
            f" -Darthas.telnetPort={self.t.arthas_telnet_port}"
            f" -Darthas.ip=127.0.0.1"
            f" -jar {self.t.arthas_jar}"
            f" {pid}"
            f" > /tmp/arthas_start.log 2>&1 </dev/null &"
            f" echo started_pid=$!"
        )
        rc_s, out_s, _ = self._exec(start_cmd, timeout=15)
        log.info("Arthas start: rc=%d pid=%d jar=%s out=%s cleanup=%s",
                 rc_s, pid, self.t.arthas_jar, out_s.strip(), cleanup_msg)

        # ── 轮询等待 HTTP 就绪（max 40s）────────────────────────────────────
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


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 3: ArthasHttpClient  —  Arthas HTTP API calls
# ═══════════════════════════════════════════════════════════════════════════════

class ArthasHttpClient:
    """
    Arthas HTTP API 客户端。
    通过本地 port-forward 端口访问 Pod 内 Arthas。
    官方文档: https://arthas.aliyun.com/en/doc/http-api.html
    """

    def __init__(self, local_port: int):
        self.url     = f"http://127.0.0.1:{local_port}/api"
        self.timeout = 35

    def _post(self, payload: dict, timeout: int = 0) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            self.url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            raw = resp.read().decode("utf-8").strip()

        # Arthas HTTP API 有时返回多行拼接 JSON：
        #   {"state":"SUCCEEDED"}
        #   {"body":{"command":"thread -n 9999","results":[...]}}
        # 需要合并成一个完整对象
        if raw.startswith("{"):
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            if len(lines) > 1:
                merged = {}
                for line in lines:
                    try:
                        merged.update(json.loads(line))
                    except Exception:
                        pass
                return merged
        return json.loads(raw)

    def ping(self, retries: int = 3, delay: float = 1.5) -> bool:
        """
        Ping with retry — port-forward TCP可通但HTTP层可能还在初始化。
        等待最多 retries*delay 秒。
        """
        for i in range(retries):
            try:
                r = self._post({"action": "exec", "command": "version"}, timeout=5)
                if r.get("state") in ("SUCCEEDED", "succeeded"):
                    return True
            except Exception as e:
                log.debug("ping attempt %d failed: %s", i+1, e)
            if i < retries - 1:
                time.sleep(delay)
        return False

    # ── One-shot commands ──────────────────────────────────────────────────────

    def exec_once(self, command: str, timeout_ms: int = 30000) -> dict:
        return self._post({
            "action": "exec",
            "command": command,
            "execTimeout": str(timeout_ms),
        }, timeout=timeout_ms // 1000 + 5)

    # ── Session commands ───────────────────────────────────────────────────────

    def init_session(self) -> dict:
        return self._post({"action": "init_session"})

    def exec_async(self, session_id: str, command: str) -> dict:
        return self._post({
            "action": "async_exec",
            "sessionId": session_id,
            "command": command,
        })

    def pull_results(self, session_id: str, consumer_id: str) -> dict:
        return self._post({
            "action": "pull_results",
            "sessionId": session_id,
            "consumerId": consumer_id,
        }, timeout=12)

    def interrupt_job(self, session_id: str) -> dict:
        return self._post({"action": "interrupt_job", "sessionId": session_id})

    def close_session(self, session_id: str) -> dict:
        return self._post({"action": "close_session", "sessionId": session_id})


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 4: ArthasConnection  —  connection lifecycle management
# ═══════════════════════════════════════════════════════════════════════════════

class ArthasConnection:
    """
    管理单个 Pod 的完整 Arthas 连接:
      1. ArthasAgentManager → 确保 Pod 内 agent 运行
      2. kubectl port-forward → 本地端口
      3. ArthasHttpClient   → HTTP API 可用
    """

    _port_counter = PF_BASE_PORT   # class-level port allocator

    def __init__(self, executor: KubectlExecutor, target: PodTarget):
        self.executor     = executor
        self.target       = target
        self.agent_mgr    = ArthasAgentManager(executor, target)
        self.client:      Optional[ArthasHttpClient]    = None
        self._pf_proc:    Optional[subprocess.Popen]    = None
        self.local_port:  int  = 0
        self.java_pid:    Optional[int] = None

    # ── Port allocation ────────────────────────────────────────────────────────

    @classmethod
    def _alloc_port(cls) -> int:
        cls._port_counter += 1
        return cls._port_counter

    # ── Port-forward helpers ───────────────────────────────────────────────────

    def _stop_port_forward(self):
        if self._pf_proc:
            try:
                self._pf_proc.terminate()
                self._pf_proc.wait(timeout=3)
            except Exception:
                pass
            self._pf_proc = None

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
        """
        建立完整的 Arthas 连接，防止重复操作。

        短路规则（按优先级）:
          1. client 已存活 → 直接返回，不重复 port-forward
          2. agent 已在 Pod 内运行 → 只建立 port-forward，跳过启动
          3. 全新启动 → agent + port-forward + ping
        """
        # ── 短路 1: 当前 client 仍然存活 ──────────────────────────────────────
        if self.client and self.client.ping(retries=1, delay=0):
            log.info("ArthasConnection already alive (port=%d) — reusing", self.local_port)
            return True, f"已连接，复用 (port {self.local_port})"

        # 若 client 已失效但 port-forward 还在，先停掉
        if self._pf_proc:
            self._stop_port_forward()
            self.client = None

        # ── Step 1: 确保 agent 在 Pod 内运行 ──────────────────────────────────
        ok, agent_msg = self.agent_mgr.ensure_agent_running()
        if not ok:
            return False, agent_msg
        self.java_pid = self.agent_mgr._pid
        log.info("Agent ready: %s", agent_msg)

        # ── Step 2: 建立 port-forward ─────────────────────────────────────────
        ok, pf_msg = self._start_port_forward()
        if not ok:
            return False, pf_msg
        log.info("Port-forward: %s", pf_msg)

        # ── Step 3: 等待 HTTP API 就绪（TCP 连通 ≠ HTTP 初始化完成）────────────
        client = ArthasHttpClient(self.local_port)
        if client.ping(retries=8, delay=2.0):
            self.client = client
            return True, f"连接成功 · {agent_msg} · {pf_msg}"

        # ── 诊断：收集启动日志 ────────────────────────────────────────────────
        _, log_tail, _ = self.executor.exec_pod(
            self.target.namespace, self.target.pod_name, self.target.container,
            "tail -15 /tmp/arthas_start.log 2>/dev/null", timeout=5)
        self._stop_port_forward()
        return False, (
            f"port-forward TCP 就绪，但 Arthas HTTP API 未响应\n"
            f"可能原因: JVM attach 耗时长 / 端口冲突 / JVM 版本不兼容\n"
            f"启动日志:\n{log_tail[:400]}"
        )

    def is_alive(self) -> bool:
        if not self.client:
            return False
        return self.client.ping(retries=1, delay=0)

    def disconnect(self):
        self._stop_port_forward()
        self.client     = None
        self.local_port = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 5: ProfilerWorkflow  —  business orchestration for JProfiler sampling
# ═══════════════════════════════════════════════════════════════════════════════


class ProfilerWorkflow:
    """
    性能分析任务编排，支持 4 种模式:

    mode='profiler'  — async-profiler (profiler start/stop)
        支持事件: cpu / alloc / lock / wall / itimer / cache-misses
        输出格式: html(火焰图) / jfr(async-profiler jfr) / collapsed / md
        命令示例: profiler start --event cpu
                  profiler stop --format html --file /tmp/result.html
        适用: 所有 JDK 版本，低开销

    mode='jfr'       — JDK Flight Recorder (jfr start/stop)
        JDK 11+ 专用，通过 Arthas jfr 命令控制
        命令示例: jfr start -n myRec -s default -d 60s -f /tmp/myRec.jfr
                  jfr stop -n myRec
                  jfr dump -n myRec -f /tmp/myRec.jfr
        输出: .jfr 文件，用 JDK Mission Control 分析

    mode='threaddump' — 线程 Dump
        命令: thread -all  (包含所有线程栈信息)
        用途: 分析死锁、线程卡顿、CPU 飙高

    mode='heapdump'   — Heap Dump
        命令: heapdump [--live] <file>
        用途: 分析内存泄漏、OOM
        注意: 会触发 Full GC + STW，生产环境慎用

    资料来源:
      async-profiler: https://arthas.aliyun.com/en/doc/profiler.html
      JDK JFR:        https://arthas.aliyun.com/en/doc/jfr.html
      thread dump:    https://arthas.aliyun.com/en/doc/thread.html
      heap dump:      https://arthas.aliyun.com/en/doc/heapdump.html
    """

    def __init__(self, conn: ArthasConnection):
        self.conn       = conn
        self.logs: list = []
        self.result     = {"status": "running", "local_file": "", "message": ""}
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _log(self, msg: str, level: str = "info"):
        entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "message": msg}
        self.logs.append(entry)
        log.info("[%s] %s", level, msg)

    def snapshot(self) -> dict:
        return {
            "status": self.result["status"],
            "logs":   list(self.logs),
            "result": dict(self.result),
        }

    def run(self, duration: int, fmt: str, output_dir: str,
            mode: str = 'profiler', event: str = 'cpu',
            jfr_name: str = 'arthas-jfr', jfr_settings: str = 'default',
            jfr_file: str = '', heap_file: str = '',
            heap_live: bool = True, **_) -> dict:
        """
        统一入口。mode 决定工作流:
          profiler  — async-profiler (所有 JDK)
          jfr       — JDK Flight Recorder (JDK 11+)
          threaddump — 线程快照
          heapdump  — 堆内存快照
        """
        t  = self.conn.target
        ex = self.conn.executor
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d%H%M%S")

        self._log(f"目标: {t.namespace}/{t.pod_name}  模式={mode}  格式={fmt}  事件={event}  时长={duration}s", "dim")

        # ① Pod 状态检查
        self._log("① 检查 Pod 状态...")
        phase = ex.get_pod_phase(t.namespace, t.pod_name)
        if phase != "Running":
            return self._fail(f"Pod 状态异常: {phase or '无法获取'}")
        self._log("Pod Running ✓", "success")

        # ② Arthas 连接
        self._log("② 连接 Arthas HTTP API...")
        ok, msg = self.conn.connect()
        if not ok:
            return self._fail(msg)
        self._log(msg + " ✓", "success")
        client = self.conn.client

        # ③ 根据 mode 分发
        if mode == 'threaddump':
            return self._run_threaddump(ex, t, client, output_dir, ts)
        elif mode == 'heapdump':
            return self._run_heapdump(ex, t, client, output_dir, ts, heap_file, heap_live)
        elif mode == 'jfr':
            return self._run_jfr(ex, t, client, output_dir, ts,
                                  duration, jfr_name, jfr_settings, jfr_file)
        else:
            return self._run_profiler(ex, t, client, output_dir, ts,
                                       duration, fmt, event)

    # ─────────────────────────────────────────────────────────────────────────
    # async-profiler 采样
    # 官方文档: https://arthas.aliyun.com/en/doc/profiler.html
    # 支持事件: cpu / alloc / lock / wall / itimer / cache-misses
    # ─────────────────────────────────────────────────────────────────────────
    def _run_profiler(self, ex, t, client, output_dir, ts,
                      duration, fmt, event) -> dict:
        ext     = 'html' if fmt in ('html', 'flamegraph') else fmt
        # 文件名含事件类型，便于区分：profiler-cpu-xxx.html / profiler-alloc-xxx.jfr
        pod_out = f"/tmp/arthas-profiler-{event}-{t.pod_name}-{ts}.{ext}"

        self._log(f"③ async-profiler 采样  事件={event}  格式={fmt}  时长={duration}s", "dim")

        # ③ profiler start — 必须用 Session 异步模式
        # profiler start 是持续运行命令，exec_once 会超时被 INTERRUPT
        self._log("③ 启动 async-profiler（Session 模式）...")
        try:
            sess = client.init_session()
            if sess.get("state") not in ("SUCCEEDED", "succeeded"):
                return self._fail(f"创建 Session 失败: {json.dumps(sess)[:200]}")
            session_id  = sess["sessionId"]
            consumer_id = sess["consumerId"]

            start_cmd  = f"profiler start --event {event}"
            start_resp = client.exec_async(session_id, start_cmd)
            self._log(f"   async_exec: {json.dumps(start_resp)[:120]}", "dim")
            if start_resp.get("state") == "FAILED":
                return self._fail(f"profiler start 失败: {json.dumps(start_resp)[:200]}")

            time.sleep(3)
            pull = client.pull_results(session_id, consumer_id)
            pull_raw = json.dumps(pull, ensure_ascii=False)
            self._log(f"   pull: {pull_raw[:120]}", "dim")
            if "error" in pull_raw.lower() and "started" not in pull_raw.lower():
                return self._fail(f"profiler start 异常: {pull_raw[:300]}")
        except Exception as e:
            return self._fail(f"profiler start 异常: {e}")

        self._log(f"async-profiler [{event}] 采样已启动 ✓", "success")
        self.result["start_time"] = datetime.now().isoformat()

        # ④ 倒计时
        self._log(f"④ 采样中，共 {duration} 秒...")
        for i in range(duration):
            if self._cancelled:
                self._log("⚠ 采样被中止，保存当前数据...", "warn")
                break
            time.sleep(1)
            if (i + 1) % 10 == 0:
                self._log(f"   进度 {i+1}/{duration}s", "dim")

        try:
            client.close_session(session_id)
        except Exception:
            pass

        # ⑤ profiler stop
        self._log(f"⑤ 停止采样，导出 {fmt}...")
        stop_cmd  = f"profiler stop --format {fmt} --file {pod_out}"
        stop_resp = client.exec_once(stop_cmd, timeout_ms=60000)
        stop_raw  = json.dumps(stop_resp, ensure_ascii=False)
        self._log(f"   stop 响应: {stop_raw}", "dim")

        state = stop_resp.get("state", "")
        if state not in ("SUCCEEDED", "succeeded"):
            return self._fail(f"profiler stop 失败 (state={state}): {stop_raw[:400]}")

        # 解析真实输出路径
        actual_path = pod_out
        try:
            for r in stop_resp.get("body", {}).get("results", []):
                for key in ("outputFile", "outputfile", "file", "fileName"):
                    val = r.get(key, "")
                    if val and isinstance(val, str) and "/" in val:
                        actual_path = val.strip()
                        self._log(f"   实际路径 [{key}]: {actual_path}", "dim")
                        break
                if actual_path != pod_out:
                    break
                import re as _re
                # 同时匹配 /tmp/ 和 /arthas-output/ 路径
                m = _re.search(r'(/(?:tmp|arthas-output|home/admin/arthas-output|root/arthas-output)/[^\s"\'\\]+\.' + ext + r')', json.dumps(r))
                if m:
                    actual_path = m.group(1)
        except Exception:
            pass

        if actual_path != pod_out:
            pod_out = actual_path

        return self._verify_and_download(ex, t, output_dir, ts, pod_out, ext)

    # ─────────────────────────────────────────────────────────────────────────
    # JDK Flight Recorder
    # 官方文档: https://arthas.aliyun.com/en/doc/jfr.html
    # 需要 JDK 11+，通过 Arthas jfr 命令控制 JVM 内置 JFR
    # ─────────────────────────────────────────────────────────────────────────
    def _run_jfr(self, ex, t, client, output_dir, ts,
                 duration, jfr_name, jfr_settings, jfr_file) -> dict:
        """
        JDK Flight Recorder via Arthas jfr 命令。
        官方文档: https://arthas.aliyun.com/en/doc/jfr.html

        关键事项:
          1. jfr start 返回 recording ID（如 "Recording 5"），stop 必须用 -r <id>
          2. 带 -d 参数时，文件在 duration 结束后自动落盘，无需手动 stop
          3. 文件需要在 start 时用 -f 指定；不指定则写到 arthas-output/
          4. jfr stop 只能执行一次（once per recording）
          5. 需要 JDK 8u262+ 或 JDK 11+
        """
        # 文件名后端生成，含 pod_name，不依赖前端传入
        jfr_file = f"/tmp/{jfr_name}-{t.pod_name[:30]}-{ts}.jfr"

        self._log("③ 启动 JDK JFR 录制（Arthas jfr 命令）", "dim")
        self._log("   注意: 需要 JDK 8u262+ 或 JDK 11+", "warn")
        self._log(f"   录制名={jfr_name}  设置={jfr_settings}  时长={duration}s", "dim")
        self._log(f"   输出文件={jfr_file}", "dim")

        # ── jfr start（带 -d 和 -f，录制结束后自动写文件）────────────────────
        # 官方示例: jfr start -n myRecording --duration 60s -f /tmp/myRecording.jfr
        start_cmd = (
            f"jfr start"
            f" -n {jfr_name}"
            f" -s {jfr_settings}"
            f" --duration {duration}s"
            f" -f {jfr_file}"
        )
        start_resp = client.exec_once(start_cmd, timeout_ms=15000)
        start_raw  = json.dumps(start_resp, ensure_ascii=False)
        self._log(f"   jfr start 响应: {start_raw[:300]}", "dim")

        # 检查启动状态
        state = start_resp.get("state", "")
        body  = json.dumps(start_resp.get("body", {}), ensure_ascii=False)
        if state not in ("SUCCEEDED", "succeeded"):
            if "not supported" in body.lower() or "jdk 11" in body.lower():
                return self._fail(
                    "JDK JFR 需要 JDK 8u262+ 或 JDK 11+，当前 JDK 不支持。"
                    "请改用 async-profiler 模式")
            return self._fail(f"jfr start 失败: {start_raw[:300]}")

        # 从响应里提取 recording ID（用于后续 status/stop/dump）
        # 响应示例: {"jfrOutput": "Recording 5 scheduled to ..."}
        recording_id = None
        import re as _re
        jfr_output = ""
        try:
            for r in start_resp.get("body", {}).get("results", []):
                jfr_output = r.get("jfrOutput", "")
                m = _re.search(r"Recording\s+(\d+)", jfr_output)
                if m:
                    recording_id = m.group(1)
                    break
        except Exception:
            pass

        self._log(f"JFR 录制已启动 ✓  recording_id={recording_id}  output={jfr_output[:80]}", "success")
        self._log(f"   说明: scheduled 表示录制将在 {duration}s 后自动完成并写入文件", "dim")
        self.result["start_time"] = datetime.now().isoformat()

        # ④ 倒计时等待录制完成
        # 带 -d 参数的 JFR 会在时间到后自动停止并写文件，不需要手动 stop
        self._log(f"④ JFR 录制中，共 {duration} 秒（自动停止）...")
        for i in range(duration):
            if self._cancelled:
                self._log("⚠ 手动中止，发送 jfr stop...", "warn")
                if recording_id:
                    client.exec_once(f"jfr stop -r {recording_id} -f {jfr_file}",
                                      timeout_ms=30000)
                break
            time.sleep(1)
            if (i + 1) % 10 == 0:
                self._log(f"   进度 {i+1}/{duration}s", "dim")

        # ⑤ 等待 JVM 完成文件写入（JFR 在 duration 结束后需要几秒落盘）
        self._log("⑤ 等待 JFR 文件落盘 (10s)...")
        for i in range(10):
            time.sleep(1)
            rc, ls_out, _ = ex.exec_pod(
                t.namespace, t.pod_name, t.container,
                f"ls -lh '{jfr_file}' 2>&1", timeout=5)
            if rc == 0 and " 0 " not in ls_out and "0B" not in ls_out:
                self._log(f"   文件已写入: {ls_out.strip()}", "success")
                break
            if i == 9:
                self._log(f"   文件状态: {ls_out.strip()}", "dim")

        # 若文件仍为 0，用 dump 强制触发写入（dump 不停止录制，只 flush 当前数据）
        rc, ls_out, _ = ex.exec_pod(
            t.namespace, t.pod_name, t.container,
            f"ls -lh '{jfr_file}' 2>&1", timeout=5)
        if rc != 0 or " 0 " in ls_out or "0B" in ls_out:
            self._log("   文件仍为 0，尝试 jfr dump...", "warn")
            if recording_id:
                dump_resp = client.exec_once(
                    f"jfr dump -r {recording_id} -f {jfr_file}", timeout_ms=30000)
                self._log(f"   jfr dump: {json.dumps(dump_resp)[:200]}", "dim")
            else:
                # 无 recording_id，按名称 dump
                dump_resp = client.exec_once(
                    f"jfr dump -n {jfr_name} -f {jfr_file}", timeout_ms=30000)
                self._log(f"   jfr dump (by name): {json.dumps(dump_resp)[:200]}", "dim")
            time.sleep(5)
            rc, ls_out, _ = ex.exec_pod(
                t.namespace, t.pod_name, t.container,
                f"ls -lh '{jfr_file}' 2>&1", timeout=5)
            self._log(f"   dump 后文件状态: {ls_out.strip()}", "dim")
            if " 0 " in ls_out or "0B" in ls_out:
                # 最后手段：扫描 arthas-output 目录
                self._log("   扫描 arthas-output 目录...", "dim")
                rc2, scan_out, _ = ex.exec_pod(
                    t.namespace, t.pod_name, t.container,
                    "ls -lt /arthas-output/*.jfr /tmp/*.jfr 2>/dev/null | head -5", timeout=5)
                if rc2 == 0 and scan_out.strip():
                    newest = scan_out.strip().splitlines()[0].split()[-1]
                    self._log(f"   找到候选文件: {newest}", "dim")
                    jfr_file = newest

        return self._verify_and_download(ex, t, output_dir, ts, jfr_file, "jfr")

    def _run_threaddump(self, ex, t, client, output_dir, ts) -> dict:
        """
        导出完整线程 Dump（含每个线程的堆栈）。

        命令策略（参考官方文档 https://arthas.aliyun.com/en/doc/thread.html）：
          - thread --all  → 只返回所有线程基本信息，无堆栈（不适合线程 Dump）
          - thread -n N   → 返回最忙的 N 个线程 + 完整堆栈（我们用 9999 等价 jstack）
          - thread -b     → 专项检测死锁/阻塞持锁线程

        响应结构: results[].threads = [{id, name, state, stackTrace:[{className,methodName,...}]}]
        """
        # ── Step 1: 获取所有线程完整堆栈（thread -n 9999 等价 jstack）─────────
        self._log("③ 导出完整线程 Dump（thread -n 9999，含堆栈）...")
        resp = client.exec_once("thread -n 9999", timeout_ms=60000)
        raw  = json.dumps(resp, ensure_ascii=False)
        self._log(f"   thread 响应: {raw[:150]}", "dim")

        if resp.get("state") not in ("SUCCEEDED", "succeeded"):
            return self._fail(f"thread -n 9999 失败: {raw[:300]}")

        # ── Step 2: 检测死锁（thread -b）────────────────────────────────────
        blocking_info = ""
        try:
            block_resp = client.exec_once("thread -b", timeout_ms=15000)
            block_raw  = json.dumps(block_resp, ensure_ascii=False)
            if "blockingThread" in block_raw or "deadlock" in block_raw.lower():
                blocking_info = block_raw
                self._log("   ⚠ 检测到阻塞/死锁信息！", "warn")
            else:
                self._log("   未发现死锁", "dim")
        except Exception as e:
            self._log(f"   thread -b 跳过: {e}", "dim")

        # ── Step 3: 解析线程数据 ─────────────────────────────────────────────
        # results[].threads 数组（thread -n N 的标准格式）
        threads_data = []
        try:
            for r in resp.get("body", {}).get("results", []):
                # busyThreads = thread -n N 的真实 key；threads = thread --all 的 key
                candidates = r.get("busyThreads") or r.get("threads") or []
                if candidates and isinstance(candidates, list):
                    threads_data = candidates
                    break
        except Exception as e:
            self._log(f"   解析异常: {e}", "warn")

        self._log(f"   解析到 {len(threads_data)} 个线程", "dim")

        # ── Step 4: 转成 jstack 风格文本 ────────────────────────────────────
        text_lines = [
            f"Full thread dump — {t.namespace}/{t.pod_name}",
            f"时间: {ts[:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:]}",
            f"线程数: {len(threads_data)}",
            "=" * 70,
            "",
        ]
        for th in threads_data:
            name   = th.get("name", "unknown")
            daemon = " daemon" if th.get("daemon") else ""
            prio   = th.get("priority", 5)
            tid    = th.get("id", 0)
            state  = th.get("state", "")
            cpu    = th.get("cpu", "")
            cpu_s  = f" cpu={cpu}%" if cpu else ""
            group  = th.get("group", "")

            text_lines.append(f'"{name}"{daemon} prio={prio} Id={tid}{cpu_s}')
            if group:
                text_lines.append(f'   group="{group}"')
            text_lines.append(f"   java.lang.Thread.State: {state}")
            if th.get("interrupted"):
                text_lines.append("   (interrupted)")

            for frame in th.get("stackTrace", []):
                cls  = frame.get("className", "")
                meth = frame.get("methodName", "")
                fn   = frame.get("fileName", "")
                ln   = frame.get("lineNumber", -1)
                if ln == -2:
                    text_lines.append(f"\tat {cls}.{meth}(Native Method)")
                elif fn:
                    text_lines.append(f"\tat {cls}.{meth}({fn}:{ln})")
                else:
                    text_lines.append(f"\tat {cls}.{meth}(Unknown Source)")

            for lk in (th.get("lockedMonitors") or []):
                text_lines.append(f"\t- locked <{lk.get('identityHashCode','?')}> ({lk.get('className','?')})")

            text_lines.append("")

        # 追加死锁信息
        if blocking_info:
            text_lines += ["", "=" * 70, "⚠ 阻塞/死锁检测结果 (thread -b):", "=" * 70, "", blocking_info]

        # 兜底：无线程数据时用原始 JSON
        if not threads_data:
            self._log("   未解析到结构化线程数据，使用原始响应", "warn")
            text_lines.append(raw)

        thread_text = "\n".join(text_lines)

        # 统计各状态线程数
        thread_count  = len(threads_data) if threads_data else 0
        blocked_count = sum(1 for th in threads_data if th.get("state") == "BLOCKED") if threads_data else 0
        waiting_count = sum(1 for th in threads_data if th.get("state") in ("WAITING","TIMED_WAITING")) if threads_data else 0
        running_count = sum(1 for th in threads_data if th.get("state") == "RUNNABLE") if threads_data else 0
        deadlock_count = thread_text.lower().count("deadlock")

        # 生成 HTML 报告（调用独立模板函数）
        import html as _html
        html_content = _build_threaddump_html(
            pod_name      = t.pod_name,
            namespace     = t.namespace,
            ts            = ts,
            thread_count  = thread_count,
            running_count = running_count,
            waiting_count = waiting_count,
            blocked_count = blocked_count,
            deadlock_count= deadlock_count,
            threads_data  = threads_data,
            raw_html      = _html.escape(thread_text),
            json_threads  = json.dumps(threads_data, ensure_ascii=False),
        )

        # 写本地 HTML 文件
        local_file = str(Path(output_dir) / f"threaddump-{t.pod_name}-{ts}.html")
        Path(local_file).write_text(html_content, encoding="utf-8")
        size_kb = Path(local_file).stat().st_size / 1024

        self._log(f"🎉 线程 Dump 完成！{local_file}  ({size_kb:.1f} KB)", "success")
        self._log(f"   含 {thread_count} 个线程  BLOCKED={blocked_count}  WAITING={waiting_count}", "dim")
        self.result.update({
            "status":     "completed",
            "local_file": local_file,
            "message":    f"完成，{thread_count} 线程 / {size_kb:.1f} KB",
        })
        return self.result

    # ─────────────────────────────────────────────────────────────────────────
    # Heap Dump
    # 官方文档: https://arthas.aliyun.com/en/doc/heapdump.html
    # ─────────────────────────────────────────────────────────────────────────
    def _run_heapdump(self, ex, t, client, output_dir, ts,
                       heap_file, heap_live) -> dict:
        if not heap_file:
            heap_file = f"/tmp/heap-{t.pod_name}-{ts}.hprof"

        live_flag = "--live" if heap_live else ""
        self._log(f"③ 导出 Heap Dump → {heap_file} (live={heap_live})", "dim")
        self._log("   ⚠ 警告: Heap Dump 会触发 Full GC 并暂停 JVM，大堆可能需要数分钟！", "warn")

        # heapdump 命令可能耗时很长，timeout 设 5 分钟
        cmd  = f"heapdump {live_flag} {heap_file}".strip()
        resp = client.exec_once(cmd, timeout_ms=300000)
        raw  = json.dumps(resp, ensure_ascii=False)
        self._log(f"   heapdump 响应: {raw[:200]}", "dim")

        state = resp.get("state", "")
        if state not in ("SUCCEEDED", "succeeded"):
            return self._fail(f"heapdump 失败: {raw[:300]}")

        return self._verify_and_download(ex, t, output_dir, ts, heap_file, "hprof")

    # ─────────────────────────────────────────────────────────────────────────
    # 公共: 验证 Pod 内文件并下载
    # ─────────────────────────────────────────────────────────────────────────
    def _verify_and_download(self, ex, t, output_dir, ts, pod_path, ext) -> dict:
        # 验证文件存在
        self._log(f"⑥ 验证 Pod 内文件: {pod_path}")
        rc, out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container,
                                  f"ls -lh '{pod_path}' 2>&1")
        if rc != 0 or "cannot access" in out.lower() or "no such file" in out.lower():
            # 兜底: 扫描常见输出目录（Arthas 有时写到 arthas-output/）
            scan_cmd = (
                f"ls -t /tmp/*.{ext} /arthas-output/*.{ext} "
                f"/home/admin/arthas-output/*.{ext} "
                f"/root/arthas-output/*.{ext} 2>/dev/null | head -5"
            )
            self._log(f"   扫描所有可能目录...", "dim")
            rc2, ls_out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container,
                                          scan_cmd, timeout=8)
            if rc2 == 0 and ls_out.strip():
                pod_path = ls_out.strip().splitlines()[0].strip()
                self._log(f"   找到备选文件: {pod_path}", "dim")
                rc, out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container,
                                          f"ls -lh '{pod_path}' 2>&1")
            if rc != 0:
                return self._fail(f"文件未找到: {pod_path}")

        self._log(f"   文件确认: {out.strip()} ✓", "success")

        # 下载到本地
        self._log("⑦ 下载文件到本地...")
        # 本地文件名规则：{Pod内文件名stem}-{pod_name}-{ts}.{ext}
        # 确保 pod_name 一定在文件名中，方便识别来源服务
        pod_name_short = t.pod_name[:30]   # 截短避免路径过长
        stem = Path(pod_path).stem
        # 如果文件名已含 pod_name → 直接用（jfr/heap 等后端生成的文件名）
        # 否则追加 pod_name 和 ts（arthas-output/ 下无规律命名的文件）
        if pod_name_short in stem:
            local_name = f"{stem}.{ext}"          # 已有 pod_name，直接用
        else:
            local_name = f"{stem}-{pod_name_short}-{ts}.{ext}"
        local_file = str(Path(output_dir) / local_name)
        rc, out, err = ex.cp_from_pod(t.namespace, t.pod_name, t.container, pod_path, local_file)
        detail = err or out or "无详细信息"
        if rc != 0:
            return self._fail(f"下载失败 (rc={rc}): {detail}")
        if not os.path.exists(local_file):
            return self._fail(f"下载命令成功但文件未找到: {local_file}")

        size_kb = os.path.getsize(local_file) / 1024
        self._log(f"🎉 完成！{local_file}  ({size_kb:.1f} KB)", "success")
        self.result.update({
            "status":     "completed",
            "local_file": local_file,
            "message":    f"完成，{size_kb:.1f} KB",
        })
        return self.result


    def _fail(self, msg: str) -> dict:
        self._log(f"✗ {msg}", "error")
        self.result.update({"status": "failed", "message": msg})
        return self.result
