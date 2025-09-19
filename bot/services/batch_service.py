"""
VideoBot Pro - Batch Service
Сервис для управления групповыми загрузками
"""

import structlog
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from uuid import uuid4
import asyncio
from sqlalchemy import text

from shared.config.database import get_async_session
from shared.models import User, DownloadBatch, DownloadTask, Platform, EventType
from shared.models.analytics import BatchStatus
from shared.models.analytics import track_download_event
from bot.utils.url_extractor import (
    extract_video_urls,
    validate_url,
    detect_platform,
    batch_validate_urls,
    group_urls_by_platform
)
from bot.config import bot_config
from bot.services.download_service import download_service, DownloadError, LimitExceededError
from worker.tasks.batch_tasks import process_batch_download

logger = structlog.get_logger(__name__)

class BatchError(Exception):
    """Базовый класс для ошибок batch обработки"""
    pass

class BatchValidationError(BatchError):
    """Ошибка валидации batch"""
    pass

class BatchLimitError(BatchError):
    """Ошибка лимитов batch"""
    pass

class BatchService:
    """Сервис для управления групповыми загрузками"""
    
    def __init__(self):
        """Инициализация сервиса"""
        self.max_batch_size = bot_config.limits.max_batch_size
        self.batch_timeout = 3600  # 1 час на обработку batch'а
        self.auto_delivery_threshold = 4  # До 4 файлов - автоматически в чат
    
    async def create_batch_from_text(
        self,
        user: User,
        text: str,
        delivery_method: str = "auto"
    ) -> DownloadBatch:
        """
        Создать batch из текста с URL
        
        Args:
            user: Пользователь
            text: Текст с URL
            delivery_method: Способ доставки (auto/individual/archive/selective)
            
        Returns:
            Созданный batch
            
        Raises:
            BatchValidationError: Если URL невалидны
            BatchLimitError: Если превышены лимиты
        """
        # Извлекаем URL из текста
        urls = extract_video_urls(text)
        
        if not urls:
            raise BatchValidationError("Не найдено поддерживаемых URL")
        
        return await self.create_batch_from_urls(user, urls, delivery_method)
    
    async def create_batch_from_urls(
        self,
        user: User,
        urls: List[str],
        delivery_method: str = "auto",
        selected_indices: Optional[List[int]] = None
    ) -> DownloadBatch:
        """
        Создать batch из списка URL
        
        Args:
            user: Пользователь
            urls: Список URL
            delivery_method: Способ доставки
            selected_indices: Индексы выбранных URL (для selective)
            
        Returns:
            Созданный batch
        """
        # Проверяем лимиты
        await self._check_batch_limits(user, urls)
        
        # Валидируем URL
        valid_urls, invalid_urls = batch_validate_urls(urls)
        
        if not valid_urls:
            raise BatchValidationError("Все URL невалидны")
        
        # Фильтруем по выбранным индексам
        if selected_indices is not None:
            valid_urls = [valid_urls[i] for i in selected_indices if i < len(valid_urls)]
        
        # Определяем способ доставки
        if delivery_method == "auto":
            delivery_method = self._determine_delivery_method(len(valid_urls))
        
        try:
            async with get_async_session() as session:
                # Создаем batch
                batch = await self._create_batch_record(
                    session=session,
                    user=user,
                    urls=valid_urls,
                    delivery_method=delivery_method,
                    invalid_urls=invalid_urls
                )
                
                # Создаем задачи для каждого URL
                tasks = await self._create_batch_tasks(
                    session=session,
                    batch=batch,
                    user=user,
                    urls=valid_urls
                )
                
                await session.commit()
                
                # Аналитика
                await track_download_event(
                    event_type=EventType.BATCH_CREATED,
                    user_id=user.id,
                    platform="mixed",
                    value=len(valid_urls),
                    event_data={
                        'batch_id': batch.id,
                        'delivery_method': delivery_method,
                        'valid_urls_count': len(valid_urls),
                        'invalid_urls_count': len(invalid_urls),
                        'platforms': self._get_platform_stats(valid_urls)
                    }
                )
                
                logger.info(
                    "Batch created",
                    batch_id=batch.id,
                    user_id=user.telegram_id,
                    urls_count=len(valid_urls),
                    delivery_method=delivery_method
                )
                
                return batch
                
        except Exception as e:
            logger.error(f"Error creating batch: {e}")
            raise BatchError(f"Не удалось создать batch: {e}")
    
    async def start_batch_processing(self, batch: DownloadBatch) -> str:
        """
        Запустить обработку batch'а
        
        Args:
            batch: Batch для обработки
            
        Returns:
            ID Celery задачи
        """
        try:
            # Обновляем статус batch'а
            async with get_async_session() as session:
                db_batch = await session.get(DownloadBatch, batch.id)
                if db_batch:
                    db_batch.mark_as_processing()
                    await session.commit()
            
            # Запускаем Celery задачу
            celery_task = process_batch_download.delay(batch.id)
            
            # Сохраняем ID Celery задачи
            async with get_async_session() as session:
                db_batch = await session.get(DownloadBatch, batch.id)
                if db_batch:
                    db_batch.celery_task_id = celery_task.id
                    await session.commit()
            
            logger.info(
                "Batch processing started",
                batch_id=batch.id,
                celery_task_id=celery_task.id
            )
            
            return celery_task.id
            
        except Exception as e:
            logger.error(f"Error starting batch processing: {e}")
            
            # Помечаем batch как неудачный
            async with get_async_session() as session:
                db_batch = await session.get(DownloadBatch, batch.id)
                if db_batch:
                    db_batch.mark_as_failed(str(e))
                    await session.commit()
            
            raise BatchError(f"Не удалось запустить обработку: {e}")
    
    async def get_batch_status(self, batch_id: int) -> Dict[str, Any]:
        """
        Получить статус batch'а
        
        Args:
            batch_id: ID batch'а
            
        Returns:
            Статус batch'а
        """
        try:
            async with get_async_session() as session:
                batch = await session.get(DownloadBatch, batch_id)
                
                if not batch:
                    return {'error': 'Batch not found'}
                
                # Получаем статистику задач
                task_stats = await self._get_batch_task_stats(session, batch_id)
                
                result = {
                    'batch_id': batch.id,
                    'batch_uuid': batch.batch_id,
                    'status': batch.status,
                    'user_id': batch.telegram_user_id,
                    'total_urls': batch.total_urls,
                    'delivery_method': batch.delivery_method,
                    'created_at': batch.created_at.isoformat(),
                    'expires_at': batch.expires_at.isoformat() if batch.expires_at else None,
                    **task_stats
                }
                
                # Дополнительные поля в зависимости от статуса
                if batch.status == BatchStatus.COMPLETED:
                    result.update({
                        'completed_at': batch.completed_at.isoformat() if batch.completed_at else None,
                        'archive_url': batch.archive_url,
                        'total_size_mb': batch.total_size_mb,
                        'processing_time_seconds': batch.processing_time_seconds
                    })
                elif batch.status == BatchStatus.FAILED:
                    result.update({
                        'error': batch.error_message,
                        'failed_at': batch.failed_at.isoformat() if batch.failed_at else None
                    })
                elif batch.status == BatchStatus.PROCESSING:
                    result.update({
                        'started_at': batch.started_at.isoformat() if batch.started_at else None,
                        'progress_percentage': self._calculate_batch_progress(task_stats),
                        'estimated_completion': self._estimate_completion_time(batch, task_stats)
                    })
                
                return result
                
        except Exception as e:
            logger.error(f"Error getting batch status: {e}")
            return {'error': str(e)}
    
    async def cancel_batch(self, batch_id: int, user_id: int) -> bool:
        """
        Отменить обработку batch'а
        
        Args:
            batch_id: ID batch'а
            user_id: ID пользователя
            
        Returns:
            True если успешно отменен
        """
        try:
            async with get_async_session() as session:
                batch = await session.get(DownloadBatch, batch_id)
                
                if not batch:
                    return False
                
                # Проверяем права на отмену
                if batch.user_id != user_id and not bot_config.is_admin(user_id):
                    return False
                
                # Отменяем только если batch еще не завершен
                if batch.status in [BatchStatus.PENDING, BatchStatus.PROCESSING]:
                    # Отменяем Celery задачу
                    if batch.celery_task_id:
                        from worker.celery_app import celery_app
                        celery_app.control.revoke(batch.celery_task_id, terminate=True)
                    
                    # Отменяем все связанные задачи
                    await session.execute(
                        text("""
                        UPDATE download_tasks 
                        SET status = 'cancelled', cancelled_at = NOW()
                        WHERE batch_id = :batch_id AND status IN ('pending', 'processing')
                        """),
                        {'batch_id': batch_id}
                    )
                    
                    # Обновляем статус batch'а
                    batch.mark_as_cancelled()
                    await session.commit()
                    
                    logger.info(f"Batch cancelled", batch_id=batch_id, user_id=user_id)
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling batch: {e}")
            return False
    
    async def get_user_batches(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        status: Optional[BatchStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить batch'и пользователя
        
        Args:
            user_id: ID пользователя
            limit: Лимит записей
            offset: Смещение
            status: Фильтр по статусу
            
        Returns:
            Список batch'ей
        """
        try:
            async with get_async_session() as session:
                query = """
                    SELECT 
                        id, batch_id, status, total_urls, delivery_method,
                        created_at, completed_at, total_size_mb
                    FROM download_batches 
                    WHERE user_id = :user_id
                """
                params = {'user_id': user_id}
                
                if status:
                    query += " AND status = :status"
                    params['status'] = status.value
                
                query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                params.update({'limit': limit, 'offset': offset})
                
                result = await session.execute(text(query), params)
                batches = result.fetchall()
                
                batch_list = []
                for batch in batches:
                    # Получаем статистику задач для каждого batch'а
                    task_stats = await self._get_batch_task_stats(session, batch.id)
                    
                    batch_list.append({
                        'batch_id': batch.id,
                        'batch_uuid': batch.batch_id,
                        'status': batch.status,
                        'total_urls': batch.total_urls,
                        'delivery_method': batch.delivery_method,
                        'created_at': batch.created_at.isoformat(),
                        'completed_at': batch.completed_at.isoformat() if batch.completed_at else None,
                        'total_size_mb': batch.total_size_mb,
                        **task_stats
                    })
                
                return batch_list
                
        except Exception as e:
            logger.error(f"Error getting user batches: {e}")
            return []
    
    async def retry_failed_batch(self, batch_id: int) -> bool:
        """
        Повторить неудачный batch
        
        Args:
            batch_id: ID batch'а
            
        Returns:
            True если повтор запущен успешно
        """
        try:
            async with get_async_session() as session:
                batch = await session.get(DownloadBatch, batch_id)
                
                if not batch or batch.status != BatchStatus.FAILED:
                    return False
                
                # Сбрасываем статус batch'а и задач
                batch.status = BatchStatus.PENDING
                batch.error_message = None
                batch.failed_at = None
                batch.retry_count = (batch.retry_count or 0) + 1
                
                # Сбрасываем неудачные задачи
                await session.execute(
                    text("""
                    UPDATE download_tasks 
                    SET status = 'pending', error_message = NULL, failed_at = NULL,
                        retry_count = retry_count + 1
                    WHERE batch_id = :batch_id AND status = 'failed'
                    """),
                    {'batch_id': batch_id}
                )
                
                await session.commit()
                
                # Запускаем повторно
                celery_task_id = await self.start_batch_processing(batch)
                
                logger.info(
                    f"Batch retry started",
                    batch_id=batch_id,
                    retry_count=batch.retry_count,
                    celery_task_id=celery_task_id
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Error retrying batch: {e}")
            return False
    
    async def cleanup_expired_batches(self) -> int:
        """
        Очистка истекших batch'ей
        
        Returns:
            Количество очищенных batch'ей
        """
        try:
            async with get_async_session() as session:
                # Помечаем истекшие batch'и как expired
                result = await session.execute(
                    text("""
                    UPDATE download_batches 
                    SET status = 'expired'
                    WHERE expires_at < NOW() 
                    AND status NOT IN ('completed', 'failed', 'cancelled', 'expired')
                    """)
                )
                
                expired_count = result.rowcount
                
                # Удаляем старые истекшие batch'и (старше 30 дней)
                old_cutoff = datetime.utcnow() - timedelta(days=30)
                await session.execute(
                    text("""
                    DELETE FROM download_batches 
                    WHERE status = 'expired' AND created_at < :cutoff
                    """),
                    {'cutoff': old_cutoff}
                )
                
                await session.commit()
                
                if expired_count > 0:
                    logger.info(f"Expired {expired_count} batch(es)")
                
                return expired_count
                
        except Exception as e:
            logger.error(f"Error cleaning up expired batches: {e}")
            return 0
    
    # Вспомогательные методы
    
    async def _check_batch_limits(self, user: User, urls: List[str]):
        """Проверка лимитов batch'а"""
        # Проверяем максимальный размер batch'а
        if len(urls) > self.max_batch_size:
            raise BatchLimitError(
                f"Максимум {self.max_batch_size} URL за раз. Получено: {len(urls)}"
            )
        
        # Проверяем дневной лимит пользователя
        daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
        if daily_limit < 999:  # Не безлимитный
            remaining = daily_limit - user.downloads_today
            if remaining < len(urls):
                raise BatchLimitError(
                    f"Недостаточно дневных загрузок. Осталось: {remaining}, требуется: {len(urls)}"
                )
    
    def _determine_delivery_method(self, urls_count: int) -> str:
        """Определить оптимальный способ доставки"""
        if urls_count <= self.auto_delivery_threshold:
            return "individual"  # Автоматически в чат
        else:
            return "ask"  # Спросить у пользователя
    
    async def _create_batch_record(
        self,
        session,
        user: User,
        urls: List[str],
        delivery_method: str,
        invalid_urls: List[str]
    ) -> DownloadBatch:
        """Создать запись batch'а в БД"""
        batch_uuid = f"batch_{uuid4().hex[:12]}"
        
        # Определяем время истечения
        retention_hours = 24  # По умолчанию
        if user.current_user_type == "premium":
            retention_hours = 24 * 30  # 30 дней
        elif user.current_user_type == "admin":
            retention_hours = 24 * 365  # 365 дней
        
        expires_at = datetime.utcnow() + timedelta(hours=retention_hours)
        
        batch = DownloadBatch(
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            batch_id=batch_uuid,
            urls=urls,
            total_urls=len(urls),
            invalid_urls=invalid_urls,
            delivery_method=delivery_method,
            send_to_chat=(delivery_method == "individual"),
            create_archive=(delivery_method == "archive"),
            expires_at=expires_at,
            status=BatchStatus.PENDING,
            priority=10 if user.current_user_type == "admin" else 5
        )
        
        session.add(batch)
        await session.flush()  # Получаем ID
        
        return batch
    
    async def _create_batch_tasks(
        self,
        session,
        batch: DownloadBatch,
        user: User,
        urls: List[str]
    ) -> List[DownloadTask]:
        """Создать задачи для batch'а"""
        tasks = []
        
        for i, url in enumerate(urls):
            task = DownloadTask.create_from_url(
                url=url,
                user_id=user.id,
                telegram_user_id=user.telegram_id,
                batch_id=batch.id,
                order_in_batch=i,
                priority=batch.priority,
                send_to_chat=batch.send_to_chat
            )
            
            session.add(task)
            tasks.append(task)
        
        return tasks
    
    async def _get_batch_task_stats(self, session, batch_id: int) -> Dict[str, Any]:
        """Получить статистику задач batch'а"""
        result = await session.execute(
            text("""
            SELECT 
                status,
                COUNT(*) as count,
                COALESCE(SUM(file_size_bytes), 0) as total_size,
                COALESCE(AVG(duration_seconds), 0) as avg_duration
            FROM download_tasks 
            WHERE batch_id = :batch_id 
            GROUP BY status
            """),
            {'batch_id': batch_id}
        )
        
        stats = result.fetchall()
        
        task_stats = {
            'completed_tasks': 0,
            'failed_tasks': 0,
            'processing_tasks': 0,
            'pending_tasks': 0,
            'cancelled_tasks': 0,
            'total_size_bytes': 0,
            'avg_duration_seconds': 0
        }
        
        for stat in stats:
            status_key = f"{stat.status}_tasks"
            if status_key in task_stats:
                task_stats[status_key] = stat.count
            task_stats['total_size_bytes'] += stat.total_size
            task_stats['avg_duration_seconds'] = max(task_stats['avg_duration_seconds'], stat.avg_duration)
        
        return task_stats
    
    def _calculate_batch_progress(self, task_stats: Dict[str, Any]) -> float:
        """Рассчитать процент выполнения batch'а"""
        total_tasks = sum(
            task_stats[key] for key in task_stats.keys() 
            if key.endswith('_tasks')
        )
        
        if total_tasks == 0:
            return 0.0
        
        completed = task_stats['completed_tasks'] + task_stats['failed_tasks']
        return (completed / total_tasks) * 100
    
    def _estimate_completion_time(self, batch: DownloadBatch, task_stats: Dict[str, Any]) -> Optional[str]:
        """Оценить время завершения batch'а"""
        if not batch.started_at:
            return None
        
        progress = self._calculate_batch_progress(task_stats)
        if progress <= 0:
            return None
        
        elapsed = datetime.utcnow() - batch.started_at
        estimated_total = elapsed.total_seconds() * (100 / progress)
        estimated_remaining = estimated_total - elapsed.total_seconds()
        
        if estimated_remaining <= 0:
            return None
        
        completion_time = datetime.utcnow() + timedelta(seconds=estimated_remaining)
        return completion_time.isoformat()
    
    def _get_platform_stats(self, urls: List[str]) -> Dict[str, int]:
        """Получить статистику по платформам"""
        platform_stats = {}
        
        for url in urls:
            platform = detect_platform(url)
            platform_stats[platform] = platform_stats.get(platform, 0) + 1
        
        return platform_stats

# Глобальный экземпляр сервиса
batch_service = BatchService()