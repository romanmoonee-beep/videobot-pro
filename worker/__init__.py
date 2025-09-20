"""
VideoBot Pro - Worker Package
Асинхронный обработчик задач на основе Celery с интеграцией CDN
"""

__version__ = "2.1.0"
__description__ = "VideoBot Pro Worker - Asynchronous task processor with CDN integration"

# Безопасный импорт основных компонентов
try:
    from .celery_app import celery_app, create_celery_app, validate_celery_config
    CELERY_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import celery_app components: {e}")
    celery_app = None
    create_celery_app = None
    validate_celery_config = None
    CELERY_AVAILABLE = False

try:
    from .config import worker_config, WorkerConfig
    CONFIG_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import worker config: {e}")
    worker_config = None
    WorkerConfig = None
    CONFIG_AVAILABLE = False

# CDN интеграция
try:
    from .integrations.cdn_upload import (
        CDNUploadClient,
        CDNIntegrationService,
        cdn_integration,
        upload_to_cdn,
        upload_thumbnail_to_cdn,
        is_cdn_available
    )
    CDN_INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: CDN integration not available: {e}")
    CDNUploadClient = None
    CDNIntegrationService = None
    cdn_integration = None
    upload_to_cdn = None
    upload_thumbnail_to_cdn = None
    is_cdn_available = None
    CDN_INTEGRATION_AVAILABLE = False

# Ленивый импорт задач чтобы избежать циклических импортов
def get_download_tasks():
    """Ленивый импорт задач скачивания с CDN интеграцией"""
    try:
        from .tasks.download_tasks import (
            download_video_task,
            download_batch_task,
            cleanup_old_files_task,
            migrate_files_to_cdn_task,
        )
        return {
            'download_video_task': download_video_task,
            'download_batch_task': download_batch_task,
            'cleanup_old_files_task': cleanup_old_files_task,
            'migrate_files_to_cdn_task': migrate_files_to_cdn_task,
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
            cleanup_old_files,
            cleanup_temp_files,
            health_check_task,
        )
        return {
            'cleanup_old_files': cleanup_old_files,
            'cleanup_temp_files': cleanup_temp_files,
            'health_check_task': health_check_task,
        }
    except ImportError as e:
        print(f"Warning: Could not import cleanup tasks: {e}")
        return {}

def get_analytics_tasks():
    """Ленивый импорт analytics задач"""
    try:
        from .tasks.analytics_tasks import (
            process_analytics_events,
            calculate_daily_stats,
        )
        return {
            'process_analytics_events': process_analytics_events,
            'calculate_daily_stats': calculate_daily_stats,
        }
    except ImportError as e:
        print(f"Warning: Could not import analytics tasks: {e}")
        return {}

def get_notification_tasks():
    """Ленивый импорт notification задач"""
    try:
        from .tasks.notification_tasks import (
            send_download_completion_notification,
            send_batch_completion_notification,
        )
        return {
            'send_download_completion_notification': send_download_completion_notification,
            'send_batch_completion_notification': send_batch_completion_notification,
        }
    except ImportError as e:
        print(f"Warning: Could not import notification tasks: {e}")
        return {}

def get_celery_schedule():
    """Получить расписание Celery задач"""
    try:
        from .config.celery_beat_schedule import CELERYBEAT_SCHEDULE
        return CELERYBEAT_SCHEDULE
    except ImportError as e:
        print(f"Warning: Could not import Celery schedule: {e}")
        return {}

# Собираем все задачи в один объект
class Tasks:
    """Контейнер для всех задач с CDN интеграцией"""
    
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
    # Core Celery
    "celery_app",
    "create_celery_app", 
    "validate_celery_config",
    "worker_config",
    "WorkerConfig",
    "tasks",
    
    # CDN Integration
    "CDNUploadClient",
    "CDNIntegrationService", 
    "cdn_integration",
    "upload_to_cdn",
    "upload_thumbnail_to_cdn",
    "is_cdn_available",
    
    # Task functions
    "get_download_tasks",
    "get_batch_tasks",
    "get_cleanup_tasks", 
    "get_analytics_tasks",
    "get_notification_tasks",
    "get_celery_schedule",
    
    # Feature flags
    "CELERY_AVAILABLE",
    "CONFIG_AVAILABLE",
    "CDN_INTEGRATION_AVAILABLE",
]

