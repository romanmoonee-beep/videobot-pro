"""
VideoBot Pro - Authentication Middleware
Аутентификация и авторизация пользователей
"""

import structlog
from typing import Any, Awaitable, Callable, Dict, Optional
from datetime import datetime

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update, User as TelegramUser

from sqlalchemy import text

from shared.config.database import get_async_session
from shared.models import User, EventType
from shared.models.analytics import track_user_event
from bot.config import bot_config
from bot.utils.user_manager import get_or_create_user, update_user_activity

logger = structlog.get_logger(__name__)

class AuthMiddleware(BaseMiddleware):
    """Middleware для аутентификации и создания пользователей"""
    
    def __init__(
        self,
        auto_create_users: bool = True,
        update_user_info: bool = True
    ):
        """
        Инициализация middleware
        
        Args:
            auto_create_users: Автоматически создавать новых пользователей
            update_user_info: Обновлять информацию существующих пользователей
        """
        self.auto_create_users = auto_create_users
        self.update_user_info = update_user_info
        
        # Кеш для часто запрашиваемых пользователей
        self._user_cache = {}
        self._cache_ttl = 300  # 5 минут
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        # Извлекаем Telegram пользователя
        telegram_user = self._extract_telegram_user(event)
        
        if not telegram_user:
            # Если нет пользователя, пропускаем
            return await handler(event, data)
        
        # Получаем или создаем пользователя в БД
        try:
            user = await self._get_or_create_user(telegram_user)
            
            # Добавляем пользователя в данные для следующих middleware
            data['user'] = user
            data['telegram_user'] = telegram_user
            
            # Проверяем заблокирован ли пользователь
            if user and user.is_banned:
                await self._handle_banned_user(event, user)
                return None
            
            # Обновляем активность если нужно
            if user and isinstance(event, (Message, CallbackQuery)):
                await self._update_user_activity(event, user)
            
        except Exception as e:
            logger.error(f"Error in auth middleware: {e}", user_id=telegram_user.id)
            # Не блокируем выполнение при ошибке аутентификации
        
        # Передаем управление следующему handler
        return await handler(event, data)
    
    def _extract_telegram_user(self, event: Update) -> Optional[TelegramUser]:
        """Извлечь Telegram пользователя из события"""
        if isinstance(event, Message):
            return event.from_user
        elif isinstance(event, CallbackQuery):
            return event.from_user
        elif hasattr(event, 'inline_query') and event.inline_query:
            return event.inline_query.from_user
        elif hasattr(event, 'chosen_inline_result') and event.chosen_inline_result:
            return event.chosen_inline_result.from_user
        elif hasattr(event, 'pre_checkout_query') and event.pre_checkout_query:
            return event.pre_checkout_query.from_user
        elif hasattr(event, 'shipping_query') and event.shipping_query:
            return event.shipping_query.from_user
        
        return None
    
    async def _get_or_create_user(self, telegram_user: TelegramUser) -> Optional[User]:
        """Получить или создать пользователя"""
        user_id = telegram_user.id
        
        # Проверяем кеш
        cache_key = f"user_{user_id}"
        if cache_key in self._user_cache:
            cached_user, cached_time = self._user_cache[cache_key]
            if (datetime.utcnow() - cached_time).total_seconds() < self._cache_ttl:
                return cached_user
        
        try:
            async with get_async_session() as session:
                if self.auto_create_users:
                    user = await get_or_create_user(
                        session=session,
                        telegram_id=user_id,
                        username=telegram_user.username,
                        first_name=telegram_user.first_name,
                        last_name=telegram_user.last_name,
                        language_code=telegram_user.language_code
                    )
                    await session.commit()
                else:
                    # Только получаем существующего пользователя
                    result = await session.execute(
                        text("SELECT * FROM users WHERE telegram_id = :telegram_id"),
                        {'telegram_id': user_id}
                    )
                    user = result.first()
                
                # Кешируем пользователя
                if user:
                    self._user_cache[cache_key] = (user, datetime.utcnow())
                
                return user
        
        except Exception as e:
            logger.error(f"Error getting/creating user: {e}", user_id=user_id)
            return None
    
    async def _handle_banned_user(self, event: Update, user: User):
        """Обработка заблокированного пользователя"""
        ban_message = "🚫 Ваш аккаунт заблокирован."
        
        if user.ban_reason:
            ban_message += f"\nПричина: {user.ban_reason}"
        
        if user.banned_until:
            ban_message += f"\nБлокировка до: {user.banned_until.strftime('%d.%m.%Y %H:%M')}"
        
        if user.banned_until and datetime.utcnow() > user.banned_until:
            # Автоматическое разблокирование
            try:
                async with get_async_session() as session:
                    db_user = await session.get(User, user.id)
                    if db_user:
                        db_user.unban_user()
                        await session.commit()
                        logger.info(f"Auto-unbanned user", user_id=user.telegram_id)
                        return  # Не блокируем, пользователь разблокирован
            except Exception as e:
                logger.error(f"Error auto-unbanning user: {e}")
        
        # Отправляем сообщение о блокировке
        try:
            if isinstance(event, Message):
                await event.answer(ban_message)
            elif isinstance(event, CallbackQuery):
                await event.answer(ban_message, show_alert=True)
        except Exception as e:
            logger.error(f"Error sending ban message: {e}")
    
    async def _update_user_activity(self, event: Update, user: User):
        """Обновить активность пользователя"""
        try:
            message_id = None
            if isinstance(event, Message):
                message_id = event.message_id
            elif isinstance(event, CallbackQuery) and event.message:
                message_id = event.message.message_id
            
            async with get_async_session() as session:
                # Получаем свежую копию пользователя из БД
                fresh_user = await session.get(User, user.id)
                if fresh_user:
                    await update_user_activity(session, fresh_user, message_id)
                    await session.commit()
        
        except Exception as e:
            logger.error(f"Error updating user activity: {e}", user_id=user.telegram_id)
    
    def clear_cache(self, user_id: Optional[int] = None):
        """Очистить кеш пользователей"""
        if user_id:
            cache_key = f"user_{user_id}"
            self._user_cache.pop(cache_key, None)
        else:
            self._user_cache.clear()
    
    def get_cached_user(self, user_id: int) -> Optional[User]:
        """Получить пользователя из кеша"""
        cache_key = f"user_{user_id}"
        if cache_key in self._user_cache:
            cached_user, cached_time = self._user_cache[cache_key]
            if (datetime.utcnow() - cached_time).total_seconds() < self._cache_ttl:
                return cached_user
        return None

