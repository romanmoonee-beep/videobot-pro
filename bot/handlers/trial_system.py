"""
VideoBot Pro - Trial System Handler
Обработчик системы пробного периода
"""

import structlog
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from shared.config.database import get_async_session
from shared.models import User, EventType
from shared.models.analytics import track_user_event
from shared.config.settings import settings
from bot.config import bot_config, get_message, MessageType
from bot.utils.user_manager import get_or_create_user, update_user_activity

logger = structlog.get_logger(__name__)

router = Router(name="trial_system")


class TrialStates(StatesGroup):
    """Состояния FSM для пробного периода"""
    confirming_activation = State()
    trial_active = State()


@router.message(F.text.in_(["/trial", "🎁 Пробный период", "trial"]))
async def trial_command(message: Message, state: FSMContext):
    """Команда пробного периода"""
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
        
        # Проверяем доступность пробного периода
        await handle_trial_request(message, user, state)
        
    except Exception as e:
        logger.error(f"Error in trial command: {e}", user_id=user_id)
        await message.answer("Ошибка при обработке запроса пробного периода")


async def handle_trial_request(message: Message, user: User, state: FSMContext):
    """Обработка запроса пробного периода"""
    
    # Проверяем включен ли пробный период
    if not bot_config.trial_enabled:
        await show_trial_disabled(message)
        return
    
    # Проверяем текущий статус пользователя
    if user.current_user_type == "admin":
        await show_admin_trial_info(message)
        return
    
    if user.current_user_type == "premium":
        await show_premium_trial_info(message, user)
        return
    
    if user.is_trial_active:
        await show_active_trial_status(message, user)
        return
    
    if user.trial_used:
        await show_trial_already_used(message, user)
        return
    
    # Показываем предложение активации
    await show_trial_activation_offer(message, user, state)


