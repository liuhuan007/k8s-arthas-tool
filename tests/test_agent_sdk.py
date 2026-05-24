#!/usr/bin/env python3
"""Agent SDK 集成单元测试

测试内容：
- AgentInterface 抽象接口
- CodeBuddyAgent 适配器
- FallbackAgent 适配器
- AgentFactory 工厂
- SessionManager 会话管理
- ResourceManager 资源管理

Author: Kou (software-engineer)
Created: 2025-05-25
"""

import pytest
import asyncio
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.agent_interface import (
    AgentInterface,
    AgentConfig,
    AgentResponse,
    AgentMessage,
    AgentStatus,
    AgentCapability,
    AgentError,
    AgentConnectionError,
    AgentTimeoutError,
    AgentToolExecutionError
)
from services.agents.codebuddy_agent import CodeBuddyAgent
from services.agents.fallback_agent import FallbackAgent
from services.agent_factory import AgentFactory, get_agent_factory
from services.session_manager import SessionManager, get_session_manager
from services.resource_manager import ResourceManager, ResourceQuota, get_resource_manager


# ============================================================================
# AgentInterface 测试
# ============================================================================

class TestAgentInterface:
    """AgentInterface 基础测试"""

    def test_agent_config_creation(self):
        """测试 AgentConfig 创建"""
        config = AgentConfig(
            model="test-model",
            api_key="test-key",
            base_url="http://test.com",
            max_turns=100,
            temperature=0.5
        )

        assert config.model == "test-model"
        assert config.api_key == "test-key"
        assert config.max_turns == 100
        assert config.temperature == 0.5

    def test_agent_config_to_dict(self):
        """测试 AgentConfig 序列化"""
        config = AgentConfig(model="test", api_key="key")
        data = config.to_dict()

        assert data["model"] == "test"
        assert data["api_key"] == "key"
        assert "max_turns" in data
        assert "temperature" in data

    def test_agent_message_creation(self):
        """测试 AgentMessage 创建"""
        msg = AgentMessage(role="user", content="hello")

        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.timestamp is not None

    def test_agent_message_to_dict(self):
        """测试 AgentMessage 序列化"""
        msg = AgentMessage(
            role="assistant",
            content="response",
            tool_calls=[{"id": "call-1", "type": "function"}]
        )
        data = msg.to_dict()

        assert data["role"] == "assistant"
        assert data["content"] == "response"
        assert len(data["tool_calls"]) == 1

    def test_agent_message_from_dict(self):
        """测试 AgentMessage 反序列化"""
        data = {
            "role": "user",
            "content": "test",
            "timestamp": "2025-01-01T00:00:00"
        }
        msg = AgentMessage.from_dict(data)

        assert msg.role == "user"
        assert msg.content == "test"

    def test_agent_response_creation(self):
        """测试 AgentResponse 创建"""
        response = AgentResponse(
            content="response",
            tool_calls=[{"id": "call-1"}],
            finish_reason="tool_calls"
        )

        assert response.content == "response"
        assert len(response.tool_calls) == 1
        assert response.finish_reason == "tool_calls"

    def test_agent_response_to_dict(self):
        """测试 AgentResponse 序列化"""
        response = AgentResponse(
            content="test",
            usage={"prompt_tokens": 100, "completion_tokens": 50}
        )
        data = response.to_dict()

        assert data["content"] == "test"
        assert data["finish_reason"] == "stop"
        assert data["usage"]["prompt_tokens"] == 100


# ============================================================================
# CodeBuddyAgent 测试
# ============================================================================

