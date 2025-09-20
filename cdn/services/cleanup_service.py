"""
VideoBot Pro - CDN Cleanup Service
Сервис для автоматической очистки файлов CDN
"""

import asyncio
import structlog
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from shared.config.storage import storage_config
from ..config import cdn_config

logger = structlog.get_logger(__name__)

class CleanupService:
    """Сервис для автоматической очистки файлов"""
    
    def __init__(self):
        self.initialized = False
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Настройки очистки
        self.cleanup_interval = 3600  # Каждый час
        self.batch_size = 100  # Количество файлов для обработки за раз
        
        # Статистика очистки
        self.cleanup_stats = {
            'last_cleanup': None,
            'total_cleanups': 0,
            'files_deleted': 0,
            'space_freed_gb': 0.0,
            'errors': 0
        }
    
    async def initialize(self):
        """Инициализация сервиса очистки"""
        if self.initialized:
            return
        
        logger.info("Initializing Cleanup Service...")
        
        try:
            # Загружаем статистику
            await self._load_cleanup_stats()
            
            self.initialized = True
            logger.info("Cleanup Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Cleanup Service: {e}")
            raise
    
    async def shutdown(self):
        """Завершение работы сервиса"""
        logger.info("Shutting down Cleanup Service...")
        
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Сохраняем статистику
        await self._save_cleanup_stats()
        
        self.initialized = False
        logger.info("Cleanup Service shutdown completed")
    
    async def start_cleanup_scheduler(self):
        """Запуск планировщика автоматической очистки"""
        logger.info("Starting cleanup scheduler...")
        
        while self.initialized:
            try:
                await self.run_cleanup()
                await asyncio.sleep(self.cleanup_interval)
                
            except asyncio.CancelledError:
                logger.info("Cleanup scheduler cancelled")
                break
            except Exception as e:
                logger.error(f"Cleanup scheduler error: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед повтором
    
    async def run_cleanup(self) -> Dict[str, any]:
        """Запуск полной очистки"""
        logger.info("Starting cleanup process...")
        
        start_time = datetime.utcnow()
        cleanup_result = {
            'start_time': start_time.isoformat(),
            'expired_files': 0,
            'orphaned_files': 0,
            'cache_files': 0,
            'temp_files': 0,
            'space_freed_gb': 0.0,
            'errors': 0,
            'duration_seconds': 0
        }
        
        try:
            # Очистка истёкших файлов
            expired_result = await self._cleanup_expired_files()
            cleanup_result['expired_files'] = expired_result['deleted_count']
            cleanup_result['space_freed_gb'] += expired_result['freed_space_gb']
            
            # Очистка кэша
            cache_result = await self._cleanup_cache()
            cleanup_result['cache_files'] = cache_result['deleted_count']
            cleanup_result['space_freed_gb'] += cache_result['freed_space_gb']
            
            # Очистка временных файлов
            temp_result = await self._cleanup_temp_files()
            cleanup_result['temp_files'] = temp_result['deleted_count']
            cleanup_result['space_freed_gb'] += temp_result['freed_space_gb']
            
            # Очистка потерянных файлов
            orphaned_result = await self._cleanup_orphaned_files()
            cleanup_result['orphaned_files'] = orphaned_result['deleted_count']
            cleanup_result['space_freed_gb'] += orphaned_result['freed_space_gb']
            
            # Обновляем статистику
            self.cleanup_stats['last_cleanup'] = datetime.utcnow()
            self.cleanup_stats['total_cleanups'] += 1
            self.cleanup_stats['files_deleted'] += sum([
                cleanup_result['expired_files'],
                cleanup_result['cache_files'],
                cleanup_result['temp_files'],
                cleanup_result['orphaned_files']
            ])
            self.cleanup_stats['space_freed_gb'] += cleanup_result['space_freed_gb']
            
            # Сохраняем статистику
            await self._save_cleanup_stats()
            
            # Обновляем общую статистику CDN
            await cdn_config.update_stats('cleanup_completed', **cleanup_result)
            
        except Exception as e:
            logger.error(f"Cleanup process failed: {e}")
            cleanup_result['errors'] += 1
            self.cleanup_stats['errors'] += 1
        
        # Вычисляем время выполнения
        end_time = datetime.utcnow()
        cleanup_result['duration_seconds'] = (end_time - start_time).total_seconds()
        cleanup_result['end_time'] = end_time.isoformat()
        
        logger.info(
            f"Cleanup completed: {cleanup_result['expired_files'] + cleanup_result['cache_files'] + cleanup_result['temp_files'] + cleanup_result['orphaned_files']} files deleted, "
            f"{cleanup_result['space_freed_gb']:.2f} GB freed in {cleanup_result['duration_seconds']:.1f}s"
        )
        
        return cleanup_result
    
    async def cleanup_expired_files_by_user_type(self, user_type: str) -> Dict[str, any]:
        """Очистка истёкших файлов для конкретного типа пользователей"""
        logger.info(f"Cleaning up expired files for user type: {user_type}")
        
        deleted_count = 0
        freed_space_gb = 0.0
        errors = 0
        
        try:
            retention_hours = cdn_config.get_retention_hours(user_type)
            cutoff_time = datetime.utcnow() - timedelta(hours=retention_hours)
            
            # Определяем папки для проверки в зависимости от типа пользователя
            folders_to_check = self._get_user_folders(user_type)
            
            for folder in folders_to_check:
                folder_path = cdn_config.storage_path / folder
                if not folder_path.exists():
                    continue
                
                async for file_path in self._scan_files(folder_path):
                    try:
                        # Проверяем время создания файла
                        file_stat = file_path.stat()
                        file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
                        
                        if file_mtime < cutoff_time:
                            # Файл просрочен, удаляем
                            file_size = file_stat.st_size
                            
                            # Удаляем локальный файл
                            file_path.unlink()
                            
                            # Удаляем из внешнего хранилища
                            rel_path = file_path.relative_to(cdn_config.storage_path)
                            if storage_config and storage_config._initialized:
                                await storage_config.delete_file(str(rel_path))
                            
                            deleted_count += 1
                            freed_space_gb += file_size / (1024**3)
                            
                            logger.debug(f"Deleted expired file: {rel_path}")
                            
                    except Exception as e:
                        logger.error(f"Error deleting expired file {file_path}: {e}")
                        errors += 1
            
        except Exception as e:
            logger.error(f"Error cleaning expired files for {user_type}: {e}")
            errors += 1
        
        return {
            'deleted_count': deleted_count,
            'freed_space_gb': freed_space_gb,
            'errors': errors
        }
    
    async def cleanup_user_files(self, user_id: int) -> Dict[str, any]:
        """Очистка всех файлов конкретного пользователя"""
        logger.info(f"Cleaning up files for user {user_id}")
        
        deleted_count = 0
        freed_space_gb = 0.0
        errors = 0
        
        try:
            user_folder = cdn_config.storage_path / "users" / str(user_id)
            
            if user_folder.exists():
                async for file_path in self._scan_files(user_folder):
                    try:
                        file_size = file_path.stat().st_size
                        
                        # Удаляем локальный файл
                        file_path.unlink()
                        
                        # Удаляем из внешнего хранилища
                        rel_path = file_path.relative_to(cdn_config.storage_path)
                        if storage_config and storage_config._initialized:
                            await storage_config.delete_file(str(rel_path))
                        
                        deleted_count += 1
                        freed_space_gb += file_size / (1024**3)
                        
                    except Exception as e:
                        logger.error(f"Error deleting user file {file_path}: {e}")
                        errors += 1
                
                # Удаляем пустые папки
                try:
                    if user_folder.exists() and not any(user_folder.iterdir()):
                        user_folder.rmdir()
                except Exception as e:
                    logger.warning(f"Could not remove empty user folder: {e}")
            
        except Exception as e:
            logger.error(f"Error cleaning user {user_id} files: {e}")
            errors += 1
        
        return {
            'deleted_count': deleted_count,
            'freed_space_gb': freed_space_gb,
            'errors': errors
        }
    
    async def get_cleanup_stats(self) -> Dict[str, any]:
        """Получение статистики очистки"""
        return {
            **self.cleanup_stats,
            'next_cleanup': (
                self.cleanup_stats['last_cleanup'] + timedelta(seconds=self.cleanup_interval)
            ).isoformat() if self.cleanup_stats['last_cleanup'] else None,
            'cleanup_interval_hours': self.cleanup_interval / 3600
        }
    
    # Приватные методы
    
    async def _cleanup_expired_files(self) -> Dict[str, any]:
        """Очистка всех истёкших файлов"""
        logger.debug("Cleaning up expired files...")
        
        total_deleted = 0
        total_freed = 0.0
        
        # Очищаем файлы для каждого типа пользователей
        for user_type in ['free', 'trial', 'premium', 'admin']:
            result = await self.cleanup_expired_files_by_user_type(user_type)
            total_deleted += result['deleted_count']
            total_freed += result['freed_space_gb']
        
        return {
            'deleted_count': total_deleted,
            'freed_space_gb': total_freed
        }
    
    async def _cleanup_cache(self) -> Dict[str, any]:
        """Очистка кэша"""
        logger.debug("Cleaning up cache...")
        
        deleted_count = 0
        freed_space_gb = 0.0
        
        try:
            cache_ttl = timedelta(hours=cdn_config.cache_settings['cache_ttl_hours'])
            cutoff_time = datetime.utcnow() - cache_ttl
            
            async for cache_file in self._scan_files(cdn_config.cache_path):
                try:
                    file_stat = cache_file.stat()
                    file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
                    
                    if file_mtime < cutoff_time:
                        file_size = file_stat.st_size
                        cache_file.unlink()
                        
                        deleted_count += 1
                        freed_space_gb += file_size / (1024**3)
                        
                except Exception as e:
                    logger.error(f"Error deleting cache file {cache_file}: {e}")
            
            # Проверяем размер кэша
            await self._enforce_cache_size_limit()
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
        
        return {
            'deleted_count': deleted_count,
            'freed_space_gb': freed_space_gb
        }
    
    async def _cleanup_temp_files(self) -> Dict[str, any]:
        """Очистка временных файлов"""
        logger.debug("Cleaning up temporary files...")
        
        deleted_count = 0
        freed_space_gb = 0.0
        
        try:
            # Удаляем файлы старше 1 часа
            cutoff_time = datetime.utcnow() - timedelta(hours=1)
            
            async for temp_file in self._scan_files(cdn_config.temp_path):
                try:
                    file_stat = temp_file.stat()
                    file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
                    
                    if file_mtime < cutoff_time:
                        file_size = file_stat.st_size
                        temp_file.unlink()
                        
                        deleted_count += 1
                        freed_space_gb += file_size / (1024**3)
                        
                except Exception as e:
                    logger.error(f"Error deleting temp file {temp_file}: {e}")
            
        except Exception as e:
            logger.error(f"Temp files cleanup failed: {e}")
        
        return {
            'deleted_count': deleted_count,
            'freed_space_gb': freed_space_gb
        }
    
    async def _cleanup_orphaned_files(self) -> Dict[str, any]:
        """Очистка потерянных файлов (без записей в БД)"""
        logger.debug("Cleaning up orphaned files...")
        
        deleted_count = 0
        freed_space_gb = 0.0
        
        try:
            # Здесь будет логика проверки файлов против БД
            # Пока это заглушка
            pass
            
        except Exception as e:
            logger.error(f"Orphaned files cleanup failed: {e}")
        
        return {
            'deleted_count': deleted_count,
            'freed_space_gb': freed_space_gb
        }
    
    async def _enforce_cache_size_limit(self):
        """Принудительное ограничение размера кэша"""
        try:
            max_size_bytes = cdn_config.cache_settings['max_cache_size_gb'] * (1024**3)
            current_size = await self._calculate_directory_size(cdn_config.cache_path)
            
            if current_size <= max_size_bytes:
                return
            
            logger.info(f"Cache size {current_size / (1024**3):.2f} GB exceeds limit, cleaning...")
            
            # Получаем все файлы кэша с временем доступа
            cache_files = []
            async for cache_file in self._scan_files(cdn_config.cache_path):
                try:
                    stat = cache_file.stat()
                    cache_files.append({
                        'path': cache_file,
                        'size': stat.st_size,
                        'atime': stat.st_atime  # Время последнего доступа
                    })
                except Exception:
                    continue
            
            # Сортируем по времени доступа (старые первыми)
            cache_files.sort(key=lambda x: x['atime'])
            
            # Удаляем файлы пока не достигнем лимита
            freed_space = 0
            for file_info in cache_files:
                if current_size - freed_space <= max_size_bytes:
                    break
                
                try:
                    file_info['path'].unlink()
                    freed_space += file_info['size']
                    logger.debug(f"Removed cache file: {file_info['path']}")
                except Exception as e:
                    logger.error(f"Error removing cache file: {e}")
            
            logger.info(f"Cache cleanup completed, freed {freed_space / (1024**3):.2f} GB")
            
        except Exception as e:
            logger.error(f"Cache size enforcement failed: {e}")
    
    async def _scan_files(self, directory: Path):
        """Асинхронный генератор для сканирования файлов"""
        try:
            if not directory.exists() or not directory.is_dir():
                return
            
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    yield file_path
                    # Даем другим задачам возможность выполниться
                    await asyncio.sleep(0)
                    
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
    
    async def _calculate_directory_size(self, directory: Path) -> int:
        """Вычисление размера директории"""
        total_size = 0
        
        try:
            async for file_path in self._scan_files(directory):
                try:
                    total_size += file_path.stat().st_size
                except Exception:
                    continue
                    
        except Exception as e:
            logger.error(f"Error calculating directory size {directory}: {e}")
        
        return total_size
    
    def _get_user_folders(self, user_type: str) -> List[str]:
        """Получение папок для проверки по типу пользователя"""
        if user_type == 'free':
            return ['users', 'free']
        elif user_type == 'trial':
            return ['trial']
        elif user_type == 'premium':
            return ['premium']
        elif user_type == 'admin':
            return ['admin']
        else:
            return ['users']
    
    async def _load_cleanup_stats(self):
        """Загрузка статистики очистки"""
        try:
            import json
            stats_file = cdn_config.storage_path / "cleanup_stats.json"
            
            if stats_file.exists():
                async with aiofiles.open(stats_file, 'r') as f:
                    content = await f.read()
                    saved_stats = json.loads(content)
                    
                    # Конвертируем строки обратно в datetime
                    if saved_stats.get('last_cleanup'):
                        saved_stats['last_cleanup'] = datetime.fromisoformat(
                            saved_stats['last_cleanup']
                        )
                    
                    self.cleanup_stats.update(saved_stats)
                    logger.debug("Cleanup statistics loaded")
                    
        except Exception as e:
            logger.warning(f"Failed to load cleanup stats: {e}")
    
    async def _save_cleanup_stats(self):
        """Сохранение статистики очистки"""
        try:
            import json
            stats_file = cdn_config.storage_path / "cleanup_stats.json"
            
            # Подготавливаем данные для сохранения
            stats_to_save = self.cleanup_stats.copy()
            if stats_to_save.get('last_cleanup'):
                stats_to_save['last_cleanup'] = stats_to_save['last_cleanup'].isoformat()
            
            async with aiofiles.open(stats_file, 'w') as f:
                await f.write(json.dumps(stats_to_save, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save cleanup stats: {e}")