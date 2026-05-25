"""
统一 Arthas 命令执行器

设计目标：
1. 统一所有模块的 Arthas 命令执行入口（server.py / performance_diagnose.py / ai_chat.py / task_center.py）
2. 统一脱敏、审计、命令历史记录
3. 支持单步执行和批量执行（场景方案）
4. 支持命令分类和超时配置
5. 支持高危命令二次确认
6. 支持异步执行、状态轮询和执行取消

使用方式：
    from backend.core.arthas_executor import ArthasCommandExecutor

    # 同步执行
    result = ArthasCommandExecutor.execute(connection, "dashboard -n 1")

    # 异步执行
    exec_id = ArthasCommandExecutor.execute_async(connection, "dashboard -n 1")
    status = ArthasCommandExecutor.poll_execution(exec_id)

    # 取消执行
    ArthasCommandExecutor.cancel_execution(exec_id)

    # 批量执行（场景方案）
    results = ArthasCommandExecutor.execute_batch(connection, [
        {"command": "trace com.example.Service *", "desc": "Trace 调用链"},
        {"command": "watch com.example.Service * '{params}'", "desc": "观察入参"},
    ])
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 执行状态枚举
# ═══════════════════════════════════════════════════════════════════════════════

class ExecutionStatus(Enum):
    """异步执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    REQUIRE_CONFIRM = "require_confirm"


# ═══════════════════════════════════════════════════════════════════════════════
# 执行记录存储（内存，支持异步轮询）
# ═══════════════════════════════════════════════════════════════════════════════

class ExecutionRecord:
    """单次异步执行记录"""

    def __init__(
        self,
        execution_id: str,
        connection_id: str,
        command: str,
        user_id: Optional[int] = None,
    ):
        self.execution_id: str = execution_id
        self.connection_id: str = connection_id
        self.command: str = command
        self.user_id: Optional[int] = user_id
        self.status: ExecutionStatus = ExecutionStatus.PENDING
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at: float = time.time()
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self.session_id: Optional[str] = None
        self.consumer_id: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def duration_ms(self) -> Optional[int]:
        """执行耗时（毫秒）"""
        if self.started_at is None:
            return None
        end = self.finished_at or time.time()
        return int((end - self.started_at) * 1000)

    @property
    def elapsed_ms(self) -> int:
        """从创建到现在的总耗时（毫秒）"""
        return int((time.time() - self.created_at) * 1000)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'execution_id': self.execution_id,
            'connection_id': self.connection_id,
            'command': self.command,
            'user_id': self.user_id,
            'status': self.status.value,
            'result': self.result,
            'error': self.error,
            'created_at': datetime.fromtimestamp(self.created_at).isoformat(),
            'started_at': datetime.fromtimestamp(self.started_at).isoformat() if self.started_at else None,
            'finished_at': datetime.fromtimestamp(self.finished_at).isoformat() if self.finished_at else None,
            'duration_ms': self.duration_ms,
            'elapsed_ms': self.elapsed_ms,
        }

    def mark_running(self, session_id: Optional[str] = None, consumer_id: Optional[str] = None):
        """标记为运行中"""
        with self._lock:
            self.status = ExecutionStatus.RUNNING
            self.started_at = time.time()
            if session_id:
                self.session_id = session_id
            if consumer_id:
                self.consumer_id = consumer_id

    def mark_succeeded(self, result: Dict[str, Any]):
        """标记为成功"""
        with self._lock:
            self.status = ExecutionStatus.SUCCEEDED
            self.result = result
            self.finished_at = time.time()

    def mark_failed(self, error: str, result: Optional[Dict[str, Any]] = None):
        """标记为失败"""
        with self._lock:
            self.status = ExecutionStatus.FAILED
            self.error = error
            if result:
                self.result = result
            self.finished_at = time.time()

    def mark_cancelled(self):
        """标记为取消"""
        with self._lock:
            self.status = ExecutionStatus.CANCELLED
            self.finished_at = time.time()

    def mark_timeout(self):
        """标记为超时"""
        with self._lock:
            self.status = ExecutionStatus.TIMEOUT
            self.finished_at = time.time()


