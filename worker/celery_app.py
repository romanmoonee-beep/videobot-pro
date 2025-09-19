"""
VideoBot Pro - Celery Application
Настройка и конфигурация Celery для worker процессов
"""

from celery import Celery
from celery.signals import worker_ready, worker_shutdown, task_prerun, task_postrun, task_failure
from kombu import Queue
import structlog
import os
import sys
import time
from datetime import timedelta

# Добавляем пути для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from shared.config.settings import settings
    from worker.config import worker_config
except ImportError as e:
    print(f"Warning: Could not import settings: {e}")
    # Fallback значения
    class FallbackSettings:
        CELERY_BROKER_URL = "redis://localhost:6379/0"
        CELERY_RESULT_BACKEND = "redis://localhost:6379/0"
    
    class FallbackWorkerConfig:
        soft_timeout = 1500
        task_timeout = 1800
        prefetch_multiplier = 1
        max_tasks_per_child = 1000
        max_memory_per_child = 200
        worker_name = "videobot-worker"
        worker_concurrency = 4
        worker_pool = "prefork"
        temp_dir = "/tmp/videobot"
    
    settings = FallbackSettings()
    worker_config = FallbackWorkerConfig()

logger = structlog.get_logger(__name__)

def create_celery_app(app_name: str = 'videobot_worker', **kwargs) -> Celery:
    """
    Создать и настроить Celery приложение
    
    Args:
        app_name: Имя приложения
        **kwargs: Дополнительные настройки
        
    Returns:
        Настроенное Celery приложение
    """
    broker_url = kwargs.get('broker_url', settings.CELERY_BROKER_URL)
    result_backend = kwargs.get('result_backend', settings.CELERY_RESULT_BACKEND)
    
    app = Celery(
        app_name,
        broker=broker_url,
        backend=result_backend,
        include=[
            'worker.tasks.download_tasks',
            'worker.tasks.batch_tasks', 
            'worker.tasks.cleanup_tasks',
            'worker.tasks.analytics_tasks',
            'worker.tasks.notification_tasks',
        ]
    )
    
    # Применяем конфигурацию
    app.conf.update(get_celery_config(**kwargs))
    
    return app

def get_celery_config(**kwargs) -> dict:
    """
    Получить конфигурацию для Celery
    
    Args:
        **kwargs: Дополнительные настройки
        
    Returns:
        Словарь с настройками
    """
    return {
        # Настройки задач
        'task_serializer': 'json',
        'accept_content': ['json'],
        'result_serializer': 'json',
        'timezone': 'UTC',
        'enable_utc': True,
        
        # Timeouts
        'task_soft_time_limit': kwargs.get('soft_timeout', worker_config.soft_timeout),
        'task_time_limit': kwargs.get('task_timeout', worker_config.task_timeout),
        
        # Worker настройки
        'worker_prefetch_multiplier': kwargs.get('prefetch_multiplier', worker_config.prefetch_multiplier),
        'worker_max_tasks_per_child': kwargs.get('max_tasks_per_child', worker_config.max_tasks_per_child),
        'worker_max_memory_per_child': kwargs.get('max_memory_per_child', worker_config.max_memory_per_child),
        
        # Retry настройки
        'task_acks_late': True,
        'task_reject_on_worker_lost': True,
        
        # Результаты
        'result_expires': 3600,  # 1 час
        'result_persistent': True,
        
        # Мониторинг
        'worker_send_task_events': True,
        'task_send_sent_event': True,
        
        # Маршрутизация задач по очередям
        'task_routes': {
            'worker.tasks.download_tasks.*': {'queue': 'downloads'},
            'worker.tasks.batch_tasks.*': {'queue': 'batch'},
            'worker.tasks.cleanup_tasks.*': {'queue': 'cleanup'},
            'worker.tasks.analytics_tasks.*': {'queue': 'analytics'},
            'worker.tasks.notification_tasks.*': {'queue': 'notifications'},
        },
        
        # Определение очередей
        'task_default_queue': 'default',
        'task_queues': (
            Queue('default', routing_key='default'),
            Queue('downloads', routing_key='downloads'),
            Queue('batch', routing_key='batch'),
            Queue('cleanup', routing_key='cleanup'),
            Queue('analytics', routing_key='analytics'),
            Queue('notifications', routing_key='notifications'),
            Queue('priority', routing_key='priority'),  # Для приоритетных задач
        ),
        
        # Приоритеты очередей
        'task_queue_priority': {
            'priority': 10,
            'downloads': 7,
            'batch': 5,
            'notifications': 3,
            'analytics': 2,
            'cleanup': 1,
        },
        
        # Beat scheduler (для периодических задач)
        'beat_schedule': {
            'cleanup-temp-files': {
                'task': 'worker.tasks.cleanup_tasks.cleanup_temp_files',
                'schedule': timedelta(hours=1),
            },
            'cleanup-old-downloads': {
                'task': 'worker.tasks.cleanup_tasks.cleanup_old_files',
                'schedule': timedelta(hours=6),
            },
            'update-daily-analytics': {
                'task': 'worker.tasks.analytics_tasks.process_analytics_events',
                'schedule': timedelta(hours=1),
            },
            'health-check': {
                'task': 'worker.tasks.cleanup_tasks.health_check_task',
                'schedule': timedelta(minutes=5),
            },
            'storage-cleanup': {
                'task': 'worker.tasks.cleanup_tasks.cleanup_expired_cdn_links',
                'schedule': timedelta(hours=12),
            },
        },
        
        # Дополнительные настройки
        'worker_disable_rate_limits': True,
        'task_ignore_result': False,
        
        # Логирование
        'worker_log_format': '[%(asctime)s: %(levelname)s/%(name)s] %(message)s',
        'worker_task_log_format': '[%(asctime)s: %(levelname)s/%(name)s][%(task_name)s(%(task_id)s)] %(message)s',
    }

