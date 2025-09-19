"""
VideoBot Pro - Download Tasks
Celery задачи для обработки отдельных загрузок видео
"""

import time
import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from celery import current_task
from celery.exceptions import Retry, WorkerLostError

from worker.celery_app import celery_app
from shared.config.database import get_async_session

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
    
    try:
        # Запускаем асинхронную обработку
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_process_download_async(task_id, self.request))
            return result
        finally:
            loop.close()
        
    except Exception as e:
        logger.error(f"Download task failed", task_id=task_id, error=str(e), exc_info=True)
        
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

async def _process_download_async(task_id: int, request_info) -> Dict[str, Any]:
    """Асинхронная обработка загрузки"""
    start_time = time.time()
    
    try:
        async with get_async_session() as session:
            # Получаем задачу из БД
            result = await session.execute(
                "SELECT * FROM download_tasks WHERE id = :task_id",
                {"task_id": task_id}
            )
            task_row = result.fetchone()
            
            if not task_row:
                raise ValueError(f"Download task {task_id} not found")
            
            # Получаем пользователя
            user_result = await session.execute(
                "SELECT * FROM users WHERE id = :user_id",
                {"user_id": task_row.user_id}
            )
            user_row = user_result.fetchone()
            
            if not user_row:
                raise ValueError(f"User {task_row.user_id} not found")
            
            # Проверяем можно ли обрабатывать задачу
            if task_row.status != 'pending':
                logger.warning(f"Task {task_id} is not pending", status=task_row.status)
                return {"success": False, "error": "Task is not pending"}
            
            # Отмечаем как обрабатывающуюся
            await session.execute("""
                UPDATE download_tasks 
                SET status = 'processing',
                    started_at = :started_at,
                    worker_id = :worker_id,
                    celery_task_id = :celery_task_id
                WHERE id = :task_id
            """, {
                "started_at": datetime.utcnow(),
                "worker_id": request_info.hostname,
                "celery_task_id": request_info.id,
                "task_id": task_id
            })
            await session.commit()
        
        # Имитация обработки файла (замените на реальную логику)
        await asyncio.sleep(2)  # Симуляция скачивания
        
        # Обновляем как завершенную
        async with get_async_session() as session:
            await session.execute("""
                UPDATE download_tasks 
                SET status = 'completed',
                    completed_at = :completed_at,
                    file_name = :file_name,
                    file_size_bytes = :file_size,
                    progress_percent = 100
                WHERE id = :task_id
            """, {
                "completed_at": datetime.utcnow(),
                "file_name": f"video_{task_id}.mp4",
                "file_size": 1024 * 1024 * 10,  # 10MB
                "task_id": task_id
            })
            await session.commit()
        
        result = {
            "success": True,
            "task_id": task_id,
            "file_info": {
                "name": f"video_{task_id}.mp4",
                "size_mb": 10,
                "format": "mp4",
                "quality": "720p"
            },
            "processing_time": int(time.time() - start_time)
        }
        
        logger.info(f"Download task completed successfully", 
                   task_id=task_id, processing_time=result["processing_time"])
        
        return result
        
    except Exception as e:
        logger.error(f"Error in download processing: {e}")
        
        # Обновляем задачу как неудачную
        try:
            async with get_async_session() as session:
                await session.execute("""
                    UPDATE download_tasks 
                    SET status = 'failed',
                        completed_at = :completed_at,
                        error_message = :error_message
                    WHERE id = :task_id
                """, {
                    "completed_at": datetime.utcnow(),
                    "error_message": str(e),
                    "task_id": task_id
                })
                await session.commit()
        except Exception as db_error:
            logger.error(f"Failed to update task status", error=str(db_error))
        
        raise

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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_retry_download_async(task_id))
            return result
        finally:
            loop.close()
        
    except Exception as e:
        logger.error(f"Failed to retry download", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}

