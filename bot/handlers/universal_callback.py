"""
VideoBot Pro - Universal Callback Handler
Универсальный обработчик всех callback запросов с перенаправлением
"""

import structlog
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from shared.config.database import get_async_session
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import bot_config
from bot.utils.user_manager import get_or_create_user

logger = structlog.get_logger(__name__)

router = Router(name="universal_callback")

# Маппинг callback'ов к их обработчикам
CALLBACK_ROUTES = {
    # Главное меню
    "back_main": "main",
    "status": "status", 
    "help": "help",
    
    # Настройки
    "settings": "settings_main",
    "settings_quality": "settings_quality",
    "settings_language": "settings_language", 
    "settings_notifications": "settings_notifications",
    "settings_delivery": "settings_delivery",
    "settings_privacy": "settings_privacy",
    "settings_export": "settings_export",
    
    # Админка
    "admin_panel": "admin_main",
    "admin_users": "admin_users",
    "admin_stats": "admin_stats", 
    "admin_broadcast": "admin_broadcast",
    "admin_channels": "admin_channels",
    "admin_finance": "admin_finance",
    "admin_system": "admin_system",
    "admin_logs": "admin_logs",
    
    # Premium
    "premium_info": "premium_main",
    "buy_premium": "premium_buy",
    "premium_benefits": "premium_benefits",
    "premium_settings": "premium_settings",
    "premium_stats": "premium_stats",
    "premium_referral": "premium_referral",
    
    # Trial
    "trial": "trial_main", 
    "trial_info": "trial_info",
    "activate_trial": "trial_activate",
    "trial_stats": "trial_stats",
    "trial_status": "trial_status",
    
    # Downloads
    "download": "download_main",
    "batch_individual": "batch_individual",
    "batch_archive": "batch_archive", 
    "batch_selective": "batch_selective",
    "batch_cancel": "batch_cancel",
    
    # Subscriptions
    "check_subscriptions": "sub_check",
    "recheck_subscriptions": "sub_recheck",
    
    # Utilities
    "detailed_stats": "stats_detailed",
    "export_data": "export_data",
    "cancel": "cancel",
    "confirm": "confirm",
}


@router.callback_query()
async def universal_callback_handler(callback: CallbackQuery, state: FSMContext):
    """
    Универсальный обработчик всех callback запросов
    """
    callback_data = callback.data
    user_id = callback.from_user.id

    logger.info(f"Processing callback: {callback_data}", user_id=user_id)

    try:
        # Получаем пользователя из БД
        async with get_async_session() as session:
            from bot.utils.user_manager import get_or_create_user
            user = await get_or_create_user(
                session=session,
                telegram_id=user_id,
                username=callback.from_user.username,
                first_name=callback.from_user.first_name
            )
            await session.commit()

        # Реальные обработчики callback'ов
        if callback_data == "status":
            await show_user_status(callback, user)

        elif callback_data == "settings":
            await show_settings_menu(callback, user)

        elif callback_data == "help":
            await show_help_menu(callback)

        elif callback_data == "download":
            await show_download_info(callback)

        elif callback_data == "trial":
            await handle_trial_request(callback, user, state)

        elif callback_data == "premium_info" or callback_data == "buy_premium":
            await handle_premium_request(callback, user, state)

        elif callback_data == "back_main":
            await show_main_menu(callback, user)

        elif callback_data == "admin_panel":
            if bot_config.is_admin(user_id):
                await show_admin_panel(callback)
            else:
                await callback.answer("🚫 Доступ запрещен", show_alert=True)

        # Остальные callback'и
        else:
            await callback.answer("Функция в разработке", show_alert=True)

    except Exception as e:
        logger.error(f"Error in callback handler: {e}", user_id=user_id)
        await callback.answer("Произошла ошибка", show_alert=True)