# 全局执行记录存储
_execution_store: Dict[str, ExecutionRecord] = {}
_execution_store_lock = threading.Lock()

# 执行记录保留时间（秒）：24 小时
_EXECUTION_RECORD_TTL = 24 * 3600


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
    # ✅ 去掉 redefine,热修复场景需要直接执行
    # 'redefine',      # 类重新定义
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
        log.info("[ArthasExecutor] ▶ 执行命令: %s (timeout=%dms)", command, timeout_ms)
        try:
            client = connection.http_client
            if not client:
                raise ValueError("http_client is None")
            result = client.exec_once(command, timeout_ms=timeout_ms)
            
            duration_ms = int((time.time() - start_time) * 1000)
            result['duration_ms'] = duration_ms
            
            log.info("[ArthasExecutor]  执行完成: state=%s, duration=%dms", 
                    result.get('state'), duration_ms)
            
            # ✅ 打印完整 result (格式化输出)
            import json
            try:
                log.info("[ArthasExecutor] 📦 完整返回:\n%s", 
                        json.dumps(result, ensure_ascii=False, indent=2)[:2000])
            except Exception:
                log.info("[ArthasExecutor] 📦 完整返回: %s", str(result)[:2000])
            
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

    # ═════════════════════════════════════════════════════════════════════════
    # 异步执行引擎（状态轮询 + 取消）
    # ═════════════════════════════════════════════════════════════════════════

    @staticmethod
    def execute_async(
        connection,
        command: str,
        timeout_ms: Optional[int] = None,
        user_id: Optional[int] = None,
        confirmed: bool = False,
    ) -> str:
        """异步执行单条 Arthas 命令（通过 Arthas Session API）

        流程：
        1. 创建本地执行记录
        2. 初始化 Arthas Session
        3. 提交异步命令
        4. 返回执行 ID，调用方可通过 poll_execution 查询

        Args:
            connection: ArthasConnection 对象
            command: Arthas 命令
            timeout_ms: 超时时间（毫秒）
            user_id: 用户 ID（用于审计）
            confirmed: 高危命令是否已确认

        Returns:
            str: 执行 ID（execution_id）
        """
        # 1. 命令预检
        cmd_name = ArthasCommandExecutor._parse_command_name(command)
        if cmd_name in _HIGH_RISK_COMMANDS and not confirmed:
            exec_id = f"exec-{uuid.uuid4().hex[:12]}"
            record = ExecutionRecord(
                execution_id=exec_id,
                connection_id=getattr(connection, 'connection_id', '') or '',
                command=command,
                user_id=user_id,
            )
            record.status = ExecutionStatus.REQUIRE_CONFIRM
            record.error = f'此命令 ({cmd_name}) 为高危操作，需要二次确认'
            record.result = {
                'state': 'REQUIRE_CONFIRM',
                'message': record.error,
                'command': command,
                'risk_level': 'high',
            }
            record.finished_at = time.time()
            _store_execution(record)
            return exec_id

        # 2. 创建执行记录
        exec_id = f"exec-{uuid.uuid4().hex[:12]}"
        record = ExecutionRecord(
            execution_id=exec_id,
            connection_id=getattr(connection, 'connection_id', '') or '',
            command=command,
            user_id=user_id,
        )
        _store_execution(record)

        # 3. 获取 HTTP 客户端
        client = getattr(connection, 'http_client', None)
        if not client:
            record.mark_failed("http_client is None，连接可能未就绪")
            return exec_id

        # 4. 在后台线程执行（初始化 session + async_exec）
        def _run_async():
            try:
                # 初始化 session
                session_resp = client.init_session()
                session_id = session_resp.get('sessionId', '')
                if not session_id:
                    record.mark_failed("无法初始化 Arthas Session", session_resp)
                    return

                consumer_id = f"consumer-{uuid.uuid4().hex[:8]}"
                record.mark_running(session_id=session_id, consumer_id=consumer_id)
                log.info("[ArthasExecutor] async exec started: session=%s, cmd=%s",
                         session_id, command)

                # 提交异步命令
                async_resp = client.exec_async(session_id, command)
                if async_resp.get('state') in ('FAILED', 'failed'):
                    record.mark_failed(
                        async_resp.get('message', '异步命令提交失败'),
                        async_resp,
                    )
                    return

                log.info("[ArthasExecutor] async command submitted: %s", command)

            except Exception as e:
                record.mark_failed(str(e))
                log.error("[ArthasExecutor] async exec error: %s", e, exc_info=True)

        thread = threading.Thread(target=_run_async, daemon=True, name=f"async-{exec_id}")
        thread.start()

        return exec_id

    @staticmethod
    def poll_execution(
        execution_id: str,
        connection=None,
        fetch_results: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """轮询异步执行状态

        如果执行仍在运行，且提供了 connection，则自动通过 Arthas HTTP API
        拉取最新的命令输出。

        Args:
            execution_id: 执行 ID
            connection: ArthasConnection（可选，用于拉取实时结果）
            fetch_results: 是否主动拉取结果（默认 True）

        Returns:
            dict: 执行状态快照（ExecutionRecord.to_dict()）
        """
        record = _get_execution(execution_id)
        if not record:
            return None

        # 如果正在运行且有连接，尝试拉取结果
        if (record.status == ExecutionStatus.RUNNING
                and connection is not None
                and fetch_results
                and record.session_id
                and record.consumer_id):
            try:
                client = getattr(connection, 'http_client', None)
                if client:
                    pull_resp = client.pull_results(record.session_id, record.consumer_id)

                    # 检查是否有新结果
                    state = pull_resp.get('state', '')
                    if state in ('SUCCEEDED', 'succeeded'):
                        # 命令完成
                        duration = record.duration_ms or 0
                        result = {
                            'state': 'SUCCEEDED',
                            'body': pull_resp.get('body', {}),
                            'message': pull_resp.get('message', ''),
                            'duration_ms': duration,
                        }
                        record.mark_succeeded(result)
                        # 关闭 session
                        try:
                            client.close_session(record.session_id)
                        except Exception:
                            pass
                    elif state in ('FAILED', 'failed'):
                        result = {
                            'state': 'FAILED',
                            'message': pull_resp.get('message', '命令执行失败'),
                        }
                        record.mark_failed(pull_resp.get('message', '命令执行失败'), result)
                        try:
                            client.close_session(record.session_id)
                        except Exception:
                            pass
                    else:
                        # 命令仍在执行中，更新中间结果
                        record.result = pull_resp

            except Exception as e:
                log.debug("[ArthasExecutor] poll results error: %s", e)

        # 检查超时
        if record.status == ExecutionStatus.RUNNING:
            cmd_name = ArthasCommandExecutor._parse_command_name(record.command)
            timeout = ArthasCommandExecutor._get_timeout(cmd_name)
            if record.elapsed_ms > timeout + 10000:  # 额外 10 秒宽限
                record.mark_timeout()
                try:
                    client = getattr(connection, 'http_client', None)
                    if client and record.session_id:
                        client.interrupt_job(record.session_id)
                        client.close_session(record.session_id)
                except Exception:
                    pass

        return record.to_dict()

    @staticmethod
    def cancel_execution(
        execution_id: str,
        connection=None,
    ) -> bool:
        """取消异步执行

        通过 Arthas HTTP API 中断正在运行的 Job 并关闭 Session。

        Args:
            execution_id: 执行 ID
            connection: ArthasConnection（可选，用于中断 Arthas Job）

        Returns:
            bool: 是否成功取消
        """
        record = _get_execution(execution_id)
        if not record:
            return False

        if record.status not in (ExecutionStatus.PENDING, ExecutionStatus.RUNNING):
            # 已经结束的执行不可取消
            return False

        # 尝试中断 Arthas 端的 Job
        if connection is not None and record.session_id:
            try:
                client = getattr(connection, 'http_client', None)
                if client:
                    client.interrupt_job(record.session_id)
                    client.close_session(record.session_id)
            except Exception as e:
                log.warning("[ArthasExecutor] interrupt job failed: %s", e)

        record.mark_cancelled()
        log.info("[ArthasExecutor] execution cancelled: %s", execution_id)
        return True

    @staticmethod
    def get_execution(execution_id: str) -> Optional[Dict[str, Any]]:
        """获取执行记录（纯查询，不触发拉取）

        Args:
            execution_id: 执行 ID

        Returns:
            dict 或 None
        """
        record = _get_execution(execution_id)
        return record.to_dict() if record else None

    @staticmethod
    def cleanup_expired_executions(max_age_seconds: Optional[int] = None):
        """清理过期的执行记录（内存管理）

        Args:
            max_age_seconds: 最大保留时间（秒），默认 24 小时
        """
        ttl = max_age_seconds or _EXECUTION_RECORD_TTL
        now = time.time()
        expired_ids = []

        with _execution_store_lock:
            for eid, record in _execution_store.items():
                if record.status in (ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED,
                                     ExecutionStatus.CANCELLED, ExecutionStatus.TIMEOUT):
                    if record.finished_at and (now - record.finished_at) > ttl:
                        expired_ids.append(eid)

            for eid in expired_ids:
                del _execution_store[eid]

        if expired_ids:
            log.info("[ArthasExecutor] cleaned %d expired execution records", len(expired_ids))


# ═══════════════════════════════════════════════════════════════════════════════
# 执行记录存储辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _store_execution(record: ExecutionRecord):
    """存储执行记录"""
    with _execution_store_lock:
        _execution_store[record.execution_id] = record


def _get_execution(execution_id: str) -> Optional[ExecutionRecord]:
    """获取执行记录"""
    with _execution_store_lock:
        return _execution_store.get(execution_id)


def get_all_executions() -> List[Dict[str, Any]]:
    """获取所有执行记录（用于调试/监控）"""
    with _execution_store_lock:
        return [r.to_dict() for r in _execution_store.values()]


# ═══════════════════════════════════════════════════════════════════════════════
# 命令安全检查
# ═══════════════════════════════════════════════════════════════════════════════

def _is_safe_command(command: str) -> bool:
    """命令安全检查 - 防止命令注入

    检查：
    1. 不包含 Shell 元字符（; | & ` $() 等）
    2. 不包含文件系统敏感路径
    3. 命令长度在合理范围内

    Args:
        command: 待检查的命令

    Returns:
        bool: 是否安全
    """
    if not command or not command.strip():
        return False

    # 命令长度限制
    if len(command) > 1000:
        return False

    # 危险 Shell 字符检查（Arthas 命令不应包含这些）
    dangerous_chars = [';', '|', '&', '`', '$(', '>', '<']
    cmd_lower = command.lower()
    for ch in dangerous_chars:
        if ch in cmd_lower:
            return False

    # 检查换行符和回车符（命令注入常见手段）
    if '\n' in command or '\r' in command:
        return False

    # ${} 格式特殊处理：只允许 Arthas 参数替换 ${param} 和 ${param:-default}
    import re
    remaining = cmd_lower
    while '${' in remaining:
        start = remaining.index('${')
        end = remaining.find('}', start)
        if end == -1:
            return False  # 未闭合的 ${
        # 检查占位符名称是否合法（字母数字下划线）
        placeholder = remaining[start + 2:end]
        if not re.match(r'^[\w.:-]+$', placeholder):
            return False
        remaining = remaining[end + 1:]

    return True
