"""
VideoBot Pro - Exceptions Package
Система исключений для всего проекта
"""

# Базовые исключения
from .base import (
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
)

# Пользовательские исключения
from .user import (
    UserException,
    UserNotFoundError,
    UserBannedError,
    UserLimitExceededError,
    UserTrialExpiredError,
    UserPremiumRequiredError,
    UserSubscriptionRequiredError,
    UserValidationError,
    UserAlreadyExistsError,
)

# Исключения загрузок
from .download import (
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
)

# Исключения хранилища
from .storage import (
    StorageException,
    FileNotFoundError,
    StorageQuotaExceededError,
    FileUploadError,
    CDNError,
    FileExpiredError,
    StorageServiceUnavailableError,
)

__all__ = [
    # Базовые исключения
    'VideoBotException',
    'VideoBotValidationError',
    'VideoBotConfigError',
    'VideoBotDatabaseError',
    'VideoBotServiceUnavailableError',
    'VideoBotRateLimitError',
    'VideoBotAuthenticationError',
    'VideoBotAuthorizationError',
    'VideoBotNotFoundError',
    'VideoBotConflictError',
    
    # Пользовательские исключения
    'UserException',
    'UserNotFoundError',
    'UserBannedError',
    'UserLimitExceededError',
    'UserTrialExpiredError',
    'UserPremiumRequiredError',
    'UserSubscriptionRequiredError',
    'UserValidationError',
    'UserAlreadyExistsError',
    
    # Исключения загрузок
    'DownloadException',
    'InvalidURLError',
    'UnsupportedPlatformError',
    'VideoNotFoundError',
    'DownloadFailedError',
    'BatchProcessingError',
    'QualityNotAvailableError',
    'DownloadTimeoutError',
    'FileSizeExceededError',
    'DownloadWorkerError',
    
    # Исключения хранилища
    'StorageException',
    'FileNotFoundError',
    'StorageQuotaExceededError',
    'FileUploadError',
    'CDNError',
    'FileExpiredError',
    'StorageServiceUnavailableError',
]

# Версия пакета исключений
EXCEPTIONS_VERSION = "2.1.0"

# Мапинг исключений по категориям (только с реальными файлами)
EXCEPTION_CATEGORIES = {
    'base': [
        VideoBotException, VideoBotValidationError, VideoBotConfigError,
        VideoBotDatabaseError, VideoBotServiceUnavailableError,
        VideoBotRateLimitError, VideoBotAuthenticationError,
        VideoBotAuthorizationError, VideoBotNotFoundError,
        VideoBotConflictError
    ],
    'user': [
        UserException, UserNotFoundError, UserBannedError,
        UserLimitExceededError, UserTrialExpiredError,
        UserPremiumRequiredError, UserSubscriptionRequiredError,
        UserValidationError, UserAlreadyExistsError
    ],
    'download': [
        DownloadException, InvalidURLError, UnsupportedPlatformError,
        VideoNotFoundError, DownloadFailedError, BatchProcessingError,
        QualityNotAvailableError, DownloadTimeoutError,
        FileSizeExceededError, DownloadWorkerError
    ],
    'storage': [
        StorageException, FileNotFoundError, StorageQuotaExceededError,
        FileUploadError, CDNError, FileExpiredError,
        StorageServiceUnavailableError
    ]
}

# Утилитарные функции для работы с исключениями

def get_exception_category(exception: VideoBotException) -> str:
    """Получить категорию исключения"""
    for category, exceptions in EXCEPTION_CATEGORIES.items():
        if type(exception) in exceptions:
            return category
    return 'unknown'

def is_user_error(exception: VideoBotException) -> bool:
    """Проверить, является ли исключение ошибкой пользователя"""
    user_error_types = EXCEPTION_CATEGORIES['user'] + [
        InvalidURLError, UnsupportedPlatformError, 
        VideoBotValidationError
    ]
    return type(exception) in user_error_types

def is_system_error(exception: VideoBotException) -> bool:
    """Проверить, является ли исключение системной ошибкой"""
    system_error_types = [
        VideoBotDatabaseError, VideoBotServiceUnavailableError,
        StorageServiceUnavailableError, DownloadWorkerError
    ]
    return type(exception) in system_error_types

def should_retry(exception: VideoBotException) -> bool:
    """Определить, стоит ли повторить операцию при данном исключении"""
    retryable_types = [
        VideoBotServiceUnavailableError,
        DownloadTimeoutError,
        StorageServiceUnavailableError,
        VideoBotDatabaseError,
    ]
    return type(exception) in retryable_types

def get_user_friendly_message(exception: Exception) -> str:
    """Получить дружественное сообщение для пользователя"""
    if isinstance(exception, VideoBotException):
        return exception.get_user_friendly_message()
    
    # Общие сообщения для стандартных исключений
    error_messages = {
        'ConnectionError': "Проблемы с подключением. Попробуйте позже.",
        'TimeoutError': "Превышено время ожидания. Попробуйте позже.",
        'PermissionError': "Недостаточно прав для выполнения действия.",
        'FileNotFoundError': "Файл не найден.",
        'ValueError': "Некорректное значение.",
        'KeyError': "Отсутствует обязательный параметр.",
    }
    
    exception_name = type(exception).__name__
    return error_messages.get(exception_name, "Произошла непредвиденная ошибка.")

def create_error_context(
    exception: Exception, 
    user_id: int = None,
    operation: str = None,
    additional_data: dict = None
) -> dict:
    """Создать контекст ошибки для логирования"""
    context = {
        'exception_type': type(exception).__name__,
        'message': str(exception),
        'timestamp': None,  # Будет добавлено при логировании
    }
    
    if user_id:
        context['user_id'] = user_id
    
    if operation:
        context['operation'] = operation
        
    if additional_data:
        context.update(additional_data)
    
    if isinstance(exception, VideoBotException):
        context.update({
            'error_code': exception.error_code,
            'details': exception.details,
            'user_message': exception.user_message
        })
    
    return context

# Декораторы для обработки исключений

def handle_exceptions(
    default_message: str = "Произошла ошибка",
    log_errors: bool = True,
    reraise: bool = False
):
    """
    Декоратор для автоматической обработки исключений
    
    Args:
        default_message: Сообщение по умолчанию для пользователя
        log_errors: Логировать ли ошибки
        reraise: Пробрасывать ли исключение дальше
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except VideoBotException as e:
                if log_errors:
                    import logging
                    logger = logging.getLogger(func.__module__)
                    logger.warning(f"VideoBot exception in {func.__name__}: {e}")
                
                if reraise:
                    raise
                return {'error': e.get_user_friendly_message()}
            except Exception as e:
                if log_errors:
                    import logging
                    logger = logging.getLogger(func.__module__)
                    logger.error(f"Unexpected exception in {func.__name__}: {e}", exc_info=True)
                
                if reraise:
                    raise
                return {'error': default_message}
        
        return wrapper
    return decorator

# Фабрика исключений для быстрого создания

class ExceptionFactory:
    """Фабрика для создания типовых исключений"""
    
    @staticmethod
    def user_not_found(user_id: int = None, telegram_id: int = None) -> UserNotFoundError:
        """Создать исключение 'пользователь не найден'"""
        return UserNotFoundError(user_id=user_id, telegram_id=telegram_id)
    
    @staticmethod
    def invalid_url(url: str, reason: str = None) -> InvalidURLError:
        """Создать исключение 'некорректный URL'"""
        return InvalidURLError(url=url, reason=reason)
    
    @staticmethod
    def download_failed(url: str, reason: str, task_id: str = None) -> DownloadFailedError:
        """Создать исключение 'загрузка не удалась'"""
        return DownloadFailedError(url=url, reason=reason, task_id=task_id)
    
    @staticmethod
    def file_not_found(file_path: str, storage_type: str = None) -> FileNotFoundError:
        """Создать исключение 'файл не найден'"""
        return FileNotFoundError(file_path=file_path, storage_type=storage_type)
    
    @staticmethod
    def limit_exceeded(
        limit_type: str, 
        current: int, 
        maximum: int, 
        user_id: int = None
    ) -> UserLimitExceededError:
        """Создать исключение 'лимит превышен'"""
        return UserLimitExceededError(
            limit_type=limit_type,
            current_value=current,
            max_value=maximum,
            user_id=user_id
        )

# Глобальный экземпляр фабрики
exceptions = ExceptionFactory()

# Дополнительные утилиты

def format_exception_for_user(exception: Exception) -> str:
    """Отформатировать исключение для показа пользователю"""
    message = get_user_friendly_message(exception)
    
    if isinstance(exception, VideoBotException):
        if exception.error_code:
            message += f"\n\nКод ошибки: {exception.error_code}"
    
    return message

def format_exception_for_admin(exception: Exception) -> str:
    """Отформатировать исключение для администратора"""
    if isinstance(exception, VideoBotException):
        details = []
        details.append(f"Тип: {type(exception).__name__}")
        details.append(f"Код: {exception.error_code}")
        details.append(f"Сообщение: {exception.message}")
        
        if exception.details:
            details.append(f"Детали: {exception.details}")
        
        return "\n".join(details)
    else:
        return f"{type(exception).__name__}: {str(exception)}"

# Константы для кодов ошибок
class ErrorCodes:
    """Стандартные коды ошибок"""
    
    # Пользовательские ошибки (1000-1999)
    USER_NOT_FOUND = "USER_NOT_FOUND_1001"
    USER_BANNED = "USER_BANNED_1002"
    USER_LIMIT_EXCEEDED = "USER_LIMIT_EXCEEDED_1003"
    TRIAL_EXPIRED = "TRIAL_EXPIRED_1004"
    PREMIUM_REQUIRED = "PREMIUM_REQUIRED_1005"
    SUBSCRIPTION_REQUIRED = "SUBSCRIPTION_REQUIRED_1006"
    
    # Ошибки загрузок (2000-2999)
    INVALID_URL = "INVALID_URL_2001"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM_2002"
    VIDEO_NOT_FOUND = "VIDEO_NOT_FOUND_2003"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED_2004"
    DOWNLOAD_TIMEOUT = "DOWNLOAD_TIMEOUT_2005"
    FILE_SIZE_EXCEEDED = "FILE_SIZE_EXCEEDED_2006"
    
    # Ошибки хранилища (3000-3999)
    FILE_NOT_FOUND = "FILE_NOT_FOUND_3001"
    STORAGE_QUOTA_EXCEEDED = "STORAGE_QUOTA_EXCEEDED_3002"
    FILE_UPLOAD_ERROR = "FILE_UPLOAD_ERROR_3003"
    CDN_ERROR = "CDN_ERROR_3004"
    FILE_EXPIRED = "FILE_EXPIRED_3005"
    
    # Системные ошибки (9000-9999)
    DATABASE_ERROR = "DATABASE_ERROR_9001"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE_9002"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED_9003"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR_9004"
    AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR_9005"

# Добавляем коды ошибок в __all__
__all__.extend([
    'get_exception_category',
    'is_user_error', 
    'is_system_error',
    'should_retry',
    'get_user_friendly_message',
    'create_error_context',
    'handle_exceptions',
    'ExceptionFactory',
    'exceptions',
    'format_exception_for_user',
    'format_exception_for_admin',
    'ErrorCodes',
    'EXCEPTION_CATEGORIES'
])