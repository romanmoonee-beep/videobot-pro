"""
VideoBot Pro - Shared Services Package
Общие сервисы для всех компонентов системы
"""

from .database import DatabaseService, get_db_session, health_check
from .redis import RedisService, get_redis_client
from .auth import AuthService, TokenManager
from .analytics import AnalyticsService, MetricsCollector

# Глобальные экземпляры сервисов
database_service: DatabaseService = None
redis_service: RedisService = None
auth_service: AuthService = None
analytics_service: AnalyticsService = None

async def initialize_services():
    """Инициализация всех shared сервисов"""
    global database_service, redis_service, auth_service, analytics_service
    
    # Инициализация базы данных
    database_service = DatabaseService()
    await database_service.initialize()
    
    # Инициализация Redis
    redis_service = RedisService()
    await redis_service.initialize()
    
    # Инициализация аутентификации
    auth_service = AuthService()
    
    # Инициализация аналитики
    analytics_service = AnalyticsService(database_service, redis_service)
    
    return {
        'database': database_service,
        'redis': redis_service,
        'auth': auth_service,
        'analytics': analytics_service
    }

async def shutdown_services():
    """Корректное завершение работы сервисов"""
    global database_service, redis_service, auth_service, analytics_service
    
    if analytics_service:
        await analytics_service.shutdown()
    
    if redis_service:
        await redis_service.shutdown()
        
    if database_service:
        await database_service.shutdown()

def get_service_status():
    """Получить статус всех сервисов"""
    return {
        'database': database_service.is_healthy() if database_service else False,
        'redis': redis_service.is_healthy() if redis_service else False,
        'auth': auth_service.is_initialized() if auth_service else False,
        'analytics': analytics_service.is_running() if analytics_service else False
    }

__all__ = [
    # Основные сервисы
    'DatabaseService',
    'RedisService', 
    'AuthService',
    'AnalyticsService',
    
    # Вспомогательные классы
    'TokenManager',
    'MetricsCollector',
    
    # Утилиты
    'get_db_session',
    'get_redis_client',
    'health_check',
    
    # Управление сервисами
    'initialize_services',
    'shutdown_services',
    'get_service_status',
    
    # Глобальные экземпляры
    'database_service',
    'redis_service',
    'auth_service', 
    'analytics_service'
]