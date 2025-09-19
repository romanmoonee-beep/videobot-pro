"""
VideoBot Pro - Batch Tasks
Celery задачи для обработки групповых загрузок
"""

import time
import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from celery import current_task, group

from worker.celery_app import celery_app
from shared.config.database import get_async_session
from shared.models import DownloadBatch, DownloadTask, User, DownloadStatus, BatchStatus, EventType
from shared.models.analytics import track_download_event
from worker.processors import BatchProcessor
from worker.storage import StorageManager
from worker.utils import ProgressTracker
from .download_tasks import process_single_download

logger = structlog.get_logger(__name__)

@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 2, 'countdown': 120},
    time_limit=7200,  # 2 hours
    soft_time_limit=6900,  # 1h 55m
    acks_late=True
)
def process_batch_download(self, batch_id: int) -> Dict[str, Any]:
    """
    Обработать batch загрузку
    
    Args:
        batch_id: ID batch'а в базе данных
        
    Returns:
        Результат обработки
    """
    logger.info(f"Starting batch processing", batch_id=batch_id, celery_task_id=self.request.id)
    
    start_time = time.time()
    progress_tracker = ProgressTracker(batch_id, self.request.id, is_batch=True)
    
    try:
        # Получаем batch из БД
        async with get_async_session() as session:
            batch = await session.get(DownloadBatch, batch_id)
            if not batch:
                raise ValueError(f"Batch {batch_id} not found")
            
            user = await session.get(User, batch.user_id)
            if not user:
                raise ValueError(f"User {batch.user_id} not found")
            
            # Проверяем можно ли обрабатывать batch
            if batch.status != DownloadStatus.PENDING:
                logger.warning(f"Batch {batch_id} is not pending", status=batch.status)
                return {"success": False, "error": "Batch is not pending"}
            
            # Отмечаем как обрабатывающийся
            batch.start_processing(
                worker_id=self.request.hostname,
                task_id=self.request.id
            )
            await session.commit()
        
        await progress_tracker.update_progress(5, "Initializing batch processing")
        
        # Создаем отдельные задачи для каждого URL
        individual_tasks = []
        
        async with get_async_session() as session:
            # Получаем все задачи batch'а
            tasks_query = await session.execute("""
                SELECT id, original_url, order_in_batch 
                FROM download_tasks 
                WHERE batch_id = :batch_id 
                ORDER BY order_in_batch
            """, {"batch_id": batch_id})
            
            batch_tasks = tasks_query.fetchall()
            
            if not batch_tasks:
                raise ValueError("No tasks found in batch")
            
            # Определяем стратегию обработки
            processing_strategy = _determine_processing_strategy(
                user_type=user.current_user_type,
                tasks_count=len(batch_tasks),
                batch_settings=batch.delivery_method
            )
            
            logger.info(f"Using processing strategy: {processing_strategy}", 
                       batch_id=batch_id, tasks_count=len(batch_tasks))
        
        await progress_tracker.update_progress(10, f"Processing {len(batch_tasks)} videos")
        
        # Обрабатываем задачи согласно стратегии
        if processing_strategy == "parallel":
            # Параллельная обработка для Premium/Admin
            individual_tasks = await _process_batch_parallel(
                batch_tasks, progress_tracker, user.current_user_type
            )
        elif processing_strategy == "sequential":
            # Последовательная обработка для Free/Trial
            individual_tasks = await _process_batch_sequential(
                batch_tasks, progress_tracker
            )
        else:
            # Смешанная стратегия - группы по 3-5 задач
            individual_tasks = await _process_batch_mixed(
                batch_tasks, progress_tracker, user.current_user_type
            )
        
        await progress_tracker.update_progress(80, "Collecting results")
        
        # Собираем результаты
        successful_tasks = []
        failed_tasks = []
        total_size_mb = 0.0
        
        for task_result in individual_tasks:
            if task_result.get("success"):
                successful_tasks.append(task_result)
                if "file_info" in task_result:
                    total_size_mb += task_result["file_info"].get("size_mb", 0)
            else:
                failed_tasks.append(task_result)
        
        # Обновляем batch в БД
        async with get_async_session() as session:
            db_batch = await session.get(DownloadBatch, batch_id)
            db_batch.completed_count = len(successful_tasks)
            db_batch.failed_count = len(failed_tasks)
            db_batch.total_size_mb = total_size_mb
            
            # Добавляем результаты
            for task_result in individual_tasks:
                db_batch.add_result(
                    url=task_result.get("original_url", ""),
                    result=task_result
                )
            
            await session.commit()
        
        await progress_tracker.update_progress(90, "Creating delivery")
        
        # Создаем доставку согласно настройкам
        delivery_result = await _create_batch_delivery(
            batch_id, successful_tasks, batch.delivery_method, user.current_user_type
        )
        
        # Финализируем batch
        async with get_async_session() as session:
            db_batch = await session.get(DownloadBatch, batch_id)
            
            if delivery_result.get("archive_url"):
                db_batch.archive_url = delivery_result["archive_url"]
                db_batch.archive_size_mb = delivery_result.get("archive_size_mb", 0)
            
            # Устанавливаем CDN ссылки
            if delivery_result.get("cdn_links"):
                for cdn_link in delivery_result["cdn_links"]:
                    db_batch.add_cdn_link(cdn_link["url"], cdn_link)
            
            # Завершаем batch
            if len(failed_tasks) == len(individual_tasks):
                db_batch.fail_processing("All tasks failed")
            else:
                db_batch.complete_processing()
            
            await session.commit()
        
        await progress_tracker.update_progress(100, "Completed")
        
        # Трекаем аналитику
        await track_download_event(
            event_type=EventType.BATCH_COMPLETED,
            user_id=user.id,
            platform="mixed",
            value=len(successful_tasks),
            duration_seconds=int(time.time() - start_time),
            event_data={
                'batch_id': batch_id,
                'total_tasks': len(individual_tasks),
                'successful_tasks': len(successful_tasks),
                'failed_tasks': len(failed_tasks),
                'total_size_mb': total_size_mb,
                'processing_time': int(time.time() - start_time),
                'delivery_method': batch.delivery_method
            }
        )
        
        # Отправляем уведомление (асинхронно)
        from .notification_tasks import send_batch_completion_notification
        send_batch_completion_notification.delay(batch_id)
        
        result = {
            "success": True,
            "batch_id": batch_id,
            "summary": {
                "total_tasks": len(individual_tasks),
                "successful": len(successful_tasks),
                "failed": len(failed_tasks),
                "total_size_mb": round(total_size_mb, 2)
            },
            "delivery": delivery_result,
            "processing_time": int(time.time() - start_time)
        }
        
        logger.info(f"Batch processing completed", 
                   batch_id=batch_id, **result["summary"])
        
        return result
        
    except Exception as e:
        logger.error(f"Batch processing failed", batch_id=batch_id, error=str(e), exc_info=True)
        
        # Обновляем batch как неудачный
        try:
            async with get_async_session() as session:
                db_batch = await session.get(DownloadBatch, batch_id)
                if db_batch:
                    db_batch.fail_processing(str(e))
                    await session.commit()
        except Exception as db_error:
            logger.error(f"Failed to update batch status", error=str(db_error))
        
        # Трекаем ошибку
        try:
            await track_download_event(
                event_type=EventType.BATCH_FAILED,
                user_id=user.id if 'user' in locals() else None,
                platform="mixed",
                duration_seconds=int(time.time() - start_time),
                event_data={
                    'batch_id': batch_id,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )
        except:
            pass
        
        # Повторяем если возможно
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying batch processing", batch_id=batch_id, retry=self.request.retries + 1)
            raise self.retry(countdown=120 * (2 ** self.request.retries))
        
        return {
            "success": False,
            "batch_id": batch_id,
            "error": str(e),
            "error_type": type(e).__name__,
            "processing_time": int(time.time() - start_time)
        }

async def _process_batch_parallel(batch_tasks: List, progress_tracker: ProgressTracker, user_type: str) -> List[Dict]:
    """Параллельная обработка batch'а"""
    
    # Определяем количество параллельных задач
    max_parallel = 5 if user_type == "admin" else 3
    
    # Создаем группы задач
    task_groups = []
    for i in range(0, len(batch_tasks), max_parallel):
        group_tasks = batch_tasks[i:i + max_parallel]
        
        # Создаем Celery группу
        job = group([
            process_single_download.s(task.id) 
            for task in group_tasks
        ])
        task_groups.append(job)
    
    results = []
    completed_groups = 0
    
    for group_job in task_groups:
        group_result = group_job.apply_async()
        group_results = group_result.get()  # Ждем завершения группы
        
        results.extend(group_results)
        completed_groups += 1
        
        # Обновляем прогресс
        progress = 10 + (completed_groups / len(task_groups)) * 70
        await progress_tracker.update_progress(
            progress, 
            f"Processed {completed_groups}/{len(task_groups)} groups"
        )
    
    return results

async def _process_batch_sequential(batch_tasks: List, progress_tracker: ProgressTracker) -> List[Dict]:
    """Последовательная обработка batch'а"""
    
    results = []
    
    for i, task in enumerate(batch_tasks):
        # Обрабатываем задачу
        task_result = process_single_download.apply_async(args=[task.id])
        result = task_result.get()  # Ждем завершения
        
        results.append(result)
        
        # Обновляем прогресс
        progress = 10 + ((i + 1) / len(batch_tasks)) * 70
        await progress_tracker.update_progress(
            progress,
            f"Processed {i + 1}/{len(batch_tasks)} videos"
        )
    
    return results

async def _process_batch_mixed(batch_tasks: List, progress_tracker: ProgressTracker, user_type: str) -> List[Dict]:
    """Смешанная обработка - небольшие группы"""
    
    group_size = 3 if user_type in ["premium", "trial"] else 2
    results = []
    
    for i in range(0, len(batch_tasks), group_size):
        group_tasks = batch_tasks[i:i + group_size]
        
        # Обрабатываем группу параллельно
        job = group([
            process_single_download.s(task.id) 
            for task in group_tasks
        ])
        
        group_result = job.apply_async()
        group_results = group_result.get()
        
        results.extend(group_results)
        
        # Обновляем прогресс
        progress = 10 + ((i + len(group_tasks)) / len(batch_tasks)) * 70
        await progress_tracker.update_progress(
            progress,
            f"Processed {min(i + group_size, len(batch_tasks))}/{len(batch_tasks)} videos"
        )
    
    return results

def _determine_processing_strategy(user_type: str, tasks_count: int, batch_settings: str) -> str:
    """Определить стратегию обработки batch'а"""
    
    if user_type == "admin":
        return "parallel"
    elif user_type == "premium" and tasks_count <= 10:
        return "parallel"
    elif user_type in ["premium", "trial"] and tasks_count <= 20:
        return "mixed"
    else:
        return "sequential"

async def _create_batch_delivery(batch_id: int, successful_tasks: List[Dict], 
                               delivery_method: str, user_type: str) -> Dict[str, Any]:
    """Создать доставку для batch'а"""
    
    storage_manager = StorageManager()
    batch_processor = BatchProcessor()
    
    delivery_result = {
        "cdn_links": [],
        "archive_url": None,
        "delivery_method": delivery_method
    }
    
    # Собираем CDN ссылки
    for task in successful_tasks:
        if task.get("cdn_url"):
            delivery_result["cdn_links"].append({
                "url": task.get("original_url", ""),
                "cdn_url": task["cdn_url"],
                "file_info": task.get("file_info", {})
            })
    
    # Создаем архив если нужно
    if delivery_method == "archive" or (delivery_method == "auto" and len(successful_tasks) > 4):
        try:
            archive_files = []
            for task in successful_tasks:
                if task.get("success") and task.get("file_info"):
                    archive_files.append({
                        "cdn_url": task["cdn_url"],
                        "file_name": task["file_info"]["name"],
                        "local_path": task.get("local_path")  # Если доступен
                    })
            
            if archive_files:
                archive_result = await batch_processor.create_archive(
                    files=archive_files,
                    batch_id=batch_id,
                    user_type=user_type
                )
                
                if archive_result.get("success"):
                    delivery_result["archive_url"] = archive_result["archive_url"]
                    delivery_result["archive_size_mb"] = archive_result.get("archive_size_mb", 0)
                    
        except Exception as e:
            logger.error(f"Failed to create batch archive", batch_id=batch_id, error=str(e))
    
    return delivery_result

@celery_app.task(bind=True)
def create_batch_archive(self, batch_id: int, force: bool = False) -> Dict[str, Any]:
    """
    Создать архив для batch'а
    
    Args:
        batch_id: ID batch'а
        force: Принудительное создание архива
        
    Returns:
        Результат создания архива
    """
    logger.info(f"Creating batch archive", batch_id=batch_id, force=force)
    
    try:
        async with get_async_session() as session:
            batch = await session.get(DownloadBatch, batch_id)
            if not batch:
                return {"success": False, "error": "Batch not found"}
            
            if not force and batch.archive_url:
                return {"success": True, "archive_url": batch.archive_url, "message": "Archive already exists"}
            
            # Получаем успешные файлы
            successful_files = batch.get_successful_files()
            if not successful_files:
                return {"success": False, "error": "No files to archive"}
            
            user = await session.get(User, batch.user_id)
            if not user:
                return {"success": False, "error": "User not found"}
        
        # Создаем архив
        batch_processor = BatchProcessor()
        archive_result = await batch_processor.create_archive(
            files=successful_files,
            batch_id=batch_id,
            user_type=user.current_user_type
        )
        
        if archive_result.get("success"):
            # Обновляем batch
            async with get_async_session() as session:
                db_batch = await session.get(DownloadBatch, batch_id)
                db_batch.archive_url = archive_result["archive_url"]
                db_batch.archive_size_mb = archive_result.get("archive_size_mb", 0)
                await session.commit()
        
        return archive_result
        
    except Exception as e:
        logger.error(f"Failed to create batch archive", batch_id=batch_id, error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def retry_failed_batch(batch_id: int) -> Dict[str, Any]:
    """
    Повторить неудачный batch
    
    Args:
        batch_id: ID batch'а
        
    Returns:
        Результат операции
    """
    logger.info(f"Retrying failed batch", batch_id=batch_id)
    
    try:
        async with get_async_session() as session:
            batch = await session.get(DownloadBatch, batch_id)
            if not batch:
                return {"success": False, "error": "Batch not found"}
            
            if batch.status != BatchStatus.FAILED:
                return {"success": False, "error": "Batch is not failed"}
            
            # Сбрасываем статус
            batch.status = DownloadStatus.PENDING
            batch.started_at = None
            batch.completed_at = None
            batch.error_messages = []
            batch.retry_count = (batch.retry_count or 0) + 1
            
            # Сбрасываем неудачные задачи
            await session.execute("""
                UPDATE download_tasks 
                SET status = 'pending', 
                    error_message = NULL,
                    started_at = NULL,
                    completed_at = NULL,
                    retry_count = retry_count + 1
                WHERE batch_id = :batch_id 
                AND status = 'failed'
            """, {"batch_id": batch_id})
            
            await session.commit()
        
        # Запускаем новую обработку
        process_batch_download.delay(batch_id)
        
        return {"success": True, "batch_id": batch_id, "message": "Batch retry initiated"}
        
    except Exception as e:
        logger.error(f"Failed to retry batch", batch_id=batch_id, error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def cleanup_expired_batches() -> Dict[str, Any]:
    """
    Очистка истекших batch'ей
    
    Returns:
        Статистика очистки
    """
    logger.info("Starting cleanup of expired batches")
    
    try:
        cleaned_count = 0
        
        async with get_async_session() as session:
            # Находим истекшие batch'и
            expired_batches = await session.execute("""
                SELECT id, archive_url 
                FROM download_batches 
                WHERE expires_at < NOW() 
                AND status = 'completed'
                LIMIT 500
            """)
            
            for batch in expired_batches.fetchall():
                try:
                    # Помечаем как истекший
                    await session.execute("""
                        UPDATE download_batches 
                        SET status = 'expired'
                        WHERE id = :batch_id
                    """, {"batch_id": batch.id})
                    
                    # Помечаем связанные задачи как истекшие
                    await session.execute("""
                        UPDATE download_tasks 
                        SET status = 'expired',
                            local_file_path = NULL
                        WHERE batch_id = :batch_id
                        AND expires_at < NOW()
                    """, {"batch_id": batch.id})
                    
                    cleaned_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to cleanup batch {batch.id}", error=str(e))
            
            await session.commit()
        
        logger.info(f"Cleaned up {cleaned_count} expired batches")
        return {"success": True, "cleaned_count": cleaned_count}
        
    except Exception as e:
        logger.error(f"Failed to cleanup expired batches", error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def check_batch_status(batch_id: int) -> Dict[str, Any]:
    """
    Проверить статус batch'а
    
    Args:
        batch_id: ID batch'а
        
    Returns:
        Статус batch'а
    """
    try:
        async with get_async_session() as session:
            batch = await session.get(DownloadBatch, batch_id)
            if not batch:
                return {"success": False, "error": "Batch not found"}
            
            # Получаем статистику задач
            task_stats = await session.execute("""
                SELECT 
                    status,
                    COUNT(*) as count
                FROM download_tasks 
                WHERE batch_id = :batch_id 
                GROUP BY status
            """, {"batch_id": batch_id})
            
            status_counts = {row.status: row.count for row in task_stats.fetchall()}
            
            return {
                "success": True,
                "batch_id": batch_id,
                "status": batch.status,
                "progress_percent": batch.progress_percent,
                "total_urls": batch.total_urls,
                "completed_count": batch.completed_count,
                "failed_count": batch.failed_count,
                "task_status_counts": status_counts,
                "created_at": batch.created_at.isoformat(),
                "started_at": batch.started_at.isoformat() if batch.started_at else None,
                "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
                "archive_url": batch.archive_url,
                "total_size_mb": batch.total_size_mb,
                "estimated_completion": batch.estimated_completion_time.isoformat() if batch.estimated_completion_time else None
            }
            
    except Exception as e:
        logger.error(f"Failed to check batch status", batch_id=batch_id, error=str(e))
        return {"success": False, "error": str(e)}