#!/usr/bin/env python3
"""Profiler Skill Handler - Bridge between Skill Registry and ProfilerWorkflow.

This module provides the handler function invoked by the WorkflowEngine when
a profiler skill is executed. It translates skill parameters into
ProfilerService calls, maintaining full compatibility with the existing
profiler infrastructure (profiler_tasks table, ProfilerWorkflow, etc.).

The handler function signature matches what WorkflowEngine._execute_handler()
expects: func(params: dict, connection_id: str) -> Any

Author: Phase 7 T01
"""
import json
import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

# Maps handler_key to (task_type, default_event, default_format)
_PROFILER_TYPE_MAP = {
    "profiler.cpu": ("cpu", "cpu", "html"),
    "profiler.jfr": ("jfr", "jfr", "jfr"),
    "profiler.threaddump": ("threaddump", "threaddump", "txt"),
    "profiler.heapdump": ("heapdump", "heapdump", "bin"),
}


def execute_profiler_skill(params: Dict[str, Any], connection_id: str) -> Any:
    """Execute a profiler skill via ProfilerService.

    This function is called by WorkflowEngine._execute_handler() when a skill
    with handler='services.profiler_skill_handler.execute_profiler_skill' is
    executed. It delegates to ProfilerService which manages the profiler_tasks
    table and ProfilerWorkflow execution.

    Args:
        params: Skill parameters dict. May contain:
            - handler_key (str): Identifies the profiler type (profiler.cpu/jfr/threaddump/heapdump)
            - duration (int): Sampling duration in seconds (default: 30-120 depending on type)
            - frequency (int): Sampling frequency in Hz (CPU only, default: 99)
            - format (str): Output format (html/jfr/collapsed/txt/bin)
            - settings (str): JFR settings profile (JFR only, default: 'profile')
            - live_only (bool): Heap dump live-only flag (default: True)
        connection_id: Connection identifier (format: cluster/namespace/pod)

    Returns:
        dict: Execution result with keys:
            - ok (bool): Whether execution succeeded
            - task_id (str): Profiler task ID for status tracking
            - message (str): Human-readable status message
            - handler_key (str): The profiler type that was executed
    """
    handler_key = params.get("handler_key", "profiler.cpu")

    type_info = _PROFILER_TYPE_MAP.get(handler_key)
    if not type_info:
        return {
            "ok": False,
            "error": f"Unknown profiler handler_key: {handler_key}",
        }

    task_type, default_event, default_format = type_info
    duration = int(params.get("duration", 60))
    fmt = params.get("format", default_format)
    event = params.get("event", default_event)

    log.info(
        "Executing profiler skill: handler_key=%s, connection_id=%s, duration=%s, format=%s",
        handler_key, connection_id, duration, fmt,
    )

    try:
        from services.profiler_service import get_profiler_service
        service = get_profiler_service()

        # Create the profiler task (inserts into profiler_tasks table)
        task_id = service.create_task(
            connection_id=connection_id,
            task_type=task_type,
            event=event,
            duration=duration,
            fmt=fmt,
            user_id=None,  # Will be set by the calling context if available
        )

        # Start execution (launches ProfilerWorkflow in background thread)
        result = service.start_task(task_id)

        if result.get("success"):
            return {
                "ok": True,
                "task_id": task_id,
                "message": result.get("message", "Profiler task started"),
                "handler_key": handler_key,
                "task_type": task_type,
                "duration": duration,
                "format": fmt,
            }
        else:
            return {
                "ok": False,
                "task_id": task_id,
                "error": result.get("message", "Failed to start profiler task"),
            }

    except Exception as e:
        log.error("Profiler skill execution failed: %s", e, exc_info=True)
        return {
            "ok": False,
            "error": str(e),
        }
