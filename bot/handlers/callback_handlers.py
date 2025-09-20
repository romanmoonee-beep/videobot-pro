"""
VideoBot Pro - Callback Handlers
Обработчик общих callback запросов и навигации
"""

import structlog
from typing import Dict, Any

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from shared.config.database import get_async_session
from shared.models import User
from bot.config import bot_config, get_message, MessageType
from bot.utils.user_manager import get_or_create_user, update_user_activity

logger = structlog.get_logger(__name__)

router = Router(name="callback_handlers")


@router.callback_query(F.data == "back_main")
async def handle_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Возврат к главному меню"""
    user_id = callback.from_user.id
    
    try:
        # Очищаем состояние
        await state.clear()
        
        async with get_async_session() as session:
            user = await get_or_create_user(
                session=session,
                telegram_id=user_id,
                username=callback.from_user.username,
                first_name=callback.from_user.first_name
            )
            await update_user_activity(session, user)
            await session.commit()
        
        # Показываем главное меню
        await show_main_menu(callback.message, user, edit=True)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in back to main: {e}", user_id=user_id)
        await callback.answer("Ошибка при возврате в меню", show_alert=True)


@router.callback_query(F.data == "status")
async def handle_status_callback(callback: CallbackQuery):
    """Показать статус пользователя"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await get_or_create_user(
                session=session,
                telegram_id=user_id,
                username=callback.from_user.username,
                first_name=callback.from_user.first_name
            )
            await update_user_activity(session, user)
            await session.commit()
            
            status_text = await format_user_status(user)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Детальная статистика", callback_data="detailed_stats")],
                [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
            ])
            
            await callback.message.edit_text(
                status_text,
                reply_markup=keyboard
            )
            await callback.answer()
    
    except Exception as e:
        logger.error(f"Error showing status: {e}", user_id=user_id)
        await callback.answer("Ошибка получения статуса", show_alert=True)


@router.callback_query(F.data == "help")
async def handle_help_callback(callback: CallbackQuery):
    """Показать помощь"""
    help_text = get_message(MessageType.HELP, "main")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Форматы", callback_data="help_formats")],
        [InlineKeyboardButton(text="💎 Premium", callback_data="premium_benefits")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_main")]
    ])
    
    await callback.message.edit_text(
        help_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "help_formats")
async def handle_help_formats(callback: CallbackQuery):
    """Показать поддерживаемые форматы"""
    formats_text = get_message(MessageType.HELP, "formats")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к помощи", callback_data="help")]
    ])
    
    await callback.message.edit_text(
        formats_text,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "premium_benefits")
async def handle_premium_benefits(callback: CallbackQuery):
    """Показать преимущества Premium"""
    benefits_text = [
        "💎 Преимущества Premium подписки",
        "",
        "🚀 Безграничные возможности:",
        "• ∞ Безлимитные скачивания",
        "• 🎬 4K качество видео (до 2160p)",
        "• 📦 Файлы до 500MB",
        "• ☁️ Хранение файлов 30 дней",
        "• 🚀 Приоритетная очередь",
        "• 🔓 Без обязательных подписок",
        "• 📊 Расширенная статистика",
        "• 🎨 Персонализация интерфейса",
        "",
        "💰 Стоимость: от $3.99/месяц",
        "🎁 Первый месяц со скидкой!",
        "",
        "📈 Сравнение с бесплатным:",
        "Free: 10 скачиваний/день, 720p, 50MB",
        "Premium: ∞ скачиваний, 4K, 500MB"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium")],
        [InlineKeyboardButton(text="🎁 Пробный период", callback_data="trial")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="help")]
    ])
    
    await callback.message.edit_text(
        "\n".join(benefits_text),
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "detailed_stats")
async def handle_detailed_stats(callback: CallbackQuery):
    """Показать детальную статистику"""
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
            
            # Получаем расширенную статистику
            stats = user.stats or {}
            
            stats_text = [
                "📊 Детальная статистика",
                "",
                f"👤 Пользователь: {user.display_name}",
                f"🆔 ID: {user.telegram_id}",
                f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}",
                f"⏰ Последняя активность: {user.last_active_at.strftime('%d.%m.%Y %H:%M') if user.last_active_at else 'Никогда'}",
                "",
                "📈 Статистика скачиваний:",
                f"• Сегодня: {user.downloads_today}",
                f"• Всего: {user.downloads_total}",
                f"• За этот месяц: {stats.get('monthly_downloads', 0)}",
                f"• Средний размер файла: {stats.get('avg_file_size_mb', 0):.1f} MB",
            ]
            
            # Статистика по платформам
            if stats.get('platforms'):
                stats_text.append("")
                stats_text.append("🎯 По платформам:")
                for platform, count in stats['platforms'].items():
                    emoji = {"youtube": "🔴", "tiktok": "🎵", "instagram": "📸"}.get(platform, "🎬")
                    stats_text.append(f"• {emoji} {platform.title()}: {count}")
            
            # Информация о подписке
            if user.current_user_type == "premium":
                stats_text.extend([
                    "",
                    "💎 Premium информация:",
                    f"• Активен с: {user.premium_started_at.strftime('%d.%m.%Y') if user.premium_started_at else 'Неизвестно'}",
                    f"• Действует до: {user.premium_expires_at.strftime('%d.%m.%Y')}",
                    f"• Автопродление: {'Включено' if user.premium_auto_renew else 'Отключено'}"
                ])
            elif user.trial_used:
                stats_text.extend([
                    "",
                    "🎁 Пробный период:",
                    f"• Использован: {user.trial_started_at.strftime('%d.%m.%Y') if user.trial_started_at else 'Да'}",
                    f"• Длительность: {stats.get('trial_downloads', 0)} скачиваний"
                ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Экспорт данных", callback_data="export_data")],
                [InlineKeyboardButton(text="🔙 Назад к статусу", callback_data="status")]
            ])
            
            await callback.message.edit_text(
                "\n".join(stats_text),
                reply_markup=keyboard
            )
            await callback.answer()
    
    except Exception as e:
        logger.error(f"Error showing detailed stats: {e}", user_id=user_id)
        await callback.answer("Ошибка получения статистики", show_alert=True)