class RequireAuthMiddleware(BaseMiddleware):
    """Middleware для обязательной аутентификации"""
    
    def __init__(self, allow_anonymous: bool = False):
        """
        Инициализация middleware
        
        Args:
            allow_anonymous: Разрешить анонимные запросы
        """
        self.allow_anonymous = allow_anonymous
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        user = data.get('user')
        
        if not user and not self.allow_anonymous:
            # Пользователь не найден и анонимные запросы не разрешены
            await self._handle_unauthenticated(event)
            return None
        
        return await handler(event, data)
    
    async def _handle_unauthenticated(self, event: Update):
        """Обработка неаутентифицированного запроса"""
        message = "🔐 Необходима регистрация. Используйте /start"
        
        try:
            if isinstance(event, Message):
                await event.answer(message)
            elif isinstance(event, CallbackQuery):
                await event.answer(message, show_alert=True)
        except Exception as e:
            logger.error(f"Error sending auth required message: {e}")

class UserTypeMiddleware(BaseMiddleware):
    """Middleware для проверки типа пользователя"""
    
    def __init__(self, required_types: list):
        """
        Инициализация middleware
        
        Args:
            required_types: Список разрешенных типов пользователей
        """
        self.required_types = required_types
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        user = data.get('user')
        
        if not user:
            return await handler(event, data)
        
        if user.current_user_type not in self.required_types:
            await self._handle_insufficient_permissions(event, user)
            return None
        
        return await handler(event, data)
    
    async def _handle_insufficient_permissions(self, event: Update, user: User):
        """Обработка недостаточных прав"""
        message = f"🚫 Требуется статус: {', '.join(self.required_types)}"
        
        try:
            if isinstance(event, Message):
                await event.answer(message)
            elif isinstance(event, CallbackQuery):
                await event.answer(message, show_alert=True)
        except Exception as e:
            logger.error(f"Error sending permission message: {e}")

# Декораторы для удобства использования

def require_auth(allow_anonymous: bool = False):
    """
    Декоратор для обязательной аутентификации
    
    Args:
        allow_anonymous: Разрешить анонимные запросы
    """
    def decorator(func):
        func._require_auth = True
        func._allow_anonymous = allow_anonymous
        return func
    return decorator

def require_user_type(*user_types):
    """
    Декоратор для проверки типа пользователя
    
    Args:
        user_types: Разрешенные типы пользователей
    """
    def decorator(func):
        func._required_user_types = user_types
        return func
    return decorator

def premium_required(func):
    """Декоратор для функций, требующих Premium"""
    return require_user_type('premium', 'admin')(func)

def admin_required(func):
    """Декоратор для функций, требующих права администратора"""
    return require_user_type('admin')(func)

# Утилиты

async def get_current_user(data: Dict[str, Any]) -> Optional[User]:
    """Получить текущего пользователя из данных middleware"""
    return data.get('user')

async def get_telegram_user(data: Dict[str, Any]) -> Optional[TelegramUser]:
    """Получить Telegram пользователя из данных middleware"""
    return data.get('telegram_user')

def is_authenticated(data: Dict[str, Any]) -> bool:
    """Проверить аутентифицирован ли пользователь"""
    return data.get('user') is not None

def has_user_type(data: Dict[str, Any], *user_types) -> bool:
    """Проверить тип пользователя"""
    user = data.get('user')
    if not user:
        return False
    return user.current_user_type in user_types

def is_premium(data: Dict[str, Any]) -> bool:
    """Проверить является ли пользователь Premium"""
    return has_user_type(data, 'premium', 'admin')

def is_admin(data: Dict[str, Any]) -> bool:
    """Проверить является ли пользователь админом"""
    return has_user_type(data, 'admin')