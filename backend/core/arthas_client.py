"""
Arthas HTTP API 客户端
官方文档: https://arthas.aliyun.com/en/doc/http-api.html
"""
import json
import logging
import time
import urllib.request

log = logging.getLogger(__name__)


class ArthasHttpClient:
    """
    Arthas HTTP API 客户端。
    通过本地 port-forward 端口访问 Pod 内 Arthas。
    """

    def __init__(self, local_port: int):
        self.url = f"http://127.0.0.1:{local_port}/api"
        self.timeout = 35

    def _post(self, payload: dict, timeout: int = 0) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            raw = resp.read().decode("utf-8").strip()

        # Arthas HTTP API 有时返回多行拼接 JSON
        if raw.startswith("{"):
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            if len(lines) > 1:
                merged = {}
                for line in lines:
                    try:
                        parsed = json.loads(line)
                        # 含 state 的行是最终状态响应，优先取
                        if "state" in parsed:
                            merged = parsed
                        else:
                            merged.update(parsed)
                    except Exception:
                        pass
                return merged
        return json.loads(raw)

    def ping(self, retries: int = 3, delay: float = 1.5) -> bool:
        """Ping with retry"""
        for i in range(retries):
            try:
                r = self._post({"action": "exec", "command": "version"}, timeout=5)
                if r.get("state") in ("SUCCEEDED", "succeeded"):
                    return True
            except Exception as e:
                log.debug("ping attempt %d failed: %s", i + 1, e)
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