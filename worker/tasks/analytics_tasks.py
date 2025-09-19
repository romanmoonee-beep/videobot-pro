"""
VideoBot Pro - Analytics Tasks
Задачи для обработки аналитики и метрик
"""

import structlog
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from celery import current_task

from worker.celery_app import celery_app
from shared.config.database import get_async_session
from shared.models import (
    AnalyticsEvent, DailyStats, User, DownloadTask, DownloadBatch, 
    Payment, EventType
)
from shared.models.analytics import track_user_event, track_system_event

logger = structlog.get_logger(__name__)

@celery_app.task(bind=True, name="analytics.process_events")
def process_analytics_events(self, batch_size: int = 1000):
    """
    Обработка необработанных аналитических событий
    
    Args:
        batch_size: Размер батча для обработки
    """
    try:
        import asyncio
        return asyncio.run(_process_analytics_events_async(batch_size))
    except Exception as e:
        logger.error(f"Error processing analytics events: {e}")
        raise

async def _process_analytics_events_async(batch_size: int):
    """Асинхронная обработка аналитических событий"""
    try:
        async with get_async_session() as session:
            # Получаем необработанные события
            result = await session.execute(
                """
                SELECT * FROM analytics_events 
                WHERE is_processed = false 
                ORDER BY created_at ASC 
                LIMIT :batch_size
                """,
                {'batch_size': batch_size}
            )
            events = result.fetchall()
            
            if not events:
                logger.info("No unprocessed analytics events found")
                return {"processed": 0}
            
            processed_count = 0
            
            for event in events:
                try:
                    # Обновляем агрегированную статистику
                    await _update_daily_stats(session, event)
                    
                    # Помечаем как обработанное
                    await session.execute(
                        """
                        UPDATE analytics_events 
                        SET is_processed = true, processed_at = :now 
                        WHERE id = :event_id
                        """,
                        {'now': datetime.utcnow(), 'event_id': event.id}
                    )
                    
                    processed_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing event {event.id}: {e}")
                    continue
            
            await session.commit()
            
            logger.info(f"Processed {processed_count} analytics events")
            return {"processed": processed_count}
            
    except Exception as e:
        logger.error(f"Error in analytics processing: {e}")
        raise

async def _update_daily_stats(session, event):
    """Обновить ежедневную статистику на основе события"""
    event_date = event.event_date
    
    # Получаем или создаем запись статистики за день
    daily_stats = await session.execute(
        "SELECT * FROM daily_stats WHERE stats_date = :date",
        {'date': event_date}
    )
    stats = daily_stats.fetchone()
    
    if not stats:
        # Создаем новую запись
        await session.execute(
            """
            INSERT INTO daily_stats (stats_date) 
            VALUES (:date)
            """,
            {'date': event_date}
        )
        await session.flush()
        
        stats = await session.execute(
            "SELECT * FROM daily_stats WHERE stats_date = :date",
            {'date': event_date}
        )
        stats = stats.fetchone()
    
    # Обновляем метрики в зависимости от типа события
    updates = {}
    
    if event.event_type == EventType.USER_REGISTERED:
        updates['new_users'] = (stats.new_users or 0) + 1
        
    elif event.event_type == EventType.USER_TRIAL_STARTED:
        updates['trial_users_started'] = (stats.trial_users_started or 0) + 1
        
    elif event.event_type == EventType.USER_PREMIUM_PURCHASED:
        updates['premium_purchases'] = (stats.premium_purchases or 0) + 1
        
    elif event.event_type == EventType.DOWNLOAD_STARTED:
        updates['total_downloads'] = (stats.total_downloads or 0) + 1
        
    elif event.event_type == EventType.DOWNLOAD_COMPLETED:
        updates['successful_downloads'] = (stats.successful_downloads or 0) + 1
        
        # Обновляем статистику по платформам
        if event.platform == 'youtube':
            updates['youtube_downloads'] = (stats.youtube_downloads or 0) + 1
        elif event.platform == 'tiktok':
            updates['tiktok_downloads'] = (stats.tiktok_downloads or 0) + 1
        elif event.platform == 'instagram':
            updates['instagram_downloads'] = (stats.instagram_downloads or 0) + 1
            
        # Добавляем размер файла
        if event.value:  # value = file_size_mb
            updates['total_file_size_mb'] = (stats.total_file_size_mb or 0) + event.value
            
    elif event.event_type == EventType.DOWNLOAD_FAILED:
        updates['failed_downloads'] = (stats.failed_downloads or 0) + 1
        
    elif event.event_type == EventType.BATCH_CREATED:
        updates['batches_created'] = (stats.batches_created or 0) + 1
        
    elif event.event_type == EventType.PAYMENT_COMPLETED:
        updates['successful_payments'] = (stats.successful_payments or 0) + 1
        if event.value:  # value = payment_amount
            updates['revenue_usd'] = (stats.revenue_usd or 0) + event.value
            
    elif event.event_type == EventType.PAYMENT_INITIATED:
        updates['total_payments'] = (stats.total_payments or 0) + 1
        
    elif event.event_type == EventType.ERROR_OCCURRED:
        updates['error_count'] = (stats.error_count or 0) + 1
    
    # Применяем обновления
    if updates:
        set_clause = ", ".join([f"{key} = :{key}" for key in updates.keys()])
        query = f"""
            UPDATE daily_stats 
            SET {set_clause}
            WHERE stats_date = :date
        """
        updates['date'] = event_date
        await session.execute(query, updates)

