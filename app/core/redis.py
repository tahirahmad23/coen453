from __future__ import annotations

import redis.asyncio as redis

from app.core.config import settings

# Global redis client
_redis_client = None

def get_redis():
    global _redis_client
    if _redis_client is None:
        # If redis_url starts with http, we might need a different approach, 
        # but for now we assume it's a redis:// or rediss:// URL as reported in the error.
        _redis_client = redis.from_url(
            settings.redis_url, 
            decode_responses=True,
            # If there's a token but it's a standard redis URL, it might be the password
            password=settings.redis_token if settings.redis_token and "redis://" in settings.redis_url else None
        )
    return _redis_client

async def redis_get(key: str) -> int | None:
    """Get a Redis key value. Returns None if key doesn't exist."""
    try:
        client = get_redis()
        val = await client.get(key)
        return int(val) if val is not None else None
    except Exception:
        return None

async def redis_set(key: str, value: str, ttl_seconds: int) -> None:
    """Set a Redis key with TTL."""
    try:
        client = get_redis()
        await client.set(key, value, ex=ttl_seconds)
    except Exception:
        pass

async def redis_get_str(key: str) -> str | None:
    """Get a Redis key as string. Returns None if not found."""
    try:
        client = get_redis()
        return await client.get(key)
    except Exception:
        return None

async def redis_delete(key: str) -> None:
    """Delete a Redis key."""
    try:
        client = get_redis()
        await client.delete(key)
    except Exception:
        pass
