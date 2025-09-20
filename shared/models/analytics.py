"""
VideoBot Pro - Analytics Model
Модель для системы аналитики и метрик
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Union
from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, 
    Text, JSON, ForeignKey, Index, CheckConstraint, 
    Float, Date
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from sqlalchemy import or_

from .base import BaseModel

class EventType:
    """Типы аналитических событий"""
    # Пользователи
    USER_REGISTERED = "user_registered"
    USER_ACTIVATED = "user_activated"
    USER_TRIAL_STARTED = "user_trial_started"
    USER_PREMIUM_PURCHASED = "user_premium_purchased"
    USER_PREMIUM_EXPIRED = "user_premium_expired"
    USER_BANNED = "user_banned"
    USER_UNBANNED = "user_unbanned"
    
    # Скачивания
    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    BATCH_CREATED = "batch_created"
    BATCH_COMPLETED = "batch_completed"
    
    # Подписки на каналы
    SUBSCRIPTION_CHECKED = "subscription_checked"
    SUBSCRIPTION_FAILED = "subscription_failed"
    
    # Платежи
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_REFUNDED = "payment_refunded"
    
    # Система
    BOT_STARTED = "bot_started"
    BOT_STOPPED = "bot_stopped"
    ERROR_OCCURRED = "error_occurred"
    
    # Контент
    MESSAGE_SENT = "message_sent"
    BUTTON_CLICKED = "button_clicked"
    COMMAND_EXECUTED = "command_executed"
    
    ALL = [
        USER_REGISTERED, USER_ACTIVATED, USER_TRIAL_STARTED, 
        USER_PREMIUM_PURCHASED, USER_PREMIUM_EXPIRED, USER_BANNED, USER_UNBANNED,
        DOWNLOAD_STARTED, DOWNLOAD_COMPLETED, DOWNLOAD_FAILED,
        BATCH_CREATED, BATCH_COMPLETED,
        SUBSCRIPTION_CHECKED, SUBSCRIPTION_FAILED,
        PAYMENT_INITIATED, PAYMENT_COMPLETED, PAYMENT_FAILED, PAYMENT_REFUNDED,
        BOT_STARTED, BOT_STOPPED, ERROR_OCCURRED,
        MESSAGE_SENT, BUTTON_CLICKED, COMMAND_EXECUTED
    ]

class BatchStatus:
    """Статусы batch-операций скачивания"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = [PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED]

