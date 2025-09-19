"""
VideoBot Pro - Required Channel Model
Модель обязательных каналов для подписки
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, 
    Text, JSON, Index, CheckConstraint, and_, or_
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import BaseModel, ActiveMixin


class RequiredChannel(BaseModel, ActiveMixin):
    """
    Модель обязательного канала для подписки
    
    Хранит информацию о каналах, на которые пользователи
    должны подписаться для использования бесплатной версии
    """
    
    __tablename__ = "required_channels"
    
    # Основная информация о канале
    channel_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Telegram ID или username канала (@channel или -100123456789)"
    )
    
    channel_username: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Username канала без @ (channel_name)"
    )
    
    channel_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Отображаемое имя канала"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Описание канала"
    )
    
    # Статус и настройки
    is_required: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Обязателен ли канал для подписки"
    )
    
    check_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Включена ли проверка подписки на канал"
    )
    
    # Приоритет и сортировка
    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        comment="Приоритет отображения (меньше = выше)"
    )
    
    order_index: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Порядок отображения в списке"
    )
    
    # Статистика канала
    subscribers_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Количество подписчиков канала"
    )
    
    last_stats_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Последнее обновление статистики"
    )
    
    # URL и ссылки
    invite_link: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Ссылка-приглашение на канал"
    )
    
    channel_url: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Публичная ссылка на канал (t.me/channel)"
    )
    
    # Настройки проверки
    check_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
        comment="Интервал проверки подписки в минутах"
    )
    
    grace_period_minutes: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
        comment="Льготный период после отписки в минутах"
    )
    
    # Условия применения
    applies_to_user_types: Mapped[List[str]] = mapped_column(
        JSON,
        default=lambda: ["free"],
        nullable=False,
        comment="К каким типам пользователей применяется (free, trial)"
    )
    
    exclude_user_types: Mapped[List[str]] = mapped_column(
        JSON,
        default=lambda: ["premium", "admin"],
        nullable=False,
        comment="Какие типы пользователей исключены из проверки"
    )
    
    # Временные ограничения
    start_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата начала действия требования"
    )
    
    end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата окончания действия требования"
    )
    
    # Сообщения и тексты
    subscription_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Сообщение при требовании подписки"
    )
    
    welcome_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Приветственное сообщение после подписки"
    )
    
    # Настройки уведомлений
    notify_on_subscribe: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Уведомлять ли администрацию о новых подписчиках"
    )
    
    notify_on_unsubscribe: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Уведомлять ли об отписках"
    )
    
    # Аналитика
    stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Статистика подписок и отписок"
    )
    
    # Администрирование
    added_by_admin_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="ID администратора, добавившего канал"
    )
    
    last_modified_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="ID последнего редактора"
    )
    
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Заметки администрации"
    )
    
    # Constraints и индексы
    __table_args__ = (
        CheckConstraint(
            'priority > 0',
            name='check_priority_positive'
        ),
        CheckConstraint(
            'check_interval_minutes > 0',
            name='check_interval_positive'
        ),
        CheckConstraint(
            'grace_period_minutes >= 0',
            name='check_grace_period_positive'
        ),
        CheckConstraint(
            'subscribers_count >= 0',
            name='check_subscribers_positive'
        ),
        # Индексы для оптимизации
        Index('idx_channel_required_active', 'is_required', 'is_active'),
        Index('idx_channel_priority_order', 'priority', 'order_index'),
        Index('idx_channel_check_enabled', 'check_enabled', 'is_active'),
        Index('idx_channel_dates', 'start_date', 'end_date'),
    )
    
    def __repr__(self) -> str:
        return f"<RequiredChannel(id={self.id}, channel_id='{self.channel_id}', name='{self.channel_name}')>"
    
    @property
    def telegram_url(self) -> str:
        """Генерирует Telegram URL канала"""
        if self.channel_username:
            return f"https://t.me/{self.channel_username.lstrip('@')}"
        elif self.channel_url:
            return self.channel_url
        else:
            return f"https://t.me/c/{self.channel_id.lstrip('-100')}"
    
    @property
    def is_currently_active(self) -> bool:
        """Проверяет, активен ли канал в данный момент"""
        if not self.is_active or not self.is_required or not self.check_enabled:
            return False
        
        now = datetime.utcnow()
        
        # Проверяем временные ограничения
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        
        return True
    
    @property
    def needs_stats_update(self) -> bool:
        """Нужно ли обновить статистику канала"""
        if not self.last_stats_update:
            return True
        
        # Обновляем статистику каждые 6 часов
        update_threshold = datetime.utcnow() - timedelta(hours=6)
        return self.last_stats_update < update_threshold
    
    @property
    def formatted_subscribers_count(self) -> str:
        """Отформатированное количество подписчиков"""
        if not self.subscribers_count:
            return "Unknown"
        
        count = self.subscribers_count
        if count >= 1000000:
            return f"{count/1000000:.1f}M"
        elif count >= 1000:
            return f"{count/1000:.1f}K"
        else:
            return str(count)
    
    def applies_to_user_type(self, user_type: str) -> bool:
        """Проверяет, применяется ли требование к типу пользователя"""
        if not self.is_currently_active:
            return False
        
        # Проверяем исключения
        if user_type in (self.exclude_user_types or []):
            return False
        
        # Проверяем применимость
        if self.applies_to_user_types and user_type not in self.applies_to_user_types:
            return False
        
        return True
    
    def update_stats(self, new_subscribers: int = None, new_unsubscribers: int = None):
        """Обновляет статистику канала"""
        if not self.stats:
            self.stats = {
                'total_new_subscribers': 0,
                'total_unsubscribers': 0,
                'daily_stats': {},
                'last_updated': datetime.utcnow().isoformat()
            }
        
        today = datetime.utcnow().date().isoformat()
        
        if new_subscribers:
            self.stats['total_new_subscribers'] += new_subscribers
            daily_stats = self.stats.get('daily_stats', {})
            daily_stats[today] = daily_stats.get(today, {})
            daily_stats[today]['new_subscribers'] = daily_stats[today].get('new_subscribers', 0) + new_subscribers
            self.stats['daily_stats'] = daily_stats
        
        if new_unsubscribers:
            self.stats['total_unsubscribers'] += new_unsubscribers
            daily_stats = self.stats.get('daily_stats', {})
            daily_stats[today] = daily_stats.get(today, {})
            daily_stats[today]['unsubscribers'] = daily_stats[today].get('unsubscribers', 0) + new_unsubscribers
            self.stats['daily_stats'] = daily_stats
        
        self.stats['last_updated'] = datetime.utcnow().isoformat()
    
    def update_subscribers_count(self, count: int):
        """Обновляет количество подписчиков"""
        old_count = self.subscribers_count or 0
        self.subscribers_count = count
        self.last_stats_update = datetime.utcnow()
        
        # Обновляем статистику роста
        if old_count > 0:
            growth = count - old_count
            if not self.stats:
                self.stats = {}
            self.stats['subscriber_growth'] = growth
            self.stats['growth_updated_at'] = datetime.utcnow().isoformat()
    
    def set_schedule(self, start_date: datetime = None, end_date: datetime = None):
        """Устанавливает расписание действия канала"""
        self.start_date = start_date
        self.end_date = end_date
    
    def configure_checking(self, interval_minutes: int = None, grace_period_minutes: int = None):
        """Настраивает параметры проверки"""
        if interval_minutes is not None:
            self.check_interval_minutes = max(1, interval_minutes)
        if grace_period_minutes is not None:
            self.grace_period_minutes = max(0, grace_period_minutes)
    
    def set_user_type_rules(self, applies_to: List[str] = None, excludes: List[str] = None):
        """Устанавливает правила применения к типам пользователей"""
        if applies_to is not None:
            self.applies_to_user_types = applies_to
        if excludes is not None:
            self.exclude_user_types = excludes
    
    def generate_subscription_button_text(self) -> str:
        """Генерирует текст для кнопки подписки"""
        return f"📱 Подписаться на {self.channel_name}"
    
    def generate_status_text(self, is_subscribed: bool) -> str:
        """Генерирует текст статуса подписки"""
        if is_subscribed:
            return f"✅ {self.channel_name}"
        else:
            return f"❌ {self.channel_name}"
    
    @classmethod
    def get_active_channels_for_user_type(cls, session, user_type: str) -> List['RequiredChannel']:
        """Получает активные каналы для типа пользователя"""
        from sqlalchemy import and_
        
        now = datetime.utcnow()
        
        query = session.query(cls).filter(
            and_(
                cls.is_active == True,
                cls.is_required == True,
                cls.check_enabled == True,
                # Проверка временных ограничений
                or_(cls.start_date.is_(None), cls.start_date <= now),
                or_(cls.end_date.is_(None), cls.end_date >= now)
            )
        ).order_by(cls.priority, cls.order_index)
        
        # Фильтруем по типу пользователя в Python (т.к. JSON фильтрация сложна)
        channels = query.all()
        return [ch for ch in channels if ch.applies_to_user_type(user_type)]
    
    @classmethod
    def create_from_channel_info(cls, channel_id: str, channel_name: str, 
                                username: str = None, **kwargs) -> 'RequiredChannel':
        """Создает канал из базовой информации"""
        # Генерируем URL канала
        channel_url = None
        if username:
            channel_url = f"https://t.me/{username.lstrip('@')}"
        
        return cls(
            channel_id=channel_id,
            channel_username=username,
            channel_name=channel_name,
            channel_url=channel_url,
            **kwargs
        )
    
    def to_dict_for_user(self) -> Dict[str, Any]:
        """Представление для пользователя"""
        return {
            'id': self.id,
            'channel_id': self.channel_id,
            'channel_name': self.channel_name,
            'description': self.description,
            'subscribers_count': self.formatted_subscribers_count,
            'telegram_url': self.telegram_url,
            'invite_link': self.invite_link,
            'subscription_message': self.subscription_message,
            'welcome_message': self.welcome_message
        }
    
    def to_dict_for_admin(self) -> Dict[str, Any]:
        """Полное представление для администратора"""
        return {
            'id': self.id,
            'channel_id': self.channel_id,
            'channel_username': self.channel_username,
            'channel_name': self.channel_name,
            'description': self.description,
            'is_required': self.is_required,
            'is_active': self.is_active,
            'check_enabled': self.check_enabled,
            'priority': self.priority,
            'order_index': self.order_index,
            'subscribers_count': self.subscribers_count,
            'formatted_subscribers_count': self.formatted_subscribers_count,
            'last_stats_update': self.last_stats_update.isoformat() if self.last_stats_update else None,
            'telegram_url': self.telegram_url,
            'invite_link': self.invite_link,
            'channel_url': self.channel_url,
            'check_interval_minutes': self.check_interval_minutes,
            'grace_period_minutes': self.grace_period_minutes,
            'applies_to_user_types': self.applies_to_user_types,
            'exclude_user_types': self.exclude_user_types,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'notify_on_subscribe': self.notify_on_subscribe,
            'notify_on_unsubscribe': self.notify_on_unsubscribe,
            'stats': self.stats,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_currently_active': self.is_currently_active
        }