async def _retry_download_async(task_id: int) -> Dict[str, Any]:
    """Асинхронный повтор загрузки"""
    try:
        async with get_async_session() as session:
            result = await session.execute(
                "SELECT * FROM download_tasks WHERE id = :task_id",
                {"task_id": task_id}
            )
            task_row = result.fetchone()
            
            if not task_row:
                return {"success": False, "error": "Task not found"}
            
            if task_row.status not in ['failed', 'cancelled']:
                return {"success": False, "error": "Task cannot be retried"}
            
            # Подготавливаем к повтору
            await session.execute("""
                UPDATE download_tasks 
                SET status = 'pending',
                    started_at = NULL,
                    completed_at = NULL,
                    error_message = NULL,
                    retry_count = COALESCE(retry_count, 0) + 1
                WHERE id = :task_id
            """, {"task_id": task_id})
            await session.commit()
        
        # Запускаем новую задачу
        process_single_download.delay(task_id)
        
        return {"success": True, "task_id": task_id, "message": "Retry initiated"}
        
    except Exception as e:
        logger.error(f"Error in retry download: {e}")
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_cleanup_expired_async())
            return result
        finally:
            loop.close()
        
    except Exception as e:
        logger.error(f"Failed to cleanup expired downloads", error=str(e))
        return {"success": False, "error": str(e)}

async def _cleanup_expired_async() -> Dict[str, Any]:
    """Асинхронная очистка истекших загрузок"""
    try:
        cleaned_count = 0
        
        async with get_async_session() as session:
            # Находим истекшие задачи
            result = await session.execute("""
                SELECT id, local_file_path 
                FROM download_tasks 
                WHERE expires_at < NOW() 
                AND status = 'completed'
                AND local_file_path IS NOT NULL
                LIMIT 1000
            """)
            
            expired_tasks = result.fetchall()
            
            for task in expired_tasks:
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
        logger.error(f"Error in cleanup expired: {e}")
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_check_status_async(task_id))
            return result
        finally:
            loop.close()
        
    except Exception as e:
        logger.error(f"Failed to check download status", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}

async def _check_status_async(task_id: int) -> Dict[str, Any]:
    """Асинхронная проверка статуса"""
    try:
        async with get_async_session() as session:
            result = await session.execute(
                "SELECT * FROM download_tasks WHERE id = :task_id",
                {"task_id": task_id}
            )
            task_row = result.fetchone()
            
            if not task_row:
                return {"success": False, "error": "Task not found"}
            
            return {
                "success": True,
                "task_id": task_id,
                "status": task_row.status,
                "progress": task_row.progress_percent or 0,
                "created_at": task_row.created_at.isoformat() if task_row.created_at else None,
                "started_at": task_row.started_at.isoformat() if task_row.started_at else None,
                "completed_at": task_row.completed_at.isoformat() if task_row.completed_at else None,
                "error": task_row.error_message,
                "file_info": {
                    "name": task_row.file_name,
                    "size_bytes": task_row.file_size_bytes,
                    "format": task_row.file_format
                } if task_row.status == 'completed' else None
            }
            
    except Exception as e:
        logger.error(f"Error checking status: {e}")
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
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_cancel_task_async(task_id, user_id))
            return result
        finally:
            loop.close()
        
    except Exception as e:
        logger.error(f"Failed to cancel download task", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}

async def _cancel_task_async(task_id: int, user_id: int) -> Dict[str, Any]:
    """Асинхронная отмена задачи"""
    try:
        async with get_async_session() as session:
            result = await session.execute(
                "SELECT * FROM download_tasks WHERE id = :task_id",
                {"task_id": task_id}
            )
            task_row = result.fetchone()
            
            if not task_row:
                return {"success": False, "error": "Task not found"}
            
            # Проверяем права
            if task_row.user_id != user_id:
                return {"success": False, "error": "Access denied"}
            
            # Можно отменить только pending или processing задачи
            if task_row.status not in ['pending', 'processing']:
                return {"success": False, "error": "Task cannot be cancelled"}
            
            # Отменяем Celery задачу если есть
            if task_row.celery_task_id:
                celery_app.control.revoke(task_row.celery_task_id, terminate=True)
            
            # Обновляем статус
            await session.execute("""
                UPDATE download_tasks 
                SET status = 'cancelled',
                    completed_at = :completed_at
                WHERE id = :task_id
            """, {
                "completed_at": datetime.utcnow(),
                "task_id": task_id
            })
            await session.commit()
        
        logger.info(f"Download task cancelled", task_id=task_id)
        return {"success": True, "task_id": task_id}
        
    except Exception as e:
        logger.error(f"Error cancelling task: {e}")
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
        # Простая реализация без Redis
        return {
            "success": True,
            "task_id": task_id,
            "progress": {
                "percent": 0,
                "message": "Progress tracking not implemented",
                "status": "unknown"
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get download progress", task_id=task_id, error=str(e))
        return {"success": False, "error": str(e)}