#!/usr/bin/env python3
"""会话管理器 - Agent 会话持久化和恢复

本模块管理 Agent 会话的持久化存储，支持：
- 会话创建和恢复
- 消息历史持久化
- 会话状态管理
- 会话过期清理

Author: Kou (software-engineer)
Created: 2025-05-25
"""

import json
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


class SessionManager:
    """会话管理器

    管理 Agent 会话的生命周期，包括创建、恢复、更新和清理。

    使用示例：
        manager = SessionManager()
        session_id = manager.create_session(user_id=1, agent_type="codebuddy")
        manager.save_message(session_id, {"role": "user", "content": "hello"})
        messages = manager.get_messages(session_id)
    """

    # 默认会话过期时间（24小时）
    DEFAULT_EXPIRY_HOURS = 24

    # 内存存储（生产环境应使用数据库）
    _sessions: Dict[str, Dict[str, Any]] = {}

    def __init__(self, db=None):
        """初始化会话管理器

        Args:
            db: 数据库实例（可选）
        """
        self._db = db

    def create_session(
        self,
        user_id: int,
        agent_type: str = "fallback",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """创建新会话

        Args:
            user_id: 用户 ID
            agent_type: Agent 类型
            metadata: 附加元数据

        Returns:
            会话 ID
        """
        session_id = f"sess-{uuid.uuid4().hex[:12]}"

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "agent_type": agent_type,
            "status": "active",
            "messages": [],
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "expires_at": (
                datetime.now() + timedelta(hours=self.DEFAULT_EXPIRY_HOURS)
            ).isoformat()
        }

        # 存储到内存
        self._sessions[session_id] = session_data

        # 持久化到数据库（如果可用）
        if self._db:
            try:
                self._db.insert("agent_sessions", {
                    "id": session_id,
                    "user_id": user_id,
                    "agent_type": agent_type,
                    "status": "active",
                    "messages_json": json.dumps([]),
                    "metadata_json": json.dumps(metadata or {}),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "expires_at": (
                        datetime.now() + timedelta(hours=self.DEFAULT_EXPIRY_HOURS)
                    ).isoformat()
                })
            except Exception as e:
                log.warning(f"Failed to persist session to database: {e}")

        log.info(f"Created session {session_id} for user {user_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话

        Args:
            session_id: 会话 ID

        Returns:
            会话数据，不存在或已过期则返回 None
        """
        # 从内存获取
        session = self._sessions.get(session_id)

        # 内存中不存在，尝试从数据库获取
        if session is None and self._db:
            try:
                row = self._db.fetch_one(
                    "SELECT * FROM agent_sessions WHERE id = ?",
                    (session_id,)
                )
                if row:
                    session = {
                        "session_id": row["id"],
                        "user_id": row["user_id"],
                        "agent_type": row["agent_type"],
                        "status": row["status"],
                        "messages": json.loads(row.get("messages_json", "[]")),
                        "metadata": json.loads(row.get("metadata_json", "{}")),
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "expires_at": row.get("expires_at")
                    }
                    # 缓存到内存
                    self._sessions[session_id] = session
            except Exception as e:
                log.warning(f"Failed to fetch session from database: {e}")

        if session is None:
            return None

        # 检查是否过期
        if self._is_expired(session):
            self.expire_session(session_id)
            return None

        return session

    def update_session(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """更新会话

        Args:
            session_id: 会话 ID
            updates: 更新数据

        Returns:
            是否更新成功
        """
        session = self.get_session(session_id)
        if session is None:
            return False

        # 更新字段
        for key, value in updates.items():
            if key in ["status", "metadata", "agent_type"]:
                session[key] = value

        session["updated_at"] = datetime.now().isoformat()

        # 更新内存
        self._sessions[session_id] = session

        # 更新数据库
        if self._db:
            try:
                self._db.update(
                    "agent_sessions",
                    {
                        "status": session["status"],
                        "metadata_json": json.dumps(session["metadata"]),
                        "updated_at": session["updated_at"]
                    },
                    "id = ?",
                    (session_id,)
                )
            except Exception as e:
                log.warning(f"Failed to update session in database: {e}")

        return True

    def save_message(
        self,
        session_id: str,
        message: Dict[str, Any]
    ) -> bool:
        """保存消息到会话

        Args:
            session_id: 会话 ID
            message: 消息数据

        Returns:
            是否保存成功
        """
        session = self.get_session(session_id)
        if session is None:
            return False

        # 添加时间戳
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()

        # 添加消息
        session["messages"].append(message)
        session["updated_at"] = datetime.now().isoformat()

        # 更新内存
        self._sessions[session_id] = session

        # 更新数据库
        if self._db:
            try:
                self._db.update(
                    "agent_sessions",
                    {
                        "messages_json": json.dumps(session["messages"]),
                        "updated_at": session["updated_at"]
                    },
                    "id = ?",
                    (session_id,)
                )
            except Exception as e:
                log.warning(f"Failed to save message to database: {e}")

        return True

    def get_messages(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """获取会话消息

        Args:
            session_id: 会话 ID
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            消息列表
        """
        session = self.get_session(session_id)
        if session is None:
            return []

        messages = session["messages"]
        return messages[offset:offset + limit]

    def delete_session(self, session_id: str) -> bool:
        """删除会话

        Args:
            session_id: 会话 ID

        Returns:
            是否删除成功
        """
        # 从内存删除
        if session_id in self._sessions:
            del self._sessions[session_id]

        # 从数据库删除
        if self._db:
            try:
                self._db.delete("agent_sessions", "id = ?", (session_id,))
            except Exception as e:
                log.warning(f"Failed to delete session from database: {e}")

        log.info(f"Deleted session {session_id}")
        return True

    def expire_session(self, session_id: str) -> bool:
        """过期会话

        Args:
            session_id: 会话 ID

        Returns:
            是否操作成功
        """
        return self.update_session(session_id, {"status": "expired"})

    def list_user_sessions(
        self,
        user_id: int,
        status: Optional[str] = "active"
    ) -> List[Dict[str, Any]]:
        """列出用户的会话

        Args:
            user_id: 用户 ID
            status: 状态过滤

        Returns:
            会话列表
        """
        sessions = []

        # 从内存查找
        for session_id, session in self._sessions.items():
            if session["user_id"] == user_id:
                if status is None or session["status"] == status:
                    # 检查是否过期
                    if not self._is_expired(session):
                        sessions.append(session)

        # 从数据库查找
        if self._db:
            try:
                query = "SELECT * FROM agent_sessions WHERE user_id = ?"
                params = [user_id]

                if status:
                    query += " AND status = ?"
                    params.append(status)

                query += " ORDER BY updated_at DESC"

                rows = self._db.fetch_all(query, tuple(params))
                for row in rows:
                    session_id = row["id"]
                    # 避免重复
                    if not any(s["session_id"] == session_id for s in sessions):
                        session = {
                            "session_id": row["id"],
                            "user_id": row["user_id"],
                            "agent_type": row["agent_type"],
                            "status": row["status"],
                            "messages": json.loads(row.get("messages_json", "[]")),
                            "metadata": json.loads(row.get("metadata_json", "{}")),
                            "created_at": row["created_at"],
                            "updated_at": row["updated_at"],
                            "expires_at": row.get("expires_at")
                        }
                        if not self._is_expired(session):
                            sessions.append(session)
            except Exception as e:
                log.warning(f"Failed to list sessions from database: {e}")

        return sessions

    def cleanup_expired_sessions(self) -> int:
        """清理过期会话

        Returns:
            清理的会话数量
        """
        cleaned = 0

        # 清理内存中的过期会话
        expired_ids = []
        for session_id, session in self._sessions.items():
            if self._is_expired(session):
                expired_ids.append(session_id)

        for session_id in expired_ids:
            self.delete_session(session_id)
            cleaned += 1

        # 清理数据库中的过期会话
        if self._db:
            try:
                self._db.delete(
                    "agent_sessions",
                    "expires_at < ? AND status = 'active'",
                    (datetime.now().isoformat(),)
                )
            except Exception as e:
                log.warning(f"Failed to cleanup expired sessions from database: {e}")

        if cleaned > 0:
            log.info(f"Cleaned up {cleaned} expired sessions")

        return cleaned

    def get_session_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """获取会话统计

        Args:
            user_id: 用户 ID（可选）

        Returns:
            统计信息
        """
        sessions = list(self._sessions.values())

        if user_id:
            sessions = [s for s in sessions if s["user_id"] == user_id]

        active = sum(1 for s in sessions if s["status"] == "active")
        expired = sum(1 for s in sessions if s["status"] == "expired")
        total_messages = sum(len(s.get("messages", [])) for s in sessions)

        return {
            "total_sessions": len(sessions),
            "active_sessions": active,
            "expired_sessions": expired,
            "total_messages": total_messages
        }

    def _is_expired(self, session: Dict[str, Any]) -> bool:
        """检查会话是否过期

        Args:
            session: 会话数据

        Returns:
            是否过期
        """
        expires_at = session.get("expires_at")
        if expires_at:
            try:
                exp_time = datetime.fromisoformat(expires_at)
                return datetime.now() > exp_time
            except (ValueError, TypeError):
                return False
        return False


# 全局实例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取 SessionManager 单例

    Returns:
        SessionManager 实例
    """
    global _session_manager
    if _session_manager is None:
        try:
            from models.db import get_db
            db = get_db()
            _session_manager = SessionManager(db)
        except Exception:
            _session_manager = SessionManager()
    return _session_manager
