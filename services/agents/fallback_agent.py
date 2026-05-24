#!/usr/bin/env python3
"""Fallback Agent 适配器 - 基于 OpenAI 兼容 API 的降级 Agent

当 CodeBuddy SDK 不可用时，自动降级到此 Agent。
支持任何 OpenAI 兼容的 API（如 DeepSeek、本地 Ollama 等）。

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


class FallbackAgent(AgentInterface):
    """Fallback Agent 适配器

    基于 OpenAI 兼容 API 的降级 Agent。当主 Agent（如 CodeBuddy）不可用时，
    自动切换到此 Agent。

    支持特性：
    - OpenAI 兼容 API 调用
    - 流式响应
    - 工具调用（function calling）
    - 自动重试

    使用示例：
        config = AgentConfig(
            model="deepseek-v3.1",
            api_key="your-api-key",
            base_url="https://api.deepseek.com/v1"
        )
        agent = FallbackAgent(config)
        await agent.initialize()
        response = await agent.send_message("分析这个 Pod 的状态")
    """

    # HTTP 请求头模板
    DEFAULT_HEADERS = {
        "Content-Type": "application/json"
    }

    def __init__(self, config: AgentConfig):
        """初始化 Fallback Agent

        Args:
            config: Agent 配置
        """
        super().__init__(config)
        self._http_client = None
        self._api_base: str = config.base_url or "https://api.openai.com/v1"
        self._headers: Dict[str, str] = {**self.DEFAULT_HEADERS}

        # 设置 API Key
        if config.api_key:
            self._headers["Authorization"] = f"Bearer {config.api_key}"

    def get_capabilities(self) -> List[AgentCapability]:
        """获取 Fallback Agent 支持的能力

        Returns:
            能力列表
        """
        return [
            AgentCapability.TEXT_GENERATION,
            AgentCapability.TOOL_CALLING,
            AgentCapability.ANALYSIS,
            AgentCapability.MULTI_TURN
        ]

    async def initialize(self) -> bool:
        """初始化 HTTP 客户端

        Returns:
            是否初始化成功

        Raises:
            AgentConnectionError: 连接失败时抛出
        """
        try:
            self._session_id = self._generate_session_id()

            # 尝试导入 aiohttp
            try:
                import aiohttp
                self._http_client = aiohttp.ClientSession(
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=self._config.timeout_seconds)
                )
            except ImportError:
                # aiohttp 不可用，使用模拟客户端
                log.warning("aiohttp not available, using mock HTTP client")
                self._http_client = _MockHTTPClient(self._headers, self._config.timeout_seconds)

            # 验证 API 连接
            await self._validate_connection()

            self._update_status(AgentStatus.IDLE)
            log.info(f"Fallback Agent initialized with session {self._session_id}")
            return True

        except Exception as e:
            self._update_status(AgentStatus.ERROR)
            log.error(f"Failed to initialize Fallback Agent: {e}")
            raise AgentConnectionError(f"Initialization failed: {str(e)}")

    async def send_message(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> AgentResponse:
        """发送消息给 Fallback Agent

        Args:
            message: 用户消息
            context: 上下文信息
            tools: 可用工具定义列表

        Returns:
            Agent 响应

        Raises:
            AgentTimeoutError: 请求超时时抛出
        """
        if self._http_client is None:
            raise AgentConnectionError("Agent not initialized")

        self._update_status(AgentStatus.THINKING)

        # 构建用户消息
        user_msg = AgentMessage(role="user", content=message)
        self._add_message(user_msg)

        # 构建请求体
        request_body = self._build_request_body(message, context, tools)

        try:
            # 发送 API 请求
            raw_response = await self._call_api(request_body)

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
        """流式发送消息

        Args:
            message: 用户消息
            context: 上下文信息
            tools: 可用工具定义列表

        Yields:
            响应片段
        """
        if self._http_client is None:
            raise AgentConnectionError("Agent not initialized")

        self._update_status(AgentStatus.THINKING)

        # 构建用户消息
        user_msg = AgentMessage(role="user", content=message)
        self._add_message(user_msg)

        # 构建请求体（启用流式）
        request_body = self._build_request_body(message, context, tools)
        request_body["stream"] = True

        full_content = ""
        try:
            async for chunk in self._call_api_stream(request_body):
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
            # 使用内置的工具网关
            from services.agent_tool_gateway import get_agent_tool_gateway
            gateway = get_agent_tool_gateway()

            result = gateway.execute_tool(
                tool_name=tool_name,
                params=arguments,
                user_id=context.get("user_id") if context else None,
                context=context
            )

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
        """关闭 Fallback Agent

        Returns:
            是否关闭成功
        """
        try:
            if self._http_client and hasattr(self._http_client, 'close'):
                await self._http_client.close()

            self._http_client = None
            self._update_status(AgentStatus.DISCONNECTED)
            log.info(f"Fallback Agent {self._session_id} closed")
            return True

        except Exception as e:
            log.error(f"Failed to close Fallback Agent: {e}")
            return False

    def health_check(self) -> Dict[str, Any]:
        """健康检查

        Returns:
            健康状态信息
        """
        return {
            "session_id": self._session_id,
            "status": self._status.value,
            "turn_count": self._turn_count,
            "model": self._config.model,
            "provider": "openai-compatible",
            "api_base": self._api_base,
            "initialized": self._http_client is not None,
            "created_at": self._created_at,
            "checked_at": datetime.now().isoformat()
        }

    async def _validate_connection(self):
        """验证 API 连接

        Raises:
            AgentConnectionError: 连接失败时抛出
        """
        try:
            # 尝试获取模型列表（轻量级请求）
            url = f"{self._api_base}/models"
            response = await self._http_client.get(url)

            # 检查响应状态
            if hasattr(response, 'status'):
                status = response.status
                if status != 200:
                    log.warning(f"API validation returned status {status}")
            elif hasattr(response, 'status_code'):
                status = response.status_code
                if status != 200:
                    log.warning(f"API validation returned status {status}")

        except Exception as e:
            # 连接验证失败，但不阻止初始化
            log.warning(f"API connection validation failed: {e}")

    def _build_request_body(
        self,
        message: str,
        context: Optional[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """构建请求体

        Args:
            message: 用户消息
            context: 上下文信息
            tools: 工具定义列表

        Returns:
            请求体字典
        """
        # 构建消息历史
        messages = [msg.to_dict() for msg in self._message_history]

        # 移除 timestamp 和 metadata 字段（API 不需要）
        cleaned_messages = []
        for msg in messages:
            cleaned = {
                "role": msg["role"],
                "content": msg["content"]
            }
            if "tool_calls" in msg and msg["tool_calls"]:
                cleaned["tool_calls"] = msg["tool_calls"]
            if "tool_call_id" in msg and msg["tool_call_id"]:
                cleaned["tool_call_id"] = msg["tool_call_id"]
            cleaned_messages.append(cleaned)

        body = {
            "model": self._config.model,
            "messages": cleaned_messages,
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
            "stream": False
        }

        # 添加工具定义
        if tools:
            body["tools"] = tools

        return body

    async def _call_api(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """调用 API

        Args:
            body: 请求体

        Returns:
            API 响应
        """
        url = f"{self._api_base}/chat/completions"

        try:
            # 使用 asyncio.wait_for 实现超时控制
            response = await asyncio.wait_for(
                self._http_client.post(url, json=body),
                timeout=self._config.timeout_seconds
            )

            # 解析响应
            if hasattr(response, 'json'):
                if asyncio.iscoroutine(response.json()):
                    return await response.json()
                return response.json()
            elif isinstance(response, dict):
                return response
            else:
                # Mock 响应
                return response

        except asyncio.TimeoutError:
            raise

    async def _call_api_stream(self, body: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """流式调用 API

        Args:
            body: 请求体

        Yields:
            响应片段
        """
        url = f"{self._api_base}/chat/completions"

        try:
            # 流式调用
            if hasattr(self._http_client, 'post_stream'):
                async for chunk in self._http_client.post_stream(url, json=body):
                    yield chunk
            else:
                # 模拟流式响应
                response = await self._call_api(body)
                content = ""
                if "choices" in response and len(response["choices"]) > 0:
                    content = response["choices"][0].get("message", {}).get("content", "")

                # 将完整响应分块返回
                chunk_size = 10
                for i in range(0, len(content), chunk_size):
                    yield content[i:i + chunk_size]
                    await asyncio.sleep(0.01)

        except Exception as e:
            log.error(f"API stream error: {e}")
            raise

    def _parse_response(self, raw_response: Dict[str, Any]) -> AgentResponse:
        """解析 API 响应

        Args:
            raw_response: API 原始响应

        Returns:
            AgentResponse 对象
        """
        # 解析内容
        content = ""
        tool_calls = None
        finish_reason = "stop"

        if "choices" in raw_response and len(raw_response["choices"]) > 0:
            choice = raw_response["choices"][0]
            message = choice.get("message", {})
            content = message.get("content", "")

            # 检查是否有工具调用
            if "tool_calls" in message and message["tool_calls"]:
                tool_calls = message["tool_calls"]
                content = content or ""  # 工具调用时 content 可能为空

            finish_reason = choice.get("finish_reason", "stop")

        # 解析使用统计
        usage = raw_response.get("usage")

        return AgentResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            metadata={"raw": raw_response}
        )


class _MockHTTPClient:
    """模拟的 HTTP 客户端

    用于 aiohttp 未安装时的开发和测试。
    """

    def __init__(self, headers: Dict[str, str], timeout: int):
        """初始化

        Args:
            headers: 请求头
            timeout: 超时时间（秒）
        """
        self.headers = headers
        self.timeout = timeout
        self._closed = False

    async def get(self, url: str) -> Dict[str, Any]:
        """模拟 GET 请求

        Args:
            url: 请求 URL

        Returns:
            模拟响应
        """
        return {"status_code": 200, "data": {"models": []}}

    async def post(self, url: str, json: Dict[str, Any] = None) -> Dict[str, Any]:
        """模拟 POST 请求

        Args:
            url: 请求 URL
            json: 请求体

        Returns:
            模拟响应
        """
        if json is None:
            json = {}

        messages = json.get("messages", [])
        last_message = messages[-1].get("content", "") if messages else ""

        # 检查是否需要工具调用
        tools = json.get("tools", [])
        if tools and "execute_capability" in [t.get("function", {}).get("name", "") for t in tools]:
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
                    "content": f"[Fallback Mock] 已收到消息: {last_message[:100]}..."
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150
            }
        }

    async def post_stream(self, url: str, json: Dict[str, Any] = None):
        """模拟流式 POST 请求

        Args:
            url: 请求 URL
            json: 请求体

        Yields:
            响应片段
        """
        if json is None:
            json = {}

        messages = json.get("messages", [])
        last_message = messages[-1].get("content", "") if messages else ""

        # 模拟流式响应
        chunks = [
            "[Fallback Mock Stream] ",
            f"已收到消息: ",
            f"{last_message[:50]}...",
            "\n处理完成。"
        ]

        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0.01)

    async def close(self):
        """关闭客户端"""
        self._closed = True
