"""
连接池管理 - 多连接并存 + 独立工作区

核心模型变更：从"单连接"到"连接池 + 独立工作区"

架构：
  ConnectionPool
    ├── _connections: Dict[str, ArthasConnection]  # 多个连接并存
    ├── _focus_conn_id: Optional[str]              # 当前焦点连接
    ├── _workspaces: Dict[str, WorkspaceState]     # per-connection 工作区
    └── _heartbeat_thread: Thread                  # 后台心跳守护

关键特性：
  - 多连接并存：每个连接独立 port-forward，切焦点不关旧连接
  - 焦点切换 = 视图切换（零延迟，无网络开销）
  - per-connection 工作区状态完整保留
  - 后台心跳守护，自动检测连接健康
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


class ConnectionState(Enum):
    """连接池中的连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    POD_CONNECTED = "pod_connected"
    ARTHAS_UPGRADING = "arthas_upgrading"
    ARTHAS_READY = "arthas_ready"
    FAILED = "failed"
    DEGRADED = "degraded"      # 心跳超时 > 3 次
    DEAD = "dead"              # 心跳超时 > 10 次


class WorkspaceTab(Enum):
    """工作区 Tab 类型"""
    MONITOR = "monitor"
    SAMPLING = "sampling"
    ARTHAS = "arthas"
    TERMINAL = "terminal"
    FILES = "files"
    HISTORY = "history"
    HOTFIX = "hotfix"
    DIAGNOSIS = "diagnosis"


@dataclass
class WorkspaceState:
    """per-connection 工作区状态"""
    active_tab: WorkspaceTab = WorkspaceTab.MONITOR
    sub_tab: str = ""           # 子 Tab（如监控的 概览/指标/进程）
    scroll_positions: Dict[str, int] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)  # 缓存的数据
    command_history: List[str] = field(default_factory=list)  # Arthas 命令历史
    
    def save_scroll(self, element_id: str, position: int):
        """保存滚动位置"""
        self.scroll_positions[element_id] = position
    
    def get_scroll(self, element_id: str) -> int:
        """获取滚动位置"""
        return self.scroll_positions.get(element_id, 0)
    
    def set_data(self, key: str, value: Any):
        """缓存数据"""
        self.data[key] = value
    
    def get_data(self, key: str, default: Any = None) -> Any:
        """获取缓存数据"""
        return self.data.get(key, default)


@dataclass
class PoolConnection:
    """连接池中的连接条目"""
    conn_id: str
    conn: Any  # ArthasConnection
    user_id: Optional[int] = None
    state: ConnectionState = ConnectionState.DISCONNECTED
    last_heartbeat: Optional[float] = None
    heartbeat_failures: int = 0
    auto_reconnect: bool = False
    mcp_available: bool = False
    level: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    @property
    def is_alive(self) -> bool:
        """连接是否存活"""
        return self.state in (
            ConnectionState.ARTHAS_READY,
            ConnectionState.POD_CONNECTED,
            ConnectionState.CONNECTING,
            ConnectionState.ARTHAS_UPGRADING,
        )
    
    @property
    def is_focused(self) -> bool:
        """是否为焦点连接（由 ConnectionPool 设置）"""
        return False  # 由 ConnectionPool 统一判断
    
    def to_dict(self) -> dict:
        """转换为字典（用于 API 响应）"""
        return {
            "conn_id": self.conn_id,
            "state": self.state.value,
            "user_id": self.user_id,
            "is_alive": self.is_alive,
            "last_heartbeat": self.last_heartbeat,
            "heartbeat_failures": self.heartbeat_failures,
            "auto_reconnect": self.auto_reconnect,
            "mcp_available": self.mcp_available,
            "level": self.level,
            "created_at": self.created_at,
            # 从 conn 对象提取信息
            "local_port": getattr(self.conn, 'local_port', 0),
            "java_pid": getattr(self.conn, 'java_pid', None),
            "arthas_version": getattr(self.conn, 'arthas_version', None),
            "arthas_address": getattr(self.conn, 'arthas_address', None),
            "pod_name": getattr(getattr(self.conn, 'target', None), 'pod_name', ''),
            "namespace": getattr(getattr(self.conn, 'target', None), 'namespace', ''),
            "cluster_name": getattr(getattr(self.conn, 'target', None), 'cluster_name', ''),
        }


