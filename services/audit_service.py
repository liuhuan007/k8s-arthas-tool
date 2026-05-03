#!/usr/bin/env python3
"""审计日志服务"""
from typing import Optional, List, Dict, Any
from flask import request
from models.db import db


class AuditService:
    """审计日志服务 - 统一处理所有审计日志记录"""
    
    @staticmethod
    def _get_client_info() -> Dict[str, str]:
        """获取客户端信息"""
        return {
            'ip_address': request.remote_addr if request else None,
            'user_agent': request.headers.get('User-Agent', '')[:500] if request else ''
        }
    
    # ─────────────────────────────────────────────────────────────────
    # 登录相关
    # ─────────────────────────────────────────────────────────────────
    
    @staticmethod
    def log_login_success(user_id: int, username: str):
        """记录登录成功"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'login',
            'resource_type': 'user',
            'resource_id': username,
            'details': f'用户 {username} 登录成功',
            **client
        })
    
    @staticmethod
    def log_login_failed(user_id: Optional[int], username: str, reason: str):
        """记录登录失败"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'login_failed',
            'resource_type': 'user',
            'resource_id': username,
            'details': f'登录失败: {reason} (用户: {username})',
            **client
        })
    
    @staticmethod
    def log_logout(user_id: int, username: str):
        """记录登出"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'logout',
            'resource_type': 'user',
            'resource_id': username,
            'details': f'用户 {username} 登出',
            **client
        })
    
    # ─────────────────────────────────────────────────────────────────
    # 用户管理相关
    # ─────────────────────────────────────────────────────────────────
    
    @staticmethod
    def log_user_created(operator_id: int, username: str, role: str):
        """记录创建用户"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': operator_id,
            'action': 'user_created',
            'resource_type': 'user',
            'resource_id': username,
            'details': f'创建用户 {username} (角色: {role})',
            **client
        })
    
    @staticmethod
    def log_user_updated(operator_id: int, username: str, changes: str):
        """记录更新用户"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': operator_id,
            'action': 'user_updated',
            'resource_type': 'user',
            'resource_id': username,
            'details': f'更新用户 {username}: {changes}',
            **client
        })
    
    @staticmethod
    def log_user_deleted(operator_id: int, username: str):
        """记录删除用户"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': operator_id,
            'action': 'user_deleted',
            'resource_type': 'user',
            'resource_id': username,
            'details': f'删除用户 {username}',
            **client
        })
    
    @staticmethod
    def log_user_status_changed(operator_id: int, username: str, new_status: str):
        """记录用户状态变更"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': operator_id,
            'action': 'user_status_changed',
            'resource_type': 'user',
            'resource_id': username,
            'details': f'用户 {username} 状态变更为 {new_status}',
            **client
        })
    
    @staticmethod
    def log_password_changed(user_id: int, username: str):
        """记录密码修改"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'change_password',
            'resource_type': 'user',
            'resource_id': username,
            'details': f'用户 {username} 修改密码',
            **client
        })
    
    # ─────────────────────────────────────────────────────────────────
    # 连接相关
    # ─────────────────────────────────────────────────────────────────
    
    @staticmethod
    def log_connection_created(user_id: int, conn_id: str, pod: str, namespace: str):
        """记录创建连接"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'connection_created',
            'resource_type': 'connection',
            'resource_id': conn_id,
            'details': f'创建连接: {namespace}/{pod}',
            **client
        })
    
    @staticmethod
    def log_connection_deleted(user_id: int, conn_id: str, pod: str, namespace: str):
        """记录删除连接"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'connection_deleted',
            'resource_type': 'connection',
            'resource_id': conn_id,
            'details': f'删除连接: {namespace}/{pod}',
            **client
        })
    
    # ─────────────────────────────────────────────────────────────────
    # 任务相关
    # ─────────────────────────────────────────────────────────────────
    
    @staticmethod
    def log_task_created(user_id: int, task_id: str, task_type: str):
        """记录创建任务"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'task_created',
            'resource_type': 'profiler_task',
            'resource_id': task_id,
            'details': f'创建性能分析任务: {task_type}',
            **client
        })
    
    @staticmethod
    def log_task_cancelled(user_id: int, task_id: str):
        """记录取消任务"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'task_cancelled',
            'resource_type': 'profiler_task',
            'resource_id': task_id,
            'details': f'取消性能分析任务',
            **client
        })
    
    # ─────────────────────────────────────────────────────────────────
    # 文件操作相关
    # ─────────────────────────────────────────────────────────────────
    
    @staticmethod
    def log_file_downloaded(user_id: int, filename: str):
        """记录文件下载"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': 'file_downloaded',
            'resource_type': 'file',
            'resource_id': filename,
            'details': f'下载文件: {filename}',
            **client
        })
    
    # ─────────────────────────────────────────────────────────────────
    # 诊断操作相关
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def log_event(user_id: int, action: str, resource_type: str,
                  resource_id: str, details: str):
        """通用事件日志记录"""
        AuditService._log_raw(user_id, action, resource_type, resource_id, details)

    @staticmethod
    def log_diagnostic_operation(user_id: int, operation: str,
                                 connection_id: str, details: str):
        """记录诊断操作（arthas exec、profiler tasks 等）"""
        AuditService._log_raw(
            user_id, operation, 'diagnostic', connection_id, details
        )

    @staticmethod
    def log_arthas_connect(user_id: int, connection_id: str,
                           cluster: str, namespace: str, pod: str):
        """记录 Arthas 连接建立"""
        AuditService.log_diagnostic_operation(
            user_id, 'arthas_connect', connection_id,
            f'Arthas 连接到 {cluster}/{namespace}/{pod}'
        )

    @staticmethod
    def log_arthas_disconnect(user_id: int, connection_id: str):
        """记录 Arthas 连接断开"""
        AuditService.log_diagnostic_operation(
            user_id, 'arthas_disconnect', connection_id,
            'Arthas 连接断开'
        )

    @staticmethod
    def log_arthas_exec(user_id: int, connection_id: str, command: str):
        """记录 Arthas 命令执行"""
        AuditService.log_diagnostic_operation(
            user_id, 'arthas_exec', connection_id,
            f'执行命令: {command}'
        )

    @staticmethod
    def log_profiler_start(user_id: int, task_id: str, task_type: str):
        """记录 Profiler 任务启动"""
        AuditService.log_diagnostic_operation(
            user_id, 'profiler_start', task_id,
            f'启动性能分析任务: {task_type}'
        )

    @staticmethod
    def log_profiler_cancel(user_id: int, task_id: str, reason: str):
        """记录 Profiler 任务取消"""
        AuditService.log_diagnostic_operation(
            user_id, 'profiler_cancel', task_id,
            f'取消性能分析任务，原因: {reason}'
        )

    @staticmethod
    def log_profiler_download(user_id: int, task_id: str, filename: str):
        """记录 Profiler 结果下载"""
        AuditService.log_diagnostic_operation(
            user_id, 'profiler_download', task_id,
            f'下载性能分析结果: {filename}'
        )

    @staticmethod
    def log_gc_download(user_id: int, cluster: str, namespace: str,
                        pod: str, filename: str):
        """记录 GC 日志下载"""
        AuditService._log_raw(
            user_id, 'gc_download', 'gc_log', filename,
            f'下载 GC 日志: {cluster}/{namespace}/{pod} -> {filename}'
        )

    @staticmethod
    def log_pod_file_read(user_id: int, connection_id: str, path: str):
        """记录 Pod 文件读取"""
        AuditService.log_diagnostic_operation(
            user_id, 'pod_file_read', connection_id,
            f'读取 Pod 文件: {path}'
        )

    @staticmethod
    def log_pod_file_download(user_id: int, connection_id: str, path: str):
        """记录 Pod 文件下载"""
        AuditService.log_diagnostic_operation(
            user_id, 'pod_file_download', connection_id,
            f'下载 Pod 文件: {path}'
        )

    # ─────────────────────────────────────────────────────────────────
    # MCP 相关
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _log_raw(user_id: int, action: str, resource_type: str,
                 resource_id: str, details: str):
        """通用审计日志记录（内部方法，供特殊场景使用）"""
        client = AuditService._get_client_info()
        db.insert('audit_logs', {
            'user_id': user_id,
            'action': action,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'details': details,
            **client
        })

    # ─────────────────────────────────────────────────────────────────
    # 通用查询方法
    # ─────────────────────────────────────────────────────────────────
    
    @staticmethod
    def query(filters: Dict[str, Any] = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """查询审计日志"""
        filters = filters or {}
        
        sql = 'SELECT * FROM audit_logs WHERE 1=1'
        params = []
        
        if 'user_id' in filters and filters['user_id']:
            sql += ' AND user_id = ?'
            params.append(filters['user_id'])
        
        if 'action' in filters and filters['action']:
            sql += ' AND action = ?'
            params.append(filters['action'])
        
        if 'resource_type' in filters and filters['resource_type']:
            sql += ' AND resource_type = ?'
            params.append(filters['resource_type'])
        
        if 'start_date' in filters and filters['start_date']:
            sql += ' AND timestamp >= ?'
            params.append(filters['start_date'])
        
        if 'end_date' in filters and filters['end_date']:
            sql += ' AND timestamp <= ?'
            params.append(filters['end_date'])
        
        sql += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        return db.fetch_all(sql, tuple(params))
    
    @staticmethod
    def count(filters: Dict[str, Any] = None) -> int:
        """统计审计日志数量"""
        filters = filters or {}
        
        sql = 'SELECT COUNT(*) as cnt FROM audit_logs WHERE 1=1'
        params = []
        
        if 'user_id' in filters and filters['user_id']:
            sql += ' AND user_id = ?'
            params.append(filters['user_id'])
        
        if 'action' in filters and filters['action']:
            sql += ' AND action = ?'
            params.append(filters['action'])
        
        if 'resource_type' in filters and filters['resource_type']:
            sql += ' AND resource_type = ?'
            params.append(filters['resource_type'])
        
        result = db.fetch_one(sql, tuple(params))
        return result['cnt'] if result else 0
    
    @staticmethod
    def get_actions() -> List[str]:
        """获取所有可用的操作类型"""
        rows = db.fetch_all('SELECT DISTINCT action FROM audit_logs ORDER BY action')
        return [row['action'] for row in rows]
    
    @staticmethod
    def get_resource_types() -> List[str]:
        """获取所有可用的资源类型"""
        rows = db.fetch_all('SELECT DISTINCT resource_type FROM audit_logs WHERE resource_type IS NOT NULL ORDER BY resource_type')
        return [row['resource_type'] for row in rows]