# Информация о worker'е с CDN поддержкой
WORKER_INFO = {
    'version': __version__,
    'description': __description__,
    'supported_platforms': ['youtube', 'tiktok', 'instagram'],
    'max_concurrent_tasks': 10,
    'queues': ['default', 'downloads', 'batches', 'cleanup', 'analytics', 'notifications', 'cdn'],
    'storage_backends': ['wasabi', 'backblaze', 'digitalocean', 'local'],
    'features': {
        'celery': CELERY_AVAILABLE,
        'config': CONFIG_AVAILABLE,
        'cdn_integration': CDN_INTEGRATION_AVAILABLE,
        'multi_cloud_upload': CDN_INTEGRATION_AVAILABLE,
        'automatic_cleanup': True,
        'batch_processing': True,
        'analytics': True,
        'notifications': True,
    },
    'cdn_features': {
        'auto_upload': CDN_INTEGRATION_AVAILABLE,
        'thumbnail_upload': CDN_INTEGRATION_AVAILABLE,
        'archive_creation': CDN_INTEGRATION_AVAILABLE,
        'file_migration': CDN_INTEGRATION_AVAILABLE,
        'health_monitoring': CDN_INTEGRATION_AVAILABLE,
    } if CDN_INTEGRATION_AVAILABLE else {}
}

def get_worker_info():
    """Получить информацию о worker'е"""
    return WORKER_INFO.copy()

def is_worker_available():
    """Проверить доступность worker'а"""
    try:
        if not CELERY_AVAILABLE or not celery_app:
            return False
            
        # Простая проверка соединения с Celery
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        return bool(active_workers)
    except Exception:
        return False

def get_worker_status():
    """Получить статус worker'а с информацией о CDN"""
    try:
        status = {
            'celery_available': CELERY_AVAILABLE,
            'cdn_integration': CDN_INTEGRATION_AVAILABLE,
            'worker_info': get_worker_info()
        }
        
        if not CELERY_AVAILABLE or not celery_app:
            status['error'] = 'Celery app not available'
            return status
            
        inspect = celery_app.control.inspect()
        status.update({
            'active': inspect.active(),
            'scheduled': inspect.scheduled(),
            'reserved': inspect.reserved(),
            'stats': inspect.stats(),
        })
        
        # Добавляем статус CDN если доступен
        if CDN_INTEGRATION_AVAILABLE and cdn_integration:
            try:
                status['cdn_status'] = {
                    'enabled': cdn_integration.enabled,
                    'available': is_cdn_available() if is_cdn_available else False
                }
            except Exception as e:
                status['cdn_status'] = {'error': str(e)}
        
        return status
        
    except Exception as e:
        return {'error': str(e)}

async def check_cdn_integration():
    """Проверить работоспособность CDN интеграции"""
    if not CDN_INTEGRATION_AVAILABLE:
        return {
            'available': False,
            'error': 'CDN integration not imported'
        }
    
    try:
        # Проверяем доступность CDN
        cdn_available = await is_cdn_available() if is_cdn_available else False
        
        result = {
            'available': cdn_available,
            'integration_enabled': cdn_integration.enabled if cdn_integration else False,
        }
        
        # Получаем статистику CDN если доступен
        if cdn_available and cdn_integration:
            try:
                cdn_stats = await cdn_integration.get_cdn_stats()
                result['cdn_stats'] = cdn_stats
            except Exception as e:
                result['cdn_stats_error'] = str(e)
        
        return result
        
    except Exception as e:
        return {
            'available': False,
            'error': str(e)
        }

