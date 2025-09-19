"""
VideoBot Pro - User Exceptions
Исключения связанные с пользователями
"""

from .base import VideoBotException, VideoBotValidationError, VideoBotAuthorizationError


class UserException(VideoBotException):
    """Базовое исключение для пользователей"""
    pass


class UserNotFoundError(UserException):
    """Пользователь не найден"""
    
    def __init__(self, user_id: int = None, telegram_id: int = None, username: str = None):
        if user_id:
            message = f"User with ID {user_id} not found"
            self.user_id = user_id
        elif telegram_id:
            message = f"User with Telegram ID {telegram_id} not found"
            self.telegram_id = telegram_id
        elif username:
            message = f"User with username '{username}' not found"
            self.username = username
        else:
            message = "User not found"
        
        super().__init__(
            message,
            user_message="Пользователь не найден.",
            error_code="USER_NOT_FOUND"
        )


class UserBannedError(UserException):
    """Пользователь заблокирован"""
    
    def __init__(self, user_id: int, reason: str = None, until: str = None):
        message = f"User {user_id} is banned"
        if reason:
            message += f": {reason}"
        
        user_message = "Ваш аккаунт заблокирован."
        if reason:
            user_message += f"\nПричина: {reason}"
        if until:
            user_message += f"\nБлокировка до: {until}"
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="USER_BANNED"
        )
        self.user_id = user_id
        self.reason = reason
        self.until = until


class UserLimitExceededError(UserException):
    """Превышен лимит пользователя"""
    
    def __init__(
        self,
        limit_type: str,
        current_value: int,
        max_value: int,
        user_id: int = None
    ):
        message = f"User limit exceeded: {limit_type} ({current_value}/{max_value})"
        
        limit_messages = {
            'daily_downloads': f"Превышен дневной лимит скачиваний ({current_value}/{max_value})",
            'file_size': f"Размер файла превышает лимит ({current_value}/{max_value} МБ)",
            'batch_size': f"Размер batch превышает лимит ({current_value}/{max_value})",
            'requests_per_minute': "Слишком много запросов. Подождите немного."
        }
        
        user_message = limit_messages.get(limit_type, "Превышен лимит.")
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="USER_LIMIT_EXCEEDED"
        )
        self.limit_type = limit_type
        self.current_value = current_value
        self.max_value = max_value
        self.user_id = user_id


class UserTrialExpiredError(UserException):
    """Пробный период истек"""
    
    def __init__(self, user_id: int):
        super().__init__(
            f"Trial period expired for user {user_id}",
            user_message="Пробный период истек. Оформите Premium подписку для продолжения.",
            error_code="TRIAL_EXPIRED"
        )
        self.user_id = user_id


class UserPremiumRequiredError(UserException):
    """Требуется Premium подписка"""
    
    def __init__(self, feature: str, user_id: int = None):
        super().__init__(
            f"Premium subscription required for feature: {feature}",
            user_message=f"Для использования '{feature}' требуется Premium подписка.",
            error_code="PREMIUM_REQUIRED"
        )
        self.feature = feature
        self.user_id = user_id


class UserSubscriptionRequiredError(UserException):
    """Требуется подписка на каналы"""
    
    def __init__(self, channels: list, user_id: int = None):
        message = f"Subscription to channels required: {channels}"
        channel_names = ', '.join(channels) if len(channels) <= 3 else f"{len(channels)} каналов"
        user_message = f"Подпишитесь на {channel_names} для продолжения использования бота."
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="SUBSCRIPTION_REQUIRED"
        )
        self.channels = channels
        self.user_id = user_id


class UserValidationError(UserException, VideoBotValidationError):
    """Ошибка валидации пользовательских данных"""
    
    def __init__(self, field: str, value: Any, reason: str):
        message = f"Invalid {field}: {reason}"
        user_message = f"Некорректное значение поля '{field}': {reason}"
        
        super().__init__(
            message,
            field=field,
            value=value,
            user_message=user_message,
            error_code="USER_VALIDATION_ERROR"
        )


class UserAlreadyExistsError(UserException):
    """Пользователь уже существует"""
    
    def __init__(self, identifier: str, value: Any):
        super().__init__(
            f"User already exists with {identifier}: {value}",
            user_message="Пользователь с такими данными уже существует.",
            error_code="USER_ALREADY_EXISTS"
        )
        self.identifier = identifier
        self.value = value