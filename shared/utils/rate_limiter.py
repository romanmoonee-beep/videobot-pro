"""
VideoBot Pro - Rate Limiting Utilities
Утилиты для ограничения частоты запросов
"""

import time
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any, Union
from datetime import datetime, timedelta
from collections import defaultdict, deque
import structlog

logger = structlog.get_logger(__name__)

class RateLimitExceeded(Exception):
    """Исключение при превышении лимита запросов"""
    def __init__(self, message: str, retry_after: int = None):
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)

class RateLimiter(ABC):
    """Абстрактный базовый класс для rate limiter'ов"""
    
    @abstractmethod
    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """
        Проверяет разрешен ли запрос
        
        Args:
            key: Ключ для идентификации клиента
            limit: Лимит запросов
            window: Временное окно в секундах
            
        Returns:
            True если запрос разрешен
        """
        pass
    
    @abstractmethod
    async def get_remaining(self, key: str, limit: int, window: int) -> int:
        """Получает количество оставшихся запросов"""
        pass
    
    @abstractmethod
    async def reset_key(self, key: str):
        """Сбрасывает лимит для ключа"""
        pass

class MemoryRateLimiter(RateLimiter):
    """Rate limiter в памяти (для одного процесса)"""
    
    def __init__(self):
        self._requests: Dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """Проверка лимита запросов"""
        async with self._lock:
            now = time.time()
            request_times = self._requests[key]
            
            # Удаляем старые запросы
            while request_times and request_times[0] <= now - window:
                request_times.popleft()
            
            # Проверяем лимит
            if len(request_times) >= limit:
                return False
            
            # Добавляем текущий запрос
            request_times.append(now)
            return True
    
    async def get_remaining(self, key: str, limit: int, window: int) -> int:
        """Получает оставшиеся запросы"""
        async with self._lock:
            now = time.time()
            request_times = self._requests[key]
            
            # Очищаем старые запросы
            while request_times and request_times[0] <= now - window:
                request_times.popleft()
            
            return max(0, limit - len(request_times))
    
    async def reset_key(self, key: str):
        """Сбрасывает лимит для ключа"""
        async with self._lock:
            if key in self._requests:
                del self._requests[key]
    
    async def cleanup(self, max_age: int = 3600):
        """Очистка старых записей"""
        async with self._lock:
            now = time.time()
            keys_to_remove = []
            
            for key, request_times in self._requests.items():
                # Очищаем старые запросы
                while request_times and request_times[0] <= now - max_age:
                    request_times.popleft()
                
                # Удаляем пустые ключи
                if not request_times:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._requests[key]

