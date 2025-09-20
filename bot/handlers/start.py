"""
VideoBot Pro - Start Command Handler
Обработчик команды /start и первый контакт с пользователем
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from shared.config.database import get_async_session
from shared.models import User, RequiredChannel, EventType
from shared.models.analytics import track_user_event
from bot.config import bot_config, get_message, MessageType, settings
from bot.utils.user_manager import get_or_create_user, update_user_activity
from bot.utils.subscription_checker import check_required_subscriptions
from bot.keyboards.inline import create_main_menu_keyboard, create_trial_keyboard
from bot.middlewares.rate_limit import rate_limit

logger = structlog.get_logger(__name__)

router = Router(name="start_handler")


@router.message(CommandStart())
@rate_limit(requests_per_minute=5)  # Ограничение на команду start
async def start_command(message: Message, state: FSMContext):
    """
    Обработчик команды /start
    Главная точка входа для пользователей
    """
    user_id = message.from_user.id
    
    try:
        # Очищаем состояние FSM
        await state.clear()
        
        # Получаем или создаем пользователя
        async with get_async_session() as session:
            user = await get_or_create_user(
                session,
                telegram_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                language_code=message.from_user.language_code
            )
            
            is_new_user = user.session_count == 0
            
            # Обновляем активность
            await update_user_activity(session, user, message.message_id)
            await session.commit()
            
            # Аналитика
            event_type = EventType.USER_REGISTERED if is_new_user else EventType.USER_ACTIVATED
            await track_user_event(
                event_type=event_type,
                user_id=user.id,
                telegram_user_id=user_id,
                user_type=user.current_user_type,
                source="bot"
            )
            
            logger.info(
                f"Start command processed",
                user_id=user_id,
                username=message.from_user.username,
                is_new_user=is_new_user,
                user_type=user.current_user_type
            )
    
    except Exception as e:
        logger.error(f"Error in start command: {e}", user_id=user_id)
        await message.answer("Произошла ошибка при инициализации. Попробуйте позже.")
        return
    
    # Определяем сценарий приветствия
    if is_new_user:
        await handle_new_user(message, user)
    else:
        await handle_returning_user(message, user)


async def handle_new_user(message: Message, user: User):
    """Обработка нового пользователя"""
    
    # Проверяем доступность пробного периода
    if bot_config.trial_enabled and not user.trial_used:
        await show_trial_offer(message, user)
    else:
        await show_welcome_message(message, user, show_subscription_info=True)


async def handle_returning_user(message: Message, user: User):
    """Обработка вернувшегося пользователя"""
    
    # Проверяем статус пробного периода
    if user.is_trial_active:
        await show_trial_active_message(message, user)
    
    # Проверяем статус Premium
    elif user.is_premium_expired and user.is_premium:
        await show_premium_expired_message(message, user)
    
    # Обычное приветствие
    else:
        await show_returning_user_message(message, user)


async def show_trial_offer(message: Message, user: User):
    """Показать предложение пробного периода"""
    
    trial_info = get_message(
        MessageType.WELCOME,
        "trial_available",
        trial_duration=bot_config.limits.max_batch_size
    )
    
    keyboard = create_trial_keyboard()
    
    await message.answer(
        trial_info,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


async def show_trial_active_message(message: Message, user: User):
    """Показать сообщение об активном пробном периоде"""
    
    # Рассчитываем оставшееся время
    if user.trial_expires_at:
        remaining = user.trial_expires_at - datetime.now(timezone.utc)
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        time_left = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
    else:
        time_left = "неизвестно"
    
    trial_message = get_message(
        MessageType.WELCOME,
        "trial_active",
        time_left=time_left
    )
    
    keyboard = create_main_menu_keyboard(user.current_user_type, is_admin=bot_config.is_admin(user.telegram_id))
    
    await message.answer(
        trial_message,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


async def show_premium_expired_message(message: Message, user: User):
    """Показать сообщение об истечении Premium"""
    
    expired_message = """⏰ <b>Ваша Premium подписка истекла</b>

Вы вернулись к бесплатному тарифу:
• 10 скачиваний в день
• Максимум 720p качество
• Обязательные подписки на каналы

