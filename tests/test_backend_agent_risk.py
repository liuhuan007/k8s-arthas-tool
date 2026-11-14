import asyncio
import json

from backend.agent.agents import create_arthas_agent
from backend.agent.base import Agent, Tool


class FakeLLM:
    def __init__(self):
        self.responses = [
            {
                "tool_calls": [{
                    "id": "call-1",
                    "function": {
                        "name": "heapdump",
                        "arguments": json.dumps({"filename": "/tmp/dump.hprof"}),
                    },
                }]
            },
            {"content": "需要用户在 UI 中确认后再执行。"},
        ]

    async def chat(self, messages, tools=None):
        return self.responses.pop(0)


def test_agent_never_executes_high_risk_tools_without_approval():
    executed = []
    approval_steps = []

    async def heapdump(**kwargs):
        executed.append(kwargs)
        return "started"

    async def on_step(*args, **kwargs):
        approval_steps.append((args, kwargs))

    agent = Agent(
        name="test",
        display_name="Test",
        system_prompt="",
        tools=[Tool("heapdump", "dump", {}, heapdump, risk_level="high")],
        llm_client=FakeLLM(),
    )

    result = asyncio.run(
        agent.run("inspect memory", mode="auto", on_step=on_step))

    assert executed == []
    assert result.steps[0].result.startswith("[需用户确认]")
    assert approval_steps[0][1]["needs_approval"] is True


def test_arthas_agent_bounds_sampling_and_never_executes_heapdump():
    executed = []

    class Connection:
        def profiler_start(self, **kwargs):
            executed.append(("profiler", kwargs))
            return "started"

        def jfr_start(self, **kwargs):
            executed.append(("jfr", kwargs))
            return "started"

        def heapdump(self, **kwargs):
            executed.append(("heapdump", kwargs))
            return "started"

    agent = create_arthas_agent(FakeLLM(), arthas_connection=Connection())

    long_sample = asyncio.run(agent.tools["arthas_profiler"].execute(duration=121))
    allowed_sample = asyncio.run(agent.tools["arthas_profiler"].execute(duration=120))
    heap_dump = asyncio.run(agent.tools["arthas_heap_dump"].execute())

    assert "逐次确认" in long_sample
    assert allowed_sample == "started"
    assert "不直接执行 Heap Dump" in heap_dump
    assert executed == [("profiler", {"duration": 120})]
