"""
VideoBot Pro - Batch Download Handler
Обработчик групповых скачиваний видео
"""

import asyncio
import re
import structlog
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from shared.config.database import get_async_session
from shared.models import User, DownloadBatch, DownloadTask, EventType, Platform
from shared.models.analytics import track_download_event
from bot.config import bot_config, get_message, MessageType
from bot.utils.user_manager import get_or_create_user, update_user_activity
from bot.utils.url_extractor import extract_video_urls, validate_url, detect_platform
from bot.utils.subscription_checker import check_required_subscriptions
from bot.keyboards.inline import create_batch_options_keyboard, create_batch_selection_keyboard
from bot.middlewares.rate_limit import rate_limit
from worker.tasks.batch_tasks import process_batch_download

logger = structlog.get_logger(__name__)

router = Router(name="batch_download")


class BatchDownloadStates(StatesGroup):
    """Состояния FSM для batch скачивания"""
    waiting_for_urls = State()
    selecting_files = State()
    choosing_delivery = State()


@router.message(F.text.regexp(r'https?://'))
@rate_limit(requests_per_minute=10)
async def handle_urls_message(message: Message, state: FSMContext):
    """
    Основной обработчик сообщений с URL
    Определяет количество ссылок и выбирает стратегию обработки
    """
    user_id = message.from_user.id
    message_text = message.text or message.caption or ""
    
    try:
        # Извлекаем URL из сообщения
        urls = extract_video_urls(message_text)
        
        if not urls:
            await message.answer(get_message(MessageType.ERROR, "invalid_url"))
            return
        
        # Проверяем лимиты
        if len(urls) > bot_config.limits.max_batch_size:
            await message.answer(
                f"⚠️ Максимум {bot_config.limits.max_batch_size} ссылок за раз! "
                f"Вы отправили {len(urls)}."
            )
            return
        
        # Получаем пользователя
        async with get_async_session() as session:
            user = await get_or_create_user(
                session=session,
                telegram_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name
            )
            
            # Проверяем может ли пользователь скачивать
            if not await can_user_download(user, len(urls)):
                await handle_download_restrictions(message, user, len(urls))
                return
            
            # Проверяем подписки для free пользователей
            if user.current_user_type in ["free"] and bot_config.required_subs_enabled:
                subscription_status = await check_required_subscriptions(user_id)
                if not subscription_status["all_subscribed"]:
                    await handle_subscription_required(message, subscription_status)
                    return
            
            await update_user_activity(session, user, message.message_id)
            await session.commit()
        
        # Определяем стратегию обработки
        if len(urls) == 1:
            # Одна ссылка - сразу скачиваем
            await process_single_download(message, urls[0], user)
        elif len(urls) <= 4:
            # 2-4 ссылки - автоматически в чат
            await process_small_batch(message, urls, user)
        else:
            # 5+ ссылок - предлагаем выбор доставки
            await process_large_batch(message, urls, user, state)
    
    except Exception as e:
        logger.error(f"Error processing URLs: {e}", user_id=user_id)
        await message.answer(get_message(MessageType.ERROR, "general"))


async def can_user_download(user: User, urls_count: int) -> bool:
    """Проверить может ли пользователь скачивать"""
    if not user.can_download:
        return False
    
    # Проверяем дневной лимит
    if not user.can_download_today():
        return False
    
    # Для batch проверяем не превысит ли лимит
    daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
    if daily_limit < 999 and (user.downloads_today + urls_count) > daily_limit:
        return False
    
    return True


async def handle_download_restrictions(message: Message, user: User, urls_count: int):
    """Обработка ограничений скачивания"""
    if user.is_banned or user.is_temp_banned:
        ban_message = "🚫 Ваш аккаунт заблокирован."
        if user.banned_until:
            ban_message += f"\nБлокировка до: {user.banned_until.strftime('%d.%m.%Y %H:%M')}"
        await message.answer(ban_message)
        return
    
    if not user.can_download_today():
        daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
        await message.answer(
            get_message(
                MessageType.ERROR,
                "daily_limit_exceeded",
                limit=daily_limit
            )
        )
        return
    
    # Превышение лимита batch'ем
    remaining = bot_config.get_user_daily_limit(user.current_user_type) - user.downloads_today
    await message.answer(
        f"⏰ Осталось скачиваний сегодня: {remaining}\n"
        f"Вы хотите скачать: {urls_count}\n\n"
        f"💎 Premium: безлимитные скачивания!"
    )


