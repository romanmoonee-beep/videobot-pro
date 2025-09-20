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

from sqlalchemy import text

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
            total_users = await session.execute(text("SELECT COUNT(*) FROM users WHERE is_deleted = false"))
            active_users = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE last_active_at > NOW() - INTERVAL '24 hours'")
            )
            premium_users = await session.execute(text("SELECT COUNT(*) FROM users WHERE is_premium = true"))
            
            # Сегодняшние метрики
            downloads_today = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE DATE(created_at) = CURRENT_DATE")
            )
            revenue_today = await session.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE DATE(completed_at) = CURRENT_DATE AND status = 'completed'")
            )
        
        admin_text = [
            "👑 Админ панель VideoBot Pro",
            "",
            "📊 Быстрая статистика:",
            f"• Всего пользователей: {total_users.scalar()}",
            f"• Активных за сутки: {active_users.scalar()}", 
            f"• Premium пользователей: {premium_users.scalar()}",
            f"• Скачиваний сегодня: {downloads_today.scalar()}",
            f"• Выручка сегодня: ${revenue_today.scalar():.2f}",
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
            total_users = await session.execute(text("SELECT COUNT(*) FROM users WHERE is_deleted = false"))
            active_24h = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE last_active_at > NOW() - INTERVAL '24 hours'")
            )
            active_7d = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE last_active_at > NOW() - INTERVAL '7 days'")
            )
            new_today = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE")
            )
            
            # Premium и Trial
            premium_active = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE is_premium = true AND premium_expires_at > NOW()")
            )
            trial_active = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE user_type = 'trial' AND trial_expires_at > NOW()")
            )
            
            # Скачивания
            downloads_today = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE DATE(created_at) = CURRENT_DATE")
            )
            downloads_week = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE created_at > NOW() - INTERVAL '7 days'")
            )
            success_rate = await session.execute(
                text("""SELECT ROUND(
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) * 100.0 / COUNT(*), 2
                ) FROM download_tasks WHERE created_at > NOW() - INTERVAL '24 hours'""")
            )
            
            # Платежи
            revenue_today = await session.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE DATE(completed_at) = CURRENT_DATE AND status = 'completed'")
            )
            revenue_week = await session.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE completed_at > NOW() - INTERVAL '7 days' AND status = 'completed'")
            )
            payments_today = await session.execute(
                text("SELECT COUNT(*) FROM payments WHERE DATE(created_at) = CURRENT_DATE")
            )
            
            # Система
            db_health = await DatabaseHealthCheck.check_connection()
            
        stats_text = [
            "📊 Детальная статистика системы",
            "",
            "👥 Пользователи:",
            f"• Всего: {total_users.scalar():,}",
            f"• Активных за 24ч: {active_24h.scalar():,}",
            f"• Активных за неделю: {active_7d.scalar():,}",
            f"• Новых сегодня: {new_today.scalar():,}",
            f"• Premium: {premium_active.scalar():,}",
            f"• Trial активных: {trial_active.scalar():,}",
            "",
            "⬇️ Скачивания:",
            f"• Сегодня: {downloads_today.scalar():,}",
            f"• За неделю: {downloads_week.scalar():,}",
            f"• Успешность: {success_rate.scalar() or 0}%",
            "",
            "💰 Финансы:",
            f"• Выручка сегодня: ${revenue_today.scalar():.2f}",
            f"• Выручка за неделю: ${revenue_week.scalar():.2f}",
            f"• Платежей сегодня: {payments_today.scalar():,}",
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
                user = await session.query(User).filter(User.telegram_id == telegram_id).first()
            
            # Поиск по username
            elif search_query.startswith("@"):
                username = search_query[1:]
                result = await session.execute(
                    text("SELECT * FROM users WHERE username = :username"),
                    {'username': username}
                )
                user = result.first()
            
            # Поиск по имени
            else:
                user = await session.query(User).filter(
                    User.first_name.ilike(f"%{search_query}%")
                ).first()
            
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
        downloads_count = (await session.execute)(
            text("SELECT COUNT(*) FROM download_tasks WHERE user_id = :user_id"),
            {"user_id": user.id}
        )
        payments_sum = await session.execute(
            text("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE user_id = :user_id AND status = 'completed'"),
            {"user_id": user.id}
        )
    
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
        f"• Скачиваний всего: {downloads_count.scalar():,}",
        f"• Скачиваний сегодня: {user.downloads_today}",
        f"• Общая выручка: ${payments_sum.scalar():.2f}",
        f"• Рефералов: {user.referrals_count}",
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
            user = await session.get(User, user_id)
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
            user = await session.get(User, user_id)
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


@router.callback_query(F.data == "admin_broadcast")
async def handle_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Создание рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    broadcast_text = [
        "📢 Создание рассылки",
        "",
        "💡 Отправьте текст сообщения для рассылки",
        "",
        "⚙️ Поддерживаемые форматы:",
        "• HTML разметка",
        "• Эмодзи",
        "• Ссылки",
        "",
        "🎯 После отправки текста выберете аудиторию"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text("\n".join(broadcast_text), reply_markup=keyboard)
    await state.set_state(AdminStates.waiting_broadcast_text)
    await callback.answer()


@router.message(AdminStates.waiting_broadcast_text)
@admin_only()
async def handle_broadcast_text(message: Message, state: FSMContext):
    """Обработка текста рассылки"""
    text = message.text or message.caption
    
    if not text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение")
        return
    
    # Показываем превью и выбор аудитории
    preview_text = [
        "📢 Превью рассылки:",
        "",
        "─────────────────",
        text,
        "─────────────────",
        "",
        "🎯 Выберите аудиторию:"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Всем пользователям", callback_data="broadcast_all"),
            InlineKeyboardButton(text="🆓 Только Free", callback_data="broadcast_free")
        ],
        [
            InlineKeyboardButton(text="💎 Только Premium", callback_data="broadcast_premium"),
            InlineKeyboardButton(text="🔥 Только Trial", callback_data="broadcast_trial")
        ],
        [
            InlineKeyboardButton(text="📊 Активным за 7 дней", callback_data="broadcast_active"),
            InlineKeyboardButton(text="🆕 Новым за 3 дня", callback_data="broadcast_new")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]
    ])
    
    await message.answer("\n".join(preview_text), reply_markup=keyboard)
    await state.update_data(broadcast_text=text)


