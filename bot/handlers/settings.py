"""
VideoBot Pro - User Settings Handler
Обработчик настроек пользователя
"""

import structlog
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command

from shared.config.database import get_async_session
from shared.models import User
from bot.config import bot_config
from bot.utils.user_manager import get_or_create_user, update_user_activity

logger = structlog.get_logger(__name__)

router = Router(name="settings")


class SettingsStates(StatesGroup):
    """Состояния FSM для настроек"""
    editing_language = State()
    editing_quality = State()
    editing_notifications = State()


@router.message(Command("settings"))
async def settings_command(message: Message):
    """Команда настроек"""
    user_id = message.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await get_or_create_user(
                session=session,
                telegram_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name
            )
            
            await update_user_activity(session, user, message.message_id)
            await session.commit()
        
        await show_main_settings(message, user)
        
    except Exception as e:
        logger.error(f"Error in settings command: {e}", user_id=user_id)
        await message.answer("Ошибка при загрузке настроек")


@router.callback_query(F.data == "settings")
async def handle_settings_callback(callback: CallbackQuery):
    """Обработка callback настроек"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await get_or_create_user(
                session=session,
                telegram_id=user_id,
                username=callback.from_user.username,
                first_name=callback.from_user.first_name
            )
            await session.commit()
        
        await show_main_settings(callback.message, user, edit=True)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in settings callback: {e}", user_id=user_id)
        await callback.answer("Ошибка при загрузке настроек", show_alert=True)


async def show_main_settings(message: Message, user: User, edit: bool = False):
    """Показать главное меню настроек"""
    
    # Текущие настройки
    current_language = user.ui_language or "ru"
    language_name = {"ru": "Русский", "en": "English"}.get(current_language, "Русский")
    
    # Настройки качества из предпочтений
    download_prefs = user.download_preferences or {}
    quality_mode = download_prefs.get("quality_mode", "auto")
    quality_display = {
        "auto": "Автоматическое",
        "manual": "Ручное",
        "max": "Максимальное"
    }.get(quality_mode, "Автоматическое")
    
    # Настройки уведомлений
    notification_prefs = user.notification_settings or {}
    notifications_enabled = notification_prefs.get("enabled", True)
    
    settings_text = [
        "⚙️ Настройки",
        "",
        "📱 Текущие настройки:",
        f"• 🌐 Язык: {language_name}",
        f"• 🎬 Качество видео: {quality_display}",
        f"• 🔔 Уведомления: {'Включены' if notifications_enabled else 'Отключены'}",
        "",
        "💡 Доступные настройки:"
    ]
    
    keyboard_rows = []
    
    # Основные настройки
    keyboard_rows.extend([
        [InlineKeyboardButton(text="🌐 Язык интерфейса", callback_data="settings_language")],
        [InlineKeyboardButton(text="🎬 Качество видео", callback_data="settings_quality")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications")]
    ])
    
    # Настройки доставки
    keyboard_rows.append([InlineKeyboardButton(text="📦 Способ доставки файлов", callback_data="settings_delivery")])
    
    # Premium настройки
    if user.current_user_type in ["premium", "admin"]:
        keyboard_rows.extend([
            [InlineKeyboardButton(text="🎨 Персонализация", callback_data="settings_personalization")],
            [InlineKeyboardButton(text="📊 Расширенные настройки", callback_data="settings_advanced")]
        ])
    
    # Дополнительные опции
    keyboard_rows.extend([
        [InlineKeyboardButton(text="🔒 Приватность", callback_data="settings_privacy")],
        [InlineKeyboardButton(text="📄 Экспорт данных", callback_data="settings_export")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    text = "\n".join(settings_text)
    
    if edit:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "settings_language")
async def handle_language_settings(callback: CallbackQuery, state: FSMContext):
    """Настройки языка"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            current_language = user.ui_language or "ru"

            language_text = [
                "🌐 Выбор языка интерфейса",
                "",
                f"Текущий язык: { {'ru': 'Русский', 'en': 'English'}.get(current_language, 'Русский')}",
                "",
                "Доступные языки:"
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{'✅' if current_language == 'ru' else '🔘'} Русский",
                    callback_data="set_language_ru"
                )],
                [InlineKeyboardButton(
                    text=f"{'✅' if current_language == 'en' else '🔘'} English", 
                    callback_data="set_language_en"
                )],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
            ])
            
            await callback.message.edit_text("\n".join(language_text), reply_markup=keyboard)
            await callback.answer()
    
    except Exception as e:
        logger.error(f"Error in language settings: {e}", user_id=user_id)
        await callback.answer("Ошибка при загрузке настроек языка", show_alert=True)


