#!/usr/bin/env python3
"""Skill Workflow Engine

执行诊断工作流 Skill，按步骤调用 CLI 命令并汇总结果。
支持 kubectl、arthas、llm 三种步骤类型。

Author: CLI Architecture Phase
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

log = logging.getLogger(__name__)


class WorkflowEngine:
    """诊断工作流执行引擎"""

    def __init__(self):
        self._cli_adapters = {}

    def get_cli_adapter(self, cli: str):
        """获取 CLI 适配器"""
        if cli not in self._cli_adapters:
            if cli == "kubectl":
                from backend.cli import KubectlAdapter
                self._cli_adapters[cli] = KubectlAdapter()
            elif cli == "arthas":
                from backend.cli import ArthasAdapter
                self._cli_adapters[cli] = ArthasAdapter()
        return self._cli_adapters.get(cli)

    def execute_workflow(self, skill: Dict, params: Dict = None,
                        connection_id: str = "") -> Dict:
        """
        执行诊断工作流

        Args:
            skill: Skill 定义（包含 workflow JSON）
            params: 用户参数
            connection_id: Arthas 连接 ID

        Returns:
            执行结果
        """
        workflow = json.loads(skill.get("workflow", "[]"))
        if not workflow:
            return {"ok": False, "error": "Workflow is empty"}

        results = {}
        start_time = datetime.now()

        for step in workflow:
            step_id = step.get("id", "unknown")
            cli = step.get("cli", "")
            command = step.get("command", "")
            step_params = self._resolve_params(step.get("params", {}), params, results)

            log.info("Executing step: %s (%s %s)", step_id, cli, command)

            # 检查条件
            condition = step.get("condition")
            if condition and not self._evaluate_condition(condition, results):
                log.info("Step %s skipped (condition not met)", step_id)
                results[step_id] = {"skipped": True, "reason": "condition_not_met"}
                continue

            # 执行步骤
            try:
                if cli == "llm":
                    result = self._execute_llm_step(step, results)
                else:
                    adapter = self.get_cli_adapter(cli)
                    if not adapter:
                        result = {"ok": False, "error": f"Unknown CLI: {cli}"}
                    else:
                        result = adapter.execute(command, step_params)

                results[step_id] = {
                    "ok": result.ok if hasattr(result, "ok") else True,
                    "data": result.data if hasattr(result, "data") else result,
                    "command": result.command if hasattr(result, "command") else command,
                }

            except Exception as e:
                log.error("Step %s failed: %s", step_id, e)
                results[step_id] = {"ok": False, "error": str(e)}

        elapsed = (datetime.now() - start_time).total_seconds()

        return {
            "ok": True,
            "skill": skill.get("name"),
            "results": results,
            "elapsed_seconds": round(elapsed, 2),
            "timestamp": datetime.now().isoformat(),
        }

    def _resolve_params(self, step_params: Dict, user_params: Dict,
                        results: Dict) -> Dict:
        """解析参数模板"""
        resolved = {}
        for key, value in step_params.items():
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                param_name = value[1:-1]
                if param_name in (user_params or {}):
                    resolved[key] = user_params[param_name]
                elif param_name in results:
                    resolved[key] = results[param_name]
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    def _evaluate_condition(self, condition: str, results: Dict) -> bool:
        """评估条件表达式"""
        try:
            # 简单条件评估: "step_id.field == value"
            parts = condition.split(" == ")
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip().strip("'\"")

                # 解析 step_id.field
                if "." in left:
                    step_id, field = left.split(".", 1)
                    if step_id in results:
                        actual = results[step_id].get(field, "")
                        return str(actual) == right
                else:
                    actual = results.get(left, {})
                    if isinstance(actual, dict):
                        return actual.get("ok", False)
            return True
        except Exception:
            return True

    def _execute_llm_step(self, step: Dict, results: Dict) -> Dict:
        """执行 LLM 分析步骤"""
        # 收集输入数据
        input_steps = step.get("input", [])
        input_data = {}
        for step_id in input_steps:
            if step_id in results:
                input_data[step_id] = results[step_id]

        # 构建 prompt
        prompt = step.get("prompt", "分析诊断结果")
        context = json.dumps(input_data, ensure_ascii=False, default=str)[:5000]

        # TODO: 调用 LLM API
        # 目前返回占位结果
        return {
            "ok": True,
            "data": {
                "analysis": f"AI 分析结果（占位）: {prompt}",
                "input_summary": list(input_data.keys()),
            },
            "command": "llm.analyze",
        }


# 全局实例
_workflow_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    """获取 WorkflowEngine 单例"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine


def execute_workflow(skill: Dict, params: Dict = None,
                     connection_id: str = "") -> Dict:
    """执行诊断工作流（便捷函数）"""
    engine = get_workflow_engine()
    return engine.execute_workflow(skill, params, connection_id)
