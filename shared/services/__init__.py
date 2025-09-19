"""
VideoBot Pro - Shared Services Package
Общие сервисы для всех компонентов системы
"""

# ИСПРАВЛЕНО: делаем импорты опциональными
try:
    from .database import DatabaseService, get_db_session, health_check
except ImportError:
    DatabaseService = None
    get_db_session = None
    health_check = None

try:
    from .redis import RedisService, get_redis_client
except ImportError:
    RedisService = None
    get_redis_client = None

try:
    from .auth import AuthService
except ImportError:
    AuthService = None

try:
    from .analytics import AnalyticsService
except ImportError:
    AnalyticsService = None

# Глобальные экземпляры сервисов
database_service = None
redis_service = None
auth_service = None
analytics_service = None

async def initialize_services():
    """Инициализация всех shared сервисов"""
    global database_service, redis_service, auth_service, analytics_service
    
    services = {}
    
    # Инициализация базы данных
    if DatabaseService:
        database_service = DatabaseService()
        await database_service.initialize()
        services['database'] = database_service
    
    # Инициализация Redis
    if RedisService:
        redis_service = RedisService()
        await redis_service.initialize()
        services['redis'] = redis_service
    
    # Инициализация аутентификации
    if AuthService:
        auth_service = AuthService()
        services['auth'] = auth_service
    
    # Инициализация аналитики
    if AnalyticsService and database_service and redis_service:
        analytics_service = AnalyticsService(database_service, redis_service)
        services['analytics'] = analytics_service
    
    return services

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