def validate_celery_config() -> bool:
    """
    Валидация конфигурации Celery
    
    Returns:
        True если конфигурация валидна
    """
    try:
        # Проверяем доступность брокера
        if not hasattr(settings, 'CELERY_BROKER_URL'):
            logger.error("CELERY_BROKER_URL not configured")
            return False
            
        # Проверяем доступность backend'а
        if not hasattr(settings, 'CELERY_RESULT_BACKEND'):
            logger.error("CELERY_RESULT_BACKEND not configured")
            return False
            
        # Проверяем worker конфигурацию
        if not hasattr(worker_config, 'worker_name'):
            logger.warning("Worker name not configured, using default")
            
        logger.info("Celery configuration validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Celery configuration validation failed: {e}")
        return False

# Создание основного Celery приложения
celery_app = create_celery_app()

# Обработчики сигналов Celery

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Обработчик готовности worker'а"""
    logger.info(
        "Worker ready",
        worker_name=getattr(worker_config, 'worker_name', 'unknown'),
        concurrency=getattr(worker_config, 'worker_concurrency', 1),
        pool=getattr(worker_config, 'worker_pool', 'prefork')
    )
    
    # Проверяем конфигурацию
    if not validate_celery_config():
        logger.error("Configuration validation failed")
    else:
        logger.info("Worker configuration is valid")

@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Обработчик завершения работы worker'а"""
    logger.info("Worker shutting down", worker_name=getattr(worker_config, 'worker_name', 'unknown'))
    
    # Очищаем временные файлы
    try:
        import shutil
        temp_dir = getattr(worker_config, 'temp_dir', '/tmp/videobot')
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info("Temporary files cleaned up")
    except Exception as e:
        logger.error("Error cleaning up temporary files", error=str(e))

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Обработчик перед выполнением задачи"""
    logger.info(
        "Task started",
        task_id=task_id,
        task_name=task.name if task else "unknown",
        args_count=len(args) if args else 0,
        kwargs_keys=list(kwargs.keys()) if kwargs else []
    )

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, 
                        retval=None, state=None, **kwds):
    """Обработчик после выполнения задачи"""
    logger.info(
        "Task completed",
        task_id=task_id,
        task_name=task.name if task else "unknown",
        state=state,
        success=(state == 'SUCCESS')
    )

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Обработчик ошибок в задачах"""
    logger.error(
        "Task failed",
        task_id=task_id,
        task_name=sender.name if sender else "unknown",
        exception=str(exception),
        exception_type=type(exception).__name__
    )

# Функции для управления Celery

