from __future__ import annotations

import os
import time
from typing import Any

_REDIS_CLIENT: Any | None = None


def _redis_url() -> str:
    return os.getenv("BLANK_REDIS_URL", "redis://127.0.0.1:6379/0").strip()


def get_redis() -> Any | None:
    """返回 Redis 客户端实例。测试可显式设置 BLANK_REDIS_URL 为空来禁用。"""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    url = _redis_url()
    if not url:
        return None
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError("Redis 模式需要安装 redis。请执行 pip install redis") from exc
    _REDIS_CLIENT = redis.from_url(url, decode_responses=True)
    return _REDIS_CLIENT


def redis_rate_limit_check(key: str, limit: int, window_seconds: int) -> bool:
    """基于 Redis Sorted Set 的滑动窗口速率限制。返回 True 表示允许通过。"""
    r = get_redis()
    if r is None:
        return False
    now = time.time()
    window_start = now - window_seconds
    member = f"{now}:{id(object())}"
    script = """
    redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1])
    local current = redis.call('ZCARD', KEYS[1])
    if current >= tonumber(ARGV[2]) then
        redis.call('EXPIRE', KEYS[1], ARGV[3])
        return 0
    end
    redis.call('ZADD', KEYS[1], ARGV[4], ARGV[5])
    redis.call('EXPIRE', KEYS[1], ARGV[3])
    return 1
    """
    return bool(r.eval(script, 1, key, window_start, limit, window_seconds, now, member))


def clear_redis_rate_limit(key: str) -> None:
    r = get_redis()
    if r is not None:
        r.delete(key)
