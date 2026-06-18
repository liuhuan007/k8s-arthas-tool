"""统一 LLM 客户端 — 支持 OpenAI / 通义千问 / Ollama"""
from __future__ import annotations
import json
import os
from typing import Any, Optional
import urllib.request


class LLMClient:
    """统一 LLM 调用接口，支持多种后端"""

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: str = "",
        base_url: str = "",
        temperature: float = 0.3,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.base_url = base_url or self._default_base_url()
        self.temperature = temperature

    def _default_base_url(self) -> str:
        defaults = {
            "openai": "https://api.openai.com/v1",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "ollama": "http://localhost:11434/v1",
        }
        return defaults.get(self.provider, defaults["openai"])

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """调用 LLM，返回标准化响应"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"content": f"[LLM 调用失败] {e}", "tool_calls": None}

        choice = body["choices"][0]["message"]

        # 解析 tool_calls
        tool_calls = None
        if choice.get("tool_calls"):
            tool_calls = []
            for tc in choice["tool_calls"]:
                tool_calls.append({
                    "id": tc["id"],
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                })

        return {
            "content": choice.get("content", ""),
            "tool_calls": tool_calls,
        }

    async def classify(self, user_input: str, options: list[str]) -> str:
        """让 LLM 分类用户意图，返回最匹配的选项"""
        prompt = f"""根据用户输入，判断属于以下哪个类别，只返回类别名称：
类别：{', '.join(options)}

用户输入：{user_input}"""

        result = await self.chat([
            {"role": "system", "content": "你是意图分类器，只返回类别名称。"},
            {"role": "user", "content": prompt},
        ])
        answer = result.get("content", "").strip().lower()
        for opt in options:
            if opt in answer:
                return opt
        return options[0] if options else "ops"
