"""
VideoBot Pro - Download Exceptions
Исключения связанные с загрузками
"""

from .base import VideoBotException, VideoBotValidationError


class DownloadException(VideoBotException):
    """Базовое исключение для загрузок"""
    pass


class InvalidURLError(DownloadException, VideoBotValidationError):
    """Некорректный URL"""
    
    def __init__(self, url: str, reason: str = None):
        message = f"Invalid URL: {url}"
        if reason:
            message += f" - {reason}"
        
        super().__init__(
            message,
            field="url",
            value=url,
            user_message="Некорректная ссылка. Проверьте правильность URL.",
            error_code="INVALID_URL"
        )
        self.url = url


class UnsupportedPlatformError(DownloadException):
    """Неподдерживаемая платформа"""
    
    def __init__(self, platform: str, url: str = None):
        message = f"Unsupported platform: {platform}"
        user_message = f"Платформа '{platform}' не поддерживается."
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="UNSUPPORTED_PLATFORM"
        )
        self.platform = platform
        self.url = url


class VideoNotFoundError(DownloadException):
    """Видео не найдено"""
    
    def __init__(self, url: str, reason: str = None):
        message = f"Video not found: {url}"
        if reason:
            message += f" - {reason}"
        
        user_messages = {
            'private': "Видео приватное или удалено автором.",
            'deleted': "Видео было удалено.",
            'unavailable': "Видео недоступно в вашем регионе.",
            'age_restricted': "Видео имеет возрастные ограничения.",
        }
        
        user_message = user_messages.get(reason, "Видео не найдено или недоступно.")
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="VIDEO_NOT_FOUND"
        )
        self.url = url
        self.reason = reason


class DownloadFailedError(DownloadException):
    """Ошибка при загрузке"""
    
    def __init__(self, url: str, reason: str, task_id: str = None):
        message = f"Download failed for {url}: {reason}"
        
        error_messages = {
            'network_error': "Ошибка сети. Попробуйте позже.",
            'timeout': "Превышено время ожидания.",
            'file_too_large': "Файл слишком большой.",
            'format_not_available': "Нужное качество недоступно.",
            'quota_exceeded': "Превышена квота загрузок.",
            'server_error': "Ошибка сервера. Попробуйте позже.",
        }
        
        user_message = error_messages.get(reason, f"Не удалось скачать видео: {reason}")
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="DOWNLOAD_FAILED"
        )
        self.url = url
        self.reason = reason
        self.task_id = task_id


class BatchProcessingError(DownloadException):
    """Ошибка обработки batch"""
    
    def __init__(
        self,
        batch_id: str,
        reason: str,
        failed_urls: list = None,
        processed_count: int = 0
    ):
        message = f"Batch processing failed: {batch_id} - {reason}"
        user_message = f"Ошибка групповой загрузки: {reason}"
        
        if failed_urls and len(failed_urls) > 0:
            user_message += f"\nНеудачных ссылок: {len(failed_urls)}"
        if processed_count > 0:
            user_message += f"\nОбработано успешно: {processed_count}"
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="BATCH_PROCESSING_ERROR"
        )
        self.batch_id = batch_id
        self.reason = reason
        self.failed_urls = failed_urls or []
        self.processed_count = processed_count


class QualityNotAvailableError(DownloadException):
    """Запрошенное качество недоступно"""
    
    def __init__(self, requested_quality: str, available_qualities: list, url: str = None):
        message = f"Quality {requested_quality} not available. Available: {available_qualities}"
        user_message = f"Качество {requested_quality} недоступно. Доступные: {', '.join(available_qualities)}"
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="QUALITY_NOT_AVAILABLE"
        )
        self.requested_quality = requested_quality
        self.available_qualities = available_qualities
        self.url = url


class DownloadTimeoutError(DownloadException):
    """Таймаут загрузки"""
    
    def __init__(self, url: str, timeout_seconds: int, task_id: str = None):
        message = f"Download timeout after {timeout_seconds}s for {url}"
        user_message = f"Время загрузки превышено ({timeout_seconds}с). Попробуйте позже."
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="DOWNLOAD_TIMEOUT"
        )
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.task_id = task_id


class FileSizeExceededError(DownloadException):
    """Размер файла превышает лимит"""
    
    def __init__(self, file_size_mb: float, max_size_mb: float, url: str = None):
        message = f"File size {file_size_mb}MB exceeds limit {max_size_mb}MB"
        user_message = f"Размер файла ({file_size_mb:.1f}МБ) превышает лимит ({max_size_mb:.1f}МБ)."
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="FILE_SIZE_EXCEEDED"
        )
        self.file_size_mb = file_size_mb
        self.max_size_mb = max_size_mb
        self.url = url


class DownloadWorkerError(DownloadException):
    """Ошибка worker'а загрузки"""
    
    def __init__(self, worker_id: str, task_id: str, reason: str):
        message = f"Worker {worker_id} failed to process task {task_id}: {reason}"
        user_message = "Ошибка обработки задачи. Попробуйте позже."
        
        super().__init__(
            message,
            user_message=user_message,
            error_code="DOWNLOAD_WORKER_ERROR"
        )
        self.worker_id = worker_id
        self.task_id = task_id
        self.reason = reason