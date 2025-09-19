"""
VideoBot Pro - User Schemas
Pydantic схемы для пользователей
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator

class UserPreferencesSchema(BaseModel):
    """Схема пользовательских предпочтений"""
    quality_mode: str = Field(default="auto", description="Режим качества: auto, max, manual")
    default_quality: Optional[str] = Field(default=None, description="Качество по умолчанию")
    format_preference: str = Field(default="mp4", description="Предпочитаемый формат")
    notification_downloads: bool = Field(default=True, description="Уведомления о скачиваниях")
    notification_system: bool = Field(default=True, description="Системные уведомления")
    auto_batch_threshold: int = Field(default=5, description="Порог для автоматического batch")
    
    @validator('quality_mode')
    def validate_quality_mode(cls, v):
        allowed = ['auto', 'max', 'manual']
        if v not in allowed:
            raise ValueError(f'Quality mode must be one of: {allowed}')
        return v

class UserStatsSchema(BaseModel):
    """Схема статистики пользователя"""
    downloads_today: int = Field(description="Скачиваний сегодня")
    downloads_total: int = Field(description="Всего скачиваний")
    downloads_successful: int = Field(description="Успешных скачиваний")
    downloads_failed: int = Field(description="Неудачных скачиваний")
    total_size_mb: float = Field(description="Общий размер скачанных файлов в МБ")
    favorite_platform: Optional[str] = Field(description="Любимая платформа")
    avg_file_size_mb: float = Field(description="Средний размер файла")
    first_download: Optional[datetime] = Field(description="Дата первого скачивания")
    last_download: Optional[datetime] = Field(description="Дата последнего скачивания")

class UserSchema(BaseModel):
    """Базовая схема пользователя"""
    id: int = Field(description="ID пользователя")
    telegram_id: int = Field(description="Telegram ID")
    username: Optional[str] = Field(description="Telegram username")
    first_name: Optional[str] = Field(description="Имя")
    last_name: Optional[str] = Field(description="Фамилия")
    language_code: Optional[str] = Field(description="Код языка")
    user_type: str = Field(description="Тип пользователя")
    is_premium: bool = Field(description="Premium статус")
    is_trial_active: bool = Field(description="Активен ли trial")
    is_banned: bool = Field(description="Заблокирован ли")
    downloads_today: int = Field(description="Скачиваний сегодня")
    downloads_total: int = Field(description="Всего скачиваний")
    daily_limit: int = Field(description="Дневной лимит")
    premium_expires_at: Optional[datetime] = Field(description="Срок окончания Premium")
    trial_expires_at: Optional[datetime] = Field(description="Срок окончания Trial")
    last_active_at: Optional[datetime] = Field(description="Последняя активность")
    created_at: datetime = Field(description="Дата регистрации")
    
    class Config:
        from_attributes = True

class UserCreateSchema(BaseModel):
    """Схема для создания пользователя"""
    telegram_id: int = Field(description="Telegram ID")
    username: Optional[str] = Field(default=None, max_length=50)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    language_code: Optional[str] = Field(default="en", max_length=10)
    referrer_id: Optional[int] = Field(default=None, description="ID пригласившего")
    registration_source: Optional[str] = Field(default="start", max_length=50)
    
    @validator('telegram_id')
    def validate_telegram_id(cls, v):
        if v <= 0:
            raise ValueError('Telegram ID must be positive')
        return v

class UserUpdateSchema(BaseModel):
    """Схема для обновления пользователя"""
    username: Optional[str] = Field(default=None, max_length=50)
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    language_code: Optional[str] = Field(default=None, max_length=10)
    ui_language: Optional[str] = Field(default=None, max_length=10)
    timezone: Optional[str] = Field(default=None, max_length=50)
    notification_settings: Optional[Dict[str, Any]] = Field(default=None)
    download_preferences: Optional[UserPreferencesSchema] = Field(default=None)
    
class UserDetailedSchema(UserSchema):
    """Детальная схема пользователя"""
    ban_reason: Optional[str] = Field(description="Причина блокировки")
    banned_at: Optional[datetime] = Field(description="Дата блокировки")
    banned_until: Optional[datetime] = Field(description="Блокировка до")
    premium_started_at: Optional[datetime] = Field(description="Начало Premium")
    premium_auto_renew: bool = Field(description="Автопродление Premium")
    trial_started_at: Optional[datetime] = Field(description="Начало Trial")
    trial_used: bool = Field(description="Использован ли Trial")
    referrer_id: Optional[int] = Field(description="ID пригласившего")
    referral_code: Optional[str] = Field(description="Реферальный код")
    referrals_count: int = Field(description="Количество рефералов")
    subscription_check_passed: bool = Field(description="Прошел проверку подписок")
    last_subscription_check: Optional[datetime] = Field(description="Последняя проверка подписок")
    subscribed_channels: Optional[List[str]] = Field(description="Подписанные каналы")
    download_preferences: Optional[Dict[str, Any]] = Field(description="Настройки скачивания")
    notification_settings: Optional[Dict[str, Any]] = Field(description="Настройки уведомлений")
    stats: Optional[Dict[str, Any]] = Field(description="Статистика")
    notes: Optional[str] = Field(description="Заметки администрации")

class UserBanSchema(BaseModel):
    """Схема для блокировки пользователя"""
    reason: str = Field(description="Причина блокировки")
    duration_days: Optional[int] = Field(default=None, description="Длительность в днях")
    
    @validator('reason')
    def validate_reason(cls, v):
        if len(v.strip()) < 3:
            raise ValueError('Ban reason must be at least 3 characters')
        return v.strip()

class UserPremiumSchema(BaseModel):
    """Схема для выдачи Premium"""
    duration_days: int = Field(description="Длительность в днях")
    auto_renew: bool = Field(default=False, description="Автопродление")
    
    @validator('duration_days')
    def validate_duration(cls, v):
        if v <= 0 or v > 3650:  # Максимум 10 лет
            raise ValueError('Duration must be between 1 and 3650 days')
        return v

class UserTrialSchema(BaseModel):
    """Схема для выдачи Trial"""
    duration_minutes: int = Field(default=60, description="Длительность в минутах")
    
    @validator('duration_minutes')
    def validate_duration(cls, v):
        if v <= 0 or v > 10080:  # Максимум неделя
            raise ValueError('Duration must be between 1 and 10080 minutes')
        return v

class UserListSchema(BaseModel):
    """Схема для списка пользователей"""
    users: List[UserSchema]
    total: int = Field(description="Общее количество")
    page: int = Field(description="Номер страницы")
    pages: int = Field(description="Всего страниц")
    per_page: int = Field(description="Пользователей на странице")

class UserSearchSchema(BaseModel):
    """Схема для поиска пользователей"""
    query: Optional[str] = Field(default=None, description="Поисковый запрос")
    user_type: Optional[str] = Field(default=None, description="Тип пользователя")
    is_banned: Optional[bool] = Field(default=None, description="Статус блокировки")
    is_premium: Optional[bool] = Field(default=None, description="Premium статус")
    registration_from: Optional[datetime] = Field(default=None, description="Зарегистрирован после")
    registration_to: Optional[datetime] = Field(default=None, description="Зарегистрирован до")
    last_active_from: Optional[datetime] = Field(default=None, description="Активен после")
    last_active_to: Optional[datetime] = Field(default=None, description="Активен до")
    min_downloads: Optional[int] = Field(default=None, description="Минимум скачиваний")
    max_downloads: Optional[int] = Field(default=None, description="Максимум скачиваний")
    page: int = Field(default=1, ge=1, description="Номер страницы")
    per_page: int = Field(default=50, ge=1, le=1000, description="Элементов на странице")
    sort_by: str = Field(default="created_at", description="Поле сортировки")
    sort_order: str = Field(default="desc", description="Порядок сортировки")
    
    @validator('user_type')
    def validate_user_type(cls, v):
        if v and v not in ['free', 'trial', 'premium', 'admin']:
            raise ValueError('Invalid user type')
        return v
    
    @validator('sort_by')
    def validate_sort_by(cls, v):
        allowed = ['created_at', 'last_active_at', 'downloads_total', 'username', 'telegram_id']
        if v not in allowed:
            raise ValueError(f'Sort field must be one of: {allowed}')
        return v
    
    @validator('sort_order')
    def validate_sort_order(cls, v):
        if v not in ['asc', 'desc']:
            raise ValueError('Sort order must be asc or desc')
        return v