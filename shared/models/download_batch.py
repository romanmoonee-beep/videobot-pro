"""
VideoBot Pro - Download Batch Model
Модель для группового скачивания видео
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, 
    Text, JSON, ForeignKey, Index, CheckConstraint, Float
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import BaseModel, DownloadStatus


class DownloadBatch(BaseModel):
    """
    Модель группового скачивания видео
    
    Представляет собой пакет ссылок, которые пользователь
    отправил для скачивания одновременно
    """
    
    __tablename__ = "download_batches"
    
    # Связь с пользователем
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID пользователя, создавшего batch"
    )
    
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Telegram ID пользователя (для быстрого поиска)"
    )
    
    # Основные данные batch'а
    batch_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Уникальный идентификатор batch'а"
    )
    
    urls: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        comment="Список URL для скачивания"
    )
    
    total_urls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Общее количество URL в batch'е"
    )
    
    # Статус обработки
    status: Mapped[str] = mapped_column(
        String(20),
        default=DownloadStatus.PENDING,
        nullable=False,
        index=True,
        comment="Статус batch'а: pending, processing, completed, failed, cancelled"
    )
    
    # Прогресс выполнения
    completed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество успешно обработанных URL"
    )
    
    failed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество неудачных URL"
    )
    
    skipped_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество пропущенных URL (дубликаты, неподдерживаемые)"
    )
    
    # Временные метки процесса
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время начала обработки"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время завершения обработки"
    )
    
    # Добавленная колонка created_at
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="Время создания batch'а"
    )
    
    # Время жизни и очистка
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Время истечения срока хранения файлов"
    )
    
    # Настройки доставки
    delivery_method: Mapped[str] = mapped_column(
        String(20),
        default="individual",
        nullable=False,
        comment="Метод доставки: individual, archive, mixed"
    )
    
    send_to_chat: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Отправлять файлы в чат"
    )
    
    create_archive: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Создавать ZIP архив"
    )
    
    # CDN и файлы
    cdn_links: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        default=list,
        comment="Ссылки на файлы в CDN"
    )
    
    archive_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="URL архива со всеми файлами"
    )
    
    archive_size_mb: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Размер архива в мегабайтах"
    )
    
    total_size_mb: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="Общий размер всех файлов в мегабайтах"
    )
    
    # Качество и настройки скачивания
    quality_preference: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Предпочтительное качество: auto, 480p, 720p, 1080p, 4K"
    )
    
    format_preference: Mapped[Optional[str]] = mapped_column(
        String(10),
        default="mp4",
        comment="Предпочтительный формат файла"
    )
    
    # Метаданные и результаты
    platform_stats: Mapped[Optional[Dict[str, int]]] = mapped_column(
        JSON,
        default=dict,
        comment="Статистика по платформам (youtube: 5, tiktok: 3)"
    )
    
    results: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON,
        default=list,
        comment="Детальные результаты обработки каждого URL"
    )
    
    error_messages: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        default=list,
        comment="Сообщения об ошибках"
    )
    
    # Worker и обработка
    worker_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="ID worker'а, обрабатывающего batch"
    )
    
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="ID задачи Celery"
    )
    
    priority: Mapped[int] = mapped_column(
        Integer,
        default=5,
        comment="Приоритет обработки (1-10, где 10 - высший)"
    )
    
    # Пользовательские настройки
    user_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID сообщения пользователя с ссылками"
    )
    
    bot_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID сообщения бота с результатами"
    )
    
    notification_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Отправлено ли уведомление о завершении"
    )
    
    # Аналитика
    processing_time_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Время обработки в секундах"
    )
    
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Количество попыток повторной обработки"
    )
    
    # Relationships
    user = relationship("User", back_populates="download_batches")
    download_tasks = relationship("DownloadTask", back_populates="batch", cascade="all, delete-orphan")
    
    # Constraints и индексы
    __table_args__ = (
        CheckConstraint(
            status.in_(DownloadStatus.ALL),
            name='check_batch_status'
        ),
        CheckConstraint(
            'total_urls > 0',
            name='check_total_urls_positive'
        ),
        CheckConstraint(
            'completed_count >= 0',
            name='check_completed_count_positive'
        ),
        CheckConstraint(
            'failed_count >= 0', 
            name='check_failed_count_positive'
        ),
        CheckConstraint(
            'skipped_count >= 0',
            name='check_skipped_count_positive'
        ),
        CheckConstraint(
            'total_size_mb >= 0',
            name='check_total_size_positive'
        ),
        CheckConstraint(
            'priority >= 1 AND priority <= 10',
            name='check_priority_range'
        ),
        CheckConstraint(
            'retry_count >= 0',
            name='check_retry_count_positive'
        ),
        # Оптимизированные индексы
        Index('idx_batch_user_status', user_id, status),
        Index('idx_batch_status_created', status, created_at),
        Index('idx_batch_expires_at', expires_at),
        Index('idx_batch_telegram_user', telegram_user_id, created_at),
        Index('idx_batch_priority_status', priority, status),
    )
    
    def __repr__(self) -> str:
        return f"<DownloadBatch(id={self.id}, batch_id='{self.batch_id}', urls={self.total_urls}, status='{self.status}')>"
    
    @property
    def progress_percent(self) -> float:
        """Прогресс выполнения в процентах"""
        if self.total_urls == 0:
            return 0.0
        processed = self.completed_count + self.failed_count + self.skipped_count
        return (processed / self.total_urls) * 100
    
    @property
    def success_rate(self) -> float:
        """Процент успешно обработанных URL"""
        if self.total_urls == 0:
            return 0.0
        return (self.completed_count / self.total_urls) * 100
    
    @property
    def is_processing(self) -> bool:
        """Находится ли batch в процессе обработки"""
        return self.status == DownloadStatus.PROCESSING
    
    @property
    def is_completed(self) -> bool:
        """Завершена ли обработка"""
        return self.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]
    
    @property
    def is_expired(self) -> bool:
        """Истек ли срок хранения"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    @property
    def time_remaining_hours(self) -> Optional[float]:
        """Сколько часов осталось до истечения"""
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.total_seconds() / 3600)
    
    @property
    def estimated_completion_time(self) -> Optional[datetime]:
        """Расчетное время завершения"""
        if self.status != DownloadStatus.PROCESSING:
            return None
            
        if not self.started_at or self.completed_count == 0:
            return None
            
        # Расчет на основе текущей скорости
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        speed = self.completed_count / elapsed  # URLs per second
        
        remaining_urls = self.total_urls - self.completed_count - self.failed_count - self.skipped_count
        if speed > 0 and remaining_urls > 0:
            remaining_seconds = remaining_urls / speed
            return datetime.utcnow() + timedelta(seconds=remaining_seconds)
            
        return None
    
    def start_processing(self, worker_id: str = None, task_id: str = None):
        """Начать обработку batch'а"""
        self.status = DownloadStatus.PROCESSING
        self.started_at = datetime.utcnow()
        if worker_id:
            self.worker_id = worker_id
        if task_id:
            self.celery_task_id = task_id
    
    def complete_processing(self):
        """Завершить обработку batch'а"""
        self.status = DownloadStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.processing_time_seconds = int(delta.total_seconds())
    
    def fail_processing(self, error_message: str = None):
        """Пометить batch как неудачный"""
        self.status = DownloadStatus.FAILED
        self.completed_at = datetime.utcnow()
        
        if error_message:
            if not self.error_messages:
                self.error_messages = []
            self.error_messages.append(error_message)
    
    def cancel_processing(self):
        """Отменить обработку batch'а"""
        self.status = DownloadStatus.CANCELLED
        self.completed_at = datetime.utcnow()
    
    def add_result(self, url: str, result: Dict[str, Any]):
        """Добавить результат обработки URL"""
        if not self.results:
            self.results = []
            
        result_entry = {
            'url': url,
            'timestamp': datetime.utcnow().isoformat(),
            **result
        }
        self.results.append(result_entry)
        
        # Обновляем счетчики
        if result.get('success', False):
            self.completed_count += 1
            file_size = result.get('file_size_mb', 0)
            self.total_size_mb += file_size
        else:
            self.failed_count += 1
    
    def add_cdn_link(self, url: str, cdn_data: Dict[str, Any]):
        """Добавить ссылку на файл в CDN"""
        if not self.cdn_links:
            self.cdn_links = []
            
        cdn_entry = {
            'original_url': url,
            'cdn_url': cdn_data.get('cdn_url'),
            'direct_url': cdn_data.get('direct_url'),
            'file_size_mb': cdn_data.get('file_size_mb'),
            'platform': cdn_data.get('platform'),
            'title': cdn_data.get('title'),
            'duration': cdn_data.get('duration'),
            'quality': cdn_data.get('quality'),
            'uploaded_at': datetime.utcnow().isoformat()
        }
        self.cdn_links.append(cdn_entry)
    
    def update_platform_stats(self, platform: str):
        """Обновить статистику по платформам"""
        if not self.platform_stats:
            self.platform_stats = {}
        
        self.platform_stats[platform] = self.platform_stats.get(platform, 0) + 1
    
    def set_expiration(self, hours: int):
        """Установить время истечения"""
        self.expires_at = datetime.utcnow() + timedelta(hours=hours)
    
    def extend_expiration(self, hours: int):
        """Продлить срок хранения"""
        if self.expires_at:
            self.expires_at += timedelta(hours=hours)
        else:
            self.set_expiration(hours)
    
    def get_successful_files(self) -> List[Dict[str, Any]]:
        """Получить список успешно обработанных файлов"""
        return [link for link in (self.cdn_links or []) if link.get('cdn_url')]
    
    def get_failed_urls(self) -> List[str]:
        """Получить список неудачных URL"""
        if not self.results:
            return []
        return [r['url'] for r in self.results if not r.get('success', False)]
    
    def calculate_stats(self) -> Dict[str, Any]:
        """Рассчитать детальную статистику batch'а"""
        return {
            'total_urls': self.total_urls,
            'completed': self.completed_count,
            'failed': self.failed_count,
            'skipped': self.skipped_count,
            'success_rate': self.success_rate,
            'total_size_mb': self.total_size_mb,
            'platform_distribution': self.platform_stats or {},
            'processing_time_seconds': self.processing_time_seconds,
            'average_file_size_mb': (
                self.total_size_mb / max(1, self.completed_count)
                if self.completed_count > 0 else 0
            ),
            'files_available': len(self.get_successful_files()),
            'archive_created': bool(self.archive_url),
            'time_remaining_hours': self.time_remaining_hours
        }
    
    def to_user_summary(self) -> Dict[str, Any]:
        """Краткая сводка для пользователя"""
        return {
            'batch_id': self.batch_id,
            'status': self.status,
            'progress': f"{self.completed_count}/{self.total_urls}",
            'success_rate': f"{self.success_rate:.1f}%",
            'total_size_mb': self.total_size_mb,
            'files_ready': len(self.get_successful_files()),
            'archive_url': self.archive_url,
            'expires_in_hours': self.time_remaining_hours,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
