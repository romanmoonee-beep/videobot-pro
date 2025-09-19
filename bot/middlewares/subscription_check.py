"""
VideoBot Pro - Subscription Check Middleware
Проверка подписок на обязательные каналы
"""

import structlog
from typing import Any, Awaitable, Callable, Dict, Optional
from datetime import datetime, timedelta

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update, InlineKeyboardMarkup, InlineKeyboardButton

from shared.config.database import get_async_session
from shared.models import User
from bot.config import bot_config
from bot.utils.subscription_checker import SubscriptionChecker

logger = structlog.get_logger(__name__)


class SubscriptionCheckMiddleware(BaseMiddleware):
    """Middleware для проверки подписок на обязательные каналы"""
    
    def __init__(
        self,
        checker: Optional[SubscriptionChecker] = None,
        check_interval: int = 300,  # 5 минут
        exempt_commands: Optional[list] = None
    ):
        """
        Инициализация middleware
        
        Args:
            checker: Экземпляр SubscriptionChecker
            check_interval: Интервал между проверками в секундах
            exempt_commands: Команды, освобожденные от проверки
        """
        self.checker = checker
        self.check_interval = check_interval
        self.exempt_commands = exempt_commands or ['/start', '/help', '/premium']
        self._last_check = {}
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        # Проверяем только сообщения
        if not isinstance(event, Message):
            return await handler(event, data)
        
        # Пропускаем если подписки не требуются
        if not bot_config.required_subs_enabled:
            return await handler(event, data)
        
        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)
        
        # Проверяем является ли команда освобожденной
        if event.text and any(event.text.startswith(cmd) for cmd in self.exempt_commands):
            return await handler(event, data)
        
        # Проверяем нужна ли проверка
        if not await self._should_check_subscription(user_id):
            return await handler(event, data)
        
        # Выполняем проверку подписок
        is_subscribed = await self._check_user_subscriptions(user_id)
        
        if not is_subscribed:
            await self._handle_missing_subscriptions(event)
            return None
        
        # Обновляем время последней проверки
        self._last_check[user_id] = datetime.utcnow()
        
        # Передаем управление следующему handler
        return await handler(event, data)
    
    async def _should_check_subscription(self, user_id: int) -> bool:
        """
        Определить нужна ли проверка подписки
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True если нужна проверка
        """
        # Проверяем админов
        if bot_config.is_admin(user_id):
            return False
        
        # Проверяем тип пользователя
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            
            if not user:
                return True
            
            # Premium и admin пользователи освобождены
            if user.current_user_type in ['premium', 'admin']:
                return False
            
            # Trial пользователи тоже могут быть освобождены
            if user.current_user_type == 'trial' and not bot_config.trial_requires_subscription:
                return False
        
        # Проверяем интервал с последней проверки
        if user_id in self._last_check:
            last_check = self._last_check[user_id]
            if datetime.utcnow() - last_check < timedelta(seconds=self.check_interval):
                return False
        
        return True
    
    async def _check_user_subscriptions(self, user_id: int) -> bool:
        """
        Проверить подписки пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True если подписан на все каналы
        """
        if not self.checker:
            return True
        
        try:
            async with get_async_session() as session:
                result = await self.checker.check_user_subscriptions(
                    user_id=user_id,
                    session=session,
                    force_check=False
                )
                
                return result.get('all_subscribed', False)
        
        except Exception as e:
            logger.error(f"Error checking subscriptions: {e}", user_id=user_id)
            # При ошибке пропускаем пользователя
            return True
    
    async def _handle_missing_subscriptions(self, event: Message):
        """Обработка отсутствующих подписок"""
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✅ Проверить подписки",
                    callback_data="check_subscriptions"
                )],
                [InlineKeyboardButton(
                    text="💎 Купить Premium (без подписок)",
                    callback_data="buy_premium"
                )]
            ])
            
            await event.answer(
                "🔒 <b>Необходимо подписаться на обязательные каналы</b>\n\n"
                "Для использования бота необходимо подписаться на наши каналы.\n"
                "Это бесплатно и займет всего минуту!\n\n"
                "Нажмите кнопку ниже для проверки подписок.",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Error sending subscription message: {e}")


class SkipSubscriptionCheck:
    """Контекстный менеджер для пропуска проверки подписок"""
    
    def __init__(self, middleware: SubscriptionCheckMiddleware, user_id: int):
        self.middleware = middleware
        self.user_id = user_id
        self.original_value = None
    
    def __enter__(self):
        # Временно отмечаем что проверка выполнена
        self.original_value = self.middleware._last_check.get(self.user_id)
        self.middleware._last_check[self.user_id] = datetime.utcnow()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Восстанавливаем оригинальное значение
        if self.original_value:
            self.middleware._last_check[self.user_id] = self.original_value
        else:
            self.middleware._last_check.pop(self.user_id, None)