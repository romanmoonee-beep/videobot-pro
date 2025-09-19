"""
VideoBot Pro - Rate Limit Filter
Фильтры для ограничения частоты запросов и защиты от спама
"""

import time
from typing import Union, Dict, Optional
from datetime import datetime, timedelta
from aiogram import types
from aiogram.filters import BaseFilter
import asyncio
import redis.asyncio as aioredis

from bot.config import bot_config
from shared.config.database import get_async_session
from shared.models import User

class RateLimitFilter(BaseFilter):
    """Базовый фильтр для ограничения частоты запросов"""
    
    def __init__(
        self, 
        rate_limit: int = 5, 
        window: int = 60,
        key_suffix: str = "general"
    ):
        """
        Args:
            rate_limit: Максимальное количество запросов
            window: Временное окно в секундах
            key_suffix: Суффикс для ключа Redis
        """
        self.rate_limit = rate_limit
        self.window = window
        self.key_suffix = key_suffix
        self._redis = None
        self._memory_storage = {}  # Fallback при недоступности Redis
    
    async def _get_redis(self):
        """Получить подключение к Redis"""
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    bot_config.redis_url or "redis://localhost:6379",
                    decode_responses=True
                )
                # Проверяем подключение
                await self._redis.ping()
            except Exception:
                self._redis = False  # Отмечаем как недоступный
        return self._redis if self._redis is not False else None
    
    async def _check_rate_limit_redis(self, key: str) -> bool:
        """Проверка лимита через Redis"""
        redis = await self._get_redis()
        if not redis:
            return await self._check_rate_limit_memory(key)
        
        try:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.window)
            results = await pipe.execute()
            
            count = results[0]
            return count <= self.rate_limit
            
        except Exception:
            return await self._check_rate_limit_memory(key)
    
    async def _check_rate_limit_memory(self, key: str) -> bool:
        """Fallback проверка через память"""
        current_time = time.time()
        
        if key not in self._memory_storage:
            self._memory_storage[key] = []
        
        # Очистка старых записей
        self._memory_storage[key] = [
            timestamp for timestamp in self._memory_storage[key]
            if current_time - timestamp < self.window
        ]
        
        # Проверка лимита
        if len(self._memory_storage[key]) >= self.rate_limit:
            return False
        
        # Добавляем новую запись
        self._memory_storage[key].append(current_time)
        return True
    
    def _get_rate_limit_key(self, user_id: int) -> str:
        """Генерация ключа для rate limiting"""
        return f"rate_limit:{user_id}:{self.key_suffix}"
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка rate limit"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        # Админы освобождены от rate limiting
        if bot_config.is_admin(user_id):
            return True
        
        key = self._get_rate_limit_key(user_id)
        allowed = await self._check_rate_limit_redis(key)
        
        if not allowed:
            return False
        
        return {
            'user_id': user_id,
            'rate_limit_passed': True,
            'key': key
        }

class SpamFilter(BaseFilter):
    """Фильтр для защиты от спама"""
    
    def __init__(self, max_messages: int = 10, window: int = 60):
        """
        Args:
            max_messages: Максимальное количество сообщений
            window: Временное окно в секундах
        """
        self.max_messages = max_messages
        self.window = window
        self.user_messages = {}
    
    def _clean_old_messages(self, user_id: int):
        """Очистка старых сообщений"""
        if user_id not in self.user_messages:
            return
        
        current_time = time.time()
        self.user_messages[user_id] = [
            msg_time for msg_time in self.user_messages[user_id]
            if current_time - msg_time < self.window
        ]
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка на спам"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        # Админы освобождены от anti-spam
        if bot_config.is_admin(user_id):
            return True
        
        current_time = time.time()
        
        # Инициализация и очистка
        if user_id not in self.user_messages:
            self.user_messages[user_id] = []
        
        self._clean_old_messages(user_id)
        
        # Проверка лимита
        if len(self.user_messages[user_id]) >= self.max_messages:
            return False
        
        # Добавляем текущее сообщение
        self.user_messages[user_id].append(current_time)
        
        return {
            'user_id': user_id,
            'spam_check_passed': True,
            'messages_count': len(self.user_messages[user_id])
        }