class TestCodeBuddyAgent:
    """CodeBuddyAgent 测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.config = AgentConfig(
            model="deepseek-v3.1",
            api_key="test-key",
            provider="codebuddy"
        )
        self.agent = CodeBuddyAgent(self.config)

    def test_initialize(self):
        """测试初始化"""
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(self.agent.initialize())

        assert result is True
        assert self.agent.session_id is not None
        assert self.agent.session_id.startswith("agent-")
        assert self.agent.status == AgentStatus.IDLE

    def test_send_message(self):
        """测试发送消息"""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.agent.initialize())
        response = loop.run_until_complete(self.agent.send_message("hello"))

        assert isinstance(response, AgentResponse)
        assert response.content is not None
        assert response.finish_reason in ["stop", "tool_calls"]
        assert len(self.agent.get_message_history()) == 2  # user + assistant

    def test_send_message_stream(self):
        """测试流式发送消息"""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.agent.initialize())
        chunks = []

        async def collect_chunks():
            async for chunk in self.agent.send_message_stream("hello"):
                chunks.append(chunk)

        loop.run_until_complete(collect_chunks())

        assert len(chunks) > 0
        assert len(self.agent.get_message_history()) == 2

    def test_tool_call(self):
        """测试工具调用"""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.agent.initialize())
        response = loop.run_until_complete(self.agent.send_message(
            "execute capability 1",
            tools=[{"name": "execute_capability", "parameters": {}}]
        ))

        # 检查是否有工具调用
        if response.tool_calls:
            assert response.finish_reason == "tool_calls"
            assert self.agent.status == AgentStatus.EXECUTING_TOOL

    def test_close(self):
        """测试关闭"""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.agent.initialize())
        result = loop.run_until_complete(self.agent.close())

        assert result is True
        assert self.agent.status == AgentStatus.DISCONNECTED

    def test_health_check(self):
        """测试健康检查"""
        health = self.agent.health_check()

        assert health["provider"] == "codebuddy"
        assert health["status"] == "idle"
        assert "session_id" in health

    def test_capabilities(self):
        """测试能力列表"""
        capabilities = self.agent.get_capabilities()

        assert AgentCapability.TEXT_GENERATION in capabilities
        assert AgentCapability.TOOL_CALLING in capabilities
        assert AgentCapability.MULTI_TURN in capabilities


# ============================================================================
# FallbackAgent 测试
# ============================================================================

class TestFallbackAgent:
    """FallbackAgent 测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.config = AgentConfig(
            model="deepseek-v3.1",
            api_key="test-key",
            base_url="https://api.deepseek.com/v1",
            provider="openai"
        )
        self.agent = FallbackAgent(self.config)

    def test_initialize(self):
        """测试初始化"""
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(self.agent.initialize())

        assert result is True
        assert self.agent.session_id is not None
        assert self.agent.status == AgentStatus.IDLE

    def test_send_message(self):
        """测试发送消息"""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.agent.initialize())
        response = loop.run_until_complete(self.agent.send_message("hello"))

        assert isinstance(response, AgentResponse)
        assert response.content is not None
        assert len(self.agent.get_message_history()) == 2

    def test_send_message_stream(self):
        """测试流式发送消息"""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.agent.initialize())
        chunks = []

        async def collect_chunks():
            async for chunk in self.agent.send_message_stream("hello"):
                chunks.append(chunk)

        loop.run_until_complete(collect_chunks())

        assert len(chunks) > 0

    def test_close(self):
        """测试关闭"""
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.agent.initialize())
        result = loop.run_until_complete(self.agent.close())

        assert result is True
        assert self.agent.status == AgentStatus.DISCONNECTED

    def test_health_check(self):
        """测试健康检查"""
        health = self.agent.health_check()

        assert health["provider"] == "openai-compatible"
        assert "api_base" in health

    def test_capabilities(self):
        """测试能力列表"""
        capabilities = self.agent.get_capabilities()

        assert AgentCapability.TEXT_GENERATION in capabilities
        assert AgentCapability.TOOL_CALLING in capabilities


# ============================================================================
# AgentFactory 测试
# ============================================================================

