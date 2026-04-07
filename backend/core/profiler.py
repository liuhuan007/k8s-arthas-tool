"""
性能分析工作流 - 支持 profiler/jfr/threaddump/heapdump
"""
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class ProfilerWorkflow:
    """
    性能分析任务编排，支持 4 种模式:
    mode='profiler'  — async-profiler (profiler start/stop)
    mode='jfr'       — JDK Flight Recorder (jfr start/stop)
    mode='threaddump' — 线程 Dump
    mode='heapdump'   — Heap Dump
    """

    def __init__(self, conn):
        self.conn = conn
        self.logs: List[Dict] = []
        self.result = {"status": "running", "local_file": "", "message": ""}
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
            "logs": list(self.logs),
            "result": dict(self.result),
        }

    def run(self, duration: int, fmt: str, output_dir: str,
            mode: str = 'profiler', event: str = 'cpu',
            jfr_name: str = 'arthas-jfr', jfr_settings: str = 'default',
            jfr_file: str = '', heap_file: str = '',
            heap_live: bool = True, **_) -> dict:
        """统一入口"""
        t = self.conn.target
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
    # ─────────────────────────────────────────────────────────────────────────
    def _run_profiler(self, ex, t, client, output_dir, ts,
                      duration, fmt, event) -> dict:
        ext = 'html' if fmt in ('html', 'flamegraph') else fmt
        pod_out = f"/tmp/arthas-profiler-{event}-{t.pod_name}-{ts}.{ext}"

        self._log(f"③ async-profiler 采样  事件={event}  格式={fmt}  时长={duration}s", "dim")

        # ③ 先检查并停止已有的 profiler（避免切换 Pod 后残留的 profiler 导致冲突）
        self._log("③ 检查是否有残留的 profiler 进程...")
        try:
            status_resp = client.exec_once("profiler status", timeout_ms=5000)
            status_raw = json.dumps(status_resp, ensure_ascii=False).lower()
            self._log(f"   profiler status: {status_raw[:200]}", "dim")
            if "running" in status_raw:
                self._log("   检测到正在运行的 profiler，先停止...", "warn")
                try:
                    client.exec_once("profiler stop", timeout_ms=10000)
                    time.sleep(1)
                except Exception:
                    pass
        except Exception:
            pass

        # ③ profiler start
        self._log("③ 启动 async-profiler（Session 模式）...")
        try:
            sess = client.init_session()
            if sess.get("state") not in ("SUCCEEDED", "succeeded"):
                return self._fail(f"创建 Session 失败: {json.dumps(sess)[:200]}")
            session_id = sess["sessionId"]
            consumer_id = sess["consumerId"]

            start_cmd = f"profiler start --event {event}"
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
        stop_cmd = f"profiler stop --format {fmt} --file {pod_out}"
        stop_resp = client.exec_once(stop_cmd, timeout_ms=60000)
        stop_raw = json.dumps(stop_resp, ensure_ascii=False)
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
                m = re.search(r'(/(?:tmp|arthas-output|home/admin/arthas-output|root/arthas-output)/[^\s"\'\\]+\.' + ext + r')', json.dumps(r))
                if m:
                    actual_path = m.group(1)
        except Exception:
            pass

        if actual_path != pod_out:
            pod_out = actual_path

        return self._verify_and_download(ex, t, output_dir, ts, pod_out, ext)

    # ─────────────────────────────────────────────────────────────────────────
    # JDK Flight Recorder
    # ─────────────────────────────────────────────────────────────────────────
    def _run_jfr(self, ex, t, client, output_dir, ts,
                 duration, jfr_name, jfr_settings, jfr_file) -> dict:
        jfr_file = f"/tmp/{jfr_name}-{t.pod_name[:30]}-{ts}.jfr"

        self._log("③ 启动 JDK JFR 录制（Arthas jfr 命令）", "dim")
        self._log("   注意: 需要 JDK 8u262+ 或 JDK 11+", "warn")
        self._log(f"   录制名={jfr_name}  设置={jfr_settings}  时长={duration}s", "dim")
        self._log(f"   输出文件={jfr_file}", "dim")

        start_cmd = (
            f"jfr start"
            f" -n {jfr_name}"
            f" -s {jfr_settings}"
            f" --duration {duration}s"
            f" -f {jfr_file}"
        )
        start_resp = client.exec_once(start_cmd, timeout_ms=15000)
        start_raw = json.dumps(start_resp, ensure_ascii=False)
        self._log(f"   jfr start 响应: {start_raw[:300]}", "dim")

        state = start_resp.get("state", "")
        body = json.dumps(start_resp.get("body", {}), ensure_ascii=False)
        if state not in ("SUCCEEDED", "succeeded"):
            if "not supported" in body.lower() or "jdk 11" in body.lower():
                return self._fail("JDK JFR 需要 JDK 8u262+ 或 JDK 11+，当前 JDK 不支持。请改用 async-profiler 模式")
            return self._fail(f"jfr start 失败: {start_raw[:300]}")

        # 提取 recording ID
        recording_id = None
        jfr_output = ""
        try:
            for r in start_resp.get("body", {}).get("results", []):
                jfr_output = r.get("jfrOutput", "")
                m = re.search(r"Recording\s+(\d+)", jfr_output)
                if m:
                    recording_id = m.group(1)
                    break
        except Exception:
            pass

        self._log(f"JFR 录制已启动 ✓  recording_id={recording_id}  output={jfr_output[:80]}", "success")
        self._log(f"   说明: scheduled 表示录制将在 {duration}s 后自动完成并写入文件", "dim")
        self.result["start_time"] = datetime.now().isoformat()

        # ④ 倒计时等待录制完成
        self._log(f"④ JFR 录制中，共 {duration} 秒（自动停止）...")
        for i in range(duration):
            if self._cancelled:
                self._log("⚠ 手动中止，发送 jfr stop...", "warn")
                if recording_id:
                    client.exec_once(f"jfr stop -r {recording_id} -f {jfr_file}", timeout_ms=30000)
                break
            time.sleep(1)
            if (i + 1) % 10 == 0:
                self._log(f"   进度 {i+1}/{duration}s", "dim")

        # ⑤ 等待 JVM 完成文件写入
        self._log("⑤ 等待 JFR 文件落盘 (10s)...")
        for i in range(10):
            time.sleep(1)
            rc, ls_out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container, f"ls -lh '{jfr_file}' 2>&1", timeout=5)
            if rc == 0 and " 0 " not in ls_out and "0B" not in ls_out:
                self._log(f"   文件已写入: {ls_out.strip()}", "success")
                break
            if i == 9:
                self._log(f"   文件状态: {ls_out.strip()}", "dim")

        # 若文件仍为 0，用 dump 强制触发写入
        rc, ls_out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container, f"ls -lh '{jfr_file}' 2>&1", timeout=5)
        if rc != 0 or " 0 " in ls_out or "0B" in ls_out:
            self._log("   文件仍为 0，尝试 jfr dump...", "warn")
            if recording_id:
                dump_resp = client.exec_once(f"jfr dump -r {recording_id} -f {jfr_file}", timeout_ms=30000)
                self._log(f"   jfr dump: {json.dumps(dump_resp)[:200]}", "dim")
            else:
                dump_resp = client.exec_once(f"jfr dump -n {jfr_name} -f {jfr_file}", timeout_ms=30000)
                self._log(f"   jfr dump (by name): {json.dumps(dump_resp)[:200]}", "dim")
            time.sleep(5)
            rc, ls_out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container, f"ls -lh '{jfr_file}' 2>&1", timeout=5)
            self._log(f"   dump 后文件状态: {ls_out.strip()}", "dim")
            if " 0 " in ls_out or "0B" in ls_out:
                self._log("   扫描 arthas-output 目录...", "dim")
                rc2, scan_out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container, "ls -lt /arthas-output/*.jfr /tmp/*.jfr 2>/dev/null | head -5", timeout=5)
                if rc2 == 0 and scan_out.strip():
                    newest = scan_out.strip().splitlines()[0].split()[-1]
                    self._log(f"   找到候选文件: {newest}", "dim")
                    jfr_file = newest

        return self._verify_and_download(ex, t, output_dir, ts, jfr_file, "jfr")

    # ─────────────────────────────────────────────────────────────────────────
    # Thread Dump
    # ─────────────────────────────────────────────────────────────────────────
    def _run_threaddump(self, ex, t, client, output_dir, ts) -> dict:
        self._log("③ 导出完整线程 Dump（thread -n 9999，含堆栈）...")
        resp = client.exec_once("thread -n 9999", timeout_ms=60000)
        raw = json.dumps(resp, ensure_ascii=False)
        self._log(f"   thread 响应: {raw[:150]}", "dim")

        if resp.get("state") not in ("SUCCEEDED", "succeeded"):
            return self._fail(f"thread -n 9999 失败: {raw[:300]}")

        # 检测死锁
        blocking_info = ""
        try:
            block_resp = client.exec_once("thread -b", timeout_ms=15000)
            block_raw = json.dumps(block_resp, ensure_ascii=False)
            if "blockingThread" in block_raw or "deadlock" in block_raw.lower():
                blocking_info = block_raw
                self._log("   ⚠ 检测到阻塞/死锁信息！", "warn")
            else:
                self._log("   未发现死锁", "dim")
        except Exception as e:
            self._log(f"   thread -b 跳过: {e}", "dim")

        # 解析线程数据
        threads_data = []
        try:
            for r in resp.get("body", {}).get("results", []):
                candidates = r.get("busyThreads") or r.get("threads") or []
                if candidates and isinstance(candidates, list):
                    threads_data = candidates
                    break
        except Exception as e:
            self._log(f"   解析异常: {e}", "warn")

        self._log(f"   解析到 {len(threads_data)} 个线程", "dim")

        # 转成 jstack 风格文本
        text_lines = [
            f"Full thread dump — {t.namespace}/{t.pod_name}",
            f"时间: {ts[:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:]}",
            f"线程数: {len(threads_data)}",
            "=" * 70,
            "",
        ]
        for th in threads_data:
            name = th.get("name", "unknown")
            daemon = " daemon" if th.get("daemon") else ""
            prio = th.get("priority", 5)
            tid = th.get("id", 0)
            state = th.get("state", "")
            cpu = th.get("cpu", "")
            cpu_s = f" cpu={cpu}%" if cpu else ""
            group = th.get("group", "")

            text_lines.append(f'"{name}"{daemon} prio={prio} Id={tid}{cpu_s}')
            if group:
                text_lines.append(f'   group="{group}"')
            text_lines.append(f"   java.lang.Thread.State: {state}")
            if th.get("interrupted"):
                text_lines.append("   (interrupted)")

            for frame in th.get("stackTrace", []):
                cls = frame.get("className", "")
                meth = frame.get("methodName", "")
                fn = frame.get("fileName", "")
                ln = frame.get("lineNumber", -1)
                if ln == -2:
                    text_lines.append(f"\tat {cls}.{meth}(Native Method)")
                elif fn:
                    text_lines.append(f"\tat {cls}.{meth}({fn}:{ln})")
                else:
                    text_lines.append(f"\tat {cls}.{meth}(Unknown Source)")

            for lk in (th.get("lockedMonitors") or []):
                text_lines.append(f"\t- locked <{lk.get('identityHashCode','?')}> ({lk.get('className','?')})")

            text_lines.append("")

        if blocking_info:
            text_lines += ["", "=" * 70, "⚠ 阻塞/死锁检测结果 (thread -b):", "=" * 70, "", blocking_info]

        if not threads_data:
            self._log("   未解析到结构化线程数据，使用原始响应", "warn")
            text_lines.append(raw)

        thread_text = "\n".join(text_lines)

        # 统计
        thread_count = len(threads_data) if threads_data else 0
        blocked_count = sum(1 for th in threads_data if th.get("state") == "BLOCKED") if threads_data else 0
        waiting_count = sum(1 for th in threads_data if th.get("state") in ("WAITING", "TIMED_WAITING")) if threads_data else 0
        running_count = sum(1 for th in threads_data if th.get("state") == "RUNNABLE") if threads_data else 0
        deadlock_count = thread_text.lower().count("deadlock")

        # 生成 HTML
        import html
        html_content = _build_threaddump_html(
            pod_name=t.pod_name,
            namespace=t.namespace,
            ts=ts,
            thread_count=thread_count,
            running_count=running_count,
            waiting_count=waiting_count,
            blocked_count=blocked_count,
            deadlock_count=deadlock_count,
            threads_data=threads_data,
            raw_html=html.escape(thread_text),
            json_threads=json.dumps(threads_data, ensure_ascii=False),
        )

        local_file = str(Path(output_dir) / f"threaddump-{t.pod_name}-{ts}.html")
        Path(local_file).write_text(html_content, encoding="utf-8")
        size_kb = Path(local_file).stat().st_size / 1024

        self._log(f"🎉 线程 Dump 完成！{local_file}  ({size_kb:.1f} KB)", "success")
        self._log(f"   含 {thread_count} 个线程  BLOCKED={blocked_count}  WAITING={waiting_count}", "dim")
        self.result.update({
            "status": "completed",
            "local_file": local_file,
            "message": f"完成，{thread_count} 线程 / {size_kb:.1f} KB",
        })
        return self.result

    # ─────────────────────────────────────────────────────────────────────────
    # Heap Dump
    # ─────────────────────────────────────────────────────────────────────────
    def _run_heapdump(self, ex, t, client, output_dir, ts, heap_file, heap_live) -> dict:
        if not heap_file:
            heap_file = f"/tmp/heap-{t.pod_name}-{ts}.hprof"

        live_flag = "--live" if heap_live else ""
        self._log(f"③ 导出 Heap Dump → {heap_file} (live={heap_live})", "dim")
        self._log("   ⚠ 警告: Heap Dump 会触发 Full GC 并暂停 JVM，大堆可能需要数分钟！", "warn")

        cmd = f"heapdump {live_flag} {heap_file}".strip()
        resp = client.exec_once(cmd, timeout_ms=300000)
        raw = json.dumps(resp, ensure_ascii=False)
        self._log(f"   heapdump 响应: {raw[:200]}", "dim")

        state = resp.get("state", "")
        if state not in ("SUCCEEDED", "succeeded"):
            return self._fail(f"heapdump 失败: {raw[:300]}")

        return self._verify_and_download(ex, t, output_dir, ts, heap_file, "hprof")

    # ─────────────────────────────────────────────────────────────────────────
    # 公共: 验证并下载
    # ─────────────────────────────────────────────────────────────────────────
    def _verify_and_download(self, ex, t, output_dir, ts, pod_path, ext) -> dict:
        self._log(f"⑥ 验证 Pod 内文件: {pod_path}")
        rc, out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container, f"ls -lh '{pod_path}' 2>&1")
        if rc != 0 or "cannot access" in out.lower() or "no such file" in out.lower():
            scan_cmd = f"ls -t /tmp/*.{ext} /arthas-output/*.{ext} /home/admin/arthas-output/*.{ext} /root/arthas-output/*.{ext} 2>/dev/null | head -5"
            self._log(f"   扫描所有可能目录...", "dim")
            rc2, ls_out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container, scan_cmd, timeout=8)
            if rc2 == 0 and ls_out.strip():
                pod_path = ls_out.strip().splitlines()[0].strip()
                self._log(f"   找到备选文件: {pod_path}", "dim")
                rc, out, _ = ex.exec_pod(t.namespace, t.pod_name, t.container, f"ls -lh '{pod_path}' 2>&1")
            if rc != 0:
                return self._fail(f"文件未找到: {pod_path}")

        self._log(f"   文件确认: {out.strip()} ✓", "success")

        self._log("⑦ 下载文件到本地...")
        # 统一使用固定命名模板，避免 Arthas/async-profiler 自行追加应用标识导致文件名过长
        local_name = f"arthas-profiler-{t.pod_name}-{ts}.{ext}"
        local_file = str(Path(output_dir) / local_name)
        # 如果文件已存在（同名任务），追加序号避免覆盖
        if os.path.exists(local_file):
            for seq in range(1, 100):
                local_name = f"arthas-profiler-{t.pod_name}-{ts}-{seq}.{ext}"
                local_file = str(Path(output_dir) / local_name)
                if not os.path.exists(local_file):
                    break
        rc, out, err = ex.cp_from_pod(t.namespace, t.pod_name, t.container, pod_path, local_file)
        detail = err or out or "无详细信息"
        if rc != 0:
            return self._fail(f"下载失败 (rc={rc}): {detail}")
        if not os.path.exists(local_file):
            return self._fail(f"下载命令成功但文件未找到: {local_file}")

        size_kb = os.path.getsize(local_file) / 1024
        self._log(f"🎉 完成！{local_file}  ({size_kb:.1f} KB)", "success")
        self.result.update({
            "status": "completed",
            "local_file": local_file,
            "message": f"完成，{size_kb:.1f} KB",
        })
        return self.result

    def _fail(self, msg: str) -> dict:
        self._log(f"✗ {msg}", "error")
        self.result.update({"status": "failed", "message": msg})
        return self.result


