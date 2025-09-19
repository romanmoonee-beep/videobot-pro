"""
VideoBot Pro - Notification Tasks
Задачи для отправки уведомлений пользователям
"""

import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from celery import current_task

from worker.celery_app import celery_app
from shared.config.database import get_async_session
from shared.models import (
    User, DownloadTask, DownloadBatch, Payment, BroadcastMessage,
    EventType
)
from shared.config.settings import settings
from shared.models.analytics import track_system_event

logger = structlog.get_logger(__name__)

@celery_app.task(bind=True, name="notifications.send_download_completion")
def send_download_completion_notification(self, task_id: int):
    """
    Отправка уведомления о завершении загрузки
    
    Args:
        task_id: ID задачи загрузки
    """
    try:
        import asyncio
        return asyncio.run(_send_download_notification_async(task_id))
    except Exception as e:
        logger.error(f"Error sending download notification: {e}")
        raise

async def _send_download_notification_async(task_id: int):
    """Асинхронная отправка уведомления о загрузке"""
    try:
        async with get_async_session() as session:
            # Получаем информацию о задаче
            task_result = await session.execute(
                """
                SELECT dt.*, u.telegram_id, u.notification_settings
                FROM download_tasks dt
                JOIN users u ON dt.user_id = u.id
                WHERE dt.id = :task_id
                """,
                {'task_id': task_id}
            )
            task_data = task_result.fetchone()
            
            if not task_data:
                logger.warning(f"Download task {task_id} not found")
                return {"error": "Task not found"}
            
            # Проверяем настройки уведомлений пользователя
            notification_settings = task_data.notification_settings or {}
            if not notification_settings.get('download_complete', True):
                return {"skipped": "User disabled notifications"}
            
            # Импортируем бота (избегаем циклических импортов)
            from aiogram import Bot
            bot = Bot(token=settings.BOT_TOKEN)
            
            # Формируем сообщение
            if task_data.status == 'completed':
                message = await _format_success_message(task_data)
                keyboard = await _create_download_keyboard(task_data)
            else:
                message = await _format_error_message(task_data)
                keyboard = None
            
            # Отправляем уведомление
            try:
                await bot.send_message(
                    chat_id=task_data.telegram_id,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                
                # Обновляем флаг уведомления
                await session.execute(
                    "UPDATE download_tasks SET notification_sent = true WHERE id = :task_id",
                    {'task_id': task_id}
                )
                await session.commit()
                
                # Трекаем событие
                await track_system_event(
                    event_type=EventType.MESSAGE_SENT,
                    event_data={
                        'type': 'download_notification',
                        'task_id': task_id,
                        'user_id': task_data.telegram_id,
                        'status': task_data.status
                    }
                )
                
                return {"sent": True, "user_id": task_data.telegram_id}
                
            except Exception as e:
                logger.error(f"Failed to send notification to user {task_data.telegram_id}: {e}")
                
                # Помечаем пользователя как заблокировавшего бота
                if "bot was blocked" in str(e).lower():
                    await session.execute(
                        """
                        UPDATE users 
                        SET is_bot_blocked = true, bot_blocked_at = :now 
                        WHERE telegram_id = :telegram_id
                        """,
                        {'now': datetime.utcnow(), 'telegram_id': task_data.telegram_id}
                    )
                    await session.commit()
                
                return {"error": str(e)}
                
    except Exception as e:
        logger.error(f"Error in download notification: {e}")
        raise

async def _format_success_message(task_data) -> str:
    """Форматирование сообщения об успешной загрузке"""
    message_parts = [
        "✅ <b>Загрузка завершена!</b>",
        ""
    ]
    
    if task_data.video_title:
        title = task_data.video_title[:50] + "..." if len(task_data.video_title) > 50 else task_data.video_title
        message_parts.append(f"📝 <b>{title}</b>")
    
    if task_data.platform:
        platform_emoji = {"youtube": "🔴", "tiktok": "⚫", "instagram": "🟣"}.get(task_data.platform, "🎬")
        message_parts.append(f"{platform_emoji} Платформа: {task_data.platform.title()}")
    
    if task_data.video_duration_seconds:
        duration = _format_duration(task_data.video_duration_seconds)
        message_parts.append(f"⏱ Длительность: {duration}")
    
    if task_data.file_size_bytes:
        size = _format_file_size(task_data.file_size_bytes)
        message_parts.append(f"📊 Размер: {size}")
    
    if task_data.actual_quality:
        message_parts.append(f"🎯 Качество: {task_data.actual_quality}")
    
    if task_data.cdn_url:
        message_parts.extend([
            "",
            "📥 Файл готов к скачиванию!"
        ])
        
        if task_data.expires_at:
            expires_in = task_data.expires_at - datetime.utcnow()
            if expires_in.days > 0:
                message_parts.append(f"⏰ Доступен: {expires_in.days} дн.")
            else:
                hours = int(expires_in.total_seconds() / 3600)
                message_parts.append(f"⏰ Доступен: {hours} ч.")
    
    return "\n".join(message_parts)

async def _format_error_message(task_data) -> str:
    """Форматирование сообщения об ошибке"""
    message_parts = [
        "❌ <b>Ошибка загрузки</b>",
        ""
    ]
    
    if task_data.platform:
        platform_emoji = {"youtube": "🔴", "tiktok": "⚫", "instagram": "🟣"}.get(task_data.platform, "🎬")
        message_parts.append(f"{platform_emoji} Платформа: {task_data.platform.title()}")
    
    # Пользовательское сообщение об ошибке
    error_msg = _get_user_friendly_error(task_data.error_message or "Неизвестная ошибка")
    message_parts.extend([
        f"💬 {error_msg}",
        "",
        "💡 <b>Попробуйте:</b>",
        "• Проверить ссылку в браузере",
        "• Попробовать другое качество",
        "• Повторить через несколько минут"
    ])
    
    return "\n".join(message_parts)

async def _create_download_keyboard(task_data):
    """Создание клавиатуры для уведомления о загрузке"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    buttons = []
    
    if task_data.cdn_url and task_data.status == 'completed':
        buttons.append([
            InlineKeyboardButton(
                text="📥 Скачать файл",
                url=task_data.cdn_url
            )
        ])
    
    if task_data.status == 'failed' and task_data.retry_count < task_data.max_retries:
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Попробовать снова",
                callback_data=f"retry_task_{task_data.id}"
            )
        ])
    
    if buttons:
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    return None

def _get_user_friendly_error(error_message: str) -> str:
    """Преобразование технической ошибки в понятную пользователю"""
    error_lower = error_message.lower()
    
    if 'video unavailable' in error_lower or 'private' in error_lower:
        return "Видео недоступно или удалено"
    elif 'age restricted' in error_lower:
        return "Видео имеет возрастные ограничения"
    elif 'geo blocked' in error_lower:
        return "Видео недоступно в вашей стране"
    elif 'network' in error_lower or 'timeout' in error_lower:
        return "Проблемы с сетевым соединением"
    elif 'file too large' in error_lower:
        return "Файл слишком большой"
    elif 'format not available' in error_lower:
        return "Нужное качество недоступно"
    else:
        return "Техническая ошибка сервиса"

def _format_duration(seconds: int) -> str:
    """Форматирование длительности"""
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    else:
        return f"{mins:02d}:{secs:02d}"

def _format_file_size(bytes_size: int) -> str:
    """Форматирование размера файла"""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} ТБ"

@celery_app.task(bind=True, name="notifications.send_batch_completion")
def send_batch_completion_notification(self, batch_id: int):
    """
    Отправка уведомления о завершении batch загрузки
    
    Args:
        batch_id: ID batch'а
    """
    try:
        import asyncio
        return asyncio.run(_send_batch_notification_async(batch_id))
    except Exception as e:
        logger.error(f"Error sending batch notification: {e}")
        raise

async def _send_batch_notification_async(batch_id: int):
    """Асинхронная отправка уведомления о batch"""
    try:
        async with get_async_session() as session:
            # Получаем информацию о batch
            batch_result = await session.execute(
                """
                SELECT db.*, u.telegram_id, u.notification_settings
                FROM download_batches db
                JOIN users u ON db.user_id = u.id
                WHERE db.id = :batch_id
                """,
                {'batch_id': batch_id}
            )
            batch_data = batch_result.fetchone()
            
            if not batch_data:
                logger.warning(f"Download batch {batch_id} not found")
                return {"error": "Batch not found"}
            
            # Проверяем настройки уведомлений
            notification_settings = batch_data.notification_settings or {}
            if not notification_settings.get('download_complete', True):
                return {"skipped": "User disabled notifications"}
            
            # Получаем статистику задач в batch
            tasks_stats = await session.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                    COALESCE(SUM(file_size_bytes)/1024/1024, 0) as total_size_mb
                FROM download_tasks 
                WHERE batch_id = :batch_id
                """,
                {'batch_id': batch_id}
            )
            stats = tasks_stats.fetchone()
            
            from aiogram import Bot
            bot = Bot(token=settings.BOT_TOKEN)
            
            # Формируем сообщение
            message = await _format_batch_message(batch_data, stats)
            keyboard = await _create_batch_keyboard(batch_data, stats)
            
            try:
                await bot.send_message(
                    chat_id=batch_data.telegram_id,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                
                # Обновляем флаг уведомления
                await session.execute(
                    "UPDATE download_batches SET notification_sent = true WHERE id = :batch_id",
                    {'batch_id': batch_id}
                )
                await session.commit()
                
                return {"sent": True, "user_id": batch_data.telegram_id}
                
            except Exception as e:
                logger.error(f"Failed to send batch notification: {e}")
                return {"error": str(e)}
                
    except Exception as e:
        logger.error(f"Error in batch notification: {e}")
        raise

async def _format_batch_message(batch_data, stats) -> str:
    """Форматирование сообщения о batch"""
    success_rate = (stats.completed / stats.total * 100) if stats.total > 0 else 0
    
    message_parts = [
        "🎉 <b>Групповая загрузка завершена!</b>",
        "",
        f"📊 Результат: {stats.completed}/{stats.total} файлов",
        f"📈 Успешность: {success_rate:.1f}%"
    ]
    
    if stats.failed > 0:
        message_parts.append(f"❌ Ошибок: {stats.failed}")
    
    if stats.total_size_mb > 0:
        message_parts.append(f"💾 Общий размер: {stats.total_size_mb:.1f} МБ")
    
    if batch_data.archive_url:
        message_parts.extend([
            "",
            "📦 Файлы упакованы в архив"
        ])
        
        if batch_data.expires_at:
            expires_in = batch_data.expires_at - datetime.utcnow()
            if expires_in.days > 0:
                message_parts.append(f"⏰ Доступен: {expires_in.days} дн.")
            else:
                hours = int(expires_in.total_seconds() / 3600)
                message_parts.append(f"⏰ Доступен: {hours} ч.")
    
    return "\n".join(message_parts)

async def _create_batch_keyboard(batch_data, stats):
    """Создание клавиатуры для batch уведомления"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    buttons = []
    
    if batch_data.archive_url:
        buttons.append([
            InlineKeyboardButton(
                text="📦 Скачать архив",
                url=batch_data.archive_url
            )
        ])
    
    if stats.failed > 0:
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Повторить неудачные",
                callback_data=f"retry_batch_{batch_data.id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="📊 Подробная статистика",
            callback_data=f"batch_stats_{batch_data.id}"
        )
    ])
    
    if buttons:
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    return None

@celery_app.task(bind=True, name="notifications.send_premium_expiry_warning")
def send_premium_expiry_warning(self, user_id: int, days_remaining: int):
    """
    Отправка предупреждения об истечении Premium
    
    Args:
        user_id: ID пользователя
        days_remaining: Дней до истечения
    """
    try:
        import asyncio
        return asyncio.run(_send_premium_warning_async(user_id, days_remaining))
    except Exception as e:
        logger.error(f"Error sending premium warning: {e}")
        raise

async def _send_premium_warning_async(user_id: int, days_remaining: int):
    """Асинхронная отправка предупреждения о Premium"""
    try:
        async with get_async_session() as session:
            user_result = await session.execute(
                "SELECT * FROM users WHERE id = :user_id",
                {'user_id': user_id}
            )
            user = user_result.fetchone()
            
            if not user or not user.is_premium:
                return {"error": "User not found or not premium"}
            
            # Проверяем настройки уведомлений
            notification_settings = user.notification_settings or {}
            if not notification_settings.get('premium_expiry', True):
                return {"skipped": "User disabled notifications"}
            
            from aiogram import Bot
            bot = Bot(token=settings.BOT_TOKEN)
            
            # Формируем сообщение
            if days_remaining > 1:
                message = f"""
⏰ <b>Premium скоро закончится!</b>

📅 Осталось дней: {days_remaining}
📆 Истекает: {user.premium_expires_at.strftime('%d.%m.%Y')}

💎 <b>Что вы потеряете:</b>
• Безлимитные скачивания
• 4K качество
• Приоритетная обработка
• Хранение файлов 30 дней

🔄 Автопродление: {'Включено' if user.premium_auto_renew else 'Отключено'}
"""
            else:
                message = """
🚨 <b>Premium истекает сегодня!</b>

⏰ Premium доступ заканчивается в течение дня.

💎 <b>Что вы потеряете:</b>
• Безлимитные скачивания
• 4K качество
• Приоритетная обработка
• Хранение файлов 30 дней
"""
            
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            keyboard_buttons = [
                [InlineKeyboardButton(
                    text="💎 Продлить Premium",
                    callback_data="renew_premium"
                )]
            ]
            
            if not user.premium_auto_renew:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="🔄 Включить автопродление",
                        callback_data="enable_auto_renew"
                    )
                ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                
                return {"sent": True, "user_id": user.telegram_id}
                
            except Exception as e:
                logger.error(f"Failed to send premium warning: {e}")
                return {"error": str(e)}
                
    except Exception as e:
        logger.error(f"Error in premium warning: {e}")
        raise

@celery_app.task(bind=True, name="notifications.send_broadcast")
def send_broadcast_message(self, broadcast_id: int, user_ids: List[int] = None, test_mode: bool = False):
    """
    Отправка рассылки пользователям
    
    Args:
        broadcast_id: ID рассылки
        user_ids: Список ID пользователей (None = все по фильтру)
        test_mode: Тестовый режим (только админам)
    """
    try:
        import asyncio
        return asyncio.run(_send_broadcast_async(broadcast_id, user_ids, test_mode))
    except Exception as e:
        logger.error(f"Error sending broadcast: {e}")
        raise

async def _send_broadcast_async(broadcast_id: int, user_ids: List[int], test_mode: bool):
    """Асинхронная отправка рассылки"""
    try:
        async with get_async_session() as session:
            # Получаем рассылку
            broadcast_result = await session.execute(
                "SELECT * FROM broadcast_messages WHERE id = :broadcast_id",
                {'broadcast_id': broadcast_id}
            )
            broadcast = broadcast_result.fetchone()
            
            if not broadcast:
                return {"error": "Broadcast not found"}
            
            # Получаем список пользователей
            if test_mode:
                # Тестовый режим - только админы
                target_users = settings.ADMIN_IDS
            elif user_ids:
                target_users = user_ids
            else:
                # Получаем пользователей по фильтру рассылки
                target_users = await _get_broadcast_target_users(session, broadcast)
            
            if not target_users:
                return {"error": "No target users found"}
            
            from aiogram import Bot
            bot = Bot(token=settings.BOT_TOKEN)
            
            # Обновляем статус рассылки
            await session.execute(
                """
                UPDATE broadcast_messages 
                SET status = 'sending', started_at = :now, total_recipients = :total
                WHERE id = :broadcast_id
                """,
                {
                    'now': datetime.utcnow(),
                    'total': len(target_users),
                    'broadcast_id': broadcast_id
                }
            )
            await session.commit()
            
            # Отправляем сообщения
            sent_count = 0
            failed_count = 0
            blocked_count = 0
            
            for user_id in target_users:
                try:
                    # Формируем клавиатуру если есть
                    keyboard = None
                    if broadcast.inline_keyboard:
                        keyboard = _parse_broadcast_keyboard(broadcast.inline_keyboard)
                    
                    # Отправляем сообщение
                    if broadcast.media_type and broadcast.media_file_id:
                        # Сообщение с медиа
                        if broadcast.media_type == 'photo':
                            await bot.send_photo(
                                chat_id=user_id,
                                photo=broadcast.media_file_id,
                                caption=broadcast.message_text,
                                reply_markup=keyboard,
                                parse_mode=broadcast.parse_mode
                            )
                        elif broadcast.media_type == 'video':
                            await bot.send_video(
                                chat_id=user_id,
                                video=broadcast.media_file_id,
                                caption=broadcast.message_text,
                                reply_markup=keyboard,
                                parse_mode=broadcast.parse_mode
                            )
                        # Добавить другие типы медиа по необходимости
                    else:
                        # Текстовое сообщение
                        await bot.send_message(
                            chat_id=user_id,
                            text=broadcast.message_text,
                            reply_markup=keyboard,
                            parse_mode=broadcast.parse_mode,
                            disable_notification=broadcast.disable_notification,
                            protect_content=broadcast.protect_content
                        )
                    
                    sent_count += 1
                    
                    # Задержка между отправками
                    if sent_count % 30 == 0:  # Каждые 30 сообщений пауза
                        import asyncio
                        await asyncio.sleep(1)
                    
                except Exception as e:
                    if "bot was blocked" in str(e).lower():
                        blocked_count += 1
                        # Помечаем пользователя как заблокировавшего бота
                        await session.execute(
                            """
                            UPDATE users 
                            SET is_bot_blocked = true, bot_blocked_at = :now 
                            WHERE telegram_id = :user_id
                            """,
                            {'now': datetime.utcnow(), 'user_id': user_id}
                        )
                    else:
                        failed_count += 1
                        logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            
            # Обновляем статистику рассылки
            await session.execute(
                """
                UPDATE broadcast_messages 
                SET status = 'completed', completed_at = :now,
                    sent_count = :sent, failed_count = :failed, blocked_count = :blocked
                WHERE id = :broadcast_id
                """,
                {
                    'now': datetime.utcnow(),
                    'sent': sent_count,
                    'failed': failed_count,
                    'blocked': blocked_count,
                    'broadcast_id': broadcast_id
                }
            )
            await session.commit()
            
            return {
                "broadcast_id": broadcast_id,
                "total_recipients": len(target_users),
                "sent": sent_count,
                "failed": failed_count,
                "blocked": blocked_count,
                "success_rate": (sent_count / len(target_users) * 100) if target_users else 0
            }
            
    except Exception as e:
        # Помечаем рассылку как неудачную
        async with get_async_session() as session:
            await session.execute(
                """
                UPDATE broadcast_messages 
                SET status = 'failed', completed_at = :now, error_message = :error
                WHERE id = :broadcast_id
                """,
                {
                    'now': datetime.utcnow(),
                    'error': str(e),
                    'broadcast_id': broadcast_id
                }
            )
            await session.commit()
        
        logger.error(f"Error in broadcast sending: {e}")
        raise

async def _get_broadcast_target_users(session, broadcast) -> List[int]:
    """Получить список пользователей для рассылки"""
    query = """
        SELECT telegram_id FROM users 
        WHERE is_deleted = false AND is_banned = false AND is_bot_blocked = false
    """
    params = {}
    
    # Фильтр по типу аудитории
    if broadcast.target_type == "premium_users":
        query += " AND is_premium = true"
    elif broadcast.target_type == "free_users":
        query += " AND is_premium = false"
    elif broadcast.target_type == "trial_users":
        query += " AND user_type = 'trial'"
    elif broadcast.target_type == "specific_users" and broadcast.target_user_ids:
        placeholders = ",".join([f":user_id_{i}" for i in range(len(broadcast.target_user_ids))])
        query += f" AND id IN ({placeholders})"
        for i, user_id in enumerate(broadcast.target_user_ids):
            params[f'user_id_{i}'] = user_id
    
    # Дополнительные фильтры
    if broadcast.target_filters:
        filters = broadcast.target_filters
        
        if 'last_active_days' in filters:
            query += " AND last_active_at > :last_active_date"
            params['last_active_date'] = datetime.utcnow() - timedelta(days=filters['last_active_days'])
        
        if 'min_downloads' in filters:
            query += " AND downloads_total >= :min_downloads"
            params['min_downloads'] = filters['min_downloads']
    
    result = await session.execute(query, params)
    return [row[0] for row in result.fetchall()]

def _parse_broadcast_keyboard(keyboard_data: Dict[str, Any]):
    """Парсинг клавиатуры рассылки"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    try:
        if not keyboard_data or 'inline_keyboard' not in keyboard_data:
            return None
        
        buttons = []
        for row in keyboard_data['inline_keyboard']:
            button_row = []
            for button in row:
                if 'url' in button:
                    button_row.append(InlineKeyboardButton(
                        text=button['text'],
                        url=button['url']
                    ))
                elif 'callback_data' in button:
                    button_row.append(InlineKeyboardButton(
                        text=button['text'],
                        callback_data=button['callback_data']
                    ))
            
            if button_row:
                buttons.append(button_row)
        
        return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        
    except Exception as e:
        logger.error(f"Error parsing broadcast keyboard: {e}")
        return None

@celery_app.task(bind=True, name="notifications.check_premium_expiry")
def check_premium_expiry_notifications(self):
    """Проверка и отправка уведомлений об истечении Premium"""
    try:
        import asyncio
        return asyncio.run(_check_premium_expiry_async())
    except Exception as e:
        logger.error(f"Error checking premium expiry: {e}")
        raise

async def _check_premium_expiry_async():
    """Асинхронная проверка истечения Premium"""
    try:
        async with get_async_session() as session:
            # Пользователи с истекающим Premium (7, 3, 1 день)
            warning_days = [7, 3, 1]
            notifications_sent = 0
            
            for days in warning_days:
                target_date = datetime.utcnow() + timedelta(days=days)
                
                users_result = await session.execute(
                    """
                    SELECT id, telegram_id, premium_expires_at 
                    FROM users 
                    WHERE is_premium = true 
                    AND premium_expires_at::date = :target_date
                    AND (notification_settings IS NULL 
                         OR notification_settings->>'premium_expiry' != 'false')
                    """,
                    {'target_date': target_date.date()}
                )
                
                users = users_result.fetchall()
                
                for user in users:
                    # Отправляем уведомление
                    send_premium_expiry_warning.delay(user.id, days)
                    notifications_sent += 1
            
            return {"notifications_scheduled": notifications_sent}
            
    except Exception as e:
        logger.error(f"Error in premium expiry check: {e}")
        raise

@celery_app.task(bind=True, name="notifications.daily_summary")
def send_daily_summary_to_admins(self):
    """Отправка ежедневной сводки администраторам"""
    try:
        import asyncio
        return asyncio.run(_send_daily_summary_async())
    except Exception as e:
        logger.error(f"Error sending daily summary: {e}")
        raise

async def _send_daily_summary_async():
    """Асинхронная отправка ежедневной сводки"""
    try:
        async with get_async_session() as session:
            yesterday = (datetime.utcnow() - timedelta(days=1)).date()
            
            # Получаем статистику за вчера
            stats_result = await session.execute(
                "SELECT * FROM daily_stats WHERE stats_date = :date",
                {'date': yesterday}
            )
            stats = stats_result.fetchone()
            
            if not stats:
                return {"error": "No stats for yesterday"}
            
            # Формируем сообщение
            message = f"""
📊 <b>Ежедневная сводка за {yesterday.strftime('%d.%m.%Y')}</b>

👥 <b>Пользователи:</b>
• Новые: {stats.new_users}
• Активные: {stats.active_users}
• Premium покупки: {stats.premium_purchases}

📥 <b>Загрузки:</b>
• Всего: {stats.total_downloads}
• Успешно: {stats.successful_downloads}
• Ошибок: {stats.failed_downloads}
• Успешность: {(stats.successful_downloads / stats.total_downloads * 100) if stats.total_downloads > 0 else 0:.1f}%

🎬 <b>По платформам:</b>
• YouTube: {stats.youtube_downloads}
• TikTok: {stats.tiktok_downloads}
• Instagram: {stats.instagram_downloads}

💰 <b>Финансы:</b>
• Выручка: ${stats.revenue_usd:.2f}
• Платежи: {stats.successful_payments}/{stats.total_payments}

📊 <b>Система:</b>
• Файлов скачано: {stats.total_file_size_mb:.1f} МБ
• Ошибок: {stats.error_count}
"""
            
            from aiogram import Bot
            bot = Bot(token=settings.BOT_TOKEN)
            
            # Отправляем всем админам
            sent_count = 0
            for admin_id in settings.ADMIN_IDS:
                try:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode="HTML"
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send summary to admin {admin_id}: {e}")
            
            return {"sent_to_admins": sent_count}
            
    except Exception as e:
        logger.error(f"Error in daily summary: {e}")
        raise