# Функция для импорта задач при необходимости
def import_all_tasks():
    """Импортировать все задачи (для принудительной регистрации)"""
    try:
        # Импортируем все модули с задачами
        imported_tasks = {}
        
        imported_tasks['download'] = get_download_tasks()
        imported_tasks['batch'] = get_batch_tasks()
        imported_tasks['cleanup'] = get_cleanup_tasks()
        imported_tasks['analytics'] = get_analytics_tasks()
        imported_tasks['notifications'] = get_notification_tasks()
        
        total_tasks = sum(len(tasks) for tasks in imported_tasks.values())
        
        print(f"✅ All worker tasks imported successfully ({total_tasks} tasks)")
        
        # Показываем CDN статус
        if CDN_INTEGRATION_AVAILABLE:
            print(f"📦 CDN integration: {'enabled' if cdn_integration and cdn_integration.enabled else 'disabled'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error importing tasks: {e}")
        return False

async def initialize_worker_with_cdn():
    """Инициализация worker'а с CDN интеграцией"""
    try:
        print(f"🚀 Initializing VideoBot Pro Worker v{__version__} with CDN...")
        
        # Проверяем основные компоненты
        if not CELERY_AVAILABLE:
            print("❌ Celery not available")
            return False
        
        if not CONFIG_AVAILABLE:
            print("❌ Worker config not available")
            return False
        
        # Проверяем CDN интеграцию
        if CDN_INTEGRATION_AVAILABLE:
            cdn_check = await check_cdn_integration()
            if cdn_check['available']:
                print("✅ CDN integration available and working")
            else:
                print(f"⚠️  CDN integration available but not working: {cdn_check.get('error', 'Unknown error')}")
        else:
            print("⚠️  CDN integration not available")
        
        # Импортируем задачи
        if import_all_tasks():
            print("✅ Worker initialization completed")
            return True
        else:
            print("❌ Worker initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Worker initialization error: {e}")
        return False

# Простые функции для интеграции с CDN
async def upload_worker_file_to_cdn(file_path: str, task_id: int, user_id: int):
    """Простая функция для загрузки файла worker'а в CDN"""
    if not CDN_INTEGRATION_AVAILABLE or not upload_to_cdn:
        raise RuntimeError("CDN integration not available")
    
    # Создаем фиктивные объекты для совместимости
    class FakeTask:
        def __init__(self, task_id):
            self.id = task_id
            self.platform = "worker"
            self.url = "worker_upload"
    
    class FakeUser:
        def __init__(self, user_id):
            self.id = user_id
            self.user_type = "free"
    
    fake_task = FakeTask(task_id)
    fake_user = FakeUser(user_id)
    
    downloaded_files = [{
        'path': file_path,
        'type': 'video',
        'metadata': {}
    }]
    
    return await upload_to_cdn(fake_task, fake_user, downloaded_files)

# Инициализация при импорте
def _initialize_worker():
    """Инициализация worker компонентов"""
    try:
        # Показываем статус компонентов
        components = {
            'Celery': CELERY_AVAILABLE,
            'Config': CONFIG_AVAILABLE,
            'CDN Integration': CDN_INTEGRATION_AVAILABLE,
        }
        
        working_components = sum(1 for available in components.values() if available)
        total_components = len(components)
        
        if working_components == total_components:
            print(f"✅ VideoBot Pro Worker v{__version__} loaded successfully")
        elif working_components > 0:
            print(f"⚠️  VideoBot Pro Worker v{__version__} loaded with warnings")
            print(f"   {working_components}/{total_components} components available")
        else:
            print(f"❌ VideoBot Pro Worker v{__version__} loaded with errors")
            print("   Critical components failed to load")
        
        # Показываем доступные компоненты
        available_components = [name for name, available in components.items() if available]
        if available_components:
            print(f"📋 Available components: {', '.join(available_components)}")
        
        # Показываем дополнительную информацию о CDN
        if CDN_INTEGRATION_AVAILABLE:
            print(f"🌐 CDN integration loaded - multi-cloud upload enabled")
        
    except Exception as e:
        print(f"❌ Worker initialization error: {e}")

# Запускаем инициализацию
_initialize_worker()