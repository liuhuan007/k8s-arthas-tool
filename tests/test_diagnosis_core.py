#!/usr/bin/env python3
"""任务中心诊断重构 - 核心功能测试"""
import pytest
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.core.parameter_validator import ParameterValidator
from backend.core.command_builder import build_command, extract_nested_value


class TestParameterValidator:
    """参数校验引擎测试"""
    
    def test_empty_schema(self):
        """空 schema 应该通过校验"""
        assert ParameterValidator.validate('', {}) is None
        assert ParameterValidator.validate('{}', {}) is None
    
    def test_required_field_missing(self):
        """必填字段缺失应该报错"""
        schema = '[{"name": "class", "label": "类名", "required": true}]'
        error = ParameterValidator.validate(schema, {})
        assert error is not None
        assert "缺少必填参数" in error
    
    def test_required_field_present(self):
        """必填字段存在应该通过"""
        schema = '[{"name": "class", "label": "类名", "required": true}]'
        error = ParameterValidator.validate(schema, {"class": "com.example.Service"})
        assert error is None
    
    def test_pattern_validation(self):
        """正则校验应该生效"""
        schema = '[{"name": "class", "label": "类名", "pattern": "^[A-Za-z_$][\\\\w.$]*$"}]'
        
        # 合法值
        error = ParameterValidator.validate(schema, {"class": "com.example.Service"})
        assert error is None
        
        # 非法值
        error = ParameterValidator.validate(schema, {"class": "123invalid"})
        assert error is not None
        assert "格式不正确" in error
    
    def test_enum_validation(self):
        """枚举值校验应该生效"""
        schema = '[{"name": "level", "label": "级别", "options": ["DEBUG", "INFO", "ERROR"]}]'
        
        # 合法值
        error = ParameterValidator.validate(schema, {"level": "DEBUG"})
        assert error is None
        
        # 非法值
        error = ParameterValidator.validate(schema, {"level": "TRACE"})
        assert error is not None
        assert "不在允许范围内" in error
    
    def test_range_validation(self):
        """数值范围校验应该生效"""
        schema = '[{"name": "timeout", "label": "超时", "type": "number", "min": 1, "max": 300}]'
        
        # 合法值
        error = ParameterValidator.validate(schema, {"timeout": 60})
        assert error is None
        
        # 超出范围
        error = ParameterValidator.validate(schema, {"timeout": 500})
        assert error is not None
        assert "不能大于" in error
    
    def test_length_validation(self):
        """长度校验应该生效"""
        schema = '[{"name": "name", "label": "名称", "min_length": 2, "max_length": 50}]'
        
        # 合法值
        error = ParameterValidator.validate(schema, {"name": "test"})
        assert error is None
        
        # 太短
        error = ParameterValidator.validate(schema, {"name": "a"})
        assert error is not None
        assert "不能少于" in error


class TestCommandBuilder:
    """命令构建器测试"""
    
    def test_simple_param_replacement(self):
        """简单参数替换"""
        template = "trace ${class} ${method}"
        params = {"class": "com.example.Service", "method": "doWork"}
        
        result = build_command(template, params)
        assert result == "trace com.example.Service doWork"
    
    def test_default_value_replacement(self):
        """默认值替换"""
        template = "trace ${class} ${method:-*}"
        
        # 提供值
        result = build_command(template, {"class": "com.example.Service", "method": "doWork"})
        assert result == "trace com.example.Service doWork"
        
        # 使用默认值
        result = build_command(template, {"class": "com.example.Service"})
        assert result == "trace com.example.Service *"
    
    def test_step_output_reference(self):
        """步骤输出引用"""
        template = "watch ${step1.class} ${step1.method}"
        params = {}
        step_outputs = {
            "step1": {"class": "com.example.Service", "method": "slowMethod"}
        }
        
        result = build_command(template, params, step_outputs)
        assert result == "watch com.example.Service slowMethod"
    
    def test_nested_field_extraction(self):
        """嵌套字段提取"""
        template = "watch ${step1.data.class}"
        step_outputs = {
            "step1": {"data": {"class": "com.example.DeepClass"}}
        }
        
        result = build_command(template, {}, step_outputs)
        assert result == "watch com.example.DeepClass"
    
    def test_array_index_access(self):
        """数组索引访问"""
        template = "thread ${step1.threads.0.id}"
        step_outputs = {
            "step1": {"threads": [{"id": 123}, {"id": 456}]}
        }
        
        result = build_command(template, {}, step_outputs)
        assert result == "thread 123"
    
    def test_missing_step_output(self):
        """缺失步骤输出应该保留原样"""
        template = "watch ${step99.class}"
        
        result = build_command(template, {}, {})
        assert result == "watch ${step99.class}"
    
    def test_mixed_params_and_step_outputs(self):
        """混合参数和步骤输出"""
        template = "trace ${controller} ${step1.slow_method} -n ${count:-10}"
        params = {"controller": "OrderController", "count": 5}
        step_outputs = {"step1": {"slow_method": "createOrder"}}
        
        result = build_command(template, params, step_outputs)
        assert result == "trace OrderController createOrder -n 5"


class TestExtractNestedValue:
    """嵌套值提取测试"""
    
    def test_simple_dict(self):
        """简单字典访问"""
        data = {"cpu": 80, "memory": 512}
        assert extract_nested_value(data, "cpu") == "80"
    
    def test_nested_dict(self):
        """嵌套字典访问"""
        data = {"data": {"cpu": 80, "threads": {"total": 150}}}
        assert extract_nested_value(data, "data.cpu") == "80"
        assert extract_nested_value(data, "data.threads.total") == "150"
    
    def test_list_access(self):
        """列表索引访问"""
        data = {"threads": [{"id": 1, "name": "main"}, {"id": 2, "name": "worker"}]}
        assert extract_nested_value(data, "threads.0.id") == "1"
        assert extract_nested_value(data, "threads.1.name") == "worker"
    
    def test_deep_nested(self):
        """深层嵌套访问"""
        data = {"a": {"b": {"c": {"d": "deep_value"}}}}
        assert extract_nested_value(data, "a.b.c.d") == "deep_value"
    
    def test_invalid_path(self):
        """无效路径应该抛出异常"""
        data = {"cpu": 80}
        with pytest.raises(KeyError):
            extract_nested_value(data, "memory")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
