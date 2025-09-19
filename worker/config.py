"""
VideoBot Pro - Worker Configuration
Конфигурация для worker процессов
"""

import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class WorkerConfig:
    """Конфигурация worker'а"""
    
    # Основные настройки
    worker_name: str = "videobot-worker"
    worker_concurrency: int = 4
    worker_pool: str = "prefork"  # prefork, eventlet, gevent, solo
    
    # Таймауты
    task_timeout: int = 1800  # 30 минут
    soft_timeout: int = 1500  # 25 минут
    
    # Настройки производительности
    prefetch_multiplier: int = 1
    max_tasks_per_child: int = 1000
    max_memory_per_child: int = 200  # MB
    
    # Директории
    base_dir: str = field(default_factory=lambda: str(Path.cwd() / "worker_data"))
    temp_dir: str = field(default_factory=lambda: tempfile.gettempdir())
    download_temp_dir: str = field(default_factory=lambda: str(Path(tempfile.gettempdir()) / "videobot_downloads"))
    
    # Настройки файлов
    max_file_size_mb: int = 500
    cleanup_after_hours: int = 24
    
    # Настройки хранилища
    local_storage_path: str = field(default_factory=lambda: str(Path.cwd() / "storage"))
    
    def __post_init__(self):
        """Инициализация после создания"""
        # Создаем директории
        try:
            Path(self.base_dir).mkdir(parents=True, exist_ok=True)
            Path(self.download_temp_dir).mkdir(parents=True, exist_ok=True)
            Path(self.local_storage_path).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create worker directories: {e}")
    
    @property
    def LOCAL_STORAGE_PATH(self) -> str:
        """Свойство для совместимости с существующим кодом"""
        return self.local_storage_path
    
    @property
    def MAX_FILE_SIZE_MB(self) -> int:
        """Свойство для совместимости с существующим кодом"""
        return self.max_file_size_mb

# Создаем глобальный экземпляр конфигурации
worker_config = WorkerConfig()

def get_downloader_config(platform: str = None) -> Dict[str, Any]:
    """
    Получить конфигурацию для downloaders
    
    Args:
        platform: Платформа (youtube, tiktok, instagram)
        
    Returns:
        Словарь с конфигурацией
    """
    base_config = {
        'temp_dir': worker_config.download_temp_dir,
        'max_file_size_mb': worker_config.max_file_size_mb,
        'timeout': worker_config.soft_timeout,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    }
    
    # Платформо-специфичные настройки
    platform_configs = {
        'youtube': {
            'extract_flat': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'format': 'best[ext=mp4]/best',
        },
        'tiktok': {
            'api_endpoints': [
                "https://api.tikmate.app",
                "https://tikdown.org/api",
                "https://ssstik.io/abc",
            ]
        },
        'instagram': {
            'session_cookies': None,
            'use_api': True,
        }
    }
    
    if platform and platform in platform_configs:
        base_config.update(platform_configs[platform])
    
    return base_config

def get_storage_config(storage_type: str) -> Dict[str, Any]:
    """
    Получить конфигурацию для хранилища
    
    Args:
        storage_type: Тип хранилища (wasabi, backblaze, digitalocean, local)
        
    Returns:
        Словарь с конфигурацией
    """
    configs = {
        'wasabi': {
            'endpoint_url': os.getenv('WASABI_ENDPOINT_URL'),
            'aws_access_key_id': os.getenv('WASABI_ACCESS_KEY'),
            'aws_secret_access_key': os.getenv('WASABI_SECRET_KEY'),
            'bucket_name': os.getenv('WASABI_BUCKET_NAME'),
            'region_name': os.getenv('WASABI_REGION', 'us-east-1'),
        },
        'backblaze': {
            'key_id': os.getenv('B2_KEY_ID'),
            'application_key': os.getenv('B2_APPLICATION_KEY'),
            'bucket_name': os.getenv('B2_BUCKET_NAME'),
        },
        'digitalocean': {
            'endpoint_url': os.getenv('DO_SPACES_ENDPOINT'),
            'aws_access_key_id': os.getenv('DO_SPACES_KEY'),
            'aws_secret_access_key': os.getenv('DO_SPACES_SECRET'),
            'bucket_name': os.getenv('DO_SPACES_BUCKET'),
            'region_name': os.getenv('DO_SPACES_REGION', 'nyc3'),
        },
        'local': {
            'base_path': worker_config.local_storage_path,
            'url_prefix': 'http://localhost:8000/files',
        }
    }
    
    return configs.get(storage_type, {})

