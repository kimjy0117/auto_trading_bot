import redis.asyncio as redis

from backend.config import get_settings

settings = get_settings()

redis_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global redis_pool
    if redis_pool is None:
        redis_pool = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return redis_pool


async def close_redis():
    global redis_pool
    if redis_pool:
        await redis_pool.close()
        redis_pool = None


async def delete_pattern(pattern: str):
    r = await get_redis()
    cursor = 0
    while True:
        cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            await r.delete(*keys)
        if cursor == 0:
            break
