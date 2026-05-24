#!/usr/bin/env python3
"""Workflow Engine 服务 - DSL步骤执行、错误处理、执行记录"""
import json
import logging
import uuid
import importlib
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

log = logging.getLogger(__name__)


class WorkflowEngine:
    """工作流引擎 - DSL步骤执行"""

    # 默认重试策略
    DEFAULT_RETRY_POLICY = {
        "mode": "resume",  # resume: 从失败步骤继续 | restart: 重新开始
        "max_retries": 3,
        "retryable_step_types": ["arthas_command", "llm_analysis", "get_pod_status", "get_pod_metrics"],
        "non_retryable_step_types": ["redefine", "mc"]
    }

    def __init__(self):
        from models.db import get_db
        self.db = get_db()

    def execute_skill(self, capability_id: int, params: Dict[str, Any],
                     connection_id: str, user_id: int = None) -> str:
        """执行 Skill"""
        # 1. 获取能力定义
        capability = self._get_capability(capability_id)
        if not capability:
            raise ValueError(f"Capability {capability_id} not found")

        # 2. 创建执行记录
        run_id = self._create_run(capability_id, connection_id, params, user_id)

        # 3. 执行 DSL
        try:
            if capability.get('steps_json'):
                # 场景方案（多步骤）
                self._execute_dsl(run_id, capability['steps_json'], params, connection_id)
            elif capability.get('arthas_command'):
                # 快捷工具/诊断模板（单命令）
                self._execute_command(run_id, capability['arthas_command'], params, connection_id)
            elif capability.get('handler'):
                # AI 诊断（处理器）
                self._execute_handler(run_id, capability['handler'], params, connection_id)
            else:
                raise ValueError("No execution method defined for capability")

            # 4. 更新状态
            self._update_run_status(run_id, "success")

        except Exception as e:
            self._update_run_status(run_id, "failed", str(e))
            raise

        return run_id

    def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """获取执行状态"""
        return self.db.fetch_one(
            "SELECT * FROM task_logs WHERE id = ?",
            (run_id,)
        )

    def get_step_logs(self, run_id: str) -> List[Dict[str, Any]]:
        """获取步骤日志"""
        return self.db.fetch_all(
            "SELECT * FROM step_logs WHERE run_id = ? ORDER BY step_number",
            (run_id,)
        )

    def cancel_run(self, run_id: str) -> bool:
        """取消执行"""
        run = self.get_run_status(run_id)
        if not run:
            return False

        if run['status'] not in ['pending', 'running']:
            return False

        self._update_run_status(run_id, "cancelled")
        return True

    def _execute_dsl(self, run_id: str, dsl: str, params: Dict[str, Any],
                    connection_id: str):
        """执行 DSL（场景方案）"""
        try:
            dsl_data = json.loads(dsl)
            steps = dsl_data.get('steps', [])
        except json.JSONDecodeError:
            raise ValueError("Invalid DSL format")

        # 获取重试策略
        retry_policy = dsl_data.get('retry_policy', self.DEFAULT_RETRY_POLICY)

        for i, step in enumerate(steps):
            step_number = i + 1
            step_id = self._create_step(run_id, step_number, step)

            # 检查条件
            if step.get('condition'):
                if not self._evaluate_condition(step['condition'], params):
                    self._update_step_status(step_id, "skipped", output="Condition not met")
                    continue

            # 执行步骤（支持重试）
            max_retries = retry_policy.get('max_retries', 3)
            retry_count = 0

            while retry_count <= max_retries:
                try:
                    # 参数替换
                    command = self._substitute_params(step.get('command', ''), params)

                    # 执行命令
                    output = self._execute_step_by_type(step, command, connection_id, params)

                    # 记录步骤完成
                    self._update_step_status(step_id, "success", output=output)

                    # 传递步骤结果
                    params[f"step{step_number}"] = {"output": output}

                    # 成功，跳出重试循环
                    break

                except Exception as e:
                    retry_count += 1
                    error_msg = f"Attempt {retry_count}/{max_retries + 1} failed: {str(e)}"

                    # 检查是否可重试
                    step_type = step.get('type', 'arthas_command')
                    if not self._is_retryable(step_type, retry_policy):
                        self._update_step_status(step_id, "failed", error=error_msg)
                        raise

                    # 检查是否超过最大重试次数
                    if retry_count > max_retries:
                        self._update_step_status(step_id, "failed", error=error_msg)
                        raise

                    # 记录重试
                    log.warning(f"Step {step_number} retry {retry_count}: {error_msg}")

            # 检查失败策略
            if step.get('on_failure') == 'abort':
                break
            elif step.get('on_failure') == 'skip':
                continue

    def _execute_command(self, run_id: str, command: str, params: Dict[str, Any],
                        connection_id: str):
        """执行单条命令（快捷工具/诊断模板）"""
        step_id = self._create_step(run_id, 1, {"command": command})

        try:
            # 参数替换
            full_command = self._substitute_params(command, params)

            # 执行命令
            output = self._execute_arthas_command(full_command, connection_id)

            # 记录步骤完成
            self._update_step_status(step_id, "success", output=output)

        except Exception as e:
            self._update_step_status(step_id, "failed", error=str(e))
            raise

    def _execute_handler(self, run_id: str, handler: str, params: Dict[str, Any],
                        connection_id: str):
        """执行 Handler（AI 诊断）"""
        step_id = self._create_step(run_id, 1, {"handler": handler})

        try:
            # 动态导入 Handler
            module_path, function_name = handler.rsplit(".", 1)
            module = importlib.import_module(module_path)
            handler_func = getattr(module, function_name)

            # 执行 Handler
            output = handler_func(params, connection_id)

            # 记录步骤完成
            self._update_step_status(step_id, "success", output=str(output))

        except Exception as e:
            self._update_step_status(step_id, "failed", error=str(e))
            raise

    def _execute_step_by_type(self, step: Dict[str, Any], command: str,
                             connection_id: str, params: Dict[str, Any]) -> str:
        """根据步骤类型执行"""
        step_type = step.get('type', 'arthas_command')

        if step_type == 'arthas_command':
            return self._execute_arthas_command(command, connection_id)
        elif step_type == 'llm_analysis':
            return self._execute_llm_analysis(step, params)
        elif step_type == 'get_pod_status':
            return self._get_pod_status(connection_id)
        elif step_type == 'get_pod_metrics':
            return self._get_pod_metrics(connection_id)
        else:
            # 默认作为 Arthas 命令执行
            return self._execute_arthas_command(command, connection_id)

    def _execute_arthas_command(self, command: str, connection_id: str) -> str:
        """执行 Arthas 命令"""
        # TODO: 集成实际的 Arthas 执行器
        # 这里先返回模拟输出
        log.info(f"Executing Arthas command: {command} on connection: {connection_id}")
        return f"[Simulated output for: {command}]"

    def _execute_llm_analysis(self, step: Dict[str, Any], params: Dict[str, Any]) -> str:
        """执行大模型分析"""
        # TODO: 集成实际的 LLM 调用
        prompt = step.get('prompt', '分析以上诊断结果')
        log.info(f"Executing LLM analysis with prompt: {prompt}")
        return f"[Simulated LLM analysis for: {prompt}]"

    def _get_pod_status(self, connection_id: str) -> str:
        """获取 Pod 状态"""
        # TODO: 集成实际的 kubectl 执行器
        log.info(f"Getting pod status for connection: {connection_id}")
        return f"[Simulated pod status for: {connection_id}]"

    def _get_pod_metrics(self, connection_id: str) -> str:
        """获取 Pod 指标"""
        # TODO: 集成实际的指标采集
        log.info(f"Getting pod metrics for connection: {connection_id}")
        return f"[Simulated pod metrics for: {connection_id}]"

    def _evaluate_condition(self, condition: str, params: Dict[str, Any]) -> bool:
        """评估条件表达式

        支持的条件格式：
        - "step2.output contains 'RUNNABLE'"
        - "step1.output contains 'ERROR'"
        - "step3.status == 'success'"
        """
        try:
            # 简单的条件解析
            if 'contains' in condition:
                parts = condition.split(' contains ')
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    expected_value = parts[1].strip().strip("'\"")

                    # 获取变量值
                    actual_value = self._get_condition_variable(var_name, params)
                    return expected_value in str(actual_value)

            elif '==' in condition:
                parts = condition.split('==')
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    expected_value = parts[1].strip().strip("'\"")

                    actual_value = self._get_condition_variable(var_name, params)
                    return str(actual_value) == expected_value

            # 如果无法解析，返回 True（执行步骤）
            log.warning(f"Cannot parse condition: {condition}")
            return True

        except Exception as e:
            log.error(f"Error evaluating condition: {condition}, error: {e}")
            return True

    def _get_condition_variable(self, var_name: str, params: Dict[str, Any]) -> Any:
        """获取条件变量的值"""
        # 支持 stepN.output 格式
        if var_name.startswith('step') and '.output' in var_name:
            step_num = var_name.replace('step', '').replace('.output', '')
            step_data = params.get(f"step{step_num}", {})
            return step_data.get('output', '')

        # 支持 stepN.status 格式
        if var_name.startswith('step') and '.status' in var_name:
            step_num = var_name.replace('step', '').replace('.status', '')
            step_data = params.get(f"step{step_num}", {})
            return step_data.get('status', '')

        # 直接返回参数值
        return params.get(var_name, '')

    def _is_retryable(self, step_type: str, retry_policy: Dict[str, Any]) -> bool:
        """检查步骤类型是否可重试"""
        retryable_types = retry_policy.get('retryable_step_types', [])
        non_retryable_types = retry_policy.get('non_retryable_step_types', [])

        if step_type in non_retryable_types:
            return False
        if step_type in retryable_types:
            return True
        # 默认可重试
        return True

    def _substitute_params(self, template: str, params: Dict[str, Any]) -> str:
        """参数替换"""
        result = template
        for key, value in params.items():
            if isinstance(value, dict) and "output" in value:
                result = result.replace(f"${{{key}.output}}", str(value["output"]))
            elif isinstance(value, (str, int, float)):
                result = result.replace(f"${{{key}}}", str(value))
        return result

    def _create_run(self, capability_id: int, connection_id: str,
                   params: Dict[str, Any], user_id: int = None) -> str:
        """创建执行记录"""
        run_id = f"run-{uuid.uuid4().hex[:12]}"

        self.db.insert('task_logs', {
            'id': run_id,
            'capability_id': capability_id,
            'user_id': user_id,
            'status': 'running',
            'execution_mode': 'immediate',
            'execution_type': 'diagnosis',
            'target_json': json.dumps({"connection_id": connection_id}),
            'params_json': json.dumps(params),
            'started_at': datetime.now().isoformat(),
        })

        return run_id

    def _create_step(self, run_id: str, step_number: int,
                    step_data: Dict[str, Any]) -> int:
        """创建步骤记录"""
        return self.db.insert('step_logs', {
            'run_id': run_id,
            'step_number': step_number,
            'step_name': step_data.get('desc', f'Step {step_number}'),
            'step_type': 'arthas_command' if 'command' in step_data else 'handler',
            'command': step_data.get('command', step_data.get('handler')),
            'status': 'running',
        })

    def _update_step_status(self, step_id: int, status: str,
                           output: str = None, error: str = None):
        """更新步骤状态"""
        updates = {'status': status}
        if output:
            updates['output'] = output
        if error:
            updates['error_message'] = error

        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        query = f"UPDATE step_logs SET {set_clause} WHERE id = ?"
        params = list(updates.values()) + [step_id]

        self.db.execute(query, tuple(params))

    def _update_run_status(self, run_id: str, status: str, error: str = None):
        """更新执行状态"""
        updates = {'status': status, 'finished_at': datetime.now().isoformat()}
        if error:
            updates['error_message'] = error

        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        query = f"UPDATE task_logs SET {set_clause} WHERE id = ?"
        params = list(updates.values()) + [run_id]

        self.db.execute(query, tuple(params))

    def _get_capability(self, capability_id: int) -> Optional[Dict[str, Any]]:
        """获取能力定义"""
        return self.db.fetch_one(
            "SELECT * FROM diagnosis_capabilities WHERE id = ?",
            (capability_id,)
        )


# 全局实例
_workflow_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    """获取 WorkflowEngine 单例"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine
