"""
VideoBot Pro - Subscription Check Handler
Обработчик проверки обязательных подписок на каналы
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aiogram import Router, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.enums import ChatMemberStatus

from shared.config.database import get_async_session
from shared.models import User, RequiredChannel, EventType
from shared.models.analytics import track_user_event
from bot.config import bot_config, get_message, MessageType
from bot.utils.user_manager import update_user_activity

logger = structlog.get_logger(__name__)

router = Router(name="subscription_check")


class SubscriptionChecker:
    """Класс для проверки подписок пользователя"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self._cache = {}  # Кэш результатов проверки
        self._cache_ttl = 300  # 5 минут
    
    async def check_user_subscriptions(self, user_id: int, force_check: bool = False) -> Dict:
        """
        Проверить подписки пользователя на все обязательные каналы
        
        Returns:
            Dict с результатами проверки:
            {
                "all_subscribed": bool,
                "subscribed_channels": List[str],
                "missing_channels": List[Dict],
                "error_channels": List[Dict],
                "check_timestamp": datetime
            }
        """
        
        # Проверяем кэш если не принудительная проверка
        cache_key = f"sub_check_{user_id}"
        if not force_check and cache_key in self._cache:
            cached_result = self._cache[cache_key]
            if datetime.utcnow() - cached_result["check_timestamp"] < timedelta(seconds=self._cache_ttl):
                return cached_result
        
        try:
            async with get_async_session() as session:
                # Получаем пользователя
                user = await session.get(User, user_id)
                if not user:
                    return {"error": "User not found"}
                
                # Получаем активные каналы для типа пользователя
                channels = RequiredChannel.get_active_channels_for_user_type(
                    session, user.current_user_type
                )
                
                if not channels:
                    # Нет обязательных каналов
                    result = {
                        "all_subscribed": True,
                        "subscribed_channels": [],
                        "missing_channels": [],
                        "error_channels": [],
                        "check_timestamp": datetime.utcnow()
                    }
                    self._cache[cache_key] = result
                    return result
                
                # Проверяем каждый канал
                subscribed = []
                missing = []
                errors = []
                
                for channel in channels:
                    try:
                        is_subscribed = await self._check_channel_subscription(
                            user_id, channel.channel_id
                        )
                        
                        if is_subscribed:
                            subscribed.append(channel.channel_id)
                        else:
                            missing.append({
                                "channel_id": channel.channel_id,
                                "channel_name": channel.channel_name,
                                "telegram_url": channel.telegram_url,
                                "invite_link": channel.invite_link
                            })
                    
                    except Exception as e:
                        logger.error(
                            f"Error checking subscription to {channel.channel_id}: {e}",
                            user_id=user_id
                        )
                        errors.append({
                            "channel_id": channel.channel_id,
                            "channel_name": channel.channel_name,
                            "error": str(e)
                        })
                
                # Формируем результат
                result = {
                    "all_subscribed": len(missing) == 0 and len(errors) == 0,
                    "subscribed_channels": subscribed,
                    "missing_channels": missing,
                    "error_channels": errors,
                    "check_timestamp": datetime.utcnow()
                }
                
                # Обновляем данные пользователя
                user.subscribed_channels = subscribed
                user.last_subscription_check = result["check_timestamp"]
                user.subscription_check_passed = result["all_subscribed"]
                
                await session.commit()
                
                # Кэшируем результат
                self._cache[cache_key] = result
                
                # Аналитика
                event_type = EventType.SUBSCRIPTION_CHECKED if result["all_subscribed"] else EventType.SUBSCRIPTION_FAILED
                await track_user_event(
                    event_type=event_type,
                    user_id=user.id,
                    telegram_user_id=user_id,
                    event_data={
                        "channels_checked": len(channels),
                        "subscribed_count": len(subscribed),
                        "missing_count": len(missing),
                        "error_count": len(errors)
                    }
                )
                
                return result
        
        except Exception as e:
            logger.error(f"Error in subscription check: {e}", user_id=user_id)
            return {"error": str(e)}
    
    async def _check_channel_subscription(self, user_id: int, channel_id: str) -> bool:
        """Проверить подписку на конкретный канал"""
        try:
            member = await self.bot.get_chat_member(channel_id, user_id)
            
            # Считаем подписанными всех кроме left и kicked
            subscribed_statuses = [
                ChatMemberStatus.CREATOR,
                ChatMemberStatus.ADMINISTRATOR, 
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.RESTRICTED  # Ограниченные, но все еще в канале
            ]
            
            return member.status in subscribed_statuses
        
        except TelegramBadRequest as e:
            if "chat not found" in str(e).lower():
                logger.warning(f"Channel not found: {channel_id}")
                return False  # Канал не найден
            elif "user not found" in str(e).lower():
                return False  # Пользователь не найден
            else:
                raise
        
        except TelegramForbiddenError:
            # Бот не имеет доступа к каналу
            logger.warning(f"Bot has no access to channel: {channel_id}")
            return False
        
        except Exception as e:
            logger.error(f"Unexpected error checking subscription: {e}")
            raise
    
    def clear_cache(self, user_id: int = None):
        """Очистить кэш проверок"""
        if user_id:
            cache_key = f"sub_check_{user_id}"
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()


