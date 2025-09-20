"""
VideoBot Pro - Analytics Tasks (ИСПРАВЛЕННАЯ ВЕРСИЯ)
Задачи для обработки аналитики и метрик
"""

import structlog
import asyncio
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from celery import current_task
from sqlalchemy import text

from worker.celery_app import celery_app
from worker.tasks.base import async_task_wrapper

logger = structlog.get_logger(__name__)

@celery_app.task(bind=True, name="analytics.process_events")
def process_analytics_events(self, batch_size: int = 1000):
    """
    Обработка необработанных аналитических событий
    
    Args:
        batch_size: Размер батча для обработки
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_process_analytics_events_async(batch_size))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error processing analytics events: {e}")
        raise

async def _process_analytics_events_async(batch_size: int):
    """Асинхронная обработка аналитических событий"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            # Получаем необработанные события
            result = await session.execute(
                text("""
                SELECT * FROM analytics_events 
                WHERE is_processed = false 
                ORDER BY created_at ASC 
                LIMIT :batch_size
                """),
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
                        text("""
                        UPDATE analytics_events 
                        SET is_processed = true, processed_at = :now 
                        WHERE id = :event_id
                        """),
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
    event_date = getattr(event, 'event_date', datetime.utcnow().date())
    
    # Получаем или создаем запись статистики за день
    daily_stats = await session.execute(
        text("SELECT * FROM daily_stats WHERE stats_date = :date"),
        {'date': event_date}
    )
    stats = daily_stats.fetchone()
    
    if not stats:
        # Создаем новую запись
        await session.execute(
            text("""
            INSERT INTO daily_stats (stats_date, new_users, total_downloads) 
            VALUES (:date, 0, 0)
            """),
            {'date': event_date}
        )
        await session.flush()

@celery_app.task(bind=True, name="analytics.calculate_daily_stats")
def calculate_daily_stats(self, target_date: str = None):
    """
    Пересчет ежедневной статистики за конкретный день
    
    Args:
        target_date: Дата в формате YYYY-MM-DD (по умолчанию вчера)
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_calculate_daily_stats_async(target_date))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error calculating daily stats: {e}")
        raise

async def _calculate_daily_stats_async(target_date: str = None):
    """Асинхронный пересчет ежедневной статистики"""
    try:
        from shared.config.database import get_async_session
        
        if target_date:
            calc_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        else:
            calc_date = (datetime.utcnow() - timedelta(days=1)).date()
        
        async with get_async_session() as session:
            # Пересчитываем все метрики за день
            stats = {}
            
            # Новые пользователи
            new_users = await session.execute(
                text("""
                SELECT COUNT(*) FROM users 
                WHERE DATE(created_at) = :date
                """),
                {'date': calc_date}
            )
            stats['new_users'] = new_users.scalar() or 0
            
            # Активные пользователи
            active_users = await session.execute(
                text("""
                SELECT COUNT(DISTINCT user_id) FROM analytics_events 
                WHERE DATE(created_at) = :date
                """),
                {'date': calc_date}
            )
            stats['active_users'] = active_users.scalar() or 0
            
            # Скачивания
            downloads = await session.execute(
                text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
                FROM download_tasks 
                WHERE DATE(created_at) = :date
                """),
                {'date': calc_date}
            )
            download_stats = downloads.fetchone()
            
            stats.update({
                'total_downloads': download_stats.total or 0,
                'successful_downloads': download_stats.successful or 0,
                'failed_downloads': download_stats.failed or 0
            })
            
            # Обновляем или создаем запись
            existing = await session.execute(
                text("SELECT id FROM daily_stats WHERE stats_date = :date"),
                {'date': calc_date}
            )
            
            if existing.fetchone():
                # Обновляем существующую
                await session.execute(text("""
                    UPDATE daily_stats 
                    SET new_users = :new_users,
                        active_users = :active_users,
                        total_downloads = :total_downloads,
                        successful_downloads = :successful_downloads,
                        failed_downloads = :failed_downloads
                    WHERE stats_date = :stats_date
                """), {**stats, 'stats_date': calc_date})
            else:
                # Создаем новую
                await session.execute(text("""
                    INSERT INTO daily_stats (stats_date, new_users, active_users, 
                                           total_downloads, successful_downloads, failed_downloads) 
                    VALUES (:stats_date, :new_users, :active_users, 
                           :total_downloads, :successful_downloads, :failed_downloads)
                """), {**stats, 'stats_date': calc_date})
            
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_cleanup_old_events_async(days_old))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error cleaning up analytics events: {e}")
        raise

async def _cleanup_old_events_async(days_old: int):
    """Асинхронная очистка старых событий"""
    try:
        from shared.config.database import get_async_session
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        async with get_async_session() as session:
            # Удаляем старые обработанные события
            result = await session.execute(
                text("""
                DELETE FROM analytics_events 
                WHERE created_at < :cutoff_date 
                AND is_processed = true
                """),
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_generate_user_report_async(user_id, days))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error generating user report: {e}")
        raise

async def _generate_user_report_async(user_id: int, days: int):
    """Асинхронная генерация отчета по пользователю"""
    try:
        from shared.config.database import get_async_session
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_async_session() as session:
            # Основная информация о пользователе
            user_info = await session.execute(
                text("SELECT * FROM users WHERE id = :user_id"),
                {'user_id': user_id}
            )
            user = user_info.fetchone()
            
            if not user:
                return {"error": "User not found"}
            
            # События пользователя
            events = await session.execute(
                text("""
                SELECT event_type, COUNT(*) as count
                FROM analytics_events 
                WHERE user_id = :user_id 
                AND created_at >= :start_date
                GROUP BY event_type
                ORDER BY count DESC
                """),
                {'user_id': user_id, 'start_date': start_date}
            )
            
            # Загрузки пользователя
            downloads = await session.execute(
                text("""
                SELECT 
                    platform,
                    status,
                    COUNT(*) as count
                FROM download_tasks 
                WHERE user_id = :user_id 
                AND created_at >= :start_date
                GROUP BY platform, status
                """),
                {'user_id': user_id, 'start_date': start_date}
            )
            
            report = {
                'user': {
                    'id': user.id,
                    'telegram_id': getattr(user, 'telegram_id', None),
                    'username': getattr(user, 'username', None),
                    'user_type': getattr(user, 'user_type', 'free'),
                    'created_at': getattr(user, 'created_at', datetime.utcnow()).isoformat()
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
                        'count': row.count
                    }
                    for row in downloads.fetchall()
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_update_activity_stats_async())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Error updating user activity stats: {e}")
        raise

async def _update_activity_stats_async():
    """Асинхронное обновление статистики активности"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            # Обновляем активных пользователей за сегодня
            today = datetime.utcnow().date()
            
            active_count = await session.execute(
                text("""
                SELECT COUNT(DISTINCT user_id) 
                FROM analytics_events 
                WHERE DATE(created_at) = :today
                """),
                {'today': today}
            )
            
            # Обновляем в daily_stats
            await session.execute(
                text("""
                UPDATE daily_stats 
                SET active_users = :count 
                WHERE stats_date = :today
                """),
                {'count': active_count.scalar() or 0, 'today': today}
            )
            
            await session.commit()
            
            return {"active_users_today": active_count.scalar() or 0}
            
    except Exception as e:
        logger.error(f"Error updating activity stats: {e}")
        raise

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