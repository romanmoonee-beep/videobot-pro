"""
VideoBot Pro - Tasks Package (ИСПРАВЛЕННАЯ ВЕРСИЯ)
Celery задачи для обработки загрузок
"""

import structlog

logger = structlog.get_logger(__name__)


try:
    from .download_tasks import (
        process_single_download,
        retry_failed_download,
        cleanup_expired_downloads,
        check_download_status,
        cancel_download_task,
    )
    logger.debug("Download tasks imported successfully")
except ImportError as e:
    logger.warning(f"Could not import download_tasks: {e}")
    # Создаем заглушки
    process_single_download = None
    retry_failed_download = None
    cleanup_expired_downloads = None
    check_download_status = None
    cancel_download_task = None

try:
    from .batch_tasks import (
        process_batch_download,
        create_batch_archive,
        retry_failed_batch,
        cleanup_expired_batches,
        check_batch_status,
    )
    logger.debug("Batch tasks imported successfully")
except ImportError as e:
    logger.warning(f"Could not import batch_tasks: {e}")
    # Создаем заглушки
    process_batch_download = None
    create_batch_archive = None
    retry_failed_batch = None
    cleanup_expired_batches = None
    check_batch_status = None

try:
    from .cleanup_tasks import (
        cleanup_old_files,
        cleanup_temp_files,
        cleanup_expired_cdn_links,
        vacuum_database,
        cleanup_analytics_events,
        health_check_task,
    )
    logger.debug("Cleanup tasks imported successfully")
except ImportError as e:
    logger.warning(f"Could not import cleanup_tasks: {e}")
    # Создаем заглушки
    cleanup_old_files = None
    cleanup_temp_files = None
    cleanup_expired_cdn_links = None
    vacuum_database = None
    cleanup_analytics_events = None
    health_check_task = None

try:
    from .analytics_tasks import (
        process_analytics_events,
        calculate_daily_stats,
        update_user_activity_stats,
        cleanup_old_analytics_events,
        generate_user_analytics_report,
        hourly_analytics_processing,
        daily_stats_calculation,
    )
    logger.debug("Analytics tasks imported successfully")
except ImportError as e:
    logger.warning(f"Could not import analytics_tasks: {e}")
    # Создаем заглушки
    process_analytics_events = None
    calculate_daily_stats = None
    update_user_activity_stats = None
    cleanup_old_analytics_events = None
    generate_user_analytics_report = None
    hourly_analytics_processing = None
    daily_stats_calculation = None

try:
    from .notification_tasks import (
        send_download_completion_notification,
        send_batch_completion_notification,
        send_premium_expiry_warning,
        send_broadcast_message,
        check_premium_expiry_notifications,
    )
    logger.debug("Notification tasks imported successfully")
except ImportError as e:
    logger.warning(f"Could not import notification_tasks: {e}")
    # Создаем заглушки
    send_download_completion_notification = None
    send_batch_completion_notification = None
    send_premium_expiry_warning = None
    send_broadcast_message = None
    check_premium_expiry_notifications = None

# ИСПРАВЛЕНИЕ: Динамическое построение __all__ только с существующими задачами
__all__ = []

