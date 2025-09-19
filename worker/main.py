"""
VideoBot Pro - Worker Main
Точка входа для запуска worker'а
"""

import os
import sys
import asyncio
import signal
from typing import Optional
import structlog

from .celery_app import celery_app, validate_celery_config
from .config import worker_config
from shared.config.database import init_database, close_database
from shared.config.redis import init_redis, close_redis

logger = structlog.get_logger(__name__)

class WorkerManager:
    """Менеджер для управления жизненным циклом worker'а"""
    
    def __init__(self):
        self.worker = None
        self.is_running = False
        self.shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """Инициализация worker'а"""
        logger.info("Initializing VideoBot Worker...")
        
        try:
            # Инициализируем базу данных
            await init_database()
            logger.info("Database connection established")
            
            # Инициализируем Redis
            await init_redis()
            logger.info("Redis connection established")
            
            # Валидируем конфигурацию Celery
            if not validate_celery_config():
                raise RuntimeError("Celery configuration validation failed")
            
            # Создаем директории для временных файлов
            os.makedirs(worker_config.download_temp_dir, exist_ok=True)
            logger.info(f"Temp directory ready: {worker_config.download_temp_dir}")
            
            logger.info("Worker initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Worker initialization failed: {e}")
            return False
    
    async def start_worker(self, worker_type: str = "worker"):
        """
        Запуск worker'а
        
        Args:
            worker_type: Тип worker'а (worker, beat, flower)
        """
        if not await self.initialize():
            sys.exit(1)
        
        self.is_running = True
        
        # Настройка обработчиков сигналов
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info(f"Starting {worker_type}...")
        
        try:
            if worker_type == "worker":
                await self._start_celery_worker()
            elif worker_type == "beat":
                await self._start_celery_beat()
            elif worker_type == "flower":
                await self._start_flower()
            else:
                raise ValueError(f"Unknown worker type: {worker_type}")
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Worker error: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def _start_celery_worker(self):
        """Запуск Celery worker'а"""
        # Импортируем все задачи для регистрации
        from . import tasks
        
        # Параметры запуска worker'а
        worker_args = [
            "--app=worker.celery_app:celery_app",
            f"--concurrency={worker_config.worker_concurrency}",
            f"--hostname=worker@%h",
            "--loglevel=INFO",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
        ]
        
        # Определяем очереди для обработки
        queues = ["default", "downloads", "batches", "cleanup", "analytics", "notifications"]
        worker_args.append(f"--queues={','.join(queues)}")
        
        logger.info(f"Starting Celery worker with args: {worker_args}")
        
        # Запускаем worker в отдельном процессе
        from celery.bin import worker
        worker_instance = worker.worker(app=celery_app)
        worker_instance.run(**{
            'concurrency': worker_config.worker_concurrency,
            'loglevel': 'INFO',
            'queues': queues,
            'hostname': 'worker@%h',
        })
    
    async def _start_celery_beat(self):
        """Запуск Celery Beat (планировщика)"""
        logger.info("Starting Celery Beat scheduler")
        
        from celery.bin import beat
        beat_instance = beat.beat(app=celery_app)
        beat_instance.run(
            loglevel='INFO',
            schedule_filename='celerybeat-schedule',
        )
    
    async def _start_flower(self):
        """Запуск Flower (мониторинг)"""
        logger.info("Starting Flower monitoring")
        
        try:
            import flower
            from flower.command import FlowerCommand
            
            flower_cmd = FlowerCommand()
            flower_cmd.execute_from_commandline([
                'flower',
                '--app=worker.celery_app:celery_app',
                '--port=5555',
                '--address=0.0.0.0',
            ])
        except ImportError:
            logger.error("Flower is not installed. Install with: pip install flower")
            raise
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов завершения"""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.shutdown_event.set()
        self.is_running = False
    
    async def shutdown(self):
        """Корректное завершение работы worker'а"""
        logger.info("Shutting down worker...")
        
        try:
            # Закрываем соединения с базой данных
            await close_database()
            logger.info("Database connections closed")
            
            # Закрываем Redis
            await close_redis()
            logger.info("Redis connections closed")
            
            # Очищаем временные файлы
            await self._cleanup_temp_files()
            
            logger.info("Worker shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    async def _cleanup_temp_files(self):
        """Очистка временных файлов"""
        try:
            import shutil
            if os.path.exists(worker_config.download_temp_dir):
                for filename in os.listdir(worker_config.download_temp_dir):
                    file_path = os.path.join(worker_config.download_temp_dir, filename)
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                logger.info("Temporary files cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning temp files: {e}")

def main():
    """Основная функция запуска"""
    import argparse
    
    parser = argparse.ArgumentParser(description="VideoBot Pro Worker")
    parser.add_argument(
        "command",
        choices=["worker", "beat", "flower", "status"],
        help="Command to run"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=worker_config.worker_concurrency,
        help="Number of concurrent worker processes"
    )
    parser.add_argument(
        "--queues",
        default="default,downloads,batches",
        help="Comma-separated list of queues to process"
    )
    parser.add_argument(
        "--loglevel",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Обновляем конфигурацию из аргументов
    if args.concurrency != worker_config.worker_concurrency:
        worker_config.worker_concurrency = args.concurrency
    
    manager = WorkerManager()
    
    if args.command == "status":
        # Показываем статус worker'а
        show_worker_status()
    else:
        # Запускаем worker
        asyncio.run(manager.start_worker(args.command))

def show_worker_status():
    """Показать статус worker'а"""
    try:
        # Проверяем активные worker'ы
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        active = inspect.active()
        
        if not stats:
            print("❌ No active workers found")
            return
        
        print("📊 Worker Status:")
        print("=" * 50)
        
        for worker_name, worker_stats in stats.items():
            print(f"\n🔧 Worker: {worker_name}")
            print(f"   Pool: {worker_stats.get('pool', {}).get('implementation', 'N/A')}")
            print(f"   Processes: {worker_stats.get('pool', {}).get('processes', 'N/A')}")
            print(f"   Active tasks: {len(active.get(worker_name, []))}")
            
            # Показываем активные задачи
            active_tasks = active.get(worker_name, [])
            if active_tasks:
                print("   📋 Active tasks:")
                for task in active_tasks[:3]:  # Показываем только первые 3
                    print(f"      - {task['name']} ({task['id'][:8]}...)")
                if len(active_tasks) > 3:
                    print(f"      ... and {len(active_tasks) - 3} more")
        
        # Проверяем очереди
        print("\n📥 Queue Status:")
        reserved = inspect.reserved()
        for worker_name, tasks in reserved.items():
            if tasks:
                print(f"   {worker_name}: {len(tasks)} reserved tasks")
        
    except Exception as e:
        print(f"❌ Error getting worker status: {e}")

if __name__ == "__main__":
    main()