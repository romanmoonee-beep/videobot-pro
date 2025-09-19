"""
VideoBot Pro - Broadcast Message Model
Модель для массовых рассылок пользователям
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, 
    Text, JSON, ForeignKey, Index, CheckConstraint, Float
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import BaseModel, SoftDeleteMixin


class BroadcastStatus:
    """Статусы рассылки"""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    
    ALL = [DRAFT, SCHEDULED, SENDING, COMPLETED, FAILED, CANCELLED, PAUSED]


class BroadcastTargetType:
    """Типы целевой аудитории"""
    ALL_USERS = "all_users"
    FREE_USERS = "free_users"
    TRIAL_USERS = "trial_users"
    PREMIUM_USERS = "premium_users"
    CUSTOM = "custom"
    SPECIFIC_USERS = "specific_users"
    
    ALL = [ALL_USERS, FREE_USERS, TRIAL_USERS, PREMIUM_USERS, CUSTOM, SPECIFIC_USERS]


class BroadcastMessage(BaseModel, SoftDeleteMixin):
    """
    Модель массовой рассылки
    
    Управляет созданием, отправкой и отслеживанием
    массовых сообщений пользователям бота
    """
    
    __tablename__ = "broadcast_messages"
    
    # Основная информация
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Заголовок рассылки (для внутреннего использования)"
    )
    
    message_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Текст сообщения для отправки"
    )
    
    message_html: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="HTML версия сообщения"
    )
    
    parse_mode: Mapped[str] = mapped_column(
        String(20),
        default="HTML",
        nullable=False,
        comment="Режим парсинга сообщения (HTML, Markdown)"
    )
    
    # Статус рассылки
    status: Mapped[str] = mapped_column(
        String(20),
        default=BroadcastStatus.DRAFT,
        nullable=False,
        index=True,
        comment="Статус рассылки"
    )
    
    # Целевая аудитория
    target_type: Mapped[str] = mapped_column(
        String(20),
        default=BroadcastTargetType.ALL_USERS,
        nullable=False,
        comment="Тип целевой аудитории"
    )
    
    target_user_ids: Mapped[Optional[List[int]]] = mapped_column(
        JSON,
        default=list,
        comment="Список конкретных user_id для отправки"
    )
    
    target_filters: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Фильтры для выборки пользователей"
    )
    
    # Расписание
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Время запланированной отправки"
    )
    
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время начала отправки"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время завершения отправки"
    )
    
    # Прогресс отправки
    total_recipients: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Общее количество получателей"
    )
    
    sent_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество успешно отправленных сообщений"
    )
    
    failed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество неудачных отправок"
    )
    
    blocked_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество заблокированных ботом пользователей"
    )
    
    # Дополнительные медиа
    media_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Тип медиа: photo, video, document, audio"
    )
    
    media_file_id: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="file_id медиафайла в Telegram"
    )
    
    media_caption: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Подпись к медиафайлу"
    )
    
    # Inline кнопки
    inline_keyboard: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Inline клавиатура для сообщения"
    )
    
    # Настройки отправки
    send_rate_per_minute: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
        comment="Скорость отправки сообщений в минуту"
    )
    
    retry_failed: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Повторять ли неудачные отправки"
    )
    
    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
        comment="Максимальное количество повторов"
    )
    
    # Аналитика
    delivery_stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Статистика доставки по часам/дням"
    )
    
    interaction_stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Статистика взаимодействий (клики по кнопкам)"
    )
    
    # Администрирование
    created_by_admin_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("admin_users.id"),
        nullable=False,
        comment="ID администратора, создавшего рассылку"
    )
    
    approved_by_admin_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("admin_users.id"),
        nullable=True,
        comment="ID администратора, одобрившего рассылку"
    )
    
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время одобрения рассылки"
    )
    
    # Worker и обработка
    worker_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="ID worker'а, обрабатывающего рассылку"
    )
    
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="ID Celery задачи"
    )
    
    # Ошибки и логи
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Сообщение об ошибке"
    )
    
    error_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Детальная информация об ошибках"
    )
    
    # Дополнительные настройки
    disable_notification: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Отправлять без звука уведомления"
    )
    
    protect_content: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Защитить контент от пересылки"
    )
    
    delete_after_hours: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Удалить сообщения через указанное количество часов"
    )
    
    # Теги и категории
    tags: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        default=list,
        comment="Теги для категоризации рассылок"
    )
    
    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Категория рассылки"
    )
    
    # Приоритет
    priority: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
        comment="Приоритет рассылки (1-10)"
    )
    
    # Relationships
    created_by_admin = relationship("AdminUser", foreign_keys=[created_by_admin_id])
    approved_by_admin = relationship("AdminUser", foreign_keys=[approved_by_admin_id])
    
    # Constraints и индексы
    __table_args__ = (
        CheckConstraint(
            status.in_(BroadcastStatus.ALL),
            name='check_broadcast_status'
        ),
        CheckConstraint(
            target_type.in_(BroadcastTargetType.ALL),
            name='check_target_type'
        ),
        CheckConstraint(
            'total_recipients >= 0',
            name='check_total_recipients_positive'
        ),
        CheckConstraint(
            'sent_count >= 0',
            name='check_sent_count_positive'
        ),
        CheckConstraint(
            'failed_count >= 0',
            name='check_failed_count_positive'
        ),
        CheckConstraint(
            'send_rate_per_minute > 0',
            name='check_send_rate_positive'
        ),
        CheckConstraint(
            'priority >= 1 AND priority <= 10',
            name='check_priority_range'
        ),
        # Индексы для оптимизации
        Index('idx_broadcast_status_scheduled', status, scheduled_at),
        Index('idx_broadcast_admin_created', created_by_admin_id, created_at),
        Index('idx_broadcast_priority_status', priority, status),
        Index('idx_broadcast_target_type', target_type, status),
    )
    
    def __repr__(self) -> str:
        return f"<BroadcastMessage(id={self.id}, title='{self.title}', status='{self.status}')>"
    
    @property
    def progress_percent(self) -> float:
        """Прогресс отправки в процентах"""
        if self.total_recipients == 0:
            return 0.0
        processed = self.sent_count + self.failed_count + self.blocked_count
        return (processed / self.total_recipients) * 100
    
    @property
    def success_rate(self) -> float:
        """Процент успешной доставки"""
        if self.total_recipients == 0:
            return 0.0
        return (self.sent_count / self.total_recipients) * 100
    
    @property
    def is_scheduled(self) -> bool:
        """Запланирована ли рассылка"""
        return self.status == BroadcastStatus.SCHEDULED and self.scheduled_at is not None
    
    @property
    def is_ready_to_send(self) -> bool:
        """Готова ли рассылка к отправке"""
        if self.status != BroadcastStatus.SCHEDULED:
            return False
        if not self.scheduled_at:
            return True  # Отправить немедленно
        return datetime.utcnow() >= self.scheduled_at
    
    @property
    def is_in_progress(self) -> bool:
        """Выполняется ли рассылка"""
        return self.status == BroadcastStatus.SENDING
    
    @property
    def is_completed(self) -> bool:
        """Завершена ли рассылка"""
        return self.status in [BroadcastStatus.COMPLETED, BroadcastStatus.FAILED, BroadcastStatus.CANCELLED]
    
    @property
    def estimated_duration_minutes(self) -> int:
        """Расчетное время выполнения в минутах"""
        if self.total_recipients == 0 or self.send_rate_per_minute == 0:
            return 0
        return max(1, self.total_recipients // self.send_rate_per_minute)
    
    @property
    def estimated_completion_time(self) -> Optional[datetime]:
        """Расчетное время завершения"""
        if not self.is_in_progress or not self.started_at:
            return None
        
        remaining = self.total_recipients - self.sent_count - self.failed_count - self.blocked_count
        if remaining <= 0:
            return datetime.utcnow()
        
        remaining_minutes = remaining / self.send_rate_per_minute
        return datetime.utcnow() + timedelta(minutes=remaining_minutes)
    
    def schedule_broadcast(self, scheduled_at: datetime = None):
        """Запланировать рассылку"""
        self.status = BroadcastStatus.SCHEDULED
        if scheduled_at:
            self.scheduled_at = scheduled_at
    
    def start_sending(self, total_recipients: int, worker_id: str = None, task_id: str = None):
        """Начать отправку рассылки"""
        self.status = BroadcastStatus.SENDING
        self.started_at = datetime.utcnow()
        self.total_recipients = total_recipients
        self.sent_count = 0
        self.failed_count = 0
        self.blocked_count = 0
        
        if worker_id:
            self.worker_id = worker_id
        if task_id:
            self.celery_task_id = task_id
    
    def update_progress(self, sent: int = 0, failed: int = 0, blocked: int = 0):
        """Обновить прогресс отправки"""
        self.sent_count += sent
        self.failed_count += failed
        self.blocked_count += blocked
        
        # Обновляем статистику по времени
        if not self.delivery_stats:
            self.delivery_stats = {}
        
        current_hour = datetime.utcnow().strftime('%Y-%m-%d %H:00')
        hour_stats = self.delivery_stats.get(current_hour, {'sent': 0, 'failed': 0, 'blocked': 0})
        hour_stats['sent'] += sent
        hour_stats['failed'] += failed
        hour_stats['blocked'] += blocked
        self.delivery_stats[current_hour] = hour_stats
    
    def complete_successfully(self):
        """Завершить рассылку успешно"""
        self.status = BroadcastStatus.COMPLETED
        self.completed_at = datetime.utcnow()
    
    def fail_broadcast(self, error_message: str, error_details: Dict[str, Any] = None):
        """Пометить рассылку как неудачную"""
        self.status = BroadcastStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
    
    def cancel_broadcast(self):
        """Отменить рассылку"""
        self.status = BroadcastStatus.CANCELLED
        self.completed_at = datetime.utcnow()
    
    def pause_broadcast(self):
        """Приостановить рассылку"""
        if self.status == BroadcastStatus.SENDING:
            self.status = BroadcastStatus.PAUSED
    
    def resume_broadcast(self):
        """Возобновить рассылку"""
        if self.status == BroadcastStatus.PAUSED:
            self.status = BroadcastStatus.SENDING
    
    def add_interaction_stat(self, interaction_type: str, user_id: int = None, data: str = None):
        """Добавить статистику взаимодействия"""
        if not self.interaction_stats:
            self.interaction_stats = {}
        
        # Общие счетчики
        total_stats = self.interaction_stats.get('total', {})
        total_stats[interaction_type] = total_stats.get(interaction_type, 0) + 1
        self.interaction_stats['total'] = total_stats
        
        # Детальные записи
        if 'details' not in self.interaction_stats:
            self.interaction_stats['details'] = []
        
        self.interaction_stats['details'].append({
            'type': interaction_type,
            'user_id': user_id,
            'data': data,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Ограничиваем количество детальных записей
        if len(self.interaction_stats['details']) > 1000:
            self.interaction_stats['details'] = self.interaction_stats['details'][-500:]
    
    def set_media(self, media_type: str, file_id: str, caption: str = None):
        """Установить медиафайл для рассылки"""
        self.media_type = media_type
        self.media_file_id = file_id
        if caption:
            self.media_caption = caption
    
    def set_inline_keyboard(self, keyboard: List[List[Dict[str, str]]]):
        """Установить inline клавиатуру"""
        self.inline_keyboard = {'inline_keyboard': keyboard}
    
    def add_button_row(self, buttons: List[Dict[str, str]]):
        """Добавить ряд кнопок"""
        if not self.inline_keyboard:
            self.inline_keyboard = {'inline_keyboard': []}
        self.inline_keyboard['inline_keyboard'].append(buttons)
    
    def get_target_users_query(self, session):
        """Получить запрос для выборки целевых пользователей"""
        from .user import User
        
        base_query = session.query(User).filter(
            User.is_deleted == False,
            User.is_banned == False
        )
        
        if self.target_type == BroadcastTargetType.ALL_USERS:
            return base_query
        elif self.target_type == BroadcastTargetType.FREE_USERS:
            return base_query.filter(User.user_type == 'free')
        elif self.target_type == BroadcastTargetType.TRIAL_USERS:
            return base_query.filter(User.user_type == 'trial')
        elif self.target_type == BroadcastTargetType.PREMIUM_USERS:
            return base_query.filter(User.user_type == 'premium')
        elif self.target_type == BroadcastTargetType.SPECIFIC_USERS:
            if self.target_user_ids:
                return base_query.filter(User.id.in_(self.target_user_ids))
        elif self.target_type == BroadcastTargetType.CUSTOM:
            # Применяем фильтры
            if self.target_filters:
                # Пример фильтров
                filters = self.target_filters
                if 'user_types' in filters:
                    base_query = base_query.filter(User.user_type.in_(filters['user_types']))
                if 'min_downloads' in filters:
                    base_query = base_query.filter(User.downloads_total >= filters['min_downloads'])
                if 'last_active_days' in filters:
                    cutoff_date = datetime.utcnow() - timedelta(days=filters['last_active_days'])
                    base_query = base_query.filter(User.last_active_at >= cutoff_date)
            return base_query
        
        return base_query.filter(False)  # Пустой результат для неизвестных типов
    
    def calculate_estimated_recipients(self, session) -> int:
        """Рассчитать примерное количество получателей"""
        query = self.get_target_users_query(session)
        return query.count()
    
    @classmethod
    def create_broadcast(cls, title: str, message_text: str, target_type: str,
                        created_by_admin_id: int, **kwargs) -> 'BroadcastMessage':
        """Создать новую рассылку"""
        return cls(
            title=title,
            message_text=message_text,
            target_type=target_type,
            created_by_admin_id=created_by_admin_id,
            **kwargs
        )
    
    def to_dict_summary(self) -> Dict[str, Any]:
        """Краткая сводка для списка рассылок"""
        return {
            'id': self.id,
            'title': self.title,
            'status': self.status,
            'target_type': self.target_type,
            'total_recipients': self.total_recipients,
            'sent_count': self.sent_count,
            'failed_count': self.failed_count,
            'progress_percent': self.progress_percent,
            'success_rate': self.success_rate,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'estimated_duration': self.estimated_duration_minutes,
            'category': self.category,
            'tags': self.tags
        }
    
    def to_dict_detailed(self) -> Dict[str, Any]:
        """Детальная информация для просмотра рассылки"""
        summary = self.to_dict_summary()
        summary.update({
            'message_text': self.message_text,
            'message_html': self.message_html,
            'parse_mode': self.parse_mode,
            'media_type': self.media_type,
            'media_file_id': self.media_file_id,
            'media_caption': self.media_caption,
            'inline_keyboard': self.inline_keyboard,
            'send_rate_per_minute': self.send_rate_per_minute,
            'retry_failed': self.retry_failed,
            'max_retries': self.max_retries,
            'blocked_count': self.blocked_count,
            'delivery_stats': self.delivery_stats,
            'interaction_stats': self.interaction_stats,
            'error_message': self.error_message,
            'disable_notification': self.disable_notification,
            'protect_content': self.protect_content,
            'priority': self.priority,
            'estimated_completion': self.estimated_completion_time.isoformat() if self.estimated_completion_time else None
        })
        return summary