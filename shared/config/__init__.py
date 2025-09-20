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

# ИСПРАВЛЕНО: делаем импорты опциональными чтобы избежать ошибок
try:
    from .redis import init_redis, close_redis
    REDIS_AVAILABLE = True
except ImportError:
    def init_redis():
        return None
    def close_redis():
        return None
    REDIS_AVAILABLE = False

try:
    from .storage import (
        StorageConfig,
        storage_config,
        init_storage,
        close_storage
    )
except ImportError:
    StorageConfig = None
    storage_config = None
    init_storage = None
    close_storage = None

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
    
    # Redis (опционально)
    'init_redis',
    'close_redis',
    'redis',
    
    # Storage (опционально)
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
    if init_redis:
        await init_redis()
    if init_storage:
        await init_storage()

async def close_all_services():
    """Закрытие всех сервисов"""
    if close_storage:
        await close_storage()
    if close_redis:
        await close_redis()
    await close_database()