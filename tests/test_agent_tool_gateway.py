#!/usr/bin/env python3
"""Agent Tool Gateway 单元测试"""
import pytest
import json
import sys
import os
from unittest.mock import MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.agent_tool_gateway import AgentToolGateway


class TestAgentToolGateway:
    """AgentToolGateway 单元测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.gateway = AgentToolGateway()
        self.gateway.db = MagicMock()
        self.gateway._log_audit = MagicMock()
        self.gateway._log_security_event = MagicMock()

    def test_register_tool(self):
        """测试注册工具"""
        def test_handler(params, context):
            return {"result": "ok"}

        self.gateway.register_tool(
            name="test_tool",
            handler=test_handler,
            description="测试工具",
            parameters={"type": "object"},
            risk_level="low"
        )

        assert "test_tool" in self.gateway.tools

    def test_get_tool_definitions(self):
        """测试获取工具定义"""
        tools = self.gateway.get_tool_definitions()

        assert len(tools) > 0
        assert any(t['name'] == 'execute_capability' for t in tools)

    def test_execute_tool_success(self):
        """测试执行工具成功"""
        result = self.gateway.execute_tool(
            tool_name="list_capabilities",
            params={},
            user_id=1
        )

        assert result['success'] is True
        assert 'result' in result

    def test_execute_tool_not_found(self):
        """测试执行不存在的工具"""
        result = self.gateway.execute_tool(
            tool_name="nonexistent_tool",
            params={},
            user_id=1
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    def test_execute_tool_with_context(self):
        """不存在或未授权的连接不能通过工具上下文访问"""
        result = self.gateway.execute_tool(
            tool_name="get_pod_status",
            params={},
            user_id=1,
            context={"connection_id": "test-connection"}
        )

        assert result['success'] is False
        assert result['error'] == "Permission denied"

    def test_execute_tool_requires_authenticated_user(self):
        result = self.gateway.execute_tool(
            tool_name="list_capabilities",
            params={}
        )

        assert result == {
            "success": False,
            "error": "Authenticated user is required",
        }

    def test_high_impact_heapdump_is_admin_only(self):
        self.gateway._is_admin = lambda user_id: False

        result = self.gateway.execute_tool(
            tool_name="start_profiler",
            params={
                "connection_id": "test-connection",
                "type": "heapdump",
            },
            user_id=1
        )

        assert result["success"] is False
        assert result["requires_confirmation"] is True
        assert "per-run confirmation" in result["error"]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
