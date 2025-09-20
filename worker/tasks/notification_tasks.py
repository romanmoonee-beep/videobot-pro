"""
VideoBot Pro - Notification Tasks (ИСПРАВЛЕННАЯ ВЕРСИЯ)
Задачи для отправки уведомлений пользователям
"""

import structlog
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from celery import current_task
from sqlalchemy import text

from worker.celery_app import celery_app
from worker.tasks.base import async_task_wrapper

logger = structlog.get_logger(__name__)

@celery_app.task(bind=True, name="notifications.send_download_completion")
def send_download_completion_notification(self, task_id: int):
    """
    Отправка уведомления о завершении загрузки
    
    Args:
        task_id: ID задачи загрузки
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_send_download_notification_async(task_id))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error sending download notification: {e}")
        raise

async def _send_download_notification_async(task_id: int):
    """Асинхронная отправка уведомления о загрузке"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            # Получаем информацию о задаче
            task_result = await session.execute(
                text("""
                SELECT dt.*, u.telegram_id, u.notification_settings
                FROM download_tasks dt
                JOIN users u ON dt.user_id = u.id
                WHERE dt.id = :task_id
                """),
                {'task_id': task_id}
            )
            task_data = task_result.fetchone()
            
            if not task_data:
                logger.warning(f"Download task {task_id} not found")
                return {"error": "Task not found"}
            
            # Проверяем настройки уведомлений пользователя
            notification_settings = getattr(task_data, 'notification_settings', {}) or {}
            if not notification_settings.get('download_complete', True):
                return {"skipped": "User disabled notifications"}
            
            # Формируем сообщение
            if getattr(task_data, 'status', None) == 'completed':
                message = await _format_success_message(task_data)
            else:
                message = await _format_error_message(task_data)
            
            # Имитация отправки уведомления
            logger.info(f"Would send notification to user {task_data.telegram_id}: {message}")
            
            # Обновляем флаг уведомления
            await session.execute(
                text("UPDATE download_tasks SET notification_sent = true WHERE id = :task_id"),
                {'task_id': task_id}
            )
            await session.commit()
            
            return {"sent": True, "user_id": task_data.telegram_id}
                
    except Exception as e:
        logger.error(f"Error in download notification: {e}")
        raise

async def _format_success_message(task_data) -> str:
    """Форматирование сообщения об успешной загрузке"""
    message_parts = [
        "✅ <b>Загрузка завершена!</b>",
        ""
    ]
    
    video_title = getattr(task_data, 'video_title', None)
    if video_title:
        title = video_title[:50] + "..." if len(video_title) > 50 else video_title
        message_parts.append(f"📝 <b>{title}</b>")
    
    platform = getattr(task_data, 'platform', None)
    if platform:
        platform_emoji = {"youtube": "🔴", "tiktok": "⚫", "instagram": "🟣"}.get(platform, "🎬")
        message_parts.append(f"{platform_emoji} Платформа: {platform.title()}")
    
    cdn_url = getattr(task_data, 'cdn_url', None)
    if cdn_url:
        message_parts.extend([
            "",
            "📥 Файл готов к скачиванию!"
        ])
    
    return "\n".join(message_parts)

async def _format_error_message(task_data) -> str:
    """Форматирование сообщения об ошибке"""
    message_parts = [
        "❌ <b>Ошибка загрузки</b>",
        ""
    ]
    
    platform = getattr(task_data, 'platform', None)
    if platform:
        platform_emoji = {"youtube": "🔴", "tiktok": "⚫", "instagram": "🟣"}.get(platform, "🎬")
        message_parts.append(f"{platform_emoji} Платформа: {platform.title()}")
    
    # Пользовательское сообщение об ошибке
    error_msg = _get_user_friendly_error(getattr(task_data, 'error_message', None) or "Неизвестная ошибка")
    message_parts.extend([
        f"💬 {error_msg}",
        "",
        "💡 <b>Попробуйте:</b>",
        "• Проверить ссылку в браузере",
        "• Попробовать другое качество",
        "• Повторить через несколько минут"
    ])
    
    return "\n".join(message_parts)