@router.callback_query(F.data.startswith("broadcast_"))
async def handle_broadcast_send(callback: CallbackQuery, state: FSMContext):
    """Отправка рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    target_audience = callback.data.replace("broadcast_", "")
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")
    
    if not broadcast_text:
        await callback.answer("Текст рассылки не найден", show_alert=True)
        return
    
    try:
        # Создаем рассылку в базе данных
        async with get_async_session() as session:
            # Получаем админа
            admin = await get_or_create_user(
                session=session,
                telegram_id=callback.from_user.id,
                username=callback.from_user.username,
                first_name=callback.from_user.first_name
            )
            
            # Определяем тип аудитории
            target_mapping = {
                "all": "all_users",
                "free": "free_users", 
                "premium": "premium_users",
                "trial": "trial_users",
                "active": "custom",
                "new": "custom"
            }
            
            target_type = target_mapping.get(target_audience, "all_users")
            
            # Создаем рассылку
            broadcast = BroadcastMessage.create_broadcast(
                title=f"Админ рассылка {datetime.now().strftime('%d.%m %H:%M')}",
                message_text=broadcast_text,
                target_type=target_type,
                created_by_admin_id=admin.id
            )
            
            # Настройки фильтров для кастомной аудитории
            if target_audience == "active":
                broadcast.target_filters = {
                    "last_active_days": 7
                }
            elif target_audience == "new":
                broadcast.target_filters = {
                    "registration_days": 3
                }
            
            session.add(broadcast)
            await session.commit()
            
            # Запускаем рассылку
            from worker.tasks.notification_tasks import send_broadcast_message
            task = send_broadcast_message.delay(broadcast.id)
            
            await callback.message.edit_text(
                f"✅ Рассылка запущена!\n\n"
                f"📋 ID: {broadcast.id}\n"
                f"🎯 Аудитория: {target_audience}\n"
                f"⚡ Task ID: {task.id}\n\n"
                f"📊 Прогресс можно отслеживать в админ панели"
            )
            
            logger.info(
                f"Broadcast started by admin",
                admin_id=callback.from_user.id,
                broadcast_id=broadcast.id,
                target_audience=target_audience,
                task_id=task.id
            )
    
    except Exception as e:
        logger.error(f"Error starting broadcast: {e}")
        await callback.answer("Ошибка при запуске рассылки", show_alert=True)
    
    await state.clear()
    await callback.answer("Рассылка запущена!")


@router.callback_query(F.data == "admin_system")
async def handle_admin_system(callback: CallbackQuery):
    """Системная информация"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    try:
        # Проверяем статус компонентов
        db_health = await DatabaseHealthCheck.check_connection()
        
        system_text = [
            "🔧 Системная информация",
            "",
            f"🤖 Версия: {settings.APP_VERSION}",
            f"🌍 Окружение: {settings.ENVIRONMENT}",
            f"🔧 Debug: {'Включен' if settings.DEBUG else 'Отключен'}",
            "",
            "💾 База данных:",
            f"• Статус: {db_health['status']}",
            f"• Время ответа: {db_health.get('response_time_ms', 0):.1f}ms",
            f"• Активных подключений: {db_health.get('active_connections', 0)}",
            "",
            "⚙️ Настройки:",
            f"• Trial: {'Включен' if settings.TRIAL_ENABLED else 'Отключен'}",
            f"• Подписки: {'Включены' if settings.REQUIRED_SUBS_ENABLED else 'Отключены'}",
            f"• Premium: {'Включен' if settings.PREMIUM_SYSTEM_ENABLED else 'Отключен'}",
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Перезагрузить", callback_data="admin_restart"),
                InlineKeyboardButton(text="🧹 Очистить кэш", callback_data="admin_clear_cache")
            ],
            [
                InlineKeyboardButton(text="📊 Health Check", callback_data="admin_health"),
                InlineKeyboardButton(text="⚡ Тест производительности", callback_data="admin_performance")
            ],
            [InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")]
        ])
        
        await callback.message.edit_text("\n".join(system_text), reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error showing system info: {e}")
        await callback.answer("Ошибка получения системной информации", show_alert=True)
    
    await callback.answer()


@router.message(Command("maintenance"))
@admin_only()
async def maintenance_mode(message: Message):
    """Режим обслуживания"""
    # Реализация переключения режима обслуживания
    maintenance_text = [
        "🔧 Режим обслуживания",
        "",
        "⚠️ В режиме обслуживания:",
        "• Новые пользователи не могут использовать бота",
        "• Скачивания приостанавливаются", 
        "• Показываются уведомления о техработах",
        "",
        "💡 Текущий статус: Активен" # TODO: Реальный статус из настроек
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔧 Включить обслуживание", callback_data="maintenance_on")],
        [InlineKeyboardButton(text="✅ Отключить обслуживание", callback_data="maintenance_off")]
    ])
    
    await message.answer("\n".join(maintenance_text), reply_markup=keyboard)