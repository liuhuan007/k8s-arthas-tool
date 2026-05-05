#!/usr/bin/env python3
"""命令构建器 - 支持跨步数据传递"""
import re
from typing import Any, Dict, Optional


def build_command(command_template: str, params: Dict[str, Any], step_outputs: Optional[Dict[str, Any]] = None) -> str:
    """构建 Arthas 命令（支持跨步数据传递）
    
    支持的语法：
    - ${param}           → 用户参数
    - ${param:-default}  → 带默认值替换
    - ${step1.output}    → 引用步骤 1 完整输出
    - ${step1.thread_id} → 引用步骤 1 输出的特定字段（支持嵌套：step1.data.cpu_usage）
    
    Args:
        command_template: 命令模板
        params: 用户参数
        step_outputs: 步骤输出字典，格式如 {"step1": {...}, "step2": {...}}
        
    Returns:
        str: 构建后的命令
    """
    command = command_template
    
    # 1. 替换用户参数
    for key, value in params.items():
        command = command.replace(f'${{{key}}}', str(value))
    
    # 2. 处理默认值 ${param:-default}
    pattern = r'\$\{(\w+):-([^}]*)\}'
    def replace_default(match):
        key = match.group(1)
        default = match.group(2)
        return str(params.get(key, default))
    
    command = re.sub(pattern, replace_default, command)
    
    # 3. 引用步骤输出（跨步数据传递）
    if step_outputs:
        pattern = r'\$\{step(\d+)\.([\w.]+)\}'
        def replace_step_output(match):
            step_order = match.group(1)
            field_path = match.group(2)
            
            step_key = f"step{step_order}"
            if step_key not in step_outputs:
                return match.group(0)  # 保留原样
            
            output = step_outputs[step_key]
            
            # 使用原生 Python 提取字段（支持嵌套）
            try:
                return extract_nested_value(output, field_path)
            except Exception:
                return match.group(0)  # 保留原样
        
        command = re.sub(pattern, replace_step_output, command)
    
    return command


def extract_nested_value(data: Any, field_path: str) -> str:
    """从嵌套字典/列表中提取值
    
    示例：
    - extract_nested_value({'data': {'cpu': 80}}, 'data.cpu') → 80
    - extract_nested_value({'threads': [{'id': 1}]}, 'threads.0.id') → 1
    
    Args:
        data: 数据源（字典或列表）
        field_path: 字段路径，用 . 分隔
        
    Returns:
        str: 提取的值（转为字符串）
    """
    keys = field_path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict):
            current = current[key]
        elif isinstance(current, list):
            current = current[int(key)]
        else:
            raise KeyError(f"Cannot access '{key}' on {type(current)}")
    
    return str(current)
