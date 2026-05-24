#!/usr/bin/env python3
"""Agent 工厂 - 管理 Agent 实例的创建和生命周期

本模块提供 Agent 工厂模式实现，支持：
- 根据配置自动创建合适的 Agent
- Agent 池化管理
- 自动降级（CodeBuddy -> Fallback）
- 单例管理

Author: Kou (software-engineer)
Created: 2025-05-25
"""

import logging
from typing import Dict, Any, Optional, List, Type
from datetime import datetime

from services.agent_interface import AgentInterface, AgentConfig, AgentStatus
from services.agent_sdk_config import AgentSDKConfig

log = logging.getLogger(__name__)


class AgentFactory:
    """Agent 工厂

    管理 Agent 实例的创建、缓存和生命周期。
    支持根据用户配置自动选择合适的 Agent 类型。

    使用示例：
        factory = AgentFactory()
        agent = await factory.create_agent(user_id=1)
        response = await agent.send_message("分析问题")
        await factory.release_agent(agent.session_id)
    """

    # 支持的 Agent 类型映射
    AGENT_TYPES: Dict[str, Type[AgentInterface]] = {}

    def __init__(self):
        """初始化 Agent 工厂"""
        self._agents: Dict[str, AgentInterface] = {}
        self._agent_configs: Dict[str, AgentConfig] = {}
        self._usage_stats: Dict[str, Dict[str, Any]] = {}

        # 延迟导入避免循环依赖
        self._register_agent_types()

    def _register_agent_types(self):
        """注册可用的 Agent 类型"""
        try:
            from services.agents.codebuddy_agent import CodeBuddyAgent
            self.AGENT_TYPES["codebuddy"] = CodeBuddyAgent
        except ImportError:
            log.warning("CodeBuddyAgent not available")

        try:
            from services.agents.fallback_agent import FallbackAgent
            self.AGENT_TYPES["fallback"] = FallbackAgent
        except ImportError:
            log.warning("FallbackAgent not available")

    async def create_agent(
        self,
        user_id: int,
        agent_type: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None
    ) -> AgentInterface:
        """创建或获取 Agent 实例

        Args:
            user_id: 用户 ID
            agent_type: 指定 Agent 类型（可选，自动检测）
            config_override: 配置覆盖（可选）

        Returns:
            Agent 实例

        Raises:
            ValueError: 无可用 Agent 类型时抛出
        """
        # 生成缓存键
        cache_key = f"user-{user_id}"

        # 检查是否已有可用的 Agent
        if cache_key in self._agents:
            agent = self._agents[cache_key]
            if agent.status not in [AgentStatus.ERROR, AgentStatus.DISCONNECTED]:
                log.debug(f"Reusing existing agent for user {user_id}")
                return agent
            else:
                # Agent 状态异常，释放并重新创建
                await self.release_agent(cache_key)

        # 获取用户配置
        sdk_config = AgentSDKConfig.get_config(user_id)
        agent_config = self._build_agent_config(sdk_config, config_override)

        # 确定 Agent 类型
        if agent_type is None:
            agent_type = self._select_agent_type(sdk_config)

        # 创建 Agent
        agent_class = self.AGENT_TYPES.get(agent_type)
        if agent_class is None:
            # 尝试降级
            agent_class = self.AGENT_TYPES.get("fallback")
            if agent_class is None:
                raise ValueError(f"No available agent type. Requested: {agent_type}")
            agent_type = "fallback"
            log.warning(f"Agent type '{agent_type}' not available, using fallback")

        # 实例化 Agent
        agent = agent_class(agent_config)

        # 初始化 Agent
        success = await agent.initialize()
        if not success:
            # 初始化失败，尝试降级
            if agent_type != "fallback":
                log.warning(f"Agent '{agent_type}' initialization failed, trying fallback")
                fallback_class = self.AGENT_TYPES.get("fallback")
                if fallback_class:
                    agent = fallback_class(agent_config)
                    success = await agent.initialize()
                    if success:
                        agent_type = "fallback"
                    else:
                        raise ValueError("All agent types failed to initialize")
            else:
                raise ValueError("Fallback agent initialization failed")

        # 缓存 Agent
        self._agents[cache_key] = agent
        self._agent_configs[cache_key] = agent_config
        self._usage_stats[cache_key] = {
            "created_at": datetime.now().isoformat(),
            "agent_type": agent_type,
            "user_id": user_id,
            "message_count": 0
        }

        log.info(f"Created agent for user {user_id}: type={agent_type}, session={agent.session_id}")
        return agent

    async def get_agent(self, session_id: str) -> Optional[AgentInterface]:
        """获取 Agent 实例

        Args:
            session_id: 会话 ID（格式：user-{user_id}）

        Returns:
            Agent 实例，不存在则返回 None
        """
        return self._agents.get(session_id)

    async def release_agent(self, session_id: str) -> bool:
        """释放 Agent 实例

        Args:
            session_id: 会话 ID

        Returns:
            是否释放成功
        """
        agent = self._agents.get(session_id)
        if agent is None:
            return False

        try:
            await agent.close()
            del self._agents[session_id]
            if session_id in self._agent_configs:
                del self._agent_configs[session_id]
            if session_id in self._usage_stats:
                del self._usage_stats[session_id]
            log.info(f"Released agent {session_id}")
            return True
        except Exception as e:
            log.error(f"Failed to release agent {session_id}: {e}")
            return False

    async def close_all(self):
        """关闭所有 Agent"""
        session_ids = list(self._agents.keys())
        for session_id in session_ids:
            await self.release_agent(session_id)
        log.info("All agents closed")

    def get_agent_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取 Agent 状态

        Args:
            session_id: 会话 ID

        Returns:
            状态信息，不存在则返回 None
        """
        agent = self._agents.get(session_id)
        if agent is None:
            return None

        stats = self._usage_stats.get(session_id, {})
        health = agent.health_check()
        health.update(stats)
        return health

    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有 Agent

        Returns:
            Agent 状态列表
        """
        agents = []
        for session_id, agent in self._agents.items():
            stats = self._usage_stats.get(session_id, {})
            health = agent.health_check()
            health.update(stats)
            agents.append(health)
        return agents

    def _select_agent_type(self, sdk_config: Dict[str, Any]) -> str:
        """根据配置选择 Agent 类型

        Args:
            sdk_config: SDK 配置

        Returns:
            Agent 类型
        """
        # 检查 provider 配置
        provider = sdk_config.get("provider", "").lower()

        if provider == "codebuddy" and "codebuddy" in self.AGENT_TYPES:
            return "codebuddy"
        elif provider in ["openai", "deepseek", "ollama"] and "fallback" in self.AGENT_TYPES:
            return "fallback"
        elif "codebuddy" in self.AGENT_TYPES:
            # 默认优先使用 CodeBuddy
            return "codebuddy"
        elif "fallback" in self.AGENT_TYPES:
            return "fallback"
        else:
            return "fallback"

    def _build_agent_config(
        self,
        sdk_config: Dict[str, Any],
        override: Optional[Dict[str, Any]] = None
    ) -> AgentConfig:
        """构建 Agent 配置

        Args:
            sdk_config: SDK 配置
            override: 配置覆盖

        Returns:
            AgentConfig 对象
        """
        config_dict = {
            "model": sdk_config.get("model", "default"),
            "api_key": sdk_config.get("api_key", ""),
            "base_url": sdk_config.get("base_url", ""),
            "provider": sdk_config.get("provider", "openai"),
            "max_turns": sdk_config.get("max_turns", 50),
            "temperature": sdk_config.get("temperature", 0.7),
            "timeout_seconds": sdk_config.get("timeout_seconds", 300),
            "max_tokens": sdk_config.get("max_tokens", 4096)
        }

        # 应用配置覆盖
        if override:
            config_dict.update(override)

        return AgentConfig(**config_dict)

    def get_factory_stats(self) -> Dict[str, Any]:
        """获取工厂统计信息

        Returns:
            统计信息
        """
        return {
            "total_agents": len(self._agents),
            "available_types": list(self.AGENT_TYPES.keys()),
            "agents": {
                sid: {
                    "status": agent.status.value,
                    "turn_count": agent.turn_count,
                    "stats": self._usage_stats.get(sid, {})
                }
                for sid, agent in self._agents.items()
            }
        }


# 全局实例
_agent_factory: Optional[AgentFactory] = None


def get_agent_factory() -> AgentFactory:
    """获取 AgentFactory 单例

    Returns:
        AgentFactory 实例
    """
    global _agent_factory
    if _agent_factory is None:
        _agent_factory = AgentFactory()
    return _agent_factory