class DownloadRateLimitFilter(RateLimitFilter):
    """Специализированный фильтр для ограничения скачиваний"""
    
    def __init__(self):
        # Настройки зависят от типа пользователя
        super().__init__(rate_limit=3, window=60, key_suffix="download")
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка лимита скачиваний с учетом типа пользователя"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        # Админы без ограничений
        if bot_config.is_admin(user_id):
            return True
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                # Определяем лимиты на основе типа пользователя
                user_type = user.current_user_type
                
                if user_type == 'premium' or user.is_trial_active:
                    # Premium и Trial: 10 запросов в минуту
                    self.rate_limit = 10
                elif user_type == 'free':
                    # Free: 3 запроса в минуту
                    self.rate_limit = 3
                else:
                    # По умолчанию
                    self.rate_limit = 2
                
                # Проверяем rate limit
                key = self._get_rate_limit_key(user_id)
                allowed = await self._check_rate_limit_redis(key)
                
                if not allowed:
                    return False
                
                return {
                    'user_id': user_id,
                    'user_type': user_type,
                    'rate_limit_passed': True,
                    'download_rate_limit': self.rate_limit
                }
                
        except Exception:
            # Fallback к базовой проверке
            return await super().__call__(message)

class CallbackRateLimitFilter(BaseFilter):
    """Фильтр для ограничения callback запросов"""
    
    def __init__(self, rate_limit: int = 20, window: int = 60):
        """
        Args:
            rate_limit: Максимальное количество callback'ов
            window: Временное окно в секундах
        """
        self.rate_limit = rate_limit
        self.window = window
        self.user_callbacks = {}
    
    def _clean_old_callbacks(self, user_id: int):
        """Очистка старых callback'ов"""
        if user_id not in self.user_callbacks:
            return
        
        current_time = time.time()
        self.user_callbacks[user_id] = [
            cb_time for cb_time in self.user_callbacks[user_id]
            if current_time - cb_time < self.window
        ]
    
    async def __call__(self, callback: types.CallbackQuery) -> Union[bool, dict]:
        """Проверка rate limit для callback"""
        if not callback.from_user:
            return False
        
        user_id = callback.from_user.id
        
        # Админы без ограничений
        if bot_config.is_admin(user_id):
            return True
        
        current_time = time.time()
        
        # Инициализация и очистка
        if user_id not in self.user_callbacks:
            self.user_callbacks[user_id] = []
        
        self._clean_old_callbacks(user_id)
        
        # Проверка лимита
        if len(self.user_callbacks[user_id]) >= self.rate_limit:
            return False
        
        # Добавляем текущий callback
        self.user_callbacks[user_id].append(current_time)
        
        return {
            'user_id': user_id,
            'callback_rate_limit_passed': True,
            'callbacks_count': len(self.user_callbacks[user_id])
        }

