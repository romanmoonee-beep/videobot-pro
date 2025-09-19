"""
VideoBot Pro - Admin Only Middleware
Ограничение доступа только для администраторов
"""

import structlog
from typing import Any, Awaitable, Callable, Dict
from functools import wraps

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

from bot.config import bot_config

logger = structlog.get_logger(__name__)


class AdminOnlyMiddleware(BaseMiddleware):
    """Middleware для проверки админских прав"""
    
    def __init__(self, auto_respond: bool = True):
        """
        Инициализация middleware
        
        Args:
            auto_respond: Автоматически отвечать при отказе в доступе
        """
        self.auto_respond = auto_respond
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        # Проверяем только handlers помеченные как admin_only
        handler_obj = data.get('handler')
        if handler_obj and not getattr(handler_obj.callback, '_admin_only', False):
            return await handler(event, data)
        
        user_id = self._get_user_id(event)
        
        if not user_id:
            return None
        
        # Проверяем является ли пользователь админом
        if not bot_config.is_admin(user_id):
            logger.warning(f"Unauthorized admin access attempt", user_id=user_id)
            
            if self.auto_respond:
                await self._handle_unauthorized_access(event)
            
            return None
        
        # Передаем управление следующему handler
        return await handler(event, data)
    
    def _get_user_id(self, event: Update) -> int:
        """Получить ID пользователя из события"""
        if isinstance(event, Message):
            return event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            return event.from_user.id if event.from_user else None
        return None
    
    async def _handle_unauthorized_access(self, event: Update):
        """Обработка неавторизованного доступа"""
        if isinstance(event, Message):
            try:
                await event.answer(
                    "🚫 Эта команда доступна только администраторам."
                )
            except Exception:
                pass
        elif isinstance(event, CallbackQuery):
            try:
                await event.answer(
                    "🚫 Доступ запрещен. Только для администраторов.",
                    show_alert=True
                )
            except Exception:
                pass


def admin_only(auto_respond: bool = True):
    """
    Декоратор для ограничения доступа к handler только для админов
    
    Args:
        auto_respond: Автоматически отвечать при отказе в доступе
    """
    def decorator(func):
        # Помечаем функцию как требующую админские права
        func._admin_only = True
        func._admin_auto_respond = auto_respond
        
        @wraps(func)
        async def wrapper(message_or_callback, *args, **kwargs):
            # Получаем user_id
            if hasattr(message_or_callback, 'from_user'):
                user_id = message_or_callback.from_user.id
            else:
                return None
            
            # Проверяем админские права
            if not bot_config.is_admin(user_id):
                logger.warning(
                    f"Unauthorized admin access attempt in {func.__name__}",
                    user_id=user_id
                )
                
                if auto_respond:
                    if hasattr(message_or_callback, 'answer'):
                        if isinstance(message_or_callback, CallbackQuery):
                            await message_or_callback.answer(
                                "🚫 Доступ запрещен",
                                show_alert=True
                            )
                        else:
                            await message_or_callback.answer(
                                "🚫 Эта команда доступна только администраторам."
                            )
                
                return None
            
            logger.info(f"Admin access granted", user_id=user_id, function=func.__name__)
            return await func(message_or_callback, *args, **kwargs)
        
        return wrapper
    return decorator


def owner_only():
    """
    Декоратор для ограничения доступа только для владельца бота
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(message_or_callback, *args, **kwargs):
            # Получаем user_id
            if hasattr(message_or_callback, 'from_user'):
                user_id = message_or_callback.from_user.id
            else:
                return None
            
            # Проверяем что это владелец (первый админ в списке)
            if not bot_config.admin_ids or user_id != bot_config.admin_ids[0]:
                logger.warning(
                    f"Unauthorized owner access attempt in {func.__name__}",
                    user_id=user_id
                )
                
                if hasattr(message_or_callback, 'answer'):
                    if isinstance(message_or_callback, CallbackQuery):
                        await message_or_callback.answer(
                            "🔒 Только для владельца бота",
                            show_alert=True
                        )
                    else:
                        await message_or_callback.answer(
                            "🔒 Эта команда доступна только владельцу бота."
                        )
                
                return None
            
            logger.info(f"Owner access granted", user_id=user_id, function=func.__name__)
            return await func(message_or_callback, *args, **kwargs)
        
        return wrapper
    return decorator