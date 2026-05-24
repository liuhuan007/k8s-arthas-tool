#!/usr/bin/env python3
"""资源管理器 - Agent 资源控制和限制

本模块管理 Agent 的资源使用，包括：
- 并发限制
- 速率控制
- Token 用量统计
- 资源配额管理

Author: Kou (software-engineer)
Created: 2025-05-25
"""

import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict
from threading import Lock

log = logging.getLogger(__name__)


class ResourceQuota:
    """资源配额"""

    def __init__(
        self,
        max_concurrent: int = 10,
        max_requests_per_minute: int = 60,
        max_tokens_per_day: int = 100000,
        max_turns_per_session: int = 50
    ):
        """初始化

        Args:
            max_concurrent: 最大并发数
            max_requests_per_minute: 每分钟最大请求数
            max_tokens_per_day: 每日最大 Token 数
            max_turns_per_session: 每会话最大轮次
        """
        self.max_concurrent = max_concurrent
        self.max_requests_per_minute = max_requests_per_minute
        self.max_tokens_per_day = max_tokens_per_day
        self.max_turns_per_session = max_turns_per_session

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "max_concurrent": self.max_concurrent,
            "max_requests_per_minute": self.max_requests_per_minute,
            "max_tokens_per_day": self.max_tokens_per_day,
            "max_turns_per_session": self.max_turns_per_session
        }


