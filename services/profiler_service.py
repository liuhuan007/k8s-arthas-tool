#!/usr/bin/env python3
"""Profiler Service 服务层 - 封装 backend/core/profiler.py

本模块提供 Profiler 服务层，负责：
- 封装 backend/core/profiler.py 的 ProfilerWorkflow 类
- 提供统一的服务层接口
- 管理 profiler_tasks 数据库表

Author: Kou (software-engineer)
Created: 2025-05-25
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from models.db import get_db
from backend.core.profiler import ProfilerWorkflow

log = logging.getLogger(__name__)


class ProfilerService:
    """Profiler 服务层 - 封装 Core 层逻辑"""

    def __init__(self):
        """初始化 Profiler 服务"""
        self.db = get_db()

    def create_task(self, connection_id: str, task_type: str = 'cpu',
                   event: str = 'cpu', duration: int = 60,
                   fmt: str = 'html', user_id: int = None) -> str:
        """创建 Profiler 任务
        
        Args:
            connection_id: 连接ID (格式: cluster/namespace/pod)
            task_type: 任务类型 (cpu/jfr/threaddump/heapdump)
            event: 事件类型 (cpu/jfr/threaddump/heapdump)
            duration: 采样时长（秒）
            fmt: 输出格式 (html/jfr/txt/bin)
            user_id: 用户ID
            
        Returns:
            任务ID
        """
        task_id = f"prof-{uuid.uuid4().hex[:8]}"
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 解析 connection_id 获取集群信息
        parts = connection_id.split('/')
        cluster_name = parts[0] if len(parts) > 0 else ''
        namespace = parts[1] if len(parts) > 1 else 'default'
        pod_name = parts[2] if len(parts) > 2 else ''
        
        self.db.insert('profiler_tasks', {
            'id': task_id,
            'connection_id': connection_id,
            'user_id': user_id,
            'type': task_type,
            'status': 'pending',
            'cluster_name': cluster_name,
            'namespace': namespace,
            'pod_name': pod_name,
            'mode': task_type,
            'event': event,
            'duration': duration,
            'format': fmt,
            'progress': 0,
            'message': '任务已创建，等待启动',
            'created_at': now_ts,
            'updated_at': now_ts,
        })
        
        log.info("Profiler 任务已创建: task_id=%s, type=%s, event=%s", 
                 task_id, task_type, event)
        return task_id

    def start_task(self, task_id: str) -> Dict[str, Any]:
        """启动 Profiler 任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含 success 和 message 的字典
        """
        # 获取任务信息
        task = self.db.fetch_one(
            'SELECT * FROM profiler_tasks WHERE id = ?',
            (task_id,)
        )
        
        if not task:
            return {"success": False, "message": f"任务 {task_id} 不存在"}
        
        if task['status'] not in ('pending', 'stopped', 'failed'):
            return {
                "success": False, 
                "message": f"任务状态为 {task['status']}，无法启动"
            }
        
        # 更新任务状态为 running
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.update('profiler_tasks', {
            'status': 'running',
            'progress': 0,
            'message': '任务启动中...',
            'updated_at': now_ts,
        }, 'id = ?', (task_id,))
        
        # 后台执行任务
        import threading
        def run_task():
            try:
                # 获取数据库连接
                from api import get_connection_by_id
                conn = get_connection_by_id(task['connection_id'])
                
                if not conn:
                    raise Exception(f"连接 {task['connection_id']} 不存在或已断开")
                
                # 创建 ProfilerWorkflow 实例
                workflow = ProfilerWorkflow(conn)
                
                # 根据任务类型设置参数
                mode = task['mode'] or task['type']
                event = task['event'] or mode
                duration = task['duration'] or 60
                fmt = task['format'] or 'html'
                
                # 设置输出目录
                from flask import current_app
                output_dir = current_app.config.get('OUTPUT_DIR', 'profiler_output')
                
                # 执行工作流
                result = workflow.run(
                    duration=duration,
                    fmt=fmt,
                    output_dir=output_dir,
                    mode=mode,
                    event=event
                )
                
                # 更新任务状态为 completed
                output_path = result.get('local_file', '')
                message = result.get('message', '任务完成')
                
                self.db.update('profiler_tasks', {
                    'status': 'completed',
                    'progress': 100,
                    'output_path': output_path,
                    'message': message,
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }, 'id = ?', (task_id,))
                
                # Phase 7 新增：写入诊断历史
                self._write_to_diagnosis_history(task_id, task, result, 'completed')
                
                log.info("Profiler 任务完成: task_id=%s, output=%s", 
                         task_id, output_path)
                
            except Exception as e:
                log.error("Profiler 任务失败: task_id=%s, error=%s", 
                          task_id, e, exc_info=True)
                self.db.update('profiler_tasks', {
                    'status': 'failed',
                    'message': str(e),
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }, 'id = ?', (task_id,))
        
        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()
        
        return {"success": True, "message": "任务已启动", "task_id": task_id}

    def stop_task(self, task_id: str) -> Dict[str, Any]:
        """停止 Profiler 任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含 success 和 message 的字典
        """
        task = self.db.fetch_one(
            'SELECT * FROM profiler_tasks WHERE id = ?',
            (task_id,)
        )
        
        if not task:
            return {"success": False, "message": f"任务 {task_id} 不存在"}
        
        if task['status'] != 'running':
            return {
                "success": False,
                "message": f"任务状态为 {task['status']}，无法停止"
            }
        
        # 更新任务状态为 stopped
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.update('profiler_tasks', {
            'status': 'stopped',
            'message': '任务已停止',
            'updated_at': now_ts,
        }, 'id = ?', (task_id,))
        
        # TODO: 实际停止 ProfilerWorkflow 的执行
        # 需要通过某种方式获取正在运行的 workflow 实例并调用 cancel()
        
        log.info("Profiler 任务已停止: task_id=%s", task_id)
        return {"success": True, "message": "任务已停止"}

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含任务详细信息的字典
        """
        task = self.db.fetch_one(
            'SELECT * FROM profiler_tasks WHERE id = ?',
            (task_id,)
        )
        
        if not task:
            return {"success": False, "message": f"任务 {task_id} 不存在"}
        
        # 计算进度（如果任务正在运行）
        progress = task.get('progress', 0)
        if task['status'] == 'running' and progress == 0:
            # 根据时间估算进度
            created_at = task.get('created_at', '')
            duration = task.get('duration', 60)
            
            try:
                from datetime import datetime as dt
                start_time = dt.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S')
                elapsed = (datetime.now() - start_time).total_seconds()
                progress = min(90, int((elapsed / duration) * 100))
            except Exception:
                progress = 50
        
        return {
            "success": True,
            "task": {
                "id": task['id'],
                "connection_id": task['connection_id'],
                "type": task['type'],
                "status": task['status'],
                "progress": progress,
                "output_path": task.get('output_path', ''),
                "message": task.get('message', ''),
                "created_at": task.get('created_at', ''),
                "updated_at": task.get('updated_at', ''),
            }
        }

    def list_tasks(self, connection_id: str = None, 
                  user_id: int = None) -> List[Dict[str, Any]]:
        """列出任务列表
        
        Args:
            connection_id: 连接ID（可选，用于过滤）
            user_id: 用户ID（可选，用于过滤）
            
        Returns:
            任务列表
        """
        query = 'SELECT * FROM profiler_tasks WHERE 1=1'
        params = []
        
        if connection_id:
            query += ' AND connection_id = ?'
            params.append(connection_id)
        
        if user_id:
            query += ' AND user_id = ?'
            params.append(user_id)
        
        query += ' ORDER BY created_at DESC LIMIT 50'
        
        tasks = self.db.fetch_all(query, tuple(params))
        return [dict(t) for t in (tasks or [])]

    def delete_task(self, task_id: str) -> Dict[str, Any]:
        """删除任务记录
        
        Args:
            task_id: 任务ID
            
        Returns:
            包含 success 和 message 的字典
        """
        task = self.db.fetch_one(
            'SELECT * FROM profiler_tasks WHERE id = ?',
            (task_id,)
        )
        
        if not task:
            return {"success": False, "message": f"任务 {task_id} 不存在"}
        
        # 如果任务正在运行，不允许删除
        if task['status'] == 'running':
            return {
                "success": False,
                "message": "任务正在运行中，请先停止任务"
            }
        
        self.db.delete('profiler_tasks', 'id = ?', (task_id,))
        
        log.info("Profiler 任务已删除: task_id=%s", task_id)
        return {"success": True, "message": "任务已删除"}

    # ── Phase 7 新增：写入诊断历史 ──────────────────────────

    def _write_to_diagnosis_history(self, task_id: str, task: Dict, 
                                    result: Dict, status: str) -> None:
        """将 Profiler 任务写入诊断历史（task_logs 表）
        
        Args:
            task_id: 任务ID
            task: 任务信息（数据库记录）
            result: ProfilerWorkflow 执行结果
            status: 任务状态（completed/failed）
        """
        try:
            now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 构建 result_json
            result_data = {
                "task_id": task_id,
                "type": task.get('type', ''),
                "event": task.get('event', ''),
                "output_path": result.get('local_file', ''),
                "message": result.get('message', ''),
                "profiler_result": result
            }
            
            # 写入 task_logs 表
            self.db.insert('task_logs', {
                'id': f"prof-{task_id}",
                'connection_id': task.get('connection_id', ''),
                'capability_id': None,  # Profiler 不是 capability
                'status': status,
                'result_json': json.dumps(result_data, ensure_ascii=False),
                'started_at': task.get('created_at', now_ts),
                'finished_at': now_ts,
                'duration_ms': (task.get('duration', 60)) * 1000,
                'error_message': '' if status == 'completed' else result.get('message', ''),
            })
            
            log.info("Profiler 任务已写入诊断历史: task_id=%s", task_id)
        except Exception as e:
            log.error("写入诊断历史失败: task_id=%s, error=%s", 
                       task_id, e, exc_info=True)


# 全局实例
_profiler_service: Optional[ProfilerService] = None


def get_profiler_service() -> ProfilerService:
    """获取 ProfilerService 单例"""
    global _profiler_service
    if _profiler_service is None:
        _profiler_service = ProfilerService()
    return _profiler_service
