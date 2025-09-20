"""
VideoBot Pro - Admin Downloads API
API для управления скачиваниями в админ панели
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import func, and_, or_, desc, asc, text
from sqlalchemy.orm import selectinload
import structlog

from shared.schemas.download import (
    DownloadTaskSchema, DownloadBatchSchema, DownloadQuerySchema,
    DownloadStatsSchema, BatchStatusSchema, TaskRetrySchema,
    BatchRetrySchema, DownloadHistorySchema
)
from shared.models import DownloadTask, DownloadBatch, User, DownloadStatus, Platform
from shared.services.database import get_db_session
from shared.services.analytics import AnalyticsService
from ..dependencies import get_current_admin, require_permission, get_analytics_service
from ..utils.export import export_downloads_to_csv, export_downloads_to_excel

logger = structlog.get_logger(__name__)
router = APIRouter()

@router.get("/", response_model=DownloadHistorySchema)
async def get_downloads(
    query: DownloadQuerySchema = Depends(),
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Получение списка скачиваний с фильтрацией и пагинацией
    """
    try:
        async with get_db_session() as session:
            # Базовый запрос
            base_query = session.query(DownloadTask).options(
                selectinload(DownloadTask.user),
                selectinload(DownloadTask.batch)
            )
            
            # Применяем фильтры
            if query.user_id:
                base_query = base_query.filter(DownloadTask.user_id == query.user_id)
            
            if query.status:
                base_query = base_query.filter(DownloadTask.status == query.status)
            
            if query.platform:
                base_query = base_query.filter(DownloadTask.platform == query.platform)
            
            if query.date_from:
                base_query = base_query.filter(DownloadTask.created_at >= query.date_from)
            
            if query.date_to:
                base_query = base_query.filter(DownloadTask.created_at <= query.date_to)
            
            # Сортировка
            sort_column = getattr(DownloadTask, query.sort_by, DownloadTask.created_at)
            if query.sort_order == "desc":
                base_query = base_query.order_by(desc(sort_column))
            else:
                base_query = base_query.order_by(asc(sort_column))
            
            # Подсчет общего количества
            total = await base_query.count()
            
            # Пагинация
            offset = (query.page - 1) * query.per_page
            tasks = await base_query.offset(offset).limit(query.per_page).all()
            
            # Преобразуем в схемы
            task_schemas = []
            for task in tasks:
                task_dict = task.to_dict()
                
                # Добавляем информацию о пользователе
                if task.user:
                    task_dict.update({
                        "user_username": task.user.username,
                        "user_type": task.user.current_user_type,
                        "user_telegram_id": task.user.telegram_id
                    })
                
                # Добавляем информацию о batch
                if task.batch:
                    task_dict.update({
                        "batch_id": task.batch.batch_id,
                        "batch_total_urls": task.batch.total_urls
                    })
                
                # Вычисляемые поля
                task_dict.update({
                    "file_size_mb": task.file_size_mb if hasattr(task, 'file_size_mb') else None,
                    "is_expired": task.expires_at and datetime.utcnow() > task.expires_at if task.expires_at else False,
                    "processing_time": (
                        (task.completed_at - task.started_at).total_seconds()
                        if task.started_at and task.completed_at else None
                    ),
                    "can_retry": task.status in ['failed'] and (task.retry_count or 0) < 3
                })
                
                task_schemas.append(DownloadTaskSchema.model_validate(task_dict))
            
            pages = (total + query.per_page - 1) // query.per_page
            
            return DownloadHistorySchema(
                tasks=task_schemas,
                total=total,
                page=query.page,
                pages=pages,
                per_page=query.per_page
            )
            
    except Exception as e:
        logger.error(f"Error getting downloads: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении списка скачиваний"
        )

