"""
VideoBot Pro - Schemas Package  
Pydantic схемы для валидации данных
"""

# Базовые схемы
from .base import (
    BaseSchema,
    TimestampSchema,
    IDSchema,
    ResponseSchema,
    PaginationSchema,
)

# Общие схемы
from .common import (
    StatusEnum,
    PlatformEnum,
    UserTypeEnum,
    QualityEnum,
)

# Пользовательские схемы
from .user import (
    UserSchema,
    UserCreateSchema,
    UserUpdateSchema,
    UserStatsSchema,
    UserPreferencesSchema
)

# Схемы загрузок
from .download import (
    DownloadTaskSchema,
    DownloadBatchSchema,
    DownloadRequestSchema,
    BatchRequestSchema,
    DownloadStatsSchema
)

# Админские схемы
from .admin import (
    AdminUserSchema,
    AdminCreateSchema,
    AdminUpdateSchema,
    BroadcastSchema,
    AdminStatsSchema
)

# Аналитические схемы
from .analytics import (
    EventSchema,
    DailyStatsSchema,
    AnalyticsQuerySchema,
    MetricsSchema
)

__all__ = [
    # Базовые схемы
    'BaseSchema',
    'TimestampSchema',
    'IDSchema',
    'ResponseSchema',
    'PaginationSchema',

    # Общие схемы
    'StatusEnum',
    'PlatformEnum',
    'UserTypeEnum',
    'QualityEnum',

    # User schemas
    'UserSchema',
    'UserCreateSchema',
    'UserUpdateSchema',
    'UserStatsSchema',
    'UserPreferencesSchema',

    # Download schemas
    'DownloadTaskSchema',
    'DownloadBatchSchema',
    'DownloadRequestSchema',
    'BatchRequestSchema',
    'DownloadStatsSchema',

    # Admin schemas
    'AdminUserSchema',
    'AdminCreateSchema',
    'AdminUpdateSchema',
    'BroadcastSchema',
    'AdminStatsSchema',

    # Analytics schemas
    'EventSchema',
    'DailyStatsSchema',
    'AnalyticsQuerySchema',
    'MetricsSchema'
]