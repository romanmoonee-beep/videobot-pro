"""
VideoBot Pro - User Activity Middleware
Отслеживание активности пользователей
"""

import structlog
from typing import Any, Awaitable, Callable, Dict
from datetime import datetime

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

from shared.config.database import get_async_session
from shared.models import User
from bot.utils.user_manager import update_user_activity

logger = structlog.get_logger(__name__)

class UserActivityMiddleware(BaseMiddleware):
    """Middleware для отслеживания активности пользователей"""
    
    def __init__(self):
        """Инициализация middleware"""
        pass
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        # Сначала выполняем handler
        result = await handler(event, data)
        
        # Затем обновляем активность
        user = data.get('user')
        if user:
            try:
                message_id = None
                if isinstance(event, Message):
                    message_id = event.message_id
                elif isinstance(event, CallbackQuery) and event.message:
                    message_id = event.message.message_id
                
                async with get_async_session() as session:
                    # Получаем свежую копию пользователя
                    fresh_user = await session.get(User, user.id)
                    if fresh_user:
                        await update_user_activity(session, fresh_user, message_id)
                        await session.commit()
                        
            except Exception as e:
                logger.error(f"Error updating user activity: {e}")
        
        return result