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
    
    只要 conn 对象在 _connections 中就返回，让后续实际操作判断是否真正可用。
    """
    from server import _connections, _connections_lock

    if not connection_id:
        with _connections_lock:
            # admin 可用所有连接，非 admin 仅自己的
            if current_user.is_admin:
                alive = [(cid, e) for cid, e in _connections.items() if e.get('conn')]
            else:
                alive = [(cid, e) for cid, e in _connections.items()
                         if e.get('user_id') == current_user.id and e.get('conn')]
            if alive:
                return alive[-1][1]['conn']
        return None

    with _connections_lock:
        entry = _connections.get(connection_id)
        if not entry:
            # 尝试模糊匹配：connection_id 可能与 _connections 的 key 略有差异
            for cid in _connections:
                if connection_id in cid or cid in connection_id:
                    log.warning("_get_alive_connection: fuzzy match %r -> %r", connection_id, cid)
                    entry = _connections[cid]
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
    from server import _connections, _connections_lock

    instances = []
    with _connections_lock:
        for cid, entry in _connections.items():
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
    }

    client = conn.http_client
    engine = RuleEngine()

    def _step(name: str):
        result["steps"].append({"name": name, "time": datetime.now().strftime("%H:%M:%S")})

    # ── Step 1: Dashboard 基线 ──────────────────────────────────────
    _step("dashboard")
    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        dash_resp = ArthasCommandExecutor.execute(conn, "dashboard -n 1", timeout_ms=15000)
        # 从 Arthas 响应中提取核心指标，避免存储完整响应导致 JSON 过大被截断
        dash_body = dash_resp.get('body', dash_resp) if isinstance(dash_resp, dict) else {}
        dash_results = dash_body.get('results', []) if isinstance(dash_body, dict) else []
        if dash_results and isinstance(dash_results[0], dict):
            r0 = dash_results[0]
            all_threads = r0.get("threads", [])
            # 存储完整线程数据，前端按需分页
            result["metrics"]["dashboard"] = json.dumps({
                "body": {
                    "threads": all_threads,
                    "memoryInfo": r0.get("memoryInfo", {}),
                    "gcInfos": r0.get("gcInfos", []),
                    "runtimeInfo": r0.get("runtimeInfo", {}),
                }
            }, ensure_ascii=False)
        else:
            result["metrics"]["dashboard"] = json.dumps(dash_resp, ensure_ascii=False)[:5000]
    except Exception as e:
        result["metrics"]["dashboard_error"] = str(e)

    # ── Step 2: Thread 快照 ───────────────────────────────────────
    _step("thread")
    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        thread_resp = ArthasCommandExecutor.execute(conn, "thread -n 15", timeout_ms=20000)
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
            result["metrics"]["threads"] = json.dumps(thread_resp, ensure_ascii=False)[:5000]
    except Exception as e:
        log.warning("Thread 指标采集失败: %s", e)

    # ── Step 3: Trace（method_slow / general 场景）────────────────
    if target in ("method_slow", "general") and class_pattern:
        _step("trace")
        try:
            from backend.core.arthas_executor import ArthasCommandExecutor
            skip = "--skipJDKMethod true"
            trace_cmd = f"trace {class_pattern} {method_pattern or '*'} -n 10 '{skip} #cost > .5'"
            trace_resp = ArthasCommandExecutor.execute(conn, trace_cmd, timeout_ms=30000)
            trace_raw = json.dumps(trace_resp, ensure_ascii=False)
            result["metrics"]["trace"] = trace_raw[:2000]
        except Exception:
            pass

    # ── Step 4: 规则引擎预筛 ────────────────────────────────────
    _step("rule_engine")
    raw_metrics = extract_metrics_from_diagnosis(result)
    rule_result = engine.evaluate(raw_metrics)
    result["rules_triggered"] = rule_result["triggered"]
    result["highlights"] = rule_result["highlights"]
    result["severity"] = rule_result["severity"]

    # ── Step 5: 生成建议 ──────────────────────────────────────────
    result["recommendations"] = _make_recommendations(result["rules_triggered"], target)

    result["status"] = "completed"
    return result


def _make_recommendations(triggered: list, target: str) -> list:
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
        if target == "oom":
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
        "tool": "dashboard" | "threads" | "trace",
        "args": { ... }           // 可选参数
    }
    """
    d = request.json or {}
    connection_id = d.get('connection_id', '')
    tool = d.get('tool', '')
    args = d.get('args', {})

    conn = _get_alive_connection(connection_id)
    if not conn:
        # 尝试用 _ensure_connection 自动重建
        from server import _ensure_connection
        rebuild_params = _parse_conn_id(connection_id)
        rebuild_d = {**d, **rebuild_params}
        conn, err = _ensure_connection(connection_id, rebuild_d)
        if err:
            log.warning("diagnose_tool: _ensure_connection failed: %s, connection_id=%r", err, connection_id)
    if not conn:
        return jsonify({"error": "Arthas 连接不可用，请先在左侧连接目标 Pod"}), 400

    try:
        from backend.core.arthas_executor import ArthasCommandExecutor
        if tool == 'dashboard':
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

    # 获取连接 — 优先用 _get_alive_connection，失败则用 server._ensure_connection 自动重建
    conn = _get_alive_connection(connection_id)
    if not conn:
        # 尝试用 _ensure_connection 自动重建（与 /api/arthas/exec 相同逻辑）
        from server import _ensure_connection
        # 从 connection_id 解析连接参数，补充到 d 中供 _ensure_connection 使用
        rebuild_params = _parse_conn_id(connection_id)
        rebuild_d = {**d, **rebuild_params}
        conn, err = _ensure_connection(connection_id, rebuild_d)
        if err:
            log.warning("diagnose_performance: _ensure_connection failed: %s, connection_id=%r, rebuild_params=%s", err, connection_id, rebuild_params)
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
        report = _run_diagnosis(conn, target, class_pattern, method_pattern)

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
        "diagnosis": { ... }   // _run_diagnosis 返回的结构化数据
    }
    """
    d = request.json or {}
    diagnosis = d.get('diagnosis', {})

    if not diagnosis:
        return jsonify({"error": "缺少 diagnosis 数据"}), 400

    # 检查 AI 配置
    from models.db import db
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
            return jsonify({
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
        "",
        "【规则命中】",
    ]

    if triggered:
        for r in triggered:
            lines.append(f"- {r['name']} ({r['severity']}): {r.get('value','?')} (阈值 {r.get('threshold','?')}{r.get('unit','')})")
    else:
        lines.append("无")

    lines.extend(["", "【关键指标】"])
    dash = metrics.get('dashboard', '')
    if dash:
        lines.append(dash[:800])
    else:
        lines.append("无 dashboard 数据")

    lines.extend(["", "【高亮】"])
    if highlights:
        lines.extend([f"- {h}" for h in highlights])
    else:
        lines.append("无明显异常")

    lines.extend(["", "请生成一份结构化诊断报告，包含：", "1. 诊断结论（一句话概括）", "2. 问题根因分析", "3. 影响范围评估", "4. 优化建议（分紧急/中期/长期）"])

    return '\n'.join(lines)