@router.get("/batches")
async def get_download_batches(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Получение списка batch скачиваний
    """
    try:
        async with get_db_session() as session:
            # Базовый запрос
            query = session.query(DownloadBatch).options(
                selectinload(DownloadBatch.user),
                selectinload(DownloadBatch.download_tasks)
            )
            
            # Фильтры
            if status:
                query = query.filter(DownloadBatch.status == status)
            
            if user_id:
                query = query.filter(DownloadBatch.user_id == user_id)
            
            # Сортировка по дате создания (новые первыми)
            query = query.order_by(desc(DownloadBatch.created_at))
            
            # Подсчет и пагинация
            total = await query.count()
            offset = (page - 1) * per_page
            batches = await query.offset(offset).limit(per_page).all()
            
            # Преобразуем в схемы
            batch_schemas = []
            for batch in batches:
                batch_dict = batch.to_dict()
                
                # Добавляем информацию о пользователе
                if batch.user:
                    batch_dict.update({
                        "user_username": batch.user.username,
                        "user_type": batch.user.current_user_type,
                        "user_telegram_id": batch.user.telegram_id
                    })
                
                # Статистика задач
                if batch.download_tasks:
                    completed = len([t for t in batch.download_tasks if t.status == 'completed'])
                    failed = len([t for t in batch.download_tasks if t.status == 'failed'])
                    total_tasks = len(batch.download_tasks)
                    
                    batch_dict.update({
                        "completed_count": completed,
                        "failed_count": failed,
                        "total_count": total_tasks,
                        "progress_percent": (completed / total_tasks * 100) if total_tasks > 0 else 0,
                        "success_rate": (completed / total_tasks * 100) if total_tasks > 0 else 0
                    })
                
                # Вычисляемые поля
                batch_dict.update({
                    "is_expired": batch.expires_at and datetime.utcnow() > batch.expires_at if batch.expires_at else False,
                    "processing_time_hours": (
                        (batch.completed_at - batch.started_at).total_seconds() / 3600
                        if batch.started_at and batch.completed_at else None
                    )
                })
                
                batch_schemas.append(DownloadBatchSchema.model_validate(batch_dict))
            
            pages = (total + per_page - 1) // per_page
            
            return {
                "batches": batch_schemas,
                "total": total,
                "page": page,
                "pages": pages,
                "per_page": per_page
            }
            
    except Exception as e:
        logger.error(f"Error getting download batches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении списка batch скачиваний"
        )

@router.get("/{task_id}", response_model=DownloadTaskSchema)
async def get_download_task(
    task_id: int,
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Получение детальной информации о задаче скачивания
    """
    try:
        async with get_db_session() as session:
            task = await session.get(DownloadTask, task_id)
            
            if not task:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Задача скачивания не найдена"
                )
            
            # Загружаем связанные данные
            await session.refresh(task, ['user', 'batch'])
            
            task_dict = task.to_dict()
            
            # Добавляем информацию о пользователе
            if task.user:
                task_dict.update({
                    "user_username": task.user.username,
                    "user_type": task.user.current_user_type,
                    "user_telegram_id": task.user.telegram_id,
                    "user_full_name": f"{task.user.first_name or ''} {task.user.last_name or ''}".strip()
                })
            
            # Добавляем информацию о batch
            if task.batch:
                task_dict.update({
                    "batch_info": {
                        "batch_id": task.batch.batch_id,
                        "total_urls": task.batch.total_urls,
                        "status": task.batch.status,
                        "delivery_method": task.batch.delivery_method
                    }
                })
            
            # Вычисляемые поля
            task_dict.update({
                "file_size_mb": task.file_size_bytes / (1024 * 1024) if task.file_size_bytes else None,
                "is_completed": task.status == 'completed',
                "is_failed": task.status == 'failed',
                "can_retry": task.status in ['failed'] and (task.retry_count or 0) < 3,
                "processing_time": (
                    (task.completed_at - task.started_at).total_seconds()
                    if task.started_at and task.completed_at else None
                ),
                "is_expired": task.expires_at and datetime.utcnow() > task.expires_at if task.expires_at else False
            })
            
            return DownloadTaskSchema.model_validate(task_dict)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting download task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении информации о задаче"
        )

