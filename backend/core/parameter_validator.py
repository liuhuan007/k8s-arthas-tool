#!/usr/bin/env python3
"""参数校验引擎 - 支持 6 种校验规则"""
import json
import re
from typing import Any, Dict, List, Optional


class ParameterValidator:
    """参数校验引擎"""
    
    @staticmethod
    def validate(schema_str: str, params: Dict[str, Any]) -> Optional[str]:
        """校验参数
        
        Args:
            schema_str: JSON 格式的参数定义字符串
            params: 用户传入的参数
            
        Returns:
            Optional[str]: 校验失败返回错误信息，成功返回 None
        """
        if not schema_str or schema_str == '{}':
            return None
        
        try:
            schema = json.loads(schema_str)
        except json.JSONDecodeError:
            return "参数定义格式错误"
        
        if not isinstance(schema, list):
            return None
        
        for field in schema:
            field_name = field.get('name')
            if not field_name:
                continue
            
            value = params.get(field_name)
            label = field.get('label', field_name)
            
            # 1. 必填项检查
            if field.get('required') and field_name not in params:
                return f"缺少必填参数: {label}"
            
            # 如果值为 None 且非必填，跳过后续校验
            if value is None:
                continue
            
            # 2. 类型检查
            field_type = field.get('type', 'text')
            type_error = ParameterValidator._check_type(field_name, label, value, field_type)
            if type_error:
                return type_error
            
            # 3. 长度限制
            length_error = ParameterValidator._check_length(field_name, label, value, field)
            if length_error:
                return length_error
            
            # 4. 正则校验
            pattern_error = ParameterValidator._check_pattern(field_name, label, value, field)
            if pattern_error:
                return pattern_error
            
            # 5. 枚举值校验
            enum_error = ParameterValidator._check_enum(field_name, label, value, field)
            if enum_error:
                return enum_error
            
            # 6. 数值范围
            range_error = ParameterValidator._check_range(field_name, label, value, field)
            if range_error:
                return range_error
        
        return None
    
    @staticmethod
    def _check_type(field_name: str, label: str, value: Any, field_type: str) -> Optional[str]:
        """类型检查"""
        if field_type == 'number':
            if not isinstance(value, (int, float)):
                try:
                    float(value)
                except (ValueError, TypeError):
                    return f"参数 {label} 必须为数字"
        elif field_type == 'boolean':
            if not isinstance(value, bool) and value not in ('true', 'false', '1', '0'):
                return f"参数 {label} 必须为布尔值"
        return None
    
    @staticmethod
    def _check_length(field_name: str, label: str, value: Any, field: Dict) -> Optional[str]:
        """长度限制检查"""
        if not isinstance(value, str):
            return None
        
        min_length = field.get('min_length')
        max_length = field.get('max_length')
        
        if min_length is not None and len(value) < min_length:
            return f"参数 {label} 长度不能少于 {min_length} 个字符"
        
        if max_length is not None and len(value) > max_length:
            return f"参数 {label} 长度不能超过 {max_length} 个字符"
        
        return None
    
    @staticmethod
    def _check_pattern(field_name: str, label: str, value: Any, field: Dict) -> Optional[str]:
        """正则校验"""
        if not isinstance(value, str):
            return None
        
        pattern = field.get('pattern')
        if pattern:
            try:
                if not re.match(pattern, value):
                    return f"参数 {label} 格式不正确"
            except re.error:
                return f"参数 {label} 的正则表达式配置错误"
        
        return None
    
    @staticmethod
    def _check_enum(field_name: str, label: str, value: Any, field: Dict) -> Optional[str]:
        """枚举值校验"""
        options = field.get('options')
        if options and isinstance(options, list):
            # options 可能是 [{'value': 'x', 'label': 'X'}] 或 ['x', 'y']
            valid_values = []
            for opt in options:
                if isinstance(opt, dict):
                    valid_values.append(opt.get('value'))
                else:
                    valid_values.append(opt)
            
            if value not in valid_values:
                return f"参数 {label} 的值不在允许范围内"
        
        return None
    
    @staticmethod
    def _check_range(field_name: str, label: str, value: Any, field: Dict) -> Optional[str]:
        """数值范围检查"""
        if not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (ValueError, TypeError):
                return None
        
        min_value = field.get('min')
        max_value = field.get('max')
        
        if min_value is not None and value < min_value:
            return f"参数 {label} 不能小于 {min_value}"
        
        if max_value is not None and value > max_value:
            return f"参数 {label} 不能大于 {max_value}"
        
        return None