@router.callback_query(F.data.startswith("set_language_"))
async def handle_set_language(callback: CallbackQuery):
    """Установка языка"""
    user_id = callback.from_user.id
    language = callback.data.split("_")[-1]
    
    if language not in ["ru", "en"]:
        await callback.answer("Неподдерживаемый язык", show_alert=True)
        return
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            user.ui_language = language
            await session.commit()
            
            language_name = {"ru": "Русский", "en": "English"}[language]
            await callback.answer(f"Язык изменен на {language_name}", show_alert=True)
            
            # Возвращаемся к настройкам
            await show_main_settings(callback.message, user, edit=True)
            
            logger.info(f"Language changed", user_id=user_id, language=language)
    
    except Exception as e:
        logger.error(f"Error setting language: {e}", user_id=user_id)
        await callback.answer("Ошибка при сохранении языка", show_alert=True)


@router.callback_query(F.data == "settings_quality")
async def handle_quality_settings(callback: CallbackQuery):
    """Настройки качества видео"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            download_prefs = user.download_preferences or {}
            current_mode = download_prefs.get("quality_mode", "auto")
            max_quality = bot_config.get_user_file_limit(user.current_user_type)
            
            quality_text = [
                "🎬 Настройки качества видео",
                "",
                f"Ваш тип аккаунта: {user.current_user_type}",
                f"Максимальное качество: {max_quality}",
                "",
                "Режимы качества:"
            ]
            
            keyboard_rows = [
                [InlineKeyboardButton(
                    text=f"{'✅' if current_mode == 'auto' else '🔘'} Автоматическое (рекомендуется)",
                    callback_data="set_quality_auto"
                )],
                [InlineKeyboardButton(
                    text=f"{'✅' if current_mode == 'max' else '🔘'} Максимальное доступное",
                    callback_data="set_quality_max"
                )]
            ]
            
            # Ручной выбор только для Premium
            if user.current_user_type in ["premium", "admin"]:
                keyboard_rows.append([InlineKeyboardButton(
                    text=f"{'✅' if current_mode == 'manual' else '🔘'} Ручной выбор",
                    callback_data="set_quality_manual"
                )])
            
            keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await callback.message.edit_text("\n".join(quality_text), reply_markup=keyboard)
            await callback.answer()
    
    except Exception as e:
        logger.error(f"Error in quality settings: {e}", user_id=user_id)
        await callback.answer("Ошибка при загрузке настроек качества", show_alert=True)


@router.callback_query(F.data.startswith("set_quality_"))
async def handle_set_quality(callback: CallbackQuery):
    """Установка режима качества"""
    user_id = callback.from_user.id
    quality_mode = callback.data.split("_")[-1]
    
    if quality_mode not in ["auto", "max", "manual"]:
        await callback.answer("Неподдерживаемый режим", show_alert=True)
        return
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            # Проверяем доступность режима
            if quality_mode == "manual" and user.current_user_type not in ["premium", "admin"]:
                await callback.answer("Ручной выбор доступен только для Premium", show_alert=True)
                return
            
            # Обновляем настройки
            if not user.download_preferences:
                user.download_preferences = {}
            
            user.download_preferences["quality_mode"] = quality_mode
            await session.commit()
            
            mode_names = {
                "auto": "автоматическое",
                "max": "максимальное доступное", 
                "manual": "ручной выбор"
            }
            
            await callback.answer(f"Качество установлено: {mode_names[quality_mode]}", show_alert=True)
            
            # Возвращаемся к настройкам
            await show_main_settings(callback.message, user, edit=True)
            
            logger.info(f"Quality mode changed", user_id=user_id, quality_mode=quality_mode)
    
    except Exception as e:
        logger.error(f"Error setting quality: {e}", user_id=user_id)
        await callback.answer("Ошибка при сохранении настроек", show_alert=True)


@router.callback_query(F.data == "settings_notifications")
async def handle_notification_settings(callback: CallbackQuery):
    """Настройки уведомлений"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            notification_prefs = user.notification_settings or {}
            
            notification_text = [
                "🔔 Настройки уведомлений",
                "",
                "Управляйте тем, какие уведомления вы получаете:"
            ]
            
            # Текущие настройки
            enabled = notification_prefs.get("enabled", True)
            download_complete = notification_prefs.get("download_complete", True)
            premium_expiry = notification_prefs.get("premium_expiry", True)
            system_updates = notification_prefs.get("system_updates", True)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{'🔔' if enabled else '🔕'} Все уведомления",
                    callback_data="toggle_notifications_enabled"
                )],
                [InlineKeyboardButton(
                    text=f"{'✅' if download_complete else '❌'} Завершение скачивания",
                    callback_data="toggle_notifications_download"
                )],
                [InlineKeyboardButton(
                    text=f"{'✅' if premium_expiry else '❌'} Истечение Premium",
                    callback_data="toggle_notifications_premium"
                )],
                [InlineKeyboardButton(
                    text=f"{'✅' if system_updates else '❌'} Системные уведомления",
                    callback_data="toggle_notifications_system"
                )],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
            ])
            
            await callback.message.edit_text("\n".join(notification_text), reply_markup=keyboard)
            await callback.answer()
    
    except Exception as e:
        logger.error(f"Error in notification settings: {e}", user_id=user_id)
        await callback.answer("Ошибка при загрузке настроек уведомлений", show_alert=True)


