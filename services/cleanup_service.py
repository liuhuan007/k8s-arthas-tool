#!/usr/bin/env python3
"""
清理服务 - 连接自动清理与磁盘保护

核心功能:
1. 连接 TTL 清理 - 过期连接自动断开
2. 产物清理 - profiler_output 定期清理
3. 日志清理 - profiler_logs 定期清理
4. 磁盘水位保护 - 使用率监控和告警
"""
import os
import glob
import time
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path

from models.db import db

log = logging.getLogger(__name__)


class CleanupService:
    """清理服务 - 管理连接和产物生命周期"""

    # 默认配置
    DEFAULT_CONFIG = {
        'connection_ttl_hours': 24,        # 连接 TTL: 24 小时
        'artifact_retention_days': 7,      # 产物保留: 7 天
        'log_retention_days': 30,          # 日志保留: 30 天
        'disk_warning_threshold': 0.80,    # 磁盘告警阈值: 80%
        'max_heapdump_size_gb': 2,         # heapdump 最大: 2GB
    }

    def __init__(self, config=None):
        """初始化清理服务"""
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.profiler_output_dir = os.path.join(os.getcwd(), 'profiler_output')

    # ═══════════════════════════════════════════════════════════════
    # 连接 TTL 清理
    # ═══════════════════════════════════════════════════════════════

    def cleanup_expired_connections(self, user_id=None):
        """
        清理过期连接
        
        过期判定: last_ping_at 超过 TTL 且 status != 'ready'
        清理动作: 更新 status='disconnected', 记录审计日志
        
        Args:
            user_id: 可选,指定用户 ID(默认清理所有用户)
            
        Returns:
            dict: {'cleaned': int, 'connections': list}
        """
        ttl_hours = self.config['connection_ttl_hours']
        cutoff_time = datetime.now() - timedelta(hours=ttl_hours)
        cutoff_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')

        query = '''
            SELECT id, cluster_name, namespace, pod_name, status, last_ping_at, owner_user_id
            FROM connections
            WHERE status != 'ready'
            AND (last_ping_at IS NULL OR last_ping_at < ?)
        '''
        params = [cutoff_str]

        if user_id:
            query += ' AND owner_user_id = ?'
            params.append(user_id)

        query += ' ORDER BY last_ping_at ASC'

        expired_conns = db.fetch_all(query, params)
        cleaned_ids = []

        for conn in expired_conns:
            conn_id = conn['id']
            try:
                # 更新状态为 disconnected
                db.update(
                    'connections',
                    {
                        'status': 'disconnected',
                        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    },
                    'id = ?',
                    (conn_id,)
                )

                # 记录审计日志
                from services.audit_service import AuditService
                AuditService._log_raw(
                    conn.get('owner_user_id', 0),
                    'connection_ttl_cleanup',
                    'connection',
                    str(conn_id),
                    f'连接 TTL 过期自动清理: {conn["cluster_name"]}/{conn["namespace"]}/{conn["pod_name"]}, '
                    f'最后活跃: {conn["last_ping_at"]}'
                )

                cleaned_ids.append(conn_id)
                log.info(
                    "Connection TTL cleaned: id=%s, cluster=%s, last_ping=%s",
                    conn_id, conn['cluster_name'], conn['last_ping_at']
                )

            except Exception as e:
                log.error("Failed to cleanup connection %s: %s", conn_id, e, exc_info=True)

        return {
            'cleaned': len(cleaned_ids),
            'connections': cleaned_ids
        }

    # ═══════════════════════════════════════════════════════════════
    # 产物清理
    # ═══════════════════════════════════════════════════════════════

    def cleanup_old_artifacts(self, retention_days=None):
        """
        清理过期产物
        
        策略: 删除 profiler_output 中超过保留天数的文件
        保护: heapdump/JFR 大文件单独检查大小限制
        
        Args:
            retention_days: 可选,覆盖默认保留天数
            
        Returns:
            dict: {'cleaned_files': int, 'cleaned_size_mb': float, 'warnings': list}
        """
        if retention_days is None:
            retention_days = self.config['artifact_retention_days']

        cutoff_time = time.time() - (retention_days * 86400)
        warnings = []
        cleaned_files = 0
        cleaned_size = 0

        if not os.path.exists(self.profiler_output_dir):
            return {'cleaned_files': 0, 'cleaned_size_mb': 0, 'warnings': []}

        # 遍历所有子目录
        for root, dirs, files in os.walk(self.profiler_output_dir):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    # 检查文件修改时间
                    mtime = os.path.getmtime(filepath)
                    if mtime < cutoff_time:
                        file_size = os.path.getsize(filepath)
                        
                        # 大文件警告(heapdump/JFR)
                        if filename.endswith(('.hprof', '.jfr')):
                            size_gb = file_size / (1024 ** 3)
                            if size_gb > self.config['max_heapdump_size_gb']:
                                warnings.append(
                                    f"大文件告警: {filepath} ({size_gb:.2f}GB > {self.config['max_heapdump_size_gb']}GB)"
                                )

                        # 删除文件
                        os.remove(filepath)
                        cleaned_files += 1
                        cleaned_size += file_size

                except Exception as e:
                    log.error("Failed to cleanup artifact %s: %s", filepath, e)

        # 清理空目录
        self._cleanup_empty_dirs(self.profiler_output_dir)

        return {
            'cleaned_files': cleaned_files,
            'cleaned_size_mb': round(cleaned_size / (1024 * 1024), 2),
            'warnings': warnings
        }

    # ═══════════════════════════════════════════════════════════════
    # 日志清理
    # ═══════════════════════════════════════════════════════════════

    def cleanup_old_logs(self, retention_days=None):
        """
        清理过期任务记录

        策略: 删除 profiler_tasks 表中超过保留天数的已完成/失败记录

        Args:
            retention_days: 可选,覆盖默认保留天数

        Returns:
            dict: {'cleaned_records': int}
        """
        if retention_days is None:
            retention_days = self.config['log_retention_days']

        cutoff_time = datetime.now() - timedelta(days=retention_days)
        cutoff_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')

        # 先查询数量
        count_result = db.fetch_one(
            "SELECT COUNT(*) as cnt FROM profiler_tasks WHERE created_at < ? AND status IN ('completed', 'failed', 'stopped', 'cancelled')",
            (cutoff_str,)
        )
        total_to_clean = count_result['cnt'] if count_result else 0

        if total_to_clean == 0:
            return {'cleaned_records': 0}

        # 删除过期记录
        db.delete("profiler_tasks", "created_at < ? AND status IN ('completed', 'failed', 'stopped', 'cancelled')", (cutoff_str,))

        log.info("Cleaned %d old profiler task records (older than %d days)",
                 total_to_clean, retention_days)

        return {'cleaned_records': total_to_clean}

    # ═══════════════════════════════════════════════════════════════
    # 磁盘水位监控
    # ═══════════════════════════════════════════════════════════════

    def check_disk_usage(self, path=None):
        """
        检查磁盘使用率
        
        Args:
            path: 可选,检查指定路径(默认检查 profiler_output 所在磁盘)
            
        Returns:
            dict: {'total_gb': float, 'used_gb': float, 'free_gb': float, 
                   'usage_percent': float, 'warning': bool, 'message': str}
        """
        if path is None:
            path = self.profiler_output_dir

        try:
            total, used, free = shutil.disk_usage(path)
            usage_percent = used / total

            warning = usage_percent >= self.config['disk_warning_threshold']
            
            result = {
                'total_gb': round(total / (1024 ** 3), 2),
                'used_gb': round(used / (1024 ** 3), 2),
                'free_gb': round(free / (1024 ** 3), 2),
                'usage_percent': round(usage_percent * 100, 2),
                'warning': warning,
                'message': ''
            }

            if warning:
                result['message'] = (
                    f"磁盘使用率 {result['usage_percent']:.1f}% 超过告警阈值 "
                    f"{self.config['disk_warning_threshold']*100:.0f}%,建议清理过期产物"
                )
                log.warning("Disk usage warning: %.1f%% on %s", result['usage_percent'], path)

            return result

        except Exception as e:
            log.error("Failed to check disk usage for %s: %s", path, e)
            return {
                'total_gb': 0,
                'used_gb': 0,
                'free_gb': 0,
                'usage_percent': 0,
                'warning': False,
                'message': f'检查失败: {str(e)}'
            }

    def get_directory_stats(self, directory=None):
        """
        获取目录统计信息
        
        Args:
            directory: 可选,指定目录(默认 profiler_output)
            
        Returns:
            dict: {'total_files': int, 'total_size_mb': float, 'oldest_file': str, 'newest_file': str}
        """
        if directory is None:
            directory = self.profiler_output_dir

        if not os.path.exists(directory):
            return {
                'total_files': 0,
                'total_size_mb': 0,
                'oldest_file': None,
                'newest_file': None
            }

        total_files = 0
        total_size = 0
        oldest_time = None
        newest_time = None
        oldest_file = None
        newest_file = None

        for root, dirs, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    mtime = os.path.getmtime(filepath)
                    file_size = os.path.getsize(filepath)

                    total_files += 1
                    total_size += file_size

                    if oldest_time is None or mtime < oldest_time:
                        oldest_time = mtime
                        oldest_file = filepath

                    if newest_time is None or mtime > newest_time:
                        newest_time = mtime
                        newest_file = filepath

                except Exception:
                    pass

        return {
            'total_files': total_files,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'oldest_file': oldest_file,
            'newest_file': newest_file,
            'oldest_time': datetime.fromtimestamp(oldest_time).isoformat() if oldest_time else None,
            'newest_time': datetime.fromtimestamp(newest_time).isoformat() if newest_time else None,
        }

    # ═══════════════════════════════════════════════════════════════
    # 综合清理(定时任务入口)
    # ═══════════════════════════════════════════════════════════════

    def run_full_cleanup(self, user_id=None):
        """
        执行完整清理流程(供定时任务调用)
        
        顺序:
        1. 检查磁盘水位
        2. 清理过期连接
        3. 清理过期产物
        4. 清理过期日志
        5. 返回清理报告
        
        Args:
            user_id: 可选,仅清理指定用户的连接
            
        Returns:
            dict: 完整清理报告
        """
        log.info("Starting full cleanup cycle...")
        start_time = time.time()

        # 1. 磁盘检查
        disk_usage = self.check_disk_usage()

        # 2. 连接清理
        connection_cleanup = self.cleanup_expired_connections(user_id)

        # 3. 产物清理
        artifact_cleanup = self.cleanup_old_artifacts()

        # 4. 日志清理
        log_cleanup = self.cleanup_old_logs()

        elapsed = time.time() - start_time

        report = {
            'timestamp': datetime.now().isoformat(),
            'elapsed_seconds': round(elapsed, 2),
            'disk_usage': disk_usage,
            'connection_cleanup': connection_cleanup,
            'artifact_cleanup': artifact_cleanup,
            'log_cleanup': log_cleanup,
            'total_cleaned_items': (
                connection_cleanup['cleaned'] + 
                artifact_cleanup['cleaned_files'] + 
                log_cleanup['cleaned_records']
            ),
            'total_freed_mb': artifact_cleanup['cleaned_size_mb']
        }

        log.info(
            "Full cleanup completed in %.2fs: %d connections, %d files (%.2fMB), %d logs",
            elapsed,
            connection_cleanup['cleaned'],
            artifact_cleanup['cleaned_files'],
            artifact_cleanup['cleaned_size_mb'],
            log_cleanup['cleaned_records']
        )

        return report

    # ═══════════════════════════════════════════════════════════════
    # 内部辅助方法
    # ═══════════════════════════════════════════════════════════════

    def _cleanup_empty_dirs(self, base_dir):
        """递归清理空目录"""
        for root, dirs, files in os.walk(base_dir, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                        log.debug("Removed empty directory: %s", dir_path)
                except Exception:
                    pass
