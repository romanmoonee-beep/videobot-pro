"""
VideoBot Pro - Batch Tasks (ИСПРАВЛЕННАЯ ВЕРСИЯ)
Celery задачи для обработки групповых загрузок
"""

import time
import asyncio
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from celery import current_task, group
from sqlalchemy import text

from worker.celery_app import celery_app
from worker.tasks.base import async_task_wrapper

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
    
    try:
        # Используем обертку для async кода
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_process_batch_download_async(batch_id, self.request))
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Batch processing failed", batch_id=batch_id, error=str(e))
        return {"success": False, "error": str(e)}

async def _process_batch_download_async(batch_id: int, request_info) -> Dict[str, Any]:
    """Асинхронная обработка batch'а"""
    try:
        from shared.config.database import get_async_session
        
        start_time = time.time()
        
        async with get_async_session() as session:
            # Получаем batch из БД
            result = await session.execute(
                text("SELECT * FROM download_batches WHERE id = :batch_id"),
                {"batch_id": batch_id}
            )
            batch_row = result.fetchone()
            
            if not batch_row:
                raise ValueError(f"Batch {batch_id} not found")
            
            # Имитация обработки
            await asyncio.sleep(2)
            
            # Обновляем статус
            await session.execute(text("""
                UPDATE download_batches 
                SET status = 'completed',
                    completed_at = :completed_at
                WHERE id = :batch_id
            """), {
                "completed_at": datetime.utcnow(),
                "batch_id": batch_id
            })
            await session.commit()
        
        return {
            "success": True,
            "batch_id": batch_id,
            "processing_time": int(time.time() - start_time)
        }
        
    except Exception as e:
        logger.error(f"Error in batch processing: {e}")
        raise

@celery_app.task
def retry_failed_batch(batch_id: int) -> Dict[str, Any]:
    """Повторить неудачный batch"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_retry_batch_async(batch_id))
        finally:
            loop.close()
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _retry_batch_async(batch_id: int) -> Dict[str, Any]:
    """Async retry logic"""
    from shared.config.database import get_async_session
    
    async with get_async_session() as session:
        await session.execute(text("""
            UPDATE download_batches 
            SET status = 'pending'
            WHERE id = :batch_id
        """), {"batch_id": batch_id})
        await session.commit()
    
    # Запускаем новую обработку
    process_batch_download.delay(batch_id)
    return {"success": True, "batch_id": batch_id}

@celery_app.task
def create_batch_archive(batch_id: int, force: bool = False) -> Dict[str, Any]:
    """Создать архив для batch'а"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_create_archive_async(batch_id, force))
        finally:
            loop.close()
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _create_archive_async(batch_id: int, force: bool) -> Dict[str, Any]:
    """Async archive creation"""
    from shared.config.database import get_async_session
    
    logger.info(f"Creating batch archive", batch_id=batch_id, force=force)
    
    async with get_async_session() as session:
        batch = await session.execute(
            text("SELECT * FROM download_batches WHERE id = :batch_id"),
            {"batch_id": batch_id}
        )
        batch_row = batch.fetchone()
        
        if not batch_row:
            return {"success": False, "error": "Batch not found"}
        
        # Имитация создания архива
        await asyncio.sleep(1)
        
        return {
            "success": True,
            "batch_id": batch_id,
            "archive_path": f"/archives/batch_{batch_id}.zip"
        }

@celery_app.task
def cleanup_expired_batches() -> Dict[str, Any]:
    """Очистка истекших batch'ей"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_cleanup_expired_async())
        finally:
            loop.close()
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _cleanup_expired_async() -> Dict[str, Any]:
    """Async cleanup"""
    from shared.config.database import get_async_session
    
    logger.info("Starting cleanup of expired batches")
    
    cleaned_count = 0
    
    async with get_async_session() as session:
        expired_batches = await session.execute(text("""
            SELECT id FROM download_batches 
            WHERE created_at < NOW() - INTERVAL '24 hours'
            AND status = 'completed'
            LIMIT 500
        """))
        
        for batch in expired_batches.fetchall():
            try:
                await session.execute(text("""
                    UPDATE download_batches 
                    SET status = 'expired'
                    WHERE id = :batch_id
                """), {"batch_id": batch.id})
                
                cleaned_count += 1
                
            except Exception as e:
                logger.error(f"Failed to cleanup batch {batch.id}", error=str(e))
        
        await session.commit()
    
    logger.info(f"Cleaned up {cleaned_count} expired batches")
    return {"success": True, "cleaned_count": cleaned_count}

@celery_app.task
def check_batch_status(batch_id: int) -> Dict[str, Any]:
    """Проверить статус batch'а"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_check_status_async(batch_id))
        finally:
            loop.close()
    except Exception as e:
        return {"success": False, "error": str(e)}

async def _check_status_async(batch_id: int) -> Dict[str, Any]:
    """Async status check"""
    from shared.config.database import get_async_session
    
    async with get_async_session() as session:
        batch = await session.execute(
            text("SELECT * FROM download_batches WHERE id = :batch_id"),
            {"batch_id": batch_id}
        )
        batch_row = batch.fetchone()
        
        if not batch_row:
            return {"success": False, "error": "Batch not found"}
        
        return {
            "success": True,
            "batch_id": batch_id,
            "status": getattr(batch_row, 'status', 'unknown'),
            "created_at": getattr(batch_row, 'created_at', datetime.utcnow()).isoformat()
        }