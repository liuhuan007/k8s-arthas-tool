#!/usr/bin/env python3
"""连接感知执行器（连接生命周期管理）

架构设计：
- 连接监听器：诊断执行过程中监听连接状态
- 连接断开回调：自动失败并清理场景方案已执行步骤
- 前端连接丢失对话框：友好的用户提示
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from models.db import db


class ConnectionListener:
    """连接监听器"""
    
    def __init__(self, connection_id: str, callback: Callable):
        self.connection_id = connection_id
        self.callback = callback
        self.is_active = True


class ConnectionManager:
    """连接管理器（全局单例）"""
    
    _listeners: Dict[str, list] = {}
    
    @classmethod
    def register_listener(cls, connection_id: str, callback: Callable) -> str:
        """注册连接监听器"""
        listener_id = str(uuid.uuid4())
        listener = ConnectionListener(connection_id, callback)
        
        if connection_id not in cls._listeners:
            cls._listeners[connection_id] = []
        
        cls._listeners[connection_id].append(listener)
        
        return listener_id
    
    @classmethod
    def unregister_listener(cls, connection_id: str, listener_id: str) -> bool:
        """移除连接监听器"""
        if connection_id in cls._listeners:
            cls._listeners[connection_id] = [
                l for l in cls._listeners[connection_id]
                if id(l) != listener_id  # 简化处理
            ]
            return True
        return False
    
    @classmethod
    def notify_connection_lost(cls, connection_id: str):
        """通知连接已断开"""
        if connection_id in cls._listeners:
            for listener in cls._listeners[connection_id]:
                if listener.is_active:
                    try:
                        listener.callback()
                    except Exception as e:
                        print(f"连接监听器回调失败: {e}")


class ConnectionAwareExecutor:
    """连接感知执行器"""
    
    def execute_with_connection_guard(
        self,
        connection_id: str,
        capability_id: int,
        params: dict,
        user_id: int,
        execution_func: Callable,
        execution_id: str = None
    ) -> Dict[str, Any]:
        """
        带连接保护的诊断执行
        
        Args:
            connection_id: Arthas 连接 ID
            capability_id: 诊断能力 ID
            params: 诊断参数
            user_id: 用户 ID
            execution_func: 实际执行函数
            execution_id: 执行 ID
            
        Returns:
            执行结果
        """
        if not execution_id:
            execution_id = str(uuid.uuid4())
        
        # 1. 注册连接监听器
        def on_connection_lost():
            """连接断开回调"""
            db.update('task_logs', {
                'status': 'failed',
                'error_message': 'Arthas 连接已断开',
                'finished_at': datetime.now(),
            }, {'id': execution_id})
            
            # 获取能力类型
            capability = db.fetch_one(
                'SELECT type FROM diagnosis_capabilities WHERE id = ?',
                (capability_id,)
            )
            
            # 如果是场景方案，清理已执行的命令
            if capability and capability['type'] == 'scenario':
                self._rollback_scenario_steps(execution_id)
        
        listener_id = ConnectionManager.register_listener(
            connection_id,
            on_connection_lost
        )
        
        try:
            # 2. 执行诊断
            result = execution_func()
            return result
            
        except Exception as e:
            # 检查是否是连接断开导致的错误
            error_msg = str(e)
            if '连接' in error_msg or 'connection' in error_msg.lower():
                # 触发连接断开回调
                on_connection_lost()
                raise ConnectionError('Arthas 连接已断开，请重新建立连接后重试') from e
            raise
            
        finally:
            # 3. 移除监听器
            ConnectionManager.unregister_listener(connection_id, listener_id)
    
    def _rollback_scenario_steps(self, execution_id: str):
        """
        回滚场景方案已执行的步骤
        
        注意：Arthas 命令无法回滚，这里仅记录日志
        """
        # 查询已执行的步骤
        steps = db.fetch_all(
            'SELECT step_number, command, status FROM task_step_logs WHERE execution_id = ?',
            (execution_id,)
        )
        
        # 记录回滚日志
        for step in steps:
            if step['status'] == 'completed':
                print(
                    f"[场景方案回滚] 步骤 {step['step_number']} 已执行: "
                    f"{step['command']}（无法回滚）"
                )


# 全局单例
_connection_aware_executor: Optional[ConnectionAwareExecutor] = None


def get_connection_aware_executor() -> ConnectionAwareExecutor:
    """获取全局连接感知执行器（单例）"""
    global _connection_aware_executor
    
    if _connection_aware_executor is None:
        _connection_aware_executor = ConnectionAwareExecutor()
    
    return _connection_aware_executor
