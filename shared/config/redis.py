# shared/services/redis.py
import redis.asyncio as aioredis
from shared.config.settings import settings

redis = None  # глобальный объект подключения


async def init_redis():
    """Инициализация подключения к Redis"""
    global redis
    if redis is None:
        redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
    return redis


async def close_redis():
    """Закрытие подключения к Redis"""
    global redis
    if redis:
        await redis.close()
        redis = None