@router.get("/batches/{batch_id}", response_model=DownloadBatchSchema)
async def get_download_batch(
    batch_id: int,
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Получение детальной информации о batch скачивания
    """
    try:
        async with get_db_session() as session:
            batch = await session.get(DownloadBatch, batch_id)
            
            if not batch:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Batch скачивания не найден"
                )
            
            # Загружаем связанные данные
            await session.refresh(batch, ['user', 'download_tasks'])
            
            batch_dict = batch.to_dict()
            
            # Добавляем информацию о пользователе
            if batch.user:
                batch_dict.update({
                    "user_username": batch.user.username,
                    "user_type": batch.user.current_user_type,
                    "user_telegram_id": batch.user.telegram_id,
                    "user_full_name": f"{batch.user.first_name or ''} {batch.user.last_name or ''}".strip()
                })
            
            # Статистика задач в batch
            if batch.download_tasks:
                tasks_by_status = {}
                total_size = 0
                platform_stats = {}
                
                for task in batch.download_tasks:
                    # Статистика по статусам
                    status_key = task.status
                    tasks_by_status[status_key] = tasks_by_status.get(status_key, 0) + 1
                    
                    # Размер файлов
                    if task.file_size_bytes:
                        total_size += task.file_size_bytes
                    
                    # Статистика по платформам
                    platform = task.platform or 'unknown'
                    platform_stats[platform] = platform_stats.get(platform, 0) + 1
                
                batch_dict["tasks_by_status"] = tasks_by_status
                batch_dict["total_size_mb"] = total_size / (1024 * 1024) if total_size > 0 else 0
                batch_dict["platform_stats"] = platform_stats
                
                # Последние задачи
                recent_tasks = sorted(
                    batch.download_tasks, 
                    key=lambda x: x.created_at, 
                    reverse=True
                )[:10]
                
                batch_dict["recent_tasks"] = [
                    {
                        "id": task.id,
                        "original_url": task.original_url,
                        "status": task.status,
                        "platform": task.platform,
                        "video_title": task.video_title,
                        "file_size_mb": task.file_size_bytes / (1024 * 1024) if task.file_size_bytes else None
                    }
                    for task in recent_tasks
                ]
                
                # Прогресс
                completed = tasks_by_status.get('completed', 0)
                total_tasks = len(batch.download_tasks)
                batch_dict["progress_percent"] = (completed / total_tasks * 100) if total_tasks > 0 else 0
                batch_dict["success_rate"] = (completed / total_tasks * 100) if total_tasks > 0 else 0
            
            # Вычисляемые поля
            batch_dict.update({
                "is_expired": batch.expires_at and datetime.utcnow() > batch.expires_at if batch.expires_at else False,
                "processing_time_hours": (
                    (batch.completed_at - batch.started_at).total_seconds() / 3600
                    if batch.started_at and batch.completed_at else None
                )
            })
            
            return DownloadBatchSchema.model_validate(batch_dict)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting download batch {batch_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении информации о batch"
        )

@router.post("/{task_id}/retry")
async def retry_download_task(
    task_id: int,
    retry_data: TaskRetrySchema,
    background_tasks: BackgroundTasks,
    current_admin = Depends(require_permission("downloads_retry")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Повторная попытка скачивания задачи
    """
    try:
        async with get_db_session() as session:
            task = await session.get(DownloadTask, task_id)
            
            if not task:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Задача скачивания не найдена"
                )
            
            if task.status not in ['failed', 'cancelled']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Задача не может быть повторена"
                )
            
            if (task.retry_count or 0) >= 3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Превышено максимальное количество попыток"
                )
            
            # Сбрасываем статус задачи
            task.status = DownloadStatus.PENDING
            task.progress_percent = 0
            task.error_message = None
            task.completed_at = None
            task.started_at = None
            task.retry_count = (task.retry_count or 0) + 1
            
            # Обновляем параметры если переданы
            if retry_data.new_quality:
                task.requested_quality = retry_data.new_quality
            
            if retry_data.new_format:
                task.requested_format = retry_data.new_format
            
            await session.commit()
            
            # Записываем в аналитику
            background_tasks.add_task(
                analytics_service.track_download_event,
                event_type="download_retried",
                user_id=task.user_id,
                platform=task.platform,
                event_data={
                    "task_id": task.id,
                    "retry_count": task.retry_count,
                    "retried_by_admin": current_admin.id,
                    "new_quality": retry_data.new_quality,
                    "new_format": retry_data.new_format
                }
            )
            
            # TODO: Здесь добавить задачу в очередь Celery для повторной обработки
            # from worker.tasks.download_tasks import process_single_download
            # process_single_download.delay(task.id)
            
            logger.info(
                f"Download task retry initiated",
                task_id=task_id,
                retry_count=task.retry_count,
                admin_id=current_admin.id
            )
            
            return {"message": "Задача поставлена на повторное скачивание"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying download task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при повторной попытке скачивания"
        )

