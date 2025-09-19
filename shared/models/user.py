"""
VideoBot Pro - User Model
Модель пользователя системы
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    BigInteger, String, Boolean, DateTime, Integer, 
    Text, JSON, Index, CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import BaseModel, SoftDeleteMixin, UserType


class User(BaseModel, SoftDeleteMixin):
    """
    Модель пользователя Telegram бота
    
    Хранит всю информацию о пользователе, его настройках,
    подписках, лимитах и статистике использования
    """
    
    __tablename__ = "users"

    # Основная информация пользователя
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
        comment="Telegram ID пользователя"
    )
    
    username: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Telegram username (без @)"
    )
    
    first_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Имя пользователя из Telegram"
    )
    
    last_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Фамилия пользователя из Telegram"
    )
    
    language_code: Mapped[Optional[str]] = mapped_column(
        String(10),
        default="en",
        comment="Код языка пользователя"
    )
    
    # Тип и статус пользователя
    user_type: Mapped[str] = mapped_column(
        String(20),
        default=UserType.FREE,
        nullable=False,
        index=True,
        comment="Тип пользователя: free, trial, premium, admin"
    )
    
    is_banned: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Заблокирован ли пользователь"
    )
    
    ban_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Причина блокировки"
    )
    
    banned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата и время блокировки"
    )
    
    banned_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Блокировка до указанной даты (для временных банов)"
    )
    
    # Подписка Premium
    is_premium: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Есть ли у пользователя Premium подписка"
    )
    
    premium_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата начала Premium подписки"
    )
    
    premium_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Дата окончания Premium подписки"
    )
    
    premium_auto_renew: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Автопродление Premium подписки"
    )
    
    # Пробный период
    trial_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата начала пробного периода"
    )
    
    trial_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Дата окончания пробного периода"
    )
    
    trial_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Использовал ли пользователь пробный период"
    )
    
    # Лимиты и использование
    downloads_today: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество скачиваний сегодня"
    )
    
    downloads_total: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Общее количество скачиваний"
    )
    
    last_download_reset: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Последний сброс дневного лимита"
    )
    
    # Подписки на каналы
    subscribed_channels: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        default=list,
        comment="Список подписанных каналов (channel_id)"
    )
    
    last_subscription_check: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Последняя проверка подписок"
    )
    
    subscription_check_passed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Прошел ли проверку подписок"
    )
    
    # Настройки и предпочтения
    notification_settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Настройки уведомлений"
    )
    
    download_preferences: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Предпочтения скачивания (качество, формат)"
    )
    
    ui_language: Mapped[str] = mapped_column(
        String(10),
        default="ru",
        comment="Язык интерфейса бота"
    )
    
    timezone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Часовой пояс пользователя"
    )
    
    # Активность
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Последняя активность пользователя"
    )
    
    last_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="ID последнего сообщения пользователя"
    )
    
    session_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Количество сессий пользователя"
    )
    
    # Реферальная система
    referrer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram ID пользователя, который пригласил"
    )
    
    referral_code: Mapped[Optional[str]] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
        index=True,
        comment="Уникальный реферальный код пользователя"
    )
    
    referrals_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Количество приглашенных пользователей"
    )
    
    # Статистика использования
    stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Статистика использования (платформы, размеры файлов и т.д.)"
    )
    
    # Метаданные
    registration_source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Источник регистрации (start, referral, deep_link)"
    )
    
    device_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Информация об устройстве пользователя"
    )
    
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Заметки администрации"
    )

    downloads: Mapped[list["DownloadTask"]] = relationship(
        "DownloadTask", back_populates="user"
    )

    # Relationships (будут добавлены в других моделях)
    download_batches = relationship("DownloadBatch", back_populates="user")
    download_tasks = relationship("DownloadTask", back_populates="user")


    payments = relationship("Payment", back_populates="user")
    analytics_events = relationship("AnalyticsEvent", back_populates="user")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            user_type.in_(UserType.ALL),
            name='check_user_type'
        ),
        CheckConstraint(
            'downloads_today >= 0',
            name='check_downloads_today_positive'
        ),
        CheckConstraint(
            'downloads_total >= 0',
            name='check_downloads_total_positive'
        ),
        CheckConstraint(
            'referrals_count >= 0',
            name='check_referrals_count_positive'
        ),
        # Индексы для оптимизации запросов
        Index('idx_user_telegram_active', telegram_id, last_active_at),
        Index('idx_user_premium_expires', is_premium, premium_expires_at),
        Index('idx_user_trial_expires', trial_expires_at),
        Index('idx_user_banned_status', is_banned, banned_until),
        Index('idx_user_type_active', user_type, last_active_at),
    )
    
    def __repr__(self) -> str:
        return f"<User(telegram_id={self.telegram_id}, username='{self.username}', type='{self.user_type}')>"
    
    @property
    def full_name(self) -> str:
        """Полное имя пользователя"""
        parts = [self.first_name, self.last_name]
        return " ".join([p for p in parts if p])
    
    @property
    def display_name(self) -> str:
        """Отображаемое имя (имя или username)"""
        return self.full_name or f"@{self.username}" if self.username else f"User {self.telegram_id}"
    
    @property
    def is_trial_active(self) -> bool:
        """Активен ли пробный период"""
        if not self.trial_expires_at:
            return False
        return datetime.utcnow() < self.trial_expires_at
    
    @property
    def is_premium_active(self) -> bool:
        """Активна ли Premium подписка"""
        if not self.is_premium or not self.premium_expires_at:
            return False
        return datetime.utcnow() < self.premium_expires_at
    
    @property
    def is_premium_expired(self) -> bool:
        """Истекла ли Premium подписка"""
        if not self.premium_expires_at:
            return False
        return datetime.utcnow() > self.premium_expires_at
    
    @property
    def current_user_type(self) -> str:
        """Текущий активный тип пользователя с учетом времени"""
        # Проверяем временную блокировку
        if self.is_temp_banned:
            return "banned"
        
        # Админы всегда админы
        if self.user_type == UserType.ADMIN:
            return UserType.ADMIN
            
        # Проверяем активный пробный период
        if self.is_trial_active:
            return UserType.TRIAL
            
        # Проверяем активную Premium подписку
        if self.is_premium_active:
            return UserType.PREMIUM
            
        # По умолчанию - бесплатный
        return UserType.FREE
    
    @property
    def is_temp_banned(self) -> bool:
        """Находится ли в временной блокировке"""
        if not self.is_banned or not self.banned_until:
            return self.is_banned
        return datetime.utcnow() < self.banned_until
    
    @property
    def can_download(self) -> bool:
        """Может ли пользователь скачивать файлы"""
        return not self.is_banned and not self.is_deleted and not self.is_temp_banned
    
    @property
    def needs_subscription_check(self) -> bool:
        """Нужна ли проверка подписок"""
        if self.current_user_type in [UserType.PREMIUM, UserType.ADMIN]:
            return False
            
        # Проверяем, давно ли была последняя проверка
        if not self.last_subscription_check:
            return True
            
        # Проверяем каждые 5 минут для активных пользователей
        time_threshold = datetime.utcnow() - timedelta(minutes=5)
        return self.last_subscription_check < time_threshold
    
    def get_daily_limit(self) -> int:
        """Получить дневной лимит скачиваний"""
        user_type = self.current_user_type
        from ..config.settings import settings
        return settings.get_daily_limit(user_type)
    
    def get_max_file_size_mb(self) -> int:
        """Получить максимальный размер файла в МБ"""
        user_type = self.current_user_type
        from ..config.settings import settings
        return settings.get_max_file_size_mb(user_type)
    
    def can_download_today(self) -> bool:
        """Может ли скачивать сегодня (не превышен лимит)"""
        if not self.can_download:
            return False
            
        daily_limit = self.get_daily_limit()
        if daily_limit >= 999:  # Практически безлимитный
            return True
            
        # Сбрасываем счетчик если прошли сутки
        if self.should_reset_daily_counter():
            self.reset_daily_downloads()
            
        return self.downloads_today < daily_limit
    
    def should_reset_daily_counter(self) -> bool:
        """Нужно ли сбросить дневной счетчик"""
        if not self.last_download_reset:
            return True
            
        # Сброс в полночь UTC
        today = datetime.utcnow().date()
        last_reset_date = self.last_download_reset.date()
        
        return today > last_reset_date
    
    def reset_daily_downloads(self):
        """Сбросить дневной счетчик скачиваний"""
        self.downloads_today = 0
        self.last_download_reset = datetime.utcnow()
    
    def increment_downloads(self, count: int = 1):
        """Увеличить счетчик скачиваний"""
        if self.should_reset_daily_counter():
            self.reset_daily_downloads()
            
        self.downloads_today += count
        self.downloads_total += count
    
    def start_trial(self, duration_minutes: int = 60):
        """Запустить пробный период"""
        if self.trial_used:
            raise ValueError("Trial period already used")
            
        self.trial_started_at = datetime.utcnow()
        self.trial_expires_at = self.trial_started_at + timedelta(minutes=duration_minutes)
        self.trial_used = True
        self.user_type = UserType.TRIAL
    
    def activate_premium(self, duration_days: int = 30):
        """Активировать Premium подписку"""
        now = datetime.utcnow()
        
        # Если уже есть активная подписка, продлеваем
        if self.is_premium_active:
            self.premium_expires_at += timedelta(days=duration_days)
        else:
            self.premium_started_at = now
            self.premium_expires_at = now + timedelta(days=duration_days)
            
        self.is_premium = True
        self.user_type = UserType.PREMIUM
    
    def deactivate_premium(self):
        """Деактивировать Premium подписку"""
        self.is_premium = False
        self.premium_expires_at = datetime.utcnow()
        self.premium_auto_renew = False
        self.user_type = UserType.FREE
    
    def ban_user(self, reason: str, duration_days: Optional[int] = None):
        """Заблокировать пользователя"""
        self.is_banned = True
        self.ban_reason = reason
        self.banned_at = datetime.utcnow()
        
        if duration_days:
            self.banned_until = self.banned_at + timedelta(days=duration_days)
    
    def unban_user(self):
        """Разблокировать пользователя"""
        self.is_banned = False
        self.ban_reason = None
        self.banned_at = None
        self.banned_until = None
    
    def update_activity(self):
        """Обновить время последней активности"""
        self.last_active_at = datetime.utcnow()
    
    def add_subscription_check(self, channels: List[str]):
        """Добавить результат проверки подписок"""
        self.subscribed_channels = channels
        self.last_subscription_check = datetime.utcnow()
        self.subscription_check_passed = True
    
    def update_stats(self, platform: str, file_size_mb: float, duration_seconds: int = None):
        """Обновить статистику использования"""
        if not self.stats:
            self.stats = {}
            
        # Статистика по платформам
        platforms = self.stats.get('platforms', {})
        platforms[platform] = platforms.get(platform, 0) + 1
        
        # Общий размер скачанных файлов
        total_size = self.stats.get('total_size_mb', 0)
        total_size += file_size_mb
        
        # Обновляем статистику
        self.stats.update({
            'platforms': platforms,
            'total_size_mb': total_size,
            'last_platform': platform,
            'updated_at': datetime.utcnow().isoformat()
        })
    
    def to_dict_safe(self) -> Dict[str, Any]:
        """Безопасная конвертация в словарь (без чувствительных данных)"""
        exclude = {'device_info', 'notes'}
        return self.to_dict(exclude=exclude)