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
        # task_id -> ProfilerWorkflow 实例（仅在任务运行期间存在）
        self._running_workflows: Dict[str, ProfilerWorkflow] = {}

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

    def _sync_workflow_progress(self, task_id: str, entry: Dict[str, Any], duration: int) -> None:
        """同步后台工作流日志到任务状态"""
        try:
            message = entry.get('message', '')
            progress = 0
            if duration > 0:
                import re
                match = re.search(r'进度\s+(\d+)/(\d+)s', message)
                if match:
                    progress = min(95, int(int(match.group(1)) / max(int(match.group(2)), 1) * 100))

            update_data = {
                'message': message,
                'updated_at': entry.get('timestamp') or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            if progress:
                update_data['progress'] = progress
            self.db.update('profiler_tasks', update_data, 'id = ?', (task_id,))
        except Exception:
            log.debug("同步 Profiler 工作流进度失败: task_id=%s", task_id, exc_info=True)

    def start_task(self, task_id: str, conn_obj=None) -> Dict[str, Any]:
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
                conn = conn_obj or get_connection_by_id(task['connection_id'])

                if not conn:
                    raise Exception(f"连接 {task['connection_id']} 不存在或已断开")

                # 创建 ProfilerWorkflow 实例
                workflow = ProfilerWorkflow(
                    conn,
                    progress_callback=lambda entry: self._sync_workflow_progress(task_id, entry, task['duration'] or 60)
                )

                # 存入运行中字典，供 stop_task 调用 cancel()
                self._running_workflows[task_id] = workflow
                
                # 根据任务类型设置参数
                mode = task['mode'] or task['type']
                event = task['event'] or mode
                duration = task['duration'] or 60
                fmt = task['format'] or 'html'
                
                # 设置输出目录（直接使用 Config，因为此方法在后台线程中执行，无 Flask 应用上下文）
                from backend.config import Config
                output_dir = Config.OUTPUT_DIR
                
                # 执行工作流
                result = workflow.run(
                    duration=duration,
                    fmt=fmt,
                    output_dir=output_dir,
                    mode=mode,
                    event=event
                )
                
                result_status = result.get('status', 'completed')
                output_path = result.get('local_file', '')
                message = result.get('message', '任务完成' if result_status == 'completed' else '任务失败')
                final_status = 'completed' if result_status == 'completed' else 'failed'
                current_task = self.db.fetch_one('SELECT progress FROM profiler_tasks WHERE id = ?', (task_id,))
                final_progress = 100 if final_status == 'completed' else (current_task or {}).get('progress', 0)

                self.db.update('profiler_tasks', {
                    'status': final_status,
                    'progress': final_progress,
                    'output_path': output_path,
                    'message': message,
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }, 'id = ?', (task_id,))
                
                # Phase 7 新增：写入诊断历史
                self._write_to_diagnosis_history(task_id, task, result, final_status)

                log.info("Profiler 任务结束: task_id=%s, status=%s, output=%s",
                         task_id, final_status, output_path)
                
            except Exception as e:
                log.error("Profiler 任务失败: task_id=%s, error=%s", 
                          task_id, e, exc_info=True)
                self.db.update('profiler_tasks', {
                    'status': 'failed',
                    'message': str(e),
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }, 'id = ?', (task_id,))
                # 写入诊断历史（失败）
                try:
                    self._write_to_diagnosis_history(task_id, task, {'message': str(e)}, 'failed')
                except Exception:
                    pass

            finally:
                # 清理运行中引用
                self._running_workflows.pop(task_id, None)

        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()
        
        # 启动超时监控线程（ duration * 3 或最少 120 秒后检查）
        task_duration = task.get('duration') or 60
        timeout_seconds = max(task_duration * 3, 120)
        def _timeout_watchdog():
            import time
            time.sleep(timeout_seconds)
            # 如果任务仍在运行，标记为超时失败
            current = self.db.fetch_one('SELECT status FROM profiler_tasks WHERE id = ?', (task_id,))
            if current and current.get('status') == 'running':
                log.warning("Profiler 任务超时: task_id=%s, timeout=%ds", task_id, timeout_seconds)
                # 尝试取消 workflow
                workflow = self._running_workflows.get(task_id)
                if workflow:
                    try:
                        workflow.cancel()
                    except Exception:
                        pass
                self.db.update('profiler_tasks', {
                    'status': 'failed',
                    'message': f'任务超时（超过 {timeout_seconds}s 未完成）',
                    'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }, 'id = ?', (task_id,))
                self._write_to_diagnosis_history(task_id, task, {'message': '任务超时'}, 'failed')
                self._running_workflows.pop(task_id, None)

        watchdog = threading.Thread(target=_timeout_watchdog, daemon=True)
        watchdog.start()

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
        
        if task['status'] not in ('running', 'starting'):
            return {
                "success": False,
                "message": f"任务状态为 {task['status']}，无法停止"
            }

        # 实际停止 ProfilerWorkflow
        workflow = self._running_workflows.get(task_id)
        if workflow:
            workflow.cancel()
            log.info("Profiler workflow cancel() 已调用: task_id=%s", task_id)
        else:
            log.warning("Profiler workflow 引用未找到（可能已完成）: task_id=%s", task_id)

        # 更新任务状态为 stopped
        now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.db.update('profiler_tasks', {
            'status': 'stopped',
            'message': '任务已停止',
            'updated_at': now_ts,
        }, 'id = ?', (task_id,))

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
        
        progress = task.get('progress', 0)
        
        return {
            "success": True,
            "task": {
                "id": task['id'],
                "connection_id": task['connection_id'],
                "type": task['type'],
                "mode": task.get('mode', task['type']),
                "event": task.get('event', ''),
                "duration": task.get('duration', 60),
                "format": task.get('format', ''),
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
            
            # 写入 task_logs 表（connection_id 存在 target_json 中，与表结构一致）
            self.db.insert('task_logs', {
                'id': f"prof-{task_id}",
                'user_id': task.get('user_id'),
                'capability_id': None,  # Profiler 不是 capability
                'execution_mode': 'manual',
                'execution_type': 'profiler',
                'run_type': 'profiler',
                'target_json': json.dumps({
                    'connection_id': task.get('connection_id', ''),
                    'cluster_name': task.get('cluster_name', ''),
                    'namespace': task.get('namespace', ''),
                    'pod_name': task.get('pod_name', ''),
                    'type': task.get('type', ''),
                }),
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
