"""
VideoBot Pro - Download Tasks
Celery задачи для обработки отдельных загрузок видео
"""

import time
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from celery import current_task
from celery.exceptions import Retry, WorkerLostError

from worker.celery_app import celery_app
from shared.config.database import get_async_session
from shared.models import DownloadTask, User, DownloadStatus, EventType
from shared.models.analytics import track_download_event, track_system_event
from worker.downloaders import DownloaderFactory
from worker.storage import StorageManager
from worker.processors import VideoProcessor
from worker.utils import ProgressTracker, QualitySelector

logger = structlog.get_logger(__name__)

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    retry_backoff=True,
    time_limit=1800,  # 30 minutes
    soft_time_limit=1500,  # 25 minutes
    acks_late=True,
    reject_on_worker_lost=True
)
def process_single_download(self, task_id: int) -> Dict[str, Any]:
    """
    Обработать отдельную задачу скачивания
    
    Args:
        task_id: ID задачи в базе данных
        
    Returns:
        Результат обработки
    """
    logger.info(f"Starting download task", task_id=task_id, celery_task_id=self.request.id)
    
    start_time = time.time()
    progress_tracker = ProgressTracker(task_id, self.request.id)
    
    try:
        # Получаем задачу из БД
        async with get_async_session() as session:
            download_task = await session.get(DownloadTask, task_id)
            if not download_task:
                raise ValueError(f"Download task {task_id} not found")
            
            user = await session.get(User, download_task.user_id)
            if not user:
                raise ValueError(f"User {download_task.user_id} not found")
            
            # Проверяем можно ли обрабатывать задачу
            if download_task.status != DownloadStatus.PENDING:
                logger.warning(f"Task {task_id} is not pending", status=download_task.status)
                return {"success": False, "error": "Task is not pending"}
            
            # Отмечаем как обрабатывающуюся
            download_task.start_processing(
                worker_id=self.request.hostname,
                celery_task_id=self.request.id
            )
            await session.commit()
        
        # Инициализируем компоненты
        downloader_factory = DownloaderFactory()
        storage_manager = StorageManager()
        video_processor = VideoProcessor()
        quality_selector = QualitySelector()
        
        # Обновляем прогресс
        await progress_tracker.update_progress(5, "Initializing download")
        
        # Получаем downloader для платформы
        downloader = downloader_factory.get_downloader(download_task.platform)
        if not downloader:
            raise ValueError(f"Unsupported platform: {download_task.platform}")
        
        await progress_tracker.update_progress(10, "Getting video info")
        
        # Получаем информацию о видео
        video_info = await downloader.get_video_info(download_task.original_url)
        
        # Сохраняем информацию о видео
        async with get_async_session() as session:
            db_task = await session.get(DownloadTask, task_id)
            db_task.set_video_info(
                title=video_info.get('title'),
                author=video_info.get('uploader'),
                duration=video_info.get('duration'),
                views=video_info.get('view_count'),
                upload_date=video_info.get('upload_date'),
                description=video_info.get('description'),
                thumbnail_url=video_info.get('thumbnail')
            )
            await session.commit()
        
        await progress_tracker.update_progress(20, "Selecting quality")
        
        # Выбираем оптимальное качество
        requested_quality = download_task.requested_quality or "auto"
        optimal_quality = quality_selector.select_quality(
            available_formats=video_info.get('formats', []),
            requested_quality=requested_quality,
            user_type=user.current_user_type,
            file_size_limit=user.get_max_file_size_mb() * 1024 * 1024
        )
        
        if not optimal_quality:
            raise ValueError("No suitable quality found for download")
        
        await progress_tracker.update_progress(30, "Starting download")
        
        # Настройки скачивания
        download_options = {
            'format': optimal_quality['format_id'],
            'quality': optimal_quality['quality'],
            'progress_callback': progress_tracker.download_progress_callback,
            'max_filesize': user.get_max_file_size_mb() * 1024 * 1024,
        }
        
        # Скачиваем файл
        download_result = await downloader.download_video(
            url=download_task.original_url,
            options=download_options
        )
        
        await progress_tracker.update_progress(70, "Processing video")
        
        # Обрабатываем видео если нужно
        processed_file = await video_processor.process_video(
            file_path=download_result['file_path'],
            task_id=task_id,
            optimize_quality=optimal_quality.get('needs_processing', False)
        )
        
        await progress_tracker.update_progress(85, "Uploading to storage")
        
        # Загружаем в облачное хранилище
        storage_result = await storage_manager.upload_file(
            file_path=processed_file['file_path'],
            task_id=task_id,
            user_type=user.current_user_type,
            metadata={
                'platform': download_task.platform,
                'quality': optimal_quality['quality'],
                'title': video_info.get('title'),
                'duration': video_info.get('duration')
            }
        )
        
        await progress_tracker.update_progress(95, "Finalizing")
        
        # Обновляем задачу в БД
        async with get_async_session() as session:
            db_task = await session.get(DownloadTask, task_id)
            
            # Устанавливаем информацию о файле
            db_task.set_file_info(
                file_name=processed_file['file_name'],
                file_size=processed_file['file_size'],
                file_format=processed_file['format'],
                actual_quality=optimal_quality['quality'],
                local_path=processed_file['file_path']
            )
            
            # Устанавливаем CDN информацию
            retention_hours = user.get_file_retention_hours()
            db_task.set_cdn_info(
                cdn_url=storage_result['cdn_url'],
                direct_url=storage_result.get('direct_url'),
                expires_hours=retention_hours
            )
            
            # Завершаем задачу
            db_task.complete_successfully()
            
            # Обновляем статистику пользователя
            user.increment_downloads()
            user.update_stats(
                platform=download_task.platform,
                file_size_mb=processed_file['file_size'] / (1024 * 1024),
                duration_seconds=video_info.get('duration')
            )
            
            await session.commit()
        
        await progress_tracker.update_progress(100, "Completed")
        
        # Трекаем аналитику
        await track_download_event(
            event_type=EventType.DOWNLOAD_COMPLETED,
            user_id=user.id,
            platform=download_task.platform,
            value=processed_file['file_size'] / (1024 * 1024),  # MB
            duration_seconds=int(time.time() - start_time),
            event_data={
                'task_id': task_id,
                'quality': optimal_quality['quality'],
                'file_format': processed_file['format'],
                'processing_time': int(time.time() - start_time)
            }
        )
        
        # Отправляем уведомление (асинхронно)
        from .notification_tasks import send_download_completion_notification
        send_download_completion_notification.delay(task_id)
        
        result = {
            "success": True,
            "task_id": task_id,
            "file_info": {
                "name": processed_file['file_name'],
                "size_mb": round(processed_file['file_size'] / (1024 * 1024), 2),
                "format": processed_file['format'],
                "quality": optimal_quality['quality']
            },
            "cdn_url": storage_result['cdn_url'],
            "processing_time": int(time.time() - start_time)
        }
        
        logger.info(f"Download task completed successfully", 
                   task_id=task_id, processing_time=result["processing_time"])
        
        return result
        
    except Exception as e:
        logger.error(f"Download task failed", task_id=task_id, error=str(e), exc_info=True)
        
        # Обновляем задачу как неудачную
        try:
            async with get_async_session() as session:
                db_task = await session.get(DownloadTask, task_id)
                if db_task:
                    db_task.fail_with_error(str(e), type(e).__name__)
                    await session.commit()
        except Exception as db_error:
            logger.error(f"Failed to update task status", error=str(db_error))
        
        # Трекаем ошибку
        try:
            await track_download_event(
                event_type=EventType.DOWNLOAD_FAILED,
                user_id=user.id if 'user' in locals() else None,
                platform=download_task.platform if 'download_task' in locals() else None,
                duration_seconds=int(time.time() - start_time),
                event_data={
                    'task_id': task_id,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
        except:
            pass
        
        # Отправляем уведомление об ошибке
        try:
            from .notification_tasks import send_download_completion_notification
            send_download_completion_notification.delay(task_id)
        except:
            pass
        
        # Повторяем если возможно
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying download task", task_id=task_id, retry=self.request.retries + 1)
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e),
            "error_type": type(e).__name__,
            "processing_time": int(time.time() - start_time)
        }

