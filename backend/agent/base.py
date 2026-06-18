"""Agent 基类和 Tool 定义"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional


@dataclass
class Tool:
    """可被 Agent 调用的工具"""
    name: str
    description: str
    parameters: dict  # JSON Schema
    executor: Callable[..., Awaitable[Any]]
    risk_level: str = "low"  # low / medium / high

    def to_schema(self) -> dict:
        """转为 LLM function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    async def execute(self, **kwargs) -> str:
        try:
            result = await self.executor(**kwargs)
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return f"[工具执行错误] {self.name}: {e}"


@dataclass
class AgentStep:
    """Agent 执行的一步"""
    tool_name: str
    tool_args: dict
    result: str


@dataclass
class AgentResult:
    """Agent 完整执行结果"""
    answer: str
    steps: list[AgentStep] = field(default_factory=list)
    mode: str = "auto"  # auto / assist


class Agent:
    """轻量 Agent 基类 — 核心是一个 while True 循环"""

    def __init__(
        self,
        name: str,
        display_name: str,
        system_prompt: str,
        tools: list[Tool],
        llm_client,
        max_steps: int = 10,
    ):
        self.name = name
        self.display_name = display_name
        self.system_prompt = system_prompt
        self.tools = {t.name: t for t in tools}
        self.llm = llm_client
        self.max_steps = max_steps

    async def run(
        self,
        user_input: str,
        mode: str = "auto",
        on_step: Callable | None = None,
    ) -> AgentResult:
        """
        执行 Agent 循环。
        mode='auto':   全自动执行
        mode='assist': 高风险操作需要用户确认
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]
        tools_schema = [t.to_schema() for t in self.tools.values()]
        steps = []

        for _ in range(self.max_steps):
            response = await self.llm.chat(
                messages=messages,
                tools=tools_schema if tools_schema else None,
            )

            # 没有 tool_calls → 最终回答
            if not response.get("tool_calls"):
                return AgentResult(
                    answer=response.get("content", ""),
                    steps=steps,
                    mode=mode,
                )

            # 执行工具调用
            messages.append({
                "role": "assistant",
                "content": response.get("content", ""),
                "tool_calls": response["tool_calls"],
            })

            for call in response["tool_calls"]:
                tool_name = call["function"]["name"]
                tool_args = json.loads(call["function"]["arguments"])
                tool = self.tools.get(tool_name)

                if not tool:
                    result = f"[未知工具] {tool_name}"
                elif mode == "assist" and tool.risk_level == "high":
                    result = f"[需确认] 高风险操作 {tool_name}，参数: {json.dumps(tool_args)}"
                    if on_step:
                        await on_step(tool_name, tool_args, result, needs_approval=True)
                else:
                    result = await tool.execute(**tool_args)
                    if on_step:
                        await on_step(tool_name, tool_args, result)

                steps.append(AgentStep(tool_name, tool_args, result))
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                })

        return AgentResult(
            answer="[达到最大步数限制，未能完成诊断]",
            steps=steps,
            mode=mode,
        )
