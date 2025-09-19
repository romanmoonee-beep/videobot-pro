"""
VideoBot Pro - Base Models
Базовые классы для всех моделей базы данных
"""

from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, func, Integer, String, Text
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSON
import uuid


class Base(DeclarativeBase):
    """Base class for all database models"""
    
    # Автоматическое именование таблиц на основе имени класса
    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + 's'


class TimestampMixin:
    """
    Mixin для автоматических временных меток
    Добавляет поля created_at и updated_at
    """
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Дата и время создания записи"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Дата и время последнего обновления записи"
    )


class IDMixin:
    """
    Mixin для первичного ключа
    Стандартный автоинкрементный ID
    """
    
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Уникальный идентификатор записи"
    )


class UUIDMixin:
    """
    Mixin для UUID первичного ключа
    Используется для распределенных систем
    """
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Уникальный идентификатор записи (UUID)"
    )


class SoftDeleteMixin:
    """
    Mixin для мягкого удаления
    Вместо физического удаления помечает записи как удаленные
    """
    
    is_deleted: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Помечена ли запись как удаленная"
    )
    
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время удаления записи"
    )
    
    def delete(self):
        """Помечает запись как удаленную"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
    
    def restore(self):
        """Восстанавливает удаленную запись"""
        self.is_deleted = False
        self.deleted_at = None


class ActiveMixin:
    """
    Mixin для активности/деактивации записей
    """
    
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Активна ли запись"
    )
    
    def activate(self):
        """Активирует запись"""
        self.is_active = True
    
    def deactivate(self):
        """Деактивирует запись"""
        self.is_active = False


class MetadataMixin:
    """
    Mixin для дополнительных метаданных
    Хранит произвольные данные в JSON формате
    """

    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Дополнительные метаданные в JSON формате"
    )


class DescriptionMixin:
    """
    Mixin для описания записей
    """
    
    title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Заголовок записи"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Описание записи"
    )


class BaseModel(Base, IDMixin, TimestampMixin):
    """
    Базовая модель для большинства таблиц
    Включает ID, временные метки
    """
    __abstract__ = True
    
    def __repr__(self) -> str:
        """Строковое представление модели"""
        class_name = self.__class__.__name__
        return f"<{class_name}(id={self.id})>"
    
    def to_dict(self, exclude: Optional[set] = None) -> Dict[str, Any]:
        """
        Конвертирует модель в словарь
        
        Args:
            exclude: Множество полей для исключения
            
        Returns:
            Словарь с данными модели
        """
        exclude = exclude or set()
        result = {}
        
        for column in self.__table__.columns:
            if column.name not in exclude:
                value = getattr(self, column.name)
                if isinstance(value, datetime):
                    value = value.isoformat()
                elif isinstance(value, uuid.UUID):
                    value = str(value)
                result[column.name] = value
                
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseModel':
        """
        Создает экземпляр модели из словаря
        
        Args:
            data: Словарь с данными
            
        Returns:
            Экземпляр модели
        """
        # Фильтруем только те ключи, которые есть в модели
        valid_columns = {c.name for c in cls.__table__.columns}
        filtered_data = {k: v for k, v in data.items() if k in valid_columns}
        
        return cls(**filtered_data)


class BaseModelWithSoftDelete(BaseModel, SoftDeleteMixin):
    """
    Базовая модель с поддержкой мягкого удаления
    """
    __abstract__ = True


class BaseModelWithUUID(Base, UUIDMixin, TimestampMixin):
    """
    Базовая модель с UUID первичным ключом
    Для распределенных систем или когда нужна дополнительная безопасность
    """
    __abstract__ = True
    
    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f"<{class_name}(id={self.id})>"


class BaseActiveModel(BaseModel, ActiveMixin):
    """
    Базовая модель с поддержкой активности/деактивации
    """
    __abstract__ = True


class BaseFullModel(BaseModel, SoftDeleteMixin, ActiveMixin, MetadataMixin):
    """
    Полная базовая модель со всеми миксинами
    Используется для сложных сущностей
    """
    __abstract__ = True


# Утилитарные функции для работы с моделями

def get_model_fields(model_class) -> set:
    """
    Получает список полей модели
    
    Args:
        model_class: Класс модели
        
    Returns:
        Множество имен полей
    """
    return {c.name for c in model_class.__table__.columns}


def model_to_dict_safe(instance: BaseModel, exclude_sensitive: bool = True) -> Dict[str, Any]:
    """
    Безопасно конвертирует модель в словарь
    Исключает чувствительные поля
    
    Args:
        instance: Экземпляр модели
        exclude_sensitive: Исключать ли чувствительные поля
        
    Returns:
        Словарь с данными
    """
    sensitive_fields = {
        'password', 'password_hash', 'token', 'secret', 'key', 
        'api_key', 'webhook_secret', 'session_id'
    }
    
    exclude = sensitive_fields if exclude_sensitive else set()
    return instance.to_dict(exclude=exclude)


def bulk_create_or_update(session, model_class, data_list: list, unique_field: str = 'id'):
    """
    Массовое создание или обновление записей
    
    Args:
        session: SQLAlchemy сессия
        model_class: Класс модели
        data_list: Список словарей с данными
        unique_field: Поле для определения уникальности
        
    Returns:
        Список созданных/обновленных объектов
    """
    results = []
    
    for data in data_list:
        unique_value = data.get(unique_field)
        if unique_value:
            # Пытаемся найти существующий объект
            existing = session.query(model_class).filter(
                getattr(model_class, unique_field) == unique_value
            ).first()
            
            if existing:
                # Обновляем существующий
                for key, value in data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                results.append(existing)
            else:
                # Создаем новый
                new_obj = model_class(**data)
                session.add(new_obj)
                results.append(new_obj)
        else:
            # Создаем новый объект без проверки уникальности
            new_obj = model_class(**data)
            session.add(new_obj)
            results.append(new_obj)
    
    return results


# Константы для статусов, используемые в моделях

class DownloadStatus:
    """Статусы скачивания"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    ALL = [PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED]


class UserType:
    """Типы пользователей"""
    FREE = "free"
    TRIAL = "trial"
    PREMIUM = "premium"
    ADMIN = "admin"
    
    ALL = [FREE, TRIAL, PREMIUM, ADMIN]


class Platform:
    """Поддерживаемые платформы"""
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    
    ALL = [YOUTUBE, TIKTOK, INSTAGRAM]


class FileStatus:
    """Статусы файлов в CDN"""
    UPLOADING = "uploading"
    AVAILABLE = "available"
    EXPIRED = "expired"
    DELETED = "deleted"
    
    ALL = [UPLOADING, AVAILABLE, EXPIRED, DELETED]