@celery_app.task(bind=True)
def retry_failed_download(self, task_id: int) -> Dict[str, Any]:
    """
    Повторить неудачную загрузку
    
    Args:
        task_id: ID задачи для повтора
        
    Returns:
        Результат операции
    """
    logger.info(f"Retrying failed download", task_id=task_id)
    
    try:
        async with get_async_session() as session:
            download_task = await session.get(DownloadTask, task_id)
            if not download_task:
                return {"success": False, "error": "Task not found"}
            
            if not download_task.can_retry:
                return {"success": False, "error": "Task cannot be retried"}
            
            # Подготавливаем к повтору
            download_task.retry_task()
            await session.commit()
        
        # Запускаем новую задачу
        process_single_download.delay(task_id)
        
        return {"success": True, "task_id": task_id, "message": "Retry initiated"}
        
    except Exception as e:
        logger.error(f"Failed to retry download", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def cleanup_expired_downloads() -> Dict[str, Any]:
    """
    Очистка истекших загрузок
    
    Returns:
        Статистика очистки
    """
    logger.info("Starting cleanup of expired downloads")
    
    try:
        cleaned_count = 0
        
        async with get_async_session() as session:
            # Находим истекшие задачи
            expired_tasks = await session.execute("""
                SELECT id, local_file_path, cdn_url 
                FROM download_tasks 
                WHERE expires_at < NOW() 
                AND status = 'completed'
                AND local_file_path IS NOT NULL
                LIMIT 1000
            """)
            
            for task in expired_tasks.fetchall():
                try:
                    # Удаляем локальный файл
                    if task.local_file_path:
                        import os
                        if os.path.exists(task.local_file_path):
                            os.remove(task.local_file_path)
                    
                    # Помечаем как истекший
                    await session.execute("""
                        UPDATE download_tasks 
                        SET local_file_path = NULL,
                            status = 'expired'
                        WHERE id = :task_id
                    """, {"task_id": task.id})
                    
                    cleaned_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to cleanup task {task.id}", error=str(e))
            
            await session.commit()
        
        logger.info(f"Cleaned up {cleaned_count} expired downloads")
        return {"success": True, "cleaned_count": cleaned_count}
        
    except Exception as e:
        logger.error(f"Failed to cleanup expired downloads", error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def check_download_status(task_id: int) -> Dict[str, Any]:
    """
    Проверить статус загрузки
    
    Args:
        task_id: ID задачи
        
    Returns:
        Статус задачи
    """
    try:
        async with get_async_session() as session:
            download_task = await session.get(DownloadTask, task_id)
            if not download_task:
                return {"success": False, "error": "Task not found"}
            
            return {
                "success": True,
                "task_id": task_id,
                "status": download_task.status,
                "progress": download_task.progress_percent,
                "created_at": download_task.created_at.isoformat(),
                "started_at": download_task.started_at.isoformat() if download_task.started_at else None,
                "completed_at": download_task.completed_at.isoformat() if download_task.completed_at else None,
                "error": download_task.error_message,
                "file_info": {
                    "name": download_task.file_name,
                    "size_bytes": download_task.file_size_bytes,
                    "format": download_task.file_format,
                    "quality": download_task.actual_quality
                } if download_task.is_completed else None,
                "cdn_url": download_task.cdn_url if download_task.is_completed else None
            }
            
    except Exception as e:
        logger.error(f"Failed to check download status", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def cancel_download_task(task_id: int, user_id: int) -> Dict[str, Any]:
    """
    Отменить задачу загрузки
    
    Args:
        task_id: ID задачи
        user_id: ID пользователя (для проверки прав)
        
    Returns:
        Результат операции
    """
    logger.info(f"Cancelling download task", task_id=task_id, user_id=user_id)
    
    try:
        async with get_async_session() as session:
            download_task = await session.get(DownloadTask, task_id)
            if not download_task:
                return {"success": False, "error": "Task not found"}
            
            # Проверяем права
            if download_task.user_id != user_id:
                return {"success": False, "error": "Access denied"}
            
            # Можно отменить только pending или processing задачи
            if download_task.status not in [DownloadStatus.PENDING, DownloadStatus.PROCESSING]:
                return {"success": False, "error": "Task cannot be cancelled"}
            
            # Отменяем Celery задачу если есть
            if download_task.celery_task_id:
                celery_app.control.revoke(download_task.celery_task_id, terminate=True)
            
            # Обновляем статус
            download_task.status = DownloadStatus.CANCELLED
            download_task.completed_at = datetime.utcnow()
            
            await session.commit()
        
        logger.info(f"Download task cancelled", task_id=task_id)
        return {"success": True, "task_id": task_id}
        
    except Exception as e:
        logger.error(f"Failed to cancel download task", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def get_download_progress(task_id: int) -> Dict[str, Any]:
    """
    Получить прогресс загрузки
    
    Args:
        task_id: ID задачи
        
    Returns:
        Прогресс загрузки
    """
    try:
        progress_tracker = ProgressTracker(task_id)
        progress_data = progress_tracker.get_current_progress()
        
        return {
            "success": True,
            "task_id": task_id,
            "progress": progress_data
        }
        
    except Exception as e:
        logger.error(f"Failed to get download progress", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}