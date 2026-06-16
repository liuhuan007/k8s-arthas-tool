import re
from dataclasses import dataclass
from typing import Optional


class ErrorCode:
    TIMEOUT = "E0001"
    CONNECTION_FAILED = "E0002"
    PERMISSION_DENIED = "E0003"
    POD_NOT_FOUND = "E1001"
    NAMESPACE_NOT_FOUND = "E1005"
    CLUSTER_UNREACHABLE = "E1007"
    ARTHAS_NOT_CONNECTED = "E2001"
    ARTHAS_COMMAND_FAILED = "E2002"


@dataclass
class MappedError:
    code: str
    message: str
    detail: str
    suggestion: str
    retryable: bool


class ErrorMapper:
    PATTERNS = [
        (re.compile(r"pods?\s+.*not\s+found", re.IGNORECASE), ErrorCode.POD_NOT_FOUND),
        (re.compile(r"namespaces?\s+.*not\s+found", re.IGNORECASE), ErrorCode.NAMESPACE_NOT_FOUND),
        (re.compile(r"Forbidden", re.IGNORECASE), ErrorCode.PERMISSION_DENIED),
        (re.compile(r"unable\s+to\s+connect", re.IGNORECASE), ErrorCode.CLUSTER_UNREACHABLE),
    ]

    SUGGESTIONS = {
        ErrorCode.TIMEOUT: "Check network connectivity and pod health",
        ErrorCode.CONNECTION_FAILED: "Verify the target host and port are reachable",
        ErrorCode.PERMISSION_DENIED: "Check RBAC permissions for this operation",
        ErrorCode.POD_NOT_FOUND: "Verify the pod exists and check the namespace",
        ErrorCode.NAMESPACE_NOT_FOUND: "Verify the namespace exists",
        ErrorCode.CLUSTER_UNREACHABLE: "Check cluster API server connectivity",
        ErrorCode.ARTHAS_NOT_CONNECTED: "Ensure Arthas agent is running on the target pod",
        ErrorCode.ARTHAS_COMMAND_FAILED: "Check Arthas agent logs for command execution errors",
    }

    @classmethod
    def map_kubectl_error(
        cls, stderr: str, returncode: int, timeout_msg: str = ""
    ) -> MappedError:
        if returncode == -1 and timeout_msg:
            return cls._make_error(ErrorCode.TIMEOUT, timeout_msg)

        for pattern, code in cls.PATTERNS:
            if pattern.search(stderr):
                return cls._make_error(code, stderr)

        if returncode != 0:
            return cls._make_error(ErrorCode.CONNECTION_FAILED, stderr)

        return cls._make_error(ErrorCode.CONNECTION_FAILED, stderr)

    @classmethod
    def _make_error(cls, code: str, detail: str) -> MappedError:
        retryable = code in (
            ErrorCode.TIMEOUT,
            ErrorCode.CONNECTION_FAILED,
            ErrorCode.CLUSTER_UNREACHABLE,
        )
        return MappedError(
            code=code,
            message=f"CLI error: {code}",
            detail=detail,
            suggestion=cls.SUGGESTIONS.get(code, "Check logs for details"),
            retryable=retryable,
        )
