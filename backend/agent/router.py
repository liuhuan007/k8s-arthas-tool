"""Agent 注册表和意图路由"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Agent


class AgentRegistry:
    """Agent 注册表 — 管理所有可用 Agent"""

    def __init__(self):
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent):
        self._agents[agent.name] = agent

    def get(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[dict]:
        return [
            {"name": a.name, "display_name": a.display_name}
            for a in self._agents.values()
        ]

    @property
    def names(self) -> list[str]:
        return list(self._agents.keys())


class AgentRouter:
    """意图路由 — 根据用户输入选择 Agent"""

    # 关键词快速匹配
    KEYWORDS = {
        "arthas": [
            "cpu高", "cpu 100", "内存", "死锁", "线程", "gc", "垃圾回收",
            "arthas", "profiler", "采样", "heap", "dump", "jfr", "火焰图",
            "内存泄漏", "oom", "full gc", "classloader", "watch", "trace",
        ],
        "k8s": [
            "pod", "容器", "调度", "node", "节点", "kubectl", "日志", "事件",
            "event", "重启", "crash", "oomkilled", "pending", "evict",
            "replica", "deployment", "service", "ingress",
        ],
    }

    def __init__(self, registry: AgentRegistry, llm_client=None):
        self.registry = registry
        self.llm = llm_client

    def route(self, user_input: str) -> str:
        """返回最匹配的 agent name（同步，关键词匹配优先）"""
        text = user_input.lower()

        # 1. 关键词快速匹配
        for agent_name, keywords in self.KEYWORDS.items():
            if any(kw in text for kw in keywords):
                if self.registry.get(agent_name):
                    return agent_name

        # 2. 默认 Ops Agent
        if self.registry.get("ops"):
            return "ops"
        return self.registry.names[0] if self.registry.names else ""
