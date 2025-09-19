"""
VideoBot Pro - Shared Package
Общий пакет для всех компонентов системы
"""

# Версия shared пакета
__version__ = "2.1.0"
__author__ = "VideoBot Pro Team"
__description__ = "Shared components for VideoBot Pro system"

# Конфигурация
from .config import (
    settings,
    get_settings,
    init_database,
    close_database,
    get_async_session,
    get_sync_session,
    DatabaseConfig,
    DatabaseHealthCheck,
    DatabaseMaintenance,
)

# Модели базы данных
from .models import (
    # Базовые классы
    Base,
    BaseModel,
    BaseModelWithSoftDelete,
    BaseModelWithUUID,
    BaseActiveModel,
    BaseFullModel,
    
    # Миксины
    TimestampMixin,
    IDMixin,
    UUIDMixin,
    SoftDeleteMixin,
    ActiveMixin,
    MetadataMixin,
    DescriptionMixin,
    
    # Основные модели
    User,
    DownloadBatch,
    DownloadTask,
    RequiredChannel,
    AdminUser,
    BroadcastMessage,
    Payment,
    AnalyticsEvent,
    DailyStats,
    
    # Константы и енумы
    DownloadStatus,
    UserType,
    Platform,
    FileStatus,
    AdminRole,
    AdminPermission,
    BroadcastStatus,
    BroadcastTargetType,
    PaymentStatus,
    PaymentMethod,
    SubscriptionPlan,
    Currency,
    EventType,
    
    # Утилитарные функции
    get_model_fields,
    model_to_dict_safe,
    bulk_create_or_update,
    track_user_event,
    track_download_event,
    track_payment_event,
    get_models_in_dependency_order,
    get_model_by_table_name,
    
    # Метаданные
    TABLES,
    TABLE_DEPENDENCIES,
    MODEL_VERSION,
    SCHEMA_VERSION,
)

# Схемы данных (Pydantic)
from .schemas import (
    # Базовые схемы
    BaseSchema,
    ResponseSchema,
    PaginationSchema,

    # Пользовательские схемы
    UserSchema,
    UserCreateSchema,
    UserUpdateSchema,
    UserStatsSchema,
    UserPreferencesSchema,  # ПРОВЕРИТЬ ЕСТЬ ЛИ В user.py

    # Схемы загрузок - ИСПРАВИТЬ НАЗВАНИЯ
    DownloadTaskSchema,  # Вместо DownloadSchema
    DownloadBatchSchema,
    DownloadRequestSchema,  # Вместо DownloadRequestSchema если есть
    BatchRequestSchema,  # Проверить есть ли
    DownloadStatsSchema,  # Проверить есть ли
    # DownloadResponseSchema,  # ЗАКОММЕНТИРОВАТЬ ЕСЛИ НЕТ

    # Админские схемы
    AdminUserSchema,
    AdminCreateSchema,
    AdminStatsSchema,
    BroadcastSchema,

    # Аналитические схемы - ПРОВЕРИТЬ КАКИЕ ЕСТЬ
    # EventSchema,           # ЗАКОММЕНТИРОВАТЬ ЕСЛИ НЕТ
    DailyStatsSchema,
    # AnalyticsQuerySchema,  # ЗАКОММЕНТИРОВАТЬ ЕСЛИ НЕТ
    MetricsSchema,
)

# Исключения
from .exceptions import (
    # Базовые исключения
    VideoBotException,
    VideoBotValidationError,
    VideoBotConfigError,
    VideoBotDatabaseError,
    VideoBotServiceUnavailableError,
    VideoBotRateLimitError,
    VideoBotAuthenticationError,
    VideoBotAuthorizationError,
    VideoBotNotFoundError,
    VideoBotConflictError,
    
    # Пользовательские исключения
    UserException,
    UserNotFoundError,
    UserBannedError,
    UserLimitExceededError,
    UserTrialExpiredError,
    UserPremiumRequiredError,
    UserSubscriptionRequiredError,
    UserValidationError,
    UserAlreadyExistsError,
    
    # Исключения загрузок
    DownloadException,
    InvalidURLError,
    UnsupportedPlatformError,
    VideoNotFoundError,
    DownloadFailedError,
    BatchProcessingError,
    QualityNotAvailableError,
    DownloadTimeoutError,
    FileSizeExceededError,
    DownloadWorkerError,
    
    # Исключения хранилища
    StorageException,
    FileNotFoundError,
    StorageQuotaExceededError,
    FileUploadError,
    CDNError,
    FileExpiredError,
    StorageServiceUnavailableError,
    
    # Утилиты исключений
    get_exception_category,
    is_user_error,
    is_system_error,
    should_retry,
    get_user_friendly_message,
    create_error_context,
    handle_exceptions,
    ExceptionFactory,
    exceptions,
    format_exception_for_user,
    format_exception_for_admin,
    ErrorCodes,
    EXCEPTION_CATEGORIES,
)