class RedisRateLimiter(RateLimiter):
    """Rate limiter с использованием Redis"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def is_allowed(self, key: str, limit: int, window: int) -> bool:
        """Проверка с использованием Redis sliding window"""
        now = time.time()
        pipeline = self.redis.pipeline()
        
        # Удаляем старые записи
        pipeline.zremrangebyscore(key, 0, now - window)
        
        # Получаем текущее количество запросов
        pipeline.zcard(key)
        
        # Добавляем текущий запрос
        pipeline.zadd(key, {str(now): now})
        
        # Устанавливаем TTL
        pipeline.expire(key, window + 1)
        
        results = await pipeline.execute()
        current_requests = results[1]
        
        return current_requests < limit
    
    async def get_remaining(self, key: str, limit: int, window: int) -> int:
        """Получает оставшиеся запросы через Redis"""
        now = time.time()
        
        # Удаляем старые записи
        await self.redis.zremrangebyscore(key, 0, now - window)
        
        # Получаем текущее количество
        current = await self.redis.zcard(key)
        
        return max(0, limit - current)
    
    async def reset_key(self, key: str):
        """Сбрасывает ключ в Redis"""
        await self.redis.delete(key)
    
    async def get_window_requests(self, key: str, window: int) -> list:
        """Получает все запросы в текущем окне"""
        now = time.time()
        return await self.redis.zrangebyscore(key, now - window, now)

class TokenBucketRateLimiter:
    """Rate limiter на основе алгоритма Token Bucket"""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: Максимальная емкость bucket
            refill_rate: Скорость пополнения токенов в секунду
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: Dict[str, Dict[str, float]] = {}
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, key: str, tokens_requested: int = 1) -> bool:
        """Проверяет доступность токенов"""
        async with self._lock:
            now = time.time()
            
            if key not in self._buckets:
                self._buckets[key] = {
                    'tokens': float(self.capacity),
                    'last_refill': now
                }
            
            bucket = self._buckets[key]
            
            # Пополняем токены
            elapsed = now - bucket['last_refill']
            new_tokens = elapsed * self.refill_rate
            bucket['tokens'] = min(self.capacity, bucket['tokens'] + new_tokens)
            bucket['last_refill'] = now
            
            # Проверяем доступность токенов
            if bucket['tokens'] >= tokens_requested:
                bucket['tokens'] -= tokens_requested
                return True
            
            return False
    
    async def get_available_tokens(self, key: str) -> float:
        """Получает количество доступных токенов"""
        async with self._lock:
            now = time.time()
            
            if key not in self._buckets:
                return float(self.capacity)
            
            bucket = self._buckets[key]
            elapsed = now - bucket['last_refill']
            new_tokens = elapsed * self.refill_rate
            
            return min(self.capacity, bucket['tokens'] + new_tokens)
    
    async def wait_for_tokens(self, key: str, tokens_needed: int = 1) -> float:
        """Рассчитывает время ожидания для получения токенов"""
        available = await self.get_available_tokens(key)
        
        if available >= tokens_needed:
            return 0.0
        
        tokens_deficit = tokens_needed - available
        return tokens_deficit / self.refill_rate

class UserRateLimiter:
    """Rate limiter для пользователей с разными типами"""
    
    def __init__(self, limiter: RateLimiter):
        self.limiter = limiter
        
        # Лимиты по типам пользователей
        self.user_limits = {
            'free': {'requests': 10, 'window': 60},      # 10 запросов в минуту
            'trial': {'requests': 30, 'window': 60},     # 30 запросов в минуту
            'premium': {'requests': 100, 'window': 60},  # 100 запросов в минуту
            'admin': {'requests': 1000, 'window': 60}    # 1000 запросов в минуту
        }
    
    async def check_user_limit(self, user_id: int, user_type: str, 
                             action: str = "general") -> Dict[str, Any]:
        """
        Проверяет лимиты пользователя
        
        Args:
            user_id: ID пользователя
            user_type: Тип пользователя
            action: Тип действия
            
        Returns:
            Словарь с результатами проверки
        """
        limits = self.user_limits.get(user_type, self.user_limits['free'])
        key = f"user:{user_id}:{action}"
        
        allowed = await self.limiter.is_allowed(
            key, limits['requests'], limits['window']
        )
        
        remaining = await self.limiter.get_remaining(
            key, limits['requests'], limits['window']
        )
        
        result = {
            'allowed': allowed,
            'remaining': remaining,
            'limit': limits['requests'],
            'window': limits['window'],
            'user_type': user_type,
            'reset_time': int(time.time()) + limits['window']
        }
        
        if not allowed:
            result['retry_after'] = limits['window']
        
        return result
    
    async def check_download_limit(self, user_id: int, user_type: str) -> Dict[str, Any]:
        """Проверяет лимит скачиваний"""
        download_limits = {
            'free': {'requests': 3, 'window': 300},      # 3 скачивания в 5 минут
            'trial': {'requests': 10, 'window': 300},    # 10 скачиваний в 5 минут
            'premium': {'requests': 50, 'window': 300},  # 50 скачиваний в 5 минут
            'admin': {'requests': 999, 'window': 60}     # Без ограничений
        }
        
        limits = download_limits.get(user_type, download_limits['free'])
        key = f"download:{user_id}"
        
        allowed = await self.limiter.is_allowed(
            key, limits['requests'], limits['window']
        )
        
        remaining = await self.limiter.get_remaining(
            key, limits['requests'], limits['window']
        )
        
        return {
            'allowed': allowed,
            'remaining': remaining,
            'limit': limits['requests'],
            'window_minutes': limits['window'] // 60,
            'retry_after': limits['window'] if not allowed else 0
        }

class GlobalRateLimiter:
    """Глобальный rate limiter для всей системы"""
    
    def __init__(self, limiter: RateLimiter):
        self.limiter = limiter
        
        # Глобальные лимиты
        self.global_limits = {
            'api_requests': {'requests': 10000, 'window': 60},        # API запросы
            'downloads': {'requests': 1000, 'window': 60},            # Скачивания
            'registrations': {'requests': 100, 'window': 3600},       # Регистрации в час
            'password_resets': {'requests': 50, 'window': 3600},      # Сброс паролей
            'premium_purchases': {'requests': 200, 'window': 3600}    # Покупки Premium
        }
    
    async def check_global_limit(self, action: str, 
                               ip_address: str = None) -> Dict[str, Any]:
        """Проверяет глобальные лимиты"""
        if action not in self.global_limits:
            return {'allowed': True, 'reason': 'no_limit_configured'}
        
        limits = self.global_limits[action]
        
        # Проверяем глобальный лимит
        global_key = f"global:{action}"
        global_allowed = await self.limiter.is_allowed(
            global_key, limits['requests'], limits['window']
        )
        
        result = {
            'allowed': global_allowed,
            'action': action,
            'global_limit': limits['requests'],
            'window': limits['window']
        }
        
        if not global_allowed:
            result['reason'] = 'global_limit_exceeded'
            result['retry_after'] = limits['window']
            return result
        
        # Если есть IP, проверяем лимит по IP
        if ip_address:
            ip_limit = limits['requests'] // 10  # IP лимит в 10 раз меньше глобального
            ip_key = f"ip:{ip_address}:{action}"
            
            ip_allowed = await self.limiter.is_allowed(
                ip_key, ip_limit, limits['window']
            )
            
            if not ip_allowed:
                result['allowed'] = False
                result['reason'] = 'ip_limit_exceeded'
                result['retry_after'] = limits['window']
        
        return result
    
    async def get_system_load(self) -> Dict[str, Any]:
        """Получает информацию о загрузке системы"""
        load_info = {}
        
        for action, limits in self.global_limits.items():
            key = f"global:{action}"
            remaining = await self.limiter.get_remaining(
                key, limits['requests'], limits['window']
            )
            
            load_percent = ((limits['requests'] - remaining) / limits['requests']) * 100
            
            load_info[action] = {
                'used': limits['requests'] - remaining,
                'limit': limits['requests'],
                'remaining': remaining,
                'load_percent': round(load_percent, 2)
            }
        
        return load_info

class AdaptiveRateLimiter:
    """Адаптивный rate limiter с автоматической регулировкой"""
    
    def __init__(self, base_limiter: RateLimiter):
        self.base_limiter = base_limiter
        self._error_rates: Dict[str, deque] = defaultdict(deque)
        self._adjustments: Dict[str, float] = defaultdict(lambda: 1.0)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, key: str, base_limit: int, window: int, 
                        error_rate: float = None) -> bool:
        """Проверка с учетом адаптивной регулировки"""
        async with self._lock:
            # Обновляем статистику ошибок если предоставлена
            if error_rate is not None:
                now = time.time()
                error_window = self._error_rates[key]
                
                # Очищаем старые записи
                while error_window and error_window[0][0] <= now - window:
                    error_window.popleft()
                
                error_window.append((now, error_rate))
                
                # Рассчитываем средний процент ошибок
                if error_window:
                    avg_error_rate = sum(rate for _, rate in error_window) / len(error_window)
                    
                    # Адаптируем лимит на основе процента ошибок
                    if avg_error_rate > 0.1:  # Если ошибок больше 10%
                        self._adjustments[key] *= 0.8  # Уменьшаем лимит на 20%
                    elif avg_error_rate < 0.05:  # Если ошибок меньше 5%
                        self._adjustments[key] = min(1.0, self._adjustments[key] * 1.1)
        
        # Применяем адаптивный лимит
        adjusted_limit = int(base_limit * self._adjustments[key])
        return await self.base_limiter.is_allowed(key, adjusted_limit, window)
    
    async def report_error(self, key: str, error_occurred: bool = True):
        """Сообщает об ошибке для адаптации лимитов"""
        error_rate = 1.0 if error_occurred else 0.0
        # Используем фиктивные значения для обновления статистики
        await self.is_allowed(key, 1, 60, error_rate)
    
    async def get_adjustment_factor(self, key: str) -> float:
        """Получает текущий коэффициент адаптации"""
        return self._adjustments[key]

class RateLimitMiddleware:
    """Middleware для автоматического применения rate limiting"""
    
    def __init__(self, user_limiter: UserRateLimiter, 
                 global_limiter: GlobalRateLimiter = None):
        self.user_limiter = user_limiter
        self.global_limiter = global_limiter
    
    async def check_limits(self, user_id: int, user_type: str, 
                          action: str, ip_address: str = None) -> Dict[str, Any]:
        """
        Проверяет все применимые лимиты
        
        Returns:
            Словарь с результатами всех проверок
        """
        results = {
            'allowed': True,
            'checks': {}
        }
        
        # Проверяем пользовательские лимиты
        user_result = await self.user_limiter.check_user_limit(
            user_id, user_type, action
        )
        results['checks']['user'] = user_result
        
        if not user_result['allowed']:
            results['allowed'] = False
            results['reason'] = 'user_limit_exceeded'
            results['retry_after'] = user_result.get('retry_after', 60)
        
        # Проверяем глобальные лимиты если настроены
        if self.global_limiter and results['allowed']:
            global_result = await self.global_limiter.check_global_limit(
                action, ip_address
            )
            results['checks']['global'] = global_result
            
            if not global_result['allowed']:
                results['allowed'] = False
                results['reason'] = global_result.get('reason', 'global_limit_exceeded')
                results['retry_after'] = global_result.get('retry_after', 60)
        
        return results

# Декораторы для удобного использования
def rate_limit(key_func: callable, limit: int, window: int, 
               limiter: RateLimiter = None):
    """
    Декоратор для применения rate limiting к функциям
    
    Args:
        key_func: Функция для генерации ключа
        limit: Лимит запросов
        window: Временное окно
        limiter: Экземпляр RateLimiter
    """
    if limiter is None:
        limiter = MemoryRateLimiter()
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            key = key_func(*args, **kwargs)
            
            if not await limiter.is_allowed(key, limit, window):
                raise RateLimitExceeded(
                    f"Rate limit exceeded for key: {key}",
                    retry_after=window
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def user_rate_limit(action: str, user_limiter: UserRateLimiter = None):
    """Декоратор для пользовательского rate limiting"""
    def decorator(func):
        async def wrapper(user_id: int, user_type: str, *args, **kwargs):
            if user_limiter:
                result = await user_limiter.check_user_limit(user_id, user_type, action)
                
                if not result['allowed']:
                    raise RateLimitExceeded(
                        f"User rate limit exceeded for action: {action}",
                        retry_after=result.get('retry_after', 60)
                    )
            
            return await func(user_id, user_type, *args, **kwargs)
        
        return wrapper
    return decorator