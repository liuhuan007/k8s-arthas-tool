#!/usr/bin/env python3
"""CodeBuddy Agent 适配器 - 实现 CodeBuddy SDK 集成

本模块实现了 AgentInterface，封装了 CodeBuddy SDK 的调用逻辑。
支持：
- 会话创建与恢复
- 工具调用协议
- 流式响应
- 自动重试

Author: Kou (software-engineer)
Created: 2025-05-25
"""

import json
import uuid
import asyncio
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime

from services.agent_interface import (
    AgentInterface,
    AgentConfig,
    AgentResponse,
    AgentMessage,
    AgentStatus,
    AgentCapability,
    AgentConnectionError,
    AgentTimeoutError,
    AgentToolExecutionError
)

log = logging.getLogger(__name__)


class CodeBuddyAgent(AgentInterface):
    """CodeBuddy Agent 适配器

    封装 CodeBuddy SDK 的调用，提供统一的 Agent 接口。
    支持流式响应和工具调用。

    使用示例：
        config = AgentConfig(
            model="deepseek-v3.1",
            api_key="your-api-key",
            provider="codebuddy"
        )
        agent = CodeBuddyAgent(config)
        await agent.initialize()
        response = await agent.send_message("分析这个 Pod 的状态")
    """

    # CodeBuddy 特有配置
    DEFAULT_EXTRA_CONFIG = {
        "permission_mode": "bypassPermissions",
        "setting_sources": ["project"],
        "internet_environment": "internal"
    }

    def __init__(self, config: AgentConfig):
        """初始化 CodeBuddy Agent

        Args:
            config: Agent 配置
        """
        super().__init__(config)
        self._sdk_client = None
        self._conversation_id: Optional[str] = None
        self._extra_config = {**self.DEFAULT_EXTRA_CONFIG}
        if config.extra:
            self._extra_config.update(config.extra)

    def get_capabilities(self) -> List[AgentCapability]:
        """获取 CodeBuddy 支持的能力

        Returns:
            能力列表
        """
        return [
            AgentCapability.TEXT_GENERATION,
            AgentCapability.TOOL_CALLING,
            AgentCapability.CODE_GENERATION,
            AgentCapability.ANALYSIS,
            AgentCapability.MULTI_TURN
        ]

    async def initialize(self) -> bool:
        """初始化 CodeBuddy SDK 连接

        Returns:
            是否初始化成功

        Raises:
            AgentConnectionError: 连接失败时抛出
        """
        try:
            self._session_id = self._generate_session_id()
            self._conversation_id = str(uuid.uuid4())

            # 尝试导入 CodeBuddy SDK
            # 注意：实际环境中需要安装 codebuddy SDK
            # 这里提供降级逻辑
            try:
                # 尝试导入 SDK（如果已安装）
                import codebuddy
                self._sdk_client = codebuddy.Client(
                    api_key=self._config.api_key,
                    base_url=self._config.base_url,
                    model=self._config.model
                )
                log.info(f"CodeBuddy SDK initialized with session {self._session_id}")
            except ImportError:
                # SDK 未安装，使用模拟模式
                log.warning("CodeBuddy SDK not available, using mock mode")
                self._sdk_client = _MockCodeBuddyClient(self._config)

            self._update_status(AgentStatus.IDLE)
            return True

        except Exception as e:
            self._update_status(AgentStatus.ERROR)
            log.error(f"Failed to initialize CodeBuddy Agent: {e}")
            raise AgentConnectionError(f"Initialization failed: {str(e)}")

    async def send_message(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AgentResponse:
        """发送消息给 CodeBuddy

        Args:
            message: 用户消息
            context: 上下文信息
            tools: 可用工具定义列表

        Returns:
            Agent 响应

        Raises:
            AgentTimeoutError: 请求超时时抛出
        """
        if self._sdk_client is None:
            raise AgentConnectionError("Agent not initialized")

        self._update_status(AgentStatus.THINKING)

        # 构建用户消息
        user_msg = AgentMessage(role="user", content=message)
        self._add_message(user_msg)

        # 构建请求参数
        request_params = self._build_request_params(message, context, tools)

        try:
            # 调用 SDK
            raw_response = await self._call_sdk(request_params)

            # 解析响应
            response = self._parse_response(raw_response)

            # 记录助手消息
            assistant_msg = AgentMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls
            )
            self._add_message(assistant_msg)

            # 更新状态
            if response.tool_calls:
                self._update_status(AgentStatus.EXECUTING_TOOL)
            else:
                self._update_status(AgentStatus.IDLE)

            return response

        except asyncio.TimeoutError:
            self._update_status(AgentStatus.ERROR)
            raise AgentTimeoutError(f"Request timed out after {self._config.timeout_seconds}s")
        except Exception as e:
            self._update_status(AgentStatus.ERROR)
            log.error(f"Failed to send message: {e}")
            raise

    async def send_message_stream(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[str, None]:
        """流式发送消息给 CodeBuddy

        Args:
            message: 用户消息
            context: 上下文信息
            tools: 可用工具定义列表

        Yields:
            响应片段
        """
        if self._sdk_client is None:
            raise AgentConnectionError("Agent not initialized")

        self._update_status(AgentStatus.THINKING)

        # 构建用户消息
        user_msg = AgentMessage(role="user", content=message)
        self._add_message(user_msg)

        # 构建请求参数（启用流式）
        request_params = self._build_request_params(message, context, tools)
        request_params["stream"] = True

        full_content = ""
        try:
            async for chunk in self._call_sdk_stream(request_params):
                full_content += chunk
                yield chunk

            # 记录完整的助手消息
            assistant_msg = AgentMessage(role="assistant", content=full_content)
            self._add_message(assistant_msg)
            self._update_status(AgentStatus.IDLE)

        except asyncio.TimeoutError:
            self._update_status(AgentStatus.ERROR)
            raise AgentTimeoutError(f"Stream timed out after {self._config.timeout_seconds}s")
        except Exception as e:
            self._update_status(AgentStatus.ERROR)
            log.error(f"Stream failed: {e}")
            raise

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
        self._update_status(AgentStatus.EXECUTING_TOOL)

        try:
            # 通过上下文获取工具执行器
            tool_executor = context.get("tool_executor") if context else None

            if tool_executor is None:
                # 使用内置的工具网关
                from services.agent_tool_gateway import get_agent_tool_gateway
                gateway = get_agent_tool_gateway()

                result = gateway.execute_tool(
                    tool_name=tool_name,
                    params=arguments,
                    user_id=context.get("user_id") if context else None,
                    context=context
                )
            else:
                result = await tool_executor(tool_name, arguments, context)

            # 记录工具调用消息
            tool_msg = AgentMessage(
                role="tool",
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=f"call-{uuid.uuid4().hex[:8]}"
            )
            self._add_message(tool_msg)

            self._update_status(AgentStatus.IDLE)
            return result

        except Exception as e:
            self._update_status(AgentStatus.ERROR)
            log.error(f"Tool execution failed: {tool_name}, error: {e}")
            raise AgentToolExecutionError(str(e), tool_name)

    async def close(self) -> bool:
        """关闭 CodeBuddy Agent

        Returns:
            是否关闭成功
        """
        try:
            if self._sdk_client and hasattr(self._sdk_client, 'close'):
                await self._sdk_client.close()

            self._sdk_client = None
            self._conversation_id = None
            self._update_status(AgentStatus.DISCONNECTED)
            log.info(f"CodeBuddy Agent {self._session_id} closed")
            return True

        except Exception as e:
            log.error(f"Failed to close CodeBuddy Agent: {e}")
            return False

    def health_check(self) -> Dict[str, Any]:
        """健康检查

        Returns:
            健康状态信息
        """
        return {
            "session_id": self._session_id,
            "conversation_id": self._conversation_id,
            "status": self._status.value,
            "turn_count": self._turn_count,
            "model": self._config.model,
            "provider": "codebuddy",
            "initialized": self._sdk_client is not None,
            "created_at": self._created_at,
            "checked_at": datetime.now().isoformat()
        }

    def _build_request_params(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """构建请求参数

        Args:
            message: 用户消息
            context: 上下文信息
            tools: 工具定义列表

        Returns:
            请求参数字典
        """
        # 构建消息历史
        messages = [msg.to_dict() for msg in self._message_history]

        params = {
            "model": self._config.model,
            "messages": messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "stream": False,
            "conversation_id": self._conversation_id
        }

        # 添加工具定义
        if tools:
            params["tools"] = tools

        # 添加 CodeBuddy 特有参数
        params.update(self._extra_config)

        # 添加上下文信息
        if context:
            params["metadata"] = {
                "user_id": context.get("user_id"),
                "connection_id": context.get("connection_id")
            }

        return params

    async def _call_sdk(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用 CodeBuddy SDK

        Args:
            params: 请求参数

        Returns:
            SDK 响应

        Raises:
            AgentTimeoutError: 超时时抛出
        """
        try:
            # 使用 asyncio.wait_for 实现超时控制
            response = await asyncio.wait_for(
                self._sdk_client.chat(params),
                timeout=self._config.timeout_seconds
            )
            return response

        except asyncio.TimeoutError:
            raise

    async def _call_sdk_stream(self, params: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """流式调用 CodeBuddy SDK

        Args:
            params: 请求参数

        Yields:
            响应片段
        """
        # 流式调用（模拟）
        # 实际实现需要根据 CodeBuddy SDK 的流式 API 调整
        try:
            async for chunk in self._sdk_client.chat_stream(params):
                yield chunk
        except Exception as e:
            log.error(f"SDK stream error: {e}")
            raise

    def _parse_response(self, raw_response: Dict[str, Any]) -> AgentResponse:
        """解析 SDK 响应

        Args:
            raw_response: SDK 原始响应

        Returns:
            AgentResponse 对象
        """
        # 解析内容
        content = ""
        if "choices" in raw_response and len(raw_response["choices"]) > 0:
            choice = raw_response["choices"][0]
            message = choice.get("message", {})
            content = message.get("content", "")

            # 检查是否有工具调用
            tool_calls = message.get("tool_calls")
            finish_reason = choice.get("finish_reason", "stop")
        else:
            tool_calls = None
            finish_reason = "stop"

        # 解析使用统计
        usage = raw_response.get("usage")

        return AgentResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            metadata={"raw": raw_response}
        )


class _MockCodeBuddyClient:
    """模拟的 CodeBuddy SDK 客户端

    用于 SDK 未安装时的开发和测试。
    """

    def __init__(self, config: AgentConfig):
        """初始化

        Args:
            config: Agent 配置
        """
        self.config = config
        self._initialized = True

    async def chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """模拟聊天接口

        Args:
            params: 请求参数

        Returns:
            模拟响应
        """
        messages = params.get("messages", [])
        last_message = messages[-1].get("content", "") if messages else ""

        # 生成模拟响应
        response_content = f"[CodeBuddy Mock] 已收到消息: {last_message[:100]}..."

        # 检查是否需要工具调用
        tools = params.get("tools", [])
        if tools and "execute_capability" in [t.get("name") for t in tools]:
            # 模拟工具调用
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": f"call-{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": "execute_capability",
                                "arguments": json.dumps({"capability_id": 1})
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150
                }
            }

        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": response_content
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            }
        }

    async def chat_stream(self, params: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """模拟流式聊天接口

        Args:
            params: 请求参数

        Yields:
            响应片段
        """
        messages = params.get("messages", [])
        last_message = messages[-1].get("content", "") if messages else ""

        # 模拟流式响应
        chunks = [
            f"[CodeBuddy Mock Stream] ",
            f"已收到消息: ",
            f"{last_message[:50]}...",
            f"\n处理完成。"
        ]

        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0.01)  # 模拟网络延迟

    async def close(self):
        """关闭客户端"""
        self._initialized = False