# Утилиты
from .utils import (
    # Безопасность
    generate_password_hash,
    check_password,
    generate_secure_token,
    verify_token,
    encrypt_data,
    decrypt_data,
    
    # Валидаторы
    validate_email,
    validate_phone,
    validate_url,
    validate_telegram_username,
    validate_file_size,
    sanitize_filename,
    
    # Помощники
    format_file_size,
    format_duration,
    format_currency,
    generate_unique_id,
    safe_int,
    safe_float,
    truncate_string,
    
    # Rate limiting
    RateLimiter,
    MemoryRateLimiter,
    RedisRateLimiter,
    
    # Шифрование
    AESCipher,
    hash_password,
    verify_password_hash,
)

# Сервисы
from .services import (
    # База данных
    DatabaseService,
    
    # Redis
    RedisService,
    init_redis,
    close_redis,
    
    # Аутентификация
    AuthService,
    JWTManager,
    
    # Аналитика
    AnalyticsService,
)

# Константы и конфигурация
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
SUPPORTED_PLATFORMS = ['youtube', 'tiktok', 'instagram']
SUPPORTED_FORMATS = ['mp4', 'webm', 'mp3']
SUPPORTED_QUALITIES = ['480p', '720p', '1080p', '1440p', '2160p']

# Мапинги для удобства использования
USER_TYPES = {
    'free': UserType.FREE,
    'trial': UserType.TRIAL,
    'premium': UserType.PREMIUM,
    'admin': UserType.ADMIN,
}

DOWNLOAD_STATUSES = {
    'pending': DownloadStatus.PENDING,
    'processing': DownloadStatus.PROCESSING,
    'completed': DownloadStatus.COMPLETED,
    'failed': DownloadStatus.FAILED,
    'cancelled': DownloadStatus.CANCELLED,
}

PLATFORMS = {
    'youtube': Platform.YOUTUBE,
    'tiktok': Platform.TIKTOK,
    'instagram': Platform.INSTAGRAM,
}

# Утилитарные функции для всего пакета

async def initialize_shared_components():
    """
    Инициализация всех компонентов shared пакета
    
    Вызывается при запуске любого сервиса
    """
    try:
        # Инициализация базы данных
        await init_database()
        
        # Инициализация Redis (если доступен)
        try:
            from .services.redis import init_redis
            await init_redis()
        except ImportError:
            pass  # Redis не обязателен
        
        # Проверка конфигурации
        if not settings.BOT_TOKEN:
            raise VideoBotConfigError("BOT_TOKEN is required")
        
        print(f"✅ Shared components v{__version__} initialized successfully")
        
    except Exception as e:
        print(f"❌ Failed to initialize shared components: {e}")
        raise VideoBotConfigError(f"Initialization failed: {e}")

async def cleanup_shared_components():
    """
    Очистка ресурсов shared пакета
    
    Вызывается при завершении работы сервиса
    """
    try:
        # Закрытие подключений к базе данных
        await close_database()
        
        # Закрытие Redis подключений
        try:
            from .services.redis import close_redis
            await close_redis()
        except ImportError:
            pass
        
        print(f"✅ Shared components cleanup completed")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")