# Список всех задач для проверки
ALL_TASKS = [
    # Download tasks
    ('process_single_download', process_single_download),
    ('retry_failed_download', retry_failed_download),
    ('cleanup_expired_downloads', cleanup_expired_downloads),
    ('check_download_status', check_download_status),
    ('cancel_download_task', cancel_download_task),
    
    # Batch tasks
    ('process_batch_download', process_batch_download),
    ('create_batch_archive', create_batch_archive),
    ('retry_failed_batch', retry_failed_batch),
    ('cleanup_expired_batches', cleanup_expired_batches),
    ('check_batch_status', check_batch_status),
    
    # Cleanup tasks
    ('cleanup_old_files', cleanup_old_files),
    ('cleanup_temp_files', cleanup_temp_files),
    ('cleanup_expired_cdn_links', cleanup_expired_cdn_links),
    ('vacuum_database', vacuum_database),
    ('cleanup_analytics_events', cleanup_analytics_events),
    ('health_check_task', health_check_task),
    
    # Analytics tasks
    ('process_analytics_events', process_analytics_events),
    ('calculate_daily_stats', calculate_daily_stats),
    ('update_user_activity_stats', update_user_activity_stats),
    ('cleanup_old_analytics_events', cleanup_old_analytics_events),
    ('generate_user_analytics_report', generate_user_analytics_report),
    ('hourly_analytics_processing', hourly_analytics_processing),
    ('daily_stats_calculation', daily_stats_calculation),
    
    # Notification tasks
    ('send_download_completion_notification', send_download_completion_notification),
    ('send_batch_completion_notification', send_batch_completion_notification),
    ('send_premium_expiry_warning', send_premium_expiry_warning),
    ('send_broadcast_message', send_broadcast_message),
    ('check_premium_expiry_notifications', check_premium_expiry_notifications),
]

# Добавляем в __all__ только существующие задачи
available_tasks = []
unavailable_tasks = []

for task_name, task_obj in ALL_TASKS:
    if task_obj is not None:
        __all__.append(task_name)
        available_tasks.append(task_name)
    else:
        unavailable_tasks.append(task_name)

# Группировка задач по типам для удобства
DOWNLOAD_TASKS = [name for name, obj in ALL_TASKS[:5] if obj is not None]
BATCH_TASKS = [name for name, obj in ALL_TASKS[5:10] if obj is not None]
CLEANUP_TASKS = [name for name, obj in ALL_TASKS[10:16] if obj is not None]
ANALYTICS_TASKS = [name for name, obj in ALL_TASKS[16:23] if obj is not None]
NOTIFICATION_TASKS = [name for name, obj in ALL_TASKS[23:] if obj is not None]

# Периодические задачи для Celery Beat
PERIODIC_TASKS = {
    # Очистка каждые 6 часов
    'cleanup-old-files': {
        'task': 'worker.tasks.cleanup_tasks.cleanup_old_files',
        'schedule': 6.0 * 60 * 60,  # 6 hours
        'enabled': cleanup_old_files is not None,
    },
    
    # Очистка temp файлов каждый час
    'cleanup-temp-files': {
        'task': 'worker.tasks.cleanup_tasks.cleanup_temp_files', 
        'schedule': 60.0 * 60,  # 1 hour
        'enabled': cleanup_temp_files is not None,
    },
    
    # Очистка истекших CDN ссылок каждые 2 часа
    'cleanup-expired-cdn': {
        'task': 'worker.tasks.cleanup_tasks.cleanup_expired_cdn_links',
        'schedule': 2.0 * 60 * 60,  # 2 hours
        'enabled': cleanup_expired_cdn_links is not None,
    },
    
    # Генерация дневной статистики в 00:30
    'generate-daily-stats': {
        'task': 'worker.tasks.analytics_tasks.daily_stats_calculation',
        'schedule': {
            'hour': 0,
            'minute': 30,
        },
        'enabled': daily_stats_calculation is not None,
    },
    
    # Обработка аналитических событий каждые 10 минут
    'process-analytics': {
        'task': 'worker.tasks.analytics_tasks.hourly_analytics_processing',
        'schedule': 10.0 * 60,  # 10 minutes
        'enabled': hourly_analytics_processing is not None,
    },
    
    # Health check каждые 5 минут
    'health-check': {
        'task': 'worker.tasks.cleanup_tasks.health_check_task',
        'schedule': 5.0 * 60,  # 5 minutes
        'enabled': health_check_task is not None,
    },
    
    # Очистка базы данных еженедельно в воскресенье в 03:00
    'vacuum-database': {
        'task': 'worker.tasks.cleanup_tasks.vacuum_database',
        'schedule': {
            'hour': 3,
            'minute': 0,
            'day_of_week': 0,  # Sunday
        },
        'enabled': vacuum_database is not None,
    },
    
    # Проверка истечения Premium подписок ежедневно в 09:00
    'check-premium-expiry': {
        'task': 'worker.tasks.notification_tasks.check_premium_expiry_notifications',
        'schedule': {
            'hour': 9,
            'minute': 0,
        },
        'enabled': check_premium_expiry_notifications is not None,
    },
}