async def handle_subscription_required(message: Message, subscription_status: Dict):
    """Обработка требования подписок"""
    from bot.handlers.subscription_check import show_subscription_check
    await show_subscription_check(message, subscription_status)


async def process_single_download(message: Message, url: str, user: User):
    """Обработка одной ссылки"""
    # Валидируем URL
    if not validate_url(url):
        await message.answer(get_message(MessageType.ERROR, "invalid_url"))
        return
    
    platform = detect_platform(url)
    
    # Отправляем сообщение о начале обработки
    processing_msg = await message.answer(
        get_message(MessageType.PROCESSING, "analyzing")
    )
    
    try:
        # Создаем batch с одной ссылкой
        async with get_async_session() as session:
            batch = await create_download_batch(
                session=session,
                user=user,
                urls=[url],
                delivery_method="individual"
            )
            await session.commit()
            
            # Аналитика
            await track_download_event(
                event_type=EventType.DOWNLOAD_STARTED,
                user_id=user.id,
                platform=platform,
                event_data={"batch_id": batch.id, "urls_count": 1}
            )
        
        # Запускаем задачу в фоне
        task = process_batch_download.delay(batch.id)
        
        # Обновляем сообщение
        await processing_msg.edit_text(
            "⏳ Скачиваю видео...\n"
            f"🔗 Ссылка: {platform.title()}\n"
            f"📊 Batch ID: {batch.batch_id}"
        )
        
        logger.info(
            f"Single download started",
            user_id=user.telegram_id,
            batch_id=batch.id,
            platform=platform,
            celery_task_id=task.id
        )
    
    except Exception as e:
        logger.error(f"Error starting single download: {e}")
        await processing_msg.edit_text(get_message(MessageType.ERROR, "general"))


async def process_small_batch(message: Message, urls: List[str], user: User):
    """Обработка маленького batch (2-4 ссылки)"""
    # Анализируем ссылки
    analysis_msg = await message.answer(
        f"📥 Найдено ссылок: {len(urls)}\n\n🔍 Анализирую..."
    )
    
    # Быстрый анализ платформ
    platforms_count = {}
    valid_urls = []
    
    for url in urls:
        if validate_url(url):
            platform = detect_platform(url)
            platforms_count[platform] = platforms_count.get(platform, 0) + 1
            valid_urls.append(url)
    
    if not valid_urls:
        await analysis_msg.edit_text(get_message(MessageType.ERROR, "invalid_url"))
        return
    
    # Показываем превью
    preview_lines = [f"📥 Готово к скачиванию: {len(valid_urls)}/{len(urls)}"]
    for platform, count in platforms_count.items():
        emoji = {"youtube": "🔴", "tiktok": "🎵", "instagram": "📸"}.get(platform, "🎬")
        preview_lines.append(f"{emoji} {platform.title()}: {count}")
    
    preview_lines.append(f"\n⚡ Автоматически отправлю в чат")
    preview_lines.append(f"📊 Примерный размер: ~{len(valid_urls) * 15}MB")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ Начать скачивание", callback_data=f"confirm_small_batch")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_batch")]
    ])
    
    await analysis_msg.edit_text(
        "\n".join(preview_lines),
        reply_markup=keyboard
    )
    
    # Сохраняем данные в состояние
    await message.bot.session.set(f"batch_urls_{message.from_user.id}", {
        "urls": valid_urls,
        "user_id": user.id,
        "delivery_method": "individual"
    })


