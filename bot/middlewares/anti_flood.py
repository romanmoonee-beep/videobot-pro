"""
VideoBot Pro - Anti-Flood Middleware
Защита от флуда сообщений
"""

import time
import structlog
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

logger = structlog.get_logger(__name__)

class AntiFloodMiddleware(BaseMiddleware):
    """Middleware для защиты от флуда"""
    
    def __init__(self, threshold: int = 5, window: int = 10):
        """
        Args:
            threshold: Максимум сообщений за окно
            window: Временное окно в секундах
        """
        self.threshold = threshold
        self.window = window
        self.user_messages = {}
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        user_id = None
        
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
        
        if not user_id:
            return await handler(event, data)
        
        # Проверяем флуд
        current_time = time.time()
        
        if user_id not in self.user_messages:
            self.user_messages[user_id] = []
        
        # Очищаем старые сообщения
        self.user_messages[user_id] = [
            msg_time for msg_time in self.user_messages[user_id]
            if current_time - msg_time < self.window
        ]
        
        # Проверяем лимит
        if len(self.user_messages[user_id]) >= self.threshold:
            logger.warning(f"Flood detected for user {user_id}")
            if isinstance(event, Message):
                await event.answer("⚡ Слишком много сообщений. Подождите немного.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⚡ Подождите перед следующим действием", show_alert=True)
            return None
        
        # Добавляем текущее сообщение
        self.user_messages[user_id].append(current_time)
        
        return await handler(event, data)