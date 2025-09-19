"""
VideoBot Pro - Download Schemas
Pydantic схемы для загрузок
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator, HttpUrl

from .base import BaseSchema, TimestampSchema, IDSchema
from .common import PlatformEnum, QualityEnum, StatusEnum

class DownloadRequestSchema(BaseModel):
    """Схема запроса на скачивание"""
    url: str = Field(description="URL видео для скачивания")
    quality: Optional[str] = Field(default=None, description="Качество видео")
    format: Optional[str] = Field(default="mp4", description="Формат файла")
    send_to_chat: bool = Field(default=True, description="Отправлять в чат")
    
    @validator('url')
    def validate_url(cls, v):
        # Простая проверка URL
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v.strip()
    
    @validator('quality')
    def validate_quality(cls, v):
        if v and v not in ['auto', '480p', '720p', '1080p', '2160p', '4K']:
            raise ValueError('Invalid quality option')
        return v
    
    @validator('format')
    def validate_format(cls, v):
        if v not in ['mp4', 'webm', 'mkv', 'avi']:
            raise ValueError('Invalid format option')
        return v

class BatchRequestSchema(BaseModel):
    """Схема запроса на групповое скачивание"""
    urls: List[str] = Field(description="Список URL для скачивания")
    quality: Optional[str] = Field(default=None, description="Качество видео")
    format: Optional[str] = Field(default="mp4", description="Формат файла")
    delivery_method: str = Field(default="auto", description="Способ доставки")
    create_archive: bool = Field(default=False, description="Создавать архив")
    selected_indices: Optional[List[int]] = Field(default=None, description="Выбранные индексы")
    
    @validator('urls')
    def validate_urls(cls, v):
        if not v:
            raise ValueError('URLs list cannot be empty')
        if len(v) > 50:  # Ограничиваем максимум
            raise ValueError('Too many URLs (max 50)')
        
        # Проверяем каждый URL
        for url in v:
            if not url.startswith(('http://', 'https://')):
                raise ValueError(f'Invalid URL: {url}')
        return v
    
    @validator('delivery_method')
    def validate_delivery_method(cls, v):
        allowed = ['auto', 'individual', 'archive', 'selective']
        if v not in allowed:
            raise ValueError(f'Delivery method must be one of: {allowed}')
        return v

class DownloadTaskSchema(BaseModel):
    """Схема задачи скачивания"""
    id: int = Field(description="ID задачи")
    task_id: str = Field(description="Уникальный ID задачи")
    original_url: str = Field(description="Оригинальный URL")
    platform: str = Field(description="Платформа")
    status: str = Field(description="Статус задачи")
    progress_percent: int = Field(description="Прогресс в процентах")
    
    # Информация о видео
    video_title: Optional[str] = Field(description="Заголовок видео")
    video_author: Optional[str] = Field(description="Автор видео")
    video_duration_seconds: Optional[int] = Field(description="Длительность в секундах")
    video_views: Optional[int] = Field(description="Количество просмотров")
    
    # Параметры скачивания
    requested_quality: Optional[str] = Field(description="Запрошенное качество")
    actual_quality: Optional[str] = Field(description="Фактическое качество")
    
    # Информация о файле
    file_name: Optional[str] = Field(description="Имя файла")
    file_size_bytes: Optional[int] = Field(description="Размер файла в байтах")
    file_format: Optional[str] = Field(description="Формат файла")
    
    # CDN и доставка
    cdn_url: Optional[str] = Field(description="CDN URL")
    direct_download_url: Optional[str] = Field(description="Прямая ссылка")
    thumbnail_url: Optional[str] = Field(description="URL превью")
    expires_at: Optional[datetime] = Field(description="Срок истечения")
    
    # Ошибки
    error_message: Optional[str] = Field(description="Сообщение об ошибке")
    retry_count: int = Field(description="Количество попыток")
    
    # Временные метки
    created_at: datetime = Field(description="Время создания")
    started_at: Optional[datetime] = Field(description="Время начала")
    completed_at: Optional[datetime] = Field(description="Время завершения")
    
    class Config:
        from_attributes = True

class DownloadBatchSchema(BaseModel):
    """Схема группового скачивания"""
    id: int = Field(description="ID batch'а")
    batch_id: str = Field(description="Уникальный ID batch'а")
    total_urls: int = Field(description="Общее количество URL")
    status: str = Field(description="Статус batch'а")
    
    # Прогресс
    completed_count: int = Field(description="Количество завершенных")
    failed_count: int = Field(description="Количество неудачных")
    skipped_count: int = Field(description="Количество пропущенных")
    progress_percent: float = Field(description="Прогресс в процентах")
    
    # Настройки доставки
    delivery_method: str = Field(description="Способ доставки")
    send_to_chat: bool = Field(description="Отправлять в чат")
    create_archive: bool = Field(description="Создавать архив")
    
    # Результаты
    total_size_mb: float = Field(description="Общий размер в МБ")
    archive_url: Optional[str] = Field(description="URL архива")
    archive_size_mb: Optional[float] = Field(description="Размер архива в МБ")
    
    # Статистика платформ
    platform_stats: Optional[Dict[str, int]] = Field(description="Статистика по платформам")
    
    # Временные метки
    created_at: datetime = Field(description="Время создания")
    started_at: Optional[datetime] = Field(description="Время начала")
    completed_at: Optional[datetime] = Field(description="Время завершения")
    expires_at: Optional[datetime] = Field(description="Срок истечения")
    
    # Оценочное время
    estimated_completion_time: Optional[datetime] = Field(description="Расчетное время завершения")
    processing_time_seconds: Optional[int] = Field(description="Время обработки")
    
    class Config:
        from_attributes = True

class BatchStatusSchema(BaseModel):
    """Схема статуса batch'а"""
    batch_id: str = Field(description="ID batch'а")
    status: str = Field(description="Статус")
    progress_percent: float = Field(description="Прогресс")
    completed_tasks: int = Field(description="Завершенных задач")
    failed_tasks: int = Field(description="Неудачных задач")
    total_tasks: int = Field(description="Всего задач")
    estimated_completion: Optional[datetime] = Field(description="Расчетное завершение")

