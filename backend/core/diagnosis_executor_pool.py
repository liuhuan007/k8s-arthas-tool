#!/usr/bin/env python3
"""诊断执行器线程池（并发控制）

架构设计：
- 全局线程池：限制并发执行数（默认 10）
- Pod 级别锁：防止同一 Pod 被并发诊断
- 超时控制：单步骤 60s 超时
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Dict, Optional

from models.db import db


class ConcurrencyError(Exception):
    """并发冲突异常"""
    pass


class DiagnosisExecutorPool:
    """诊断执行器线程池（并发控制）"""
    
    def __init__(self, max_workers: int = 10, step_timeout: int = 60):
        """
        Args:
            max_workers: 全局最大并发数
            step_timeout: 单步骤超时时间（秒）
        """
        self.max_workers = max_workers
        self.step_timeout = step_timeout
        
        # 全局线程池
        self.global_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix='diagnosis-'
        )
        
        # Pod 级别锁（防止同一 Pod 被并发诊断）
        self.pod_locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        
        # 活跃执行追踪
        self.active_executions: Dict[str, Dict[str, Any]] = {}
        # 取消信号：execution_id → threading.Event
        self.cancel_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
    
    def submit_diagnosis(
        self,
        connection_id: str,
        capability_id: int,
        params: dict,
        user_id: int,
        execution_id: str
    ) -> Dict[str, Any]:
        """
        提交诊断任务（带并发控制）
        
        返回 Pod 锁和清理函数，由调用方在执行完成后释放
        
        Args:
            connection_id: Arthas 连接 ID
            capability_id: 诊断能力 ID
            params: 诊断参数
            user_id: 用户 ID
            execution_id: 执行 ID
            
        Returns:
            {'ok': True, 'pod_lock': Lock, 'cleanup': Callable} 或 {'ok': False, 'error': str}
            
        Raises:
            ConcurrencyError: 并发冲突
        """
        # 1. 获取连接信息
        connection = db.fetch_one(
            'SELECT * FROM connections WHERE id = ?',
            (connection_id,)
        )
        
        if not connection:
            raise ValueError('连接不存在')
        
        # 2. 构建 Pod key
        pod_key = f"{connection['cluster_name']}/{connection['namespace']}/{connection['pod_name']}"
        
        # 3. 检查全局并发数
        with self._lock:
            active_count = len([
                e for e in self.active_executions.values()
                if e['status'] == 'running'
            ])
            
            if active_count >= self.max_workers:
                raise ConcurrencyError(
                    f'系统繁忙（{active_count}/{self.max_workers} 个诊断正在执行），请稍后重试'
                )
        
        # 4. 获取 Pod 级别锁
        pod_lock = self.pod_locks[pod_key]
        
        if not pod_lock.acquire(blocking=False):
            raise ConcurrencyError(
                f'Pod {pod_key} 正在被诊断，请稍后重试'
            )
        
        # 5. 注册活跃执行 + 创建取消信号
        cancel_event = threading.Event()
        with self._lock:
            self.active_executions[execution_id] = {
                'execution_id': execution_id,
                'connection_id': connection_id,
                'capability_id': capability_id,
                'pod_key': pod_key,
                'status': 'running',
                'started_at': time.time(),
                'user_id': user_id,
            }
            self.cancel_events[execution_id] = cancel_event
        
        # 6. 返回锁、取消信号和清理函数
        def cleanup(status='completed', error=None):
            """执行完成后清理"""
            with self._lock:
                if execution_id in self.active_executions:
                    self.active_executions[execution_id]['status'] = status
                    if error:
                        self.active_executions[execution_id]['error'] = error
                    self.active_executions[execution_id]['finished_at'] = time.time()

            # 释放 Pod 锁
            pod_lock.release()

            # 3 秒后从活跃列表移除
            def delayed_cleanup():
                time.sleep(3)
                with self._lock:
                    self.active_executions.pop(execution_id, None)
                    self.cancel_events.pop(execution_id, None)

            threading.Thread(target=delayed_cleanup, daemon=True).start()

        return {
            'ok': True,
            'execution_id': execution_id,
            'pod_lock': pod_lock,
            'cancel_event': cancel_event,
            'cleanup': cleanup,
        }
    
    def _execute_with_guard(
        self,
        execution_id: str,
        connection_id: str,
        capability_id: int,
        params: dict,
        user_id: int,
        pod_lock: threading.Lock,
        pod_key: str
    ) -> Dict[str, Any]:
        """
        带保护的诊断执行
        
        确保无论成功或失败，都会释放 Pod 锁并更新执行状态
        """
        # 实际执行逻辑（由 API 层处理）
        # 这里只负责状态管理，实际执行在 API 层
        # 因为需要访问 Flask 上下文
        
        # 返回执行 ID，实际执行由调用方处理
        return {
            'execution_id': execution_id,
            'status': 'submitted',
        }
    
    def is_cancelled(self, execution_id: str) -> bool:
        """检查执行是否已取消（内存信号，比 DB 查询快）"""
        cancel_event = self.cancel_events.get(execution_id)
        if cancel_event and cancel_event.is_set():
            return True
        with self._lock:
            execution = self.active_executions.get(execution_id)
            return bool(execution and execution.get('status') == 'cancelled')

    def get_active_count(self) -> int:
        """获取活跃执行数"""
        with self._lock:
            return len([
                e for e in self.active_executions.values()
                if e['status'] == 'running'
            ])
    
    def get_active_executions(self) -> list:
        """获取活跃执行列表"""
        with self._lock:
            return list(self.active_executions.values())
    
    def cancel_execution(self, execution_id: str) -> bool:
        """
        取消执行（协作式）

        设置取消信号，场景方案每步前检查此信号。
        """
        with self._lock:
            execution = self.active_executions.get(execution_id)
            if execution and execution['status'] == 'running':
                execution['status'] = 'cancelled'
                # 设置取消信号，通知正在执行的场景方案停止后续步骤
                cancel_event = self.cancel_events.get(execution_id)
                if cancel_event:
                    cancel_event.set()
                return True
        return False
    
    def shutdown(self, wait: bool = True):
        """关闭线程池"""
        self.global_pool.shutdown(wait=wait)


# 全局单例
_diagnosis_pool: Optional[DiagnosisExecutorPool] = None


def get_diagnosis_executor_pool() -> DiagnosisExecutorPool:
    """获取全局诊断执行器线程池（单例）"""
    global _diagnosis_pool
    
    if _diagnosis_pool is None:
        _diagnosis_pool = DiagnosisExecutorPool(
            max_workers=10,
            step_timeout=60
        )
    
    return _diagnosis_pool
