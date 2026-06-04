#!/usr/bin/env python3
"""task_logs 定时清理服务"""
import logging
from datetime import datetime
from typing import Optional

from models.db import db

log = logging.getLogger(__name__)


def get_cleanup_config(key: str, default: str) -> str:
    """从 system_configs 读取清理配置
    
    Args:
        key: 配置键
        default: 默认值
        
    Returns:
        str: 配置值
    """
    try:
        result = db.fetch_one(
            'SELECT value FROM system_configs WHERE key = ?',
            (key,)
        )
        return result['value'] if result else default
    except Exception as e:
        log.warning("读取清理配置失败 %s: %s", key, e)
        return default


class TaskLogsCleanupService:
    """task_logs 定时清理服务"""
    
    async def cleanup_expired_logs(self):
        """清理过期的 task_logs"""
        try:
            retention_days = int(get_cleanup_config('task_logs.retention_days', '30'))
            
            # 1. 查询过期日志数量
            count_result = db.fetch_one(
                """
                SELECT COUNT(*) as cnt FROM task_logs 
                WHERE is_archived = 0 
                  AND finished_at < datetime('now', '-' || ? || ' days')
                """,
                (retention_days,)
            )
            expired_count = count_result['cnt'] if count_result else 0
            
            if expired_count == 0:
                log.info("没有过期的 task_logs 需要清理")
                return
            
            log.info("发现 %d 条过期的 task_logs，开始归档...", expired_count)
            
            # 2. 归档到历史表
            db.execute(
                """
                INSERT OR IGNORE INTO task_logs_archive 
                SELECT *, CURRENT_TIMESTAMP as archived_at
                FROM task_logs 
                WHERE is_archived = 0 
                  AND finished_at < datetime('now', '-' || ? || ' days')
                """,
                (retention_days,)
            )
            
            # 3. 标记为已归档
            db.execute(
                """
                UPDATE task_logs SET is_archived = 1 
                WHERE is_archived = 0 
                  AND finished_at < datetime('now', '-' || ? || ' days')
                """,
                (retention_days,)
            )
            
            # 4. 删除已归档的旧日志（可选，保留 is_archived=1 的记录用于查询）
            # db.execute(
            #     """
            #     DELETE FROM task_logs 
            #     WHERE is_archived = 1 
            #       AND finished_at < datetime('now', '-' || ? || ' days')
            #     """,
            #     (retention_days,)
            # )
            
            # 5. 清理孤立的 arthas_command_logs（独立清理）
            arthas_retention_days = int(get_cleanup_config('arthas_command_logs.retention_days', '30'))
            db.execute(
                """
                DELETE FROM arthas_command_logs 
                WHERE connection_id NOT IN (SELECT id FROM connections)
                  AND timestamp < datetime('now', '-' || ? || ' days')
                """,
                (arthas_retention_days,)
            )
            
            log.info("task_logs 清理完成，归档 %d 条记录", expired_count)
            
        except Exception as e:
            log.error("task_logs 清理失败: %s", e, exc_info=True)
    
    async def cleanup_old_archives(self):
        """清理旧的归档日志"""
        try:
            retention_days = int(get_cleanup_config('task_logs_archive.retention_days', '365'))
            
            # 查询过期归档数量
            count_result = db.fetch_one(
                """
                SELECT COUNT(*) as cnt FROM task_logs_archive
                WHERE archived_at < datetime('now', '-' || ? || ' days')
                """,
                (retention_days,)
            )
            expired_count = count_result['cnt'] if count_result else 0
            
            if expired_count == 0:
                log.info("没有过期的归档日志需要清理")
                return
            
            log.info("发现 %d 条过期的归档日志，开始清理...", expired_count)
            
            # 删除过期归档
            db.execute(
                """
                DELETE FROM task_logs_archive
                WHERE archived_at < datetime('now', '-' || ? || ' days')
                """,
                (retention_days,)
            )
            
            log.info("归档日志清理完成，删除 %d 条记录", expired_count)
            
        except Exception as e:
            log.error("归档日志清理失败: %s", e, exc_info=True)
    
    def get_cleanup_stats(self) -> dict:
        """获取清理统计信息"""
        try:
            active_logs = db.fetch_one("SELECT COUNT(*) as cnt FROM task_logs WHERE is_archived = 0")
            archived_logs = db.fetch_one("SELECT COUNT(*) as cnt FROM task_logs WHERE is_archived = 1")
            archive_total = db.fetch_one("SELECT COUNT(*) as cnt FROM task_logs_archive")
            
            return {
                'active_logs': active_logs['cnt'] if active_logs else 0,
                'archived_logs': archived_logs['archived_logs'] if archived_logs else 0,
                'archive_total': archive_total['cnt'] if archive_total else 0,
                'retention_days': int(get_cleanup_config('task_logs.retention_days', '30')),
                'archive_retention_days': int(get_cleanup_config('task_logs_archive.retention_days', '365')),
            }
        except Exception as e:
            log.error("获取清理统计失败: %s", e)
            return {}