class DownloadStatsSchema(BaseModel):
    """Схема статистики скачиваний"""
    total_downloads: int = Field(description="Всего скачиваний")
    successful_downloads: int = Field(description="Успешных скачиваний")
    failed_downloads: int = Field(description="Неудачных скачиваний")
    success_rate: float = Field(description="Процент успеха")
    
    # Статистика по платформам
    youtube_downloads: int = Field(description="YouTube скачиваний")
    tiktok_downloads: int = Field(description="TikTok скачиваний")
    instagram_downloads: int = Field(description="Instagram скачиваний")
    
    # Размеры файлов
    total_file_size_gb: float = Field(description="Общий размер в ГБ")
    avg_file_size_mb: float = Field(description="Средний размер файла в МБ")
    
    # Время обработки
    avg_processing_time_seconds: float = Field(description="Среднее время обработки")
    total_processing_time_hours: float = Field(description="Общее время обработки в часах")
    
    # Качество
    quality_distribution: Dict[str, int] = Field(description="Распределение по качеству")
    format_distribution: Dict[str, int] = Field(description="Распределение по форматам")
    
    # Временная статистика
    downloads_today: int = Field(description="Скачиваний сегодня")
    downloads_this_week: int = Field(description="Скачиваний на этой неделе")
    downloads_this_month: int = Field(description="Скачиваний в этом месяце")

class DownloadHistorySchema(BaseModel):
    """Схема истории скачиваний"""
    tasks: List[DownloadTaskSchema]
    total: int = Field(description="Общее количество")
    page: int = Field(description="Номер страницы")
    pages: int = Field(description="Всего страниц")
    per_page: int = Field(description="Задач на странице")