@router.callback_query(F.data == "export_data")
async def handle_export_data(callback: CallbackQuery):
    """Экспорт пользовательских данных"""
    await callback.answer("Функция в разработке", show_alert=True)


@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    """Универсальная отмена действия"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено.\n\n"
        "💡 Используйте команды для работы с ботом."
    )
    await callback.answer("Отменено")


# === НОВЫЕ ОБРАБОТЧИКИ ДЛЯ НЕДОСТАЮЩИХ CALLBACK'ОВ ===

@router.callback_query(F.data == "download")
async def handle_download_callback(callback: CallbackQuery):
    """Обработка callback'а скачивания"""
    download_text = [
        "📥 <b>Скачивание видео</b>",
        "",
        "🎬 <b>Поддерживаемые платформы:</b>",
        "• YouTube Shorts",
        "• TikTok",
        "• Instagram Reels",
        "",
        "💡 <b>Как скачать:</b>",
        "1. Скопируйте ссылку на видео",
        "2. Отправьте ее мне в чат",
        "3. Получите файл!",
        "",
        "📦 <b>Batch загрузка:</b>",
        "Отправьте несколько ссылок сразу для группового скачивания"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await callback.message.edit_text(
        "\n".join(download_text),
        reply_markup=keyboard
    )
    await callback.answer()


# === УТИЛИТЫ ===

async def show_main_menu(message, user: User, edit: bool = False):
    """Показать главное меню"""
    from bot.keyboards.inline import create_main_menu_keyboard
    
    # Определяем тип клавиатуры по типу пользователя
    keyboard = create_main_menu_keyboard(
        user.current_user_type, 
        is_admin=bot_config.is_admin(user.telegram_id)
    )
    
    # Приветственное сообщение
    daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
    daily_limit_text = str(daily_limit) if daily_limit < 999 else "∞"
    
    user_type_display = {
        "free": "🆓 Бесплатный",
        "trial": "🔥 Пробный период", 
        "premium": "💎 Premium",
        "admin": "👑 Администратор"
    }.get(user.current_user_type, user.current_user_type)
    
    welcome_text = get_message(
        MessageType.WELCOME,
        "returning_user",
        downloads_today=user.downloads_today,
        daily_limit=daily_limit_text,
        total_downloads=user.downloads_total,
        user_type=user_type_display
    )
    
    if edit:
        await message.edit_text(welcome_text, reply_markup=keyboard)
    else:
        await message.answer(welcome_text, reply_markup=keyboard)


async def format_user_status(user: User) -> str:
    """Форматирование статуса пользователя"""
    
    # Базовая информация
    user_type_display = {
        "free": "🆓 Бесплатный",
        "trial": "🔥 Пробный период",
        "premium": "💎 Premium", 
        "admin": "👑 Администратор"
    }.get(user.current_user_type, user.current_user_type)
    
    # Лимиты
    daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
    file_limit = bot_config.get_user_file_limit(user.current_user_type)
    
    # Построение сообщения
    status_parts = [
        f"👤 <b>{user.display_name}</b>",
        f"🔖 Тип: {user_type_display}",
        "",
        "📊 <b>Статистика:</b>",
        f"• Скачано сегодня: {user.downloads_today}/{daily_limit if daily_limit < 999 else '∞'}",
        f"• Всего скачано: {user.downloads_total}",
        f"• Размер файлов: до {file_limit}MB",
        "",
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y')}",
    ]
    
    # Дополнительная информация по типу аккаунта
    if user.current_user_type == "trial" and user.trial_expires_at:
        from datetime import datetime, timezone
        remaining = user.trial_expires_at - datetime.now(timezone.utc)
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_left = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
            status_parts.append(f"⏰ Пробный период: осталось {time_left}")
    
    elif user.current_user_type == "premium" and user.premium_expires_at:
        status_parts.append(f"💎 Premium до: {user.premium_expires_at.strftime('%d.%m.%Y')}")
    
    # Проверка подписок для free пользователей
    if user.current_user_type == "free" and bot_config.required_subs_enabled:
        if hasattr(user, 'subscription_check_passed') and user.subscription_check_passed:
            status_parts.append("✅ Подписки: проверены")
        else:
            status_parts.append("🔒 Подписки: требуется проверка")
    
    return "\n".join(status_parts)


def create_back_button(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    """Создать кнопку назад"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]
    ])


def create_confirmation_keyboard(confirm_data: str, cancel_data: str = "cancel") -> InlineKeyboardMarkup:
    """Создать клавиатуру подтверждения"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=confirm_data),
            InlineKeyboardButton(text="❌ Нет", callback_data=cancel_data)
        ]
    ])