def _get_user_friendly_error(error_message: str) -> str:
    """Преобразование технической ошибки в понятную пользователю"""
    if not error_message:
        return "Техническая ошибка сервиса"
        
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

@celery_app.task(bind=True, name="notifications.send_batch_completion")
def send_batch_completion_notification(self, batch_id: int):
    """
    Отправка уведомления о завершении batch загрузки
    
    Args:
        batch_id: ID batch'а
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_send_batch_notification_async(batch_id))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error sending batch notification: {e}")
        raise

async def _send_batch_notification_async(batch_id: int):
    """Асинхронная отправка уведомления о batch"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            # Получаем информацию о batch
            batch_result = await session.execute(
                text("""
                SELECT db.*, u.telegram_id, u.notification_settings
                FROM download_batches db
                JOIN users u ON db.user_id = u.id
                WHERE db.id = :batch_id
                """),
                {'batch_id': batch_id}
            )
            batch_data = batch_result.fetchone()
            
            if not batch_data:
                logger.warning(f"Download batch {batch_id} not found")
                return {"error": "Batch not found"}
            
            # Проверяем настройки уведомлений
            notification_settings = getattr(batch_data, 'notification_settings', {}) or {}
            if not notification_settings.get('download_complete', True):
                return {"skipped": "User disabled notifications"}
            
            # Получаем статистику задач в batch
            tasks_stats = await session.execute(
                text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
                FROM download_tasks 
                WHERE batch_id = :batch_id
                """),
                {'batch_id': batch_id}
            )
            stats = tasks_stats.fetchone()
            
            # Формируем сообщение
            message = await _format_batch_message(batch_data, stats)
            
            # Имитация отправки уведомления
            logger.info(f"Would send batch notification to user {batch_data.telegram_id}: {message}")
            
            # Обновляем флаг уведомления
            await session.execute(
                text("UPDATE download_batches SET notification_sent = true WHERE id = :batch_id"),
                {'batch_id': batch_id}
            )
            await session.commit()
            
            return {"sent": True, "user_id": batch_data.telegram_id}
                
    except Exception as e:
        logger.error(f"Error in batch notification: {e}")
        raise

async def _format_batch_message(batch_data, stats) -> str:
    """Форматирование сообщения о batch"""
    total = getattr(stats, 'total', 0)
    completed = getattr(stats, 'completed', 0)
    failed = getattr(stats, 'failed', 0)
    
    success_rate = (completed / total * 100) if total > 0 else 0
    
    message_parts = [
        "🎉 <b>Групповая загрузка завершена!</b>",
        "",
        f"📊 Результат: {completed}/{total} файлов",
        f"📈 Успешность: {success_rate:.1f}%"
    ]
    
    if failed > 0:
        message_parts.append(f"❌ Ошибок: {failed}")
    
    archive_url = getattr(batch_data, 'archive_url', None)
    if archive_url:
        message_parts.extend([
            "",
            "📦 Файлы упакованы в архив"
        ])
    
    return "\n".join(message_parts)

@celery_app.task(bind=True, name="notifications.send_premium_expiry_warning")
def send_premium_expiry_warning(self, user_id: int, days_remaining: int):
    """
    Отправка предупреждения об истечении Premium
    
    Args:
        user_id: ID пользователя
        days_remaining: Дней до истечения
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_send_premium_warning_async(user_id, days_remaining))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error sending premium warning: {e}")
        raise

