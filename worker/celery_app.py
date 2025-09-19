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

from shared.config.settings import settings
from worker.config import worker_config

logger = structlog.get_logger(__name__)

# Создание Celery приложения
celery_app = Celery(
    'videobot_worker',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'worker.tasks.download_tasks',
        'worker.tasks.batch_tasks', 
        'worker.tasks.cleanup_tasks',
        'worker.tasks.analytics_tasks',
        'worker.tasks.notification_tasks',
    ]
)

# Конфигурация Celery
celery_app.conf.update(
    # Настройки задач
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Timeouts
    task_soft_time_limit=worker_config.soft_timeout,
    task_time_limit=worker_config.task_timeout,
    
    # Worker настройки
    worker_prefetch_multiplier=worker_config.prefetch_multiplier,
    worker_max_tasks_per_child=worker_config.max_tasks_per_child,
    worker_max_memory_per_child=worker_config.max_memory_per_child,
    
    # Retry настройки
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Результаты
    result_expires=3600,  # 1 час
    result_persistent=True,
    
    # Мониторинг
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Маршрутизация задач по очередям
    task_routes={
        'worker.tasks.download_tasks.*': {'queue': 'downloads'},
        'worker.tasks.batch_tasks.*': {'queue': 'batch'},
        'worker.tasks.cleanup_tasks.*': {'queue': 'cleanup'},
        'worker.tasks.analytics_tasks.*': {'queue': 'analytics'},
        'worker.tasks.notification_tasks.*': {'queue': 'notifications'},
    },
    
    # Определение очередей
    task_default_queue='default',
    task_queues=(
        Queue('default', routing_key='default'),
        Queue('downloads', routing_key='downloads'),
        Queue('batch', routing_key='batch'),
        Queue('cleanup', routing_key='cleanup'),
        Queue('analytics', routing_key='analytics'),
        Queue('notifications', routing_key='notifications'),
        Queue('priority', routing_key='priority'),  # Для приоритетных задач
    ),
    
    # Приоритеты очередей
    task_queue_priority={
        'priority': 10,
        'downloads': 7,
        'batch': 5,
        'notifications': 3,
        'analytics': 2,
        'cleanup': 1,
    },
    
    # Beat scheduler (для периодических задач)
    beat_schedule={
        'cleanup-temp-files': {
            'task': 'worker.tasks.cleanup_tasks.cleanup_temp_files',
            'schedule': timedelta(hours=1),
        },
        'cleanup-old-downloads': {
            'task': 'worker.tasks.cleanup_tasks.cleanup_old_downloads',
            'schedule': timedelta(hours=6),
        },
        'update-daily-analytics': {
            'task': 'worker.tasks.analytics_tasks.update_daily_analytics',
            'schedule': timedelta(hours=1),
        },
        'health-check': {
            'task': 'worker.tasks.analytics_tasks.worker_health_check',
            'schedule': timedelta(minutes=5),
        },
        'storage-cleanup': {
            'task': 'worker.tasks.cleanup_tasks.cleanup_expired_files',
            'schedule': timedelta(hours=12),
        },
    },
    
    # Дополнительные настройки
    worker_disable_rate_limits=True,
    task_ignore_result=False,
    
    # Логирование
    worker_log_format='[%(asctime)s: %(levelname)s/%(name)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(name)s][%(task_name)s(%(task_id)s)] %(message)s',
)

# Обработчики сигналов Celery

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Обработчик готовности worker'а"""
    logger.info(
        "Worker ready",
        worker_name=worker_config.worker_name,
        concurrency=worker_config.worker_concurrency,
        pool=worker_config.worker_pool
    )
    
    # Проверяем конфигурацию
    from worker.config import validate_config
    errors = validate_config()
    if errors:
        logger.error("Configuration errors detected", errors=errors)
    else:
        logger.info("Worker configuration is valid")

@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Обработчик завершения работы worker'а"""
    logger.info("Worker shutting down", worker_name=worker_config.worker_name)
    
    # Очищаем временные файлы
    try:
        import shutil
        if worker_config.temp_dir.exists():
            shutil.rmtree(worker_config.temp_dir, ignore_errors=True)
        logger.info("Temporary files cleaned up")
    except Exception as e:
        logger.error("Error cleaning up temporary files", error=str(e))

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Обработчик перед выполнением задачи"""
    logger.info(
        "Task started",
        task_id=task_id,
        task_name=task.name,
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
        task_name=task.name,
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

# Middleware для мониторинга производительности
class TaskPerformanceMiddleware:
    """Middleware для отслеживания производительности задач"""
    
    def __init__(self, get_response=None):
        self.get_response = get_response
        
    def __call__(self, request):
        # Логика до выполнения задачи
        start_time = time.time()
        
        response = self.get_response(request) if self.get_response else None
        
        # Логика после выполнения задачи
        duration = time.time() - start_time
        
        if duration > 60:  # Задачи дольше минуты
            logger.warning(
                "Long running task detected",
                duration=duration,
                task_name=getattr(request, 'task_name', 'unknown')
            )
        
        return response

# Функции для управления Celery

def start_worker(concurrency=None, pool=None, queues=None, loglevel='INFO'):
    """Запуск worker'а программно"""
    from celery.bin import worker
    
    concurrency = concurrency or worker_config.worker_concurrency
    pool = pool or worker_config.worker_pool
    queues = queues or ['default', 'downloads', 'batch', 'cleanup', 'analytics', 'notifications']
    
    worker_instance = worker.worker(app=celery_app)
    
    options = {
        'concurrency': concurrency,
        'pool': pool,
        'queues': queues,
        'loglevel': loglevel,
        'traceback': True,
        'hostname': f"{worker_config.worker_name}@%h",
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
    inspect = celery_app.control.inspect()
    
    return {
        'active': inspect.active(),
        'scheduled': inspect.scheduled(), 
        'reserved': inspect.reserved(),
        'stats': inspect.stats(),
        'registered': inspect.registered(),
    }

def purge_queue(queue_name):
    """Очистка очереди"""
    with celery_app.pool.acquire(block=True) as conn:
        return celery_app.control.purge()

def get_queue_length(queue_name):
    """Получить длину очереди"""
    with celery_app.connection() as conn:
        return conn.default_channel.queue_declare(
            queue=queue_name, passive=True
        ).message_count

# Утилиты для задач

def get_task_info(task_id):
    """Получить информацию о задаче"""
    result = celery_app.AsyncResult(task_id)
    return {
        'id': task_id,
        'state': result.state,
        'result': result.result,
        'traceback': result.traceback,
        'info': result.info,
    }

def cancel_task(task_id):
    """Отменить задачу"""
    celery_app.control.revoke(task_id, terminate=True)

def retry_failed_tasks():
    """Повторить неудачные задачи"""
    # Эта функция будет реализована в tasks
    pass

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
    if not os.path.exists('/var/log/videobot'):
        os.makedirs('/var/log/videobot', exist_ok=True)
        
    file_handler = logging.FileHandler('/var/log/videobot/worker.log')
    file_handler.setFormatter(formatter)
    celery_logger.addHandler(file_handler)

# Инициализация при импорте
setup_logging()

# Экспорт основных объектов
__all__ = [
    'celery_app',
    'start_worker', 
    'start_beat',
    'start_flower',
    'inspect_workers',
    'get_task_info',
    'cancel_task',
]