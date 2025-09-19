"""
VideoBot Pro - Worker Package
Асинхронный обработчик задач на основе Celery
"""

__version__ = "2.1.0"
__description__ = "VideoBot Pro Worker - Asynchronous task processor"

# Экспорт основных компонентов
from .celery_app import celery_app, create_celery_app, validate_celery_config
from .config import worker_config, WorkerConfig

# Lazy import задач чтобы избежать циклических импортов
def get_download_tasks():
    """Ленивый импорт задач скачивания"""
    try:
        from .tasks.download_tasks import (
            process_single_download,
            retry_failed_download,
        )
        return {
            'process_single_download': process_single_download,
            'retry_failed_download': retry_failed_download,
        }
    except ImportError as e:
        print(f"Warning: Could not import download tasks: {e}")
        return {}

def get_batch_tasks():
    """Ленивый импорт batch задач"""
    try:
        from .tasks.batch_tasks import (
            process_batch_download,
        )
        return {
            'process_batch_download': process_batch_download,
        }
    except ImportError as e:
        print(f"Warning: Could not import batch tasks: {e}")
        return {}

def get_cleanup_tasks():
    """Ленивый импорт cleanup задач"""
    try:
        from .tasks.cleanup_tasks import (
            cleanup_expired_files,
            cleanup_old_batches,
            cleanup_analytics_data,
        )
        return {
            'cleanup_expired_files': cleanup_expired_files,
            'cleanup_old_batches': cleanup_old_batches,
            'cleanup_analytics_data': cleanup_analytics_data,
        }
    except ImportError as e:
        print(f"Warning: Could not import cleanup tasks: {e}")
        return {}

def get_analytics_tasks():
    """Ленивый импорт analytics задач"""
    try:
        from .tasks.analytics_tasks import (
            update_daily_stats,
            aggregate_user_stats,
            generate_reports,
        )
        return {
            'update_daily_stats': update_daily_stats,
            'aggregate_user_stats': aggregate_user_stats,
            'generate_reports': generate_reports,
        }
    except ImportError as e:
        print(f"Warning: Could not import analytics tasks: {e}")
        return {}

def get_notification_tasks():
    """Ленивый импорт notification задач"""
    try:
        from .tasks.notification_tasks import (
            send_download_notification,
            send_batch_notification,
            send_broadcast_message,
        )
        return {
            'send_download_notification': send_download_notification,
            'send_batch_notification': send_batch_notification,
            'send_broadcast_message': send_broadcast_message,
        }
    except ImportError as e:
        print(f"Warning: Could not import notification tasks: {e}")
        return {}

# Собираем все задачи в один объект
class Tasks:
    """Контейнер для всех задач"""
    
    def __init__(self):
        self._download_tasks = None
        self._batch_tasks = None
        self._cleanup_tasks = None
        self._analytics_tasks = None
        self._notification_tasks = None
    
    @property
    def download(self):
        if self._download_tasks is None:
            self._download_tasks = get_download_tasks()
        return self._download_tasks
    
    @property
    def batch(self):
        if self._batch_tasks is None:
            self._batch_tasks = get_batch_tasks()
        return self._batch_tasks
    
    @property
    def cleanup(self):
        if self._cleanup_tasks is None:
            self._cleanup_tasks = get_cleanup_tasks()
        return self._cleanup_tasks
    
    @property
    def analytics(self):
        if self._analytics_tasks is None:
            self._analytics_tasks = get_analytics_tasks()
        return self._analytics_tasks
    
    @property
    def notifications(self):
        if self._notification_tasks is None:
            self._notification_tasks = get_notification_tasks()
        return self._notification_tasks

# Создаем экземпляр задач
tasks = Tasks()

# Основные экспорты
__all__ = [
    # Core
    "celery_app",
    "create_celery_app", 
    "validate_celery_config",
    "worker_config",
    "WorkerConfig",
    "tasks",
    
    # Utility functions
    "get_download_tasks",
    "get_batch_tasks",
    "get_cleanup_tasks", 
    "get_analytics_tasks",
    "get_notification_tasks",
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

def is_worker_available():
    """Проверить доступность worker'а"""
    try:
        # Простая проверка соединения с Celery
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        return bool(active_workers)
    except Exception:
        return False

def get_worker_status():
    """Получить статус worker'а"""
    try:
        inspect = celery_app.control.inspect()
        return {
            'active': inspect.active(),
            'scheduled': inspect.scheduled(),
            'reserved': inspect.reserved(),
            'stats': inspect.stats(),
        }
    except Exception as e:
        return {'error': str(e)}

# Функция для импорта задач при необходимости
def import_all_tasks():
    """Импортировать все задачи (для принудительной регистрации)"""
    try:
        # Импортируем все модули с задачами
        from . import tasks as task_modules
        print(f"✅ All worker tasks imported successfully")
        return True
    except Exception as e:
        print(f"❌ Error importing tasks: {e}")
        return False

print(f"🚀 VideoBot Pro Worker v{__version__} loaded")