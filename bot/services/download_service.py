"""
VideoBot Pro - Download Service
Сервис для управления загрузками видео
"""

import structlog
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from sqlalchemy import text

from shared.config.database import get_async_session
from shared.models import User, DownloadTask, DownloadBatch, Platform, EventType
from shared.models.analytics import track_download_event
from worker.utils.progress_tracker import TaskStatus
from bot.utils.url_extractor import (
    validate_url, 
    detect_platform, 
    extract_video_id,
    normalize_url
)
from bot.config import bot_config
from worker.tasks.download_tasks import process_single_download

logger = structlog.get_logger(__name__)

class DownloadError(Exception):
    """Базовый класс для ошибок загрузки"""
    pass

class ValidationError(DownloadError):
    """Ошибка валидации URL"""
    pass

class LimitExceededError(DownloadError):
    """Ошибка превышения лимитов"""
    pass

class PlatformError(DownloadError):
    """Ошибка платформы"""
    pass

class DownloadService:
    """Сервис для управления загрузками"""
    
    def __init__(self):
        """Инициализация сервиса"""
        self.supported_platforms = ['youtube', 'tiktok', 'instagram']
        self.max_retries = 3
        self.retry_delay = 5  # секунд
    
    async def create_download_task(
        self,
        user: User,
        url: str,
        quality: Optional[str] = None,
        send_to_chat: bool = True,
        batch_id: Optional[int] = None,
        priority: int = 5
    ) -> DownloadTask:
        """
        Создать задачу загрузки
        
        Args:
            user: Пользователь
            url: URL видео
            quality: Требуемое качество
            send_to_chat: Отправлять ли файл в чат
            batch_id: ID batch'а если часть группы
            priority: Приоритет задачи
            
        Returns:
            Созданная задача
            
        Raises:
            ValidationError: Если URL невалидный
            LimitExceededError: Если превышены лимиты
        """
        # Валидация URL
        await self._validate_url(url)
        
        # Нормализация URL
        normalized_url = normalize_url(url)
        platform = detect_platform(normalized_url)
        
        # Проверка лимитов пользователя
        await self._check_user_limits(user)
        
        # Определение качества
        if not quality:
            quality = await self._get_optimal_quality(user, platform)
        
        try:
            async with get_async_session() as session:
                # Создание задачи
                task = DownloadTask.create_from_url(
                    url=normalized_url,
                    user_id=user.id,
                    telegram_user_id=user.telegram_id,
                    batch_id=batch_id,
                    quality=quality,
                    send_to_chat=send_to_chat,
                    priority=priority
                )
                
                session.add(task)
                await session.flush()  # Получаем ID
                
                # Аналитика
                await track_download_event(
                    event_type=EventType.DOWNLOAD_REQUESTED,
                    user_id=user.id,
                    platform=platform,
                    event_data={
                        'task_id': task.id,
                        'url': normalized_url,
                        'quality': quality
                    }
                )
                
                await session.commit()
                
                logger.info(
                    "Download task created",
                    task_id=task.id,
                    user_id=user.telegram_id,
                    platform=platform,
                    url=normalized_url[:50] + "..."
                )
                
                return task
                
        except Exception as e:
            logger.error(f"Error creating download task: {e}")
            raise DownloadError(f"Не удалось создать задачу: {e}")
    
    async def start_download(self, task: DownloadTask) -> str:
        """
        Запустить загрузку
        
        Args:
            task: Задача загрузки
            
        Returns:
            ID Celery задачи
        """
        try:
            # Обновляем статус
            async with get_async_session() as session:
                db_task = await session.get(DownloadTask, task.id)
                if db_task:
                    db_task.mark_as_processing()
                    await session.commit()
            
            # Запускаем Celery задачу
            celery_task = process_single_download.delay(task.id)
            
            # Сохраняем ID Celery задачи
            async with get_async_session() as session:
                db_task = await session.get(DownloadTask, task.id)
                if db_task:
                    db_task.celery_task_id = celery_task.id
                    await session.commit()
            
            logger.info(
                "Download started",
                task_id=task.id,
                celery_task_id=celery_task.id
            )
            
            return celery_task.id
            
        except Exception as e:
            logger.error(f"Error starting download: {e}")
            
            # Помечаем задачу как неудачную
            async with get_async_session() as session:
                db_task = await session.get(DownloadTask, task.id)
                if db_task:
                    db_task.mark_as_failed(str(e))
                    await session.commit()
            
            raise DownloadError(f"Не удалось запустить загрузку: {e}")
    
    async def get_task_status(self, task_id: int) -> Dict[str, Any]:
        """
        Получить статус задачи
        
        Args:
            task_id: ID задачи
            
        Returns:
            Статус задачи
        """
        try:
            async with get_async_session() as session:
                task = await session.get(DownloadTask, task_id)
                
                if not task:
                    return {'error': 'Task not found'}
                
                result = {
                    'task_id': task.id,
                    'status': task.status,
                    'progress': task.progress,
                    'url': task.url,
                    'platform': task.platform,
                    'created_at': task.created_at.isoformat(),
                    'user_id': task.telegram_user_id
                }
                
                # Дополнительные поля в зависимости от статуса
                if task.status == TaskStatus.COMPLETED:
                    result.update({
                        'file_path': task.file_path,
                        'file_size': task.file_size_bytes,
                        'duration': task.duration_seconds,
                        'cdn_url': task.cdn_url,
                        'completed_at': task.completed_at.isoformat() if task.completed_at else None
                    })
                elif task.status == TaskStatus.FAILED:
                    result.update({
                        'error': task.error_message,
                        'failed_at': task.failed_at.isoformat() if task.failed_at else None
                    })
                elif task.status == TaskStatus.PROCESSING:
                    result.update({
                        'started_at': task.started_at.isoformat() if task.started_at else None,
                        'estimated_completion': task.estimated_completion.isoformat() if task.estimated_completion else None
                    })
                
                return result
                
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return {'error': str(e)}
    
    async def cancel_download(self, task_id: int, user_id: int) -> bool:
        """
        Отменить загрузку
        
        Args:
            task_id: ID задачи
            user_id: ID пользователя
            
        Returns:
            True если успешно отменена
        """
        try:
            async with get_async_session() as session:
                task = await session.get(DownloadTask, task_id)
                
                if not task:
                    return False
                
                # Проверяем права на отмену
                if task.user_id != user_id and not bot_config.is_admin(user_id):
                    return False
                
                # Отменяем только если задача еще не завершена
                if task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
                    # Отменяем Celery задачу если есть
                    if task.celery_task_id:
                        from worker.celery_app import celery_app
                        celery_app.control.revoke(task.celery_task_id, terminate=True)
                    
                    # Обновляем статус
                    task.mark_as_cancelled()
                    await session.commit()
                    
                    logger.info(f"Download cancelled", task_id=task_id, user_id=user_id)
                    return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling download: {e}")
            return False
    
    async def get_user_downloads(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        status: Optional[TaskStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        Получить загрузки пользователя
        
        Args:
            user_id: ID пользователя
            limit: Лимит записей
            offset: Смещение
            status: Фильтр по статусу
            
        Returns:
            Список загрузок
        """
        try:
            async with get_async_session() as session:
                query = """
                    SELECT * FROM download_tasks 
                    WHERE user_id = :user_id
                """
                params = {'user_id': user_id}
                
                if status:
                    query += " AND status = :status"
                    params['status'] = status.value
                
                query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                params.update({'limit': limit, 'offset': offset})
                
                result = await session.execute(query, params)
                tasks = result.fetchall()
                
                return [
                    {
                        'task_id': task.id,
                        'url': task.url,
                        'platform': task.platform,
                        'status': task.status,
                        'created_at': task.created_at.isoformat(),
                        'file_size': task.file_size_bytes,
                        'duration': task.duration_seconds
                    }
                    for task in tasks
                ]
                
        except Exception as e:
            logger.error(f"Error getting user downloads: {e}")
            return []
    
    async def cleanup_old_tasks(self, days_old: int = 7) -> int:
        """
        Очистка старых задач
        
        Args:
            days_old: Возраст задач в днях
            
        Returns:
            Количество удаленных задач
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            async with get_async_session() as session:
                # Удаляем старые завершенные/отмененные задачи
                result = await session.execute(
                    text(
                        """
                        DELETE FROM download_tasks 
                        WHERE created_at < :cutoff_date 
                        AND status IN ('completed', 'failed', 'cancelled')
                        """
                    ),
                    {'cutoff_date': cutoff_date}
                )
                
                deleted_count = result.rowcount
                await session.commit()
                
                logger.info(f"Cleaned up {deleted_count} old download tasks")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error cleaning up old tasks: {e}")
            return 0
    
    async def _validate_url(self, url: str):
        """Валидация URL"""
        if not validate_url(url):
            raise ValidationError("Неподдерживаемый URL")
        
        platform = detect_platform(url)
        if platform not in self.supported_platforms:
            raise ValidationError(f"Платформа {platform} не поддерживается")
    
    async def _check_user_limits(self, user: User):
        """Проверка лимитов пользователя"""
        # Проверяем дневной лимит
        if not user.can_download_today():
            daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
            raise LimitExceededError(
                f"Превышен дневной лимит загрузок ({daily_limit})"
            )
        
        # Проверяем бан
        if user.is_banned:
            raise LimitExceededError("Пользователь заблокирован")
    
    async def _get_optimal_quality(self, user: User, platform: str) -> str:
        """Определить оптимальное качество для пользователя"""
        # Получаем предпочтения пользователя
        preferences = user.download_preferences or {}
        quality_mode = preferences.get('quality_mode', 'auto')
        
        # Максимальное доступное качество по типу пользователя
        max_quality_map = {
            'free': '720p',
            'trial': '1080p', 
            'premium': '2160p',
            'admin': '2160p'
        }
        
        max_quality = max_quality_map.get(user.current_user_type, '720p')
        
        if quality_mode == 'auto':
            # Автоматический выбор оптимального качества
            if user.current_user_type in ['premium', 'admin']:
                return '1080p'  # Оптимальный баланс качества/размера
            else:
                return '720p'
        elif quality_mode == 'max':
            return max_quality
        else:
            # Ручной режим - возвращаем максимально доступное
            return max_quality
    
    async def retry_failed_task(self, task_id: int) -> bool:
        """
        Повторить неудачную задачу
        
        Args:
            task_id: ID задачи
            
        Returns:
            True если повтор запущен успешно
        """
        try:
            async with get_async_session() as session:
                task = await session.get(DownloadTask, task_id)
                
                if not task or task.status != TaskStatus.FAILED:
                    return False
                
                # Проверяем количество попыток
                if task.retry_count >= self.max_retries:
                    logger.warning(f"Max retries exceeded for task {task_id}")
                    return False
                
                # Увеличиваем счетчик попыток
                task.retry_count += 1
                task.error_message = None
                task.failed_at = None
                
                await session.commit()
                
                # Запускаем повторно
                celery_task_id = await self.start_download(task)
                
                logger.info(
                    f"Task retry started",
                    task_id=task_id,
                    retry_count=task.retry_count,
                    celery_task_id=celery_task_id
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Error retrying task: {e}")
            return False

# Глобальный экземпляр сервиса
download_service = DownloadService()