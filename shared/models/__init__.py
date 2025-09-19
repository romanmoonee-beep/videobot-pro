"""
VideoBot Pro - Models Package
Централизованный импорт всех моделей базы данных
"""

# Базовые классы и константы (импортируем первыми)
from .base import (
    Base,
    BaseModel,
    BaseModelWithSoftDelete,
    BaseModelWithUUID,
    BaseActiveModel,
    BaseFullModel,
    TimestampMixin,
    IDMixin,
    UUIDMixin,
    SoftDeleteMixin,
    ActiveMixin,
    MetadataMixin,
    DescriptionMixin,
    # Константы
    DownloadStatus,
    UserType,
    Platform,
    FileStatus,
    # Утилиты
    get_model_fields,
    model_to_dict_safe,
    bulk_create_or_update,
)

# Основные модели (импортируем в правильном порядке зависимостей)
from .user import User
from .admin_user import AdminUser, AdminRole, AdminPermission
from .required_channel import RequiredChannel
from .download_batch import DownloadBatch
from .download_task import DownloadTask
from .broadcast_message import (
    BroadcastMessage,
    BroadcastStatus, 
    BroadcastTargetType,
)
from .payment import (
    Payment,
    PaymentStatus,
    PaymentMethod,
    SubscriptionPlan,
    Currency,
)
from .analytics import (
    AnalyticsEvent,
    DailyStats,
    EventType,
    # Утилиты аналитики
    track_user_event,
    track_download_event,
    track_payment_event,
)

# Все модели для алхимии и миграций
__all__ = [
    # Базовые классы
    "Base",
    "BaseModel", 
    "BaseModelWithSoftDelete",
    "BaseModelWithUUID",
    "BaseActiveModel",
    "BaseFullModel",
    
    # Миксины
    "TimestampMixin",
    "IDMixin", 
    "UUIDMixin",
    "SoftDeleteMixin",
    "ActiveMixin",
    "MetadataMixin",
    "DescriptionMixin",
    
    # Основные модели
    "User",
    "DownloadBatch",
    "DownloadTask",
    "RequiredChannel", 
    "AdminUser",
    "BroadcastMessage",
    "Payment",
    "AnalyticsEvent",
    "DailyStats",
    
    # Константы и енумы
    "DownloadStatus",
    "UserType",
    "Platform",
    "FileStatus",
    "AdminRole",
    "AdminPermission",
    "BroadcastStatus",
    "BroadcastTargetType", 
    "PaymentStatus",
    "PaymentMethod",
    "SubscriptionPlan",
    "Currency",
    "EventType",
    
    # Утилитарные функции
    "get_model_fields",
    "model_to_dict_safe",
    "bulk_create_or_update",
    "track_user_event",
    "track_download_event",
    "track_payment_event",
]

# Список всех таблиц для миграций
TABLES = [
    "users",
    "admin_users", 
    "required_channels",
    "download_batches",
    "download_tasks",
    "broadcast_messages",
    "payments",
    "analytics_events",
    "daily_stats",
]