class DownloadQuerySchema(BaseModel):
    """Схема запроса истории скачиваний"""
    user_id: Optional[int] = Field(default=None, description="ID пользователя")
    status: Optional[str] = Field(default=None, description="Статус задач")
    platform: Optional[str] = Field(default=None, description="Платформа")
    date_from: Optional[datetime] = Field(default=None, description="Начальная дата")
    date_to: Optional[datetime] = Field(default=None, description="Конечная дата")
    page: int = Field(default=1, ge=1, description="Номер страницы")
    per_page: int = Field(default=20, ge=1, le=100, description="Элементов на странице")
    sort_by: str = Field(default="created_at", description="Поле сортировки")
    sort_order: str = Field(default="desc", description="Порядок сортировки")
    
    @validator('status')
    def validate_status(cls, v):
        if v and v not in ['pending', 'processing', 'completed', 'failed', 'cancelled']:
            raise ValueError('Invalid status')
        return v
    
    @validator('platform')
    def validate_platform(cls, v):
        if v and v not in ['youtube', 'tiktok', 'instagram']:
            raise ValueError('Invalid platform')
        return v
    
    @validator('sort_by')
    def validate_sort_by(cls, v):
        allowed = ['created_at', 'completed_at', 'file_size_bytes', 'video_duration_seconds']
        if v not in allowed:
            raise ValueError(f'Sort field must be one of: {allowed}')
        return v
    
    @validator('sort_order')
    def validate_sort_order(cls, v):
        if v not in ['asc', 'desc']:
            raise ValueError('Sort order must be asc or desc')
        return v

class TaskRetrySchema(BaseModel):
    """Схема для повтора задачи"""
    task_id: int = Field(description="ID задачи для повтора")
    new_quality: Optional[str] = Field(default=None, description="Новое качество")
    new_format: Optional[str] = Field(default=None, description="Новый формат")

class BatchRetrySchema(BaseModel):
    """Схема для повтора batch'а"""
    batch_id: int = Field(description="ID batch'а для повтора")
    retry_failed_only: bool = Field(default=True, description="Повторять только неудачные")
    new_quality: Optional[str] = Field(default=None, description="Новое качество")

class PlatformStatsSchema(BaseModel):
    """Схема статистики по платформам"""
    platform: str = Field(description="Платформа")
    total_downloads: int = Field(description="Всего скачиваний")
    successful_downloads: int = Field(description="Успешных скачиваний")
    failed_downloads: int = Field(description="Неудачных скачиваний")
    success_rate: float = Field(description="Процент успеха")
    avg_file_size_mb: float = Field(description="Средний размер файла")
    total_size_gb: float = Field(description="Общий размер в ГБ")
    avg_processing_time: float = Field(description="Среднее время обработки")
    most_popular_quality: str = Field(description="Самое популярное качество")

class QualityStatsSchema(BaseModel):
    """Схема статистики по качеству"""
    quality: str = Field(description="Качество")
    download_count: int = Field(description="Количество скачиваний")
    avg_file_size_mb: float = Field(description="Средний размер файла")
    total_size_gb: float = Field(description="Общий размер в ГБ")
    percentage: float = Field(description="Процент от общего числа")

class ErrorStatsSchema(BaseModel):
    """Схема статистики ошибок"""
    error_type: str = Field(description="Тип ошибки")
    count: int = Field(description="Количество")
    percentage: float = Field(description="Процент от общего числа")
    platforms_affected: List[str] = Field(description="Затронутые платформы")
    last_occurrence: datetime = Field(description="Последнее появление")

class DownloadAnalyticsSchema(BaseModel):
    """Схема аналитики скачиваний"""
    overview: DownloadStatsSchema
    platform_stats: List[PlatformStatsSchema]
    quality_stats: List[QualityStatsSchema]
    error_stats: List[ErrorStatsSchema]
    hourly_distribution: Dict[int, int] = Field(description="Распределение по часам")
    daily_trend: List[Dict[str, Any]] = Field(description="Тренд по дням")
    user_type_distribution: Dict[str, int] = Field(description="Распределение по типам пользователей")