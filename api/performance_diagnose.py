#!/usr/bin/env python3
"""
性能诊断端点 — 一键性能诊断 + 规则预筛 + LLM 报告生成

路由：
  POST /api/ai/diagnose_performance    — 一键诊断（核心入口）
  GET  /api/ai/diagnose_instances       — 列出可诊断的已连接实例

架构：
  诊断端点 → Arthas 采集（trace/dashboard/thread） → 规则引擎预筛
  → 结构化数据 + LLM 解读 → 诊断报告（根因/影响/建议）

依赖：
  - backend.core.rule_engine  — 规则预筛
  - api.ai_chat               — LLM 调用能力
"""
import json
import logging
import time
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from backend.core.rule_engine import RuleEngine, extract_metrics_from_diagnosis

log = logging.getLogger(__name__)
diag_bp = Blueprint('performance_diagnose', __name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_conn_id(connection_id: str) -> dict:
    """从 connection_id 解析出 cluster_name / namespace / pod_name。
    
    格式: {cluster}/{ns}/{pod} 或 {cluster}/{ns}/{pod}@u{user_id}
    """
    # 去掉 @u 后缀
    raw = connection_id.split('@u')[0] if '@u' in connection_id else connection_id
    parts = raw.split('/')
    if len(parts) >= 3:
        return {
            'cluster_name': parts[0],
            'namespace': '/'.join(parts[1:-1]),  # namespace 可能含 /
            'pod_name': parts[-1],
        }
    return {}


def _get_alive_connection(connection_id: str):
    """获取活跃的 Arthas 连接
    
    只要 conn 对象在 connections 中就返回，让后续实际操作判断是否真正可用。
    """
    from backend.app_context import connections, connections_lock

    if not connection_id:
        with connections_lock:
            # admin 可用所有连接，非 admin 仅自己的
            if current_user.is_admin:
                alive = [(cid, e) for cid, e in connections.items() if e.get('conn')]
            else:
                alive = [(cid, e) for cid, e in connections.items()
                         if e.get('user_id') == current_user.id and e.get('conn')]
            if alive:
                return alive[-1][1]['conn']
        return None

    with connections_lock:
        entry = connections.get(connection_id)
        if not entry:
            # 尝试模糊匹配：connection_id 可能与 connections 的 key 略有差异
            for cid in connections:
                if connection_id in cid or cid in connection_id:
                    log.warning("_get_alive_connection: fuzzy match %r -> %r", connection_id, cid)
                    entry = connections[cid]
                    break
            if not entry:
                return None
        # admin 可以访问所有连接，非 admin 只能访问自己的
        if not current_user.is_admin and entry.get('user_id') != current_user.id:
            return None
        conn = entry.get('conn')
        if not conn:
            log.warning("_get_alive_connection: entry found but conn is None")
            return None
        return conn


def _list_diagnosable_instances() -> list:
    """列出当前用户所有可诊断的已连接实例"""
    from backend.app_context import connections, connections_lock

    instances = []
    with connections_lock:
        for cid, entry in connections.items():
            # admin 可看所有，非 admin 仅自己的
            if not current_user.is_admin and entry.get('user_id') != current_user.id:
                continue
            conn = entry.get('conn')
            if conn:
                instances.append({
                        "connection_id": cid,
                        "pod": conn.target.pod_name,
                        "namespace": conn.target.namespace,
                        "cluster": conn.target.cluster_name,
                        "container": conn.target.container,
                        "java_pid": conn.java_pid,
                        "arthas_version": conn.arthas_version,
                        "local_port": conn.local_port,
                    })
    return instances


def _persist_diagnosis_run(diagnosis: dict, conn, user_id: int,
                           duration_ms: int) -> str:
    """Persist the server-collected evidence and return its opaque run identifier."""
    from models.db import db

    run_id = f"diag-{uuid.uuid4().hex}"
    now = datetime.now().isoformat()
    errors = [
        f"{step['name']}: {step.get('error', '采集失败')}"
        for step in diagnosis.get("steps", [])
        if step.get("status") == "failed"
    ]
    db.insert("task_logs", {
        "id": run_id,
        "user_id": user_id,
        "capability_id": None,
        "execution_mode": "manual",
        "execution_type": "diagnosis",
        "run_type": "diagnosis",
        "target_json": json.dumps({
            "connection_id": diagnosis.get("connection_id", ""),
            "cluster": conn.target.cluster_name,
            "namespace": conn.target.namespace,
            "pod": conn.target.pod_name,
            "container": conn.target.container,
            "target": diagnosis.get("target"),
        }, ensure_ascii=False),
        "params_json": json.dumps({
            "target": diagnosis.get("target"),
            "class_pattern": diagnosis.get("class_pattern", ""),
            "method_pattern": diagnosis.get("method_pattern", ""),
        }, ensure_ascii=False),
        "status": diagnosis.get("status", "failed"),
        "result_json": json.dumps(diagnosis, ensure_ascii=False),
        "started_at": diagnosis.get("timestamp", now),
        "finished_at": now,
        "duration_ms": duration_ms,
        "error_message": "; ".join(errors),
    })
    return run_id


# ═══════════════════════════════════════════════════════════════════════════════
# 核心诊断逻辑
# ═══════════════════════════════════════════════════════════════════════════════

def _run_diagnosis(conn, target: str, class_pattern: str, method_pattern: str) -> dict:
    """
    执行完整诊断流程：
    1. Dashboard 采集 JVM 基线
    2. Thread 快照
    3. 可选 trace 方法耗时
    4. 规则引擎预筛
    返回结构化诊断结果。
    """
    import re

    result = {
        "timestamp": datetime.now().isoformat(),
        "target": target,
        "cluster": conn.target.cluster_name,
        "container": conn.target.container,
        "pod": conn.target.pod_name,
        "namespace": conn.target.namespace,
        "java_pid": conn.java_pid,
        "steps": [],
        "rules_triggered": [],
        "metrics": {},
        "highlights": [],
        "recommendations": [],
        "severity": "normal",
        "status": "running",
        "class_pattern": class_pattern,
        "method_pattern": method_pattern,
    }

    client = conn.http_client
    engine = RuleEngine()

    def _step(name: str):
        step = {
            "name": name,
            "started_at": datetime.now().isoformat(),
            "status": "running",
        }
        result["steps"].append(step)
        return step

    def _step_finished(step: dict, status: str, error: str = None):
        step["finished_at"] = datetime.now().isoformat()
        step["status"] = status
        if error:
            step["error"] = error

    # ── Step 1: Dashboard 基线 ──────────────────────────────────────
    dashboard_step = _step("dashboard")
    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        dash_resp = ArthasCommandExecutor.execute(conn, "dashboard -n 1", timeout_ms=15000)
        if isinstance(dash_resp, dict) and dash_resp.get("state") not in (
                None, "", "SUCCEEDED", "SUCCESS", "COMPLETED"):
            raise RuntimeError(dash_resp.get("message") or dash_resp["state"])
        # 从 Arthas 响应中提取核心指标，避免存储完整响应导致 JSON 过大被截断
        dash_body = dash_resp.get('body', dash_resp) if isinstance(dash_resp, dict) else {}
        dash_results = dash_body.get('results', []) if isinstance(dash_body, dict) else []
        if dash_results and isinstance(dash_results[0], dict):
            r0 = dash_results[0]
            all_threads = r0.get("threads", [])
            # 存储完整线程数据，前端按需分页
            dashboard_evidence = {
                "threads": all_threads,
                "memoryInfo": r0.get("memoryInfo", {}),
                "gcInfos": r0.get("gcInfos", []),
                "runtimeInfo": r0.get("runtimeInfo", {}),
            }
            for key in ("cpu_percent", "cpuPercent", "cpuUsage", "jvmCpu"):
                if key in r0:
                    dashboard_evidence[key] = r0[key]
            result["metrics"]["dashboard"] = json.dumps({
                "body": {
                    **dashboard_evidence,
                }
            }, ensure_ascii=False)
        else:
            result["metrics"]["dashboard"] = json.dumps(dash_resp, ensure_ascii=False)
        _step_finished(dashboard_step, "completed")
    except Exception as e:
        result["metrics"]["dashboard_error"] = str(e)
        _step_finished(dashboard_step, "failed", str(e))

    # ── Step 2: Thread 快照 ───────────────────────────────────────
    thread_step = _step("thread")
    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        thread_resp = ArthasCommandExecutor.execute(conn, "thread -n 15", timeout_ms=20000)
        if isinstance(thread_resp, dict) and thread_resp.get("state") not in (
                None, "", "SUCCEEDED", "SUCCESS", "COMPLETED"):
            raise RuntimeError(thread_resp.get("message") or thread_resp["state"])
        # 从 Arthas 响应中提取线程列表，避免存储完整响应被截断
        thread_body = thread_resp.get('body', thread_resp) if isinstance(thread_resp, dict) else {}
        thread_results = thread_body.get('results', []) if isinstance(thread_body, dict) else []
        if thread_results and isinstance(thread_results[0], dict):
            r0 = thread_results[0]
            busy = r0.get('busyThreads', r0.get('threads', []))
            # 存储完整线程数据，前端按需分页
            result["metrics"]["threads"] = json.dumps({
                "body": {
                    "busyThreads": busy,
                }
            }, ensure_ascii=False)
        else:
            result["metrics"]["threads"] = json.dumps(thread_resp, ensure_ascii=False)
        _step_finished(thread_step, "completed")
    except Exception as e:
        log.warning("Thread 指标采集失败: %s", e)
        result["metrics"]["threads_error"] = str(e)
        _step_finished(thread_step, "failed", str(e))

    # ── Step 3: Trace（method_slow / general 场景）────────────────
    if target in ("method_slow", "general") and class_pattern:
        trace_step = _step("trace")
        try:
            from backend.core.arthas_executor import ArthasCommandExecutor
            skip = "--skipJDKMethod true"
            trace_cmd = f"trace {class_pattern} {method_pattern or '*'} -n 10 '{skip} #cost > .5'"
            trace_resp = ArthasCommandExecutor.execute(conn, trace_cmd, timeout_ms=30000)
            if isinstance(trace_resp, dict) and trace_resp.get("state") not in (
                    None, "", "SUCCEEDED", "SUCCESS", "COMPLETED"):
                raise RuntimeError(trace_resp.get("message") or trace_resp["state"])
            trace_raw = json.dumps(trace_resp, ensure_ascii=False)
            result["metrics"]["trace"] = trace_raw
            _step_finished(trace_step, "completed")
        except Exception as e:
            log.warning("Trace 指标采集失败: %s", e)
            result["metrics"]["trace_error"] = str(e)
            _step_finished(trace_step, "failed", str(e))

    # ── Step 4: 规则引擎预筛 ────────────────────────────────────
    rule_step = _step("rule_engine")
    raw_metrics = extract_metrics_from_diagnosis(result)
    rule_result = engine.evaluate(raw_metrics)
    result["rules_triggered"] = rule_result["triggered"]
    result["highlights"] = rule_result["highlights"]
    result["severity"] = rule_result["severity"]
    result["summary"] = rule_result["summary"]
    _step_finished(rule_step, "completed")

    # ── Step 5: 生成建议 ──────────────────────────────────────────
    collection_steps = [step for step in result["steps"] if step["name"] != "rule_engine"]
    successful_steps = sum(step["status"] == "completed" for step in collection_steps)
    failed_steps = sum(step["status"] == "failed" for step in collection_steps)
    result["status"] = "completed"
    if failed_steps:
        result["status"] = "partial" if successful_steps else "failed"
    if not raw_metrics:
        result["status"] = "partial" if successful_steps else "failed"
        result["severity"] = "unknown"
    result["collection_complete"] = failed_steps == 0 and bool(raw_metrics)
    if result["status"] != "completed":
        result["summary"] = "诊断数据不完整；规则结果仅基于已采集证据，不能据此确认问题已排除"
    result["recommendations"] = _make_recommendations(
        result["rules_triggered"], target, result["status"])

    return result


def _make_recommendations(triggered: list, target: str,
                          diagnosis_status: str = "completed") -> list:
    """根据规则命中情况生成优化建议"""
    recs = []
    rule_ids = {r["rule_id"] for r in triggered}

    if "very_slow_method" in rule_ids:
        recs.append("🔴 方法耗时超过 2 秒，建议立即分析调用链路，优先优化数据库查询或外部调用")
    elif "slow_method" in rule_ids:
        recs.append("⚠️ 方法耗时偏高，建议 trace 详细分析，定位具体哪个子调用慢")
    if "high_cpu" in rule_ids or "very_high_cpu" in rule_ids:
        recs.append("⚠️ CPU 使用率高，建议 thread -n 查看热点线程定位瓶颈")
    if "very_high_old_gen" in rule_ids:
        recs.append("🔴 Old 区接近满，建议 heapdump 后使用 MAT 分析内存泄漏")
    elif "high_old_gen" in rule_ids:
        recs.append("⚠️ Old 区内存偏高，建议观察是否有内存泄漏趋势")
    if "thread_blocked" in rule_ids:
        recs.append("⚠️ BLOCKED 线程多，建议执行 thread -b 检查死锁，分析锁竞争")
    if "thread_deadlock" in rule_ids:
        recs.append("🔴 死锁检测到！建议立即分析线程堆栈，定位循环依赖的锁")
    if "full_gc" in rule_ids:
        recs.append("🔴 发生 Full GC，建议分析老年代对象，可能存在内存泄漏")
    if "high_gc_freq" in rule_ids:
        recs.append("⚠️ Young GC 频率高，可能存在大量短生命周期对象，建议分析堆外内存或调整 Eden 区大小")

    if not recs:
        if diagnosis_status != "completed":
            recs.append("诊断数据采集不完整，当前结果不能用于确认或排除性能问题，请检查失败步骤后重试")
        elif target == "oom":
            recs.append("未检测到明显内存异常，建议持续观察 Old 区趋势")
        elif target == "thread_block":
            recs.append("未检测到线程阻塞，建议扩大诊断范围或检查业务日志")
        else:
            recs.append("✅ 当前指标正常，未检测到明显性能问题")

    return recs


# ═══════════════════════════════════════════════════════════════════════════════
# REST 端点
# ═══════════════════════════════════════════════════════════════════════════════

@diag_bp.route('/api/diagnose/tool', methods=['POST'])
@login_required
def diagnose_tool():
    """
    直接执行诊断工具（不需要 AI 配置）。
    供性能诊断面板的「快速工具」按钮调用。

    POST /api/diagnose/tool
    {
        "connection_id": "xxx",
        "tool": "jvm" | "dashboard" | "threads" | "trace",
        "args": { ... }           // 可选参数
    }
    """
    d = request.json or {}
    connection_id = d.get('connection_id', '')
    tool = d.get('tool', '')
    args = d.get('args', {})

    conn = _get_alive_connection(connection_id)
    if not conn:
        # 尝试用 ensure_connection 自动重建
        from backend.app_context import ensure_connection
        rebuild_params = _parse_conn_id(connection_id)
        rebuild_d = {**d, **rebuild_params}
        conn, err = ensure_connection(connection_id, rebuild_d)
        if err:
            log.warning("diagnose_tool: ensure_connection failed: %s, connection_id=%r", err, connection_id)
    if not conn:
        return jsonify({"error": "Arthas 连接不可用，请先在左侧连接目标 Pod"}), 400

    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        if tool == 'jvm':
            resp = ArthasCommandExecutor.execute(conn, "jvm", timeout_ms=10000)
            return jsonify({"ok": True, "data": resp})
        elif tool == 'dashboard':
            resp = ArthasCommandExecutor.execute(conn, "dashboard -n 1", timeout_ms=15000)
            return jsonify({"ok": True, "data": resp})
        elif tool == 'threads':
            top_n = args.get('top_n', 15)
            from backend.core.arthas_executor import ArthasCommandExecutor
            resp = ArthasCommandExecutor.execute(conn, f"thread -n {top_n}", timeout_ms=20000)
            # 死锁检测
            deadlock = None
            if args.get('check_deadlock', True):
                try:
                    dl = ArthasCommandExecutor.execute(conn, "thread -b", timeout_ms=15000)
                    # thread -b 返回 {body: {blockingThread: null}} 或 {body: {blockingThread: {...}}}
                    # 需要检查 blockingThread 的值是否非空，不能只看字段名
                    dl_body = dl.get('body', {}) if isinstance(dl, dict) else {}
                    bt = dl_body.get('blockingThread')
                    if bt and isinstance(bt, dict) and bt.get('threadName'):
                        deadlock = dl
                except Exception:
                    pass
            return jsonify({"ok": True, "data": resp, "deadlock": deadlock})
        elif tool == 'trace':
            cp = args.get('class_pattern', '')
            mp = args.get('method_pattern', '*')
            if not cp:
                return jsonify({"error": "class_pattern 不能为空"}), 400
            skip = '--skipJDKMethod true' if args.get('skip_jdk', True) else ''
            sample_count = args.get('sample_count', 5)
            cmd = f"trace {cp} {mp} -n {sample_count} '{skip} #cost > .5' '#cost > .1'"
            from backend.core.arthas_executor import ArthasCommandExecutor
            resp = ArthasCommandExecutor.execute(conn, cmd, timeout_ms=30000)
            return jsonify({"ok": True, "data": resp})
        elif tool == 'watch':
            cp = args.get('class_pattern', '')
            mp = args.get('method_pattern', '*')
            if not cp:
                return jsonify({"error": "class_pattern 不能为空"}), 400
            n = args.get('n', 5)
            condition = args.get('condition', '')
            cmd = f"watch {cp} {mp} -n {n}"
            if condition:
                cmd += f" '{condition}'"
            from backend.core.arthas_executor import ArthasCommandExecutor
            resp = ArthasCommandExecutor.execute(conn, cmd, timeout_ms=30000)
            return jsonify({"ok": True, "data": resp})
        elif tool == 'jad':
            class_name = args.get('class_name', '')
            if not class_name:
                return jsonify({"error": "class_name 不能为空"}), 400
            cmd = f"jad --source-only {class_name}"
            from backend.core.arthas_executor import ArthasCommandExecutor
            resp = ArthasCommandExecutor.execute(conn, cmd, timeout_ms=30000)
            return jsonify({"ok": True, "data": resp})
        else:
            return jsonify({"error": f"未知工具: {tool}"}), 400
    except Exception as e:
        log.error("diagnose_tool failed: %s", e, exc_info=True)
        return jsonify({"error": f"执行失败: {str(e)}"}), 500


@diag_bp.route('/api/ai/diagnose_instances', methods=['GET'])
@login_required
def list_diagnose_instances():
    """列出当前用户所有可诊断的已连接实例"""
    instances = _list_diagnosable_instances()
    return jsonify({
        "instances": instances,
        "count": len(instances)
    })


@diag_bp.route('/api/ai/diagnose_performance', methods=['POST'])
@login_required
def diagnose_performance():
    """
    一键性能诊断核心入口。

    POST /api/ai/diagnose_performance?connection_id=xxx
    {
        "connection_id": "xxx",       // 可选，优先用 query parameter
        "target": "general",           // method_slow | oom | thread_block | general
        "class_pattern": "com.example.*", // 可选
        "method_pattern": "save*"      // 可选
    }

    返回结构化诊断报告。
    """
    d = request.json or {}
    # 优先从 query parameter 获取，再从 body 获取
    connection_id = request.args.get('connection_id', '') or d.get('connection_id', '')
    target = d.get('target', 'general')
    class_pattern = d.get('class_pattern', '')
    method_pattern = d.get('method_pattern', '')

    # 获取连接 — 优先用 _get_alive_connection，失败则用 server.ensure_connection 自动重建
    conn = _get_alive_connection(connection_id)
    if not conn:
        # 尝试用 ensure_connection 自动重建（与 /api/arthas/exec 相同逻辑）
        from backend.app_context import ensure_connection
        # 从 connection_id 解析连接参数，补充到 d 中供 ensure_connection 使用
        rebuild_params = _parse_conn_id(connection_id)
        rebuild_d = {**d, **rebuild_params}
        conn, err = ensure_connection(connection_id, rebuild_d)
        if err:
            log.warning("diagnose_performance: ensure_connection failed: %s, connection_id=%r, rebuild_params=%s", err, connection_id, rebuild_params)
    if not conn:
        # 尝试列出可用实例供用户选择
        instances = _list_diagnosable_instances()
        if instances:
            return jsonify({
                "error": "未指定 connection_id，且没有活跃连接",
                "instances": instances,
                "hint": "请在 instances 中选择一个 connection_id"
            }), 400
        return jsonify({"error": "没有任何活跃的 Arthas 连接，请先在左侧连接目标 Pod"}), 400

    # 执行诊断
    try:
        started = time.monotonic()
        report = _run_diagnosis(conn, target, class_pattern, method_pattern)
        report["connection_id"] = connection_id
        report["duration_ms"] = int((time.monotonic() - started) * 1000)
        report["run_id"] = _persist_diagnosis_run(
            report, conn, current_user.id, report["duration_ms"])

        # 审计
        try:
            from services.audit_service import AuditService
            AuditService._log_raw(
                current_user.id, 'performance_diagnose', 'diagnose_report',
                conn.target.pod_name,
                f"诊断 target={target} class={class_pattern or '*'} severity={report['severity']}"
            )
        except Exception:
            pass

        return jsonify(report)

    except Exception as e:
        log.error("diagnose_performance failed: %s", e, exc_info=True)
        return jsonify({"error": f"诊断失败: {str(e)}"}), 500


@diag_bp.route('/api/ai/diagnose_performance/report', methods=['POST'])
@login_required
def generate_diagnose_report():
    """
    基于诊断结果 + LLM 生成自然语言诊断报告。
    需要先有 AI 配置（ai_chat 中的 config）。

    POST /api/ai/diagnose_performance/report
    {
        "run_id": "diag-..."   // 服务端保存的诊断运行 ID
    }
    """
    d = request.json or {}
    run_id = d.get('run_id', '')
    if not isinstance(run_id, str) or not run_id.startswith("diag-"):
        return jsonify({"error": "缺少有效的 run_id"}), 400

    from models.db import db
    run = db.fetch_one(
        "SELECT * FROM task_logs WHERE id = ? AND is_archived = 0",
        (run_id,))
    if not run:
        return jsonify({"error": "诊断记录不存在或已归档"}), 404
    if run.get("user_id") != current_user.id and not current_user.is_admin:
        return jsonify({"error": "无权访问该诊断记录"}), 403
    try:
        diagnosis = json.loads(run.get("result_json") or "{}")
    except (TypeError, ValueError):
        log.error("Invalid diagnosis result JSON: run_id=%s", run_id)
        return jsonify({"error": "诊断记录数据损坏"}), 500
    if not diagnosis:
        return jsonify({"error": "诊断记录没有可用数据"}), 422

    # 检查 AI 配置
    config = db.fetch_one('SELECT * FROM ai_config WHERE user_id = ?', (current_user.id,))
    if not config:
        return jsonify({
            "error": "请先配置大模型（API Key + 模型名称）",
            "need_config": True,
            "hint": "点击「⚙️ 配置大模型」或在 AI 助手面板的 ⚙️ 按钮中配置"
        }), 400

    # 构建 LLM Prompt
    prompt = _build_llm_report_prompt(diagnosis)

    try:
        import urllib.request
        base_url = config['base_url'].rstrip('/')
        url = f"{base_url}/chat/completions"

        payload = {
            "model": config['model'],
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的 Java 性能诊断工程师，帮助用户分析 Arthas 诊断数据，生成结构化诊断报告。直接输出报告，不要额外解释。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.3,
        }

        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        if config.get('api_key'):
            req.add_header('Authorization', f"Bearer {config['api_key']}")

        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            db.update("task_logs", {
                "ai_analysis_result": content,
            }, "id = ?", (run_id,))
            return jsonify({
                "run_id": run_id,
                "report": content,
                "diagnosis_summary": {
                    "severity": diagnosis.get('severity', 'unknown'),
                    "rules_triggered": [r['name'] for r in diagnosis.get('rules_triggered', [])],
                    "recommendations": diagnosis.get('recommendations', [])
                }
            })

    except Exception as e:
        log.error("generate_diagnose_report failed: %s", e)
        return jsonify({"error": f"LLM 报告生成失败: {str(e)}"}), 500


def _build_llm_report_prompt(diagnosis: dict) -> str:
    """构建 LLM 报告生成 Prompt"""
    triggered = diagnosis.get('rules_triggered', [])
    highlights = diagnosis.get('highlights', [])
    metrics = diagnosis.get('metrics', {})

    lines = [
        f"诊断时间: {diagnosis.get('timestamp', '')}",
        f"目标 Pod: {diagnosis.get('namespace', '')}/{diagnosis.get('pod', '')}",
        f"Java PID: {diagnosis.get('java_pid', '')}",
        f"诊断场景: {diagnosis.get('target', 'general')}",
        f"采集状态: {diagnosis.get('status', 'unknown')}（collection_complete={diagnosis.get('collection_complete', False)}）",
        "",
        "【采集步骤】",
        *[
            f"- {step.get('name')}: {step.get('status')}"
            + (f" — {step.get('error')}" if step.get('error') else "")
            for step in diagnosis.get('steps', [])
        ],
        "",
        "【规则命中】",
    ]

    if triggered:
        for r in triggered:
            lines.append(f"- {r['name']} ({r['severity']}): {r.get('value','?')} (阈值 {r.get('threshold','?')}{r.get('unit','')})")
    else:
        lines.append("无")

    lines.extend(["", "【关键指标】"])
    for label, key, limit in (
            ("Dashboard", "dashboard", 3000),
            ("线程快照", "threads", 5000),
            ("Trace", "trace", 5000)):
        lines.extend(["", f"【{label} 证据】"])
        evidence = metrics.get(key)
        if evidence:
            lines.append(str(evidence)[:limit])
        else:
            error = metrics.get(f"{key}_error")
            lines.append(f"采集失败: {error}" if error else "无数据")

    lines.extend(["", "【高亮】"])
    if highlights:
        lines.extend([f"- {h}" for h in highlights])
    else:
        lines.append("无明显异常")

    lines.extend([
        "",
        "约束：只依据提供的采集证据下结论；采集失败或数据不足时明确说明不确定性。",
        "单次 GC 累积计数不能代表 GC 频率或趋势，不要据此判断 GC 过于频繁。",
        "请生成一份结构化诊断报告，包含：",
        "1. 诊断结论（一句话概括）",
        "2. 问题根因分析",
        "3. 影响范围评估",
        "4. 优化建议（分紧急/中期/长期）",
    ])

    return '\n'.join(lines)
