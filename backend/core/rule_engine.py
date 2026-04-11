"""
轻量规则引擎 — 性能诊断预筛层
在 LLM 分析前对 Arthas 原始数据进行规则匹配，
打标签 + 提取高价值片段，避免全量数据丢给 LLM 产生噪声。

规则设计原则：
- 阈值可配置，通过 PRESET_RULES 统一管理
- 返回结构化结果，包含：触发规则、高亮片段、摘要
- 与诊断端点解耦，可独立调用
"""
import re
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# 预设规则定义
# ═══════════════════════════════════════════════════════════════════════════════

class Rule:
    """单条规则定义"""
    def __init__(self, rule_id: str, name: str, description: str,
                 threshold: float, unit: str = "ms", severity: str = "warn"):
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.threshold = threshold
        self.unit = unit
        self.severity = severity  # warn / critical

    def match(self, value: float) -> bool:
        return value > self.threshold


PRESET_RULES: Dict[str, Rule] = {
    # ── 方法耗时 ────────────────────────────────────────────────
    "slow_method": Rule(
        rule_id="slow_method",
        name="慢方法",
        description="方法调用耗时超过阈值",
        threshold=500.0,
        unit="ms",
        severity="warn"
    ),
    "very_slow_method": Rule(
        rule_id="very_slow_method",
        name="极慢方法",
        description="方法调用耗时超过 2 秒",
        threshold=2000.0,
        unit="ms",
        severity="critical"
    ),

    # ── 内存规则 ─────────────────────────────────────────────────
    "high_old_gen": Rule(
        rule_id="high_old_gen",
        name="Old 区内存高",
        description="老年代内存使用率偏高",
        threshold=800.0,
        unit="MB",
        severity="warn"
    ),
    "very_high_old_gen": Rule(
        rule_id="very_high_old_gen",
        name="Old 区内存危险",
        description="老年代接近或达到上限",
        threshold=1500.0,
        unit="MB",
        severity="critical"
    ),

    # ── CPU 规则 ─────────────────────────────────────────────────
    "high_cpu": Rule(
        rule_id="high_cpu",
        name="CPU 使用率高",
        description="JVM CPU 使用率超过阈值",
        threshold=80.0,
        unit="%",
        severity="warn"
    ),
    "very_high_cpu": Rule(
        rule_id="very_high_cpu",
        name="CPU 使用率危险",
        description="JVM CPU 使用率超过 95%",
        threshold=95.0,
        unit="%",
        severity="critical"
    ),

    # ── 线程规则 ─────────────────────────────────────────────────
    "thread_blocked": Rule(
        rule_id="thread_blocked",
        name="BLOCKED 线程多",
        description="BLOCKED 状态线程数量过多",
        threshold=3.0,
        unit="count",
        severity="warn"
    ),
    "thread_deadlock": Rule(
        rule_id="thread_deadlock",
        name="死锁检测",
        description="线程死锁",
        threshold=1.0,
        unit="count",
        severity="critical"
    ),

    # ── GC 规则 ──────────────────────────────────────────────────
    "high_gc_freq": Rule(
        rule_id="high_gc_freq",
        name="GC 频率高",
        description="Young GC 次数过多",
        threshold=100.0,
        unit="count",
        severity="warn"
    ),
    "full_gc": Rule(
        rule_id="full_gc",
        name="Full GC",
        description="发生 Full GC",
        threshold=1.0,
        unit="count",
        severity="critical"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# 规则引擎核心
# ═══════════════════════════════════════════════════════════════════════════════

class RuleEngine:
    """
    规则引擎：接收 Arthas 原始数据，输出规则命中结果 + 高亮摘要。

    使用方式：
        engine = RuleEngine()
        result = engine.evaluate({
            "trace_ms": 1200,
            "cpu_percent": 85,
            "old_gen_mb": 1200,
            "blocked_threads": 5,
        })
    """

    def __init__(self, custom_rules: Optional[Dict[str, Rule]] = None):
        self.rules = dict(PRESET_RULES)
        if custom_rules:
            self.rules.update(custom_rules)

    def evaluate(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估指标是否命中规则。

        支持的 metric key：
          trace_ms          — 方法耗时（毫秒）
          cpu_percent       — CPU 使用率（%）
          old_gen_mb        — Old 区内存（MB）
          young_gc_count    — Young GC 次数
          full_gc_count     — Full GC 次数
          blocked_threads   — BLOCKED 线程数量
          deadlock_found    — 是否检测到死锁（bool）
        """
        triggered = []
        highlights = []
        severity = "normal"

        # 方法耗时
        if "trace_ms" in metrics:
            v = float(metrics["trace_ms"])
            for rid in ("slow_method", "very_slow_method"):
                rule = self.rules.get(rid)
                if rule and rule.match(v):
                    triggered.append({
                        "rule_id": rid,
                        "name": rule.name,
                        "severity": rule.severity,
                        "value": v,
                        "threshold": rule.threshold,
                        "unit": rule.unit,
                        "description": rule.description
                    })
                    highlights.append(f"⚠️ {rule.name}: {v:.0f}{rule.unit}（阈值 {rule.threshold}{rule.unit}）")
                    if rule.severity == "critical":
                        severity = "critical"

        # CPU
        if "cpu_percent" in metrics:
            v = float(metrics["cpu_percent"])
            for rid in ("high_cpu", "very_high_cpu"):
                rule = self.rules.get(rid)
                if rule and rule.match(v):
                    triggered.append({
                        "rule_id": rid,
                        "name": rule.name,
                        "severity": rule.severity,
                        "value": v,
                        "threshold": rule.threshold,
                        "unit": rule.unit,
                        "description": rule.description
                    })
                    highlights.append(f"⚠️ {rule.name}: {v:.1f}%")
                    if rule.severity == "critical":
                        severity = "critical"

        # Old 区
        if "old_gen_mb" in metrics:
            v = float(metrics["old_gen_mb"])
            for rid in ("high_old_gen", "very_high_old_gen"):
                rule = self.rules.get(rid)
                if rule and rule.match(v):
                    triggered.append({
                        "rule_id": rid,
                        "name": rule.name,
                        "severity": rule.severity,
                        "value": v,
                        "threshold": rule.threshold,
                        "unit": rule.unit,
                        "description": rule.description
                    })
                    highlights.append(f"⚠️ {rule.name}: {v:.0f}MB")
                    if rule.severity == "critical":
                        severity = "critical"

        # BLOCKED 线程
        if "blocked_threads" in metrics:
            v = float(metrics["blocked_threads"])
            rule = self.rules.get("thread_blocked")
            if rule and rule.match(v):
                triggered.append({
                    "rule_id": "thread_blocked",
                    "name": rule.name,
                    "severity": rule.severity,
                    "value": int(v),
                    "threshold": int(rule.threshold),
                    "unit": "count",
                    "description": rule.description
                })
                highlights.append(f"⚠️ {rule.name}: {int(v)} 个")
                severity = "critical"

        # 死锁
        if metrics.get("deadlock_found"):
            rule = self.rules.get("thread_deadlock")
            if rule:
                triggered.append({
                    "rule_id": "thread_deadlock",
                    "name": rule.name,
                    "severity": "critical",
                    "value": 1,
                    "threshold": 1,
                    "unit": "count",
                    "description": rule.description
                })
                highlights.append("🔴 死锁检测: 发现线程死锁！")
                severity = "critical"

        # GC 次数
        if "young_gc_count" in metrics:
            v = float(metrics["young_gc_count"])
            rule = self.rules.get("high_gc_freq")
            if rule and rule.match(v):
                triggered.append({
                    "rule_id": "high_gc_freq",
                    "name": rule.name,
                    "severity": rule.severity,
                    "value": int(v),
                    "threshold": int(rule.threshold),
                    "unit": "count",
                    "description": rule.description
                })
                highlights.append(f"⚠️ {rule.name}: {int(v)} 次")

        if "full_gc_count" in metrics:
            v = float(metrics["full_gc_count"])
            rule = self.rules.get("full_gc")
            if rule and rule.match(v):
                triggered.append({
                    "rule_id": "full_gc",
                    "name": rule.name,
                    "severity": "critical",
                    "value": int(v),
                    "threshold": int(rule.threshold),
                    "unit": "count",
                    "description": rule.description
                })
                highlights.append(f"🔴 {rule.name}: {int(v)} 次")
                severity = "critical"

        return {
            "triggered": triggered,
            "highlights": highlights,
            "severity": severity,
            "summary": self._make_summary(triggered),
        }

    def _make_summary(self, triggered: List[Dict]) -> str:
        if not triggered:
            return "✅ 未检测到异常指标，JVM 运行正常"
        critical = [r for r in triggered if r["severity"] == "critical"]
        warns = [r for r in triggered if r["severity"] == "warn"]
        parts = []
        if critical:
            parts.append(f"🔴 {len(critical)} 个严重问题")
        if warns:
            parts.append(f"⚠️ {len(warns)} 个警告")
        return "，".join(parts) if parts else "未检测到异常"


# ═══════════════════════════════════════════════════════════════════════════════
# 便捷入口
# ═══════════════════════════════════════════════════════════════════════════════

# 全局单例，供 ai_chat.py 直接调用
_default_engine = RuleEngine()


def prescreen(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    入口函数：从 Arthas 原始数据中提取指标并运行规则预筛。

    data 格式示例（来自 _arthas_diagnose_performance）：
    {
        "trace_ms": 1200,
        "cpu_percent": 85,
        "old_gen_mb": 1200,
        "blocked_threads": 5,
        "deadlock_found": False,
        "young_gc_count": 200,
        "full_gc_count": 1,
    }
    """
    return _default_engine.evaluate(data)


def extract_metrics_from_diagnosis(diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    """
    从诊断结果中提取规则引擎所需的指标。
    支持从 dashboard/thread/trace 的原始文本中正则提取。
    """
    import re
    metrics: Dict[str, Any] = {}

    # 从 dashboard 原始文本提取
    dash = diagnosis.get("metrics", {}).get("dashboard", "")
    if dash:
        cpu = re.search(r'cpu\s*=\s*(\d+(?:\.\d+)?)\s*%', dash, re.I)
        if cpu:
            metrics["cpu_percent"] = float(cpu.group(1))

        old = re.search(r'Old[^\d]*(\d+(?:\.\d+)?)\s*(MB|GB)', dash, re.I)
        if old:
            v = float(old.group(1))
            metrics["old_gen_mb"] = v * (1024 if old.group(2) == "GB" else 1)

        ygc = re.search(r'YGC[^\d]*(\d+)', dash, re.I)
        if ygc:
            metrics["young_gc_count"] = int(ygc.group(1))

        fgc = re.search(r'FGC[^\d]*(\d+)', dash, re.I)
        if fgc:
            metrics["full_gc_count"] = int(fgc.group(1))

    # 从 thread 原始文本提取 BLOCKED 数量
    threads_raw = diagnosis.get("metrics", {}).get("threads", "")
    if threads_raw:
        metrics["blocked_threads"] = threads_raw.lower().count('"state":"blocked"')

    # 从 deadlock_info 提取
    if diagnosis.get("deadlock_info"):
        metrics["deadlock_found"] = True

    # 从 trace 原始文本提取耗时
    trace_raw = diagnosis.get("metrics", {}).get("trace", "")
    if trace_raw:
        # 提取最大耗时（ms）
        costs = re.findall(r'(\d+(?:\.\d+)?)\s*ms', trace_raw)
        if costs:
            metrics["trace_ms"] = max(float(c) for c in costs)

    return metrics
