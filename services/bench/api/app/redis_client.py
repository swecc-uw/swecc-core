"""Async Redis client for bench-api (rate limits, etc.)."""

from __future__ import annotations

import os
from functools import lru_cache

import redis.asyncio as redis


def redis_url() -> str:
    host = os.getenv("REDIS_HOST", "swecc-redis-instance")
    port = int(os.getenv("REDIS_PORT", "6379"))
    db = int(os.getenv("REDIS_DB", "2"))
    return f"redis://{host}:{port}/{db}"


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.from_url(redis_url(), decode_responses=True)


async def try_claim_run_dispatch(run_id: str, *, ttl_seconds: int = 600) -> bool:
    """Redis SET NX — only one bench-api replica rescues a given run."""
    try:
        client = get_redis()
        claimed = await client.set(
            f"bench:run:dispatch:{run_id}",
            "1",
            nx=True,
            ex=ttl_seconds,
        )
        return bool(claimed)
    except Exception:
        # Prefer making progress when Redis is down (typical single-replica dev).
        return True