def get_shared_info() -> dict:
    """Получить информацию о shared пакете"""
    return {
        'version': __version__,
        'author': __author__,
        'description': __description__,
        'models_count': len(TABLES),
        'tables': TABLES,
        'supported_platforms': SUPPORTED_PLATFORMS,
        'supported_formats': SUPPORTED_FORMATS,
        'supported_qualities': SUPPORTED_QUALITIES,
    }

def validate_shared_config() -> list:
    """
    Валидация конфигурации shared компонентов
    
    Returns:
        Список ошибок (пустой если все ОК)
    """
    errors = []
    
    # Проверяем обязательные настройки
    required_settings = [
        'DATABASE_URL', 
        'BOT_TOKEN'
    ]
    
    for setting in required_settings:
        if not hasattr(settings, setting) or not getattr(settings, setting):
            errors.append(f"Missing required setting: {setting}")
    
    # Проверяем форматы настроек
    if settings.DATABASE_POOL_SIZE <= 0:
        errors.append("DATABASE_POOL_SIZE must be positive")
    
    if settings.FREE_DAILY_LIMIT <= 0:
        errors.append("FREE_DAILY_LIMIT must be positive")
    
    if not settings.ADMIN_IDS:
        errors.append("At least one ADMIN_ID is required")
    
    return errors

# Декораторы для shared функциональности

def with_database_session(func):
    """
    Декоратор для автоматического управления сессией БД
    """
    async def wrapper(*args, **kwargs):
        async with get_async_session() as session:
            return await func(session, *args, **kwargs)
    return wrapper

