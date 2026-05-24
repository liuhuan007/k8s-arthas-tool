#!/usr/bin/env python3
"""Agent Tool Gateway 服务 - 受控工具暴露、权限控制、审计"""
import json
import logging
from typing import Optional, Dict, Any, List, Callable

log = logging.getLogger(__name__)


class AgentToolGateway:
    """Agent 工具网关 - 受控工具暴露"""

    def __init__(self):
        from models.db import get_db
        self.db = get_db()
        self.tools: Dict[str, Dict[str, Any]] = {}
        self._register_default_tools()

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
                    "pod_name": {"type": "string", "description": "Pod名称"},
                    "namespace": {"type": "string", "description": "命名空间"}
                },
                "required": ["pod_name", "namespace"]
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
                    "pod_name": {"type": "string", "description": "Pod名称"},
                    "namespace": {"type": "string", "description": "命名空间"}
                },
                "required": ["pod_name", "namespace"]
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
        """检查权限"""
        # TODO: 实现更细粒度的权限控制
        return True

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
        # TODO: 集成实际的 kubectl 执行器
        pod_name = params.get('pod_name')
        namespace = params.get('namespace')

        return {
            "pod_name": pod_name,
            "namespace": namespace,
            "status": "running",
            "message": "[Simulated pod status]"
        }

    def _get_pod_metrics(self, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """获取Pod指标"""
        # TODO: 集成实际的指标采集
        pod_name = params.get('pod_name')
        namespace = params.get('namespace')

        return {
            "pod_name": pod_name,
            "namespace": namespace,
            "cpu_usage": "10%",
            "memory_usage": "256Mi",
            "message": "[Simulated pod metrics]"
        }

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


# 全局实例
_agent_tool_gateway: Optional[AgentToolGateway] = None


def get_agent_tool_gateway() -> AgentToolGateway:
    """获取 AgentToolGateway 单例"""
    global _agent_tool_gateway
    if _agent_tool_gateway is None:
        _agent_tool_gateway = AgentToolGateway()
    return _agent_tool_gateway
