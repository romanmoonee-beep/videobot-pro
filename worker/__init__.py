"""
VideoBot Pro - Worker Package
Асинхронный обработчик задач на основе Celery
"""

__version__ = "2.1.0"
__description__ = "VideoBot Pro Worker - Asynchronous task processor"

# Экспорт основных компонентов
from .celery_app import celery_app, create_celery_app
from .config import worker_config, WorkerConfig
from .tasks import (
    # Download tasks
    process_single_download,
    process_batch_download,
    retry_failed_download,
    
    # Cleanup tasks
    cleanup_expired_files,
    cleanup_old_batches,
    cleanup_analytics_data,
    
    # Analytics tasks
    update_daily_stats,
    aggregate_user_stats,
    generate_reports,
    
    # Notification tasks
    send_download_notification,
    send_batch_notification,
    send_broadcast_message,
)

__all__ = [
    # Core
    "celery_app",
    "create_celery_app", 
    "worker_config",
    "WorkerConfig",
    
    # Tasks
    "process_single_download",
    "process_batch_download", 
    "retry_failed_download",
    "cleanup_expired_files",
    "cleanup_old_batches",
    "cleanup_analytics_data",
    "update_daily_stats",
    "aggregate_user_stats",
    "generate_reports",
    "send_download_notification",
    "send_batch_notification",
    "send_broadcast_message",
]

# Информация о worker'е
WORKER_INFO = {
    'version': __version__,
    'description': __description__,
    'supported_platforms': ['youtube', 'tiktok', 'instagram'],
    'max_concurrent_tasks': 10,
    'queues': ['default', 'downloads', 'batches', 'cleanup', 'analytics', 'notifications'],
    'storage_backends': ['wasabi', 'backblaze', 'digitalocean', 'local'],
}

def get_worker_info():
    """Получить информацию о worker'е"""
    return WORKER_INFO.copy()

print(f"🚀 VideoBot Pro Worker v{__version__} loaded")