# ═══════════════════════════════════════════════════════════════════════════════
# Thread Dump HTML 模板
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
    raw_html: str,
    json_threads: str,
) -> str:
    """生成线程 Dump 的 HTML 报告"""
    import html as _html

    ts_fmt = f"{ts[:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:]}"
    deadlock_badge = (
        f"<div class=\"stat\" style=\"border-color:#f7768e\">"
        f"<b style=\"color:#f7768e\">{deadlock_count}</b>DEADLOCK</div>"
        if deadlock_count else ""
    )

    p_name_esc = _html.escape(pod_name)
    ns_esc = _html.escape(namespace)

    btn_all = f'<button class="tbtn on" onclick="filt(&apos;all&apos;,this)">All ({thread_count})</button>'
    btn_r = f'<button class="tbtn" onclick="filt(&apos;r&apos;,this)">🟢 RUNNABLE ({running_count})</button>'
    btn_w = f'<button class="tbtn" onclick="filt(&apos;w&apos;,this)">🟠 WAITING ({waiting_count})</button>'
    btn_b = f'<button class="tbtn" onclick="filt(&apos;b&apos;,this)">🔴 BLOCKED ({blocked_count})</button>'
    summary = f"共 {thread_count} 个线程 · RUNNABLE={running_count} · WAITING(含TIMED)={waiting_count} · BLOCKED={blocked_count}"

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