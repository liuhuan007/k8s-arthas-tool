import subprocess
import logging
from typing import Any, Dict, List
from .adapter import CLIAdapter, StructuredResult
from .structured_output import StructuredOutput
from .health_checker import HealthChecker
from .safety_guard import SafetyGuard
from .error_mapper import ErrorMapper
from .command_registry import CommandRegistry

log = logging.getLogger(__name__)


class KubectlAdapter(CLIAdapter):
    def __init__(self, kubeconfig: str = "", context: str = ""):
        self.kubeconfig = kubeconfig
        self.context = context

    def _base_cmd(self) -> List[str]:
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd += ["--kubeconfig", self.kubeconfig]
        if self.context:
            cmd += ["--context", self.context]
        return cmd

    def _run(self, args: List[str], timeout: int = 30):
        cmd = self._base_cmd() + args
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout)
            stdout = r.stdout.decode('utf-8', errors='replace') if r.stdout else ''
            stderr = r.stderr.decode('utf-8', errors='replace') if r.stderr else ''
            return r.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"kubectl 超时 ({timeout}s)"
        except FileNotFoundError:
            return -1, "", "kubectl 未找到"

    def execute(self, command: str, params: Dict[str, Any]) -> StructuredResult:
        ns = params.get("namespace", "default")
        risk = SafetyGuard.check_risk("kubectl", command)
        if risk["requires_confirm"]:
            return StructuredResult(ok=False, command=command,
                                    error="REQUIRES_CONFIRMATION",
                                    error_detail={"risk": risk})

        args = self._build_args(command, params, ns)
        rc, stdout, stderr = self._run(args)

        if rc == 0:
            data = StructuredOutput.parse_output(stdout, command)
            health = HealthChecker.check_pod_list(data) if command == "get_pods" and isinstance(data, list) else None
            return StructuredResult(ok=True, command=" ".join(args),
                                    data=data, raw_output=stdout, health=health)
        else:
            error = ErrorMapper.map_kubectl_error(stderr, rc)
            return StructuredResult(ok=False, command=" ".join(args),
                                    error=error.code,
                                    error_detail={"code": error.code, "message": error.message,
                                                  "detail": error.detail, "suggestion": error.suggestion,
                                                  "retryable": error.retryable})

    def _build_args(self, command: str, params: Dict, ns: str) -> List[str]:
        if command == "get_pods":
            args = ["-n", ns, "get", "pods", "-o", "wide"]
            label = params.get("label", "")
            if label:
                args += ["-l", label]
            return args
        elif command == "describe_pod":
            return ["-n", ns, "describe", "pod", params.get("name", "")]
        elif command == "get_pod_logs":
            args = ["-n", ns, "logs", params.get("name", "")]
            if params.get("previous"):
                args.append("--previous")
            return args
        elif command == "delete_pod":
            return ["-n", ns, "delete", "pod", params.get("name", "")]
        elif command == "top_pods":
            return ["-n", ns, "top", "pods", "--no-headers"]
        elif command == "top_nodes":
            return ["top", "nodes", "--no-headers"]
        elif command == "get_events":
            return ["-n", ns, "get", "events", "--sort-by=.lastTimestamp"]
        elif command == "get_nodes":
            return ["get", "nodes", "-o", "wide"]
        elif command == "cluster_info":
            return ["cluster-info"]
        return ["get", command]

    def get_commands(self) -> List[Dict]:
        return CommandRegistry.get_commands("kubectl")

    def health_check(self, target: str = "", params: Dict = None) -> Dict:
        return {"status": "implemented", "target": target}

    def dry_run(self, command: str, params: Dict[str, Any]) -> Dict:
        return SafetyGuard.dry_run("kubectl", command, params)
