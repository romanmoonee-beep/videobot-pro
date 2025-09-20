"""
VideoBot Pro - CDN Configuration
Конфигурация CDN сервиса
"""

import os
import asyncio
import aiofiles
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

from shared.config.settings import settings
from shared.config.storage import storage_config, StorageProvider

logger = structlog.get_logger(__name__)

class CDNConfig:
    """Конфигурация CDN сервиса"""
    
    def __init__(self):
        self.initialized = False
        
        # Пути хранения
        self.storage_path = Path(settings.WORKER_STORAGE_PATH)
        self.temp_path = Path(settings.WORKER_TEMP_DIR)
        self.cache_path = self.storage_path / "cache"
        
        # Настройки CDN
        self.max_file_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024  # В байтах
        self.allowed_extensions = {
            'video': ['.mp4', '.webm', '.mkv', '.avi', '.mov'],
            'audio': ['.mp3', '.aac', '.wav', '.flac', '.ogg'],
            'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
            'archive': ['.zip', '.rar', '.7z', '.tar', '.gz']
        }
        
        # Время жизни файлов по типам пользователей (в часах)
        self.file_retention = {
            'free': settings.FREE_FILE_RETENTION_HOURS,
            'trial': settings.FREE_FILE_RETENTION_HOURS,
            'premium': settings.PREMIUM_FILE_RETENTION_HOURS,
            'admin': settings.ADMIN_FILE_RETENTION_HOURS
        }
        
        # Настройки кэширования
        self.cache_settings = {
            'max_cache_size_gb': 10,  # Максимальный размер кэша
            'cache_ttl_hours': 24,    # Время жизни кэша
            'enable_compression': True,
            'compression_formats': ['.txt', '.js', '.css', '.json', '.xml']
        }
        
        # Настройки пропускной способности
        self.bandwidth_settings = {
            'max_bandwidth_mbps': settings.CDN_MAX_BANDWIDTH_MBPS,
            'concurrent_downloads': 100,
            'rate_limit_per_ip': 10,  # Запросов в минуту с одного IP
            'rate_limit_window': 60   # Окно в секундах
        }
        
        # Статистика
        self.stats = {
            'total_files': 0,
            'total_size_gb': 0.0,
            'requests_count': 0,
            'bandwidth_used_gb': 0.0,
            'cache_hits': 0,
            'cache_misses': 0
        }
    
    async def initialize(self):
        """Инициализация CDN конфигурации"""
        if self.initialized:
            return
        
        logger.info("Initializing CDN configuration...")
        
        try:
            # Создаем необходимые директории
            await self._create_directories()
            
            # Инициализируем хранилище
            await storage_config.initialize()
            
            # Загружаем статистику
            await self._load_stats()
            
            # Очищаем временные файлы
            await self._cleanup_temp_files()
            
            self.initialized = True
            logger.info("CDN configuration initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize CDN configuration: {e}")
            raise
    
    async def _create_directories(self):
        """Создание необходимых директорий"""
        directories = [
            self.storage_path,
            self.temp_path,
            self.cache_path,
            self.storage_path / "uploads",
            self.storage_path / "processed",
            self.storage_path / "archives"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Directory ensured: {directory}")
    
    async def _cleanup_temp_files(self):
        """Очистка временных файлов"""
        try:
            temp_files = list(self.temp_path.rglob("*"))
            deleted_count = 0
            
            for file_path in temp_files:
                if file_path.is_file():
                    try:
                        # Удаляем файлы старше 1 часа
                        file_age = datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)
                        if file_age > timedelta(hours=1):
                            file_path.unlink()
                            deleted_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete temp file {file_path}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} temporary files")
                
        except Exception as e:
            logger.error(f"Temp files cleanup failed: {e}")
    
    async def _load_stats(self):
        """Загрузка статистики CDN"""
        try:
            stats_file = self.storage_path / "cdn_stats.json"
            
            if stats_file.exists():
                import json
                async with aiofiles.open(stats_file, 'r') as f:
                    content = await f.read()
                    saved_stats = json.loads(content)
                    self.stats.update(saved_stats)
                    logger.info("CDN statistics loaded")
            else:
                await self._calculate_initial_stats()
                
        except Exception as e:
            logger.warning(f"Failed to load CDN stats: {e}")
            await self._calculate_initial_stats()
    
    async def _calculate_initial_stats(self):
        """Расчет начальной статистики"""
        try:
            total_files = 0
            total_size = 0
            
            # Подсчитываем файлы в storage
            for file_path in self.storage_path.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith('.'):
                    total_files += 1
                    total_size += file_path.stat().st_size
            
            self.stats.update({
                'total_files': total_files,
                'total_size_gb': total_size / (1024**3)
            })
            
            await self._save_stats()
            logger.info(f"Initial stats calculated: {total_files} files, {total_size / (1024**3):.2f} GB")
            
        except Exception as e:
            logger.error(f"Failed to calculate initial stats: {e}")
    
    async def _save_stats(self):
        """Сохранение статистики"""
        try:
            import json
            stats_file = self.storage_path / "cdn_stats.json"
            
            async with aiofiles.open(stats_file, 'w') as f:
                await f.write(json.dumps(self.stats, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save CDN stats: {e}")
    
    def is_allowed_extension(self, filename: str, file_type: str = None) -> bool:
        """Проверка разрешенного расширения файла"""
        ext = Path(filename).suffix.lower()
        
        if file_type and file_type in self.allowed_extensions:
            return ext in self.allowed_extensions[file_type]
        
        # Проверяем во всех категориях
        for extensions in self.allowed_extensions.values():
            if ext in extensions:
                return True
        
        return False
    
    def get_file_type(self, filename: str) -> Optional[str]:
        """Определение типа файла по расширению"""
        ext = Path(filename).suffix.lower()
        
        for file_type, extensions in self.allowed_extensions.items():
            if ext in extensions:
                return file_type
        
        return None
    
    def get_retention_hours(self, user_type: str) -> int:
        """Получение времени хранения для типа пользователя"""
        return self.file_retention.get(user_type, self.file_retention['free'])
    
    def get_max_file_size(self, user_type: str) -> int:
        """Получение максимального размера файла для пользователя"""
        size_limits = {
            'free': settings.FREE_MAX_FILE_SIZE_MB,
            'trial': settings.PREMIUM_MAX_FILE_SIZE_MB,
            'premium': settings.PREMIUM_MAX_FILE_SIZE_MB,
            'admin': settings.ADMIN_MAX_FILE_SIZE_MB
        }
        
        max_size_mb = size_limits.get(user_type, size_limits['free'])
        return max_size_mb * 1024 * 1024  # Возвращаем в байтах
    
    async def update_stats(self, operation: str, **kwargs):
        """Обновление статистики CDN"""
        try:
            if operation == 'file_uploaded':
                self.stats['total_files'] += 1
                self.stats['total_size_gb'] += kwargs.get('size_gb', 0)
            
            elif operation == 'file_downloaded':
                self.stats['requests_count'] += 1
                self.stats['bandwidth_used_gb'] += kwargs.get('size_gb', 0)
            
            elif operation == 'file_deleted':
                self.stats['total_files'] -= 1
                self.stats['total_size_gb'] -= kwargs.get('size_gb', 0)
            
            elif operation == 'cache_hit':
                self.stats['cache_hits'] += 1
            
            elif operation == 'cache_miss':
                self.stats['cache_misses'] += 1
            
            # Сохраняем статистику периодически
            if self.stats['requests_count'] % 100 == 0:
                await self._save_stats()
                
        except Exception as e:
            logger.error(f"Failed to update stats: {e}")
    
    async def get_storage_info(self) -> Dict[str, Any]:
        """Получение информации о хранилище"""
        try:
            storage_info = {
                'local_storage': {
                    'path': str(self.storage_path),
                    'total_files': self.stats['total_files'],
                    'total_size_gb': round(self.stats['total_size_gb'], 2)
                },
                'cache': {
                    'path': str(self.cache_path),
                    'max_size_gb': self.cache_settings['max_cache_size_gb'],
                    'hits': self.stats['cache_hits'],
                    'misses': self.stats['cache_misses'],
                    'hit_ratio': self._calculate_cache_hit_ratio()
                },
                'bandwidth': {
                    'max_mbps': self.bandwidth_settings['max_bandwidth_mbps'],
                    'used_gb': round(self.stats['bandwidth_used_gb'], 2),
                    'requests_total': self.stats['requests_count']
                }
            }
            
            # Добавляем информацию о внешнем хранилище
            if storage_config:
                external_stats = await storage_config.get_storage_stats()
                storage_info['external_storage'] = external_stats
            
            return storage_info
            
        except Exception as e:
            logger.error(f"Failed to get storage info: {e}")
            return {}
    
    def _calculate_cache_hit_ratio(self) -> float:
        """Расчет коэффициента попаданий в кэш"""
        total_requests = self.stats['cache_hits'] + self.stats['cache_misses']
        if total_requests == 0:
            return 0.0
        return round((self.stats['cache_hits'] / total_requests) * 100, 2)
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка здоровья CDN"""
        try:
            # Проверяем доступность директорий
            directories_ok = all([
                self.storage_path.exists(),
                self.temp_path.exists(),
                self.cache_path.exists()
            ])
            
            # Проверяем свободное место
            storage_stats = os.statvfs(self.storage_path)
            free_space_gb = (storage_stats.f_bavail * storage_stats.f_frsize) / (1024**3)
            
            # Проверяем внешнее хранилище
            external_storage_ok = True
            try:
                if storage_config and storage_config._initialized:
                    # Простая проверка доступности
                    await storage_config.file_exists("health_check_test")
            except Exception:
                external_storage_ok = False
            
            # Определяем общий статус
            overall_status = "healthy"
            if not directories_ok:
                overall_status = "unhealthy"
            elif free_space_gb < 1.0:  # Меньше 1 ГБ свободного места
                overall_status = "warning"
            elif not external_storage_ok:
                overall_status = "warning"
            
            return {
                "status": overall_status,
                "checks": {
                    "directories": directories_ok,
                    "free_space_gb": round(free_space_gb, 2),
                    "external_storage": external_storage_ok,
                    "total_files": self.stats['total_files'],
                    "cache_hit_ratio": self._calculate_cache_hit_ratio()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"CDN health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def cleanup_expired_files(self) -> Dict[str, int]:
        """Очистка истекших файлов"""
        try:
            deleted_files = 0
            freed_space_gb = 0.0
            
            # Очищаем кэш
            cache_deleted, cache_freed = await self._cleanup_cache()
            deleted_files += cache_deleted
            freed_space_gb += cache_freed
            
            # Очищаем временные файлы
            await self._cleanup_temp_files()
            
            # Обновляем статистику
            self.stats['total_files'] -= deleted_files
            self.stats['total_size_gb'] -= freed_space_gb
            await self._save_stats()
            
            logger.info(f"Cleanup completed: {deleted_files} files, {freed_space_gb:.2f} GB freed")
            
            return {
                'deleted_files': deleted_files,
                'freed_space_gb': round(freed_space_gb, 2)
            }
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return {'deleted_files': 0, 'freed_space_gb': 0.0}
    
    async def _cleanup_cache(self) -> tuple:
        """Очистка кэша"""
        deleted_count = 0
        freed_space = 0.0
        
        try:
            cache_ttl = timedelta(hours=self.cache_settings['cache_ttl_hours'])
            cutoff_time = datetime.now() - cache_ttl
            
            for cache_file in self.cache_path.rglob("*"):
                if cache_file.is_file():
                    file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        file_size = cache_file.stat().st_size
                        cache_file.unlink()
                        deleted_count += 1
                        freed_space += file_size / (1024**3)
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
        
        return deleted_count, freed_space
    
    def get_file_url(self, file_path: str, cdn_domain: str = None) -> str:
        """Генерация URL файла для CDN"""
        if cdn_domain:
            return f"https://{cdn_domain}/{file_path}"
        else:
            return f"http://{settings.CDN_HOST}:{settings.CDN_PORT}/api/v1/files/{file_path}"

# Глобальный экземпляр конфигурации
cdn_config = CDNConfig()