class TestAgentFactory:
    """AgentFactory 测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.factory = AgentFactory()

    def test_create_agent_with_mock_db(self):
        """测试创建 Agent（使用模拟数据库）"""
        # 使用 mock 避免实际数据库调用
        from unittest.mock import patch, MagicMock

        mock_config = {
            "model": "test-model",
            "api_key": "test-key",
            "base_url": "http://test.com",
            "provider": "codebuddy"
        }

        with patch('services.agent_sdk_config.AgentSDKConfig.get_config', return_value=mock_config):
            loop = asyncio.new_event_loop()
            agent = loop.run_until_complete(self.factory.create_agent(user_id=1))

            assert agent is not None
            assert agent.session_id is not None

            # 清理
            loop.run_until_complete(self.factory.close_all())

    def test_get_agent(self):
        """测试获取 Agent"""
        from unittest.mock import patch

        mock_config = {
            "model": "test",
            "api_key": "key",
            "provider": "fallback"
        }

        with patch('services.agent_sdk_config.AgentSDKConfig.get_config', return_value=mock_config):
            loop = asyncio.new_event_loop()
            agent = loop.run_until_complete(self.factory.create_agent(user_id=1))
            cache_key = f"user-1"

            retrieved = loop.run_until_complete(self.factory.get_agent(cache_key))
            assert retrieved is not None
            assert retrieved.session_id == agent.session_id

            loop.run_until_complete(self.factory.close_all())

    def test_release_agent(self):
        """测试释放 Agent"""
        from unittest.mock import patch

        mock_config = {
            "model": "test",
            "api_key": "key",
            "provider": "fallback"
        }

        with patch('services.agent_sdk_config.AgentSDKConfig.get_config', return_value=mock_config):
            loop = asyncio.new_event_loop()
            agent = loop.run_until_complete(self.factory.create_agent(user_id=1))
            cache_key = f"user-1"

            result = loop.run_until_complete(self.factory.release_agent(cache_key))
            assert result is True

            retrieved = loop.run_until_complete(self.factory.get_agent(cache_key))
            assert retrieved is None

    def test_list_agents(self):
        """测试列出 Agent"""
        from unittest.mock import patch

        mock_config = {
            "model": "test",
            "api_key": "key",
            "provider": "fallback"
        }

        with patch('services.agent_sdk_config.AgentSDKConfig.get_config', return_value=mock_config):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.factory.create_agent(user_id=1))
            loop.run_until_complete(self.factory.create_agent(user_id=2))

            agents = self.factory.list_agents()
            assert len(agents) == 2

            loop.run_until_complete(self.factory.close_all())

    def test_factory_stats(self):
        """测试工厂统计"""
        stats = self.factory.get_factory_stats()

        assert "total_agents" in stats
        assert "available_types" in stats


# ============================================================================
# SessionManager 测试
# ============================================================================

class TestSessionManager:
    """SessionManager 测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.manager = SessionManager()
        # 清理共享状态
        SessionManager._sessions.clear()

    def test_create_session(self):
        """测试创建会话"""
        session_id = self.manager.create_session(
            user_id=1,
            agent_type="codebuddy"
        )

        assert session_id is not None
        assert session_id.startswith("sess-")

    def test_get_session(self):
        """测试获取会话"""
        session_id = self.manager.create_session(user_id=1)
        session = self.manager.get_session(session_id)

        assert session is not None
        assert session["user_id"] == 1
        assert session["status"] == "active"

    def test_save_message(self):
        """测试保存消息"""
        session_id = self.manager.create_session(user_id=1)
        result = self.manager.save_message(session_id, {
            "role": "user",
            "content": "hello"
        })

        assert result is True

        messages = self.manager.get_messages(session_id)
        assert len(messages) == 1
        assert messages[0]["content"] == "hello"

    def test_update_session(self):
        """测试更新会话"""
        session_id = self.manager.create_session(user_id=1)
        result = self.manager.update_session(session_id, {
            "status": "expired"
        })

        assert result is True

        session = self.manager.get_session(session_id)
        assert session["status"] == "expired"

    def test_delete_session(self):
        """测试删除会话"""
        session_id = self.manager.create_session(user_id=1)
        result = self.manager.delete_session(session_id)

        assert result is True

        session = self.manager.get_session(session_id)
        assert session is None

    def test_list_user_sessions(self):
        """测试列出用户会话"""
        self.manager.create_session(user_id=1)
        self.manager.create_session(user_id=1)
        self.manager.create_session(user_id=2)

        sessions = self.manager.list_user_sessions(user_id=1)
        assert len(sessions) == 2

    def test_cleanup_expired_sessions(self):
        """测试清理过期会话"""
        session_id = self.manager.create_session(user_id=1)
        # 手动设置过期时间到过去
        SessionManager._sessions[session_id]["expires_at"] = "2020-01-01T00:00:00"

        cleaned = self.manager.cleanup_expired_sessions()
        assert cleaned >= 1

    def test_session_stats(self):
        """测试会话统计"""
        self.manager.create_session(user_id=1)
        self.manager.create_session(user_id=1)

        stats = self.manager.get_session_stats(user_id=1)
        assert stats["total_sessions"] == 2


# ============================================================================
# ResourceManager 测试
# ============================================================================

