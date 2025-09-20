"""
VideoBot Pro - Redis Service
Управление подключениями к Redis и кэшированием
"""

import asyncio
import json
import structlog
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from shared.config.settings import settings

logger = structlog.get_logger(__name__)


class RedisService:
    """Сервис для работы с Redis"""

    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        self._initialized = False
        self._health_status = False

        # Метрики
        self.operation_count = 0
        self.error_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.last_health_check: Optional[datetime] = None

    async def initialize(self):
        """Инициализация Redis подключения"""
        if self._initialized:
            return
        try:
            logger.info("Initializing Redis service...")

            self.client = redis.Redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await self.client.ping()

            self._pubsub = None
            self._initialized = True
            self._health_status = True
            logger.info("Redis service initialized successfully")
        except Exception as e:
            self._health_status = False
            logger.error(f"Failed to initialize Redis service: {e}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """Проверка состояния Redis"""
        try:
            if not self.client:
                return {"status": "not_initialized"}

            start_time = asyncio.get_event_loop().time()
            pong = await self.client.ping()
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000

            info = await self.client.info()
            memory_info = {
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_peak": info.get("used_memory_peak", 0),
                "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
            }

            self._health_status = pong is True
            self.last_health_check = datetime.utcnow()

            return {
                "status": "healthy" if self._health_status else "unhealthy",
                "response_time_ms": round(response_time, 2),
                "memory": memory_info,
                "connected_clients": info.get("connected_clients", 0),
                "operations_total": self.operation_count,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "hit_ratio": round(
                    self.cache_hits / (self.cache_hits + self.cache_misses + 1) * 100, 2
                ),
                "error_count": self.error_count,
                "last_check": self.last_health_check.isoformat(),
            }
        except Exception as e:
            self._health_status = False
            logger.error(f"Redis health check failed: {e}")
            return {"status": "unhealthy", "error": str(e), "last_check": datetime.utcnow().isoformat()}

    def is_healthy(self) -> bool:
        """Проверить состояние сервиса"""
        return self._health_status and self._initialized

    def _get_key(self, key: str) -> str:
        """Добавить prefix к ключу"""
        return f"{settings.REDIS_PREFIX}{key}"

    # ------------------------------
    # CRUD операции
    # ------------------------------

    async def get(self, key: str, default: Any = None) -> Any:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            value = await self.client.get(full_key)
            if value is None:
                self.cache_misses += 1
                return default
            self.cache_hits += 1
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis GET operation failed for key {key}: {e}")
            return default

    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            if not isinstance(value, str):
                value = json.dumps(value, default=str)
            expire_time = expire or settings.REDIS_EXPIRE_TIME
            return await self.client.set(full_key, value, ex=expire_time)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis SET operation failed for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            result = await self.client.delete(full_key)
            return bool(result)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis DELETE operation failed for key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            result = await self.client.exists(full_key)
            return bool(result)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis EXISTS operation failed for key {key}: {e}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            result = await self.client.expire(full_key, seconds)
            return bool(result)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis EXPIRE operation failed for key {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            return await self.client.ttl(full_key)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis TTL operation failed for key {key}: {e}")
            return -1

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            return await self.client.incrby(full_key, amount)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis INCRBY operation failed for key {key}: {e}")
            return None

    async def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            return await self.client.decrby(full_key, amount)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis DECRBY operation failed for key {key}: {e}")
            return None

    # ------------------------------
    # Методы работы со списками
    # ------------------------------

    async def list_push(self, key: str, *values: Any, left: bool = True) -> Optional[int]:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            serialized_values = [
                v if isinstance(v, str) else json.dumps(v, default=str) for v in values
            ]
            if left:
                return await self.client.lpush(full_key, *serialized_values)
            return await self.client.rpush(full_key, *serialized_values)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis LIST_PUSH operation failed for key {key}: {e}")
            return None

    async def list_pop(self, key: str, left: bool = True) -> Any:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            result = await self.client.lpop(full_key) if left else await self.client.rpop(full_key)
            if result is None:
                return None
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis LIST_POP operation failed for key {key}: {e}")
            return None

    async def list_length(self, key: str) -> int:
        try:
            self.operation_count += 1
            return await self.client.llen(self._get_key(key))
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis LLEN operation failed for key {key}: {e}")
            return 0

    async def list_range(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            results = await self.client.lrange(full_key, start, end)
            parsed_results = []
            for r in results:
                try:
                    parsed_results.append(json.loads(r))
                except (json.JSONDecodeError, TypeError):
                    parsed_results.append(r)
            return parsed_results
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis LRANGE operation failed for key {key}: {e}")
            return []

# ------------------------------
# Множества (sets)
# ------------------------------

    async def set_add(self, key: str, *values: Any) -> Optional[int]:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            serialized_values = [
                v if isinstance(v, str) else json.dumps(v, default=str) for v in values
            ]
            return await self.client.sadd(full_key, *serialized_values)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis SADD operation failed for key {key}: {e}")
            return None

    async def set_remove(self, key: str, *values: Any) -> Optional[int]:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            serialized_values = [
                v if isinstance(v, str) else json.dumps(v, default=str) for v in values
            ]
            return await self.client.srem(full_key, *serialized_values)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis SREM operation failed for key {key}: {e}")
            return None

    async def set_members(self, key: str) -> List[Any]:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            results = await self.client.smembers(full_key)
            parsed_results = []
            for r in results:
                try:
                    parsed_results.append(json.loads(r))
                except (json.JSONDecodeError, TypeError):
                    parsed_results.append(r)
            return parsed_results
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis SMEMBERS operation failed for key {key}: {e}")
            return []

# ------------------------------
# Хеши (hashes)
# ------------------------------

    async def hash_set(self, key: str, field: str, value: Any) -> bool:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            if not isinstance(value, str):
                value = json.dumps(value, default=str)
            result = await self.client.hset(full_key, field, value)
            return bool(result)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis HSET operation failed for key {key}, field {field}: {e}")
            return False

    async def hash_get(self, key: str, field: str, default: Any = None) -> Any:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            result = await self.client.hget(full_key, field)
            if result is None:
                self.cache_misses += 1
                return default
            self.cache_hits += 1
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis HGET operation failed for key {key}, field {field}: {e}")
            return default

    async def hash_get_all(self, key: str) -> Dict[str, Any]:
        try:
            self.operation_count += 1
            full_key = self._get_key(key)
            results = await self.client.hgetall(full_key)
            parsed_results = {}
            for field, value in results.items():
                try:
                    parsed_results[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    parsed_results[field] = value
            return parsed_results
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis HGETALL operation failed for key {key}: {e}")
            return {}

# ------------------------------
# Pub/Sub
# ------------------------------

    async def publish(self, channel: str, message: Any) -> Optional[int]:
        try:
            self.operation_count += 1
            full_channel = self._get_key(f"channel:{channel}")
            if not isinstance(message, str):
                message = json.dumps(message, default=str)
            return await self.client.publish(full_channel, message)
        except Exception as e:
            self.error_count += 1
            logger.error(f"Redis PUBLISH operation failed for channel {channel}: {e}")
            return None

    async def subscribe(self, channel: str) -> bool:
        try:
            if not self.pubsub:
                self.pubsub = self.client.pubsub()
            full_channel = self._get_key(f"channel:{channel}")
            await self.pubsub.subscribe(full_channel)
            return True
        except Exception as e:
            logger.error(f"Redis SUBSCRIBE operation failed for channel {channel}: {e}")
            return False

    async def unsubscribe(self, channel: str) -> bool:
        try:
            if not self.pubsub:
                return True
            full_channel = self._get_key(f"channel:{channel}")
            await self.pubsub.unsubscribe(full_channel)
            return True
        except Exception as e:
            logger.error(f"Redis UNSUBSCRIBE operation failed for channel {channel}: {e}")
            return False

    async def get_message(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            if not self.pubsub:
                return None
            message = await self.pubsub.get_message(timeout=timeout)
            if message and message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                except (json.JSONDecodeError, TypeError):
                    data = message['data']
                return {"channel": message['channel'], "data": data, "type": message['type']}
            return None
        except Exception as e:
            logger.error(f"Redis GET_MESSAGE operation failed: {e}")
            return None
# ------------------------------
# Декоратор кэширования
# ------------------------------
def redis_cache(key_template: str, expire: int = None):
    """Декоратор для кэширования результатов функций"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache_key = key_template.format(*args, **kwargs)
            redis_client = await get_redis_client()
            cached_result = await redis_client.get(cache_key)
            if cached_result is not None:
                return cached_result
            result = await func(*args, **kwargs)
            await redis_client.set(cache_key, result, expire)
            return result
        return wrapper
    return decorator

# ------------------------------
# RateLimiter
# ------------------------------
class RateLimiter:
    """Rate limiter на основе Redis"""
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service

    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """Проверить, разрешена ли операция"""
        try:
            current_time = int(datetime.utcnow().timestamp())
            window_start = current_time - window
            pipe = self.redis.client.pipeline()
            await pipe.zremrangebyscore(self._get_key(key), 0, window_start)
            count = await pipe.zcard(self._get_key(key))
            if count >= limit:
                return False
            await pipe.zadd(self._get_key(key), {str(current_time): current_time})
            await pipe.expire(self._get_key(key), window + 1)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            return True

    def _get_key(self, key: str) -> str:
        return f"rate_limit:{key}"

# ------------------------------
# Менеджер сессий на Redis
# ------------------------------
class RedisSessionManager:
    """Менеджер сессий пользователей на Redis"""
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
        self.session_prefix = "session:"

    async def create_session(self, user_id: int, session_data: Dict[str, Any], expire: int = 3600) -> str:
        import uuid
        session_id = str(uuid.uuid4())
        session_key = f"{self.session_prefix}{session_id}"
        await self.redis.hash_set(session_key, "user_id", user_id)
        await self.redis.hash_set(session_key, "created_at", datetime.utcnow().isoformat())
        for key, value in session_data.items():
            await self.redis.hash_set(session_key, key, value)
        await self.redis.expire(session_key, expire)
        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session_key = f"{self.session_prefix}{session_id}"
        return await self.redis.hash_get_all(session_key)

    async def update_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        session_key = f"{self.session_prefix}{session_id}"
        for key, value in data.items():
            await self.redis.hash_set(session_key, key, value)
        return True

    async def delete_session(self, session_id: str) -> bool:
        session_key = f"{self.session_prefix}{session_id}"
        return await self.redis.delete(session_key)

# ------------------------------
# Глобальный экземпляр RedisService
# ------------------------------
_redis_service = RedisService()

async def get_redis_client() -> RedisService:
    """Получить Redis клиент"""
    if not _redis_service._initialized:
        await _redis_service.initialize()
    return _redis_service
