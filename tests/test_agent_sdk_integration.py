#!/usr/bin/env python3
"""Agent SDK 集成测试 - 验证 Agent 抽象接口、适配器、工厂、网关的功能

测试范围:
1. AgentInterface 抽象接口及数据类
2. CodeBuddyAgent 适配器
3. FallbackAgent 适配器
4. AgentFactory 工厂（含自动降级）
5. AgentToolGateway 网关
6. AgentSDKConfig 配置管理
7. 端到端集成流程

Author: Edward (software-qa-engineer)
Created: 2025-05-25
"""

import sys
import os
import json
import uuid
import asyncio
import sqlite3
import tempfile
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

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
    AgentToolExecutionError,
    AgentRateLimitError,
)
from services.agents.codebuddy_agent import CodeBuddyAgent
from services.agents.fallback_agent import FallbackAgent
from services.agent_factory import AgentFactory
from services.agent_tool_gateway import AgentToolGateway
from services.agent_sdk_config import AgentSDKConfig


# ═══════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def agent_config():
    """创建 Agent 配置"""
    return AgentConfig(
        model="test-model",
        api_key="test-api-key",
        base_url="http://localhost:8080/v1",
        max_turns=10,
        temperature=0.5,
        timeout_seconds=30,
        max_tokens=2048,
        provider="codebuddy"
    )


@pytest.fixture
def fallback_config():
    """创建 Fallback Agent 配置"""
    return AgentConfig(
        model="deepseek-v3.1",
        api_key="test-api-key",
        base_url="http://localhost:8080/v1",
        max_turns=10,
        temperature=0.5,
        timeout_seconds=30,
        max_tokens=2048,
        provider="openai"
    )


