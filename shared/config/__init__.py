"""
VideoBot Pro - Shared Config Package
Централизованная конфигурация для всех сервисов
"""

from .settings import settings, get_settings
from .database import (
    init_database, 
    close_database, 
    get_async_session,
    get_sync_session,
    DatabaseHealthCheck,
    DatabaseMaintenance,
    with_retry,
    db_config
)
from .redis import init_redis, close_redis, redis
from .storage import (
    StorageConfig,
    storage_config,
    init_storage,
    close_storage
)

__all__ = [
    # Settings
    'settings',
    'get_settings',
    
    # Database
    'init_database',
    'close_database', 
    'get_async_session',
    'get_sync_session',
    'DatabaseHealthCheck',
    'DatabaseMaintenance',
    'with_retry',
    'db_config',
    
    # Redis
    'init_redis',
    'close_redis',
    'redis',
    
    # Storage
    'StorageConfig',
    'storage_config',
    'init_storage',
    'close_storage'
]

class DatabaseConfig:
    """Конфигурация базы данных - заглушка для совместимости"""
    pass

# Функции инициализации всех сервисов
async def init_all_services():
    """Инициализация всех сервисов конфигурации"""
    await init_database()
    await init_redis()
    await init_storage()

async def close_all_services():
    """Закрытие всех сервисов"""
    await close_storage()
    await close_redis()
    await close_database()