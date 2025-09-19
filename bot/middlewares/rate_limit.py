"""
VideoBot Pro - Rate Limit Middleware
Ограничение частоты запросов
"""

import time
import structlog
from typing import Any, Awaitable, Callable, Dict, Optional
from functools import wraps

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Middleware для ограничения частоты запросов"""
    
    def __init__(
        self, 
        default_limit: int = 30,
        time_window: int = 60,
        storage: Optional[Dict] = None
    ):
        """
        Инициализация middleware
        
        Args:
            default_limit: Лимит запросов по умолчанию
            time_window: Временное окно в секундах
            storage: Хранилище для счетчиков
        """
        self.default_limit = default_limit
        self.time_window = time_window
        self.storage = storage or {}
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        user_id = self._get_user_id(event)
        
        if not user_id:
            return await handler(event, data)
        
        # Проверяем rate limit
        if not self._check_rate_limit(user_id):
            await self._handle_rate_limit_exceeded(event)
            return None
        
        # Обновляем счетчик
        self._update_counter(user_id)
        
        # Передаем управление следующему handler
        return await handler(event, data)
    
    def _get_user_id(self, event: Update) -> Optional[int]:
        """Получить ID пользователя из события"""
        if isinstance(event, Message):
            return event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            return event.from_user.id if event.from_user else None
        return None
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """
        Проверить превышен ли лимит
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True если лимит не превышен
        """
        current_time = time.time()
        user_key = f"rate_{user_id}"
        
        if user_key not in self.storage:
            self.storage[user_key] = {
                'count': 0,
                'window_start': current_time
            }
            return True
        
        user_data = self.storage[user_key]
        
        # Проверяем, не истекло ли временное окно
        if current_time - user_data['window_start'] >= self.time_window:
            # Сбрасываем счетчик
            user_data['count'] = 0
            user_data['window_start'] = current_time
            return True
        
        # Проверяем лимит
        return user_data['count'] < self.default_limit
    
    def _update_counter(self, user_id: int):
        """Обновить счетчик запросов"""
        user_key = f"rate_{user_id}"
        
        if user_key in self.storage:
            self.storage[user_key]['count'] += 1
        else:
            self.storage[user_key] = {
                'count': 1,
                'window_start': time.time()
            }
    
    async def _handle_rate_limit_exceeded(self, event: Update):
        """Обработка превышения лимита"""
        user_id = self._get_user_id(event)
        
        logger.warning(f"Rate limit exceeded", user_id=user_id)
        
        if isinstance(event, Message):
            try:
                await event.answer(
                    "⚡ Слишком много запросов. Подождите немного и попробуйте снова."
                )
            except Exception:
                pass
        elif isinstance(event, CallbackQuery):
            try:
                await event.answer(
                    "⚡ Слишком много запросов. Подождите.",
                    show_alert=True
                )
            except Exception:
                pass
    
    def get_user_remaining_requests(self, user_id: int) -> int:
        """Получить количество оставшихся запросов"""
        user_key = f"rate_{user_id}"
        
        if user_key not in self.storage:
            return self.default_limit
        
        user_data = self.storage[user_key]
        current_time = time.time()
        
        if current_time - user_data['window_start'] >= self.time_window:
            return self.default_limit
        
        return max(0, self.default_limit - user_data['count'])
    
    def reset_user_limit(self, user_id: int):
        """Сбросить лимит пользователя"""
        user_key = f"rate_{user_id}"
        if user_key in self.storage:
            del self.storage[user_key]


def rate_limit(
    requests_per_minute: int = 30,
    key_func: Optional[Callable] = None
):
    """
    Декоратор для установки rate limit на конкретный handler
    
    Args:
        requests_per_minute: Количество запросов в минуту
        key_func: Функция для получения ключа rate limiting
    """
    def decorator(func):
        # Сохраняем параметры rate limit в атрибутах функции
        func._rate_limit = requests_per_minute
        func._rate_limit_key_func = key_func
        
        @wraps(func)
        async def wrapper(message_or_callback, *args, **kwargs):
            # Получаем user_id
            if hasattr(message_or_callback, 'from_user'):
                user_id = message_or_callback.from_user.id
            else:
                return await func(message_or_callback, *args, **kwargs)
            
            # Применяем кастомную функцию ключа если есть
            if key_func:
                limit_key = key_func(message_or_callback)
            else:
                limit_key = f"handler_{func.__name__}_{user_id}"
            
            # Простая проверка rate limit
            current_time = time.time()
            
            if not hasattr(wrapper, '_rate_storage'):
                wrapper._rate_storage = {}
            
            if limit_key in wrapper._rate_storage:
                last_call, call_count = wrapper._rate_storage[limit_key]
                
                # Сбрасываем счетчик если прошла минута
                if current_time - last_call > 60:
                    wrapper._rate_storage[limit_key] = (current_time, 1)
                # Проверяем лимит
                elif call_count >= requests_per_minute:
                    remaining = 60 - (current_time - last_call)
                    
                    if hasattr(message_or_callback, 'answer'):
                        await message_or_callback.answer(
                            f"⚡ Подождите {int(remaining)} сек"
                        )
                    return None
                else:
                    wrapper._rate_storage[limit_key] = (last_call, call_count + 1)
            else:
                wrapper._rate_storage[limit_key] = (current_time, 1)
            
            return await func(message_or_callback, *args, **kwargs)
        
        return wrapper
    return decorator