"""
VideoBot Pro - Cleanup Tasks
Celery задачи для очистки и обслуживания системы
"""

import os
import shutil
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path

from worker.celery_app import celery_app
from shared.config.database import get_async_session, DatabaseHealthCheck, DatabaseMaintenance
from shared.models import DownloadTask, DownloadBatch, User, AnalyticsEvent
from worker.storage import StorageManager

logger = structlog.get_logger(__name__)

@celery_app.task
def cleanup_old_files(max_age_hours: int = 24) -> Dict[str, Any]:
    """
    Очистка старых файлов
    
    Args:
        max_age_hours: Максимальный возраст файлов в часах
        
    Returns:
        Статистика очистки
    """
    logger.info(f"Starting cleanup of files older than {max_age_hours} hours")
    
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        total_size_freed = 0
        files_deleted = 0
        
        async with get_async_session() as session:
            # Находим файлы для удаления
            expired_files = await session.execute("""
                SELECT id, local_file_path, file_size_bytes, expires_at
                FROM download_tasks 
                WHERE (expires_at < :cutoff_time OR created_at < :old_cutoff)
                AND local_file_path IS NOT NULL
                AND status = 'completed'
                LIMIT 1000
            """, {
                "cutoff_time": cutoff_time,
                "old_cutoff": datetime.utcnow() - timedelta(hours=max_age_hours * 2)
            })
            
            for file_record in expired_files.fetchall():
                try:
                    file_path = file_record.local_file_path
                    if file_path and os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        
                        total_size_freed += file_size
                        files_deleted += 1
                        
                        # Обновляем запись в БД
                        await session.execute("""
                            UPDATE download_tasks 
                            SET local_file_path = NULL,
                                updated_at = NOW()
                            WHERE id = :task_id
                        """, {"task_id": file_record.id})
                        
                        logger.debug(f"Deleted file: {file_path}")
                        
                except Exception as e:
                    logger.error(f"Failed to delete file {file_record.local_file_path}", error=str(e))
            
            await session.commit()
        
        # Очищаем пустые директории
        empty_dirs_removed = _cleanup_empty_directories()
        
        total_size_mb = total_size_freed / (1024 * 1024)
        
        logger.info(f"Cleanup completed", 
                   files_deleted=files_deleted, 
                   size_freed_mb=round(total_size_mb, 2),
                   empty_dirs_removed=empty_dirs_removed)
        
        return {
            "success": True,
            "files_deleted": files_deleted,
            "size_freed_mb": round(total_size_mb, 2),
            "empty_dirs_removed": empty_dirs_removed,
            "cutoff_time": cutoff_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup old files", error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def cleanup_temp_files() -> Dict[str, Any]:
    """
    Очистка временных файлов
    
    Returns:
        Статистика очистки
    """
    logger.info("Starting cleanup of temporary files")
    
    try:
        temp_dirs = [
            "/tmp/videobot",
            "/var/tmp/videobot", 
            "./temp",
            "./downloads/temp"
        ]
        
        total_size_freed = 0
        files_deleted = 0
        
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                size_freed, files_count = _cleanup_directory(
                    temp_dir, 
                    max_age_hours=1,  # Temp файлы старше 1 часа
                    recursive=True
                )
                total_size_freed += size_freed
                files_deleted += files_count
        
        # Очищаем старые логи yt-dlp
        ytdl_temp_size, ytdl_files = _cleanup_ytdlp_temp_files()
        total_size_freed += ytdl_temp_size
        files_deleted += ytdl_files
        
        total_size_mb = total_size_freed / (1024 * 1024)
        
        logger.info(f"Temp files cleanup completed",
                   files_deleted=files_deleted,
                   size_freed_mb=round(total_size_mb, 2))
        
        return {
            "success": True,
            "files_deleted": files_deleted,
            "size_freed_mb": round(total_size_mb, 2)
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup temp files", error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def cleanup_expired_cdn_links() -> Dict[str, Any]:
    """
    Очистка истекших CDN ссылок
    
    Returns:
        Статистика очистки
    """
    logger.info("Starting cleanup of expired CDN links")
    
    try:
        storage_manager = StorageManager()
        cleaned_count = 0
        
        async with get_async_session() as session:
            # Находим истекшие CDN ссылки
            expired_links = await session.execute("""
                SELECT id, cdn_url, file_name
                FROM download_tasks 
                WHERE expires_at < NOW()
                AND cdn_url IS NOT NULL
                AND status = 'completed'
                LIMIT 500
            """)
            
            for link_record in expired_links.fetchall():
                try:
                    # Удаляем файл из CDN
                    if link_record.cdn_url:
                        delete_result = await storage_manager.delete_file(
                            cdn_url=link_record.cdn_url,
                            file_name=link_record.file_name
                        )
                        
                        if delete_result.get("success"):
                            # Обновляем запись в БД
                            await session.execute("""
                                UPDATE download_tasks 
                                SET cdn_url = NULL,
                                    direct_download_url = NULL,
                                    status = 'expired',
                                    updated_at = NOW()
                                WHERE id = :task_id
                            """, {"task_id": link_record.id})
                            
                            cleaned_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to cleanup CDN link {link_record.cdn_url}", error=str(e))
            
            await session.commit()
        
        # Очищаем истекшие архивы batch'ей
        batch_archives_cleaned = await _cleanup_expired_batch_archives()
        
        logger.info(f"CDN cleanup completed",
                   cdn_links_cleaned=cleaned_count,
                   batch_archives_cleaned=batch_archives_cleaned)
        
        return {
            "success": True,
            "cdn_links_cleaned": cleaned_count,
            "batch_archives_cleaned": batch_archives_cleaned
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup expired CDN links", error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def vacuum_database() -> Dict[str, Any]:
    """
    Выполнить VACUUM и оптимизацию базы данных
    
    Returns:
        Результат операции
    """
    logger.info("Starting database vacuum and optimization")
    
    try:
        # Выполняем VACUUM
        vacuum_result = await DatabaseMaintenance.vacuum_tables()
        
        # Обновляем статистику таблиц
        await DatabaseMaintenance.update_table_statistics()
        
        # Очищаем старые аналитические события
        analytics_cleaned = await DatabaseMaintenance.cleanup_old_analytics(days=90)
        
        # Получаем статистику БД после очистки
        db_stats = await DatabaseHealthCheck.get_database_stats()
        
        logger.info(f"Database maintenance completed",
                   analytics_events_cleaned=analytics_cleaned,
                   database_size=db_stats.get("database_size"))
        
        return {
            "success": True,
            "vacuum_completed": True,
            "analytics_events_cleaned": analytics_cleaned,
            "database_stats": db_stats
        }
        
    except Exception as e:
        logger.error(f"Failed to vacuum database", error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def cleanup_analytics_events(days_to_keep: int = 30) -> Dict[str, Any]:
    """
    Очистка старых аналитических событий
    
    Args:
        days_to_keep: Сколько дней хранить события
        
    Returns:
        Статистика очистки
    """
    logger.info(f"Starting cleanup of analytics events older than {days_to_keep} days")
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        async with get_async_session() as session:
            # Удаляем старые события, которые уже обработаны
            result = await session.execute("""
                DELETE FROM analytics_events 
                WHERE created_at < :cutoff_date 
                AND is_processed = true
            """, {"cutoff_date": cutoff_date})
            
            deleted_count = result.rowcount
            await session.commit()
        
        logger.info(f"Analytics cleanup completed", deleted_events=deleted_count)
        
        return {
            "success": True,
            "deleted_events": deleted_count,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup analytics events", error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def health_check_task() -> Dict[str, Any]:
    """
    Проверка состояния системы
    
    Returns:
        Статус системы
    """
    logger.info("Starting system health check")
    
    try:
        health_status = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "healthy",
            "components": {}
        }
        
        # Проверка базы данных
        try:
            db_health = await DatabaseHealthCheck.check_connection()
            health_status["components"]["database"] = db_health
            
            if db_health["status"] != "healthy":
                health_status["overall_status"] = "degraded"
                
        except Exception as e:
            health_status["components"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["overall_status"] = "unhealthy"
        
        # Проверка дискового пространства
        try:
            disk_usage = _check_disk_usage()
            health_status["components"]["disk"] = disk_usage
            
            if disk_usage["usage_percent"] > 90:
                health_status["overall_status"] = "critical"
            elif disk_usage["usage_percent"] > 80:
                health_status["overall_status"] = "degraded"
                
        except Exception as e:
            health_status["components"]["disk"] = {
                "status": "unknown",
                "error": str(e)
            }
        
        # Проверка очередей Celery
        try:
            queue_health = _check_celery_queues()
            health_status["components"]["queues"] = queue_health
            
            if not queue_health["all_healthy"]:
                health_status["overall_status"] = "degraded"
                
        except Exception as e:
            health_status["components"]["queues"] = {
                "status": "unknown",
                "error": str(e)
            }
        
        # Проверка хранилища
        try:
            storage_manager = StorageManager()
            storage_health = await storage_manager.health_check()
            health_status["components"]["storage"] = storage_health
            
            if storage_health["status"] != "healthy":
                health_status["overall_status"] = "degraded"
                
        except Exception as e:
            health_status["components"]["storage"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Проверка активных задач
        try:
            active_tasks = _check_active_tasks()
            health_status["components"]["tasks"] = active_tasks
            
        except Exception as e:
            health_status["components"]["tasks"] = {
                "status": "unknown",
                "error": str(e)
            }
        
        logger.info(f"Health check completed", overall_status=health_status["overall_status"])
        
        return {
            "success": True,
            "health_status": health_status
        }
        
    except Exception as e:
        logger.error(f"Health check failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "health_status": {
                "overall_status": "unhealthy",
                "error": str(e)
            }
        }

@celery_app.task
def cleanup_failed_tasks(max_age_hours: int = 48) -> Dict[str, Any]:
    """
    Очистка застрявших и неудачных задач
    
    Args:
        max_age_hours: Максимальный возраст задач в часах
        
    Returns:
        Статистика очистки
    """
    logger.info(f"Starting cleanup of failed tasks older than {max_age_hours} hours")
    
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        async with get_async_session() as session:
            # Находим застрявшие задачи (processing но давно не обновлялись)
            stuck_tasks = await session.execute("""
                UPDATE download_tasks 
                SET status = 'failed',
                    error_message = 'Task stuck in processing state',
                    completed_at = NOW()
                WHERE status = 'processing' 
                AND updated_at < :cutoff_time
                RETURNING id
            """, {"cutoff_time": cutoff_time})
            
            stuck_count = len(stuck_tasks.fetchall())
            
            # Находим старые неудачные задачи для удаления
            old_failed = await session.execute("""
                DELETE FROM download_tasks 
                WHERE status IN ('failed', 'cancelled') 
                AND completed_at < :old_cutoff
                RETURNING id
            """, {"old_cutoff": datetime.utcnow() - timedelta(days=7)})
            
            deleted_count = len(old_failed.fetchall())
            
            # Аналогично для batch'ей
            stuck_batches = await session.execute("""
                UPDATE download_batches 
                SET status = 'failed',
                    error_messages = ARRAY['Batch stuck in processing state'],
                    completed_at = NOW()
                WHERE status = 'processing' 
                AND updated_at < :cutoff_time
                RETURNING id
            """, {"cutoff_time": cutoff_time})
            
            stuck_batches_count = len(stuck_batches.fetchall())
            
            await session.commit()
        
        logger.info(f"Failed tasks cleanup completed",
                   stuck_tasks=stuck_count,
                   deleted_tasks=deleted_count,
                   stuck_batches=stuck_batches_count)
        
        return {
            "success": True,
            "stuck_tasks_fixed": stuck_count,
            "old_tasks_deleted": deleted_count,
            "stuck_batches_fixed": stuck_batches_count
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup failed tasks", error=str(e))
        return {"success": False, "error": str(e)}

@celery_app.task
def optimize_storage() -> Dict[str, Any]:
    """
    Оптимизация использования хранилища
    
    Returns:
        Результат оптимизации
    """
    logger.info("Starting storage optimization")
    
    try:
        storage_manager = StorageManager()
        
        # Получаем статистику использования
        usage_stats = await storage_manager.get_usage_statistics()
        
        optimizations = {
            "duplicates_removed": 0,
            "orphaned_files_removed": 0,
            "space_freed_mb": 0.0
        }
        
        # Удаляем дубликаты файлов
        if usage_stats.get("has_duplicates", False):
            duplicate_result = await storage_manager.remove_duplicates()
            optimizations["duplicates_removed"] = duplicate_result.get("removed_count", 0)
            optimizations["space_freed_mb"] += duplicate_result.get("space_freed_mb", 0)
        
        # Удаляем потерянные файлы (без записей в БД)
        orphaned_result = await storage_manager.cleanup_orphaned_files()
        optimizations["orphaned_files_removed"] = orphaned_result.get("removed_count", 0)
        optimizations["space_freed_mb"] += orphaned_result.get("space_freed_mb", 0)
        
        # Сжимаем старые архивы если возможно
        compression_result = await storage_manager.compress_old_archives()
        optimizations["space_freed_mb"] += compression_result.get("space_saved_mb", 0)
        
        logger.info(f"Storage optimization completed", **optimizations)
        
        return {
            "success": True,
            "optimizations": optimizations,
            "usage_before": usage_stats,
            "usage_after": await storage_manager.get_usage_statistics()
        }
        
    except Exception as e:
        logger.error(f"Failed to optimize storage", error=str(e))
        return {"success": False, "error": str(e)}

# Вспомогательные функции

def _cleanup_directory(directory: str, max_age_hours: int = 24, recursive: bool = False) -> tuple:
    """Очистить директорию от старых файлов"""
    
    if not os.path.exists(directory):
        return 0, 0
    
    cutoff_time = time.time() - (max_age_hours * 3600)
    total_size = 0
    files_count = 0
    
    try:
        if recursive:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if os.path.getmtime(file_path) < cutoff_time:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            total_size += file_size
                            files_count += 1
                    except Exception:
                        continue
        else:
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    try:
                        if os.path.getmtime(file_path) < cutoff_time:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            total_size += file_size
                            files_count += 1
                    except Exception:
                        continue
    except Exception as e:
        logger.error(f"Error cleaning directory {directory}", error=str(e))
    
    return total_size, files_count

def _cleanup_empty_directories() -> int:
    """Удалить пустые директории"""
    
    directories_to_check = [
        "./downloads",
        "./temp", 
        "/tmp/videobot",
        "/var/tmp/videobot"
    ]
    
    removed_count = 0
    
    for base_dir in directories_to_check:
        if os.path.exists(base_dir):
            try:
                for root, dirs, files in os.walk(base_dir, topdown=False):
                    for directory in dirs:
                        dir_path = os.path.join(root, directory)
                        try:
                            if not os.listdir(dir_path):  # Директория пустая
                                os.rmdir(dir_path)
                                removed_count += 1
                        except Exception:
                            continue
            except Exception as e:
                logger.error(f"Error removing empty directories from {base_dir}", error=str(e))
    
    return removed_count

def _cleanup_ytdlp_temp_files() -> tuple:
    """Очистить временные файлы yt-dlp"""
    
    import tempfile
    temp_dir = tempfile.gettempdir()
    
    ytdlp_patterns = [
        "yt-dlp_*",
        "youtube-dl_*", 
        "*.tmp",
        "*.part"
    ]
    
    total_size = 0
    files_count = 0
    
    try:
        import glob
        
        for pattern in ytdlp_patterns:
            pattern_path = os.path.join(temp_dir, pattern)
            for file_path in glob.glob(pattern_path):
                try:
                    # Удаляем файлы старше 2 часов
                    if os.path.getmtime(file_path) < time.time() - 7200:
                        if os.path.isfile(file_path):
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            total_size += file_size
                            files_count += 1
                except Exception:
                    continue
                    
    except Exception as e:
        logger.error(f"Error cleaning yt-dlp temp files", error=str(e))
    
    return total_size, files_count

async def _cleanup_expired_batch_archives() -> int:
    """Очистить истекшие архивы batch'ей"""
    
    try:
        storage_manager = StorageManager()
        cleaned_count = 0
        
        async with get_async_session() as session:
            expired_archives = await session.execute("""
                SELECT id, archive_url 
                FROM download_batches 
                WHERE expires_at < NOW()
                AND archive_url IS NOT NULL
                AND status = 'completed'
                LIMIT 100
            """)
            
            for archive in expired_archives.fetchall():
                try:
                    if archive.archive_url:
                        delete_result = await storage_manager.delete_file(
                            cdn_url=archive.archive_url
                        )
                        
                        if delete_result.get("success"):
                            await session.execute("""
                                UPDATE download_batches 
                                SET archive_url = NULL,
                                    status = 'expired'
                                WHERE id = :batch_id
                            """, {"batch_id": archive.id})
                            
                            cleaned_count += 1
                            
                except Exception as e:
                    logger.error(f"Failed to cleanup archive {archive.archive_url}", error=str(e))
            
            await session.commit()
            
    except Exception as e:
        logger.error(f"Error cleaning expired batch archives", error=str(e))
    
    return cleaned_count

def _check_disk_usage() -> Dict[str, Any]:
    """Проверить использование дискового пространства"""
    
    try:
        import shutil
        
        # Проверяем основные директории
        paths_to_check = [
            "/",  # Root
            "./",  # Current directory
            "/tmp",  # Temp
            "/var/tmp"  # Var temp
        ]
        
        disk_info = {}
        max_usage = 0
        
        for path in paths_to_check:
            if os.path.exists(path):
                try:
                    total, used, free = shutil.disk_usage(path)
                    usage_percent = (used / total) * 100
                    
                    disk_info[path] = {
                        "total_gb": round(total / (1024**3), 2),
                        "used_gb": round(used / (1024**3), 2),
                        "free_gb": round(free / (1024**3), 2),
                        "usage_percent": round(usage_percent, 1)
                    }
                    
                    max_usage = max(max_usage, usage_percent)
                    
                except Exception:
                    continue
        
        status = "healthy"
        if max_usage > 90:
            status = "critical"
        elif max_usage > 80:
            status = "warning"
        
        return {
            "status": status,
            "usage_percent": max_usage,
            "paths": disk_info
        }
        
    except Exception as e:
        return {
            "status": "unknown",
            "error": str(e)
        }

def _check_celery_queues() -> Dict[str, Any]:
    """Проверить состояние очередей Celery"""
    
    try:
        inspect = celery_app.control.inspect()
        
        # Получаем информацию об активных задачах
        active_tasks = inspect.active()
        reserved_tasks = inspect.reserved()
        
        queue_stats = {
            "downloads": {"active": 0, "reserved": 0},
            "notifications": {"active": 0, "reserved": 0},
            "cleanup": {"active": 0, "reserved": 0},
            "analytics": {"active": 0, "reserved": 0}
        }
        
        # Подсчитываем задачи по очередям
        if active_tasks:
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    queue = task.get("delivery_info", {}).get("routing_key", "default")
                    if queue in queue_stats:
                        queue_stats[queue]["active"] += 1
        
        if reserved_tasks:
            for worker, tasks in reserved_tasks.items():
                for task in tasks:
                    queue = task.get("delivery_info", {}).get("routing_key", "default")
                    if queue in queue_stats:
                        queue_stats[queue]["reserved"] += 1
        
        # Проверяем на застрявшие задачи
        total_active = sum(q["active"] for q in queue_stats.values())
        total_reserved = sum(q["reserved"] for q in queue_stats.values())
        
        all_healthy = total_active < 100 and total_reserved < 500  # Пороговые значения
        
        return {
            "all_healthy": all_healthy,
            "total_active": total_active,
            "total_reserved": total_reserved,
            "queues": queue_stats
        }
        
    except Exception as e:
        return {
            "all_healthy": False,
            "error": str(e)
        }

def _check_active_tasks() -> Dict[str, Any]:
    """Проверить активные задачи"""
    
    try:
        async with get_async_session() as session:
            # Подсчитываем задачи по статусам
            task_stats = await session.execute("""
                SELECT status, COUNT(*) as count
                FROM download_tasks 
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY status
            """)
            
            status_counts = {row.status: row.count for row in task_stats.fetchall()}
            
            # Подсчитываем batch'и
            batch_stats = await session.execute("""
                SELECT status, COUNT(*) as count
                FROM download_batches 
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY status
            """)
            
            batch_counts = {row.status: row.count for row in batch_stats.fetchall()}
            
            # Проверяем на проблемы
            processing_tasks = status_counts.get("processing", 0)
            processing_batches = batch_counts.get("processing", 0)
            
            is_healthy = processing_tasks < 50 and processing_batches < 10
            
            return {
                "status": "healthy" if is_healthy else "warning",
                "tasks": status_counts,
                "batches": batch_counts,
                "processing_tasks": processing_tasks,
                "processing_batches": processing_batches
            }
            
    except Exception as e:
        return {
            "status": "unknown",
            "error": str(e)
        }