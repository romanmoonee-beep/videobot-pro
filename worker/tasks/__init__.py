"""
VideoBot Pro - Worker Tasks Package
Celery задачи для обработки загрузок
"""

from .download_tasks import (
    process_single_download,
    retry_failed_download,
    cleanup_expired_downloads,
    check_download_status,
    cancel_download_task,
)

from .batch_tasks import (
    process_batch_download,
    create_batch_archive,
    retry_failed_batch,
    cleanup_expired_batches,
    check_batch_status,
)

from .cleanup_tasks import (
    cleanup_old_files,
    cleanup_temp_files,
    cleanup_expired_cdn_links,
    vacuum_database,
    cleanup_analytics_events,
    health_check_task,
)

from .analytics_tasks import (
    process_analytics_events,
    generate_daily_stats,
    update_user_stats,
    calculate_platform_stats,
    export_analytics_data,
)

from .notification_tasks import (
    send_download_completion_notification,
    send_batch_completion_notification,
    send_premium_expiry_notification,
    send_system_notification,
    send_broadcast_message,
)

__all__ = [
    # Download tasks
    'process_single_download',
    'retry_failed_download', 
    'cleanup_expired_downloads',
    'check_download_status',
    'cancel_download_task',
    
    # Batch tasks
    'process_batch_download',
    'create_batch_archive',
    'retry_failed_batch',
    'cleanup_expired_batches', 
    'check_batch_status',
    
    # Cleanup tasks
    'cleanup_old_files',
    'cleanup_temp_files',
    'cleanup_expired_cdn_links',
    'vacuum_database',
    'cleanup_analytics_events',
    'health_check_task',
    
    # Analytics tasks
    'process_analytics_events',
    'generate_daily_stats',
    'update_user_stats',
    'calculate_platform_stats',
    'export_analytics_data',
    
    # Notification tasks
    'send_download_completion_notification',
    'send_batch_completion_notification', 
    'send_premium_expiry_notification',
    'send_system_notification',
    'send_broadcast_message',
]

# Регистрация периодических задач
PERIODIC_TASKS = {
    # Очистка каждые 6 часов
    'cleanup-old-files': {
        'task': 'worker.tasks.cleanup_tasks.cleanup_old_files',
        'schedule': 6.0 * 60 * 60,  # 6 hours
    },
    
    # Очистка temp файлов каждый час
    'cleanup-temp-files': {
        'task': 'worker.tasks.cleanup_tasks.cleanup_temp_files', 
        'schedule': 60.0 * 60,  # 1 hour
    },
    
    # Очистка истекших CDN ссылок каждые 2 часа
    'cleanup-expired-cdn': {
        'task': 'worker.tasks.cleanup_tasks.cleanup_expired_cdn_links',
        'schedule': 2.0 * 60 * 60,  # 2 hours
    },
    
    # Генерация дневной статистики в 00:30
    'generate-daily-stats': {
        'task': 'worker.tasks.analytics_tasks.generate_daily_stats',
        'schedule': {
            'hour': 0,
            'minute': 30,
        },
    },
    
    # Обработка аналитических событий каждые 10 минут
    'process-analytics': {
        'task': 'worker.tasks.analytics_tasks.process_analytics_events',
        'schedule': 10.0 * 60,  # 10 minutes
    },
    
    # Health check каждые 5 минут
    'health-check': {
        'task': 'worker.tasks.cleanup_tasks.health_check_task',
        'schedule': 5.0 * 60,  # 5 minutes
    },
    
    # Очистка базы данных еженедельно в воскресенье в 03:00
    'vacuum-database': {
        'task': 'worker.tasks.cleanup_tasks.vacuum_database',
        'schedule': {
            'hour': 3,
            'minute': 0,
            'day_of_week': 0,  # Sunday
        },
    },
}

# Конфигурация роутинга задач
TASK_ROUTES = {
    # Критичные задачи на быструю очередь
    'worker.tasks.download_tasks.process_single_download': {'queue': 'downloads'},
    'worker.tasks.batch_tasks.process_batch_download': {'queue': 'downloads'},
    'worker.tasks.notification_tasks.*': {'queue': 'notifications'},
    
    # Фоновые задачи на медленную очередь  
    'worker.tasks.cleanup_tasks.*': {'queue': 'cleanup'},
    'worker.tasks.analytics_tasks.*': {'queue': 'analytics'},
}

# Приоритеты задач
TASK_PRIORITIES = {
    'high': 9,
    'normal': 5, 
    'low': 1,
}

def get_task_priority(user_type: str) -> int:
    """Получить приоритет задачи на основе типа пользователя"""
    priority_map = {
        'admin': TASK_PRIORITIES['high'],
        'premium': TASK_PRIORITIES['high'], 
        'trial': TASK_PRIORITIES['normal'],
        'free': TASK_PRIORITIES['low'],
    }
    return priority_map.get(user_type, TASK_PRIORITIES['normal'])