class AnalyticsEvent(BaseModel):
    """
    Модель аналитического события
    
    Записывает все значимые события в системе для
    последующего анализа и построения метрик
    """
    
    __tablename__ = "analytics_events"
    
    # Основная информация о событии
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Тип события"
    )
    
    event_category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="Категория события (user, download, payment, system)"
    )
    
    # Связанные сущности
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="ID пользователя (если применимо)"
    )
    
    telegram_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Telegram ID пользователя"
    )
    
    admin_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID администратора (если действие выполнено админом)"
    )
    
    # Связанные объекты
    download_task_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("download_tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID задачи скачивания"
    )
    
    download_batch_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("download_batches.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID batch'а скачивания"
    )
    
    payment_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID платежа"
    )
    
    broadcast_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("broadcast_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID рассылки"
    )
    
    # Данные события
    event_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Дополнительные данные события"
    )
    
    # Метрики
    value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Числовое значение (сумма платежа, размер файла, время выполнения)"
    )
    
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Длительность операции в секундах"
    )
    
    # Контекст
    platform: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Платформа (для скачиваний)"
    )
    
    user_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Тип пользователя на момент события"
    )
    
    source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Источник события (bot, web, api, admin)"
    )
    
    # Техническая информация
    session_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="ID сессии пользователя"
    )
    
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP адрес"
    )
    
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User Agent"
    )
    
    # Временная информация
    event_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Дата события (для группировки)"
    )
    
    event_hour: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Час события (0-23)"
    )
    
    # Статус обработки
    is_processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Обработано ли событие в агрегатах"
    )
    
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время обработки события"
    )
    
    # Relationships
    user = relationship("User", back_populates="analytics_events")
    admin_user = relationship("AdminUser", foreign_keys=[admin_user_id])
    download_task = relationship("DownloadTask", foreign_keys=[download_task_id])
    download_batch = relationship("DownloadBatch", foreign_keys=[download_batch_id])
    payment = relationship("Payment", foreign_keys=[payment_id])
    broadcast = relationship("BroadcastMessage", foreign_keys=[broadcast_id])
    
    # Constraints и индексы
    __table_args__ = (
        CheckConstraint(
            event_type.in_(EventType.ALL),
            name='check_event_type'
        ),
        CheckConstraint(
            'event_hour >= 0 AND event_hour <= 23',
            name='check_event_hour_range'
        ),
        CheckConstraint(
            'duration_seconds >= 0',
            name='check_duration_positive'
        ),
        # Композитные индексы для аналитики
        Index('idx_analytics_type_date', 'event_type', 'event_date'),
        Index('idx_analytics_category_date', 'event_category', 'event_date'),
        Index('idx_analytics_user_date', 'user_id', 'event_date'),
        Index('idx_analytics_platform_date', 'platform', 'event_date'),
        Index('idx_analytics_date_hour', 'event_date', 'event_hour'),
        Index('idx_analytics_processed', 'is_processed', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<AnalyticsEvent(id={self.id}, type='{self.event_type}', user_id={self.user_id})>"
    
    @classmethod
    def track_event(cls, event_type: str, user_id: int = None, telegram_user_id: int = None,
                   event_data: Dict[str, Any] = None, value: float = None,
                   duration_seconds: int = None, platform: str = None,
                   user_type: str = None, source: str = "bot", **kwargs) -> 'AnalyticsEvent':
        """Создать событие аналитики"""
        now = datetime.utcnow()
        
        # Определяем категорию по типу события
        category = cls._get_event_category(event_type)
        
        return cls(
            event_type=event_type,
            event_category=category,
            user_id=user_id,
            telegram_user_id=telegram_user_id,
            event_data=event_data or {},
            value=value,
            duration_seconds=duration_seconds,
            platform=platform,
            user_type=user_type,
            source=source,
            event_date=now.date(),
            event_hour=now.hour,
            **kwargs
        )
    
    @staticmethod
    def _get_event_category(event_type: str) -> str:
        """Определить категорию события по типу"""
        if event_type.startswith('user_'):
            return 'user'
        elif event_type.startswith('download_') or event_type.startswith('batch_'):
            return 'download'
        elif event_type.startswith('payment_'):
            return 'payment'
        elif event_type.startswith('subscription_'):
            return 'subscription'
        elif event_type in ['bot_started', 'bot_stopped', 'error_occurred']:
            return 'system'
        elif event_type in ['message_sent', 'button_clicked', 'command_executed']:
            return 'interaction'
        else:
            return 'other'
    
    def mark_as_processed(self):
        """Пометить событие как обработанное"""
        self.is_processed = True
        self.processed_at = datetime.utcnow()


class DailyStats(BaseModel):
    """
    Модель ежедневной агрегированной статистики
    
    Хранит агрегированные метрики по дням для быстрого доступа
    """
    
    __tablename__ = "daily_stats"
    
    # Дата статистики
    stats_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Дата статистики"
    )
    
    # Пользователи
    new_users: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Новые пользователи за день"
    )
    
    active_users: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Активные пользователи за день"
    )
    
    trial_users_started: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Пользователей начали пробный период"
    )
    
    premium_purchases: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Покупок Premium за день"
    )
    
    # Скачивания
    total_downloads: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Общее количество скачиваний"
    )
    
    successful_downloads: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Успешных скачиваний"
    )
    
    failed_downloads: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Неудачных скачиваний"
    )
    
    batches_created: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Создано batch'ей"
    )
    
    # Платформы
    youtube_downloads: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Скачиваний с YouTube"
    )
    
    tiktok_downloads: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Скачиваний с TikTok"
    )
    
    instagram_downloads: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Скачиваний с Instagram"
    )
    
    # Финансы
    revenue_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Выручка в долларах"
    )
    
    total_payments: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Общее количество платежей"
    )
    
    successful_payments: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Успешных платежей"
    )
    
    # Системные метрики
    total_file_size_mb: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Общий размер скачанных файлов в МБ"
    )
    
    avg_processing_time_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Среднее время обработки в секундах"
    )
    
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество ошибок"
    )
    
    # Дополнительные метрики
    additional_metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Дополнительные метрики в JSON"
    )
    
    # Constraints и индексы
    __table_args__ = (
        Index('idx_daily_stats_date', stats_date, unique=True),
        CheckConstraint('new_users >= 0', name='check_new_users_positive'),
        CheckConstraint('active_users >= 0', name='check_active_users_positive'),
        CheckConstraint('total_downloads >= 0', name='check_downloads_positive'),
        CheckConstraint('revenue_usd >= 0', name='check_revenue_positive'),
    )
    
    def __repr__(self) -> str:
        return f"<DailyStats(date={self.stats_date}, users={self.new_users}, downloads={self.total_downloads})>"
    
    @property
    def download_success_rate(self) -> float:
        """Процент успешных скачиваний"""
        if self.total_downloads == 0:
            return 0.0
        return (self.successful_downloads / self.total_downloads) * 100
    
    @property
    def payment_success_rate(self) -> float:
        """Процент успешных платежей"""
        if self.total_payments == 0:
            return 0.0
        return (self.successful_payments / self.total_payments) * 100
    
    @property
    def avg_revenue_per_user(self) -> float:
        """Средняя выручка на пользователя"""
        if self.active_users == 0:
            return 0.0
        return self.revenue_usd / self.active_users
    
    @classmethod
    def get_or_create_for_date(cls, session, target_date: date) -> 'DailyStats':
        """Получить или создать статистику для даты"""
        stats = session.query(cls).filter(cls.stats_date == target_date).first()
        if not stats:
            stats = cls(stats_date=target_date)
            session.add(stats)
        return stats
    
    def update_user_metrics(self, new_users: int = 0, active_users: int = 0,
                          trial_started: int = 0, premium_purchases: int = 0):
        """Обновить метрики пользователей"""
        self.new_users += new_users
        self.active_users = active_users  # Абсолютное значение
        self.trial_users_started += trial_started
        self.premium_purchases += premium_purchases
    
    def update_download_metrics(self, total: int = 0, successful: int = 0, failed: int = 0,
                              batches: int = 0, youtube: int = 0, tiktok: int = 0,
                              instagram: int = 0, file_size_mb: float = 0):
        """Обновить метрики скачиваний"""
        self.total_downloads += total
        self.successful_downloads += successful
        self.failed_downloads += failed
        self.batches_created += batches
        self.youtube_downloads += youtube
        self.tiktok_downloads += tiktok
        self.instagram_downloads += instagram
        self.total_file_size_mb += file_size_mb
    
    def update_payment_metrics(self, revenue: float = 0, total_payments: int = 0,
                             successful_payments: int = 0):
        """Обновить финансовые метрики"""
        self.revenue_usd += revenue
        self.total_payments += total_payments
        self.successful_payments += successful_payments
    
    def update_system_metrics(self, errors: int = 0, avg_processing_time: float = None):
        """Обновить системные метрики"""
        self.error_count += errors
        if avg_processing_time is not None:
            self.avg_processing_time_seconds = avg_processing_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертировать в словарь"""
        return {
            'stats_date': self.stats_date.isoformat(),
            'new_users': self.new_users,
            'active_users': self.active_users,
            'trial_users_started': self.trial_users_started,
            'premium_purchases': self.premium_purchases,
            'total_downloads': self.total_downloads,
            'successful_downloads': self.successful_downloads,
            'failed_downloads': self.failed_downloads,
            'download_success_rate': self.download_success_rate,
            'batches_created': self.batches_created,
            'youtube_downloads': self.youtube_downloads,
            'tiktok_downloads': self.tiktok_downloads,
            'instagram_downloads': self.instagram_downloads,
            'revenue_usd': self.revenue_usd,
            'total_payments': self.total_payments,
            'successful_payments': self.successful_payments,
            'payment_success_rate': self.payment_success_rate,
            'avg_revenue_per_user': self.avg_revenue_per_user,
            'total_file_size_mb': self.total_file_size_mb,
            'avg_processing_time_seconds': self.avg_processing_time_seconds,
            'error_count': self.error_count,
            'additional_metrics': self.additional_metrics
        }


# Утилитарные функции для аналитики

async def track_user_event(event_type: str, user_id: int, telegram_user_id: int,
                    user_type: str = None, **kwargs):
    """Отследить событие пользователя"""
    return AnalyticsEvent.track_event(
        event_type=event_type,
        user_id=user_id,
        telegram_user_id=telegram_user_id,
        user_type=user_type,
        **kwargs
    )

async def track_download_event(event_type: str, user_id: int, platform: str,
                        file_size_mb: float = None, duration_seconds: int = None,
                        **kwargs):
    """Отследить событие скачивания"""
    return AnalyticsEvent.track_event(
        event_type=event_type,
        user_id=user_id,
        platform=platform,
        value=file_size_mb,
        duration_seconds=duration_seconds,
        **kwargs
    )

async def track_payment_event(event_type: str, user_id: int, payment_amount: float,
                       payment_method: str = None, **kwargs):
    """Отследить событие платежа"""
    return AnalyticsEvent.track_event(
        event_type=event_type,
        user_id=user_id,
        value=payment_amount,
        event_data={'payment_method': payment_method},
        **kwargs
    )


async def track_system_event(event_type: str, event_data: Dict[str, Any] = None,
                       error_message: str = None, duration_seconds: int = None,
                       **kwargs):
    """Отследить системное событие"""
    data = event_data or {}
    if error_message:
        data['error_message'] = error_message

    return AnalyticsEvent.track_event(
        event_type=event_type,
        event_data=data,
        duration_seconds=duration_seconds,
        source='system',
        **kwargs
    )