class TestResourceManager:
    """ResourceManager 测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.manager = ResourceManager()

    def test_acquire_release_session(self):
        """测试获取和释放会话"""
        session_id = "test-session-1"

        # 获取会话
        result = self.manager.acquire_session(session_id)
        assert result is True

        # 释放会话
        self.manager.release_session(session_id)

    def test_concurrent_limit(self):
        """测试并发限制"""
        quota = ResourceQuota(max_concurrent=3)
        self.manager.set_quota(quota)

        # 获取3个会话
        assert self.manager.acquire_session("s1") is True
        assert self.manager.acquire_session("s2") is True
        assert self.manager.acquire_session("s3") is True

        # 第4个应该失败
        assert self.manager.acquire_session("s4") is False

        # 释放后可以再获取
        self.manager.release_session("s1")
        assert self.manager.acquire_session("s4") is True

        # 清理
        self.manager.release_session("s2")
        self.manager.release_session("s3")
        self.manager.release_session("s4")

    def test_rate_limit(self):
        """测试速率限制"""
        quota = ResourceQuota(max_requests_per_minute=5)
        self.manager.set_quota(quota)

        # 允许5个请求
        for i in range(5):
            assert self.manager.check_rate_limit(user_id=1) is True
            self.manager.record_request(user_id=1)

        # 第6个应该被限制
        assert self.manager.check_rate_limit(user_id=1) is False

    def test_token_limit(self):
        """测试 Token 限制"""
        quota = ResourceQuota(max_tokens_per_day=1000)
        self.manager.set_quota(quota)

        # 记录一些 Token
        self.manager.record_request(user_id=1, tokens=500)

        # 检查限制
        assert self.manager.check_token_limit(user_id=1, tokens_requested=400) is True
        assert self.manager.check_token_limit(user_id=1, tokens_requested=600) is False

    def test_turn_limit(self):
        """测试轮次限制"""
        quota = ResourceQuota(max_turns_per_session=10)
        self.manager.set_quota(quota)

        session_id = "test-session"
        self.manager.acquire_session(session_id)

        # 记录轮次
        for i in range(10):
            assert self.manager.check_turn_limit(session_id) is True
            self.manager.record_turn(session_id)

        # 第11个应该失败
        assert self.manager.check_turn_limit(session_id) is False

        self.manager.release_session(session_id)

    def test_usage_stats(self):
        """测试使用统计"""
        self.manager.acquire_session("s1")
        self.manager.record_request(user_id=1, tokens=100)

        stats = self.manager.get_usage_stats(user_id=1)

        assert stats["active_sessions"] >= 0
        assert stats["total_tokens"] >= 100

    def test_reset_stats(self):
        """测试重置统计"""
        self.manager.record_request(user_id=1, tokens=100)
        self.manager.reset_user_stats(user_id=1)

        stats = self.manager.get_usage_stats(user_id=1)
        assert stats["total_tokens"] == 0

    def test_quota_update(self):
        """测试配额更新"""
        new_quota = ResourceQuota(
            max_concurrent=50,
            max_requests_per_minute=100
        )
        self.manager.set_quota(new_quota)

        assert self.manager.quota.max_concurrent == 50
        assert self.manager.quota.max_requests_per_minute == 100


# ============================================================================
# 集成测试
# ============================================================================

class TestAgentSDKIntegration:
    """Agent SDK 集成测试"""

    def test_full_agent_workflow(self):
        """测试完整的 Agent 工作流"""
        # 创建 Agent
        config = AgentConfig(
            model="test",
            api_key="test-key",
            provider="codebuddy"
        )
        agent = CodeBuddyAgent(config)

        loop = asyncio.new_event_loop()

        # 初始化
        loop.run_until_complete(agent.initialize())
        assert agent.session_id is not None

        # 发送消息
        response = loop.run_until_complete(agent.send_message("analyze this pod"))
        assert response.content is not None

        # 获取历史
        history = agent.get_message_history()
        assert len(history) == 2

        # 健康检查
        health = agent.health_check()
        assert health["status"] != "error"

        # 关闭
        loop.run_until_complete(agent.close())
        assert agent.status == AgentStatus.DISCONNECTED

    def test_fallback_workflow(self):
        """测试 Fallback Agent 工作流"""
        config = AgentConfig(
            model="deepseek-v3.1",
            api_key="test-key",
            base_url="https://api.deepseek.com/v1"
        )
        agent = FallbackAgent(config)

        loop = asyncio.new_event_loop()

        loop.run_until_complete(agent.initialize())

        response = loop.run_until_complete(agent.send_message("hello"))
        assert response.content is not None

        loop.run_until_complete(agent.close())
        assert agent.status == AgentStatus.DISCONNECTED


# ============================================================================
# 异常测试
# ============================================================================

class TestAgentErrors:
    """Agent 异常测试"""

    def test_agent_error(self):
        """测试 AgentError"""
        error = AgentError("test error", "TEST_CODE")
        assert str(error) == "test error"
        assert error.error_code == "TEST_CODE"

    def test_connection_error(self):
        """测试 AgentConnectionError"""
        error = AgentConnectionError("connection failed")
        assert error.error_code == "AGENT_CONNECTION_ERROR"

    def test_timeout_error(self):
        """测试 AgentTimeoutError"""
        error = AgentTimeoutError()
        assert error.error_code == "AGENT_TIMEOUT_ERROR"

    def test_tool_execution_error(self):
        """测试 AgentToolExecutionError"""
        error = AgentToolExecutionError("tool failed", "test_tool")
        assert error.tool_name == "test_tool"
        assert error.error_code == "AGENT_TOOL_EXECUTION_ERROR"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
