# shared/models/download_task.py
"""
VideoBot Pro - Download Task Model
Модель для отдельной задачи скачивания видео
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, 
    Text, JSON, ForeignKey, Index, CheckConstraint, Float
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from urllib.parse import urlparse

from .base import BaseModel, DownloadStatus, Platform

class DownloadTask(BaseModel):
    """
    Модель отдельной задачи скачивания видео
    
    Представляет собой одну ссылку внутри batch'а или отдельное скачивание
    """
    
    __tablename__ = "download_tasks"
    
    # Связи с другими сущностями
    batch_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("download_batches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="ID batch'а (если задача является частью группового скачивания)"
    )
    
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID пользователя"
    )
    
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Telegram ID пользователя"
    )
    
    # Основные данные задачи
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    
    original_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Оригинальная URL для скачивания"
    )
    
    cleaned_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Очищенная URL (без tracking параметров)"
    )
    
    platform: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Платформа видео: youtube, tiktok, instagram"
    )
    
    # Статус и прогресс
    status: Mapped[str] = mapped_column(
        String(20),
        default=DownloadStatus.PENDING,
        nullable=False,
        index=True,
        comment="Статус задачи"
    )
    
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Прогресс скачивания в процентах (0-100)"
    )
    
    # Временные метки
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время начала скачивания"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время завершения скачивания"
    )
    
    # Информация о видео
    video_title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Заголовок видео"
    )
    
    video_duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Длительность видео в секундах"
    )
    
    # Параметры скачивания
    requested_quality: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Запрошенное качество: auto, 480p, 720p, 1080p, 4K"
    )
    
    actual_quality: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Фактическое качество скачанного файла"
    )
    
    # Информация о файле
    file_name: Mapped[Optional[str]] = mapped_column(
        String(300),
        nullable=True,
        comment="Имя скачанного файла"
    )
    
    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Размер файла в байтах"
    )
    
    # CDN и доставка
    cdn_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="URL файла в CDN"
    )
    
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Срок истечения доступности файла"
    )
    
    # Ошибки
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Сообщение об ошибке"
    )
    
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Количество попыток повторного скачивания"
    )
    
    # Приоритет
    priority: Mapped[int] = mapped_column(
        Integer,
        default=5,
        comment="Приоритет задачи (1-10)"
    )

    user: Mapped["User"] = relationship("User", back_populates="downloads")

    # Constraints и индексы
    __table_args__ = (
        CheckConstraint(
            status.in_(DownloadStatus.ALL),
            name='check_task_status'
        ),
        CheckConstraint(
            platform.in_(Platform.ALL),
            name='check_platform_valid'
        ),
        CheckConstraint(
            'progress_percent >= 0 AND progress_percent <= 100',
            name='check_progress_range'
        ),
        CheckConstraint(
            'retry_count >= 0',
            name='check_retry_count_positive'
        ),
        CheckConstraint(
            'priority >= 1 AND priority <= 10',
            name='check_priority_range'
        ),
        # Используем правильные ссылки на колонки
        Index('idx_task_user_status', 'user_id', 'status'),
        Index('idx_task_batch_order', 'batch_id', 'priority'),
        Index('idx_task_platform_status', 'platform', 'status'),
        Index('idx_task_expires_at', 'expires_at'),
        Index('idx_task_priority_status', 'priority', 'status'),
    )
    
    def __repr__(self) -> str:
        return f"<DownloadTask(id={self.id}, task_id='{self.task_id}', status='{self.status}')>"
    
    @property
    def file_size_mb(self) -> float:
        """Размер файла в мегабайтах"""
        if not self.file_size_bytes:
            return 0.0
        return self.file_size_bytes / (1024 * 1024)
    
    @property
    def is_completed(self) -> bool:
        """Завершена ли задача"""
        return self.status == DownloadStatus.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        """Провалилась ли задача"""
        return self.status == DownloadStatus.FAILED
    
    @property
    def can_retry(self) -> bool:
        """Можно ли повторить задачу"""
        return self.retry_count < 3 and self.is_failed
    
    @classmethod
    def create_from_url(cls, url: str, user_id: int, telegram_user_id: int, **kwargs) -> 'DownloadTask':
        """Создать задачу из URL"""
        # Определяем платформу по URL
        platform = cls._detect_platform(url)
        
        # Генерируем уникальный task_id
        import uuid
        task_id = f"task_{uuid.uuid4().hex[:16]}"
        
        return cls(
            task_id=task_id,
            original_url=url,
            cleaned_url=cls._clean_url(url),
            platform=platform,
            user_id=user_id,
            telegram_user_id=telegram_user_id,
            **kwargs
        )
    
    @staticmethod
    def _detect_platform(url: str) -> str:
        """Определить платформу по URL"""
        url_lower = url.lower()
        
        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return Platform.YOUTUBE
        elif 'tiktok.com' in url_lower or 'vm.tiktok.com' in url_lower:
            return Platform.TIKTOK
        elif 'instagram.com' in url_lower:
            return Platform.INSTAGRAM
        else:
            return "unknown"
    
    @staticmethod
    def _clean_url(url: str) -> str:
        """Очистить URL от tracking параметров"""
        try:
            parsed = urlparse(url)
            # Простая очистка - можно расширить
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except:
            return url
    
    def mark_as_processing(self):
        """Пометить как обрабатывающуюся"""
        self.status = DownloadStatus.PROCESSING
        self.started_at = datetime.utcnow()
    
    def mark_as_completed(self):
        """Пометить как завершенную"""
        self.status = DownloadStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.progress_percent = 100
    
    def mark_as_failed(self, error: str):
        """Пометить как неудачную"""
        self.status = DownloadStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error