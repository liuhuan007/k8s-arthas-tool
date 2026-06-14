#!/usr/bin/env python3
"""MCP Skill Handler - Bridge between Skill Registry and MCP Agent Tool Gateway.

This module provides the handler function invoked by the WorkflowEngine when
an MCP skill is executed. It translates skill parameters into connection-level
operations using the existing ArthasConnection infrastructure (server._connections).

The handler function signature matches what WorkflowEngine._execute_handler()
expects: func(params: dict, connection_id: str) -> Any

Handler keys:
  - mcp.kubectl_exec   -> Execute arbitrary command in Pod
  - mcp.arthas_command -> Execute Arthas diagnostic command
  - mcp.get_pod_metrics -> Collect Pod resource metrics

Author: Phase 7 T03
"""

import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

# Maps handler_key to implementation function
_MCP_HANDLER_MAP = {
    "mcp.kubectl_exec": "_kubectl_exec",
    "mcp.arthas_command": "_arthas_command",
    "mcp.get_pod_metrics": "_pod_metrics",
}


def execute_mcp_skill(params: Dict[str, Any], connection_id: str) -> Any:
    """Execute an MCP skill via the ArthasConnection infrastructure.

    This function is called by WorkflowEngine._execute_handler() when a skill
    with handler='services.mcp_skill_handler.execute_mcp_skill' is executed.

    Args:
        params: Skill parameters dict. May contain:
            - handler_key (str): Identifies the MCP skill type
            - command (str): Command to execute (kubectl_exec/arthas_command)
            - timeout (int): Command timeout in seconds (default: 30)
            - metrics_type (str): Metrics type (cpu/memory/network/all)
        connection_id: Connection identifier (format: cluster/namespace/pod)

    Returns:
        dict: Execution result with keys:
            - ok (bool): Whether execution succeeded
            - result (dict): Skill-specific result data
            - error (str): Error message if failed
            - handler_key (str): The MCP skill type that was executed
    """
    handler_key = params.get("handler_key", "")

    log.info(
        "Executing MCP skill: handler_key=%s, connection_id=%s",
        handler_key, connection_id,
    )

    handler_name = _MCP_HANDLER_MAP.get(handler_key)
    if not handler_name:
        return {
            "ok": False,
            "error": f"Unknown MCP handler_key: {handler_key}",
        }

    # Resolve connection from server._connections
    conn = _get_connection(connection_id)
    if not conn:
        return {
            "ok": False,
            "error": f"Connection not found or inactive: {connection_id}",
        }

    # Dispatch to handler implementation
    handler_func = globals().get(handler_name)
    if not handler_func:
        return {
            "ok": False,
            "error": f"Handler function not found: {handler_name}",
        }

    try:
        result = handler_func(params, conn)
        return {
            "ok": True,
            "result": result,
            "handler_key": handler_key,
        }
    except Exception as e:
        log.error("MCP skill execution failed: %s - %s", handler_key, e, exc_info=True)
        return {
            "ok": False,
            "error": str(e),
        }


def _get_connection(connection_id: str):
    """Retrieve the active ArthasConnection from server._connections.

    Args:
        connection_id: Connection identifier (format: cluster/namespace/pod)

    Returns:
        ArthasConnection object or None if not found/inactive.
    """
    try:
        from backend.app_context import connections, connections_lock
        with connections_lock:
            entry = connections.get(connection_id)
        if entry and entry.get("conn"):
            return entry["conn"]
        return None
    except Exception as e:
        log.warning("Failed to retrieve connection %s: %s", connection_id, e)
        return None


# ── Handler implementations ────────────────────────────────────────────


def _kubectl_exec(params: Dict[str, Any], connection) -> Dict[str, Any]:
    """Execute a command inside the Pod via ArthasConnection agent.

    Args:
        params: Must contain 'command' (str). Optional 'timeout' (int, seconds).
        connection: Active ArthasConnection with agent_mgr.

    Returns:
        dict with stdout, stderr, exit_code.
    """
    command = params.get("command")
    if not command:
        raise ValueError("command is required")

    timeout = params.get("timeout", 30)

    if not connection or not hasattr(connection, "agent_mgr") or not connection.agent_mgr:
        raise ValueError("Arthas connection not available")

    rc, out, err = connection.agent_mgr._exec(command, timeout=timeout)

    output = out[:8000] if out else ""
    if len(out or "") > 8000:
        output += f"\n... (truncated, total {len(out)} chars)"

    return {
        "exit_code": rc,
        "stdout": output,
        "stderr": (err or "")[:2000],
        "command": command,
    }


def _arthas_command(params: Dict[str, Any], connection) -> Dict[str, Any]:
    """Execute an Arthas diagnostic command via ArthasCommandExecutor.

    Args:
        params: Must contain 'command' (str). Optional 'timeout' (int, seconds).
        connection: Active ArthasConnection with http_client.

    Returns:
        dict with state, output, command.
    """
    command = params.get("command")
    if not command:
        raise ValueError("command is required")

    timeout = params.get("timeout", 30)

    if not connection or not getattr(connection, "http_client", None):
        raise ValueError("Arthas HTTP connection not available")

    # Forbidden command safety check
    forbidden = ["redefine", "retransform", "ognl", "reset", "shutdown"]
    cmd_name = command.split()[0].lower() if command else ""
    if cmd_name in forbidden:
        raise ValueError(f"Forbidden Arthas command: {cmd_name}")

    from backend.core.arthas_executor import ArthasCommandExecutor

    result = ArthasCommandExecutor.execute(
        connection,
        command,
        timeout_ms=timeout * 1000,
        skip_audit=False,
        skip_history=False,
    )

    state = result.get("state", "")
    body = result.get("body", [])

    if isinstance(body, list):
        output = "\n".join(str(line) for line in body)
    else:
        output = str(body)

    # Truncate excessively long output
    if len(output) > 8000:
        output = output[:8000] + f"\n... (truncated, total {len(output)} chars)"

    return {
        "state": state,
        "output": output,
        "command": command,
        "duration_ms": result.get("duration_ms", 0),
    }


def _pod_metrics(params: Dict[str, Any], connection) -> Dict[str, Any]:
    """Collect Pod resource metrics (CPU, memory, network).

    Args:
        params: Optional 'metrics_type' (cpu|memory|network|all).
        connection: Active ArthasConnection with agent_mgr.

    Returns:
        dict with metrics data.
    """
    metrics_type = params.get("metrics_type", "all")

    if not connection or not hasattr(connection, "agent_mgr") or not connection.agent_mgr:
        raise ValueError("Arthas connection not available")

    commands = {
        "cpu": "top -bn1 | head -5",
        "memory": "free -b 2>/dev/null || cat /proc/meminfo | head -10",
        "network": "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | wc -l; ss -tlnp 2>/dev/null | head -20",
        "all": (
            'echo "=== CPU ==="; top -bn1 | head -5; '
            'echo "=== Memory ==="; free -b 2>/dev/null; '
            'echo "=== Disk ==="; df -h / 2>/dev/null | tail -1; '
            'echo "=== Network ==="; ss -s 2>/dev/null'
        ),
    }

    command = commands.get(metrics_type, commands["all"])

    rc, out, err = connection.agent_mgr._exec(command, timeout=10)

    return {
        "metrics_type": metrics_type,
        "exit_code": rc,
        "data": (out or "")[:3000] if rc == 0 else (err or "")[:2000],
    }