async def show_trial_disabled(message: Message):
    """Сообщение о том, что пробный период отключен"""
    disabled_text = [
        "⏰ Пробный период временно недоступен",
        "",
        "💡 Альтернативные варианты:",
        "• Оформите Premium подписку",
        "• Пользуйтесь бесплатным планом",
        "• Следите за новостями о специальных акциях"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Premium", callback_data="premium_info")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await message.answer("\n".join(disabled_text), reply_markup=keyboard)


async def show_admin_trial_info(message: Message):
    """Информация о пробном периоде для админа"""
    admin_text = [
        "👑 Административная информация о пробном периоде",
        "",
        f"⚙️ Статус: {'Включен' if bot_config.trial_enabled else 'Отключен'}",
        f"⏰ Длительность: {settings.TRIAL_DURATION_MINUTES} минут",
        "",
        "🎯 Возможности пробного периода:",
        "• Безлимитные скачивания",
        "• Все поддерживаемые платформы",
        "• HD качество (до 1080p)",
        "• Без обязательных подписок",
        "• Файлы до 500MB",
        "",
        "👑 Как админ, у вас уже есть все эти возможности"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Настройки пробного периода", callback_data="admin_trial_settings")],
        [InlineKeyboardButton(text="📊 Статистика пробных периодов", callback_data="admin_trial_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await message.answer("\n".join(admin_text), reply_markup=keyboard)


async def show_premium_trial_info(message: Message, user: User):
    """Информация о пробном периоде для Premium пользователя"""
    days_left = (user.premium_expires_at - datetime.utcnow()).days if user.premium_expires_at else 0
    
    premium_text = [
        "💎 У вас уже активен Premium!",
        "",
        f"⏰ Premium действует до: {user.premium_expires_at.strftime('%d.%m.%Y')}",
        f"📅 Осталось дней: {days_left}",
        "",
        "🎁 Ваши текущие возможности превышают пробный период:",
        "• ∞ Безлимитные скачивания",
        "• 🎬 4K качество видео",
        "• 📦 Файлы до 500MB",
        "• ☁️ Хранение файлов 30 дней",
        "• 🚀 Приоритетная обработка",
        "",
        "💡 Пробный период предназначен для новых пользователей"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статус Premium", callback_data="premium_status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await message.answer("\n".join(premium_text), reply_markup=keyboard)


async def show_active_trial_status(message: Message, user: User):
    """Показать статус активного пробного периода"""
    
    # Рассчитываем оставшееся время
    if user.trial_expires_at:
        remaining = user.trial_expires_at - datetime.utcnow()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_left = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
        else:
            time_left = "истек"
    else:
        time_left = "неизвестно"
    
    status_text = [
        "🔥 Пробный период активен!",
        "",
        f"⏰ Осталось времени: {time_left}",
        f"📊 Скачано сегодня: {user.downloads_today}",
        "",
        "🎁 Активные возможности:",
        "• ∞ Безлимитные скачивания",
        "• 🎬 HD качество (до 1080p)",
        "• 📦 Файлы до 500MB",
        "• 🚀 Быстрая обработка",
        "• 🔓 Без обязательных подписок",
        "",
        "💡 После окончания перейдете на бесплатный план"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="upgrade_to_premium")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="trial_stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await message.answer("\n".join(status_text), reply_markup=keyboard)


async def show_trial_already_used(message: Message, user: User):
    """Сообщение о том, что пробный период уже использован"""
    used_text = [
        "⏰ Пробный период уже использован",
        "",
        f"📅 Использован: {user.trial_started_at.strftime('%d.%m.%Y %H:%M') if user.trial_started_at else 'Дата неизвестна'}",
        "",
        "💡 Пробный период можно использовать только один раз",
        "",
        "🎯 Доступные варианты:",
        "• 💎 Premium подписка - все возможности",
        "• 🆓 Бесплатный план - 10 загрузок в день",
        "• 🎁 Следите за специальными акциями"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium")],
        [InlineKeyboardButton(text="📊 Мой статус", callback_data="status")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await message.answer("\n".join(used_text), reply_markup=keyboard)


async def show_trial_activation_offer(message: Message, user: User, state: FSMContext):
    """Предложение активации пробного периода"""
    
    offer_text = [
        "🎁 Активировать пробный период?",
        "",
        f"⏰ Длительность: {settings.TRIAL_DURATION_MINUTES} минут",
        "",
        "🚀 Что вы получите:",
        "• ∞ Безлимитные скачивания",
        "• 🎬 HD качество (до 1080p)",
        "• 📦 Файлы до 500MB",
        "• 🚀 Приоритетная обработка",
        "• 🔓 Без обязательных подписок",
        "• 📱 Все поддерживаемые платформы",
        "",
        "⚡ После активации сразу можете скачивать!",
        "",
        "💡 Пробный период можно использовать только один раз"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Активировать пробный период", callback_data="activate_trial")],
        [InlineKeyboardButton(text="ℹ️ Подробнее о Premium", callback_data="premium_vs_trial")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")]
    ])
    
    await message.answer("\n".join(offer_text), reply_markup=keyboard)
    await state.set_state(TrialStates.confirming_activation)


@router.callback_query(F.data == "activate_trial")
async def handle_trial_activation(callback: CallbackQuery, state: FSMContext):
    """Обработка активации пробного периода"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            # Проверяем можно ли активировать
            if user.trial_used:
                await callback.answer("Пробный период уже использован", show_alert=True)
                return
            
            if user.is_trial_active:
                await callback.answer("Пробный период уже активен", show_alert=True)
                return
            
            if user.current_user_type in ["premium", "admin"]:
                await callback.answer("У вас уже есть все возможности", show_alert=True)
                return
            
            # Активируем пробный период
            user.start_trial(duration_minutes=settings.TRIAL_DURATION_MINUTES)
            
            await session.commit()
            
            # Аналитика
            await track_user_event(
                event_type=EventType.USER_TRIAL_STARTED,
                user_id=user.id,
                telegram_user_id=user.telegram_id,
                user_type="trial",
                event_data={
                    "duration_minutes": settings.TRIAL_DURATION_MINUTES,
                    "trial_expires_at": user.trial_expires_at.isoformat()
                }
            )
        
        # Сообщение об успешной активации
        success_text = [
            "🎉 Пробный период активирован!",
            "",
            f"⏰ Действует: {settings.TRIAL_DURATION_MINUTES} минут",
            f"📅 До: {user.trial_expires_at.strftime('%d.%m.%Y %H:%M')}",
            "",
            "🚀 Теперь доступно:",
            "• ∞ Безлимитные скачивания",
            "• 🎬 HD качество (до 1080p)",
            "• 📦 Файлы до 500MB",
            "• 🔓 Без обязательных подписок",
            "",
            "💡 Отправьте ссылку на видео для скачивания!"
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика пробного периода", callback_data="trial_stats")],
            [InlineKeyboardButton(text="💎 Купить Premium", callback_data="upgrade_to_premium")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_main")]
        ])
        
        await callback.message.edit_text(
            "\n".join(success_text),
            reply_markup=keyboard
        )
        
        await state.set_state(TrialStates.trial_active)
        await callback.answer("Пробный период активирован!", show_alert=False)
        
        logger.info(
            f"Trial activated",
            user_id=user_id,
            duration_minutes=settings.TRIAL_DURATION_MINUTES,
            expires_at=user.trial_expires_at.isoformat()
        )
    
    except Exception as e:
        logger.error(f"Error activating trial: {e}", user_id=user_id)
        await callback.answer("Ошибка при активации пробного периода", show_alert=True)


@router.callback_query(F.data == "trial_stats")
async def show_trial_statistics(callback: CallbackQuery):
    """Показать статистику пробного периода"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            if not user.is_trial_active and not user.trial_used:
                await callback.answer("Пробный период не был активирован", show_alert=True)
                return
            
            # Рассчитываем статистику
            stats = user.stats or {}
            
            if user.is_trial_active:
                # Активный пробный период
                remaining = user.trial_expires_at - datetime.utcnow()
                elapsed = datetime.utcnow() - user.trial_started_at
                
                hours_remaining = int(remaining.total_seconds() // 3600)
                minutes_remaining = int((remaining.total_seconds() % 3600) // 60)
                
                hours_used = int(elapsed.total_seconds() // 3600)
                minutes_used = int((elapsed.total_seconds() % 3600) // 60)
                
                stats_text = [
                    "📊 Статистика пробного периода",
                    "",
                    "⏰ Время:",
                    f"• Осталось: {hours_remaining}ч {minutes_remaining}м",
                    f"• Использовано: {hours_used}ч {minutes_used}м",
                    f"• Активирован: {user.trial_started_at.strftime('%d.%m.%Y %H:%M')}",
                    "",
                    "📈 Использование:",
                    f"• Скачано файлов: {user.downloads_today}",
                    f"• Размер файлов: {stats.get('trial_size_mb', 0):.1f} MB"
                ]
            else:
                # Завершенный пробный период
                duration = user.trial_expires_at - user.trial_started_at if user.trial_expires_at and user.trial_started_at else timedelta(0)
                
                stats_text = [
                    "📊 Статистика пробного периода",
                    "",
                    "✅ Пробный период завершен",
                    "",
                    "⏰ Время:",
                    f"• Длительность: {int(duration.total_seconds() // 60)} минут",
                    f"• Активирован: {user.trial_started_at.strftime('%d.%m.%Y %H:%M')}",
                    f"• Завершен: {user.trial_expires_at.strftime('%d.%m.%Y %H:%M')}",
                    "",
                    "📈 Использование:",
                    f"• Скачано файлов: {stats.get('trial_downloads', 0)}",
                    f"• Размер файлов: {stats.get('trial_size_mb', 0):.1f} MB"
                ]
            
            # Добавляем статистику по платформам
            if stats.get('platforms'):
                stats_text.append("")
                stats_text.append("🎯 По платформам:")
                for platform, count in stats['platforms'].items():
                    emoji = {"youtube": "🔴", "tiktok": "🎵", "instagram": "📸"}.get(platform, "🎬")
                    stats_text.append(f"• {emoji} {platform.title()}: {count}")
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить Premium", callback_data="upgrade_to_premium")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_trial")]
        ])
        
        await callback.message.edit_text(
            "\n".join(stats_text),
            reply_markup=keyboard
        )
    
    except Exception as e:
        logger.error(f"Error showing trial stats: {e}", user_id=user_id)
        await callback.answer("Ошибка получения статистики", show_alert=True)


@router.callback_query(F.data == "premium_vs_trial")
async def show_premium_vs_trial(callback: CallbackQuery):
    """Сравнение Premium и пробного периода"""
    
    comparison_text = [
        "💎 Premium vs 🎁 Пробный период",
        "",
        "🎁 <b>Пробный период (60 минут):</b>",
        "• ✅ Безлимитные скачивания",
        "• ✅ HD качество (до 1080p)",
        "• ✅ Файлы до 500MB",
        "• ✅ Без обязательных подписок",
        "• ⏰ Только 60 минут",
        "• ❌ Один раз в жизни",
        "",
        "💎 <b>Premium подписка:</b>",
        "• ✅ Безлимитные скачивания",
        "• ✅ 4K качество (до 2160p)",
        "• ✅ Файлы до 500MB",
        "• ✅ Хранение файлов 30 дней",
        "• ✅ Приоритетная обработка",
        "• ✅ Расширенная статистика",
        "• ⏰ От 30 дней до года",
        "• 💰 От $3.99/месяц"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Активировать пробный период", callback_data="activate_trial")],
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await callback.message.edit_text(
        "\n".join(comparison_text),
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "upgrade_to_premium")
async def handle_upgrade_to_premium(callback: CallbackQuery, state: FSMContext):
    """Обработка перехода на Premium"""
    await callback.answer("Переходим к выбору Premium плана...")
    
    # Очищаем состояние trial
    await state.clear()
    
    # Перенаправляем на Premium
    from bot.handlers.premium import show_premium_plans
    
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


# Утилиты для работы с пробным периодом

async def check_trial_expiry():
    """Проверка истекших пробных периодов (запускается периодически)"""
    try:
        async with get_async_session() as session:
            expired_trials = await session.query(User).filter(
                User.trial_expires_at < datetime.utcnow(),
                User.user_type == "trial"
            ).all()
            
            for user in expired_trials:
                # Переводим в бесплатный тип
                user.user_type = "free"
                
                # Уведомляем пользователя
                try:
                    from aiogram import Bot
                    bot = Bot.get_current()
                    await bot.send_message(
                        user.telegram_id,
                        "⏰ Пробный период завершен!\n\n"
                        "Теперь доступен бесплатный план:\n"
                        "• 10 скачиваний в день\n"
                        "• HD качество (720p)\n"
                        "• Обязательные подписки на каналы\n\n"
                        "💎 Купить Premium: /premium"
                    )
                    
                    # Аналитика
                    await track_user_event(
                        event_type=EventType.USER_PREMIUM_EXPIRED,  # Используем как trial expired
                        user_id=user.id,
                        telegram_user_id=user.telegram_id,
                        user_type="free"
                    )
                    
                except Exception:
                    pass  # Пользователь заблокировал бота
            
            await session.commit()
            
            if expired_trials:
                logger.info(f"Expired {len(expired_trials)} trial periods")
    
    except Exception as e:
        logger.error(f"Error checking trial expiry: {e}")


def get_trial_time_remaining(user: User) -> Optional[timedelta]:
    """Получить оставшееся время пробного периода"""
    if not user.is_trial_active or not user.trial_expires_at:
        return None
    
    remaining = user.trial_expires_at - datetime.utcnow()
    return remaining if remaining.total_seconds() > 0 else timedelta(0)


def format_trial_time(time_delta: timedelta) -> str:
    """Отформатировать оставшееся время пробного периода"""
    if time_delta.total_seconds() <= 0:
        return "истек"
    
    hours = int(time_delta.total_seconds() // 3600)
    minutes = int((time_delta.total_seconds() % 3600) // 60)
    
    if hours > 0:
        return f"{hours}ч {minutes}м"
    else:
        return f"{minutes}м"