class FloodProtectionFilter(BaseFilter):
    """Усиленная защита от флуда"""
    
    def __init__(self):
        self.user_activity = {}
        self.warning_threshold = 5  # Предупреждение при 5 сообщениях за 10 сек
        self.ban_threshold = 15     # Временный бан при 15 сообщениях за 30 сек
        self.warning_window = 10    # Окно для предупреждения
        self.ban_window = 30        # Окно для бана
    
    def _track_user_activity(self, user_id: int):
        """Отслеживание активности пользователя"""
        current_time = time.time()
        
        if user_id not in self.user_activity:
            self.user_activity[user_id] = {
                'messages': [],
                'warnings': 0,
                'temp_ban_until': None
            }
        
        user_data = self.user_activity[user_id]
        
        # Очистка старых сообщений
        user_data['messages'] = [
            msg_time for msg_time in user_data['messages']
            if current_time - msg_time < self.ban_window
        ]
        
        # Добавляем текущее сообщение
        user_data['messages'].append(current_time)
        
        return user_data
    
    def _check_flood_status(self, user_data: dict) -> dict:
        """Проверка статуса флуда"""
        current_time = time.time()
        messages = user_data['messages']
        
        # Проверка временного бана
        if user_data.get('temp_ban_until') and current_time < user_data['temp_ban_until']:
            return {
                'status': 'banned',
                'until': user_data['temp_ban_until'],
                'reason': 'temporary_flood_ban'
            }
        
        # Счетчики для разных окон
        warning_count = len([
            t for t in messages 
            if current_time - t < self.warning_window
        ])
        ban_count = len(messages)
        
        # Проверка на бан
        if ban_count >= self.ban_threshold:
            user_data['temp_ban_until'] = current_time + 300  # 5 минут бана
            return {
                'status': 'flood_detected',
                'action': 'temporary_ban',
                'ban_duration': 300,
                'messages_count': ban_count
            }
        
        # Проверка на предупреждение
        if warning_count >= self.warning_threshold:
            user_data['warnings'] += 1
            return {
                'status': 'warning',
                'warning_count': user_data['warnings'],
                'messages_count': warning_count
            }
        
        return {'status': 'ok'}
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка флуд-защиты"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        # Админы освобождены от флуд-защиты
        if bot_config.is_admin(user_id):
            return True
        
        # Отслеживаем активность
        user_data = self._track_user_activity(user_id)
        flood_status = self._check_flood_status(user_data)
        
        # Блокируем при флуде или бане
        if flood_status['status'] in ['banned', 'flood_detected']:
            return False
        
        return {
            'user_id': user_id,
            'flood_check_passed': True,
            'flood_status': flood_status
        }

class UserThrottleFilter(BaseFilter):
    """Персональный троттлинг для каждого пользователя"""
    
    def __init__(self):
        self.user_throttles = {}
        self.default_cooldown = 2  # секунды между сообщениями
    
    def _get_user_cooldown(self, user_type: str) -> float:
        """Получить кулдаун для типа пользователя"""
        cooldowns = {
            'admin': 0,      # Админы без кулдауна
            'premium': 1,    # Premium - 1 секунда
            'trial': 1.5,    # Trial - 1.5 секунды  
            'free': 3        # Free - 3 секунды
        }
        return cooldowns.get(user_type, self.default_cooldown)
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка персонального троттлинга"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        current_time = time.time()
        
        # Админы без ограничений
        if bot_config.is_admin(user_id):
            return True
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                user_type = user.current_user_type
                cooldown = self._get_user_cooldown(user_type)
                
                # Проверяем последнее сообщение
                if user_id in self.user_throttles:
                    last_message_time = self.user_throttles[user_id]
                    if current_time - last_message_time < cooldown:
                        return False
                
                # Обновляем время последнего сообщения
                self.user_throttles[user_id] = current_time
                
                return {
                    'user_id': user_id,
                    'user_type': user_type,
                    'throttle_passed': True,
                    'cooldown': cooldown
                }
                
        except Exception:
            # Fallback к базовому кулдауну
            if user_id in self.user_throttles:
                last_message_time = self.user_throttles[user_id]
                if current_time - last_message_time < self.default_cooldown:
                    return False
            
            self.user_throttles[user_id] = current_time
            return True

class BulkActionFilter(BaseFilter):
    """Фильтр для ограничения массовых действий"""
    
    def __init__(self, max_actions: int = 50, window: int = 3600):
        """
        Args:
            max_actions: Максимальное количество действий
            window: Временное окно в секундах (по умолчанию час)
        """
        self.max_actions = max_actions
        self.window = window
        self.user_actions = {}
    
    def _clean_old_actions(self, user_id: int):
        """Очистка старых действий"""
        if user_id not in self.user_actions:
            return
        
        current_time = time.time()
        self.user_actions[user_id] = [
            action_time for action_time in self.user_actions[user_id]
            if current_time - action_time < self.window
        ]
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка лимита массовых действий"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        current_time = time.time()
        
        # Админы и Premium пользователи имеют увеличенные лимиты
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if user:
                    user_type = user.current_user_type
                    if user_type == 'admin':
                        return True  # Админы без ограничений
                    elif user_type in ['premium', 'trial']:
                        max_actions = self.max_actions * 2  # Двойной лимит
                    else:
                        max_actions = self.max_actions
                else:
                    max_actions = self.max_actions // 2  # Уменьшенный лимит для неизвестных
                    
        except Exception:
            max_actions = self.max_actions
        
        # Инициализация и очистка
        if user_id not in self.user_actions:
            self.user_actions[user_id] = []
        
        self._clean_old_actions(user_id)
        
        # Проверка лимита
        if len(self.user_actions[user_id]) >= max_actions:
            return False
        
        # Добавляем текущее действие
        self.user_actions[user_id].append(current_time)
        
        return {
            'user_id': user_id,
            'bulk_action_passed': True,
            'actions_count': len(self.user_actions[user_id]),
            'max_actions': max_actions
        }