@celery_app.task(bind=True, name="analytics.calculate_daily_stats")
def calculate_daily_stats(self, target_date: str = None):
    """
    Пересчет ежедневной статистики за конкретный день
    
    Args:
        target_date: Дата в формате YYYY-MM-DD (по умолчанию вчера)
    """
    try:
        import asyncio
        return asyncio.run(_calculate_daily_stats_async(target_date))
    except Exception as e:
        logger.error(f"Error calculating daily stats: {e}")
        raise

async def _calculate_daily_stats_async(target_date: str = None):
    """Асинхронный пересчет ежедневной статистики"""
    try:
        if target_date:
            calc_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        else:
            calc_date = (datetime.utcnow() - timedelta(days=1)).date()
        
        async with get_async_session() as session:
            # Пересчитываем все метрики за день
            stats = {}
            
            # Новые пользователи
            new_users = await session.execute(
                """
                SELECT COUNT(*) FROM users 
                WHERE DATE(created_at) = :date
                """,
                {'date': calc_date}
            )
            stats['new_users'] = new_users.scalar() or 0
            
            # Активные пользователи
            active_users = await session.execute(
                """
                SELECT COUNT(DISTINCT user_id) FROM analytics_events 
                WHERE event_date = :date
                """,
                {'date': calc_date}
            )
            stats['active_users'] = active_users.scalar() or 0
            
            # Скачивания
            downloads = await session.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                    COUNT(CASE WHEN platform = 'youtube' AND status = 'completed' THEN 1 END) as youtube,
                    COUNT(CASE WHEN platform = 'tiktok' AND status = 'completed' THEN 1 END) as tiktok,
                    COUNT(CASE WHEN platform = 'instagram' AND status = 'completed' THEN 1 END) as instagram,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN file_size_bytes/1024/1024 END), 0) as total_size_mb
                FROM download_tasks 
                WHERE DATE(created_at) = :date
                """,
                {'date': calc_date}
            )
            download_stats = downloads.fetchone()
            
            stats.update({
                'total_downloads': download_stats.total or 0,
                'successful_downloads': download_stats.successful or 0,
                'failed_downloads': download_stats.failed or 0,
                'youtube_downloads': download_stats.youtube or 0,
                'tiktok_downloads': download_stats.tiktok or 0,
                'instagram_downloads': download_stats.instagram or 0,
                'total_file_size_mb': float(download_stats.total_size_mb or 0)
            })
            
            # Batch'и
            batches = await session.execute(
                """
                SELECT COUNT(*) FROM download_batches 
                WHERE DATE(created_at) = :date
                """,
                {'date': calc_date}
            )
            stats['batches_created'] = batches.scalar() or 0
            
            # Платежи
            payments = await session.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                    COALESCE(SUM(CASE WHEN status = 'completed' THEN amount END), 0) as revenue
                FROM payments 
                WHERE DATE(created_at) = :date
                """,
                {'date': calc_date}
            )
            payment_stats = payments.fetchone()
            
            stats.update({
                'total_payments': payment_stats.total or 0,
                'successful_payments': payment_stats.successful or 0,
                'revenue_usd': float(payment_stats.revenue or 0)
            })
            
            # Trial и Premium
            trial_stats = await session.execute(
                """
                SELECT COUNT(*) FROM analytics_events 
                WHERE event_date = :date AND event_type = 'user_trial_started'
                """,
                {'date': calc_date}
            )
            stats['trial_users_started'] = trial_stats.scalar() or 0
            
            premium_stats = await session.execute(
                """
                SELECT COUNT(*) FROM analytics_events 
                WHERE event_date = :date AND event_type = 'user_premium_purchased'
                """,
                {'date': calc_date}
            )
            stats['premium_purchases'] = premium_stats.scalar() or 0
            
            # Ошибки
            errors = await session.execute(
                """
                SELECT COUNT(*) FROM analytics_events 
                WHERE event_date = :date AND event_type = 'error_occurred'
                """,
                {'date': calc_date}
            )
            stats['error_count'] = errors.scalar() or 0
            
            # Обновляем или создаем запись
            existing = await session.execute(
                "SELECT id FROM daily_stats WHERE stats_date = :date",
                {'date': calc_date}
            )
            
            if existing.fetchone():
                # Обновляем существующую
                set_clause = ", ".join([f"{key} = :{key}" for key in stats.keys()])
                query = f"""
                    UPDATE daily_stats 
                    SET {set_clause}
                    WHERE stats_date = :stats_date
                """
                stats['stats_date'] = calc_date
                await session.execute(query, stats)
            else:
                # Создаем новую
                columns = list(stats.keys()) + ['stats_date']
                values = [f":{col}" for col in columns]
                query = f"""
                    INSERT INTO daily_stats ({', '.join(columns)}) 
                    VALUES ({', '.join(values)})
                """
                stats['stats_date'] = calc_date
                await session.execute(query, stats)
            
            await session.commit()
            
            logger.info(f"Calculated daily stats for {calc_date}: {stats}")
            return {"date": calc_date.isoformat(), "stats": stats}
            
    except Exception as e:
        logger.error(f"Error calculating daily stats: {e}")
        raise

