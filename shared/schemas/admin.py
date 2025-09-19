"""
VideoBot Pro - Admin Schemas
Pydantic схемы для администрирования
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator, EmailStr

from .base import BaseSchema, TimestampSchema, IDSchema

class AdminUserSchema(BaseModel):
    """Схема администратора"""
    id: int = Field(description="ID администратора")
    username: str = Field(description="Имя пользователя")
    email: Optional[EmailStr] = Field(description="Email")
    full_name: Optional[str] = Field(description="Полное имя")
    role: str = Field(description="Роль")
    is_active: bool = Field(description="Активен ли аккаунт")
    is_verified: bool = Field(description="Подтвержден ли аккаунт")
    telegram_id: Optional[int] = Field(description="Telegram ID")
    telegram_username: Optional[str] = Field(description="Telegram username")
    last_login_at: Optional[datetime] = Field(description="Последний вход")
    last_activity_at: Optional[datetime] = Field(description="Последняя активность")
    actions_count: int = Field(description="Количество действий")
    created_at: datetime = Field(description="Дата создания")
    
    class Config:
        from_attributes = True

class AdminCreateSchema(BaseModel):
    """Схема создания администратора"""
    username: str = Field(min_length=3, max_length=50, description="Имя пользователя")
    email: Optional[EmailStr] = Field(description="Email")
    password: str = Field(min_length=8, description="Пароль")
    full_name: Optional[str] = Field(max_length=100, description="Полное имя")
    role: str = Field(description="Роль")
    telegram_id: Optional[int] = Field(description="Telegram ID")
    phone: Optional[str] = Field(max_length=20, description="Телефон")
    
    @validator('username')
    def validate_username(cls, v):
        if not v.isalnum():
            raise ValueError('Username must contain only letters and numbers')
        return v.lower()
    
    @validator('role')
    def validate_role(cls, v):
        allowed_roles = ['super_admin', 'admin', 'moderator', 'support', 'viewer']
        if v not in allowed_roles:
            raise ValueError(f'Role must be one of: {allowed_roles}')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v

class AdminUpdateSchema(BaseModel):
    """Схема обновления администратора"""
    email: Optional[EmailStr] = Field(default=None, description="Email")
    full_name: Optional[str] = Field(default=None, max_length=100, description="Полное имя")
    phone: Optional[str] = Field(default=None, max_length=20, description="Телефон")
    telegram_id: Optional[int] = Field(default=None, description="Telegram ID")
    telegram_username: Optional[str] = Field(default=None, description="Telegram username")
    timezone: Optional[str] = Field(default=None, description="Часовой пояс")
    language: Optional[str] = Field(default=None, description="Язык")
    dashboard_settings: Optional[Dict[str, Any]] = Field(default=None, description="Настройки дашборда")
    notification_settings: Optional[Dict[str, Any]] = Field(default=None, description="Настройки уведомлений")

class AdminPasswordChangeSchema(BaseModel):
    """Схема смены пароля"""
    current_password: str = Field(description="Текущий пароль")
    new_password: str = Field(min_length=8, description="Новый пароль")
    confirm_password: str = Field(description="Подтверждение пароля")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v

class AdminRoleChangeSchema(BaseModel):
    """Схема смены роли администратора"""
    new_role: str = Field(description="Новая роль")
    reason: Optional[str] = Field(description="Причина смены роли")
    
    @validator('new_role')
    def validate_role(cls, v):
        allowed_roles = ['super_admin', 'admin', 'moderator', 'support', 'viewer']
        if v not in allowed_roles:
            raise ValueError(f'Role must be one of: {allowed_roles}')
        return v

class BroadcastSchema(BaseModel):
    """Схема рассылки"""
    title: str = Field(max_length=200, description="Заголовок рассылки")
    message_text: str = Field(description="Текст сообщения")
    target_type: str = Field(description="Тип аудитории")
    target_user_ids: Optional[List[int]] = Field(default=None, description="Конкретные пользователи")
    target_filters: Optional[Dict[str, Any]] = Field(default=None, description="Фильтры аудитории")
    scheduled_at: Optional[datetime] = Field(default=None, description="Время отправки")
    media_type: Optional[str] = Field(default=None, description="Тип медиа")
    media_file_id: Optional[str] = Field(default=None, description="ID медиафайла")
    media_caption: Optional[str] = Field(default=None, description="Подпись к медиа")
    inline_keyboard: Optional[Dict[str, Any]] = Field(default=None, description="Inline клавиатура")
    send_rate_per_minute: int = Field(default=30, description="Скорость отправки")
    disable_notification: bool = Field(default=False, description="Без звука")
    protect_content: bool = Field(default=False, description="Защитить контент")
    
    @validator('target_type')
    def validate_target_type(cls, v):
        allowed = ['all_users', 'free_users', 'trial_users', 'premium_users', 'custom', 'specific_users']
        if v not in allowed:
            raise ValueError(f'Target type must be one of: {allowed}')
        return v
    
    @validator('send_rate_per_minute')
    def validate_send_rate(cls, v):
        if v < 1 or v > 100:
            raise ValueError('Send rate must be between 1 and 100 per minute')
        return v

class BroadcastUpdateSchema(BaseModel):
    """Схема обновления рассылки"""
    title: Optional[str] = Field(default=None, max_length=200)
    message_text: Optional[str] = Field(default=None)
    scheduled_at: Optional[datetime] = Field(default=None)
    send_rate_per_minute: Optional[int] = Field(default=None, ge=1, le=100)
    disable_notification: Optional[bool] = Field(default=None)
    protect_content: Optional[bool] = Field(default=None)

class AdminStatsSchema(BaseModel):
    """Схема статистики для администратора"""
    # Основные метрики
    total_users: int = Field(description="Всего пользователей")
    new_users_today: int = Field(description="Новых пользователей сегодня")
    active_users_today: int = Field(description="Активных пользователей сегодня")
    premium_users: int = Field(description="Premium пользователей")
    trial_users: int = Field(description="Trial пользователей")
    banned_users: int = Field(description="Заблокированных пользователей")
    
    # Скачивания
    total_downloads: int = Field(description="Всего скачиваний")
    downloads_today: int = Field(description="Скачиваний сегодня")
    successful_downloads_today: int = Field(description="Успешных скачиваний сегодня")
    failed_downloads_today: int = Field(description="Неудачных скачиваний сегодня")
    
    # Финансы
    total_revenue: float = Field(description="Общая выручка")
    revenue_today: float = Field(description="Выручка сегодня")
    revenue_this_month: float = Field(description="Выручка в этом месяце")
    successful_payments_today: int = Field(description="Успешных платежей сегодня")
    
    # Система
    total_file_size_gb: float = Field(description="Общий размер файлов в ГБ")
    active_tasks: int = Field(description="Активных задач")
    pending_tasks: int = Field(description="Задач в очереди")
    error_rate_percent: float = Field(description="Процент ошибок")
    
    # Тренды
    user_growth_percent: float = Field(description="Рост пользователей в процентах")
    download_growth_percent: float = Field(description="Рост скачиваний в процентах")
    revenue_growth_percent: float = Field(description="Рост выручки в процентах")
    
    # Распределение
    platform_distribution: Dict[str, int] = Field(description="Распределение по платформам")
    user_type_distribution: Dict[str, int] = Field(description="Распределение по типам пользователей")
    
    # Последние активности
    recent_registrations: int = Field(description="Регистраций за последний час")
    recent_downloads: int = Field(description="Скачиваний за последний час")
    recent_payments: int = Field(description="Платежей за последний час")

class AdminActionSchema(BaseModel):
    """Схема действия администратора"""
    action_type: str = Field(description="Тип действия")
    target_id: Optional[int] = Field(description="ID цели действия")
    target_type: Optional[str] = Field(description="Тип цели")
    details: Optional[Dict[str, Any]] = Field(description="Детали действия")
    reason: Optional[str] = Field(description="Причина действия")

class SystemConfigSchema(BaseModel):
    """Схема системной конфигурации"""
    maintenance_mode: bool = Field(description="Режим обслуживания")
    registration_enabled: bool = Field(description="Регистрация включена")
    trial_enabled: bool = Field(description="Trial включен")
    premium_enabled: bool = Field(description="Premium включен")
    required_subs_enabled: bool = Field(description="Обязательные подписки включены")
    batch_processing_enabled: bool = Field(description="Batch обработка включена")
    max_batch_size: int = Field(description="Максимальный размер batch")
    free_daily_limit: int = Field(description="Дневной лимит для free")
    trial_duration_minutes: int = Field(description="Длительность trial в минутах")
    download_timeout_seconds: int = Field(description="Таймаут скачивания")

class ChannelSchema(BaseModel):
    """Схема канала"""
    id: int = Field(description="ID канала")
    channel_id: str = Field(description="Telegram ID канала")
    channel_name: str = Field(description="Название канала")
    channel_username: Optional[str] = Field(description="Username канала")
    is_required: bool = Field(description="Обязателен ли канал")
    is_active: bool = Field(description="Активен ли канал")
    subscribers_count: Optional[int] = Field(description="Количество подписчиков")
    invite_link: Optional[str] = Field(description="Ссылка-приглашение")
    priority: int = Field(description="Приоритет")
    
    class Config:
        from_attributes = True

class ChannelCreateSchema(BaseModel):
    """Схема создания канала"""
    channel_id: str = Field(description="Telegram ID или username канала")
    channel_name: str = Field(max_length=200, description="Название канала")
    description: Optional[str] = Field(default=None, description="Описание")
    invite_link: Optional[str] = Field(default=None, description="Ссылка-приглашение")
    priority: int = Field(default=100, description="Приоритет")
    check_interval_minutes: int = Field(default=5, description="Интервал проверки")
    
    @validator('channel_id')
    def validate_channel_id(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Channel ID cannot be empty')
        # Убираем @ если есть
        if v.startswith('@'):
            v = v[1:]
        return v
    
    @validator('priority')
    def validate_priority(cls, v):
        if v < 1 or v > 1000:
            raise ValueError('Priority must be between 1 and 1000')
        return v

class ChannelUpdateSchema(BaseModel):
    """Схема обновления канала"""
    channel_name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None)
    is_required: Optional[bool] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)
    invite_link: Optional[str] = Field(default=None)
    priority: Optional[int] = Field(default=None, ge=1, le=1000)
    check_interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)

class AdminLoginSchema(BaseModel):
    """Схема входа администратора"""
    username: str = Field(description="Имя пользователя")
    password: str = Field(description="Пароль")
    remember_me: bool = Field(default=False, description="Запомнить меня")
    
    @validator('username')
    def validate_username(cls, v):
        return v.strip().lower()

class AdminTokenSchema(BaseModel):
    """Схема токена администратора"""
    access_token: str = Field(description="Токен доступа")
    refresh_token: str = Field(description="Токен обновления")
    token_type: str = Field(default="bearer", description="Тип токена")
    expires_in: int = Field(description="Время жизни токена в секундах")

class AdminActivitySchema(BaseModel):
    """Схема активности администратора"""
    id: int = Field(description="ID записи")
    admin_id: int = Field(description="ID администратора")
    admin_username: str = Field(description="Имя администратора")
    action_type: str = Field(description="Тип действия")
    target_type: Optional[str] = Field(description="Тип цели")
    target_id: Optional[int] = Field(description="ID цели")
    description: str = Field(description="Описание действия")
    ip_address: Optional[str] = Field(description="IP адрес")
    user_agent: Optional[str] = Field(description="User Agent")
    created_at: datetime = Field(description="Время действия")
    
    class Config:
        from_attributes = True

class SystemHealthSchema(BaseModel):
    """Схема здоровья системы"""
    status: str = Field(description="Общий статус системы")
    database_status: str = Field(description="Статус базы данных")
    redis_status: str = Field(description="Статус Redis")
    storage_status: str = Field(description="Статус хранилища")
    worker_status: str = Field(description="Статус воркеров")
    
    # Метрики производительности
    response_time_ms: float = Field(description="Время ответа в мс")
    memory_usage_percent: float = Field(description="Использование памяти в %")
    cpu_usage_percent: float = Field(description="Использование CPU в %")
    disk_usage_percent: float = Field(description="Использование диска в %")
    
    # Статистика подключений
    active_connections: int = Field(description="Активных подключений")
    database_pool_size: int = Field(description="Размер пула БД")
    redis_connected_clients: int = Field(description="Подключенных клиентов Redis")
    
    # Очереди и задачи
    pending_tasks: int = Field(description="Задач в очереди")
    processing_tasks: int = Field(description="Обрабатываемых задач")
    failed_tasks_last_hour: int = Field(description="Неудачных задач за час")
    
    # Временные метки
    uptime_seconds: int = Field(description="Время работы в секундах")
    last_restart: datetime = Field(description="Время последнего перезапуска")
    last_check: datetime = Field(description="Время последней проверки")

class LogEntrySchema(BaseModel):
    """Схема записи лога"""
    id: int = Field(description="ID записи")
    level: str = Field(description="Уровень лога")
    message: str = Field(description="Сообщение")
    module: str = Field(description="Модуль")
    function: Optional[str] = Field(description="Функция")
    user_id: Optional[int] = Field(description="ID пользователя")
    admin_id: Optional[int] = Field(description="ID администратора")
    extra_data: Optional[Dict[str, Any]] = Field(description="Дополнительные данные")
    created_at: datetime = Field(description="Время создания")
    
    class Config:
        from_attributes = True

class LogQuerySchema(BaseModel):
    """Схема запроса логов"""
    level: Optional[str] = Field(default=None, description="Уровень лога")
    module: Optional[str] = Field(default=None, description="Модуль")
    user_id: Optional[int] = Field(default=None, description="ID пользователя")
    admin_id: Optional[int] = Field(default=None, description="ID администратора")
    date_from: Optional[datetime] = Field(default=None, description="Начальная дата")
    date_to: Optional[datetime] = Field(default=None, description="Конечная дата")
    search: Optional[str] = Field(default=None, description="Поиск по сообщению")
    page: int = Field(default=1, ge=1, description="Номер страницы")
    per_page: int = Field(default=50, ge=1, le=1000, description="Записей на странице")
    
    @validator('level')
    def validate_level(cls, v):
        if v and v not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError('Invalid log level')
        return v