#!/usr/bin/env python3
"""Agent Tool Gateway 服务 - 受控工具暴露、权限控制、审计

本模块提供 Agent 工具网关，负责：
- 受控工具暴露
- 权限控制
- 审计日志
- 工具执行管理

支持与 Agent SDK 集成，提供统一的工具调用接口。

Author: Kou (software-engineer)
Created: 2025-05-25
"""
import json
import logging
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

log = logging.getLogger(__name__)


class AgentToolGateway:
    """Agent 工具网关 - 受控工具暴露"""

    def __init__(self):
        from models.db import get_db
        self.db = get_db()
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._register_default_tools()

    def _get_connection(self, connection_id: str):
        """获取活跃的 Arthas 连接"""
        try:
            from server import _connections, _connections_lock
            with _connections_lock:
                entry = _connections.get(connection_id)
            if entry and entry.get('conn'):
                conn = entry['conn']
                # 验证连接是否存活
                if hasattr(conn, 'http_client') and conn.http_client:
                    return conn
            return None
        except Exception:
            return None

    def _register_default_tools(self):
        """注册默认工具"""
        # 执行诊断能力
        self.register_tool(
            name="execute_capability",
            handler=self._execute_capability,
            description="执行指定的诊断能力",
            parameters={
                "type": "object",
                "properties": {
                    "capability_id": {"type": "integer", "description": "能力ID"},
                    "params": {"type": "object", "description": "参数"}
                },
                "required": ["capability_id"]
            },
            risk_level="medium"
        )

        # 获取Pod状态
        self.register_tool(
            name="get_pod_status",
            handler=self._get_pod_status,
            description="获取指定Pod的运行状态",
            parameters={
                "type": "object",
                "properties": {
                    "connection_id": {"type": "string", "description": "连接ID (格式: cluster/namespace/pod)"},
                    "detail": {"type": "string", "enum": ["basic", "processes", "network"], "default": "basic"}
                },
                "required": ["connection_id"]
            },
            risk_level="low"
        )

        # 获取Pod指标
        self.register_tool(
            name="get_pod_metrics",
            handler=self._get_pod_metrics,
            description="获取指定Pod的资源使用指标",
            parameters={
                "type": "object",
                "properties": {
                    "connection_id": {"type": "string", "description": "连接ID (格式: cluster/namespace/pod)"}
                },
                "required": ["connection_id"]
            },
            risk_level="low"
        )

        # 列出可用能力
        self.register_tool(
            name="list_capabilities",
            handler=self._list_capabilities,
            description="列出所有可用的诊断能力",
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "能力类别过滤"}
                }
            },
            risk_level="low"
        )

        # 搜索能力
        self.register_tool(
            name="search_capabilities",
            handler=self._search_capabilities,
            description="根据关键词搜索诊断能力",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["keyword"]
            },
            risk_level="low"
        )

        # 获取连接信息
        self.register_tool(
            name="get_connection_info",
            handler=self._get_connection_info,
            description="获取指定连接的详细信息",
            parameters={
                "type": "object",
                "properties": {
                    "connection_id": {"type": "string", "description": "连接ID"}
                },
                "required": ["connection_id"]
            },
            risk_level="low"
        )

        # 获取诊断执行状态
        self.register_tool(
            name="get_execution_status",
            handler=self._get_execution_status,
            description="获取诊断执行的状态和结果",
            parameters={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "执行ID"}
                },
                "required": ["run_id"]
            },
            risk_level="low"
        )

        # 执行 Arthas 命令
        self.register_tool(
            name="execute_arthas_command",
            handler=self._execute_arthas_command,
            description="执行单条 Arthas 命令",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Arthas 命令"},
                    "connection_id": {"type": "string", "description": "连接ID"}
                },
                "required": ["command", "connection_id"]
            },
            risk_level="medium"
        )

        # 获取 JVM 状态
        self.register_tool(
            name="get_jvm_status",
            handler=self._get_jvm_status,
            description="获取 JVM 的整体状态（dashboard）",
            parameters={
                "type": "object",
                "properties": {
                    "connection_id": {"type": "string", "description": "连接ID"}
                },
                "required": ["connection_id"]
            },
            risk_level="low"
        )

        # 获取线程状态
        self.register_tool(
            name="get_thread_status",
            handler=self._get_thread_status,
            description="获取 Java 线程状态",
            parameters={
                "type": "object",
                "properties": {
                    "connection_id": {"type": "string", "description": "连接ID"},
                    "thread_name": {"type": "string", "description": "线程名（可选）"}
                },
                "required": ["connection_id"]
            },
            risk_level="low"
        )

        # ── Profiler 工具（Phase 7 新增）─────────────────────────────
        # 启动性能采样
        self.register_tool(
            name="start_profiler",
            handler=self._start_profiler,
            description="启动性能采样（CPU/JFR/ThreadDump/HeapDump）",
            parameters={
                "type": "object",
                "properties": {
                    "connection_id": {"type": "string", "description": "连接ID"},
                    "type": {"type": "string", "enum": ["cpu", "jfr", "threaddump", "heapdump"], "description": "采样类型"},
                    "duration": {"type": "integer", "description": "采样时长（秒）", "default": 60}
                },
                "required": ["connection_id", "type"]
            },
            risk_level="medium"
        )

        # 停止性能采样
        self.register_tool(
            name="stop_profiler",
            handler=self._stop_profiler,
            description="停止性能采样",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"}
                },
                "required": ["task_id"]
            },
            risk_level="low"
        )

        # 查询采样任务状态
        self.register_tool(
            name="get_profiler_status",
            handler=self._get_profiler_status,
            description="查询性能采样任务状态",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"}
                },
                "required": ["task_id"]
            },
            risk_level="low"
        )

    def register_tool(self, name: str, handler: Callable,
                     description: str, parameters: Dict[str, Any],
                     risk_level: str = "low"):
        """注册工具"""
        self.tools[name] = {
            "handler": handler,
            "description": description,
            "parameters": parameters,
            "risk_level": risk_level
        }

    def execute_tool(self, tool_name: str, params: Dict[str, Any],
                    user_id: int = None, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行工具"""
        tool = self.tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}

        # 检查权限
        if not self._check_permission(tool_name, user_id):
            return {"success": False, "error": "Permission denied"}

        # 执行工具
        try:
            result = tool['handler'](params, context or {})

            # 记录审计日志
            self._log_audit(tool_name, params, user_id, context)

            return {"success": True, "result": result}
        except Exception as e:
            log.error(f"Tool execution failed: {tool_name}, error: {e}")
            return {"success": False, "error": str(e)}

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取工具定义（供 Agent 使用）"""
        definitions = []
        for name, tool in self.tools.items():
            definitions.append({
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"]
            })
        return definitions

    def _check_permission(self, tool_name: str, user_id: int = None) -> bool:
        """检查权限：high 风险工具仅 admin 可用"""
        tool = self.tools.get(tool_name)
        if not tool:
            return False
        risk_level = tool.get('risk_level', 'low')
        if risk_level != 'high':
            return True
        if not user_id:
            return False
        try:
            from models.db import db
            user = db.fetch_one('SELECT is_admin FROM users WHERE id = ?', (user_id,))
            return bool(user and user.get('is_admin'))
        except Exception:
            return False

    def _log_audit(self, tool_name: str, params: Dict[str, Any],
                  user_id: int = None, context: Dict[str, Any] = None):
        """记录审计日志"""
        from services.audit_service import log_audit_action
        log_audit_action(
            action=f"agent_tool:{tool_name}",
            resource_type="agent_tool",
            resource_id=tool_name,
            details=json.dumps({
                "params": params,
                "user_id": user_id,
                "context": context
            })
        )

    def _execute_capability(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """执行诊断能力"""
        from services.workflow_engine import get_workflow_engine

        capability_id = params.get('capability_id')
        skill_params = params.get('params', {})
        connection_id = context.get('connection_id')
        user_id = context.get('user_id')

        if not capability_id:
            raise ValueError("capability_id is required")
        if not connection_id:
            raise ValueError("connection_id is required in context")

        engine = get_workflow_engine()
        run_id = engine.execute_skill(
            capability_id=capability_id,
            params=skill_params,
            connection_id=connection_id,
            user_id=user_id
        )

        return {"run_id": run_id}

    def _get_pod_status(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """获取Pod状态"""
        connection_id = params.get('connection_id')
        detail = params.get('detail', 'basic')
        if not connection_id:
            raise ValueError("connection_id is required")

        conn = self._get_connection(connection_id)
        if not conn:
            return {"error": f"连接 {connection_id} 不可用"}

        try:
            if detail == 'processes':
                rc, out, err = conn.agent_mgr._exec('ps aux --sort=-%cpu | head -20', timeout=10)
                return {"processes": out[:3000] if rc == 0 else err}
            elif detail == 'network':
                rc, out, err = conn.agent_mgr._exec('cat /proc/net/tcp /proc/net/tcp6 2>/dev/null | wc -l; ss -tlnp 2>/dev/null | head -20', timeout=10)
                return {"network": out[:3000] if rc == 0 else err}
            else:
                rc, out, err = conn.agent_mgr._exec(
                    'echo "=== Pod Status ==="; '
                    'cat /proc/1/status 2>/dev/null | grep -E "^(Name|State|VmRSS|Threads)"; '
                    'echo "=== CPU ==="; '
                    'top -bn1 | head -5; '
                    'echo "=== Memory ==="; '
                    'free -h 2>/dev/null || cat /proc/meminfo | head -5',
                    timeout=10
                )
                return {"status": out[:3000] if rc == 0 else err}
        except Exception as e:
            return {"error": str(e)}

    def _get_pod_metrics(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """获取Pod指标"""
        connection_id = params.get('connection_id')
        if not connection_id:
            raise ValueError("connection_id is required")

        conn = self._get_connection(connection_id)
        if not conn:
            return {"error": f"连接 {connection_id} 不可用"}

        try:
            rc, out, err = conn.agent_mgr._exec(
                'echo "=== CPU ==="; top -bn1 | head -5; '
                'echo "=== Memory ==="; free -b 2>/dev/null; '
                'echo "=== Disk ==="; df -h / 2>/dev/null | tail -1',
                timeout=10
            )
            return {"metrics": out[:3000] if rc == 0 else err}
        except Exception as e:
            return {"error": str(e)}

    def _list_capabilities(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """列出可用能力"""
        category = params.get('category')

        query = "SELECT id, name, category, level, description, risk_level FROM diagnosis_capabilities WHERE 1=1"
        query_params = []

        if category:
            query += " AND category = ?"
            query_params.append(category)

        query += " ORDER BY category, level, name"

        capabilities = self.db.fetch_all(query, tuple(query_params))
        return {"capabilities": capabilities}

    def _search_capabilities(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """搜索诊断能力"""
        keyword = params.get('keyword', '')

        query = """
            SELECT id, name, category, level, description, risk_level
            FROM diagnosis_capabilities
            WHERE name LIKE ? OR description LIKE ?
            ORDER BY category, level, name
            LIMIT 20
        """
        keyword_pattern = f"%{keyword}%"
        capabilities = self.db.fetch_all(query, (keyword_pattern, keyword_pattern))
        return {"capabilities": capabilities}

    def _get_connection_info(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """获取连接信息"""
        connection_id = params.get('connection_id')
        if not connection_id:
            raise ValueError("connection_id is required")

        connection = self.db.fetch_one(
            "SELECT * FROM connections WHERE id = ?",
            (connection_id,)
        )

        if not connection:
            return {"error": f"Connection {connection_id} not found"}

        return {
            "connection_id": connection["id"],
            "cluster_name": connection["cluster_name"],
            "namespace": connection["namespace"],
            "pod_name": connection["pod_name"],
            "status": connection.get("status", "unknown"),
            "local_port": connection.get("local_port"),
            "java_pid": connection.get("java_pid")
        }

    def _get_execution_status(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """获取执行状态"""
        run_id = params.get('run_id')
        if not run_id:
            raise ValueError("run_id is required")

        run = self.db.fetch_one(
            "SELECT * FROM task_logs WHERE id = ?",
            (run_id,)
        )

        if not run:
            return {"error": f"Execution {run_id} not found"}

        # 获取步骤日志
        steps = self.db.fetch_all(
            "SELECT * FROM step_logs WHERE run_id = ? ORDER BY step_number",
            (run_id,)
        )

        return {
            "run_id": run["id"],
            "status": run["status"],
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "error_message": run.get("error_message"),
            "steps": [
                {
                    "step_number": s["step_number"],
                    "step_name": s.get("step_name"),
                    "status": s["status"],
                    "output": s.get("output")
                }
                for s in steps
            ]
        }

    def _execute_arthas_command(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """执行 Arthas 命令"""
        command = params.get('command')
        connection_id = params.get('connection_id')

        if not command:
            raise ValueError("command is required")
        if not connection_id:
            raise ValueError("connection_id is required")

        # 命令安全校验
        forbidden = ["redefine", "retransform", "ognl", "reset", "shutdown"]
        cmd_name = command.split()[0].lower()
        if cmd_name in forbidden:
            return {"error": f"Forbidden command: {cmd_name}"}

        conn = self._get_connection(connection_id)
        if not conn:
            return {"error": f"连接 {connection_id} 不可用"}

        try:
            from backend.core.arthas_executor import ArthasCommandExecutor
            result = ArthasCommandExecutor.execute(conn, command, timeout_ms=60000)

            state = result.get('state', '')
            body = result.get('body', [])

            if isinstance(body, list):
                output = '\n'.join(str(line) for line in body)
            else:
                output = str(body)

            # 截断过长输出
            if len(output) > 8000:
                output = output[:8000] + f'\n... (输出已截断，共 {len(output)} 字符)'

            return {"state": state, "output": output, "command": command}
        except Exception as e:
            return {"error": str(e)}

    def _get_jvm_status(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """获取 JVM 状态（通过 Arthas dashboard 命令）"""
        connection_id = params.get('connection_id')
        if not connection_id:
            raise ValueError("connection_id is required")

        conn = self._get_connection(connection_id)
        if not conn:
            return {"error": f"连接 {connection_id} 不可用"}

        try:
            from backend.core.arthas_executor import ArthasCommandExecutor
            resp = ArthasCommandExecutor.execute(conn, "dashboard -n 1", timeout_ms=15000)
            body = resp.get('body', resp)
            results = body.get('results', []) if isinstance(body, dict) else []

            if not results:
                return {"error": "无法获取 JVM 状态", "raw": str(body)[:2000]}

            data = results[0] if isinstance(results, list) and results else {}
            return {
                "connection_id": connection_id,
                "threads": data.get('threads', []),
                "memory": data.get('memoryInfo', []),
                "gc": data.get('gcInfos', []),
                "runtime": data.get('runtimeInfo', {}),
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_thread_status(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """获取线程状态（通过 Arthas thread 命令）"""
        connection_id = params.get('connection_id')
        top_n = params.get('top_n', 10)

        if not connection_id:
            raise ValueError("connection_id is required")

        conn = self._get_connection(connection_id)
        if not conn:
            return {"error": f"连接 {connection_id} 不可用"}

        try:
            from backend.core.arthas_executor import ArthasCommandExecutor
            resp = ArthasCommandExecutor.execute(conn, f"thread -n {top_n}", timeout_ms=20000)
            body = resp.get('body', resp)
            results = body.get('results', []) if isinstance(body, dict) else []

            if not results:
                return {"error": "无法获取线程状态", "raw": str(body)[:2000]}

            data = results[0] if isinstance(results, list) and results else {}
            busy_threads = data.get('busyThreads', [])

            return {
                "connection_id": connection_id,
                "thread_count": len(busy_threads),
                "threads": busy_threads,
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Profiler 工具处理（Phase 7 新增）─────────────────────────

    def _start_profiler(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """启动性能采样"""
        connection_id = params.get('connection_id')
        task_type = params.get('type', 'cpu')
        duration = params.get('duration', 60)

        if not connection_id:
            raise ValueError("connection_id is required")

        if task_type not in ('cpu', 'jfr', 'threaddump', 'heapdump'):
            raise ValueError(f"无效的采样类型: {task_type}")

        log.info(f"Starting profiler: connection_id={connection_id}, type={task_type}, duration={duration}")

        try:
            from services.profiler_service import get_profiler_service
            service = get_profiler_service()
            user_id = context.get('user_id')

            # 根据类型设置 event 和 format
            event_map = {
                'cpu': 'cpu',
                'jfr': 'jfr',
                'threaddump': 'threaddump',
                'heapdump': 'heapdump'
            }
            event = event_map.get(task_type, 'cpu')
            fmt_map = {
                'cpu': 'html',
                'jfr': 'jfr',
                'threaddump': 'txt',
                'heapdump': 'bin'
            }
            fmt = fmt_map.get(task_type, 'html')

            task_id = service.create_task(
                connection_id=connection_id,
                task_type=task_type,
                event=event,
                duration=duration,
                fmt=fmt,
                user_id=user_id
            )

            # 启动任务
            result = service.start_task(task_id)

            return {
                "task_id": task_id,
                "status": "running",
                "message": f"性能采样已启动（类型: {task_type}，时长: {duration}秒）"
            }
        except Exception as e:
            log.error(f"启动性能采样失败: {e}", exc_info=True)
            return {"error": str(e)}

    def _stop_profiler(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """停止性能采样"""
        task_id = params.get('task_id')

        if not task_id:
            raise ValueError("task_id is required")

        log.info(f"Stopping profiler: task_id={task_id}")

        try:
            from services.profiler_service import get_profiler_service
            service = get_profiler_service()
            result = service.stop_task(task_id)

            if result.get('success'):
                return {
                    "task_id": task_id,
                    "status": "stopped",
                    "message": "性能采样已停止"
                }
            else:
                return {"error": result.get('message', '停止失败')}
        except Exception as e:
            log.error(f"停止性能采样失败: {e}", exc_info=True)
            return {"error": str(e)}

    def _get_profiler_status(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """查询性能采样任务状态"""
        task_id = params.get('task_id')

        if not task_id:
            raise ValueError("task_id is required")

        log.info(f"Getting profiler status: task_id={task_id}")

        try:
            from services.profiler_service import get_profiler_service
            service = get_profiler_service()
            result = service.get_task_status(task_id)

            if result.get('success'):
                task = result.get('task', {})
                return {
                    "task_id": task_id,
                    "status": task.get('status', 'unknown'),
                    "progress": task.get('progress', 0),
                    "message": task.get('message', ''),
                    "output_path": task.get('output_path', ''),
                    "created_at": task.get('created_at', ''),
                    "updated_at": task.get('updated_at', '')
                }
            else:
                return {"error": result.get('message', '查询失败')}
        except Exception as e:
            log.error(f"查询性能采样状态失败: {e}", exc_info=True)
            return {"error": str(e)}


# 全局实例
_agent_tool_gateway: Optional[AgentToolGateway] = None


def get_agent_tool_gateway() -> AgentToolGateway:
    """获取 AgentToolGateway 单例"""
    global _agent_tool_gateway
    if _agent_tool_gateway is None:
        _agent_tool_gateway = AgentToolGateway()
    return _agent_tool_gateway