@celery_app.task(bind=True, name="analytics.cleanup_old_events")
def cleanup_old_analytics_events(self, days_old: int = 90):
    """
    Очистка старых аналитических событий
    
    Args:
        days_old: Возраст событий в днях для удаления
    """
    try:
        import asyncio
        return asyncio.run(_cleanup_old_events_async(days_old))
    except Exception as e:
        logger.error(f"Error cleaning up analytics events: {e}")
        raise

async def _cleanup_old_events_async(days_old: int):
    """Асинхронная очистка старых событий"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        async with get_async_session() as session:
            # Удаляем старые обработанные события
            result = await session.execute(
                """
                DELETE FROM analytics_events 
                WHERE created_at < :cutoff_date 
                AND is_processed = true
                """,
                {'cutoff_date': cutoff_date}
            )
            
            deleted_count = result.rowcount
            await session.commit()
            
            logger.info(f"Deleted {deleted_count} old analytics events")
            return {"deleted": deleted_count, "cutoff_date": cutoff_date.isoformat()}
            
    except Exception as e:
        logger.error(f"Error cleaning up old events: {e}")
        raise

@celery_app.task(bind=True, name="analytics.generate_user_report")
def generate_user_analytics_report(self, user_id: int, days: int = 30):
    """
    Генерация аналитического отчета по пользователю
    
    Args:
        user_id: ID пользователя
        days: Количество дней для анализа
    """
    try:
        import asyncio
        return asyncio.run(_generate_user_report_async(user_id, days))
    except Exception as e:
        logger.error(f"Error generating user report: {e}")
        raise

async def _generate_user_report_async(user_id: int, days: int):
    """Асинхронная генерация отчета по пользователю"""
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_async_session() as session:
            # Основная информация о пользователе
            user_info = await session.execute(
                "SELECT * FROM users WHERE id = :user_id",
                {'user_id': user_id}
            )
            user = user_info.fetchone()
            
            if not user:
                return {"error": "User not found"}
            
            # События пользователя
            events = await session.execute(
                """
                SELECT event_type, COUNT(*) as count
                FROM analytics_events 
                WHERE user_id = :user_id 
                AND created_at >= :start_date
                GROUP BY event_type
                ORDER BY count DESC
                """,
                {'user_id': user_id, 'start_date': start_date}
            )
            
            # Загрузки пользователя
            downloads = await session.execute(
                """
                SELECT 
                    platform,
                    status,
                    COUNT(*) as count,
                    COALESCE(SUM(file_size_bytes)/1024/1024, 0) as total_size_mb
                FROM download_tasks 
                WHERE user_id = :user_id 
                AND created_at >= :start_date
                GROUP BY platform, status
                """,
                {'user_id': user_id, 'start_date': start_date}
            )
            
            # Платежи пользователя
            payments = await session.execute(
                """
                SELECT 
                    status,
                    COUNT(*) as count,
                    COALESCE(SUM(amount), 0) as total_amount
                FROM payments 
                WHERE user_id = :user_id 
                AND created_at >= :start_date
                GROUP BY status
                """,
                {'user_id': user_id, 'start_date': start_date}
            )
            
            report = {
                'user': {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'username': user.username,
                    'user_type': user.user_type,
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'last_active_at': user.last_active_at.isoformat() if user.last_active_at else None
                },
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': datetime.utcnow().isoformat(),
                    'days': days
                },
                'events': [
                    {'type': row.event_type, 'count': row.count}
                    for row in events.fetchall()
                ],
                'downloads': [
                    {
                        'platform': row.platform,
                        'status': row.status,
                        'count': row.count,
                        'total_size_mb': float(row.total_size_mb)
                    }
                    for row in downloads.fetchall()
                ],
                'payments': [
                    {
                        'status': row.status,
                        'count': row.count,
                        'total_amount': float(row.total_amount)
                    }
                    for row in payments.fetchall()
                ]
            }
            
            return report
            
    except Exception as e:
        logger.error(f"Error generating user report: {e}")
        raise

@celery_app.task(bind=True, name="analytics.update_user_activity")
def update_user_activity_stats(self):
    """Обновление статистики активности пользователей"""
    try:
        import asyncio
        return asyncio.run(_update_activity_stats_async())
    except Exception as e:
        logger.error(f"Error updating user activity stats: {e}")
        raise

async def _update_activity_stats_async():
    """Асинхронное обновление статистики активности"""
    try:
        async with get_async_session() as session:
            # Обновляем активных пользователей за сегодня
            today = datetime.utcnow().date()
            
            active_count = await session.execute(
                """
                SELECT COUNT(DISTINCT user_id) 
                FROM analytics_events 
                WHERE event_date = :today
                """,
                {'today': today}
            )
            
            # Обновляем в daily_stats
            await session.execute(
                """
                UPDATE daily_stats 
                SET active_users = :count 
                WHERE stats_date = :today
                """,
                {'count': active_count.scalar() or 0, 'today': today}
            )
            
            await session.commit()
            
            return {"active_users_today": active_count.scalar() or 0}
            
    except Exception as e:
        logger.error(f"Error updating activity stats: {e}")
        raise

# Периодические задачи для автоматического запуска
@celery_app.task(bind=True, name="analytics.hourly_processing")
def hourly_analytics_processing(self):
    """Ежечасная обработка аналитики"""
    try:
        # Обрабатываем события
        process_analytics_events.delay(batch_size=5000)
        
        # Обновляем активность пользователей
        update_user_activity_stats.delay()
        
        return {"status": "scheduled"}
        
    except Exception as e:
        logger.error(f"Error in hourly processing: {e}")
        raise

@celery_app.task(bind=True, name="analytics.daily_calculation")
def daily_stats_calculation(self):
    """Ежедневный пересчет статистики"""
    try:
        # Пересчитываем статистику за вчера
        yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
        calculate_daily_stats.delay(target_date=yesterday)
        
        # Очищаем старые события (раз в день)
        cleanup_old_analytics_events.delay(days_old=90)
        
        return {"status": "scheduled"}
        
    except Exception as e:
        logger.error(f"Error in daily calculation: {e}")
        raise