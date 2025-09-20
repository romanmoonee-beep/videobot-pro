"""
VideoBot Pro - Admin Commands Handler
Обработчик административных команд
"""

import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command

from sqlalchemy import text, select

from shared.config.database import get_async_session, DatabaseHealthCheck
from shared.models import User, DownloadBatch, Payment, RequiredChannel, BroadcastMessage, EventType
from shared.models.analytics import track_user_event
from shared.config.settings import settings
from bot.config import bot_config, is_admin
from bot.utils.user_manager import get_or_create_user
from bot.middlewares.admin_only import admin_only

logger = structlog.get_logger(__name__)

router = Router(name="admin_commands")


class AdminStates(StatesGroup):
    """Состояния FSM для админских операций"""
    waiting_broadcast_text = State()
    waiting_user_search = State()
    waiting_channel_add = State()
    editing_settings = State()


@router.message(Command("admin"))
@admin_only()
async def admin_panel(message: Message):
    """Главная админ панель"""
    user_id = message.from_user.id
    
    try:
        # Получаем базовую статистику
        async with get_async_session() as session:
            # Общие метрики
            total_users_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE is_deleted = false")
            )
            total_users = total_users_result.scalar()
            
            active_users_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE last_active_at > NOW() - INTERVAL '24 hours'")
            )
            active_users = active_users_result.scalar()
            
            premium_users_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE user_type = 'premium'")
            )
            premium_users = premium_users_result.scalar()
            
            # Сегодняшние метрики
            downloads_today_result = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE DATE(created_at) = CURRENT_DATE")
            )
            downloads_today = downloads_today_result.scalar()
            
            revenue_today_result = await session.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE DATE(completed_at) = CURRENT_DATE AND status = 'completed'")
            )
            revenue_today = revenue_today_result.scalar()
        
        admin_text = [
            "👑 Админ панель VideoBot Pro",
            "",
            "📊 Быстрая статистика:",
            f"• Всего пользователей: {total_users}",
            f"• Активных за сутки: {active_users}", 
            f"• Premium пользователей: {premium_users}",
            f"• Скачиваний сегодня: {downloads_today}",
            f"• Выручка сегодня: ${revenue_today:.2f}",
            "",
            f"🤖 Версия бота: {settings.APP_VERSION}",
            f"⚙️ Режим: {settings.ENVIRONMENT}"
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")
            ],
            [
                InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"), 
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
            ],
            [
                InlineKeyboardButton(text="📋 Каналы", callback_data="admin_channels"),
                InlineKeyboardButton(text="💰 Финансы", callback_data="admin_finance")
            ],
            [
                InlineKeyboardButton(text="🔧 Система", callback_data="admin_system"),
                InlineKeyboardButton(text="📝 Логи", callback_data="admin_logs")
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
        ])
        
        await message.answer("\n".join(admin_text), reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in admin panel: {e}", user_id=user_id)
        await message.answer("Ошибка при загрузке админ панели")


@router.message(Command("stats"))
@admin_only()
async def admin_stats_command(message: Message):
    """Команда статистики для админов"""
    await show_detailed_stats(message)


@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: CallbackQuery):
    """Показать детальную статистику"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    await show_detailed_stats(callback.message, edit=True)
    await callback.answer()


async def show_detailed_stats(message: Message, edit: bool = False):
    """Показать детальную статистику системы"""
    try:
        async with get_async_session() as session:
            # Пользователи
            total_users_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE is_deleted = false")
            )
            total_users = total_users_result.scalar()
            
            active_24h_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE last_active_at > NOW() - INTERVAL '24 hours'")
            )
            active_24h = active_24h_result.scalar()
            
            active_7d_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE last_active_at > NOW() - INTERVAL '7 days'")
            )
            active_7d = active_7d_result.scalar()
            
            new_today_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE")
            )
            new_today = new_today_result.scalar()
            
            # Premium и Trial
            premium_active_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE user_type = 'premium' AND premium_expires_at > NOW()")
            )
            premium_active = premium_active_result.scalar()
            
            trial_active_result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE user_type = 'trial' AND trial_expires_at > NOW()")
            )
            trial_active = trial_active_result.scalar()
            
            # Скачивания
            downloads_today_result = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE DATE(created_at) = CURRENT_DATE")
            )
            downloads_today = downloads_today_result.scalar()
            
            downloads_week_result = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE created_at > NOW() - INTERVAL '7 days'")
            )
            downloads_week = downloads_week_result.scalar()
            
            success_rate_result = await session.execute(
                text("""SELECT ROUND(
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0 / COUNT(*), 2
                ) FROM download_tasks WHERE created_at > NOW() - INTERVAL '24 hours'""")
            )
            success_rate = success_rate_result.scalar()
            
            # Платежи
            revenue_today_result = await session.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE DATE(completed_at) = CURRENT_DATE AND status = 'completed'")
            )
            revenue_today = revenue_today_result.scalar()
            
            revenue_week_result = await session.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE completed_at > NOW() - INTERVAL '7 days' AND status = 'completed'")
            )
            revenue_week = revenue_week_result.scalar()
            
            payments_today_result = await session.execute(
                text("SELECT COUNT(*) FROM payments WHERE DATE(created_at) = CURRENT_DATE")
            )
            payments_today = payments_today_result.scalar()
            
            # Система
            db_health = await DatabaseHealthCheck.check_connection()
            
        stats_text = [
            "📊 Детальная статистика системы",
            "",
            "👥 Пользователи:",
            f"• Всего: {total_users:,}",
            f"• Активных за 24ч: {active_24h:,}",
            f"• Активных за неделю: {active_7d:,}",
            f"• Новых сегодня: {new_today:,}",
            f"• Premium: {premium_active:,}",
            f"• Trial активных: {trial_active:,}",
            "",
            "⬇️ Скачивания:",
            f"• Сегодня: {downloads_today:,}",
            f"• За неделю: {downloads_week:,}",
            f"• Успешность: {success_rate or 0}%",
            "",
            "💰 Финансы:",
            f"• Выручка сегодня: ${revenue_today:.2f}",
            f"• Выручка за неделю: ${revenue_week:.2f}",
            f"• Платежей сегодня: {payments_today:,}",
            "",
            "🔧 Система:",
            f"• База данных: {db_health['status']}",
            f"• Время ответа БД: {db_health.get('response_time_ms', 0):.1f}ms"
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Графики", callback_data="admin_charts"),
                InlineKeyboardButton(text="📋 Отчеты", callback_data="admin_reports")
            ],
            [InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")]
        ])
        
        if edit:
            await message.edit_text("\n".join(stats_text), reply_markup=keyboard)
        else:
            await message.answer("\n".join(stats_text), reply_markup=keyboard)
            
    except Exception as e:
        logger.error(f"Error showing admin stats: {e}")
        error_text = "Ошибка при загрузке статистики"
        if edit:
            await message.edit_text(error_text)
        else:
            await message.answer(error_text)


@router.callback_query(F.data == "admin_users")
async def handle_admin_users(callback: CallbackQuery, state: FSMContext):
    """Управление пользователями"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    users_text = [
        "👥 Управление пользователями",
        "",
        "🔍 Поиск пользователя:",
        "• По Telegram ID",
        "• По username",
        "• По имени",
        "",
        "💡 Отправьте ID или @username для поиска"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Топ пользователи", callback_data="admin_top_users"),
            InlineKeyboardButton(text="🆕 Новые", callback_data="admin_new_users")
        ],
        [
            InlineKeyboardButton(text="💎 Premium", callback_data="admin_premium_users"),
            InlineKeyboardButton(text="🚫 Заблокированные", callback_data="admin_banned_users")
        ],
        [InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text("\n".join(users_text), reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_user_search)
    await callback.answer()


@router.message(AdminStates.waiting_user_search)
@admin_only()
async def handle_user_search(message: Message, state: FSMContext):
    """Обработка поиска пользователя"""
    search_query = message.text.strip()
    
    try:
        async with get_async_session() as session:
            user = None
            
            # Поиск по Telegram ID
            if search_query.isdigit():
                telegram_id = int(search_query)
                result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = result.scalar_one_or_none()
            
            # Поиск по username
            elif search_query.startswith("@"):
                username = search_query[1:]
                result = await session.execute(
                    select(User).where(User.username == username)
                )
                user = result.scalar_one_or_none()
            
            # Поиск по имени
            else:
                result = await session.execute(
                    select(User).where(User.first_name.ilike(f"%{search_query}%"))
                )
                user = result.scalar_one_or_none()
            
            if not user:
                await message.answer(f"Пользователь '{search_query}' не найден")
                return
            
            await show_user_details(message, user)
            await state.clear()
    
    except Exception as e:
        logger.error(f"Error in user search: {e}")
        await message.answer("Ошибка при поиске пользователя")
        await state.clear()


async def show_user_details(message: Message, user: User):
    """Показать детали пользователя"""
    # Получаем дополнительную статистику
    async with get_async_session() as session:
        downloads_count_result = await session.execute(
            text("SELECT COUNT(*) FROM download_tasks WHERE user_id = :user_id"),
            {"user_id": user.id}
        )
        downloads_count = downloads_count_result.scalar()
        
        payments_sum_result = await session.execute(
            text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE user_id = :user_id AND status = 'completed'"),
            {"user_id": user.id}
        )
        payments_sum = payments_sum_result.scalar()
    
    status_emoji = {
        "free": "🆓",
        "trial": "🔥", 
        "premium": "💎",
        "admin": "👑"
    }.get(user.current_user_type, "❓")
    
    user_text = [
        f"👤 {user.display_name}",
        "",
        f"🆔 ID: {user.telegram_id}",
        f"👤 Username: @{user.username or 'не указан'}",
        f"🔖 Тип: {status_emoji} {user.current_user_type}",
        f"📅 Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}",
        f"⏰ Последняя активность: {user.last_active_at.strftime('%d.%m.%Y %H:%M') if user.last_active_at else 'никогда'}",
        "",
        "📊 Статистика:",
        f"• Скачиваний всего: {downloads_count:,}",
        f"• Скачиваний сегодня: {user.downloads_today}",
        f"• Общая выручка: ${payments_sum:.2f}",
        f"• Рефералов: {getattr(user, 'referrals_count', 0)}",
        "",
        f"🚫 Статус: {'Заблокирован' if user.is_banned else 'Активен'}",
        f"🎁 Trial: {'Использован' if user.trial_used else 'Доступен'}"
    ]
    
    if user.is_premium_active:
        user_text.append(f"💎 Premium до: {user.premium_expires_at.strftime('%d.%m.%Y')}")
    
    if user.is_trial_active:
        remaining = user.trial_expires_at - datetime.utcnow()
        hours = int(remaining.total_seconds() // 3600)
        user_text.append(f"🔥 Trial: осталось {hours}ч")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💎 Выдать Premium", callback_data=f"admin_grant_premium_{user.id}"),
            InlineKeyboardButton(text="🎁 Активировать Trial", callback_data=f"admin_grant_trial_{user.id}")
        ],
        [
            InlineKeyboardButton(text="🚫 Заблокировать" if not user.is_banned else "✅ Разблокировать", 
                               callback_data=f"admin_ban_{user.id}" if not user.is_banned else f"admin_unban_{user.id}"),
            InlineKeyboardButton(text="📧 Сообщение", callback_data=f"admin_message_{user.id}")
        ],
        [
            InlineKeyboardButton(text="📊 Детальная статистика", callback_data=f"admin_user_stats_{user.id}"),
            InlineKeyboardButton(text="💰 История платежей", callback_data=f"admin_user_payments_{user.id}")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_users")]
    ])
    
    await message.answer("\n".join(user_text), reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin_grant_premium_"))
async def handle_grant_premium(callback: CallbackQuery):
    """Выдача Premium пользователю"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            # Выдаем Premium на 30 дней
            user.activate_premium(duration_days=30)
            await session.commit()
            
            # Уведомляем пользователя
            try:
                await callback.bot.send_message(
                    user.telegram_id,
                    "🎉 Вам выдан Premium доступ на 30 дней!\n\n"
                    "💎 Все Premium возможности теперь доступны."
                )
            except Exception:
                pass
            
            await callback.answer("Premium выдан на 30 дней", show_alert=True)
            await show_user_details(callback.message, user)
            
            logger.info(
                f"Premium granted by admin",
                admin_id=callback.from_user.id,
                target_user_id=user.telegram_id,
                duration_days=30
            )
    
    except Exception as e:
        logger.error(f"Error granting premium: {e}")
        await callback.answer("Ошибка при выдаче Premium", show_alert=True)


@router.callback_query(F.data.startswith("admin_ban_"))
async def handle_ban_user(callback: CallbackQuery):
    """Блокировка пользователя"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    try:
        async with get_async_session() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            user.ban_user("Заблокирован администратором")
            await session.commit()
            
            await callback.answer("Пользователь заблокирован", show_alert=True)
            await show_user_details(callback.message, user)
            
            logger.info(
                f"User banned by admin",
                admin_id=callback.from_user.id,
                target_user_id=user.telegram_id
            )
    
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await callback.answer("Ошибка при блокировке", show_alert=True)


@router.callback_query(F.data == "admin_panel")
async def handle_admin_panel_callback(callback: CallbackQuery):
    """Callback версия админ панели"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return

    mock_message = type('MockMessage', (), {
        'from_user': callback.from_user,
        'answer': callback.message.edit_text
    })()

    try:
        await admin_panel(mock_message)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in admin panel callback: {e}")
        await callback.answer("Ошибка в админ панели", show_alert=True)