💎 Хотите продлить Premium?"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Продлить Premium", callback_data="renew_premium")],
        [InlineKeyboardButton(text="📊 Мой статус", callback_data="status")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    
    await message.answer(
        expired_message,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


async def show_welcome_message(message: Message, user: User, show_subscription_info: bool = False):
    """Показать основное приветственное сообщение"""
    
    # Подготавливаем информацию о пробном периоде
    trial_info = ""
    if bot_config.trial_enabled and not user.trial_used:
        trial_info = f"""
🎁 <b>Доступен пробный период!</b>
⏰ {settings.TRIAL_DURATION_MINUTES} минут бесплатного Premium доступа
"""
    
    # Информация о подписках
    subscription_info = ""
    if show_subscription_info and bot_config.required_subs_enabled:
        if user.current_user_type in ["free", "trial"]:
            subscription_info = "\n🔒 <i>Для бесплатного использования требуется подписка на каналы</i>"
    
    welcome_text = get_message(
        MessageType.WELCOME,
        "new_user",
        trial_info=trial_info,
        subscription_info=subscription_info
    )
    
    keyboard = create_main_menu_keyboard(
        user.current_user_type, 
        is_admin=bot_config.is_admin(user.telegram_id)
    )
    
    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


async def show_returning_user_message(message: Message, user: User):
    """Показать сообщение для вернувшегося пользователя"""
    
    # Получаем лимиты пользователя
    daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
    daily_limit_text = str(daily_limit) if daily_limit < 999 else "∞"
    
    # Форматируем тип пользователя
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
    
    keyboard = create_main_menu_keyboard(
        user.current_user_type,
        is_admin=bot_config.is_admin(user.telegram_id)
    )
    
    await message.answer(
        welcome_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


@router.message(Command("help"))
async def help_command(message: Message):
    """Команда помощи"""
    
    help_text = get_message(MessageType.HELP, "main")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Форматы", callback_data="help_formats")],
        [InlineKeyboardButton(text="💎 Premium", callback_data="premium_benefits")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_main")]
    ])
    
    await message.answer(
        help_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


@router.message(Command("status"))
async def status_command(message: Message):
    """Команда статуса пользователя"""
    
    user_id = message.from_user.id
    
    try:
        async with get_async_session() as session:
            # Получаем пользователя
            user = await session.get(User, user_id)
            
            if not user:
                await message.answer("❌ Пользователь не найден. Используйте /start")
                return
            
            # Обновляем активность
            await update_user_activity(session, user, message.message_id)
            await session.commit()
            
            # Формируем статус
            status_text = await format_user_status(user)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 Детальная статистика", callback_data="detailed_stats")],
                [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_main")]
            ])
            
            await message.answer(
                status_text,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
    
    except Exception as e:
        logger.error(f"Error in status command: {e}", user_id=user_id)
        await message.answer("❌ Ошибка при получении статуса")


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
        remaining = user.trial_expires_at - (datetime.now(timezone.utc))
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            time_left = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"
            status_parts.append(f"⏰ Пробный период: осталось {time_left}")
    
    elif user.current_user_type == "premium" and user.premium_expires_at:
        status_parts.append(f"💎 Premium до: {user.premium_expires_at.strftime('%d.%m.%Y')}")
    
    # Проверка подписок для free пользователей
    if user.current_user_type == "free" and bot_config.required_subs_enabled:
        if user.subscription_check_passed:
            status_parts.append("✅ Подписки: проверены")
        else:
            status_parts.append("🔒 Подписки: требуется проверка")
    
    return "\n".join(status_parts)


@router.message(Command("settings"))
async def settings_command(message: Message):
    """Команда настроек"""
    
    settings_text = """⚙️ <b>Настройки</b>

🔧 <b>Доступные настройки:</b>
• Качество видео (автоматическое/ручное)
• Язык интерфейса
• Уведомления
• Способ доставки файлов

🚀 <b>Для Premium:</b>
• Автоматическое качество 4K
• Персонализация интерфейса"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Качество видео", callback_data="settings_quality")],
        [InlineKeyboardButton(text="🌐 Язык", callback_data="settings_language")],
        [InlineKeyboardButton(text="📮 Уведомления", callback_data="settings_notifications")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await message.answer(
        settings_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


# Обработчики deep links
@router.message(CommandStart(deep_link=True))
async def start_with_params(message: Message, command: CommandStart, state: FSMContext):
    """Обработка start с параметрами (deep linking)"""
    
    params = command.args
    user_id = message.from_user.id
    
    logger.info(f"Start with params: {params}", user_id=user_id)
    
    # Сначала выполняем обычный start
    await start_command(message, state)
    
    # Затем обрабатываем параметры
    if params:
        await handle_deep_link_params(message, params)


async def handle_deep_link_params(message: Message, params: str):
    """Обработка параметров deep link"""
    
    try:
        if params.startswith("ref_"):
            # Реферальная ссылка
            referrer_id = int(params[4:])
            await handle_referral_link(message, referrer_id)
        
        elif params == "trial":
            # Прямая ссылка на пробный период
            await message.answer("🎁 Переходим к активации пробного периода...")
            # TODO: Implement trial activation
        
        elif params == "premium":
            # Прямая ссылка на Premium
            await message.answer("💎 Переходим к оформлению Premium...")
            # TODO: Implement premium purchase
        
        else:
            logger.warning(f"Unknown deep link params: {params}")
    
    except Exception as e:
        logger.error(f"Error handling deep link params: {e}", params=params)


@router.message(F.text.regexp(r'https?://'))
async def handle_single_url(message: Message, state: FSMContext):
    """Обработка одиночной ссылки на видео"""
    user_id = message.from_user.id

    try:
        # Очищаем состояние
        await state.clear()

        # Извлекаем URL
        from bot.utils.url_extractor import extract_video_urls, validate_url, detect_platform

        urls = extract_video_urls(message.text)

        if not urls:
            await message.answer("❌ Не найдено поддерживаемых ссылок")
            return

        # Берем первую ссылку
        url = urls[0]

        if not validate_url(url):
            await message.answer("❌ Неподдерживаемая ссылка")
            return

        platform = detect_platform(url)

        # Получаем пользователя
        async with get_async_session() as session:
            user = await get_or_create_user(
                session=session,
                telegram_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name
            )
            await session.commit()

        # Проверяем лимиты
        if not user.can_download_today():
            daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
            await message.answer(
                f"⏰ Дневной лимит исчерпан ({daily_limit})\n"
                f"💎 Premium: безлимитные скачивания!"
            )
            return

        # Отправляем сообщение о начале обработки
        processing_msg = await message.answer(
            f"⏳ Начинаю загрузку...\n"
            f"🔗 Платформа: {platform.title()}\n"
            f"📱 Отправлю файл в чат"
        )

        # Используем batch сервис для создания одиночной загрузки
        from bot.services.batch_service import batch_service

        batch = await batch_service.create_batch_from_urls(
            user=user,
            urls=[url],
            delivery_method="individual"
        )

        # Запускаем обработку
        celery_task_id = await batch_service.start_batch_processing(batch)

        # Обновляем сообщение
        await processing_msg.edit_text(
            f"✅ Загрузка запущена!\n"
            f"🔗 Платформа: {platform.title()}\n"
            f"📊 ID: {batch.batch_id}\n"
            f"⏱️ Примерное время: 1-3 минуты"
        )

        logger.info(
            f"Single download started",
            user_id=user_id,
            platform=platform,
            batch_id=batch.id,
            celery_task_id=celery_task_id
        )

    except Exception as e:
        logger.error(f"Error processing single URL: {e}", user_id=user_id)
        await message.answer("❌ Произошла ошибка при обработке ссылки. Попробуйте позже.")


async def handle_referral_link(message: Message, referrer_id: int):
    """Обработка реферальной ссылки"""
    
    user_id = message.from_user.id
    
    # Нельзя быть рефералом самого себя
    if user_id == referrer_id:
        return
    
    try:
        async with get_async_session() as session:
            # Получаем нового пользователя
            new_user = await session.get(User, user_id)
            if not new_user or new_user.referrer_id:
                return  # Уже есть реферер или пользователь не найден
            
            # Получаем реферера
            referrer = await session.get(User, referrer_id)
            if not referrer:
                return
            
            # Устанавливаем связь
            new_user.referrer_id = referrer.telegram_id
            referrer.referrals_count += 1
            
            await session.commit()
            
            # Уведомляем пользователя
            await message.answer(
                f"🎉 Вы перешли по приглашению от {referrer.display_name}!\n"
                "Получите бонус за регистрацию!"
            )
            
            logger.info(
                f"Referral link processed", 
                new_user_id=user_id, 
                referrer_id=referrer_id
            )

    except Exception as e:
        logger.error(f"Error processing referral: {e}")