class ResourceManager:
    """资源管理器

    管理 Agent 的资源使用和限制，防止资源滥用。

    使用示例：
        manager = ResourceManager()
        if manager.check_rate_limit(user_id=1):
            # 允许请求
            manager.record_request(user_id=1, tokens=100)
        else:
            # 限流
            raise Exception("Rate limit exceeded")
    """

    def __init__(self, quota: Optional[ResourceQuota] = None):
        """初始化

        Args:
            quota: 资源配额（可选）
        """
        self._quota = quota or ResourceQuota()
        self._lock = Lock()

        # 运行时状态
        self._active_sessions: Dict[str, datetime] = {}
        self._request_counts: Dict[str, List[float]] = defaultdict(list)
        self._token_counts: Dict[str, int] = defaultdict(int)
        self._turn_counts: Dict[str, int] = defaultdict(int)
        self._daily_token_counts: Dict[str, int] = defaultdict(int)
        self._last_cleanup: datetime = datetime.now()

    @property
    def quota(self) -> ResourceQuota:
        """获取配额"""
        return self._quota

    def set_quota(self, quota: ResourceQuota):
        """设置配额

        Args:
            quota: 新配额
        """
        self._quota = quota

    def acquire_session(self, session_id: str) -> bool:
        """获取会话资源

        Args:
            session_id: 会话 ID

        Returns:
            是否获取成功
        """
        with self._lock:
            # 检查并发限制
            if len(self._active_sessions) >= self._quota.max_concurrent:
                log.warning(f"Concurrent session limit reached: {self._quota.max_concurrent}")
                return False

            # 注册会话
            self._active_sessions[session_id] = datetime.now()
            log.debug(f"Acquired session: {session_id}")
            return True

    def release_session(self, session_id: str):
        """释放会话资源

        Args:
            session_id: 会话 ID
        """
        with self._lock:
            if session_id in self._active_sessions:
                del self._active_sessions[session_id]
                log.debug(f"Released session: {session_id}")

    def check_rate_limit(self, user_id: int) -> bool:
        """检查速率限制

        Args:
            user_id: 用户 ID

        Returns:
            是否允许请求
        """
        with self._lock:
            now = time.time()
            user_key = f"user-{user_id}"

            # 清理过期记录（1分钟前）
            cutoff = now - 60
            self._request_counts[user_key] = [
                t for t in self._request_counts[user_key] if t > cutoff
            ]

            # 检查速率限制
            current_count = len(self._request_counts[user_key])
            if current_count >= self._quota.max_requests_per_minute:
                log.warning(f"Rate limit exceeded for user {user_id}: {current_count}/{self._quota.max_requests_per_minute}")
                return False

            return True

    def record_request(self, user_id: int, tokens: int = 0):
        """记录请求

        Args:
            user_id: 用户 ID
            tokens: Token 使用量
        """
        with self._lock:
            now = time.time()
            today = datetime.now().strftime("%Y-%m-%d")
            user_key = f"user-{user_id}"

            # 记录请求时间
            self._request_counts[user_key].append(now)

            # 记录 Token 使用
            if tokens > 0:
                self._token_counts[user_key] += tokens

                # 记录每日 Token 使用
                daily_key = f"{user_key}-{today}"
                self._daily_token_counts[daily_key] += tokens

            # 定期清理
            self._maybe_cleanup()

    def check_token_limit(self, user_id: int, tokens_requested: int = 0) -> bool:
        """检查 Token 限制

        Args:
            user_id: 用户 ID
            tokens_requested: 请求的 Token 数

        Returns:
            是否允许
        """
        today = datetime.now().strftime("%Y-%m-%d")
        user_key = f"user-{user_id}"
        daily_key = f"{user_key}-{today}"

        current_tokens = self._daily_token_counts.get(daily_key, 0)
        total_tokens = current_tokens + tokens_requested

        if total_tokens > self._quota.max_tokens_per_day:
            log.warning(
                f"Token limit exceeded for user {user_id}: "
                f"{current_tokens}/{self._quota.max_tokens_per_day}"
            )
            return False

        return True

    def check_turn_limit(self, session_id: str) -> bool:
        """检查轮次限制

        Args:
            session_id: 会话 ID

        Returns:
            是否允许
        """
        current_turns = self._turn_counts.get(session_id, 0)

        if current_turns >= self._quota.max_turns_per_session:
            log.warning(
                f"Turn limit exceeded for session {session_id}: "
                f"{current_turns}/{self._quota.max_turns_per_session}"
            )
            return False

        return True

    def record_turn(self, session_id: str):
        """记录轮次

        Args:
            session_id: 会话 ID
        """
        with self._lock:
            self._turn_counts[session_id] = self._turn_counts.get(session_id, 0) + 1

    def get_usage_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """获取使用统计

        Args:
            user_id: 用户 ID（可选）

        Returns:
            统计信息
        """
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")

            if user_id:
                user_key = f"user-{user_id}"
                daily_key = f"{user_key}-{today}"

                return {
                    "active_sessions": sum(
                        1 for sid in self._active_sessions
                        if sid.startswith(user_key)
                    ),
                    "requests_this_minute": len(
                        self._request_counts.get(user_key, [])
                    ),
                    "total_tokens": self._token_counts.get(user_key, 0),
                    "daily_tokens": self._daily_token_counts.get(daily_key, 0),
                    "quota": self._quota.to_dict()
                }

            # 全局统计
            return {
                "active_sessions": len(self._active_sessions),
                "total_users": len(self._request_counts),
                "total_tokens": sum(self._token_counts.values()),
                "quota": self._quota.to_dict()
            }

    def get_user_turn_count(self, session_id: str) -> int:
        """获取会话轮次

        Args:
            session_id: 会话 ID

        Returns:
            当前轮次数
        """
        return self._turn_counts.get(session_id, 0)

    def reset_user_stats(self, user_id: int):
        """重置用户统计

        Args:
            user_id: 用户 ID
        """
        with self._lock:
            user_key = f"user-{user_id}"
            self._request_counts.pop(user_key, None)
            self._token_counts.pop(user_key, None)

            # 重置每日统计
            today = datetime.now().strftime("%Y-%m-%d")
            daily_key = f"{user_key}-{today}"
            self._daily_token_counts.pop(daily_key, None)

            log.info(f"Reset stats for user {user_id}")

    def reset_session_stats(self, session_id: str):
        """重置会话统计

        Args:
            session_id: 会话 ID
        """
        with self._lock:
            self._turn_counts.pop(session_id, None)
            log.info(f"Reset session stats: {session_id}")

    def _maybe_cleanup(self):
        """定期清理过期数据"""
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() > 300:  # 5分钟清理一次
            self._cleanup_old_data()
            self._last_cleanup = now

    def _cleanup_old_data(self):
        """清理过期数据"""
        now = time.time()
        cutoff = now - 3600  # 1小时前

        # 清理请求计数
        for key in list(self._request_counts.keys()):
            self._request_counts[key] = [
                t for t in self._request_counts[key] if t > cutoff
            ]
            if not self._request_counts[key]:
                del self._request_counts[key]

        # 清理过期会话
        expired_sessions = [
            sid for sid, created in self._active_sessions.items()
            if (datetime.now() - created).total_seconds() > 3600
        ]
        for sid in expired_sessions:
            del self._active_sessions[sid]

        log.debug(f"Cleaned up {len(expired_sessions)} expired sessions")


# 全局实例
_resource_manager: Optional[ResourceManager] = None


def get_resource_manager() -> ResourceManager:
    """获取 ResourceManager 单例

    Returns:
        ResourceManager 实例
    """
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = ResourceManager()
    return _resource_manager