# Глобальный экземпляр проверяльщика
subscription_checker: Optional[SubscriptionChecker] = None


def init_subscription_checker(bot: Bot):
    """Инициализация проверяльщика подписок"""
    global subscription_checker
    subscription_checker = SubscriptionChecker(bot)


async def check_required_subscriptions(user_id: int, force_check: bool = False) -> Dict:
    """Удобная функция для проверки подписок"""
    if not subscription_checker:
        return {"error": "Subscription checker not initialized"}
    
    return await subscription_checker.check_user_subscriptions(user_id, force_check)


async def show_subscription_check(message: Message, subscription_status: Dict = None):
    """Показать интерфейс проверки подписок"""
    user_id = message.from_user.id
    
    # Если статус не передан, проверяем
    if not subscription_status:
        subscription_status = await check_required_subscriptions(user_id)
    
    if subscription_status.get("error"):
        await message.answer("Ошибка при проверке подписок. Попробуйте позже.")
        return
    
    if subscription_status["all_subscribed"]:
        await message.answer(
            "✅ Отлично! Вы подписаны на все обязательные каналы.\n"
            "Теперь можете пользоваться ботом!"
        )
        return
    
    # Формируем сообщение с каналами
    missing_channels = subscription_status["missing_channels"]
    
    channels_text = []
    keyboard_buttons = []
    
    for i, channel in enumerate(missing_channels):
        # Статус подписки
        status = "🔴 Не подписан"
        
        channels_text.append(
            f"{status} <b>{channel['channel_name']}</b>\n"
            f"👥 Подписчиков: много\n"
        )
        
        # Кнопка подписки
        if channel.get("invite_link"):
            button_url = channel["invite_link"]
        else:
            button_url = channel["telegram_url"]
        
        keyboard_buttons.append([
            InlineKeyboardButton(
                text=f"📱 {channel['channel_name']}", 
                url=button_url
            )
        ])
    
    # Добавляем кнопки действий
    keyboard_buttons.extend([
        [InlineKeyboardButton(text="✅ Я подписался!", callback_data="check_subscriptions")],
        [InlineKeyboardButton(text="🔄 Проверить еще раз", callback_data="recheck_subscriptions")],
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium")]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    main_text = [
        "🔒 <b>Для продолжения подпишитесь на каналы</b>",
        "",
        "📢 <b>Обязательные каналы:</b>",
        "",
        *channels_text,
        f"📊 Прогресс: {len(subscription_status['subscribed_channels'])}/{len(missing_channels) + len(subscription_status['subscribed_channels'])} каналов",
        "",
        "💡 <i>Premium пользователи освобождены от этого требования</i>"
    ]
    
    await message.answer(
        "\n".join(main_text),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


@router.callback_query(F.data == "check_subscriptions")
async def handle_subscription_check(callback: CallbackQuery):
    """Обработка проверки подписок"""
    user_id = callback.from_user.id
    
    # Показываем индикатор загрузки
    await callback.answer("Проверяю подписки...", show_alert=False)
    
    try:
        # Принудительная проверка подписок
        subscription_status = await check_required_subscriptions(user_id, force_check=True)
        
        if subscription_status.get("error"):
            await callback.message.edit_text(
                "❌ Ошибка при проверке подписок.\n"
                "Попробуйте позже или обратитесь в поддержку."
            )
            return
        
        if subscription_status["all_subscribed"]:
            # Все подписки активны
            await callback.message.edit_text(
                "🎉 <b>Отлично! Все подписки активны</b>\n\n"
                + "\n".join([f"✅ {ch}" for ch in subscription_status["subscribed_channels"]]) +
                "\n\n🎁 Теперь доступно:\n"
                "• 10 скачиваний в день\n"
                "• HD качество (до 720p)\n"
                "• Файлы до 50MB\n\n"
                "📊 Использовано сегодня: 0/10"
            )
            
            # Обновляем активность пользователя
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                if user:
                    await update_user_activity(session, user)
                    await session.commit()
        
        else:
            # Еще есть неподписанные каналы
            missing_count = len(subscription_status["missing_channels"])
            subscribed_count = len(subscription_status["subscribed_channels"])
            
            await callback.message.edit_text(
                f"⚠️ <b>Осталось подписаться: {missing_count} каналов</b>\n\n"
                f"✅ Подписаны: {subscribed_count}\n"
                f"❌ Не подписаны: {missing_count}\n\n"
                "🔄 Подпишитесь на оставшиеся каналы и нажмите кнопку еще раз."
            )
            
            # Показываем обновленный список
            await asyncio.sleep(2)
            await show_subscription_check(callback.message, subscription_status)
    
    except Exception as e:
        logger.error(f"Error in subscription check callback: {e}", user_id=user_id)
        await callback.message.edit_text(
            "❌ Произошла ошибка при проверке.\n"
            "Попробуйте еще раз или обратитесь в поддержку."
        )


@router.callback_query(F.data == "recheck_subscriptions")
async def handle_subscription_recheck(callback: CallbackQuery):
    """Перепроверка подписок"""
    user_id = callback.from_user.id
    
    await callback.answer("Проверяю подписки заново...", show_alert=False)
    
    # Очищаем кэш и проверяем заново
    if subscription_checker:
        subscription_checker.clear_cache(user_id)
    
    subscription_status = await check_required_subscriptions(user_id, force_check=True)
    
    if subscription_status.get("error"):
        await callback.answer("Ошибка при проверке", show_alert=True)
        return
    
    if subscription_status["all_subscribed"]:
        await callback.message.edit_text(
            "🎉 <b>Поздравляем!</b>\n\n"
            "Все подписки активированы!\n"
            "Теперь вы можете пользоваться ботом.\n\n"
            "💡 Отправьте ссылку на видео для скачивания!"
        )
    else:
        await show_subscription_check(callback.message, subscription_status)


async def periodic_subscription_cleanup():
    """Периодическая очистка кэша подписок"""
    if subscription_checker:
        subscription_checker.clear_cache()
        logger.info("Subscription cache cleared")


# Утилиты для других модулей

async def is_user_subscribed_to_required_channels(user_id: int) -> bool:
    """Проверить подписан ли пользователь на все обязательные каналы"""
    if not bot_config.required_subs_enabled:
        return True
    
    result = await check_required_subscriptions(user_id)
    return result.get("all_subscribed", False)


async def get_user_subscription_status(user_id: int) -> Optional[Dict]:
    """Получить статус подписок пользователя"""
    try:
        return await check_required_subscriptions(user_id)
    except Exception as e:
        logger.error(f"Error getting subscription status: {e}", user_id=user_id)
        return None


async def force_subscription_recheck(user_id: int) -> bool:
    """Принудительная перепроверка подписок"""
    try:
        if subscription_checker:
            subscription_checker.clear_cache(user_id)
        
        result = await check_required_subscriptions(user_id, force_check=True)
        return result.get("all_subscribed", False)
    except Exception as e:
        logger.error(f"Error in force recheck: {e}", user_id=user_id)
        return False