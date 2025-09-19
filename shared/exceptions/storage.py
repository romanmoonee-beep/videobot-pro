"""
VideoBot Pro - Storage Exceptions
Исключения связанные с хранением файлов
"""

from .base import VideoBotException


class StorageException(VideoBotException):
    """Базовое исключение для хранилища"""
    pass


class FileNotFoundError(StorageException):
    """Файл не найден в хранилище"""
    
    def __init__(self, file_path: str, storage_type: str = None):
        message = f"File not found: {file_path}"
        if storage_type:
            message += f" in {storage_type}"
        
        super().__init__(
            message,
            user_message="Файл не найден.",
            error_code="FILE_NOT_FOUND"
        )
        self.file_path = file_path
        self.storage_type = storage_type


class StorageQuotaExceededError(StorageException):
    """Превышена квота хранилища"""
    
    def __init__(self, used_space_gb: float, quota_gb: float, storage_type: str = None):
        message = f"Storage quota exceeded: {used_space_gb}GB / {quota_gb}GB"
        user_message = "Превышена квота хранилища. Обратитесь к администратору."
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="STORAGE_QUOTA_EXCEEDED"
        )
        self.used_space_gb = used_space_gb
        self.quota_gb = quota_gb
        self.storage_type = storage_type


class FileUploadError(StorageException):
    """Ошибка загрузки файла в хранилище"""
    
    def __init__(self, file_path: str, reason: str, storage_type: str = None):
        message = f"File upload failed: {file_path} - {reason}"
        user_message = f"Ошибка загрузки файла: {reason}"
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="FILE_UPLOAD_ERROR"
        )
        self.file_path = file_path
        self.reason = reason
        self.storage_type = storage_type


class CDNError(StorageException):
    """Ошибка CDN"""
    
    def __init__(self, url: str, reason: str, status_code: int = None):
        message = f"CDN error for {url}: {reason}"
        user_message = "Ошибка доступа к файлу. Попробуйте позже."
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="CDN_ERROR"
        )
        self.url = url
        self.reason = reason
        self.status_code = status_code


class FileExpiredError(StorageException):
    """Срок файла истек"""
    
    def __init__(self, file_path: str, expired_at: str):
        message = f"File expired: {file_path} at {expired_at}"
        user_message = "Срок доступности файла истек."
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="FILE_EXPIRED"
        )
        self.file_path = file_path
        self.expired_at = expired_at


class StorageServiceUnavailableError(StorageException):
    """Сервис хранилища недоступен"""
    
    def __init__(self, storage_type: str, reason: str = None):
        message = f"Storage service unavailable: {storage_type}"
        if reason:
            message += f" - {reason}"
        
        super().__init__(
            message,
            user_message="Сервис хранения временно недоступен. Попробуйте позже.",
            error_code="STORAGE_SERVICE_UNAVAILABLE"
        )
        self.storage_type = storage_type
        self.reason = reason