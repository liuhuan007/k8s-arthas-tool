"""In-memory TTL cache for reducing repeated DB queries."""
import threading
import time
import logging
from functools import wraps
from typing import Any, Optional

log = logging.getLogger(__name__)


class TTLCache:
    """Thread-safe in-memory cache with per-key TTL."""

    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expire_at)
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Return cached value if present and not expired, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expire_at = entry
            if time.time() > expire_at:
                # Expired -- remove lazily
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: int = None):
        """Store a value with an optional per-key TTL (seconds)."""
        if ttl is None:
            ttl = self._default_ttl
        expire_at = time.time() + ttl
        with self._lock:
            # Evict oldest entries when at capacity
            if len(self._store) >= self._max_size and key not in self._store:
                self._evict_expired()
            if len(self._store) >= self._max_size and key not in self._store:
                # Still full after evicting expired -- drop oldest by expire_at
                oldest_key = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest_key]
            self._store[key] = (value, expire_at)

    def delete(self, key: str):
        """Remove a specific key."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        """Remove all entries."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def invalidate_prefix(self, prefix: str):
        """Remove all keys starting with prefix."""
        with self._lock:
            keys_to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._store[k]

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._store),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0,
                "default_ttl": self._default_ttl,
            }

    def _evict_expired(self):
        """Remove all expired entries (caller must hold _lock)."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]


# ── Global cache instances ─────────────────────────────────────────────────────
query_cache = TTLCache(default_ttl=300, max_size=500)    # DB query results (5 min)
config_cache = TTLCache(default_ttl=3600, max_size=50)    # Config values (1 h)


# ── Cache decorator ───────────────────────────────────────────────────────────

def cached(cache_instance: TTLCache, ttl: int = None, key_prefix: str = ''):
    """Decorator to cache function return values.

    Usage::

        @cached(query_cache, ttl=60, key_prefix='clusters')
        def get_clusters(user_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from function name + args (skip first 'self' arg)
            sig_args = args[1:] if args and hasattr(args[0], '__class__') else args
            cache_key = (
                f"{key_prefix or func.__name__}:"
                f"{hash((sig_args, tuple(sorted(kwargs.items()))))}"
            )
            result = cache_instance.get(cache_key)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            if result is not None:
                cache_instance.set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator


# ── Invalidation helpers ──────────────────────────────────────────────────────

def invalidate_connection_cache(conn_id: str = None):
    """Invalidate connection-related cache entries."""
    if conn_id:
        query_cache.delete(f"connection:{conn_id}")
    query_cache.invalidate_prefix("connections:")
    query_cache.invalidate_prefix("list_pod_connections:")
    query_cache.invalidate_prefix("list_arthas_connections:")


def invalidate_cluster_cache():
    """Invalidate cluster-related cache entries."""
    query_cache.invalidate_prefix("clusters:")
    query_cache.invalidate_prefix("list_clusters:")
    config_cache.invalidate_prefix("clusters:")


def invalidate_skill_cache():
    """Invalidate skill-related cache entries."""
    query_cache.invalidate_prefix("skills:")
    query_cache.invalidate_prefix("list_skills:")
    query_cache.invalidate_prefix("get_skill_stats:")
    query_cache.invalidate_prefix("search_skills:")


def invalidate_task_cache():
    """Invalidate task-related cache entries."""
    query_cache.invalidate_prefix("tasks:")
    query_cache.invalidate_prefix("task_stats:")