# Фильтруем только активные периодические задачи
ACTIVE_PERIODIC_TASKS = {
    name: config for name, config in PERIODIC_TASKS.items() 
    if config.get('enabled', False)
}

# Конфигурация роутинга задач
TASK_ROUTES = {
    # Критичные задачи на быструю очередь
    'worker.tasks.download_tasks.*': {'queue': 'downloads'},
    'worker.tasks.batch_tasks.*': {'queue': 'downloads'},
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

def get_available_tasks() -> dict:
    """Получить список всех доступных задач по категориям"""
    return {
        'download': DOWNLOAD_TASKS,
        'batch': BATCH_TASKS,
        'cleanup': CLEANUP_TASKS,
        'analytics': ANALYTICS_TASKS,
        'notifications': NOTIFICATION_TASKS,
        'total_available': len(available_tasks),
        'total_unavailable': len(unavailable_tasks),
    }

def get_task_by_name(task_name: str):
    """
    Получить объект задачи по имени
    
    Args:
        task_name: Имя задачи
        
    Returns:
        Объект задачи или None если не найдена
    """
    return globals().get(task_name)

def is_task_available(task_name: str) -> bool:
    """
    Проверить доступность задачи
    
    Args:
        task_name: Имя задачи
        
    Returns:
        True если задача доступна
    """
    return task_name in available_tasks

def get_tasks_info() -> dict:
    """Получить подробную информацию о задачах"""
    return {
        'package_version': '2.1.0',
        'total_tasks_defined': len(ALL_TASKS),
        'available_tasks': len(available_tasks),
        'unavailable_tasks': len(unavailable_tasks),
        'available_task_names': available_tasks,
        'unavailable_task_names': unavailable_tasks,
        'periodic_tasks_available': len(ACTIVE_PERIODIC_TASKS),
        'periodic_tasks_total': len(PERIODIC_TASKS),
        'task_categories': {
            'download': len(DOWNLOAD_TASKS),
            'batch': len(BATCH_TASKS),
            'cleanup': len(CLEANUP_TASKS),
            'analytics': len(ANALYTICS_TASKS),
            'notifications': len(NOTIFICATION_TASKS),
        }
    }

# Функции для работы с задачами
def submit_download_task(url: str, user_id: int, **kwargs):
    """Отправить задачу на скачивание"""
    if process_single_download is None:
        raise RuntimeError("Download tasks not available")
    
    # Здесь будет логика создания задачи в БД и отправки в Celery
    # Пока что заглушка
    logger.info(f"Would submit download task for URL: {url}")
    return {"task_id": "mock_task_id", "status": "pending"}

def submit_batch_task(urls: list, user_id: int, **kwargs):
    """Отправить batch задачу"""
    if process_batch_download is None:
        raise RuntimeError("Batch tasks not available")
    
    logger.info(f"Would submit batch task for {len(urls)} URLs")
    return {"batch_id": "mock_batch_id", "status": "pending"}

# Логирование статуса загрузки
logger.info(
    "Tasks package loaded",
    available_tasks=len(available_tasks),
    unavailable_tasks=len(unavailable_tasks),
    periodic_tasks=len(ACTIVE_PERIODIC_TASKS)
)

if unavailable_tasks:
    logger.warning(
        "Some tasks are not available",
        unavailable_tasks=unavailable_tasks[:5]  # Показываем первые 5
    )

if available_tasks:
    logger.info(
        "Available task categories",
        download=len(DOWNLOAD_TASKS),
        batch=len(BATCH_TASKS),
        cleanup=len(CLEANUP_TASKS),
        analytics=len(ANALYTICS_TASKS),
        notifications=len(NOTIFICATION_TASKS)
    )

print(f"📦 VideoBot Pro Tasks v2.1.0 - {len(available_tasks)}/{len(ALL_TASKS)} tasks available")