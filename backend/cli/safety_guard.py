from typing import Dict, Any
from .adapter import RiskLevel


class SafetyGuard:
    RISK_MAP = {
        ("kubectl", "get_pods"): RiskLevel.READ,
        ("kubectl", "describe_pod"): RiskLevel.READ,
        ("kubectl", "get_pod_logs"): RiskLevel.READ,
        ("kubectl", "get_events"): RiskLevel.READ,
        ("kubectl", "get_nodes"): RiskLevel.READ,
        ("kubectl", "top_pods"): RiskLevel.READ,
        ("kubectl", "top_nodes"): RiskLevel.READ,
        ("kubectl", "cluster_info"): RiskLevel.READ,
        ("kubectl", "exec_in_pod"): RiskLevel.LOW,
        ("kubectl", "port_forward"): RiskLevel.LOW,
        ("kubectl", "delete_pod"): RiskLevel.HIGH,
        ("arthas", "thread"): RiskLevel.READ,
        ("arthas", "thread_deadlock"): RiskLevel.READ,
        ("arthas", "dashboard"): RiskLevel.READ,
        ("arthas", "trace"): RiskLevel.READ,
        ("arthas", "watch"): RiskLevel.READ,
        ("arthas", "jad"): RiskLevel.READ,
        ("arthas", "sc"): RiskLevel.READ,
        ("arthas", "sm"): RiskLevel.READ,
        ("arthas", "heapdump"): RiskLevel.HIGH,
        ("arthas", "profiler"): RiskLevel.MEDIUM,
    }

    @classmethod
    def check_risk(cls, cli: str, command: str) -> Dict[str, Any]:
        level = cls.RISK_MAP.get((cli, command), RiskLevel.READ)
        return {
            "level": level,
            "requires_confirm": level in (RiskLevel.HIGH, RiskLevel.MEDIUM),
            "dry_run_supported": level in (RiskLevel.HIGH,),
        }

    @classmethod
    def dry_run(cls, cli: str, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        risk = cls.check_risk(cli, command)
        if cli == "kubectl" and command == "delete_pod":
            name = params.get("name", "<pod>")
            ns = params.get("namespace", "default")
            return {
                "dry_run": True,
                "command": f"kubectl delete pod {name} -n {ns} --dry-run=client",
                "risk_level": risk["level"],
                "requires_confirmation": risk["requires_confirm"],
            }
        return {"dry_run": True, "command": f"{cli} {command}", "risk_level": risk["level"]}