@router.post("/batches/{batch_id}/retry")
async def retry_download_batch(
    batch_id: int,
    retry_data: BatchRetrySchema,
    background_tasks: BackgroundTasks,
    current_admin = Depends(require_permission("downloads_retry")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Повторная попытка скачивания batch'а
    """
    try:
        async with get_db_session() as session:
            batch = await session.get(DownloadBatch, batch_id)
            
            if not batch:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Batch скачивания не найден"
                )
            
            # Загружаем связанные задачи
            await session.refresh(batch, ['download_tasks'])
            
            # Определяем какие задачи повторять
            tasks_to_retry = []
            if retry_data.retry_failed_only:
                tasks_to_retry = [
                    task for task in batch.download_tasks 
                    if task.status == 'failed' and (task.retry_count or 0) < 3
                ]
            else:
                tasks_to_retry = [
                    task for task in batch.download_tasks 
                    if task.status in ['failed', 'cancelled'] and (task.retry_count or 0) < 3
                ]
            
            if not tasks_to_retry:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Нет задач для повтора в данном batch'е"
                )
            
            # Сбрасываем статус batch'а если он завершен
            if batch.status in ['completed', 'failed']:
                batch.status = 'processing'
                batch.completed_at = None
            
            # Сбрасываем статус задач
            retried_count = 0
            for task in tasks_to_retry:
                task.status = 'pending'
                task.progress_percent = 0
                task.error_message = None
                task.completed_at = None
                task.started_at = None
                task.retry_count = (task.retry_count or 0) + 1
                
                # Обновляем параметры
                if retry_data.new_quality:
                    task.requested_quality = retry_data.new_quality
                
                retried_count += 1
            
            await session.commit()
            
            # Записываем в аналитику
            background_tasks.add_task(
                analytics_service.track_download_event,
                event_type="batch_retried",
                user_id=batch.user_id,
                platform="batch",
                event_data={
                    "batch_id": batch.id,
                    "tasks_retried": retried_count,
                    "retry_failed_only": retry_data.retry_failed_only,
                    "retried_by_admin": current_admin.id
                }
            )
            
            # TODO: Добавить задачи в очередь Celery
            
            logger.info(
                f"Download batch retry initiated",
                batch_id=batch_id,
                tasks_retried=retried_count,
                admin_id=current_admin.id
            )
            
            return {
                "message": f"Запущено повторное скачивание для {retried_count} задач",
                "retried_tasks": retried_count
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying download batch {batch_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при повторной попытке скачивания batch'а"
        )

@router.delete("/{task_id}")
async def cancel_download_task(
    task_id: int,
    current_admin = Depends(require_permission("downloads_cancel")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Отмена задачи скачивания
    """
    try:
        async with get_db_session() as session:
            task = await session.get(DownloadTask, task_id)
            
            if not task:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Задача скачивания не найдена"
                )
            
            if task.status in ['completed', 'failed', 'cancelled']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Задача уже завершена или отменена"
                )
            
            # Отменяем задачу
            task.status = 'cancelled'
            task.completed_at = datetime.utcnow()
            task.error_message = f"Отменено администратором {current_admin.username}"
            
            await session.commit()
            
            # Аналитика
            await analytics_service.track_download_event(
                event_type="download_cancelled",
                user_id=task.user_id,
                platform=task.platform,
                event_data={
                    "task_id": task.id,
                    "cancelled_by_admin": current_admin.id,
                    "original_status": task.status
                }
            )
            
            # TODO: Отменить задачу в Celery
            
            logger.info(
                f"Download task cancelled",
                task_id=task_id,
                admin_id=current_admin.id
            )
            
            return {"message": "Задача скачивания отменена"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling download task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при отмене задачи"
        )

