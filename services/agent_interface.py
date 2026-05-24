#!/usr/bin/env python3
"""Agent 抽象接口 - 定义 Agent 的统一交互协议

本模块定义了 Agent 的抽象接口，所有 Agent 适配器（CodeBuddy、Fallback 等）
必须实现此接口。接口设计遵循策略模式，支持多 Agent 切换和自动降级。

Author: Kou (software-engineer)
Created: 2025-05-25
"""

import uuid
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime
from enum import Enum

log = logging.getLogger(__name__)


class AgentStatus(Enum):
    """Agent 状态枚举"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING_TOOL = "executing_tool"
    WAITING_CONFIRM = "waiting_confirm"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class AgentCapability(Enum):
    """Agent 能力枚举"""
    TEXT_GENERATION = "text_generation"
    TOOL_CALLING = "tool_calling"
    CODE_GENERATION = "code_generation"
    ANALYSIS = "analysis"
    MULTI_TURN = "multi_turn"


@dataclass
class AgentMessage:
    """Agent 消息数据结构"""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {"role": self.role, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.metadata:
            result["metadata"] = self.metadata
        result["timestamp"] = self.timestamp
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """从字典创建消息"""
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
            metadata=data.get("metadata"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class AgentResponse:
    """Agent 响应数据结构"""
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    finish_reason: str = "stop"  # "stop", "tool_calls", "length", "error"
    usage: Optional[Dict[str, int]] = None  # token 使用统计
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "content": self.content,
            "finish_reason": self.finish_reason
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.usage:
            result["usage"] = self.usage
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class AgentConfig:
    """Agent 配置数据结构"""
    model: str = "default"
    api_key: str = ""
    base_url: str = ""
    max_turns: int = 50
    temperature: float = 0.7
    timeout_seconds: int = 300
    max_tokens: int = 4096
    provider: str = "openai"
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "model": self.model,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "max_turns": self.max_turns,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "max_tokens": self.max_tokens,
            "provider": self.provider
        }
        if self.extra:
            result["extra"] = self.extra
        return result


class AgentInterface(ABC):
    """Agent 抽象接口

    所有 Agent 适配器必须实现此接口。接口定义了 Agent 的核心能力：
    - 会话管理（创建、恢复、关闭）
    - 消息发送（单轮、多轮）
    - 工具调用处理
    - 状态查询

    使用示例：
        agent = CodeBuddyAgent(config)
        await agent.initialize()
        response = await agent.send_message("分析这个 Pod 的状态", context)
        await agent.close()
    """

    def __init__(self, config: AgentConfig):
        """初始化 Agent

        Args:
            config: Agent 配置
        """
        self._config = config
        self._session_id: Optional[str] = None
        self._status: AgentStatus = AgentStatus.IDLE
        self._created_at: str = datetime.now().isoformat()
        self._message_history: List[AgentMessage] = []
        self._turn_count: int = 0

    @property
    def session_id(self) -> Optional[str]:
        """获取会话 ID"""
        return self._session_id

    @property
    def status(self) -> AgentStatus:
        """获取 Agent 状态"""
        return self._status

    @property
    def turn_count(self) -> int:
        """获取当前轮次"""
        return self._turn_count

    @property
    def config(self) -> AgentConfig:
        """获取配置"""
        return self._config

    def get_capabilities(self) -> List[AgentCapability]:
        """获取 Agent 支持的能力列表

        Returns:
            能力列表
        """
        return [
            AgentCapability.TEXT_GENERATION,
            AgentCapability.TOOL_CALLING,
            AgentCapability.ANALYSIS
        ]

    def get_message_history(self) -> List[AgentMessage]:
        """获取消息历史

        Returns:
            消息历史列表
        """
        return self._message_history.copy()

    @abstractmethod
    async def initialize(self) -> bool:
        """初始化 Agent 连接

        Returns:
            是否初始化成功
        """
        pass

    @abstractmethod
    async def send_message(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AgentResponse:
        """发送消息给 Agent

        Args:
            message: 用户消息
            context: 上下文信息（连接 ID、用户 ID 等）
            tools: 可用工具定义列表

        Returns:
            Agent 响应
        """
        pass

    @abstractmethod
    async def send_message_stream(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[str, None]:
        """流式发送消息给 Agent

        Args:
            message: 用户消息
            context: 上下文信息
            tools: 可用工具定义列表

        Yields:
            响应片段
        """
        pass

    @abstractmethod
    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行工具调用

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            context: 上下文信息

        Returns:
            工具执行结果
        """
        pass

    @abstractmethod
    async def close(self) -> bool:
        """关闭 Agent 连接

        Returns:
            是否关闭成功
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """健康检查

        Returns:
            健康状态信息
        """
        pass

    def reset(self):
        """重置 Agent 状态"""
        self._message_history.clear()
        self._turn_count = 0
        self._status = AgentStatus.IDLE
        log.info(f"Agent session {self._session_id} reset")

    def _generate_session_id(self) -> str:
        """生成会话 ID

        Returns:
            唯一会话 ID
        """
        return f"agent-{uuid.uuid4().hex[:12]}"

    def _add_message(self, message: AgentMessage):
        """添加消息到历史

        Args:
            message: 消息对象
        """
        self._message_history.append(message)
        if message.role == "user":
            self._turn_count += 1

    def _update_status(self, status: AgentStatus):
        """更新 Agent 状态

        Args:
            status: 新状态
        """
        old_status = self._status
        self._status = status
        if old_status != status:
            log.debug(f"Agent status changed: {old_status.value} -> {status.value}")


class AgentError(Exception):
    """Agent 错误基类"""

    def __init__(self, message: str, error_code: str = "AGENT_ERROR"):
        """初始化

        Args:
            message: 错误消息
            error_code: 错误代码
        """
        super().__init__(message)
        self.error_code = error_code


class AgentConnectionError(AgentError):
    """Agent 连接错误"""

    def __init__(self, message: str = "Failed to connect to Agent"):
        super().__init__(message, "AGENT_CONNECTION_ERROR")


class AgentTimeoutError(AgentError):
    """Agent 超时错误"""

    def __init__(self, message: str = "Agent request timed out"):
        super().__init__(message, "AGENT_TIMEOUT_ERROR")


class AgentToolExecutionError(AgentError):
    """Agent 工具执行错误"""

    def __init__(self, message: str, tool_name: str = ""):
        super().__init__(message, "AGENT_TOOL_EXECUTION_ERROR")
        self.tool_name = tool_name


class AgentRateLimitError(AgentError):
    """Agent 限流错误"""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        super().__init__(message, "AGENT_RATE_LIMIT_ERROR")
        self.retry_after = retry_after
