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
    "get_models_in_dependency_order",
    "get_model_by_table_name"
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

def get_models_in_dependency_order():
    """Возвращает модели в порядке зависимостей для миграций"""
    return [
        User,
        AdminUser,
        RequiredChannel,
        DownloadBatch,
        DownloadTask,
        BroadcastMessage,
        Payment,
        AnalyticsEvent,
        DailyStats,
    ]

def get_model_by_table_name(table_name: str):
    """Получить модель по имени таблицы"""
    models_map = {
        'users': User,
        'admin_users': AdminUser,
        'required_channels': RequiredChannel,
        'download_batches': DownloadBatch,
        'download_tasks': DownloadTask,
        'broadcast_messages': BroadcastMessage,
        'payments': Payment,
        'analytics_events': AnalyticsEvent,
        'daily_stats': DailyStats,
    }
    return models_map.get(table_name)

# Метаданные
MODEL_VERSION = "2.1.0"
SCHEMA_VERSION = "1.0.0"

# Зависимости таблиц для миграций
TABLE_DEPENDENCIES = {
    'users': [],
    'admin_users': [],
    'required_channels': [],
    'download_batches': ['users'],
    'download_tasks': ['users', 'download_batches'],
    'broadcast_messages': ['admin_users'],
    'payments': ['users'],
    'analytics_events': ['users', 'admin_users'],
    'daily_stats': [],
}