async def _send_premium_warning_async(user_id: int, days_remaining: int):
    """Асинхронная отправка предупреждения о Premium"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            user_result = await session.execute(
                text("SELECT * FROM users WHERE id = :user_id"),
                {'user_id': user_id}
            )
            user = user_result.fetchone()
            
            if not user or not getattr(user, 'is_premium', False):
                return {"error": "User not found or not premium"}
            
            # Проверяем настройки уведомлений
            notification_settings = getattr(user, 'notification_settings', {}) or {}
            if not notification_settings.get('premium_expiry', True):
                return {"skipped": "User disabled notifications"}
            
            # Формируем сообщение
            if days_remaining > 1:
                message = f"""
⏰ <b>Premium скоро закончится!</b>

📅 Осталось дней: {days_remaining}

💎 <b>Что вы потеряете:</b>
• Безлимитные скачивания
• 4K качество
• Приоритетная обработка
• Хранение файлов 30 дней
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
            
            # Имитация отправки уведомления
            logger.info(f"Would send premium warning to user {user.telegram_id}: {message}")
            
            return {"sent": True, "user_id": user.telegram_id}
                
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_send_broadcast_async(broadcast_id, user_ids, test_mode))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error sending broadcast: {e}")
        raise

async def _send_broadcast_async(broadcast_id: int, user_ids: List[int], test_mode: bool):
    """Асинхронная отправка рассылки"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            # Получаем рассылку
            broadcast_result = await session.execute(
                text("SELECT * FROM broadcast_messages WHERE id = :broadcast_id"),
                {'broadcast_id': broadcast_id}
            )
            broadcast = broadcast_result.fetchone()
            
            if not broadcast:
                return {"error": "Broadcast not found"}
            
            # Получаем список пользователей
            if test_mode:
                # Тестовый режим - только админы
                target_users = [123456789]  # Example admin ID
            elif user_ids:
                target_users = user_ids
            else:
                # Получаем пользователей по фильтру рассылки
                target_users = await _get_broadcast_target_users(session, broadcast)
            
            if not target_users:
                return {"error": "No target users found"}
            
            # Обновляем статус рассылки
            await session.execute(
                text("""
                UPDATE broadcast_messages 
                SET status = 'sending', started_at = :now, total_recipients = :total
                WHERE id = :broadcast_id
                """),
                {
                    'now': datetime.utcnow(),
                    'total': len(target_users),
                    'broadcast_id': broadcast_id
                }
            )
            await session.commit()
            
            # Имитация отправки сообщений
            sent_count = len(target_users)
            failed_count = 0
            blocked_count = 0
            
            logger.info(f"Would send broadcast to {sent_count} users")
            
            # Обновляем статистику рассылки
            await session.execute(
                text("""
                UPDATE broadcast_messages 
                SET status = 'completed', completed_at = :now,
                    sent_count = :sent, failed_count = :failed, blocked_count = :blocked
                WHERE id = :broadcast_id
                """),
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
        logger.error(f"Error in broadcast sending: {e}")
        raise

async def _get_broadcast_target_users(session, broadcast) -> List[int]:
    """Получить список пользователей для рассылки"""
    try:
        result = await session.execute(text("""
            SELECT telegram_id FROM users 
            WHERE is_deleted = false AND is_banned = false
            LIMIT 100
        """))
        
        return [row[0] for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Error getting broadcast targets: {e}")
        return []

@celery_app.task(bind=True, name="notifications.check_premium_expiry")
def check_premium_expiry_notifications(self):
    """Проверка и отправка уведомлений об истечении Premium"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_check_premium_expiry_async())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error checking premium expiry: {e}")
        raise

async def _check_premium_expiry_async():
    """Асинхронная проверка истечения Premium"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            # Пользователи с истекающим Premium (7, 3, 1 день)
            warning_days = [7, 3, 1]
            notifications_sent = 0
            
            for days in warning_days:
                target_date = datetime.utcnow() + timedelta(days=days)
                
                users_result = await session.execute(
                    text("""
                    SELECT id, telegram_id, premium_expires_at 
                    FROM users 
                    WHERE is_premium = true 
                    AND DATE(premium_expires_at) = :target_date
                    """),
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