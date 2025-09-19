"""
VideoBot Pro - Schemas Package
Pydantic схемы для валидации данных
"""

from .user import (
    UserSchema,
    UserCreateSchema,
    UserUpdateSchema,
    UserStatsSchema,
    UserPreferencesSchema
)
from .download import (
    DownloadTaskSchema,
    DownloadBatchSchema,
    DownloadRequestSchema,
    BatchRequestSchema,
    DownloadStatsSchema
)
from .admin import (
    AdminUserSchema,
    AdminCreateSchema,
    AdminUpdateSchema,
    BroadcastSchema,
    AdminStatsSchema
)
from .analytics import (
    EventSchema,
    DailyStatsSchema,
    AnalyticsQuerySchema,
    MetricsSchema
)

__all__ = [
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