def with_exception_handling(default_return=None):
    """
    Декоратор для стандартной обработки исключений
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except VideoBotException:
                raise  # Пробрасываем наши исключения
            except Exception as e:
                # Логируем и превращаем в VideoBotException
                import logging
                logger = logging.getLogger(func.__module__)
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                raise VideoBotException(
                    f"Internal error in {func.__name__}",
                    original_exception=e
                )
        return wrapper
    return decorator

# Контекстные менеджеры

class DatabaseTransaction:
    """Контекстный менеджер для транзакций БД"""
    
    def __init__(self, session=None):
        self.session = session
        self.should_close = session is None
    
    async def __aenter__(self):
        if self.should_close:
            self.session = await get_async_session().__aenter__()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        else:
            await self.session.commit()
        
        if self.should_close:
            await self.session.close()

# Экспорт всех компонентов
__all__ = [
    # Метаинформация
    '__version__',
    '__author__',
    '__description__',

    # Конфигурация
    'settings',
    'get_settings',
    'init_database',
    'close_database',
    'get_async_session',
    'get_sync_session',
    'DatabaseConfig',
    'DatabaseHealthCheck',
    'DatabaseMaintenance',

    # Модели
    'Base', 'BaseModel', 'BaseModelWithSoftDelete', 'BaseModelWithUUID',
    'BaseActiveModel', 'BaseFullModel',
    'TimestampMixin', 'IDMixin', 'UUIDMixin', 'SoftDeleteMixin',
    'ActiveMixin', 'MetadataMixin', 'DescriptionMixin',
    'User', 'DownloadBatch', 'DownloadTask', 'RequiredChannel',
    'AdminUser', 'BroadcastMessage', 'Payment', 'AnalyticsEvent', 'DailyStats',

    # Константы
    'DownloadStatus', 'UserType', 'Platform', 'FileStatus',
    'AdminRole', 'AdminPermission', 'BroadcastStatus', 'BroadcastTargetType',
    'PaymentStatus', 'PaymentMethod', 'SubscriptionPlan', 'Currency', 'EventType',
    'TABLES', 'TABLE_DEPENDENCIES', 'MODEL_VERSION', 'SCHEMA_VERSION',

    # Схемы - ТОЛЬКО СУЩЕСТВУЮЩИЕ
    'BaseSchema', 'ResponseSchema', 'PaginationSchema',
    'UserSchema', 'UserCreateSchema', 'UserUpdateSchema', 'UserStatsSchema',
    'DownloadTaskSchema', 'DownloadBatchSchema',  # ИСПРАВЛЕНО
    'DownloadRequestSchema',  # Если есть
    'AdminUserSchema', 'AdminCreateSchema', 'AdminStatsSchema', 'BroadcastSchema',
    'DailyStatsSchema',

    # Исключения
    'VideoBotException', 'VideoBotValidationError', 'VideoBotConfigError',
    'VideoBotDatabaseError', 'VideoBotServiceUnavailableError',
    'VideoBotRateLimitError', 'VideoBotAuthenticationError',
    'VideoBotAuthorizationError', 'VideoBotNotFoundError', 'VideoBotConflictError',
    'UserException', 'UserNotFoundError', 'UserBannedError', 'UserLimitExceededError',
    'UserTrialExpiredError', 'UserPremiumRequiredError', 'UserSubscriptionRequiredError',
    'UserValidationError', 'UserAlreadyExistsError',
    'DownloadException', 'InvalidURLError', 'UnsupportedPlatformError',
    'VideoNotFoundError', 'DownloadFailedError', 'BatchProcessingError',
    'QualityNotAvailableError', 'DownloadTimeoutError', 'FileSizeExceededError',
    'DownloadWorkerError',
    'StorageException', 'FileNotFoundError', 'StorageQuotaExceededError',
    'FileUploadError', 'CDNError', 'FileExpiredError', 'StorageServiceUnavailableError',

    # Утилиты исключений
    'get_exception_category', 'is_user_error', 'is_system_error', 'should_retry',
    'get_user_friendly_message', 'create_error_context', 'handle_exceptions',
    'ExceptionFactory', 'exceptions', 'format_exception_for_user',
    'format_exception_for_admin', 'ErrorCodes', 'EXCEPTION_CATEGORIES',

    # Утилиты
    'generate_password_hash', 'check_password', 'generate_secure_token',
    'verify_token', 'encrypt_data', 'decrypt_data',
    'validate_email', 'validate_phone', 'validate_url',
    'validate_telegram_username', 'validate_file_size', 'sanitize_filename',
    'format_file_size', 'format_duration', 'format_currency',
    'generate_unique_id', 'safe_int', 'safe_float', 'truncate_string',
    'RateLimiter', 'MemoryRateLimiter', 'RedisRateLimiter',
    'AESCipher', 'hash_password', 'verify_password_hash',

    # Сервисы
    'DatabaseService', 'RedisService', 'init_redis', 'close_redis',
    'AuthService', 'JWTManager', 'AnalyticsService',

    # Константы
    'DEFAULT_PAGE_SIZE', 'MAX_PAGE_SIZE', 'SUPPORTED_PLATFORMS',
    'SUPPORTED_FORMATS', 'SUPPORTED_QUALITIES',
    'USER_TYPES', 'DOWNLOAD_STATUSES', 'PLATFORMS',

    # Функции управления
    'initialize_shared_components', 'cleanup_shared_components',
    'get_shared_info', 'validate_shared_config',

    # Декораторы
    'with_database_session', 'with_exception_handling',

    # Контекстные менеджеры
    'DatabaseTransaction',

    # Утилиты моделей
    'get_model_fields', 'model_to_dict_safe', 'bulk_create_or_update',
    'track_user_event', 'track_download_event', 'track_payment_event',
    'get_models_in_dependency_order', 'get_model_by_table_name',
]

# Информация о компонентах для отладки
SHARED_COMPONENTS_INFO = {
    'config': 'Database configuration and settings management',
    'models': 'SQLAlchemy ORM models and database schema',
    'schemas': 'Pydantic schemas for data validation',
    'exceptions': 'Custom exception hierarchy for error handling',
    'utils': 'Utility functions for common operations',
    'services': 'Core business logic services',
}

# Проверка целостности при импорте
try:
    validation_errors = validate_shared_config()
    if validation_errors:
        import warnings
        for error in validation_errors:
            warnings.warn(f"Shared config validation: {error}", UserWarning)
except Exception as e:
    import warnings
    warnings.warn(f"Failed to validate shared config: {e}", ImportWarning)

print(f"🚀 VideoBot Pro Shared Package v{__version__} loaded")
print(f"📊 Components: {', '.join(SHARED_COMPONENTS_INFO.keys())}")
print(f"🗄️  Database tables: {len(TABLES)}")
print(f"🎯 Platforms: {', '.join(SUPPORTED_PLATFORMS)}")