async def process_large_batch(message: Message, urls: List[str], user: User, state: FSMContext):
    """Обработка большого batch (5+ ссылок)"""
    # Анализируем ссылки
    analysis_msg = await message.answer(
        f"📥 Найдено ссылок: {len(urls)}\n\n🔍 Анализирую..."
    )
    
    # Валидируем все URL
    valid_urls = []
    invalid_count = 0
    platforms_stats = {}
    
    for url in urls:
        if validate_url(url):
            platform = detect_platform(url)
            platforms_stats[platform] = platforms_stats.get(platform, 0) + 1
            valid_urls.append({
                "url": url,
                "platform": platform,
                "selected": True  # По умолчанию все выбраны
            })
        else:
            invalid_count += 1
    
    if not valid_urls:
        await analysis_msg.edit_text(get_message(MessageType.ERROR, "invalid_url"))
        return
    
    # Формируем сообщение выбора
    choice_text = [
        f"📥 Найдено ссылок: {len(valid_urls)}",
        f"❌ Неподдерживаемых: {invalid_count}" if invalid_count > 0 else "",
        "",
        "🤔 Как вам удобнее получить файлы?",
        "",
        f"📊 Примерный размер: ~{len(valid_urls) * 20}MB"
    ]
    
    # Добавляем статистику по платформам
    if platforms_stats:
        choice_text.append("\n🎯 Найденные платформы:")
        for platform, count in platforms_stats.items():
            emoji = {"youtube": "🔴", "tiktok": "🎵", "instagram": "📸"}.get(platform, "🎬")
            choice_text.append(f"• {emoji} {platform.title()}: {count}")
    
    keyboard = create_batch_options_keyboard(len(valid_urls))
    
    await analysis_msg.edit_text(
        "\n".join([line for line in choice_text if line]),
        reply_markup=keyboard
    )
    
    # Сохраняем данные в FSM
    await state.set_state(BatchDownloadStates.choosing_delivery)
    await state.update_data({
        "urls": valid_urls,
        "user_id": user.id,
        "platforms_stats": platforms_stats,
        "original_message_id": analysis_msg.message_id
    })


@router.callback_query(F.data.startswith("batch_"))
async def handle_batch_callbacks(callback: CallbackQuery, state: FSMContext):
    """Обработчик callback'ов для batch операций"""
    action = callback.data.split("_", 1)[1]
    user_id = callback.from_user.id
    
    try:
        if action == "individual":
            await handle_individual_delivery(callback, state)
        elif action == "archive":
            await handle_archive_delivery(callback, state)
        elif action == "selective":
            await handle_selective_delivery(callback, state)
        elif action == "cancel":
            await handle_cancel_batch(callback, state)
        elif action.startswith("confirm"):
            await handle_confirm_batch(callback, state)
        else:
            await callback.answer("Неизвестная команда")
    
    except Exception as e:
        logger.error(f"Error in batch callback: {e}", user_id=user_id)
        await callback.answer("Произошла ошибка")


async def handle_individual_delivery(callback: CallbackQuery, state: FSMContext):
    """Обработка доставки по одному файлу"""
    data = await state.get_data()
    urls_data = data.get("urls", [])
    user_id = data.get("user_id")
    
    await callback.message.edit_text(
        f"📱 <b>Отправка в чат по одному</b>\n\n"
        f"📁 Файлов: {len(urls_data)}\n"
        f"⚡ Начинаю обработку...",
        reply_markup=None
    )
    
    # Создаем batch
    await create_and_start_batch(
        callback.message,
        urls_data,
        user_id,
        delivery_method="individual"
    )
    
    await state.clear()
    await callback.answer()


async def handle_archive_delivery(callback: CallbackQuery, state: FSMContext):
    """Обработка доставки архивом"""
    data = await state.get_data()
    urls_data = data.get("urls", [])
    user_id = data.get("user_id")
    
    await callback.message.edit_text(
        f"📦 <b>Создание архива</b>\n\n"
        f"📁 Файлов: {len(urls_data)}\n"
        f"🌐 Доставка через CDN\n"
        f"⏰ Доступен 24 часа\n\n"
        f"⚡ Начинаю обработку...",
        reply_markup=None
    )
    
    # Создаем batch с архивом
    await create_and_start_batch(
        callback.message,
        urls_data,
        user_id,
        delivery_method="archive"
    )
    
    await state.clear()
    await callback.answer("Создаю ZIP архив...")


