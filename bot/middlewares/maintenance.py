"""
VideoBot Pro - Maintenance Middleware
Режим технического обслуживания
"""

import structlog
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

from bot.config import bot_config

logger = structlog.get_logger(__name__)

class MaintenanceMiddleware(BaseMiddleware):
    """Middleware для режима обслуживания"""
    
    def __init__(self):
        """Инициализация middleware"""
        self.maintenance_mode = False  # Можно вынести в конфигурацию
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        # Если режим обслуживания отключен
        if not self.maintenance_mode:
            return await handler(event, data)
        
        # Получаем ID пользователя
        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
        
        # Админы могут работать в режиме обслуживания
        if user_id and bot_config.is_admin(user_id):
            return await handler(event, data)
        
        # Для всех остальных показываем сообщение об обслуживании
        maintenance_message = (
            "🔧 <b>Техническое обслуживание</b>\n\n"
            "Бот временно недоступен из-за технических работ.\n"
            "Попробуйте позже.\n\n"
            "⏰ Примерное время: 10-30 минут"
        )
        
        try:
            if isinstance(event, Message):
                await event.answer(maintenance_message)
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "Бот на техническом обслуживании",
                    show_alert=True
                )
        except Exception as e:
            logger.error(f"Error sending maintenance message: {e}")
        
        return None
    
    def enable_maintenance(self):
        """Включить режим обслуживания"""
        self.maintenance_mode = True
        logger.info("Maintenance mode enabled")
    
    def disable_maintenance(self):
        """Отключить режим обслуживания"""
        self.maintenance_mode = False
        logger.info("Maintenance mode disabled")