class ConnectionPool:
    """连接池 - 管理多个并存的连接
    
    核心职责：
    1. 管理多个 ArthasConnection 的生命周期
    2. 提供焦点切换（纯元数据操作，零延迟）
    3. 维护 per-connection 工作区状态
    4. 后台心跳守护，检测连接健康
    
    使用方式：
        pool = ConnectionPool(state_manager)
        pool.add("cluster/ns/pod", conn, user_id=1)
        pool.set_focus("cluster/ns/pod")  # 零延迟切换
        focused = pool.get_focused()
    """
    
    def __init__(self, state_manager=None, max_connections: int = 20,
                 workspace_store=None):
        self._connections: Dict[str, PoolConnection] = {}
        self._focus_conn_id: Optional[str] = None
        self._state_manager = state_manager
        self._max_connections = max_connections
        self._lock = threading.RLock()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()
        self._heartbeat_interval = 5  # 秒
        self._active_conns: set = set()  # 当前活跃连接集合
        if workspace_store is not None:
            self._workspace_store = workspace_store
        else:
            from .workspace_store import WorkspaceStore
            self._workspace_store = WorkspaceStore()
        
        # 回调函数
        self._on_state_change: Optional[Callable[[str, ConnectionState, ConnectionState], None]] = None
        self._on_connection_added: Optional[Callable[[str], None]] = None
        self._on_connection_removed: Optional[Callable[[str], None]] = None
        self._on_focus_changed: Optional[Callable[[Optional[str], Optional[str]], None]] = None
    
    # ── 连接管理 ──────────────────────────────────────────────────────────────
    
    def add(self, conn_id: str, conn: Any, user_id: Optional[int] = None,
            mcp_available: bool = False, level: Optional[str] = None) -> bool:
        """添加连接到池中
        
        Args:
            conn_id: 连接 ID (格式: cluster/namespace/pod)
            conn: ArthasConnection 对象
            user_id: 用户 ID
            mcp_available: MCP 端点是否可用
            
        Returns:
            bool: 是否成功添加
        """
        with self._lock:
            if conn_id in self._connections:
                log.warning("Connection %s already exists in pool", conn_id)
                return False
            
            if len(self._connections) >= self._max_connections:
                log.warning("Connection pool full (%d/%d)", 
                           len(self._connections), self._max_connections)
                return False
            
            pool_conn = PoolConnection(
                conn_id=conn_id,
                conn=conn,
                user_id=user_id,
                state=ConnectionState.ARTHAS_READY,  # 假设添加时已就绪
                mcp_available=mcp_available,
                level=level,
            )
            self._connections[conn_id] = pool_conn
            
            # 确保 workspace 已创建
            self._workspace_store.get_or_create(conn_id)
            
            log.info("Connection added to pool: %s (total: %d)", 
                    conn_id, len(self._connections))
            
            if self._on_connection_added:
                try:
                    self._on_connection_added(conn_id)
                except Exception as e:
                    log.debug("on_connection_added callback error: %s", e)
            
            return True
    
    def upsert(self, conn_id: str, conn: Any, user_id: Optional[int] = None,
               mcp_available: bool = False,
               state: ConnectionState = ConnectionState.ARTHAS_READY,
               level: Optional[str] = None) -> bool:
        """Add a connection or replace the runtime object for an existing one.

        Returns True when a new pool entry is created, False when an existing
        entry is updated in place.
        """
        with self._lock:
            pool_conn = self._connections.get(conn_id)
            if pool_conn:
                pool_conn.conn = conn
                pool_conn.user_id = user_id
                pool_conn.mcp_available = mcp_available
                pool_conn.state = state
                pool_conn.level = level
                pool_conn.heartbeat_failures = 0
                pool_conn.last_heartbeat = None
                self._workspace_store.get_or_create(conn_id)
                return False

            if len(self._connections) >= self._max_connections:
                log.warning("Connection pool full (%d/%d)",
                            len(self._connections), self._max_connections)
                return False

            self._connections[conn_id] = PoolConnection(
                conn_id=conn_id,
                conn=conn,
                user_id=user_id,
                state=state,
                mcp_available=mcp_available,
                level=level,
            )
            self._workspace_store.get_or_create(conn_id)

            if self._on_connection_added:
                try:
                    self._on_connection_added(conn_id)
                except Exception as e:
                    log.debug("on_connection_added callback error: %s", e)

            return True

    def remove(self, conn_id: str) -> bool:
        """从池中移除连接（断开 + 清理）
        
        Args:
            conn_id: 连接 ID
            
        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            pool_conn = self._connections.pop(conn_id, None)
            if not pool_conn:
                log.warning("Connection %s not found in pool", conn_id)
                return False
            
            # 断开连接
            try:
                pool_conn.conn.disconnect()
            except Exception as e:
                log.debug("Disconnect error for %s: %s", conn_id, e)
            
            # 如果是焦点连接，切换到下一个
            if self._focus_conn_id == conn_id:
                self._focus_conn_id = None
                # 自动切换到下一个连接
                if self._connections:
                    next_id = next(iter(self._connections.keys()))
                    self._focus_conn_id = next_id
                    log.info("Focus auto-switched to: %s", next_id)
            
            log.info("Connection removed from pool: %s (total: %d)", 
                    conn_id, len(self._connections))
            
            if self._on_connection_removed:
                try:
                    self._on_connection_removed(conn_id)
                except Exception as e:
                    log.debug("on_connection_removed callback error: %s", e)
            
            return True
    
    def get(self, conn_id: str) -> Optional[PoolConnection]:
        """获取指定连接
        
        Args:
            conn_id: 连接 ID
            
        Returns:
            PoolConnection 或 None
        """
        return self._connections.get(conn_id)
    
    def get_connection(self, conn_id: str) -> Optional[Any]:
        """获取 ArthasConnection 对象
        
        Args:
            conn_id: 连接 ID
            
        Returns:
            ArthasConnection 或 None
        """
        pool_conn = self._connections.get(conn_id)
        return pool_conn.conn if pool_conn else None
    
    # ── 焦点管理 ──────────────────────────────────────────────────────────────
    
    def set_focus(self, conn_id: str) -> bool:
        """切换焦点（纯元数据操作，零延迟）
        
        这是连接池的核心优势：切换焦点不触发任何网络操作，
        只是改变当前活跃连接的指针。
        
        Args:
            conn_id: 要切换到的连接 ID
            
        Returns:
            bool: 是否成功切换
        """
        with self._lock:
            if conn_id not in self._connections:
                log.warning("Cannot focus %s: not in pool", conn_id)
                return False
            
            old_focus = self._focus_conn_id
            self._focus_conn_id = conn_id
            
            if old_focus != conn_id:
                log.info("Focus changed: %s -> %s", old_focus, conn_id)
                
                if self._on_focus_changed:
                    try:
                        self._on_focus_changed(old_focus, conn_id)
                    except Exception as e:
                        log.debug("on_focus_changed callback error: %s", e)
            
            return True
    
    def get_focused(self) -> Optional[PoolConnection]:
        """获取当前焦点连接
        
        Returns:
            PoolConnection 或 None
        """
        if self._focus_conn_id:
            return self._connections.get(self._focus_conn_id)
        return None
    
    def get_focused_id(self) -> Optional[str]:
        """获取当前焦点连接 ID
        
        Returns:
            连接 ID 或 None
        """
        return self._focus_conn_id
    
    def get_workspace(self, conn_id: str) -> Optional[WorkspaceState]:
        """获取 per-connection 工作区状态
        
        Args:
            conn_id: 连接 ID
            
        Returns:
            WorkspaceState 或 None
        """
        return self._workspace_store.get(conn_id)

    # ── 连接生命周期协议 (acquire/release) ──────────────────────────────────

    def acquire(self, conn_id: str) -> bool:
        """标记连接为活跃状态，阻止清理程序回收

        Args:
            conn_id: 连接 ID

        Returns:
            bool: 是否成功标记
        """
        with self._lock:
            if conn_id not in self._connections:
                return False
            self._active_conns.add(conn_id)
            return True

    def release(self, conn_id: str) -> bool:
        """释放连接活跃标记，允许清理

        Args:
            conn_id: 连接 ID

        Returns:
            bool: 连接是否存在
        """
        with self._lock:
            if conn_id not in self._connections:
                return False
            self._active_conns.discard(conn_id)
            return True

    def is_active(self, conn_id: str) -> bool:
        """检查连接是否标记为活跃"""
        with self._lock:
            return conn_id in self._active_conns

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._active_conns)
    
    # ── 连接列表 ──────────────────────────────────────────────────────────────
    
    def list_all(self) -> List[dict]:
        """列出所有连接及其状态
        
        Returns:
            连接列表
        """
        result = []
        for conn_id, pool_conn in self._connections.items():
            info = pool_conn.to_dict()
            info['is_focused'] = (conn_id == self._focus_conn_id)
            result.append(info)
        return result
    
    def list_by_state(self, state: ConnectionState) -> List[dict]:
        """按状态过滤连接
        
        Args:
            state: 要过滤的连接状态
            
        Returns:
            符合条件的连接列表
        """
        return [c for c in self.list_all() if c['state'] == state.value]
    
    def count(self) -> int:
        """获取连接总数"""
        return len(self._connections)

    def stats(self) -> dict:
        """结构化计数器

        Returns:
            dict: {
                "total_connections": int,
                "active_connections": int,
                "idle_connections": int,
                "states": Dict[str, int],
                "max_connections": int,
                "focus_id": str | None,
                "workspace_count": int,
            }
        """
        with self._lock:
            state_counts: Dict[str, int] = {}
            for pc in self._connections.values():
                key = pc.state.value
                state_counts[key] = state_counts.get(key, 0) + 1

            return {
                "total_connections": len(self._connections),
                "active_connections": len(self._active_conns),
                "idle_connections": len(self._connections) - len(self._active_conns),
                "states": state_counts,
                "max_connections": self._max_connections,
                "focus_id": self._focus_conn_id,
                "workspace_count": self._workspace_store.count(),
            }
    
    # ── 连接状态更新 ──────────────────────────────────────────────────────────
    
    def update_state(self, conn_id: str, new_state: ConnectionState) -> bool:
        """更新连接状态
        
        Args:
            conn_id: 连接 ID
            new_state: 新状态
            
        Returns:
            bool: 是否成功更新
        """
        with self._lock:
            pool_conn = self._connections.get(conn_id)
            if not pool_conn:
                return False
            
            old_state = pool_conn.state
            if old_state == new_state:
                return True
            
            pool_conn.state = new_state
            
            # 重置心跳失败计数（状态恢复时）
            if new_state in (ConnectionState.ARTHAS_READY, ConnectionState.POD_CONNECTED):
                pool_conn.heartbeat_failures = 0
            
            log.info("Connection %s state: %s -> %s", 
                    conn_id, old_state.value, new_state.value)
            
            # 通过状态管理器持久化
            if self._state_manager:
                try:
                    from .connection_state import ConnectionState as CS
                    state_map = {
                        ConnectionState.DISCONNECTED: CS.DISCONNECTED,
                        ConnectionState.CONNECTING: CS.POD_SELECTED,
                        ConnectionState.POD_CONNECTED: CS.POD_CHECKED,
                        ConnectionState.ARTHAS_UPGRADING: CS.START_AGENT,
                        ConnectionState.ARTHAS_READY: CS.READY,
                        ConnectionState.FAILED: CS.FAILED,
                        ConnectionState.DEGRADED: CS.READY,  # DEGRADED 映射到 READY
                        ConnectionState.DEAD: CS.FAILED,
                    }
                    cs_state = state_map.get(new_state, CS.DISCONNECTED)
                    self._state_manager.transition_state(
                        conn_id, old_state, cs_state,
                        message=f"Pool state: {new_state.value}"
                    )
                except Exception as e:
                    log.debug("State manager update error: %s", e)
            
            return True
    
    # ── 心跳机制 ──────────────────────────────────────────────────────────────
    
    def start_heartbeat(self, interval: int = 5):
        """启动心跳守护线程
        
        Args:
            interval: 心跳间隔（秒）
        """
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            log.info("Heartbeat thread already running")
            return
        
        self._heartbeat_interval = interval
        self._stop_heartbeat.clear()
        
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="connection-pool-heartbeat",
        )
        self._heartbeat_thread.start()
        log.info("Heartbeat started (interval: %ds)", interval)
    
    def stop_heartbeat(self):
        """停止心跳守护线程"""
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
            self._heartbeat_thread = None
            log.info("Heartbeat stopped")
    
    def _heartbeat_loop(self):
        """心跳循环"""
        while not self._stop_heartbeat.wait(self._heartbeat_interval):
            try:
                self._check_all_connections()
                self.cleanup_dead()
            except Exception as e:
                log.error("Heartbeat loop error: %s", e, exc_info=True)

    def _check_all_connections(self):
        """检查所有连接的健康状态

        安全策略（防止快照后连接被移除导致的竞态）：
          1. 快照在锁内完成
          2. 每项处理前快速验证连接仍存在于池中
          3. is_alive 超时由底层控制，不阻塞心跳循环
        """
        with self._lock:
            snapshot = list(self._connections.items())

        for conn_id, pool_conn in snapshot:
            try:
                # 跳过快照后被移除的连接（静默忽略）
                if conn_id not in self._connections:
                    continue

                # 跳过非活跃连接
                if pool_conn.state in (ConnectionState.DISCONNECTED, ConnectionState.DEAD):
                    continue

                # 检查连接存活（可能 hang，在锁外执行）
                alive = pool_conn.conn.is_alive()
                pool_conn.last_heartbeat = time.time()

                if alive:
                    if pool_conn.heartbeat_failures > 0:
                        log.info("Connection %s recovered (failures reset)", conn_id)
                    pool_conn.heartbeat_failures = 0

                    if pool_conn.state == ConnectionState.DEGRADED:
                        self.update_state(conn_id, ConnectionState.ARTHAS_READY)
                else:
                    pool_conn.heartbeat_failures += 1
                    log.warning("Connection %s heartbeat failed (%d/%d)",
                              conn_id, pool_conn.heartbeat_failures, 10)

                    if pool_conn.heartbeat_failures >= 10:
                        self.update_state(conn_id, ConnectionState.DEAD)
                        log.error("Connection %s marked DEAD", conn_id)
                    elif pool_conn.heartbeat_failures >= 3:
                        if pool_conn.state != ConnectionState.DEGRADED:
                            self.update_state(conn_id, ConnectionState.DEGRADED)

            except Exception as e:
                log.error("Heartbeat check failed for %s: %s", conn_id, e)
    
    # ── 回调注册 ──────────────────────────────────────────────────────────────
    
    def on_state_change(self, callback: Callable[[str, ConnectionState, ConnectionState], None]):
        """注册状态变更回调"""
        self._on_state_change = callback
    
    def on_connection_added(self, callback: Callable[[str], None]):
        """注册连接添加回调"""
        self._on_connection_added = callback
    
    def on_connection_removed(self, callback: Callable[[str], None]):
        """注册连接移除回调"""
        self._on_connection_removed = callback
    
    def on_focus_changed(self, callback: Callable[[Optional[str], Optional[str]], None]):
        """注册焦点变更回调"""
        self._on_focus_changed = callback
    
    # ── 清理 ──────────────────────────────────────────────────────────────────
    
    def disconnect_all(self):
        """断开所有连接"""
        with self._lock:
            for conn_id in list(self._connections.keys()):
                self.remove(conn_id)
            log.info("All connections disconnected")
    
    def cleanup_dead(self) -> int:
        """清理 DEAD 状态的连接（快照模式，避免全周期持锁）
        活跃连接不会被清理。
        
        Returns:
            清理的连接数量
        """
        with self._lock:
            dead_ids = [
                conn_id for conn_id, pool_conn in self._connections.items()
                if pool_conn.state == ConnectionState.DEAD
                and conn_id not in self._active_conns
            ]
        
        cleaned = 0
        for conn_id in dead_ids:
            if self.remove(conn_id):
                cleaned += 1
        
        if cleaned:
            log.info("Cleaned up %d dead connections (attempted %d)", cleaned, len(dead_ids))
        
        return cleaned