def validate_config() -> List[str]:
    """
    Валидация конфигурации worker'а
    
    Returns:
        Список ошибок конфигурации
    """
    errors = []
    
    try:
        # Проверяем директории
        if not os.path.exists(worker_config.base_dir):
            try:
                Path(worker_config.base_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                errors.append(f"Cannot create base directory: {worker_config.base_dir}")
        
        if not os.path.exists(worker_config.download_temp_dir):
            try:
                Path(worker_config.download_temp_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                errors.append(f"Cannot create temp directory: {worker_config.download_temp_dir}")
        
        # Проверяем настройки производительности
        if worker_config.worker_concurrency < 1:
            errors.append("Worker concurrency must be at least 1")
        
        if worker_config.task_timeout <= worker_config.soft_timeout:
            errors.append("Task timeout must be greater than soft timeout")
        
        if worker_config.max_file_size_mb < 1:
            errors.append("Max file size must be at least 1 MB")
        
        # Проверяем доступность инструментов
        try:
            import subprocess
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, timeout=5)
        except Exception:
            errors.append("FFmpeg not found or not working")
        
        try:
            import subprocess
            subprocess.run(['ffprobe', '-version'], capture_output=True, check=True, timeout=5)
        except Exception:
            errors.append("FFprobe not found or not working")
        
    except Exception as e:
        errors.append(f"Unexpected error during validation: {e}")
    
    return errors

def update_config(**kwargs):
    """
    Обновить конфигурацию worker'а
    
    Args:
        **kwargs: Параметры для обновления
    """
    global worker_config
    
    for key, value in kwargs.items():
        if hasattr(worker_config, key):
            setattr(worker_config, key, value)
            logger.info(f"Updated worker config: {key} = {value}")
        else:
            logger.warning(f"Unknown config parameter: {key}")

def get_config_summary() -> Dict[str, Any]:
    """
    Получить сводку конфигурации
    
    Returns:
        Словарь с основными параметрами конфигурации
    """
    return {
        'worker_name': worker_config.worker_name,
        'concurrency': worker_config.worker_concurrency,
        'pool': worker_config.worker_pool,
        'task_timeout': worker_config.task_timeout,
        'soft_timeout': worker_config.soft_timeout,
        'max_file_size_mb': worker_config.max_file_size_mb,
        'base_dir': worker_config.base_dir,
        'temp_dir': worker_config.download_temp_dir,
        'storage_path': worker_config.local_storage_path,
    }

def load_config_from_env():
    """Загрузить конфигурацию из переменных окружения"""
    env_mapping = {
        'WORKER_NAME': 'worker_name',
        'WORKER_CONCURRENCY': ('worker_concurrency', int),
        'WORKER_POOL': 'worker_pool',
        'TASK_TIMEOUT': ('task_timeout', int),
        'SOFT_TIMEOUT': ('soft_timeout', int),
        'MAX_FILE_SIZE_MB': ('max_file_size_mb', int),
        'WORKER_BASE_DIR': 'base_dir',
        'WORKER_TEMP_DIR': 'download_temp_dir',
        'WORKER_STORAGE_PATH': 'local_storage_path',
    }
    
    updates = {}
    
    for env_var, config_attr in env_mapping.items():
        env_value = os.getenv(env_var)
        if env_value:
            try:
                if isinstance(config_attr, tuple):
                    attr_name, attr_type = config_attr
                    updates[attr_name] = attr_type(env_value)
                else:
                    updates[config_attr] = env_value
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid value for {env_var}: {env_value} ({e})")
    
    if updates:
        update_config(**updates)
        logger.info(f"Loaded {len(updates)} config values from environment")

# Загружаем конфигурацию из окружения при импорте
try:
    load_config_from_env()
except Exception as e:
    logger.error(f"Error loading config from environment: {e}")

# Валидируем конфигурацию при импорте
try:
    validation_errors = validate_config()
    if validation_errors:
        logger.warning("Configuration validation errors:", errors=validation_errors)
    else:
        logger.info("Worker configuration validated successfully")
except Exception as e:
    logger.error(f"Error validating configuration: {e}")

logger.info("Worker configuration loaded", **get_config_summary())