async def route_callback(callback: CallbackQuery, state: FSMContext, route: str):
    """Перенаправление callback'а к соответствующему обработчику"""
    
    try:
        if route == "main":
            from .callback_handlers import handle_back_to_main
            return await handle_back_to_main(callback, state)
            
        elif route == "status":
            from .callback_handlers import handle_status_callback
            return await handle_status_callback(callback)
            
        elif route == "help":
            from .callback_handlers import handle_help_callback
            return await handle_help_callback(callback)
            
        # Настройки
        elif route == "settings_main":
            from .settings import handle_settings_callback
            return await handle_settings_callback(callback)
            
        elif route == "settings_quality":
            from .settings import handle_quality_settings
            return await handle_quality_settings(callback)
            
        elif route == "settings_language":
            from .settings import handle_language_settings
            return await handle_language_settings(callback, state)
            
        elif route == "settings_notifications":
            from .settings import handle_notification_settings
            return await handle_notification_settings(callback)
            
        elif route == "settings_delivery":
            from .settings import handle_delivery_settings
            return await handle_delivery_settings(callback)
            
        elif route == "settings_privacy":
            from .settings import handle_privacy_settings
            return await handle_privacy_settings(callback)
            
        # Админка
        elif route == "admin_main":
            from .admin_commands import admin_panel
            # Создаем mock message объект
            mock_message = type('MockMessage', (), {
                'from_user': callback.from_user,
                'answer': callback.message.edit_text,
                'edit_text': callback.message.edit_text
            })()
            return await admin_panel(mock_message)
            
        elif route == "admin_users":
            from .admin_commands import handle_admin_users
            return await handle_admin_users(callback, state)
            
        elif route == "admin_stats":
            from .admin_commands import handle_admin_stats
            return await handle_admin_stats(callback)
            
        # Premium
        elif route == "premium_main" or route == "buy_premium":
            from .premium import premium_command
            mock_message = type('MockMessage', (), {
                'from_user': callback.from_user,
                'answer': callback.message.edit_text
            })()
            return await premium_command(mock_message, state)
            
        elif route == "premium_benefits":
            from .callback_handlers import handle_premium_benefits
            return await handle_premium_benefits(callback)
            
        # Trial
        elif route == "trial_main" or route == "trial":
            from .trial_system import trial_command
            mock_message = type('MockMessage', (), {
                'from_user': callback.from_user,
                'answer': callback.message.edit_text,
                'text': '/trial'
            })()
            return await trial_command(mock_message, state)
            
        elif route == "trial_activate":
            from .trial_system import handle_trial_activation
            return await handle_trial_activation(callback, state)
            
        elif route == "trial_stats":
            from .trial_system import show_trial_statistics
            return await show_trial_statistics(callback)
            
        # Downloads
        elif route == "batch_individual":
            from .batch_download import handle_individual_delivery
            return await handle_individual_delivery(callback, state)
            
        elif route == "batch_archive":
            from .batch_download import handle_archive_delivery
            return await handle_archive_delivery(callback, state)
            
        elif route == "batch_selective":
            from .batch_download import handle_selective_delivery
            return await handle_selective_delivery(callback, state)
            
        elif route == "batch_cancel":
            from .batch_download import handle_cancel_batch
            return await handle_cancel_batch(callback, state)
            
        # Subscriptions
        elif route == "sub_check":
            from .subscription_check import handle_subscription_check
            return await handle_subscription_check(callback)
            
        elif route == "sub_recheck":
            from .subscription_check import handle_subscription_recheck
            return await handle_subscription_recheck(callback)
            
        # Utilities
        elif route == "stats_detailed":
            from .callback_handlers import handle_detailed_stats
            return await handle_detailed_stats(callback)
            
        elif route == "cancel":
            from .callback_handlers import handle_cancel
            return await handle_cancel(callback, state)
            
        else:
            # Неизвестный route
            await callback.answer("Функция в разработке", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in route {route}: {e}", user_id=callback.from_user.id)
        await callback.answer("Произошла ошибка", show_alert=True)


def get_prefix_handlers():
    """Возвращает обработчики для префиксов callback данных"""
    return {
        "set_language_": handle_language_set,
        "set_quality_": handle_quality_set,
        "set_delivery_": handle_delivery_set,
        "toggle_notifications_": handle_notification_toggle,
        "premium_plan_": handle_premium_plan,
        "payment_": handle_payment_method,
        "admin_grant_": handle_admin_grant,
        "admin_ban_": handle_admin_ban,
        "admin_user_": handle_admin_user_action,
        "batch_": handle_batch_action,
        "retry_": handle_retry_action,
    }


# Обработчики префиксов
async def handle_language_set(callback: CallbackQuery, state: FSMContext):
    """Обработка установки языка"""
    try:
        from .settings import handle_set_language
        return await handle_set_language(callback)
    except Exception as e:
        logger.error(f"Error setting language: {e}")
        await callback.answer("Ошибка при установке языка", show_alert=True)


async def handle_quality_set(callback: CallbackQuery, state: FSMContext):
    """Обработка установки качества"""
    try:
        from .settings import handle_set_quality
        return await handle_set_quality(callback)
    except Exception as e:
        logger.error(f"Error setting quality: {e}")
        await callback.answer("Ошибка при установке качества", show_alert=True)


async def handle_delivery_set(callback: CallbackQuery, state: FSMContext):
    """Обработка установки способа доставки"""
    try:
        from .settings import handle_set_delivery
        return await handle_set_delivery(callback)
    except Exception as e:
        logger.error(f"Error setting delivery: {e}")
        await callback.answer("Ошибка при установке доставки", show_alert=True)


async def handle_notification_toggle(callback: CallbackQuery, state: FSMContext):
    """Обработка переключения уведомлений"""
    try:
        from .settings import handle_toggle_notification
        return await handle_toggle_notification(callback)
    except Exception as e:
        logger.error(f"Error toggling notification: {e}")
        await callback.answer("Ошибка при изменении уведомлений", show_alert=True)


async def handle_premium_plan(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора премиум плана"""
    try:
        from .premium import handle_plan_selection
        return await handle_plan_selection(callback, state)
    except Exception as e:
        logger.error(f"Error selecting premium plan: {e}")
        await callback.answer("Ошибка при выборе плана", show_alert=True)


async def handle_payment_method(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора способа оплаты"""
    try:
        from .premium import handle_payment_method
        return await handle_payment_method(callback, state)
    except Exception as e:
        logger.error(f"Error selecting payment method: {e}")
        await callback.answer("Ошибка при выборе оплаты", show_alert=True)


async def handle_admin_grant(callback: CallbackQuery, state: FSMContext):
    """Обработка админских операций выдачи"""
    if "premium" in callback.data:
        try:
            from .admin_commands import handle_grant_premium
            return await handle_grant_premium(callback)
        except Exception as e:
            logger.error(f"Error granting premium: {e}")
            await callback.answer("Ошибка при выдаче премиум", show_alert=True)
    else:
        await callback.answer("Неизвестная операция", show_alert=True)


async def handle_admin_ban(callback: CallbackQuery, state: FSMContext):
    """Обработка админских операций бана"""
    try:
        from .admin_commands import handle_ban_user
        return await handle_ban_user(callback)
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await callback.answer("Ошибка при блокировке", show_alert=True)


async def handle_admin_user_action(callback: CallbackQuery, state: FSMContext):
    """Обработка других админских действий с пользователями"""
    await callback.answer("Функция в разработке", show_alert=True)


async def handle_batch_action(callback: CallbackQuery, state: FSMContext):
    """Обработка действий с batch"""
    try:
        from .batch_download import handle_batch_callbacks
        return await handle_batch_callbacks(callback, state)
    except Exception as e:
        logger.error(f"Error in batch action: {e}")
        await callback.answer("Ошибка в обработке batch", show_alert=True)


async def handle_retry_action(callback: CallbackQuery, state: FSMContext):
    """Обработка повтора операций"""
    await callback.answer("Функция повтора в разработке", show_alert=True)


# Debug handler - логирует все необработанные callback'и
@router.callback_query()
async def debug_unhandled_callback(callback: CallbackQuery):
    """Debug обработчик для необработанных callback'ов"""
    logger.warning(
        f"UNHANDLED CALLBACK: {callback.data}",
        user_id=callback.from_user.id,
        username=callback.from_user.username
    )
    
    await callback.answer(
        f"🐛 Debug: callback '{callback.data}' не обработан",
        show_alert=True
    )