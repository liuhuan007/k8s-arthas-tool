import json
import logging
import urllib.request
from typing import Any, Dict, List
from .adapter import CLIAdapter, StructuredResult
from .safety_guard import SafetyGuard
from .error_mapper import ErrorCode
from .command_registry import CommandRegistry

log = logging.getLogger(__name__)


class ArthasAdapter(CLIAdapter):
    def __init__(self, base_url: str = ""):
        self.base_url = base_url.rstrip('/')

    def execute(self, command: str, params: Dict[str, Any]) -> StructuredResult:
        if not self.base_url:
            return StructuredResult(ok=False, command=command,
                                    error=ErrorCode.ARTHAS_NOT_CONNECTED,
                                    error_detail={"message": "Arthas base_url not configured"})

        risk = SafetyGuard.check_risk("arthas", command)
        if risk["requires_confirm"]:
            return StructuredResult(ok=False, command=command,
                                    error="REQUIRES_CONFIRMATION",
                                    error_detail={"risk": risk})

        arthas_cmd = self._build_arthas_command(command, params)
        try:
            url = f"{self.base_url}/api/exec"
            payload = json.dumps({"command": arthas_cmd}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, method='POST')
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))

            output = result.get('body', [])
            if isinstance(output, list):
                raw = '\n'.join(str(l) for l in output)
            else:
                raw = str(output)

            return StructuredResult(ok=True, command=arthas_cmd,
                                    data={"output": raw}, raw_output=raw)
        except Exception as e:
            return StructuredResult(ok=False, command=arthas_cmd,
                                    error=ErrorCode.ARTHAS_COMMAND_FAILED,
                                    error_detail={"message": str(e)})

    def _build_arthas_command(self, command: str, params: Dict) -> str:
        if command == "thread":
            n = params.get("top_n", 5)
            return f"thread -n {n}"
        elif command == "thread_deadlock":
            return "thread -b"
        elif command == "dashboard":
            n = params.get("n", 1)
            return f"dashboard -n {n}"
        elif command == "trace":
            cls = params.get("class_pattern", "")
            method = params.get("method_pattern", "*")
            n = params.get("sample_count", 5)
            return f"trace {cls} {method} -n {n}"
        elif command == "jad":
            return f"jad {params.get('class_pattern', '')}"
        elif command == "sc":
            return f"sc -d {params.get('class_pattern', '')}"
        elif command == "watch":
            cls = params.get("class_pattern", "")
            method = params.get("method_pattern", "*")
            expr = params.get("expr", "{params,returnObj}")
            return f"watch {cls} {method} '{expr}' -e -x 2"
        elif command == "heapdump":
            path = params.get("path", "/tmp/heap.hprof")
            return f"heapdump --live {path}"
        elif command == "profiler":
            event = params.get("event", "cpu")
            duration = params.get("duration", 30)
            return f"profiler start --event {event} --duration {duration}"
        return command

    def get_commands(self) -> List[Dict]:
        return CommandRegistry.get_commands("arthas")

    def health_check(self, target: str = "", params: Dict = None) -> Dict:
        if not self.base_url:
            return {"status": "disconnected"}
        try:
            url = f"{self.base_url}/api/version"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"status": "connected"}
        except Exception:
            return {"status": "disconnected"}

    def dry_run(self, command: str, params: Dict[str, Any]) -> Dict:
        arthas_cmd = self._build_arthas_command(command, params)
        return {"dry_run": True, "command": arthas_cmd, "risk_level": SafetyGuard.check_risk("arthas", command)["level"]}
