"""
VideoBot Pro - Admin User Model
Модель администраторов системы
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, 
    Text, JSON, Index, CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash, check_password_hash

from .base import BaseModel, SoftDeleteMixin


class AdminRole:
    """Роли администраторов"""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"
    SUPPORT = "support"
    VIEWER = "viewer"
    
    ALL = [SUPER_ADMIN, ADMIN, MODERATOR, SUPPORT, VIEWER]
    
    # Иерархия ролей (высшие включают права низших)
    HIERARCHY = {
        SUPER_ADMIN: 100,
        ADMIN: 80,
        MODERATOR: 60,
        SUPPORT: 40,
        VIEWER: 20
    }


class AdminPermission:
    """Права доступа администраторов"""
    # Управление пользователями
    USER_VIEW = "user_view"
    USER_EDIT = "user_edit"
    USER_BAN = "user_ban"
    USER_PREMIUM = "user_premium"
    USER_DELETE = "user_delete"
    
    # Управление системой
    SYSTEM_CONFIG = "system_config"
    SYSTEM_STATS = "system_stats"
    SYSTEM_LOGS = "system_logs"
    SYSTEM_MAINTENANCE = "system_maintenance"
    
    # Управление каналами
    CHANNEL_VIEW = "channel_view"
    CHANNEL_MANAGE = "channel_manage"
    CHANNEL_DELETE = "channel_delete"
    
    # Управление контентом
    CONTENT_MODERATE = "content_moderate"
    CONTENT_DELETE = "content_delete"
    
    # Рассылки
    BROADCAST_CREATE = "broadcast_create"
    BROADCAST_SEND = "broadcast_send"
    
    # Финансы
    FINANCE_VIEW = "finance_view"
    FINANCE_MANAGE = "finance_manage"
    
    # Администрирование
    ADMIN_MANAGE = "admin_manage"
    
    # Все права
    ALL = [
        USER_VIEW, USER_EDIT, USER_BAN, USER_PREMIUM, USER_DELETE,
        SYSTEM_CONFIG, SYSTEM_STATS, SYSTEM_LOGS, SYSTEM_MAINTENANCE,
        CHANNEL_VIEW, CHANNEL_MANAGE, CHANNEL_DELETE,
        CONTENT_MODERATE, CONTENT_DELETE,
        BROADCAST_CREATE, BROADCAST_SEND,
        FINANCE_VIEW, FINANCE_MANAGE,
        ADMIN_MANAGE
    ]


class AdminUser(BaseModel, SoftDeleteMixin):
    """
    Модель администратора системы
    
    Хранит информацию об администраторах, их ролях,
    правах доступа и активности в системе
    """
    
    __tablename__ = "admin_users"
    
    # Основная информация
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Уникальное имя администратора"
    )
    
    email: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="Email администратора"
    )
    
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Хеш пароля"
    )
    
    # Связь с Telegram (опционально)
    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
        index=True,
        comment="Telegram ID администратора"
    )
    
    telegram_username: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Telegram username"
    )
    
    # Личная информация
    full_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Полное имя администратора"
    )
    
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Номер телефона"
    )
    
    # Роли и права
    role: Mapped[str] = mapped_column(
        String(20),
        default=AdminRole.SUPPORT,
        nullable=False,
        index=True,
        comment="Роль администратора"
    )
    
    permissions: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        comment="Дополнительные права доступа"
    )
    
    # Статус аккаунта
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
        comment="Активен ли аккаунт"
    )
    
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Подтвержден ли аккаунт"
    )
    
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Заблокирован ли аккаунт"
    )
    
    # Безопасность
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество неудачных попыток входа"
    )
    
    last_failed_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время последней неудачной попытки входа"
    )
    
    lockout_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Заблокирован до указанного времени"
    )
    
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Дата последней смены пароля"
    )
    
    two_factor_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Включена ли двухфакторная аутентификация"
    )
    
    two_factor_secret: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Секретный ключ для 2FA"
    )
    
    # Сессии
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время последнего входа"
    )
    
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Время последней активности"
    )
    
    last_login_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP последнего входа"
    )
    
    session_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Количество активных сессий"
    )
    
    # Настройки и предпочтения
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="UTC",
        nullable=False,
        comment="Часовой пояс администратора"
    )
    
    language: Mapped[str] = mapped_column(
        String(10),
        default="en",
        nullable=False,
        comment="Язык интерфейса"
    )
    
    dashboard_settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Настройки дашборда"
    )
    
    notification_settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Настройки уведомлений"
    )
    
    # Аналитика и статистика
    actions_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Общее количество выполненных действий"
    )
    
    last_action_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Тип последнего действия"
    )
    
    stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Статистика активности администратора"
    )
    
    # Администрирование
    created_by_admin_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="ID администратора, создавшего аккаунт"
    )
    
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Заметки о администраторе"
    )
    
    # Relationships (будут добавлены)
    # audit_logs = relationship("AdminAuditLog", back_populates="admin")
    # broadcasts = relationship("BroadcastMessage", back_populates="created_by_admin")
    
    # Constraints и индексы
    __table_args__ = (
        CheckConstraint(
            role.in_(AdminRole.ALL),
            name='check_admin_role'
        ),
        CheckConstraint(
            'failed_login_attempts >= 0',
            name='check_failed_attempts_positive'
        ),
        CheckConstraint(
            'actions_count >= 0',
            name='check_actions_count_positive'
        ),
        CheckConstraint(
            'session_count >= 0',
            name='check_session_count_positive'
        ),
        # Индексы для оптимизации
        Index('idx_admin_active_role', is_active, role),
        Index('idx_admin_last_activity', last_activity_at),
        Index('idx_admin_telegram', telegram_id, is_active),
        Index('idx_admin_lockout', lockout_until, is_active),
    )
    
    def __repr__(self) -> str:
        return f"<AdminUser(id={self.id}, username='{self.username}', role='{self.role}')>"
    
    @property
    def is_super_admin(self) -> bool:
        """Является ли суперадминистратором"""
        return self.role == AdminRole.SUPER_ADMIN
    
    @property
    def is_currently_locked(self) -> bool:
        """Заблокирован ли сейчас аккаунт"""
        if self.is_locked:
            return True
        if self.lockout_until and datetime.utcnow() < self.lockout_until:
            return True
        return False
    
    @property
    def can_login(self) -> bool:
        """Может ли администратор войти в систему"""
        return (
            self.is_active and 
            not self.is_deleted and 
            not self.is_currently_locked
        )
    
    @property
    def role_level(self) -> int:
        """Числовой уровень роли для сравнения"""
        return AdminRole.HIERARCHY.get(self.role, 0)
    
    @property
    def display_name(self) -> str:
        """Отображаемое имя администратора"""
        return self.full_name or self.username
    
    def set_password(self, password: str):
        """Установить новый пароль"""
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()
        self.failed_login_attempts = 0
        self.lockout_until = None
    
    def check_password(self, password: str) -> bool:
        """Проверить пароль"""
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission: str) -> bool:
        """Проверить наличие права"""
        # Суперадмин имеет все права
        if self.is_super_admin:
            return True
        
        # Проверяем прямые права
        if permission in (self.permissions or []):
            return True
        
        # Проверяем права по роли
        role_permissions = self._get_role_permissions()
        return permission in role_permissions
    
    def has_role_level(self, required_level: int) -> bool:
        """Проверить уровень роли"""
        return self.role_level >= required_level
    
    def can_manage_user(self, other_admin: 'AdminUser') -> bool:
        """Может ли управлять другим администратором"""
        if not self.is_super_admin:
            return False
        return self.role_level > other_admin.role_level
    
    def _get_role_permissions(self) -> List[str]:
        """Получить права по роли"""
        role_perms = {
            AdminRole.SUPER_ADMIN: AdminPermission.ALL,
            AdminRole.ADMIN: [
                AdminPermission.USER_VIEW, AdminPermission.USER_EDIT, 
                AdminPermission.USER_BAN, AdminPermission.USER_PREMIUM,
                AdminPermission.SYSTEM_STATS, AdminPermission.SYSTEM_LOGS,
                AdminPermission.CHANNEL_VIEW, AdminPermission.CHANNEL_MANAGE,
                AdminPermission.CONTENT_MODERATE, AdminPermission.CONTENT_DELETE,
                AdminPermission.BROADCAST_CREATE, AdminPermission.BROADCAST_SEND,
                AdminPermission.FINANCE_VIEW
            ],
            AdminRole.MODERATOR: [
                AdminPermission.USER_VIEW, AdminPermission.USER_BAN,
                AdminPermission.CONTENT_MODERATE, AdminPermission.CONTENT_DELETE,
                AdminPermission.CHANNEL_VIEW
            ],
            AdminRole.SUPPORT: [
                AdminPermission.USER_VIEW, AdminPermission.SYSTEM_STATS
            ],
            AdminRole.VIEWER: [
                AdminPermission.USER_VIEW, AdminPermission.SYSTEM_STATS
            ]
        }
        return role_perms.get(self.role, [])
    
    def record_login_attempt(self, success: bool, ip_address: str = None):
        """Записать попытку входа"""
        if success:
            self.last_login_at = datetime.utcnow()
            self.last_activity_at = datetime.utcnow()
            if ip_address:
                self.last_login_ip = ip_address
            self.failed_login_attempts = 0
            self.lockout_until = None
        else:
            self.failed_login_attempts += 1
            self.last_failed_login = datetime.utcnow()
            
            # Блокируем после 5 неудачных попыток
            if self.failed_login_attempts >= 5:
                self.lockout_until = datetime.utcnow() + timedelta(minutes=30)
    
    def update_activity(self):
        """Обновить время последней активности"""
        self.last_activity_at = datetime.utcnow()
    
    def record_action(self, action_type: str, details: Dict[str, Any] = None):
        """Записать выполненное действие"""
        self.actions_count += 1
        self.last_action_type = action_type
        self.update_activity()
        
        # Обновляем статистику
        if not self.stats:
            self.stats = {}
        
        actions_stats = self.stats.get('actions', {})
        actions_stats[action_type] = actions_stats.get(action_type, 0) + 1
        self.stats['actions'] = actions_stats
        self.stats['last_action_at'] = datetime.utcnow().isoformat()
        
        if details:
            self.stats['last_action_details'] = details
    
    def enable_2fa(self, secret: str):
        """Включить двухфакторную аутентификацию"""
        self.two_factor_enabled = True
        self.two_factor_secret = secret
    
    def disable_2fa(self):
        """Отключить двухфакторную аутентификацию"""
        self.two_factor_enabled = False
        self.two_factor_secret = None
    
    def lock_account(self, reason: str = None, duration_minutes: int = None):
        """Заблокировать аккаунт"""
        self.is_locked = True
        if duration_minutes:
            self.lockout_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
        if reason:
            self.notes = f"Locked: {reason}\n{self.notes or ''}"
    
    def unlock_account(self):
        """Разблокировать аккаунт"""
        self.is_locked = False
        self.lockout_until = None
        self.failed_login_attempts = 0
    
    def change_role(self, new_role: str, changed_by_admin_id: int = None):
        """Изменить роль администратора"""
        if new_role not in AdminRole.ALL:
            raise ValueError(f"Invalid role: {new_role}")
        
        old_role = self.role
        self.role = new_role
        
        # Записываем в статистику
        if not self.stats:
            self.stats = {}
        self.stats['role_changes'] = self.stats.get('role_changes', [])
        self.stats['role_changes'].append({
            'from': old_role,
            'to': new_role,
            'changed_at': datetime.utcnow().isoformat(),
            'changed_by': changed_by_admin_id
        })
    
    def get_dashboard_config(self) -> Dict[str, Any]:
        """Получить конфигурацию дашборда"""
        default_config = {
            'theme': 'light',
            'widgets': ['users', 'downloads', 'revenue'],
            'refresh_interval': 30,
            'charts': {
                'users_chart': True,
                'downloads_chart': True,
                'revenue_chart': self.has_permission(AdminPermission.FINANCE_VIEW)
            }
        }
        
        if self.dashboard_settings:
            default_config.update(self.dashboard_settings)
        
        return default_config
    
    def update_dashboard_config(self, config: Dict[str, Any]):
        """Обновить конфигурацию дашборда"""
        if not self.dashboard_settings:
            self.dashboard_settings = {}
        self.dashboard_settings.update(config)
    
    @classmethod
    def create_admin(cls, username: str, password: str, role: str = AdminRole.SUPPORT,
                    email: str = None, telegram_id: int = None, 
                    created_by_admin_id: int = None) -> 'AdminUser':
        """Создать нового администратора"""
        admin = cls(
            username=username,
            email=email,
            telegram_id=telegram_id,
            role=role,
            created_by_admin_id=created_by_admin_id
        )
        admin.set_password(password)
        return admin
    
    def to_dict_safe(self) -> Dict[str, Any]:
        """Безопасное представление (без чувствительных данных)"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'telegram_id': self.telegram_id,
            'telegram_username': self.telegram_username,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'last_activity_at': self.last_activity_at.isoformat() if self.last_activity_at else None,
            'actions_count': self.actions_count,
            'role_level': self.role_level,
            'permissions': self._get_role_permissions() + (self.permissions or []),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }