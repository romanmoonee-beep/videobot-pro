"""
VideoBot Pro - Base Exceptions
Базовые классы исключений для всего проекта
"""

import traceback
from typing import Optional, Dict, Any, List
from datetime import datetime


class VideoBotException(Exception):
    """
    Базовое исключение VideoBot Pro
    
    Все исключения проекта должны наследоваться от этого класса
    """

    def __init__(
            self,
            message: str,
            error_code: str = None,
            details: Dict[str, Any] = None,
            user_message: str = None,
            original_exception: Exception = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.details = details or {}
        self.user_message = user_message or message
        self.original_exception = original_exception
        self.timestamp = datetime.utcnow()
        self.traceback_str = traceback.format_exc() if original_exception else None
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"
    
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message='{self.message}', "
            f"error_code='{self.error_code}', "
            f"details={self.details}"
            f")"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертировать исключение в словарь"""
        return {
            'error_type': self.__class__.__name__,
            'error_code': self.error_code,
            'message': self.message,
            'user_message': self.user_message,
            'details': self.details,
            'timestamp': self.timestamp.isoformat(),
            'traceback': self.traceback_str
        }
    
    def get_user_friendly_message(self) -> str:
        """Получить сообщение, подходящее для показа пользователю"""
        return self.user_message
    
    def add_detail(self, key: str, value: Any):
        """Добавить деталь к исключению"""
        self.details[key] = value
        return self
    
    def with_context(self, **kwargs) -> 'VideoBotException':
        """Добавить контекст к исключению"""
        self.details.update(kwargs)
        return self


class VideoBotValidationError(VideoBotException):
    """Ошибка валидации данных"""
    
    def __init__(
        self,
        message: str,
        field: str = None,
        value: Any = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        if field:
            self.add_detail('field', field)
        if value is not None:
            self.add_detail('value', value)


class VideoBotConfigError(VideoBotException):
    """Ошибка конфигурации системы"""
    
    def __init__(self, message: str, config_key: str = None, **kwargs):
        super().__init__(
            message,
            user_message="Ошибка конфигурации системы. Обратитесь к администратору.",
            **kwargs
        )
        if config_key:
            self.add_detail('config_key', config_key)


class VideoBotDatabaseError(VideoBotException):
    """Ошибка базы данных"""
    
    def __init__(
        self,
        message: str,
        query: str = None,
        table: str = None,
        **kwargs
    ):
        super().__init__(
            message,
            user_message="Временная ошибка базы данных. Попробуйте позже.",
            **kwargs
        )
        if query:
            self.add_detail('query', query)
        if table:
            self.add_detail('table', table)


class VideoBotServiceUnavailableError(VideoBotException):
    """Сервис временно недоступен"""
    
    def __init__(
        self,
        message: str,
        service_name: str = None,
        retry_after: int = None,
        **kwargs
    ):
        super().__init__(
            message,
            user_message="Сервис временно недоступен. Попробуйте позже.",
            **kwargs
        )
        if service_name:
            self.add_detail('service_name', service_name)
        if retry_after:
            self.add_detail('retry_after', retry_after)


class VideoBotRateLimitError(VideoBotException):
    """Превышен лимит запросов"""
    
    def __init__(
        self,
        message: str,
        limit: int = None,
        reset_time: datetime = None,
        **kwargs
    ):
        super().__init__(
            message,
            user_message="Слишком много запросов. Подождите немного.",
            **kwargs
        )
        if limit:
            self.add_detail('limit', limit)
        if reset_time:
            self.add_detail('reset_time', reset_time.isoformat())


class VideoBotAuthenticationError(VideoBotException):
    """Ошибка аутентификации"""
    
    def __init__(self, message: str = "Authentication required", **kwargs):
        super().__init__(
            message,
            user_message="Требуется авторизация.",
            **kwargs
        )


class VideoBotAuthorizationError(VideoBotException):
    """Ошибка авторизации (недостаточно прав)"""
    
    def __init__(self, message: str = "Insufficient permissions", **kwargs):
        super().__init__(
            message,
            user_message="Недостаточно прав для выполнения действия.",
            **kwargs
        )


class VideoBotNotFoundError(VideoBotException):
    """Ресурс не найден"""
    
    def __init__(
        self,
        message: str,
        resource_type: str = None,
        resource_id: Any = None,
        **kwargs
    ):
        super().__init__(
            message,
            user_message="Запрошенный ресурс не найден.",
            **kwargs
        )
        if resource_type:
            self.add_detail('resource_type', resource_type)
        if resource_id:
            self.add_detail('resource_id', resource_id)


class VideoBotConflictError(VideoBotException):
    """Конфликт при выполнении операции"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            user_message="Конфликт данных. Попробуйте обновить страницу.",
            **kwargs
        )