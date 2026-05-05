"""
统一 Arthas 命令执行器

设计目标：
1. 统一所有模块的 Arthas 命令执行入口（server.py / performance_diagnose.py / ai_chat.py / task_center.py）
2. 统一脱敏、审计、命令历史记录
3. 支持单步执行和批量执行（场景方案）
4. 支持命令分类和超时配置
5. 支持高危命令二次确认

使用方式：
    from backend.core.arthas_executor import ArthasCommandExecutor
    
    # 单步执行
    result = ArthasCommandExecutor.execute(connection, "dashboard -n 1")
    
    # 批量执行（场景方案）
    results = ArthasCommandExecutor.execute_batch(connection, [
        {"command": "trace com.example.Service *", "desc": "Trace 调用链"},
        {"command": "watch com.example.Service * '{params}'", "desc": "观察入参"},
    ])
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 命令分类与超时配置
# ═══════════════════════════════════════════════════════════════════════════════

# 命令超时配置（毫秒）
_COMMAND_TIMEOUT_CONFIG = {
    # 快捷查询类（5-15秒）
    'dashboard': 15000,
    'version': 5000,
    'sysprop': 5000,
    'sysenv': 5000,
    'vmoption': 5000,
    
    # 线程分析类（15-30秒）
    'thread': 30000,
    'jvm': 10000,
    
    # 方法诊断类（30-60秒）
    'trace': 60000,
    'watch': 60000,
    'stack': 30000,
    'monitor': 30000,
    'tt': 30000,
    
    # 类加载与反编译（30秒）
    'sc': 10000,
    'sm': 10000,
    'jad': 30000,
    'classloader': 10000,
    
    # 采样与Dump（60-120秒）
    'profiler': 120000,
    'heapdump': 120000,
    'jfr': 120000,
    'dump': 60000,
    
    # 日志控制（10秒）
    'logger': 10000,
    
    # 热更新（60秒）
    'redefine': 60000,
    'retransform': 60000,
    'mc': 60000,
    
    # OGNL（30秒）
    'ognl': 30000,
}

# 高危命令列表（需要二次确认）
_HIGH_RISK_COMMANDS = {
    'redefine',      # 类重新定义
    'retransform',   # 类热替换
    'heapdump',      # 堆Dump（可能影响性能）
    'profiler',      # 性能采样（有一定开销）
    'logger',        # 日志级别修改（影响线上日志）
    'vmoption',      # JVM参数修改
    'stop',          # 停止Arthas
}

# 只读命令列表（仅查询，无副作用）
_READ_ONLY_COMMANDS = {
    'dashboard', 'thread', 'jvm', 'sysprop', 'sysenv', 'vmoption',
    'sc', 'sm', 'jad', 'classloader', 'logger',
    'trace', 'watch', 'stack', 'monitor', 'tt',
    'ognl', 'version', 'session',
}


class ArthasCommandExecutor:
    """统一的 Arthas 命令执行器"""
    
    @staticmethod
    def execute(
        connection,
        command: str,
        timeout_ms: Optional[int] = None,
        skip_audit: bool = False,
        skip_history: bool = False,
        confirmed: bool = False,
    ) -> dict:
        """执行单条 Arthas 命令
        
        Args:
            connection: ArthasConnection 对象
            command: Arthas 命令，如 "dashboard -n 1"
            timeout_ms: 超时时间（毫秒），如果不指定则根据命令类型自动推断
            skip_audit: 是否跳过审计日志（默认 False）
            skip_history: 是否跳过命令历史记录（默认 False）
            confirmed: 高危命令是否已确认（默认 False）
        
        Returns:
            dict: Arthas HTTP API 响应，格式如：
                {
                    "state": "SUCCEEDED",
                    "body": {...},
                    "duration_ms": 1234,
                }
        
        Raises:
            ValueError: 高危命令未确认
            Exception: 执行失败
        """
        # 1. 命令解析
        cmd_name = ArthasCommandExecutor._parse_command_name(command)
        
        # 2. 高危命令检查
        if cmd_name in _HIGH_RISK_COMMANDS and not confirmed:
            return {
                'state': 'REQUIRE_CONFIRM',
                'message': f'此命令 ({cmd_name}) 为高危操作，需要二次确认',
                'command': command,
                'risk_level': 'high',
            }
        
        # 3. 超时配置
        if timeout_ms is None:
            timeout_ms = ArthasCommandExecutor._get_timeout(cmd_name)
        
        # 4. 执行命令
        start_time = time.time()
        try:
            client = connection.http_client
            result = client.exec_once(command, timeout_ms=timeout_ms)
            
            duration_ms = int((time.time() - start_time) * 1000)
            result['duration_ms'] = duration_ms
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            result = {
                'state': 'FAILED',
                'message': str(e),
                'duration_ms': duration_ms,
            }
            log.error("Arthas command failed: %s - %s", command, e, exc_info=True)
        
        # 5. 脱敏处理
        masked_output = ArthasCommandExecutor._mask_output(result)
        
        # 6. 记录命令历史
        if not skip_history:
            ArthasCommandExecutor._save_history(
                connection, command, masked_output, result.get('message', '')
            )
        
        # 7. 记录审计日志
        if not skip_audit:
            ArthasCommandExecutor._log_audit(
                connection, command, result, duration_ms
            )
        
        return result
    
    @staticmethod
    def execute_batch(
        connection,
        commands: List[Dict[str, str]],
        timeout_ms: Optional[int] = None,
        fail_fast: bool = True,
    ) -> List[Dict[str, Any]]:
        """批量执行 Arthas 命令（场景方案使用）
        
        Args:
            connection: ArthasConnection 对象
            commands: 命令列表，每项包含：
                - command: Arthas 命令
                - desc: 步骤描述（可选）
                - timeout_ms: 单步超时（可选，覆盖全局配置）
            timeout_ms: 全局超时时间（毫秒），如果单步未指定则使用此值
            fail_fast: 是否快速失败（某步失败后停止后续步骤）
        
        Returns:
            list: 每步执行结果，格式如：
                [
                    {
                        "step": 1,
                        "command": "trace ...",
                        "desc": "Trace 调用链",
                        "result": {...},
                        "success": True,
                    },
                    ...
                ]
        """
        results = []
        
        for idx, cmd_def in enumerate(commands, start=1):
            command = cmd_def.get('command', '')
            desc = cmd_def.get('desc', '')
            step_timeout = cmd_def.get('timeout_ms', timeout_ms)
            
            # 执行单步
            result = ArthasCommandExecutor.execute(
                connection,
                command,
                timeout_ms=step_timeout,
                skip_audit=True,  # 批量执行只在最后记录一次审计
                skip_history=True,  # 批量执行只记录一次历史
            )
            
            step_result = {
                'step': idx,
                'command': command,
                'desc': desc,
                'result': result,
                'success': result.get('state') in ('SUCCEEDED', 'succeeded'),
            }
            results.append(step_result)
            
            # 快速失败检查
            if fail_fast and not step_result['success']:
                log.warning("Batch execution failed at step %d: %s", idx, command)
                break
        
        # 批量执行的总体审计
        if len(results) > 1:
            ArthasCommandExecutor._log_batch_audit(connection, commands, results)
        
        return results
    
    @staticmethod
    def _parse_command_name(command: str) -> str:
        """解析命令名称（第一个单词）
        
        Args:
            command: 完整命令，如 "trace com.example.Service * -n 5"
        
        Returns:
            str: 命令名称，如 "trace"
        """
        parts = command.strip().split()
        return parts[0] if parts else ''
    
    @staticmethod
    def _get_timeout(cmd_name: str) -> int:
        """获取命令超时配置
        
        Args:
            cmd_name: 命令名称
        
        Returns:
            int: 超时时间（毫秒）
        """
        return _COMMAND_TIMEOUT_CONFIG.get(cmd_name, 30000)  # 默认 30 秒
    
    @staticmethod
    def _mask_output(result: dict) -> str:
        """脱敏输出内容
        
        Args:
            result: Arthas 命令执行结果
        
        Returns:
            str: 脱敏后的 JSON 字符串
        """
        try:
            from services.safety_service import SafetyService
            return SafetyService.mask_sensitive_output(json.dumps(result, ensure_ascii=False))
        except Exception as e:
            log.warning("Output masking failed: %s", e)
            return str(result)
    
    @staticmethod
    def _save_history(connection, command: str, output: str, error: str = ''):
        """保存命令历史到数据库
        
        Args:
            connection: ArthasConnection 对象
            command: 执行的命令
            output: 脱敏后的输出
            error: 错误信息
        """
        try:
            from models.db import db
            
            # 获取 user_id（如果 connection 有该属性）
            user_id = getattr(connection, 'user_id', None)
            
            db.insert('arthas_commands', {
                'connection_id': getattr(connection, 'connection_id', None) or f"{connection.target.cluster_name}/{connection.target.namespace}/{connection.target.pod_name}",
                'user_id': user_id,
                'command': command,
                'output': output[:10000],  # 限制输出长度
                'error': error[:1000],
            })
        except Exception as e:
            log.warning("Save command history failed: %s", e)
    
    @staticmethod
    def _log_audit(connection, command: str, result: dict, duration_ms: int):
        """记录审计日志
        
        Args:
            connection: ArthasConnection 对象
            command: 执行的命令
            result: 执行结果
            duration_ms: 执行耗时
        """
        try:
            from services.audit_service import AuditService
            from flask_login import current_user
            
            user_id = None
            try:
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                pass
            
            # 如果 connection 有 user_id，优先使用
            if not user_id:
                user_id = getattr(connection, 'user_id', None)
            
            AuditService.log_event(
                action='execute_arthas_command',
                resource_type='arthas_command',
                resource_id=getattr(connection, 'connection_id', None) or f"{connection.target.cluster_name}/{connection.target.namespace}/{connection.target.pod_name}",
                details=json.dumps({
                    'command': command,
                    'state': result.get('state', 'UNKNOWN'),
                    'duration_ms': duration_ms,
                    'cluster_name': getattr(connection, 'cluster_name', ''),
                    'namespace': getattr(connection, 'namespace', ''),
                    'pod_name': getattr(connection, 'pod_name', ''),
                }),
                user_id=user_id,
            )
        except Exception as e:
            log.warning("Audit log failed: %s", e)
    
    @staticmethod
    def _log_batch_audit(connection, commands: List[Dict], results: List[Dict]):
        """记录批量执行的审计日志
        
        Args:
            connection: ArthasConnection 对象
            commands: 命令列表
            results: 执行结果列表
        """
        try:
            from services.audit_service import AuditService
            from flask_login import current_user
            
            user_id = None
            try:
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
            except Exception:
                pass
            
            if not user_id:
                user_id = getattr(connection, 'user_id', None)
            
            # 汇总信息
            total_steps = len(results)
            success_steps = sum(1 for r in results if r.get('success'))
            total_duration = sum(r.get('result', {}).get('duration_ms', 0) for r in results)
            
            AuditService.log_event(
                action='execute_arthas_batch',
                resource_type='diagnosis_scenario',
                resource_id=connection.id,
                details=json.dumps({
                    'total_steps': total_steps,
                    'success_steps': success_steps,
                    'failed_steps': total_steps - success_steps,
                    'total_duration_ms': total_duration,
                    'commands': [c.get('command', '') for c in commands],
                    'cluster_name': getattr(connection, 'cluster_name', ''),
                    'namespace': getattr(connection, 'namespace', ''),
                    'pod_name': getattr(connection, 'pod_name', ''),
                }),
                user_id=user_id,
            )
        except Exception as e:
            log.warning("Batch audit log failed: %s", e)
    
    @staticmethod
    def is_read_only(command: str) -> bool:
        """判断命令是否为只读（无副作用）
        
        Args:
            command: Arthas 命令
        
        Returns:
            bool: 是否只读
        """
        cmd_name = ArthasCommandExecutor._parse_command_name(command)
        return cmd_name in _READ_ONLY_COMMANDS
    
    @staticmethod
    def is_high_risk(command: str) -> bool:
        """判断命令是否为高危命令
        
        Args:
            command: Arthas 命令
        
        Returns:
            bool: 是否高危
        """
        cmd_name = ArthasCommandExecutor._parse_command_name(command)
        return cmd_name in _HIGH_RISK_COMMANDS
    
    @staticmethod
    def get_command_info(command: str) -> dict:
        """获取命令信息（分类、超时、风险等级）
        
        Args:
            command: Arthas 命令
        
        Returns:
            dict: 命令信息
        """
        cmd_name = ArthasCommandExecutor._parse_command_name(command)
        
        return {
            'name': cmd_name,
            'timeout_ms': ArthasCommandExecutor._get_timeout(cmd_name),
            'is_read_only': cmd_name in _READ_ONLY_COMMANDS,
            'is_high_risk': cmd_name in _HIGH_RISK_COMMANDS,
            'risk_level': 'high' if cmd_name in _HIGH_RISK_COMMANDS else 'low',
        }