def start_worker(concurrency=None, pool=None, queues=None, loglevel='INFO'):
    """Запуск worker'а программно"""
    from celery.bin import worker
    
    concurrency = concurrency or getattr(worker_config, 'worker_concurrency', 4)
    pool = pool or getattr(worker_config, 'worker_pool', 'prefork')
    queues = queues or ['default', 'downloads', 'batch', 'cleanup', 'analytics', 'notifications']
    
    worker_instance = worker.worker(app=celery_app)
    
    options = {
        'concurrency': concurrency,
        'pool': pool,
        'queues': queues,
        'loglevel': loglevel,
        'traceback': True,
        'hostname': f"{getattr(worker_config, 'worker_name', 'worker')}@%h",
    }
    
    logger.info("Starting Celery worker", **options)
    worker_instance.run(**options)

def start_beat():
    """Запуск Celery Beat scheduler'а"""
    from celery.bin import beat
    
    beat_instance = beat.beat(app=celery_app)
    options = {
        'loglevel': 'INFO',
        'schedule_filename': '/tmp/celerybeat-schedule'
    }
    
    logger.info("Starting Celery Beat scheduler")
    beat_instance.run(**options)

def start_flower(port=5555):
    """Запуск Flower для мониторинга"""
    try:
        from flower.command import FlowerCommand
        
        flower_cmd = FlowerCommand()
        flower_cmd.apply_config_defaults()
        
        options = {
            'broker_api': settings.CELERY_BROKER_URL,
            'port': port,
            'url_prefix': '/flower',
        }
        
        logger.info(f"Starting Flower monitoring on port {port}")
        flower_cmd.run(**options)
    except ImportError:
        logger.error("Flower not installed. Install with: pip install flower")

def inspect_workers():
    """Инспекция активных worker'ов"""
    try:
        inspect = celery_app.control.inspect()
        
        return {
            'active': inspect.active(),
            'scheduled': inspect.scheduled(), 
            'reserved': inspect.reserved(),
            'stats': inspect.stats(),
            'registered': inspect.registered(),
        }
    except Exception as e:
        logger.error(f"Error inspecting workers: {e}")
        return {}

def purge_queue(queue_name):
    """Очистка очереди"""
    try:
        with celery_app.pool.acquire(block=True) as conn:
            return celery_app.control.purge()
    except Exception as e:
        logger.error(f"Error purging queue {queue_name}: {e}")
        return False

def get_queue_length(queue_name):
    """Получить длину очереди"""
    try:
        with celery_app.connection() as conn:
            return conn.default_channel.queue_declare(
                queue=queue_name, passive=True
            ).message_count
    except Exception as e:
        logger.error(f"Error getting queue length for {queue_name}: {e}")
        return 0

# Утилиты для задач

def get_task_info(task_id):
    """Получить информацию о задаче"""
    try:
        result = celery_app.AsyncResult(task_id)
        return {
            'id': task_id,
            'state': result.state,
            'result': result.result,
            'traceback': result.traceback,
            'info': result.info,
        }
    except Exception as e:
        logger.error(f"Error getting task info for {task_id}: {e}")
        return {'id': task_id, 'error': str(e)}

def cancel_task(task_id):
    """Отменить задачу"""
    try:
        celery_app.control.revoke(task_id, terminate=True)
        return True
    except Exception as e:
        logger.error(f"Error cancelling task {task_id}: {e}")
        return False

def retry_failed_tasks():
    """Повторить неудачные задачи"""
    # Эта функция будет реализована в tasks
    logger.info("Retry failed tasks functionality not implemented yet")
    return False

# Настройка логирования для Celery
import logging
from celery.utils.log import get_task_logger

def setup_logging():
    """Настройка логирования"""
    
    # Celery logger
    celery_logger = get_task_logger(__name__)
    celery_logger.setLevel(logging.INFO)
    
    # Форматтер
    formatter = logging.Formatter(
        '[%(asctime)s: %(levelname)s/%(name)s] %(message)s'
    )
    
    # Handler для файла
    log_dir = '/var/log/videobot'
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError:
            # Если не можем создать /var/log/videobot, используем /tmp
            log_dir = '/tmp'
        
    file_handler = logging.FileHandler(f'{log_dir}/worker.log')
    file_handler.setFormatter(formatter)
    celery_logger.addHandler(file_handler)

# Инициализация при импорте
try:
    setup_logging()
except Exception as e:
    print(f"Warning: Could not setup logging: {e}")

# Экспорт основных объектов
__all__ = [
    'celery_app',
    'create_celery_app',
    'validate_celery_config',
    'get_celery_config',
    'start_worker', 
    'start_beat',
    'start_flower',
    'inspect_workers',
    'get_task_info',
    'cancel_task',
]

print(f"🚀 VideoBot Pro Celery App initialized")