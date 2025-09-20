"""
VideoBot Pro - CDN Rate Limit Middleware  
Middleware для ограничения частоты запросов к CDN
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, Optional
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from shared.services.redis import redis_service
from ..config import cdn_config

logger = structlog.get_logger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware для ограничения частоты запросов"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Локальный кэш для быстрого доступа
        self._local_cache: Dict[str, Dict] = {}
        self._cache_cleanup_interval = 300  # 5 минут
        self._last_cleanup = datetime.utcnow()
        
        # Лимиты по умолчанию (запросов в минуту)
        self.default_limits = {
            'free': 10,
            'trial': 15, 
            'premium': 30,
            'admin': 100,
            'owner': 1000,
            'anonymous': 5
        }
        
        # Пути с особыми лимитами
        self.path_limits = {
            '/api/v1/files/': {
                'free': 5,
                'trial': 10,
                'premium': 20,
                'admin': 50,
                'anonymous': 2
            },
            '/api/v1/stats/': {
                'admin': 20,
                'owner': 50
            }
        }
        
        # Исключенные пути
        self.excluded_paths = {
            '/health',
            '/',
            '/docs',
            '/redoc',
            '/openapi.json'
        }
    
    async def dispatch(self, request: Request, call_next):
        """Обработка запроса с проверкой лимитов"""
        try:
            # Проверяем, нужно ли применять лимиты
            if self._is_excluded_path(request.url.path):
                return await call_next(request)
            
            # Очистка кэша при необходимости
            await self._cleanup_cache_if_needed()
            
            # Получаем идентификатор клиента
            client_id = self._get_client_identifier(request)
            
            # Получаем тип пользователя
            user_type = self._get_user_type(request)
            
            # Проверяем лимиты
            if not await self._check_rate_limit(client_id, user_type, request.url.path):
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"}
                )
            
            # Записываем запрос
            await self._record_request(client_id, user_type, request.url.path)
            
            response = await call_next(request)
            
            # Добавляем заголовки с информацией о лимитах
            await self._add_rate_limit_headers(response, client_id, user_type, request.url.path)
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limit middleware error: {e}")
            # В случае ошибки пропускаем запрос
            return await call_next(request)
    
    def _is_excluded_path(self, path: str) -> bool:
        """Проверка, исключен ли путь из rate limiting"""
        return any(path.startswith(excluded) for excluded in self.excluded_paths)
    
    def _get_client_identifier(self, request: Request) -> str:
        """Получение идентификатора клиента"""
        # Приоритет: user_id > real_ip > client_ip
        user = getattr(request.state, 'user', None)
        if user:
            return f"user:{user.id}"
        
        # Получаем реальный IP из заголовков
        real_ip = (
            request.headers.get("X-Real-IP") or
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            request.client.host if request.client else "unknown"
        )
        
        return f"ip:{real_ip}"
    
    def _get_user_type(self, request: Request) -> str:
        """Получение типа пользователя"""
        user = getattr(request.state, 'user', None)
        if user:
            return user.user_type
        return 'anonymous'
    
    async def _check_rate_limit(self, client_id: str, user_type: str, path: str) -> bool:
        """Проверка лимита запросов"""
        try:
            # Получаем лимит для данного пути и типа пользователя
            limit = self._get_limit(user_type, path)
            
            # Ключ для Redis
            redis_key = f"rate_limit:{client_id}:{path.split('/')[1] if '/' in path else 'global'}"
            
            # Проверяем в локальном кэше сначала
            local_key = f"{client_id}:{path}"
            now = datetime.utcnow()
            
            if local_key in self._local_cache:
                cache_entry = self._local_cache[local_key]
                if now - cache_entry['last_reset'] < timedelta(minutes=1):
                    if cache_entry['count'] >= limit:
                        return False
                else:
                    # Сбрасываем счетчик
                    cache_entry['count'] = 0
                    cache_entry['last_reset'] = now
            
            # Проверяем в Redis для точности
            if redis_service.is_connected():
                current_count = await redis_service.get(redis_key)
                current_count = int(current_count) if current_count else 0
                
                if current_count >= limit:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # В случае ошибки разрешаем запрос
            return True
    
    async def _record_request(self, client_id: str, user_type: str, path: str):
        """Запись запроса в счетчики"""
        try:
            # Обновляем локальный кэш
            local_key = f"{client_id}:{path}"
            now = datetime.utcnow()
            
            if local_key not in self._local_cache:
                self._local_cache[local_key] = {
                    'count': 0,
                    'last_reset': now
                }
            
            cache_entry = self._local_cache[local_key]
            
            # Сбрасываем счетчик если прошла минута
            if now - cache_entry['last_reset'] >= timedelta(minutes=1):
                cache_entry['count'] = 0
                cache_entry['last_reset'] = now
            
            cache_entry['count'] += 1
            
            # Обновляем Redis
            if redis_service.is_connected():
                redis_key = f"rate_limit:{client_id}:{path.split('/')[1] if '/' in path else 'global'}"
                
                # Используем pipeline для атомарности
                async with redis_service.pipeline() as pipe:
                    await pipe.incr(redis_key)
                    await pipe.expire(redis_key, 60)  # TTL 60 секунд
                    await pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to record request: {e}")
    
    async def _add_rate_limit_headers(self, response: Response, client_id: str, user_type: str, path: str):
        """Добавление заголовков с информацией о лимитах"""
        try:
            limit = self._get_limit(user_type, path)
            
            # Получаем текущее количество запросов
            local_key = f"{client_id}:{path}"
            current_count = 0
            
            if local_key in self._local_cache:
                current_count = self._local_cache[local_key]['count']
            
            remaining = max(0, limit - current_count)
            reset_time = int((datetime.utcnow() + timedelta(minutes=1)).timestamp())
            
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(reset_time)
            
        except Exception as e:
            logger.error(f"Failed to add rate limit headers: {e}")
    
    def _get_limit(self, user_type: str, path: str) -> int:
        """Получение лимита для типа пользователя и пути"""
        # Проверяем специальные лимиты для пути
        for path_prefix, limits in self.path_limits.items():
            if path.startswith(path_prefix):
                return limits.get(user_type, self.default_limits.get(user_type, 5))
        
        # Используем лимиты по умолчанию
        return self.default_limits.get(user_type, 5)
    
    async def _cleanup_cache_if_needed(self):
        """Очистка устаревших записей из локального кэша"""
        now = datetime.utcnow()
        
        if now - self._last_cleanup < timedelta(seconds=self._cache_cleanup_interval):
            return
        
        try:
            # Удаляем старые записи
            expired_keys = []
            cutoff_time = now - timedelta(minutes=2)
            
            for key, entry in self._local_cache.items():
                if entry['last_reset'] < cutoff_time:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._local_cache[key]
            
            self._last_cleanup = now
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
    
    async def get_rate_limit_info(self, client_id: str, user_type: str, path: str) -> Dict:
        """Получение информации о текущих лимитах (для API)"""
        try:
            limit = self._get_limit(user_type, path)
            local_key = f"{client_id}:{path}"
            
            current_count = 0
            last_reset = datetime.utcnow()
            
            if local_key in self._local_cache:
                entry = self._local_cache[local_key]
                current_count = entry['count']
                last_reset = entry['last_reset']
            
            remaining = max(0, limit - current_count)
            reset_in_seconds = max(0, 60 - int((datetime.utcnow() - last_reset).total_seconds()))
            
            return {
                "limit": limit,
                "used": current_count,
                "remaining": remaining,
                "reset_in_seconds": reset_in_seconds,
                "user_type": user_type
            }
            
        except Exception as e:
            logger.error(f"Failed to get rate limit info: {e}")
            return {
                "limit": 0,
                "used": 0,
                "remaining": 0,
                "reset_in_seconds": 60,
                "user_type": user_type
            }