"""Key-value store abstraction — Redis khi có REDIS_URL, fallback in-memory.

Vì sao cần fallback: cho phép deploy 1 container duy nhất (Railway/Render free tier)
mà vẫn chạy được, đồng thời khi cắm Redis vào thì app trở thành stateless thật sự
(nhiều instance share chung state). Cùng một interface -> rate_limiter / cost_guard /
history dùng chung, không lặp code (DRY).
"""
from __future__ import annotations

import threading
import time
from typing import Any


class MemoryStore:
    """In-memory store mô phỏng tập lệnh Redis mà app cần. Có TTL + thread-safe."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._expire_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def _expired(self, key: str) -> bool:
        exp = self._expire_at.get(key)
        if exp is not None and exp <= time.time():
            self._data.pop(key, None)
            self._expire_at.pop(key, None)
            return True
        return False

    def ping(self) -> bool:
        return True

    def incr(self, key: str) -> int:
        with self._lock:
            self._expired(key)
            val = int(self._data.get(key, 0)) + 1
            self._data[key] = val
            return val

    def incrbyfloat(self, key: str, amount: float) -> float:
        with self._lock:
            self._expired(key)
            val = float(self._data.get(key, 0.0)) + amount
            self._data[key] = val
            return val

    def get(self, key: str):
        with self._lock:
            if self._expired(key):
                return None
            val = self._data.get(key)
            return None if val is None else str(val)

    def expire(self, key: str, seconds: int) -> None:
        with self._lock:
            if key in self._data:
                self._expire_at[key] = time.time() + seconds

    def rpush(self, key: str, value: str) -> int:
        with self._lock:
            self._expired(key)
            lst = self._data.setdefault(key, [])
            lst.append(value)
            return len(lst)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        with self._lock:
            if self._expired(key):
                return []
            lst = self._data.get(key, [])
            if end == -1:
                return list(lst[start:])
            return list(lst[start:end + 1])


def _build_store():
    """Trả về (client, backend_name)."""
    from .config import settings

    if settings.redis_url:
        try:
            import redis

            client = redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            return client, "redis"
        except Exception:
            # Redis cấu hình nhưng không kết nối được -> degrade sang memory.
            pass
    return MemoryStore(), "memory"


store, backend = _build_store()
