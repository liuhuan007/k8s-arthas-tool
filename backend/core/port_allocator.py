"""
线程安全端口分配器 — kubectl port-forward 端口管理

职责：
  管理 32000-32767 端口段，支持 acquire/release 模式。
  避免 ArthasConnection 类级可变状态导致的端口泄漏问题。

使用方式：
    allocator = PortAllocator()
    port = allocator.acquire()       # 分配（可能抛出 PortExhaustedError）
    allocator.release(port)          # 释放
    allocator.release(port)          # 幂等释放（不会抛异常）
"""
from __future__ import annotations

import itertools
import logging
import threading
from typing import Optional

log = logging.getLogger(__name__)

PF_BASE_PORT = 32000
PF_MAX_PORT = 32767


class PortExhaustedError(RuntimeError):
    def __init__(self, base: int, max_port: int):
        super().__init__(
            f"Port range exhausted: {max_port} maximum reached. "
            f"Restart service or increase PF_MAX_PORT."
        )
        self.base = base
        self.max_port = max_port


class PortAllocator:
    """线程安全端口分配器"""

    def __init__(self, base_port: int = PF_BASE_PORT, max_port: int = PF_MAX_PORT):
        self._base = base_port
        self._max = max_port
        self._used: set = set()
        self._lock = threading.Lock()
        self._counter = itertools.count(base_port)
        self._range_size = max_port - base_port + 1

    def acquire(self) -> int:
        """分配一个可用端口

        Returns:
            可用端口号

        Raises:
            PortExhaustedError: 端口段已耗尽
        """
        with self._lock:
            if len(self._used) >= self._range_size:
                raise PortExhaustedError(self._base, self._max)

            start = self._base + (next(self._counter) % self._range_size)
            for offset in range(self._range_size):
                port = self._base + ((start - self._base + offset) % self._range_size)
                if port not in self._used:
                    self._used.add(port)
                    return port

        raise PortExhaustedError(self._base, self._max)

    def release(self, port: int):
        """释放端口（幂等，线程安全）

        Args:
            port: 要释放的端口号
        """
        with self._lock:
            self._used.discard(port)

    @property
    def in_use(self) -> int:
        """当前已分配的端口数"""
        with self._lock:
            return len(self._used)

    @property
    def available(self) -> int:
        """剩余可用端口数"""
        with self._lock:
            return self._range_size - len(self._used)

    def reset(self):
        """重置所有分配（仅用于测试）"""
        with self._lock:
            self._used.clear()
            self._counter = itertools.count(self._base)

    def stats(self) -> dict:
        """获取分配器统计信息"""
        with self._lock:
            return {
                "base": self._base,
                "max": self._max,
                "in_use": len(self._used),
                "available": self._range_size - len(self._used),
                "capacity": self._range_size,
            }

    def is_allocated(self, port: int) -> bool:
        """检查端口是否已被分配"""
        with self._lock:
            return port in self._used


# 全局默认分配器（单例）
_default_allocator: Optional[PortAllocator] = None


def get_port_allocator(
    base_port: int = PF_BASE_PORT, max_port: int = PF_MAX_PORT,
) -> PortAllocator:
    """获取全局默认分配器"""
    global _default_allocator
    if _default_allocator is None:
        _default_allocator = PortAllocator(base_port=base_port, max_port=max_port)
    return _default_allocator