class GlobalRateLimitFilter(BaseFilter):
    """Глобальный rate limiting для всего бота"""
    
    def __init__(self, global_limit: int = 1000, window: int = 60):
        """
        Args:
            global_limit: Глобальный лимит запросов в минуту
            window: Временное окно
        """
        self.global_limit = global_limit
        self.window = window
        self.requests = []
        self._lock = asyncio.Lock()
    
    async def _clean_old_requests(self):
        """Очистка старых запросов"""
        current_time = time.time()
        self.requests = [
            req_time for req_time in self.requests
            if current_time - req_time < self.window
        ]
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка глобального rate limit"""
        async with self._lock:
            current_time = time.time()
            
            # Очищаем старые запросы
            await self._clean_old_requests()
            
            # Проверяем глобальный лимит
            if len(self.requests) >= self.global_limit:
                return False
            
            # Добавляем текущий запрос
            self.requests.append(current_time)
            
            return {
                'global_rate_limit_passed': True,
                'current_load': len(self.requests),
                'max_load': self.global_limit
            }

# Предопределенные экземпляры фильтров
general_rate_limit = RateLimitFilter(rate_limit=10, window=60)
download_rate_limit = DownloadRateLimitFilter()
spam_filter = SpamFilter(max_messages=8, window=60)
callback_rate_limit = CallbackRateLimitFilter(rate_limit=15, window=60)
flood_protection = FloodProtectionFilter()
user_throttle = UserThrottleFilter()
bulk_action_limit = BulkActionFilter()
global_rate_limit = GlobalRateLimitFilter()

# Комбинированный фильтр для основных проверок
class MainRateLimitFilter(BaseFilter):
    """Основной комбинированный фильтр rate limiting"""
    
    def __init__(self):
        self.filters = [
            flood_protection,
            user_throttle,
            spam_filter,
            general_rate_limit
        ]
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка всех основных rate limit фильтров"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        results = {}
        
        # Проверяем каждый фильтр
        for filter_instance in self.filters:
            result = await filter_instance(message)
            if not result:
                return False
            
            if isinstance(result, dict):
                results.update(result)
        
        results['all_rate_limits_passed'] = True
        results['user_id'] = user_id
        
        return results

# Основной комбинированный фильтр
main_rate_limit = MainRateLimitFilter()

# Фабричные функции
def custom_rate_limit(limit: int, window: int, suffix: str = "custom") -> RateLimitFilter:
    """Создать кастомный rate limit фильтр"""
    return RateLimitFilter(limit, window, suffix)

def user_type_rate_limit(user_type: str) -> RateLimitFilter:
    """Создать rate limit для конкретного типа пользователя"""
    limits = {
        'free': (3, 60),
        'trial': (10, 60), 
        'premium': (30, 60),
        'admin': (100, 60)
    }
    
    limit, window = limits.get(user_type, (5, 60))
    return RateLimitFilter(limit, window, f"user_type_{user_type}")

def strict_spam_filter(messages: int = 5, window: int = 30) -> SpamFilter:
    """Создать строгий spam фильтр"""
    return SpamFilter(messages, window)

def lenient_rate_limit(limit: int = 20, window: int = 60) -> RateLimitFilter:
    """Создать мягкий rate limit"""
    return RateLimitFilter(limit, window, "lenient")