#!/usr/bin/env python3
"""Workflow Engine 单元测试"""
import pytest
import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.workflow_engine import WorkflowEngine


class TestWorkflowEngine:
    """WorkflowEngine 单元测试"""

    def setup_method(self):
        """每个测试方法前执行"""
        self.engine = WorkflowEngine()
        self.engine.db = self.engine.db.__class__(":memory:")

    def test_create_run(self):
        """测试创建执行记录"""
        run_id = self.engine._create_run(
            capability_id=1,
            connection_id="test-connection",
            params={"test": "value"},
            user_id=1
        )

        assert run_id.startswith("run-")

        # 验证记录创建
        run = self.engine.get_run_status(run_id)
        assert run is not None
        assert run['status'] == 'running'
        assert run['capability_id'] == 1

    def test_create_step(self):
        """测试创建步骤记录"""
        run_id = self.engine._create_run(
            capability_id=1,
            connection_id="test-connection",
            params={}
        )

        step_id = self.engine._create_step(
            run_id=run_id,
            step_number=1,
            step_data={"command": "dashboard -n 1", "desc": "获取JVM状态"}
        )

        assert step_id > 0

        # 验证步骤创建
        steps = self.engine.get_step_logs(run_id)
        assert len(steps) == 1
        assert steps[0]['step_number'] == 1
        assert steps[0]['command'] == 'dashboard -n 1'

    def test_substitute_params(self):
        """测试参数替换"""
        template = "trace ${class} ${method} -n 10"
        params = {
            "class": "com.example.Service",
            "method": "process"
        }

        result = self.engine._substitute_params(template, params)
        assert result == "trace com.example.Service process -n 10"

    def test_substitute_params_with_step_output(self):
        """测试步骤输出参数替换"""
        template = "thread ${step1.output}"
        params = {
            "step1": {"output": "pool-1-thread-3"}
        }

        result = self.engine._substitute_params(template, params)
        assert result == "thread pool-1-thread-3"

    def test_evaluate_condition_contains(self):
        """测试条件评估 - contains"""
        params = {
            "step2": {"output": "pool-1-thread-3 RUNNABLE"}
        }

        result = self.engine._evaluate_condition("step2.output contains 'RUNNABLE'", params)
        assert result is True

        result = self.engine._evaluate_condition("step2.output contains 'BLOCKED'", params)
        assert result is False

    def test_evaluate_condition_equals(self):
        """测试条件评估 - equals"""
        params = {
            "step1": {"status": "success"}
        }

        result = self.engine._evaluate_condition("step1.status == 'success'", params)
        assert result is True

        result = self.engine._evaluate_condition("step1.status == 'failed'", params)
        assert result is False

    def test_is_retryable(self):
        """测试可重试检查"""
        retry_policy = {
            "retryable_step_types": ["arthas_command", "llm_analysis"],
            "non_retryable_step_types": ["redefine", "mc"]
        }

        assert self.engine._is_retryable("arthas_command", retry_policy) is True
        assert self.engine._is_retryable("llm_analysis", retry_policy) is True
        assert self.engine._is_retryable("redefine", retry_policy) is False
        assert self.engine._is_retryable("mc", retry_policy) is False
        assert self.engine._is_retryable("unknown", retry_policy) is True  # 默认可重试

    def test_cancel_run(self):
        """测试取消执行"""
        run_id = self.engine._create_run(
            capability_id=1,
            connection_id="test-connection",
            params={}
        )

        success = self.engine.cancel_run(run_id)
        assert success is True

        # 验证状态更新
        run = self.engine.get_run_status(run_id)
        assert run['status'] == 'cancelled'

    def test_cancel_run_completed(self):
        """测试取消已完成的执行"""
        run_id = self.engine._create_run(
            capability_id=1,
            connection_id="test-connection",
            params={}
        )

        # 模拟完成
        self.engine._update_run_status(run_id, "success")

        success = self.engine.cancel_run(run_id)
        assert success is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