async def handle_selective_delivery(callback: CallbackQuery, state: FSMContext):
    """Обработка выборочной доставки"""
    data = await state.get_data()
    urls_data = data.get("urls", [])
    
    # Создаем клавиатуру для выбора файлов
    keyboard = create_batch_selection_keyboard(urls_data)
    
    selection_text = [
        f"⚙️ <b>Выберите файлы ({sum(1 for u in urls_data if u['selected'])}/{len(urls_data)})</b>",
        "",
        "🎯 Доступные видео:"
    ]
    
    # Добавляем список файлов
    for i, url_data in enumerate(urls_data[:10], 1):  # Показываем первые 10
        status = "✅" if url_data["selected"] else "❌"
        platform = url_data["platform"].title()
        emoji = {"Youtube": "🔴", "Tiktok": "🎵", "Instagram": "📸"}.get(platform, "🎬")
        selection_text.append(f"{status} {i}. {emoji} {platform}")
    
    if len(urls_data) > 10:
        selection_text.append(f"... и еще {len(urls_data) - 10}")
    
    await callback.message.edit_text(
        "\n".join(selection_text),
        reply_markup=keyboard
    )
    
    await state.set_state(BatchDownloadStates.selecting_files)
    await callback.answer()


async def handle_cancel_batch(callback: CallbackQuery, state: FSMContext):
    """Отмена batch операции"""
    await callback.message.edit_text(
        "❌ Операция отменена.\n\n"
        "💡 Отправьте ссылки еще раз для повторной обработки."
    )
    
    await state.clear()
    await callback.answer("Операция отменена")


async def create_download_batch(session, user: User, urls: List[str], 
                               delivery_method: str = "individual") -> DownloadBatch:
    """Создание batch задачи в базе данных"""
    from uuid import uuid4
    
    # Генерируем уникальный batch_id
    batch_id = f"batch_{uuid4().hex[:12]}"
    
    # Создаем batch
    batch = DownloadBatch(
        user_id=user.id,
        telegram_user_id=user.telegram_id,
        batch_id=batch_id,
        urls=urls,
        total_urls=len(urls),
        delivery_method=delivery_method,
        send_to_chat=(delivery_method == "individual"),
        create_archive=(delivery_method == "archive"),
        user_message_id=None,  # Заполним позже если нужно
        priority=10 if user.current_user_type == "admin" else 5
    )
    
    # Устанавливаем время истечения
    retention_hours = bot_config.get_user_limits(user.current_user_type)
    if hasattr(retention_hours, '__getitem__'):
        hours = 24  # default fallback
    else:
        hours = retention_hours
    batch.set_expiration(hours)
    
    session.add(batch)
    await session.flush()  # Получаем ID
    
    # Создаем отдельные задачи для каждого URL
    for i, url in enumerate(urls):
        task = DownloadTask.create_from_url(
            url=url,
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            batch_id=batch.id,
            order_in_batch=i,
            priority=batch.priority
        )
        session.add(task)
    
    return batch


async def create_and_start_batch(message: Message, urls_data: List[Dict], 
                                user_id: int, delivery_method: str):
    """Создание и запуск batch задачи"""
    try:
        async with get_async_session() as session:
            # Получаем пользователя
            user = await session.get(User, user_id)
            if not user:
                await message.edit_text("❌ Пользователь не найден")
                return
            
            # Извлекаем только URL
            urls = [item["url"] if isinstance(item, dict) else item for item in urls_data]
            
            # Создаем batch
            batch = await create_download_batch(
                session=session,
                user=user,
                urls=urls,
                delivery_method=delivery_method
            )
            
            # Обновляем счетчики пользователя
            user.increment_downloads(len(urls))
            
            await session.commit()
            
            # Аналитика
            await track_download_event(
                event_type=EventType.BATCH_CREATED,
                user_id=user.id,
                platform="mixed",
                value=len(urls),
                event_data={
                    "batch_id": batch.id,
                    "delivery_method": delivery_method
                }
            )
        
        # Запускаем обработку в фоне
        task = process_batch_download.delay(batch.id)
        
        # Обновляем сообщение
        progress_text = [
            f"✅ <b>Batch создан</b>",
            f"📋 ID: {batch.batch_id}",
            f"📁 Файлов: {len(urls)}",
            f"🚀 Метод: {delivery_method}",
            "",
            f"⏳ Обработка началась...",
            f"📊 Вы можете продолжать отправлять новые ссылки"
        ]
        
        await message.edit_text("\n".join(progress_text))
        
        logger.info(
            f"Batch created and started",
            user_id=user.telegram_id,
            batch_id=batch.id,
            urls_count=len(urls),
            delivery_method=delivery_method,
            celery_task_id=task.id
        )
    
    except Exception as e:
        logger.error(f"Error creating batch: {e}")
        await message.edit_text(
            "❌ Ошибка при создании задачи. Попробуйте позже."
        )