"""
VideoBot Pro - Subscription Check Handler
Обработчик проверки обязательных подписок на каналы
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.enums import ChatMemberStatus

from shared.config.database import get_async_session
from shared.models import User, RequiredChannel, EventType
from shared.models.analytics import track_user_event
from bot.config import bot_config, get_message, MessageType
from bot.utils.user_manager import update_user_activity
from bot.utils.subscription_checker import SubscriptionChecker

logger = structlog.get_logger(__name__)

router = Router(name="subscription_check")

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