@router.delete("/batches/{batch_id}")
async def cancel_download_batch(
    batch_id: int,
    current_admin = Depends(require_permission("downloads_cancel")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Отмена batch'а скачивания
    """
    try:
        async with get_db_session() as session:
            batch = await session.get(DownloadBatch, batch_id)
            
            if not batch:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Batch скачивания не найден"
                )
            
            if batch.status in ['completed', 'failed', 'cancelled']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Batch уже завершен или отменен"
                )
            
            # Загружаем задачи
            await session.refresh(batch, ['download_tasks'])
            
            # Отменяем batch и все активные задачи
            batch.status = 'cancelled'
            batch.completed_at = datetime.utcnow()
            
            cancelled_tasks = 0
            for task in batch.download_tasks:
                if task.status in ['pending', 'processing']:
                    task.status = 'cancelled'
                    task.completed_at = datetime.utcnow()
                    task.error_message = f"Отменено с batch'ем администратором {current_admin.username}"
                    cancelled_tasks += 1
            
            await session.commit()
            
            # Аналитика
            await analytics_service.track_download_event(
                event_type="batch_cancelled",
                user_id=batch.user_id,
                platform="batch",
                event_data={
                    "batch_id": batch.id,
                    "cancelled_tasks": cancelled_tasks,
                    "cancelled_by_admin": current_admin.id
                }
            )
            
            logger.info(
                f"Download batch cancelled",
                batch_id=batch_id,
                cancelled_tasks=cancelled_tasks,
                admin_id=current_admin.id
            )
            
            return {
                "message": f"Batch отменен, отменено {cancelled_tasks} активных задач",
                "cancelled_tasks": cancelled_tasks
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling download batch {batch_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при отмене batch'а"
        )

@router.get("/stats/overview", response_model=DownloadStatsSchema)
async def get_downloads_overview(
    days: int = Query(30, ge=1, le=365, description="Период анализа"),
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Общая статистика скачиваний
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Основные счетчики
            total_downloads = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE created_at >= :start_date"),
                {"start_date": start_date}
            )
            total_downloads = total_downloads.scalar()
            
            successful_downloads = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE created_at >= :start_date AND status = 'completed'"),
                {"start_date": start_date}
            )
            successful_downloads = successful_downloads.scalar()
            
            failed_downloads = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE created_at >= :start_date AND status = 'failed'"),
                {"start_date": start_date}
            )
            failed_downloads = failed_downloads.scalar()
            
            success_rate = (successful_downloads / max(total_downloads, 1)) * 100
            
            # Статистика по платформам
            platform_stats = await session.execute(text("""
                SELECT 
                    platform,
                    COUNT(*) as count
                FROM download_tasks 
                WHERE created_at >= :start_date
                GROUP BY platform
                ORDER BY count DESC
            """), {"start_date": start_date})
            
            youtube_downloads = 0
            tiktok_downloads = 0
            instagram_downloads = 0
            
            for row in platform_stats.fetchall():
                if row.platform == 'youtube':
                    youtube_downloads = row.count
                elif row.platform == 'tiktok':
                    tiktok_downloads = row.count
                elif row.platform == 'instagram':
                    instagram_downloads = row.count
            
            # Размеры файлов
            file_size_stats = await session.execute(text("""
                SELECT 
                    SUM(file_size_bytes) as total_size,
                    AVG(file_size_bytes) as avg_size
                FROM download_tasks 
                WHERE created_at >= :start_date 
                AND file_size_bytes IS NOT NULL
            """), {"start_date": start_date})
            
            file_stats = file_size_stats.fetchone()
            total_file_size_gb = (file_stats.total_size or 0) / (1024**3)
            avg_file_size_mb = (file_stats.avg_size or 0) / (1024**2)
            
            # Время обработки
            processing_time_stats = await session.execute(text("""
                SELECT 
                    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_time,
                    SUM(EXTRACT(EPOCH FROM (completed_at - started_at))) as total_time
                FROM download_tasks 
                WHERE created_at >= :start_date
                AND started_at IS NOT NULL 
                AND completed_at IS NOT NULL
            """), {"start_date": start_date})
            
            time_stats = processing_time_stats.fetchone()
            avg_processing_time_seconds = float(time_stats.avg_time or 0)
            total_processing_time_hours = (time_stats.total_time or 0) / 3600
            
            # Распределение по качеству
            quality_stats = await session.execute(text("""
                SELECT 
                    actual_quality,
                    COUNT(*) as count
                FROM download_tasks 
                WHERE created_at >= :start_date
                GROUP BY actual_quality
                ORDER BY count DESC
            """), {"start_date": start_date})
            
            quality_distribution = {}
            for row in quality_stats.fetchall():
                quality = row.actual_quality or "unknown"
                quality_distribution[quality] = row.count
            
            # Скачивания за периоды
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)
            month_start = today_start - timedelta(days=30)
            
            downloads_today = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE created_at >= :today"),
                {"today": today_start}
            )
            downloads_today = downloads_today.scalar()
            
            downloads_this_week = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE created_at >= :week"),
                {"week": week_start}
            )
            downloads_this_week = downloads_this_week.scalar()
            
            downloads_this_month = await session.execute(
                text("SELECT COUNT(*) FROM download_tasks WHERE created_at >= :month"),
                {"month": month_start}
            )
            downloads_this_month = downloads_this_month.scalar()
            
            return DownloadStatsSchema(
                total_downloads=total_downloads,
                successful_downloads=successful_downloads,
                failed_downloads=failed_downloads,
                success_rate=round(success_rate, 2),
                youtube_downloads=youtube_downloads,
                tiktok_downloads=tiktok_downloads,
                instagram_downloads=instagram_downloads,
                total_file_size_gb=round(total_file_size_gb, 2),
                avg_file_size_mb=round(avg_file_size_mb, 2),
                avg_processing_time_seconds=round(avg_processing_time_seconds, 2),
                total_processing_time_hours=round(total_processing_time_hours, 2),
                quality_distribution=quality_distribution,
                format_distribution={"mp4": total_downloads},  # TODO: Добавить поле format
                downloads_today=downloads_today,
                downloads_this_week=downloads_this_week,
                downloads_this_month=downloads_this_month
            )
            
    except Exception as e:
        logger.error(f"Error getting downloads overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении статистики скачиваний"
        )

@router.get("/export")
async def export_downloads(
    format: str = Query("csv", regex="^(csv|excel)$"),
    days: int = Query(30, ge=1, le=365),
    status: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Экспорт данных скачиваний
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Базовый запрос
            query_text = """
                SELECT 
                    dt.*,
                    u.username,
                    u.first_name,
                    u.last_name,
                    u.user_type,
                    u.telegram_id as user_telegram_id
                FROM download_tasks dt
                LEFT JOIN users u ON dt.user_id = u.id
                WHERE dt.created_at >= :start_date
            """
            params = {"start_date": start_date}
            
            # Применяем фильтры
            if status:
                query_text += " AND dt.status = :status"
                params["status"] = status
            
            if platform:
                query_text += " AND dt.platform = :platform"
                params["platform"] = platform
            
            query_text += " ORDER BY dt.created_at DESC"
            
            result = await session.execute(text(query_text), params)
            tasks = result.fetchall()
            
            if format == "excel":
                return await export_downloads_to_excel(tasks)
            else:
                return await export_downloads_to_csv(tasks)
                
    except Exception as e:
        logger.error(f"Error exporting downloads: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при экспорте данных"
        )

@router.post("/cleanup")
async def cleanup_old_downloads(
    days: int = Query(7, ge=1, le=365, description="Удалить задачи старше N дней"),
    only_completed: bool = Query(True, description="Удалять только завершенные задачи"),
    current_admin = Depends(require_permission("system_maintenance"))
):
    """
    Очистка старых задач скачивания
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Базовый запрос
            query_text = "DELETE FROM download_tasks WHERE created_at < :cutoff_date"
            params = {"cutoff_date": cutoff_date}
            
            # Если только завершенные - добавляем фильтр
            if only_completed:
                query_text += " AND status IN ('completed', 'failed', 'cancelled')"
            
            # Подсчитываем количество для удаления
            count_query = query_text.replace("DELETE FROM", "SELECT COUNT(*) FROM")
            count_result = await session.execute(text(count_query), params)
            count_to_delete = count_result.scalar()
            
            if count_to_delete == 0:
                return {"message": "Нет задач для удаления", "deleted_count": 0}
            
            # Удаляем задачи
            result = await session.execute(text(query_text), params)
            deleted_count = result.rowcount
            await session.commit()
            
            logger.info(
                f"Cleanup completed",
                deleted_count=deleted_count,
                cutoff_date=cutoff_date,
                admin_id=current_admin.id
            )
            
            return {
                "message": f"Удалено {deleted_count} задач",
                "deleted_count": deleted_count,
                "cutoff_date": cutoff_date.isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error cleaning up downloads: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при очистке задач"
        )

@router.get("/analytics/platform-stats")
async def get_platform_analytics(
    days: int = Query(30, ge=1, le=365),
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Аналитика по платформам
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            result = await session.execute(text("""
                SELECT 
                    platform,
                    COUNT(*) as total_downloads,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                    AVG(CASE WHEN file_size_bytes > 0 THEN file_size_bytes END) as avg_file_size,
                    SUM(CASE WHEN file_size_bytes > 0 THEN file_size_bytes END) as total_file_size,
                    AVG(CASE WHEN started_at IS NOT NULL AND completed_at IS NOT NULL 
                         THEN EXTRACT(EPOCH FROM (completed_at - started_at)) END) as avg_processing_time
                FROM download_tasks 
                WHERE created_at >= :start_date 
                GROUP BY platform
                ORDER BY total_downloads DESC
            """), {"start_date": start_date})
            
            platform_stats = []
            for row in result.fetchall():
                success_rate = (row.successful / row.total_downloads * 100) if row.total_downloads > 0 else 0
                
                platform_stats.append({
                    "platform": row.platform or "unknown",
                    "total_downloads": row.total_downloads,
                    "successful": row.successful,
                    "failed": row.failed,
                    "success_rate": round(success_rate, 2),
                    "avg_file_size_mb": round((row.avg_file_size or 0) / (1024 * 1024), 2),
                    "total_file_size_gb": round((row.total_file_size or 0) / (1024 * 1024 * 1024), 2),
                    "avg_processing_time_seconds": round(row.avg_processing_time or 0, 2)
                })
            
            return {
                "period_days": days,
                "platforms": platform_stats,
                "total_platforms": len(platform_stats)
            }
            
    except Exception as e:
        logger.error(f"Error getting platform analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении аналитики платформ"
        )

@router.get("/analytics/daily-trend")
async def get_daily_downloads_trend(
    days: int = Query(30, ge=1, le=365),
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Тренд скачиваний по дням
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            result = await session.execute(text("""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as total_downloads,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_downloads,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_downloads,
                    SUM(CASE WHEN file_size_bytes > 0 THEN file_size_bytes END) as total_size
                FROM download_tasks 
                WHERE created_at >= :start_date
                GROUP BY DATE(created_at)
                ORDER BY date
            """), {"start_date": start_date})
            
            daily_data = []
            for row in result.fetchall():
                success_rate = (row.successful_downloads / row.total_downloads * 100) if row.total_downloads > 0 else 0
                
                daily_data.append({
                    "date": row.date.isoformat(),
                    "total_downloads": row.total_downloads,
                    "successful_downloads": row.successful_downloads,
                    "failed_downloads": row.failed_downloads,
                    "success_rate": round(success_rate, 2),
                    "total_size_mb": round((row.total_size or 0) / (1024 * 1024), 2)
                })
            
            return {
                "period_days": days,
                "daily_data": daily_data,
                "total_days": len(daily_data)
            }
            
    except Exception as e:
        logger.error(f"Error getting daily trend: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении тренда"
        )

@router.get("/analytics/top-errors")
async def get_top_download_errors(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    current_admin = Depends(require_permission("downloads_view"))
):
    """
    Топ ошибок скачивания
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            result = await session.execute(text("""
                SELECT 
                    error_message,
                    COUNT(*) as count,
                    platform,
                    COUNT(DISTINCT user_id) as affected_users
                FROM download_tasks 
                WHERE created_at >= :start_date 
                AND status = 'failed'
                AND error_message IS NOT NULL
                GROUP BY error_message, platform
                ORDER BY count DESC
                LIMIT :limit
            """), {"start_date": start_date, "limit": limit})
            
            top_errors = []
            for row in result.fetchall():
                # Сокращаем длинные сообщения об ошибках
                error_message = row.error_message
                if len(error_message) > 100:
                    error_message = error_message[:97] + "..."
                
                top_errors.append({
                    "error_message": error_message,
                    "count": row.count,
                    "platform": row.platform,
                    "affected_users": row.affected_users
                })
            
            return {
                "period_days": days,
                "top_errors": top_errors,
                "total_error_types": len(top_errors)
            }
            
    except Exception as e:
        logger.error(f"Error getting top errors: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении топа ошибок"
        )