@router.callback_query(F.data.startswith("toggle_notifications_"))
async def handle_toggle_notification(callback: CallbackQuery):
    """Переключение настроек уведомлений"""
    user_id = callback.from_user.id
    setting_key = callback.data.replace("toggle_notifications_", "")
    
    key_mapping = {
        "enabled": "enabled",
        "download": "download_complete", 
        "premium": "premium_expiry",
        "system": "system_updates"
    }
    
    if setting_key not in key_mapping:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            if not user.notification_settings:
                user.notification_settings = {}
            
            setting_name = key_mapping[setting_key]
            current_value = user.notification_settings.get(setting_name, True)
            user.notification_settings[setting_name] = not current_value
            
            await session.commit()
            
            status = "включены" if not current_value else "отключены"
            await callback.answer(f"Уведомления {status}", show_alert=False)
            
            # Обновляем интерфейс
            await handle_notification_settings(callback)
            
            logger.info(f"Notification setting changed", user_id=user_id, setting=setting_name, value=not current_value)
    
    except Exception as e:
        logger.error(f"Error toggling notification: {e}", user_id=user_id)
        await callback.answer("Ошибка при изменении настроек", show_alert=True)


@router.callback_query(F.data == "settings_delivery")
async def handle_delivery_settings(callback: CallbackQuery):
    """Настройки способа доставки файлов"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            download_prefs = user.download_preferences or {}
            default_delivery = download_prefs.get("default_delivery", "individual")
            
            delivery_text = [
                "📦 Способ доставки файлов",
                "",
                "Как по умолчанию получать файлы при batch скачивании:",
                "",
                "📱 Индивидуально - каждый файл отдельным сообщением",
                "📦 Архивом - все файлы в ZIP через CDN",
                "🤔 Спрашивать - выбор при каждом скачивании"
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{'✅' if default_delivery == 'individual' else '🔘'} Индивидуально",
                    callback_data="set_delivery_individual"
                )],
                [InlineKeyboardButton(
                    text=f"{'✅' if default_delivery == 'archive' else '🔘'} Архивом",
                    callback_data="set_delivery_archive"
                )],
                [InlineKeyboardButton(
                    text=f"{'✅' if default_delivery == 'ask' else '🔘'} Всегда спрашивать",
                    callback_data="set_delivery_ask"
                )],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
            ])
            
            await callback.message.edit_text("\n".join(delivery_text), reply_markup=keyboard)
            await callback.answer()
    
    except Exception as e:
        logger.error(f"Error in delivery settings: {e}", user_id=user_id)
        await callback.answer("Ошибка при загрузке настроек доставки", show_alert=True)


@router.callback_query(F.data.startswith("set_delivery_"))
async def handle_set_delivery(callback: CallbackQuery):
    """Установка способа доставки"""
    user_id = callback.from_user.id
    delivery_mode = callback.data.split("_")[-1]
    
    if delivery_mode not in ["individual", "archive", "ask"]:
        await callback.answer("Неподдерживаемый способ", show_alert=True)
        return
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            if not user.download_preferences:
                user.download_preferences = {}
            
            user.download_preferences["default_delivery"] = delivery_mode
            await session.commit()
            
            mode_names = {
                "individual": "индивидуально",
                "archive": "архивом",
                "ask": "всегда спрашивать"
            }
            
            await callback.answer(f"Способ доставки: {mode_names[delivery_mode]}", show_alert=True)
            
            # Возвращаемся к настройкам
            await show_main_settings(callback.message, user, edit=True)
            
            logger.info(f"Delivery mode changed", user_id=user_id, delivery_mode=delivery_mode)
    
    except Exception as e:
        logger.error(f"Error setting delivery: {e}", user_id=user_id)
        await callback.answer("Ошибка при сохранении настроек", show_alert=True)


@router.callback_query(F.data == "settings_privacy")
async def handle_privacy_settings(callback: CallbackQuery):
    """Настройки приватности"""
    privacy_text = [
        "🔒 Настройки приватности",
        "",
        "🛡️ Защита данных:",
        "• Все персональные данные надежно защищены",
        "• Ваши файлы автоматически удаляются",
        "• История скачиваний сохраняется локально",
        "",
        "📊 Сбор данных:",
        "• Анонимная статистика использования",
        "• Аналитика ошибок для улучшения сервиса",
        "• Данные не передаются третьим лицам",
        "",
        "🗑️ Удаление данных:",
        "• Полное удаление аккаунта по запросу",
        "• Очистка истории скачиваний",
        "• Удаление файлов из CDN"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Удалить историю скачиваний", callback_data="privacy_clear_history")],
        [InlineKeyboardButton(text="📄 Политика конфиденциальности", callback_data="privacy_policy")],
        [InlineKeyboardButton(text="❌ Удалить аккаунт", callback_data="privacy_delete_account")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
    ])
    
    await callback.message.edit_text("\n".join(privacy_text), reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "settings_export")
async def handle_export_settings(callback: CallbackQuery):
    """Экспорт пользовательских данных"""
    user_id = callback.from_user.id
    
    export_text = [
        "📄 Экспорт данных",
        "",
        "📦 Доступные данные для экспорта:",
        "• История скачиваний",
        "• Настройки аккаунта",
        "• Статистика использования",
        "• История платежей (для Premium)",
        "",
        "📧 Экспорт будет отправлен в личные сообщения",
        "⏱️ Время подготовки: до 5 минут"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Экспортировать все данные", callback_data="export_all_data")],
        [InlineKeyboardButton(text="📊 Только статистику", callback_data="export_stats_only")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="settings")]
    ])
    
    await callback.message.edit_text("\n".join(export_text), reply_markup=keyboard)
    await callback.answer()


# Обработчики экспорта данных (заглушки)
@router.callback_query(F.data == "export_all_data")
async def handle_export_all(callback: CallbackQuery):
    await callback.answer("Функция в разработке", show_alert=True)

@router.callback_query(F.data == "privacy_clear_history")  
async def handle_clear_history(callback: CallbackQuery):
    await callback.answer("Функция в разработке", show_alert=True)

@router.callback_query(F.data == "privacy_delete_account")
async def handle_delete_account(callback: CallbackQuery):
    await callback.answer("Обратитесь в поддержку для удаления аккаунта", show_alert=True)