class MockDB:
    """模拟数据库 - 用于 Agent 测试"""

    def __init__(self, db_path=None):
        if db_path:
            self.db_path = db_path
        else:
            db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
            os.close(db_fd)
            self._init_tables()

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS connections (
            id TEXT PRIMARY KEY, cluster_name TEXT, namespace TEXT, pod_name TEXT,
            level TEXT DEFAULT 'arthas', local_port INTEGER, user_id INTEGER,
            status TEXT DEFAULT 'disconnected', owner_user_id INTEGER
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS diagnosis_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            category TEXT, level INTEGER, description TEXT, risk_level TEXT DEFAULT 'low'
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS task_logs (
            id TEXT PRIMARY KEY, task_id INTEGER, capability_id INTEGER,
            user_id INTEGER, status TEXT NOT NULL DEFAULT 'pending',
            execution_mode TEXT DEFAULT 'manual', started_at TIMESTAMP,
            finished_at TIMESTAMP, error_message TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS step_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT,
            step_number INTEGER, step_name TEXT, step_type TEXT,
            command TEXT, output TEXT, status TEXT DEFAULT 'pending'
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            action TEXT NOT NULL, resource_type TEXT, resource_id TEXT,
            details TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS ai_config (
            user_id INTEGER PRIMARY KEY, api_key TEXT, base_url TEXT,
            model TEXT, provider TEXT DEFAULT 'openai', system_prompt TEXT
        )''')
        # 插入测试数据
        cursor.execute("INSERT INTO connections (id, user_id, cluster_name, namespace, pod_name, status) VALUES (?, ?, ?, ?, ?, ?)",
                       ('test-conn-001', 1, 'test-cluster', 'default', 'test-pod-001', 'connected'))
        cursor.execute("INSERT INTO diagnosis_capabilities (id, name, category, level, description, risk_level) VALUES (?, ?, ?, ?, ?, ?)",
                       (1, 'test-capability', 'test', 1, 'Test capability', 'low'))
        cursor.execute("INSERT INTO ai_config (user_id, api_key, base_url, model, provider) VALUES (?, ?, ?, ?, ?)",
                       (1, 'test-key', 'http://test.com', 'test-model', 'openai'))
        conn.commit()
        conn.close()

    def fetch_one(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, params).fetchone()
        conn.close()
        return dict(row) if row else None

    def fetch_all(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def execute(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(sql, params)
        conn.commit()
        conn.close()
        return cursor

    def insert(self, table, data):
        cols = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        return self.execute(sql, tuple(data.values()))

    def update(self, table, data, where, where_params):
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        return self.execute(sql, tuple(data.values()) + where_params)

    def count(self, table, where="1=1", where_params=()):
        sql = f"SELECT COUNT(*) as cnt FROM {table} WHERE {where}"
        result = self.fetch_one(sql, where_params)
        return result['cnt'] if result else 0

    def close(self):
        try:
            os.unlink(self.db_path)
        except:
            pass


@pytest.fixture
def mock_db():
    """创建模拟数据库实例"""
    db = MockDB()
    yield db
    db.close()


@pytest.fixture
def agent_tool_gateway(mock_db):
    """创建 AgentToolGateway 实例（mock DB + mock audit）"""
    with patch('models.db.get_db', return_value=mock_db):
        gw = AgentToolGateway()
    gw.db = mock_db
    # 在实例级别 mock _log_audit，避免 audit_service 导入失败
    gw._log_audit = MagicMock()
    return gw


@pytest.fixture
def db_config_mock(mock_db):
    """Mock AgentSDKConfig 的数据库"""
    with patch('services.agent_sdk_config.db', mock_db):
        yield mock_db


# ═══════════════════════════════════════════════════════════════════
#  1. AgentInterface 抽象接口及数据类测试
# ═══════════════════════════════════════════════════════════════════

class TestAgentInterfaceDataClasses:
    """测试 AgentInterface 数据类"""

    def test_agent_message_creation(self):
        msg = AgentMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        assert msg.metadata is None
        assert msg.timestamp is not None

    def test_agent_message_to_dict(self):
        msg = AgentMessage(
            role="assistant", content="Response",
            tool_calls=[{"name": "test"}],
            metadata={"key": "value"}
        )
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Response"
        assert d["tool_calls"] == [{"name": "test"}]
        assert d["metadata"] == {"key": "value"}
        assert "timestamp" in d

    def test_agent_message_from_dict(self):
        data = {
            "role": "user", "content": "Test",
            "tool_calls": [{"id": "123"}],
            "tool_call_id": "call-001",
            "metadata": {"test": True},
            "timestamp": "2025-01-01T00:00:00"
        }
        msg = AgentMessage.from_dict(data)
        assert msg.role == "user"
        assert msg.content == "Test"
        assert msg.tool_calls == [{"id": "123"}]
        assert msg.tool_call_id == "call-001"
        assert msg.metadata == {"test": True}

    def test_agent_message_from_dict_defaults(self):
        msg = AgentMessage.from_dict({})
        assert msg.role == "user"
        assert msg.content == ""

    def test_agent_response_creation(self):
        resp = AgentResponse(
            content="Hello", tool_calls=None, finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 20}
        )
        assert resp.content == "Hello"
        assert resp.tool_calls is None
        assert resp.finish_reason == "stop"
        assert resp.usage["prompt_tokens"] == 10

    def test_agent_response_to_dict(self):
        resp = AgentResponse(
            content="Test", tool_calls=[{"name": "tool1"}],
            finish_reason="tool_calls",
            usage={"total": 100},
            metadata={"raw": {}}
        )
        d = resp.to_dict()
        assert d["content"] == "Test"
        assert d["tool_calls"] == [{"name": "tool1"}]
        assert d["finish_reason"] == "tool_calls"
        assert d["usage"]["total"] == 100
        assert d["metadata"]["raw"] == {}

    def test_agent_response_to_dict_minimal(self):
        resp = AgentResponse(content="Only content")
        d = resp.to_dict()
        assert "content" in d
        assert "finish_reason" in d
        assert "tool_calls" not in d
        assert "usage" not in d

    def test_agent_config_creation(self):
        config = AgentConfig(
            model="gpt-4", api_key="key", base_url="http://api.com",
            max_turns=20, temperature=0.3, timeout_seconds=60,
            max_tokens=8192, provider="openai"
        )
        assert config.model == "gpt-4"
        assert config.api_key == "key"
        assert config.max_turns == 20
        assert config.temperature == 0.3

    def test_agent_config_defaults(self):
        config = AgentConfig()
        assert config.model == "default"
        assert config.max_turns == 50
        assert config.temperature == 0.7
        assert config.timeout_seconds == 300

    def test_agent_config_to_dict(self):
        config = AgentConfig(model="test", extra={"custom": "value"})
        d = config.to_dict()
        assert d["model"] == "test"
        assert d["extra"]["custom"] == "value"

    def test_agent_config_to_dict_no_extra(self):
        config = AgentConfig(model="test")
        d = config.to_dict()
        assert "extra" not in d


class TestAgentEnums:
    """测试 Agent 枚举"""

    def test_agent_status_values(self):
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.THINKING.value == "thinking"
        assert AgentStatus.EXECUTING_TOOL.value == "executing_tool"
        assert AgentStatus.WAITING_CONFIRM.value == "waiting_confirm"
        assert AgentStatus.ERROR.value == "error"
        assert AgentStatus.DISCONNECTED.value == "disconnected"

    def test_agent_capability_values(self):
        assert AgentCapability.TEXT_GENERATION.value == "text_generation"
        assert AgentCapability.TOOL_CALLING.value == "tool_calling"
        assert AgentCapability.CODE_GENERATION.value == "code_generation"
        assert AgentCapability.ANALYSIS.value == "analysis"
        assert AgentCapability.MULTI_TURN.value == "multi_turn"


class TestAgentErrors:
    """测试 Agent 错误类"""

    def test_agent_error(self):
        err = AgentError("test error", "TEST_CODE")
        assert str(err) == "test error"
        assert err.error_code == "TEST_CODE"

    def test_agent_connection_error(self):
        err = AgentConnectionError("connection failed")
        assert str(err) == "connection failed"
        assert err.error_code == "AGENT_CONNECTION_ERROR"

    def test_agent_timeout_error(self):
        err = AgentTimeoutError("timeout")
        assert str(err) == "timeout"
        assert err.error_code == "AGENT_TIMEOUT_ERROR"

    def test_agent_tool_execution_error(self):
        err = AgentToolExecutionError("tool failed", "my_tool")
        assert str(err) == "tool failed"
        assert err.error_code == "AGENT_TOOL_EXECUTION_ERROR"
        assert err.tool_name == "my_tool"

    def test_agent_rate_limit_error(self):
        err = AgentRateLimitError("rate limited", retry_after=30)
        assert str(err) == "rate limited"
        assert err.error_code == "AGENT_RATE_LIMIT_ERROR"
        assert err.retry_after == 30

    def test_error_inheritance(self):
        assert issubclass(AgentConnectionError, AgentError)
        assert issubclass(AgentTimeoutError, AgentError)
        assert issubclass(AgentToolExecutionError, AgentError)
        assert issubclass(AgentRateLimitError, AgentError)
        assert issubclass(AgentError, Exception)


# ═══════════════════════════════════════════════════════════════════
#  2. CodeBuddyAgent 适配器测试
# ═══════════════════════════════════════════════════════════════════

class TestCodeBuddyAgent:
    """CodeBuddyAgent 集成测试"""

    @pytest.fixture
    def agent(self, agent_config):
        return CodeBuddyAgent(agent_config)

    def test_init(self, agent, agent_config):
        assert agent._config == agent_config
        assert agent._sdk_client is None
        assert agent._session_id is None
        assert agent._status == AgentStatus.IDLE
        assert agent._turn_count == 0
        assert agent._message_history == []

    def test_get_capabilities(self, agent):
        caps = agent.get_capabilities()
        assert AgentCapability.TEXT_GENERATION in caps
        assert AgentCapability.TOOL_CALLING in caps
        assert AgentCapability.CODE_GENERATION in caps
        assert AgentCapability.ANALYSIS in caps
        assert AgentCapability.MULTI_TURN in caps

    async def test_initialize(self, agent):
        result = await agent.initialize()
        assert result is True
        assert agent._session_id is not None
        assert agent._session_id.startswith("agent-")
        assert agent._sdk_client is not None
        assert agent._status == AgentStatus.IDLE

    async def test_send_message(self, agent):
        await agent.initialize()
        response = await agent.send_message("Hello, world!")
        assert isinstance(response, AgentResponse)
        assert response.content is not None
        assert response.finish_reason in ["stop", "tool_calls"]
        assert agent._turn_count == 1
        assert len(agent._message_history) == 2  # user + assistant

    async def test_send_message_with_context(self, agent):
        await agent.initialize()
        context = {"user_id": 1, "connection_id": "test-conn"}
        response = await agent.send_message("Test message", context=context)
        assert isinstance(response, AgentResponse)

    async def test_send_message_with_tools(self, agent):
        await agent.initialize()
        tools = [
            {"name": "execute_capability", "description": "执行诊断能力",
             "parameters": {"type": "object", "properties": {}}}
        ]
        response = await agent.send_message("使用工具", tools=tools)
        assert isinstance(response, AgentResponse)

    async def test_send_message_stream(self, agent):
        await agent.initialize()
        chunks = []
        async for chunk in agent.send_message_stream("Stream test"):
            chunks.append(chunk)
        assert len(chunks) > 0
        full_response = "".join(chunks)
        assert len(full_response) > 0
        assert agent._turn_count == 1

    async def test_send_message_before_init(self, agent):
        with pytest.raises(AgentConnectionError):
            await agent.send_message("Hello")

    async def test_send_message_stream_before_init(self, agent):
        with pytest.raises(AgentConnectionError):
            async for _ in agent.send_message_stream("Hello"):
                pass

    async def test_close(self, agent):
        await agent.initialize()
        result = await agent.close()
        assert result is True
        assert agent._sdk_client is None
        assert agent._status == AgentStatus.DISCONNECTED

    def test_health_check(self, agent):
        health = agent.health_check()
        assert "session_id" in health
        assert "status" in health
        assert "turn_count" in health
        assert "model" in health
        assert health["provider"] == "codebuddy"
        assert health["initialized"] is False

    async def test_health_check_after_init(self, agent):
        await agent.initialize()
        health = agent.health_check()
        assert health["initialized"] is True
        assert health["session_id"] is not None

    async def test_multi_turn_conversation(self, agent):
        await agent.initialize()
        await agent.send_message("第一轮消息")
        assert agent._turn_count == 1
        assert len(agent._message_history) == 2

        await agent.send_message("第二轮消息")
        assert agent._turn_count == 2
        assert len(agent._message_history) == 4

        await agent.send_message("第三轮消息")
        assert agent._turn_count == 3

    def test_message_history(self, agent):
        history = agent.get_message_history()
        assert isinstance(history, list)
        assert len(history) == 0

    def test_message_history_copy(self, agent):
        asyncio.get_event_loop().run_until_complete(agent.initialize())
        asyncio.get_event_loop().run_until_complete(agent.send_message("Test"))
        history = agent.get_message_history()
        assert len(history) > 0
        history.clear()
        original = agent.get_message_history()
        assert len(original) > 0

    def test_reset(self, agent):
        asyncio.get_event_loop().run_until_complete(agent.initialize())
        asyncio.get_event_loop().run_until_complete(agent.send_message("Test"))
        agent.reset()
        assert agent._turn_count == 0
        assert agent._status == AgentStatus.IDLE
        assert len(agent._message_history) == 0

    async def test_execute_tool_via_gateway(self, agent):
        await agent.initialize()
        result = await agent.execute_tool(
            "get_pod_status",
            {"pod_name": "test-pod", "namespace": "default"},
            context={"user_id": 1}
        )
        assert result is not None
        assert "success" in result

    async def test_status_transitions(self, agent):
        await agent.initialize()
        assert agent.status == AgentStatus.IDLE
        response = await agent.send_message("Test")
        assert agent.status == AgentStatus.IDLE


# ═══════════════════════════════════════════════════════════════════
#  3. FallbackAgent 适配器测试
# ═══════════════════════════════════════════════════════════════════

class TestFallbackAgent:
    """FallbackAgent 集成测试"""

    @pytest.fixture
    def agent(self, fallback_config):
        return FallbackAgent(fallback_config)

    def test_init(self, agent, fallback_config):
        assert agent._config == fallback_config
        assert agent._http_client is None
        assert agent._session_id is None
        assert agent._api_base == "http://localhost:8080/v1"

    def test_get_capabilities(self, agent):
        caps = agent.get_capabilities()
        assert AgentCapability.TEXT_GENERATION in caps
        assert AgentCapability.TOOL_CALLING in caps
        assert AgentCapability.ANALYSIS in caps
        assert AgentCapability.MULTI_TURN in caps

    async def test_initialize(self, agent):
        result = await agent.initialize()
        assert result is True
        assert agent._session_id is not None
        assert agent._http_client is not None
        assert agent._status == AgentStatus.IDLE

    async def test_send_message(self, agent):
        await agent.initialize()
        response = await agent.send_message("Hello from fallback!")
        assert isinstance(response, AgentResponse)
        assert response.content is not None
        assert agent._turn_count == 1

    @pytest.mark.xfail(
        reason="BUG: _MockHTTPClient.post() parameter 'json' shadows json module import, "
               "causing json.dumps() to fail with AttributeError: 'dict' has no attribute 'dumps'",
        strict=True
    )
    async def test_send_message_with_tools(self, agent):
        """测试 FallbackAgent 发送带工具的消息

        此测试标记为 xfail 因为 _MockHTTPClient.post() 方法中参数名 'json'
        遮蔽了模块级导入的 json 模块，导致 json.dumps() 调用失败。

        期望工程师修复: 将 _MockHTTPClient.post() 的参数名从 'json' 改为 'body' 或 'data'
        """
        await agent.initialize()
        tools = [
            {"type": "function", "function": {
                "name": "execute_capability", "description": "执行诊断能力",
                "parameters": {"type": "object", "properties": {}}
            }}
        ]
        response = await agent.send_message("使用工具", tools=tools)
        assert isinstance(response, AgentResponse)

    async def test_send_message_stream(self, agent):
        await agent.initialize()
        chunks = []
        async for chunk in agent.send_message_stream("Stream from fallback"):
            chunks.append(chunk)
        assert len(chunks) > 0
        full_response = "".join(chunks)
        assert len(full_response) > 0

    async def test_send_message_before_init(self, agent):
        with pytest.raises(AgentConnectionError):
            await agent.send_message("Hello")

    async def test_close(self, agent):
        await agent.initialize()
        result = await agent.close()
        assert result is True
        assert agent._http_client is None
        assert agent._status == AgentStatus.DISCONNECTED

    def test_health_check(self, agent):
        health = agent.health_check()
        assert "session_id" in health
        assert "status" in health
        assert health["provider"] == "openai-compatible"
        assert health["api_base"] == "http://localhost:8080/v1"
        assert health["initialized"] is False

    async def test_execute_tool(self, agent):
        await agent.initialize()
        result = await agent.execute_tool(
            "get_pod_status",
            {"pod_name": "test-pod", "namespace": "default"},
            context={"user_id": 1}
        )
        assert result is not None

    async def test_multi_turn_conversation(self, agent):
        await agent.initialize()
        await agent.send_message("Message 1")
        assert agent._turn_count == 1
        await agent.send_message("Message 2")
        assert agent._turn_count == 2
        await agent.send_message("Message 3")
        assert agent._turn_count == 3
        assert len(agent._message_history) == 6  # 3*(user + assistant)

    async def test_reset(self, agent):
        await agent.initialize()
        await agent.send_message("Test")
        agent.reset()
        assert agent._turn_count == 0
        assert len(agent._message_history) == 0


# ═══════════════════════════════════════════════════════════════════
#  4. AgentFactory 工厂测试
# ═══════════════════════════════════════════════════════════════════

class TestAgentFactory:
    """AgentFactory 集成测试"""

    @pytest.fixture
    def factory(self):
        return AgentFactory()

    def test_init(self, factory):
        assert factory._agents == {}
        assert factory._agent_configs == {}
        assert factory._usage_stats == {}
        assert "codebuddy" in factory.AGENT_TYPES
        assert "fallback" in factory.AGENT_TYPES

    async def test_create_agent_codebuddy(self, factory, db_config_mock):
        # provider 为 openai，工厂会根据配置选择 FallbackAgent
        # 但如果配置了 codebuddy provider，则创建 CodeBuddyAgent
        with patch.object(AgentSDKConfig, 'get_config', return_value={
            "provider": "codebuddy", "api_key": "test-key", "model": "test-model"
        }):
            agent = await factory.create_agent(user_id=1)
            assert agent is not None
            assert isinstance(agent, CodeBuddyAgent)
            assert agent._session_id is not None

    async def test_create_agent_explicit_type(self, factory, db_config_mock):
        agent = await factory.create_agent(user_id=1, agent_type="fallback")
        assert isinstance(agent, FallbackAgent)

    async def test_create_agent_caching(self, factory, db_config_mock):
        # provider=openai -> FallbackAgent
        agent1 = await factory.create_agent(user_id=1)
        agent2 = await factory.create_agent(user_id=1)
        assert agent1 is agent2  # 同一个实例

    async def test_get_agent(self, factory, db_config_mock):
        agent = await factory.create_agent(user_id=1)
        # Factory 的 get_agent 使用 cache_key 格式 "user-{user_id}"
        cache_key = "user-1"
        retrieved = await factory.get_agent(cache_key)
        assert retrieved is agent

    async def test_get_agent_not_found(self, factory):
        result = await factory.get_agent("nonexistent-id")
        assert result is None

    async def test_release_agent(self, factory, db_config_mock):
        agent = await factory.create_agent(user_id=1)
        # Factory 使用 cache_key = "user-{user_id}"
        cache_key = "user-1"
        result = await factory.release_agent(cache_key)
        assert result is True
        assert await factory.get_agent(cache_key) is None

    async def test_release_nonexistent_agent(self, factory):
        result = await factory.release_agent("nonexistent-id")
        assert result is False

    async def test_close_all(self, factory, db_config_mock):
        await factory.create_agent(user_id=1)
        await factory.create_agent(user_id=2)
        assert len(factory._agents) == 2
        await factory.close_all()
        assert len(factory._agents) == 0

    def test_get_agent_status_nonexistent(self, factory):
        result = factory.get_agent_status("nonexistent-id")
        assert result is None

    async def test_get_agent_status_active(self, factory, db_config_mock):
        agent = await factory.create_agent(user_id=1)
        # Factory 使用 cache_key = "user-{user_id}"
        cache_key = "user-1"
        status = factory.get_agent_status(cache_key)
        assert status is not None
        assert "session_id" in status
        assert "status" in status
        assert "agent_type" in status

    def test_list_agents_empty(self, factory):
        agents = factory.list_agents()
        assert agents == []

    async def test_list_agents(self, factory, db_config_mock):
        await factory.create_agent(user_id=1)
        agents = factory.list_agents()
        assert len(agents) == 1
        assert "session_id" in agents[0]

    def test_factory_stats(self, factory):
        stats = factory.get_factory_stats()
        assert "total_agents" in stats
        assert "available_types" in stats
        assert stats["total_agents"] == 0

    async def test_fallback_on_init_failure(self, factory, db_config_mock):
        async def mock_init_fail(self_inner):
            return False

        with patch.object(CodeBuddyAgent, 'initialize', mock_init_fail):
            agent = await factory.create_agent(user_id=1)
            assert isinstance(agent, FallbackAgent)

    async def test_agent_type_selection_codebuddy(self, factory, db_config_mock):
        with patch.object(AgentSDKConfig, 'get_config', return_value={
            "provider": "codebuddy", "api_key": "test-key", "model": "test-model"
        }):
            agent = await factory.create_agent(user_id=1)
            assert isinstance(agent, CodeBuddyAgent)

    async def test_agent_type_selection_openai(self, factory, db_config_mock):
        with patch.object(AgentSDKConfig, 'get_config', return_value={
            "provider": "openai", "api_key": "test-key", "model": "test-model"
        }):
            agent = await factory.create_agent(user_id=1)
            assert isinstance(agent, FallbackAgent)


# ═══════════════════════════════════════════════════════════════════
#  5. AgentToolGateway 网关测试
# ═══════════════════════════════════════════════════════════════════

class TestAgentToolGateway:
    """AgentToolGateway 集成测试"""

    def test_init_default_tools(self, agent_tool_gateway):
        assert "execute_capability" in agent_tool_gateway.tools
        assert "get_pod_status" in agent_tool_gateway.tools
        assert "get_pod_metrics" in agent_tool_gateway.tools
        assert "list_capabilities" in agent_tool_gateway.tools

    def test_register_tool(self, agent_tool_gateway):
        def handler(params, context):
            return {"result": "ok"}

        agent_tool_gateway.register_tool(
            name="custom_tool", handler=handler,
            description="自定义工具", parameters={"type": "object", "properties": {}},
            risk_level="low"
        )
        assert "custom_tool" in agent_tool_gateway.tools
        assert agent_tool_gateway.tools["custom_tool"]["description"] == "自定义工具"
        assert agent_tool_gateway.tools["custom_tool"]["risk_level"] == "low"

    def test_get_tool_definitions(self, agent_tool_gateway):
        definitions = agent_tool_gateway.get_tool_definitions()
        assert len(definitions) >= 4
        for d in definitions:
            assert "name" in d
            assert "description" in d
            assert "parameters" in d

    def test_execute_tool_success(self, agent_tool_gateway):
        result = agent_tool_gateway.execute_tool(
            tool_name="get_pod_status",
            params={"pod_name": "test-pod", "namespace": "default"},
            user_id=1
        )
        assert result["success"] is True
        assert "result" in result

    def test_execute_tool_not_found(self, agent_tool_gateway):
        result = agent_tool_gateway.execute_tool(
            tool_name="nonexistent_tool", params={}, user_id=1
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_execute_tool_with_context(self, agent_tool_gateway):
        result = agent_tool_gateway.execute_tool(
            tool_name="get_pod_status",
            params={"pod_name": "test-pod", "namespace": "default"},
            user_id=1,
            context={"connection_id": "test-conn", "user_id": 1}
        )
        assert result["success"] is True

    def test_execute_tool_exception_handling(self, agent_tool_gateway):
        def failing_handler(params, context):
            raise RuntimeError("Tool execution failed")

        agent_tool_gateway.register_tool(
            name="failing_tool", handler=failing_handler,
            description="会失败的工具", parameters={"type": "object"},
            risk_level="low"
        )
        result = agent_tool_gateway.execute_tool(
            tool_name="failing_tool", params={}, user_id=1
        )
        assert result["success"] is False
        assert "Tool execution failed" in result["error"]

    def test_list_capabilities(self, agent_tool_gateway):
        result = agent_tool_gateway.execute_tool(
            tool_name="list_capabilities", params={}, user_id=1
        )
        assert result["success"] is True
        assert "result" in result
        assert "capabilities" in result["result"]

    def test_get_pod_status(self, agent_tool_gateway):
        result = agent_tool_gateway.execute_tool(
            tool_name="get_pod_status",
            params={"pod_name": "my-pod", "namespace": "default"},
            user_id=1
        )
        assert result["success"] is True
        data = result["result"]
        assert data["pod_name"] == "my-pod"
        assert data["namespace"] == "default"

    def test_get_pod_metrics(self, agent_tool_gateway):
        result = agent_tool_gateway.execute_tool(
            tool_name="get_pod_metrics",
            params={"pod_name": "my-pod", "namespace": "default"},
            user_id=1
        )
        assert result["success"] is True
        data = result["result"]
        assert data["pod_name"] == "my-pod"
        assert "cpu_usage" in data
        assert "memory_usage" in data


# ═══════════════════════════════════════════════════════════════════
#  6. AgentSDKConfig 配置管理测试
# ═══════════════════════════════════════════════════════════════════

class TestAgentSDKConfig:
    """AgentSDKConfig 集成测试"""

    def test_default_config(self):
        assert AgentSDKConfig.DEFAULT_CONFIG["permission_mode"] == "bypassPermissions"
        assert AgentSDKConfig.DEFAULT_CONFIG["max_turns"] == 50

    def test_get_config_with_db(self, db_config_mock):
        config = AgentSDKConfig.get_config(user_id=1)
        assert config["model"] == "test-model"
        assert config["api_key"] == "test-key"
        assert config["base_url"] == "http://test.com"
        assert config["provider"] == "openai"

    def test_get_config_without_db(self, db_config_mock):
        config = AgentSDKConfig.get_config(user_id=999)
        assert config["permission_mode"] == "bypassPermissions"
        assert config["max_turns"] == 50

    def test_get_agent_sdk_options_codebuddy(self, db_config_mock):
        db_config_mock.execute(
            "UPDATE ai_config SET provider = 'codebuddy' WHERE user_id = 1"
        )
        options = AgentSDKConfig.get_agent_sdk_options(user_id=1)
        assert "model" in options
        assert "permission_mode" in options
        assert "env" in options
        assert "CODEBUDDY_API_KEY" in options["env"]

    def test_get_agent_sdk_options_openai(self, db_config_mock):
        options = AgentSDKConfig.get_agent_sdk_options(user_id=1)
        assert "model" in options
        assert "api_key" in options
        assert "base_url" in options

    def test_is_agent_sdk_available_with_key(self, db_config_mock):
        result = AgentSDKConfig.is_agent_sdk_available(user_id=1)
        assert result is True

    def test_is_agent_sdk_available_without_key(self, db_config_mock):
        db_config_mock.execute("UPDATE ai_config SET api_key = '' WHERE user_id = 1")
        result = AgentSDKConfig.is_agent_sdk_available(user_id=1)
        assert result is False

    def test_is_agent_sdk_available_unsupported_provider(self, db_config_mock):
        db_config_mock.execute(
            "UPDATE ai_config SET provider = 'unsupported' WHERE user_id = 1"
        )
        result = AgentSDKConfig.is_agent_sdk_available(user_id=1)
        assert result is False


# ═══════════════════════════════════════════════════════════════════
#  7. 端到端集成测试
# ═══════════════════════════════════════════════════════════════════

class TestEndToEndIntegration:
    """端到端集成测试"""

    async def test_full_flow_factory_agent_message(self, db_config_mock):
        factory = AgentFactory()
        try:
            agent = await factory.create_agent(user_id=1)
            assert agent is not None
            assert agent.session_id is not None

            response = await agent.send_message("分析 Pod 状态")
            assert isinstance(response, AgentResponse)
            assert response.content is not None

            history = agent.get_message_history()
            assert len(history) >= 2

            # Factory 使用 cache_key
            cache_key = "user-1"
            status = factory.get_agent_status(cache_key)
            assert status is not None
            assert status["turn_count"] == 1
        finally:
            await factory.close_all()

    async def test_full_flow_with_tool_execution(self, db_config_mock):
        factory = AgentFactory()
        try:
            agent = await factory.create_agent(user_id=1)
            result = await agent.execute_tool(
                "get_pod_status",
                {"pod_name": "test-pod", "namespace": "default"},
                context={"user_id": 1}
            )
            assert result is not None

            history = agent.get_message_history()
            tool_messages = [m for m in history if m.role == "tool"]
            assert len(tool_messages) >= 1
        finally:
            await factory.close_all()

    async def test_fallback_mechanism(self, db_config_mock):
        factory = AgentFactory()
        try:
            async def mock_init_fail(self_inner):
                return False

            with patch.object(CodeBuddyAgent, 'initialize', mock_init_fail):
                agent = await factory.create_agent(user_id=1)
                assert isinstance(agent, FallbackAgent)

                response = await agent.send_message("降级后测试")
                assert isinstance(response, AgentResponse)
                assert response.content is not None
        finally:
            await factory.close_all()

    async def test_streaming_flow(self, db_config_mock):
        factory = AgentFactory()
        try:
            agent = await factory.create_agent(user_id=1, agent_type="fallback")
            chunks = []
            async for chunk in agent.send_message_stream("流式测试"):
                chunks.append(chunk)
            assert len(chunks) > 0
            full_content = "".join(chunks)
            assert len(full_content) > 0
        finally:
            await factory.close_all()

    async def test_concurrent_agents(self, db_config_mock):
        factory = AgentFactory()
        try:
            agents = []
            for i in range(3):
                agent = await factory.create_agent(user_id=i + 1)
                agents.append(agent)
            assert len(agents) == 3
            assert len(factory._agents) == 3

            tasks = [agent.send_message(f"并发消息 {i}") for i, agent in enumerate(agents)]
            responses = await asyncio.gather(*tasks)
            assert len(responses) == 3
            for resp in responses:
                assert isinstance(resp, AgentResponse)
        finally:
            await factory.close_all()

    async def test_agent_lifecycle(self, db_config_mock):
        factory = AgentFactory()
        agent = await factory.create_agent(user_id=1)
        assert agent.status == AgentStatus.IDLE

        await agent.send_message("测试")
        assert agent.turn_count == 1

        # Factory 使用 cache_key = "user-{user_id}"
        cache_key = "user-1"
        status = factory.get_agent_status(cache_key)
        assert status["turn_count"] == 1

        released = await factory.release_agent(cache_key)
        assert released is True
        assert await factory.get_agent(cache_key) is None

    async def test_factory_list_agents(self, db_config_mock):
        factory = AgentFactory()
        try:
            await factory.create_agent(user_id=1)
            await factory.create_agent(user_id=2)
            agents = factory.list_agents()
            assert len(agents) == 2
            for agent_info in agents:
                assert "session_id" in agent_info
                assert "status" in agent_info
                assert "agent_type" in agent_info
        finally:
            await factory.close_all()


# ═══════════════════════════════════════════════════════════════════
#  8. 异常与边界条件测试
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """异常与边界条件测试"""

    def test_agent_message_empty_content(self):
        msg = AgentMessage(role="user", content="")
        assert msg.content == ""
        d = msg.to_dict()
        assert d["content"] == ""

    def test_agent_config_special_characters(self):
        config = AgentConfig(
            model="model/with/slashes",
            api_key="key-with-special-chars!@#$%^&*()",
            base_url="http://localhost:8080/v1?param=value"
        )
        d = config.to_dict()
        assert d["model"] == "model/with/slashes"
        assert "special-chars" in d["api_key"]

    def test_tool_risk_levels(self, agent_tool_gateway):
        def low_handler(p, c):
            return {"level": "low"}

        def medium_handler(p, c):
            return {"level": "medium"}

        def high_handler(p, c):
            return {"level": "high"}

        agent_tool_gateway.register_tool("low_tool", low_handler, "低风险", {}, "low")
        agent_tool_gateway.register_tool("medium_tool", medium_handler, "中风险", {}, "medium")
        agent_tool_gateway.register_tool("high_tool", high_handler, "高风险", {}, "high")

        assert agent_tool_gateway.tools["low_tool"]["risk_level"] == "low"
        assert agent_tool_gateway.tools["medium_tool"]["risk_level"] == "medium"
        assert agent_tool_gateway.tools["high_tool"]["risk_level"] == "high"

    def test_tool_definitions_format(self, agent_tool_gateway):
        defs = agent_tool_gateway.get_tool_definitions()
        for d in defs:
            assert isinstance(d["name"], str)
            assert isinstance(d["description"], str)
            assert isinstance(d["parameters"], dict)

    async def test_agent_send_empty_message(self):
        config = AgentConfig(api_key="test")
        agent = CodeBuddyAgent(config)
        await agent.initialize()
        response = await agent.send_message("")
        assert isinstance(response, AgentResponse)
        assert agent._turn_count == 1

    def test_factory_no_agent_types(self):
        factory = AgentFactory()
        factory.AGENT_TYPES = {}
        with pytest.raises(ValueError, match="No available agent type"):
            asyncio.get_event_loop().run_until_complete(
                factory.create_agent(user_id=1)
            )

    def test_execute_capability_missing_params(self, agent_tool_gateway):
        result = agent_tool_gateway.execute_tool(
            tool_name="execute_capability", params={}, user_id=1
        )
        assert result["success"] is False


# ═══════════════════════════════════════════════════════════════════
#  9. 并发与资源控制测试
# ═══════════════════════════════════════════════════════════════════

class TestConcurrency:
    """并发与资源控制测试"""

    async def test_concurrent_message_sending(self):
        config = AgentConfig(api_key="test")
        agent = CodeBuddyAgent(config)
        await agent.initialize()

        tasks = [agent.send_message(f"Message {i}") for i in range(5)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for resp in responses:
            assert isinstance(resp, AgentResponse)

    def test_concurrent_tool_execution(self, agent_tool_gateway):
        """测试并发工具执行（同步方法）"""
        results = []
        for i in range(5):
            result = agent_tool_gateway.execute_tool(
                tool_name="get_pod_status",
                params={"pod_name": f"pod-{i}", "namespace": "default"},
                user_id=1
            )
            results.append(result)
        for result in results:
            assert result["success"] is True

    async def test_factory_thread_safety(self, db_config_mock):
        factory = AgentFactory()
        try:
            tasks = [factory.create_agent(user_id=i) for i in range(5)]
            agents = await asyncio.gather(*tasks)
            session_ids = [a.session_id for a in agents]
            assert len(set(session_ids)) == 5
        finally:
            await factory.close_all()


# ═══════════════════════════════════════════════════════════════════
#  10. 集成测试 - Agent + Gateway 协作
# ═══════════════════════════════════════════════════════════════════

class TestAgentGatewayCollaboration:
    """Agent 与 Gateway 协作集成测试"""

    async def test_agent_uses_gateway_for_tools(self, db_config_mock):
        factory = AgentFactory()
        try:
            agent = await factory.create_agent(user_id=1)
            result = await agent.execute_tool(
                "get_pod_status",
                {"pod_name": "test-pod", "namespace": "default"},
                context={"user_id": 1}
            )
            assert result is not None
        finally:
            await factory.close_all()

    async def test_tool_call_logged_in_history(self, db_config_mock):
        factory = AgentFactory()
        try:
            agent = await factory.create_agent(user_id=1)
            await agent.execute_tool(
                "get_pod_status",
                {"pod_name": "test-pod", "namespace": "default"},
                context={"user_id": 1}
            )
            history = agent.get_message_history()
            tool_messages = [m for m in history if m.role == "tool"]
            assert len(tool_messages) >= 1
        finally:
            await factory.close_all()

    async def test_multiple_tool_calls(self, db_config_mock):
        factory = AgentFactory()
        try:
            agent = await factory.create_agent(user_id=1)
            await agent.execute_tool(
                "get_pod_status",
                {"pod_name": "pod-1", "namespace": "default"},
                context={"user_id": 1}
            )
            await agent.execute_tool(
                "get_pod_metrics",
                {"pod_name": "pod-1", "namespace": "default"},
                context={"user_id": 1}
            )
            await agent.execute_tool(
                "list_capabilities", {}, context={"user_id": 1}
            )
            history = agent.get_message_history()
            tool_messages = [m for m in history if m.role == "tool"]
            assert len(tool_messages) == 3
        finally:
            await factory.close_all()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
