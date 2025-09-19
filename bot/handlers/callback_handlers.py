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
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            status_text = bot_config.format_user_status(user)
            
            # Детальная статистика
            daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
            file_limit = bot_config.get_user_file_limit(user.current_user_type)
            
            detailed_status = [
                f"👤 {user.display_name}",
                f"📊 {status_text}",
                "",
                "📈 Подробная информация:",
                f"• Скачано сегодня: {user.downloads_today}/{daily_limit if daily_limit < 999 else '∞'}",
                f"• Всего скачано: {user.downloads_total}",
                f"• Лимит файла: {file_limit}MB",
                f"• Регистрация: {user.created_at.strftime('%d.%m.%Y')}",
            ]
            
            if user.is_premium_active:
                detailed_status.append(f"💎 Premium до: {user.premium_expires_at.strftime('%d.%m.%Y')}")
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Детальная статистика", callback_data="detailed_stats")],
                [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
            ])
            
            await callback.message.edit_text(
                "\n".join(detailed_status),
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


@router.callback_query(F.data == "buy_premium")
async def handle_buy_premium(callback: CallbackQuery):
    """Перенаправление к покупке Premium"""
    await callback.answer("Переходим к оформлению Premium...")
    
    # Перенаправляем на premium handler
    from bot.handlers.premium import show_premium_plans
    from aiogram.fsm.context import FSMContext
    
    # Создаем новый контекст состояния
    state = FSMContext.get_current()
    
    user_id = callback.from_user.id
    async with get_async_session() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=user_id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name
        )
        await session.commit()
    
    await show_premium_plans(callback.message, user, state)


@router.callback_query(F.data == "trial")
async def handle_trial_callback(callback: CallbackQuery):
    """Перенаправление к пробному периоду"""
    await callback.answer("Переходим к активации пробного периода...")
    
    # Перенаправляем на trial handler
    from bot.handlers.trial_system import handle_trial_request
    from aiogram.fsm.context import FSMContext
    
    state = FSMContext.get_current()
    
    user_id = callback.from_user.id
    async with get_async_session() as session:
        user = await get_or_create_user(
            session=session,
            telegram_id=user_id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name
        )
        await session.commit()
    
    await handle_trial_request(callback.message, user, state)


@router.callback_query(F.data == "detailed_stats")
async def handle_detailed_stats(callback: CallbackQuery):
    """Показать детальную статистику"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
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
    # TODO: Реализовать экспорт данных в JSON/CSV


async def show_main_menu(message, user: User, edit: bool = False):
    """Показать главное меню"""
    # Определяем тип клавиатуры по типу пользователя
    if bot_config.is_admin(user.telegram_id):
        keyboard_config = bot_config.keyboards["main_menu"]["admin"]
    elif user.is_premium_active:
        keyboard_config = bot_config.keyboards["main_menu"]["premium"]
    else:
        keyboard_config = bot_config.keyboards["main_menu"]["free"]
    
    # Создаем клавиатуру
    keyboard_rows = []
    for row in keyboard_config:
        button_row = []
        for button in row:
            button_row.append(
                InlineKeyboardButton(
                    text=button["text"], 
                    callback_data=button["callback"]
                )
            )
        keyboard_rows.append(button_row)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    # Приветственное сообщение
    welcome_text = get_message(
        MessageType.WELCOME,
        "returning_user",
        downloads_today=user.downloads_today,
        daily_limit=bot_config.get_user_daily_limit(user.current_user_type),
        total_downloads=user.downloads_total,
        user_type=bot_config.format_user_status(user)
    )
    
    if edit:
        await message.edit_text(welcome_text, reply_markup=keyboard)
    else:
        await message.answer(welcome_text, reply_markup=keyboard)


# Утилиты для работы с callback

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


@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    """Универсальная отмена действия"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено.\n\n"
        "💡 Используйте команды для работы с ботом."
    )
    await callback.answer("Отменено")