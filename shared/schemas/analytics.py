"""
VideoBot Pro - Analytics Schemas
Pydantic схемы для аналитики и метрик
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator

class EventSchema(BaseModel):
    """Схема аналитического события"""
    id: int = Field(description="ID события")
    event_type: str = Field(description="Тип события")
    event_category: str = Field(description="Категория события")
    user_id: Optional[int] = Field(description="ID пользователя")
    telegram_user_id: Optional[int] = Field(description="Telegram ID пользователя")
    value: Optional[float] = Field(description="Числовое значение")
    duration_seconds: Optional[int] = Field(description="Длительность в секундах")
    platform: Optional[str] = Field(description="Платформа")
    user_type: Optional[str] = Field(description="Тип пользователя")
    event_data: Optional[Dict[str, Any]] = Field(description="Данные события")
    created_at: datetime = Field(description="Время события")
    
    class Config:
        from_attributes = True

class DailyStatsSchema(BaseModel):
    """Схема ежедневной статистики"""
    stats_date: date = Field(description="Дата статистики")
    new_users: int = Field(description="Новые пользователи")
    active_users: int = Field(description="Активные пользователи")
    total_downloads: int = Field(description="Всего скачиваний")
    successful_downloads: int = Field(description="Успешных скачиваний")
    failed_downloads: int = Field(description="Неудачных скачиваний")
    youtube_downloads: int = Field(description="YouTube скачиваний")
    tiktok_downloads: int = Field(description="TikTok скачиваний")
    instagram_downloads: int = Field(description="Instagram скачиваний")
    revenue_usd: float = Field(description="Выручка в долларах")
    total_payments: int = Field(description="Всего платежей")
    successful_payments: int = Field(description="Успешных платежей")
    total_file_size_mb: float = Field(description="Общий размер файлов в МБ")
    avg_processing_time_seconds: Optional[float] = Field(description="Среднее время обработки")
    error_count: int = Field(description="Количество ошибок")
    
    class Config:
        from_attributes = True

class AnalyticsQuerySchema(BaseModel):
    """Схема запроса аналитики"""
    date_from: Optional[date] = Field(default=None, description="Начальная дата")
    date_to: Optional[date] = Field(default=None, description="Конечная дата")
    event_type: Optional[str] = Field(default=None, description="Тип события")
    event_category: Optional[str] = Field(default=None, description="Категория события")
    user_id: Optional[int] = Field(default=None, description="ID пользователя")
    platform: Optional[str] = Field(default=None, description="Платформа")
    user_type: Optional[str] = Field(default=None, description="Тип пользователя")
    group_by: str = Field(default="date", description="Группировка данных")
    aggregation: str = Field(default="count", description="Тип агрегации")
    limit: int = Field(default=100, ge=1, le=10000, description="Лимит записей")
    
    @validator('group_by')
    def validate_group_by(cls, v):
        allowed = ['date', 'hour', 'platform', 'user_type', 'event_type']
        if v not in allowed:
            raise ValueError(f'Group by must be one of: {allowed}')
        return v
    
    @validator('aggregation')
    def validate_aggregation(cls, v):
        allowed = ['count', 'sum', 'avg', 'min', 'max']
        if v not in allowed:
            raise ValueError(f'Aggregation must be one of: {allowed}')
        return v

class MetricsSchema(BaseModel):
    """Схема метрик"""
    name: str = Field(description="Название метрики")
    value: float = Field(description="Значение метрики")
    unit: Optional[str] = Field(description="Единица измерения")
    change_percent: Optional[float] = Field(description="Изменение в процентах")
    trend: Optional[str] = Field(description="Тренд: up, down, stable")
    period: str = Field(description="Период")
    
    @validator('trend')
    def validate_trend(cls, v):
        if v and v not in ['up', 'down', 'stable']:
            raise ValueError('Trend must be up, down or stable')
        return v

class UserAnalyticsSchema(BaseModel):
    """Схема аналитики пользователей"""
    total_users: int = Field(description="Всего пользователей")
    new_users: int = Field(description="Новые пользователи за период")
    active_users: int = Field(description="Активные пользователи за период")
    premium_users: int = Field(description="Premium пользователей")
    trial_users: int = Field(description="Trial пользователей")
    banned_users: int = Field(description="Заблокированных пользователей")
    
    # Динамика
    user_growth_rate: float = Field(description="Темп роста пользователей")
    churn_rate: float = Field(description="Отток пользователей")
    retention_rate: float = Field(description="Удержание пользователей")
    
    # Распределение
    user_type_distribution: Dict[str, int] = Field(description="Распределение по типам")
    registration_sources: Dict[str, int] = Field(description="Источники регистрации")
    language_distribution: Dict[str, int] = Field(description="Распределение по языкам")
    
    # Активность
    avg_session_duration: float = Field(description="Средняя длительность сессии")
    avg_downloads_per_user: float = Field(description="Среднее количество скачиваний на пользователя")
    most_active_hours: List[int] = Field(description="Самые активные часы")

class DownloadAnalyticsSchema(BaseModel):
    """Схема аналитики скачиваний"""
    total_downloads: int = Field(description="Всего скачиваний")
    successful_downloads: int = Field(description="Успешных скачиваний")
    failed_downloads: int = Field(description="Неудачных скачиваний")
    success_rate: float = Field(description="Процент успеха")
    
    # Платформы
    platform_stats: Dict[str, Dict[str, Any]] = Field(description="Статистика по платформам")
    most_popular_platform: str = Field(description="Самая популярная платформа")
    
    # Качество и форматы
    quality_distribution: Dict[str, int] = Field(description="Распределение по качеству")
    format_distribution: Dict[str, int] = Field(description="Распределение по форматам")
    
    # Размеры и производительность
    total_size_gb: float = Field(description="Общий размер в ГБ")
    avg_file_size_mb: float = Field(description="Средний размер файла в МБ")
    avg_processing_time: float = Field(description="Среднее время обработки")
    
    # Тренды
    daily_downloads: List[Dict[str, Any]] = Field(description="Скачивания по дням")
    hourly_distribution: Dict[int, int] = Field(description="Распределение по часам")
    
    # Ошибки
    error_rate: float = Field(description="Процент ошибок")
    top_errors: List[Dict[str, Any]] = Field(description="Топ ошибок")

class RevenueAnalyticsSchema(BaseModel):
    """Схема аналитики доходов"""
    total_revenue: float = Field(description="Общий доход")
    revenue_growth: float = Field(description="Рост дохода")
    total_payments: int = Field(description="Всего платежей")
    successful_payments: int = Field(description="Успешных платежей")
    payment_success_rate: float = Field(description="Процент успешных платежей")
    
    # Средние значения
    avg_payment_amount: float = Field(description="Средняя сумма платежа")
    avg_revenue_per_user: float = Field(description="Средний доход с пользователя")
    
    # Планы подписки
    subscription_distribution: Dict[str, Dict[str, Any]] = Field(description="Распределение по планам")
    most_popular_plan: str = Field(description="Самый популярный план")
    
    # Конверсия
    trial_to_premium_rate: float = Field(description="Конверсия из trial в premium")
    free_to_premium_rate: float = Field(description="Конверсия из free в premium")
    
    # Тренды
    daily_revenue: List[Dict[str, Any]] = Field(description="Доход по дням")
    monthly_recurring_revenue: float = Field(description="Месячный повторяющийся доход")

class SystemAnalyticsSchema(BaseModel):
    """Схема системной аналитики"""
    total_requests: int = Field(description="Всего запросов")
    successful_requests: int = Field(description="Успешных запросов")
    failed_requests: int = Field(description="Неудачных запросов")
    error_rate: float = Field(description="Процент ошибок")
    
    # Производительность
    avg_response_time: float = Field(description="Среднее время ответа")
    max_response_time: float = Field(description="Максимальное время ответа")
    throughput: float = Field(description="Пропускная способность")
    
    # Ресурсы
    avg_cpu_usage: float = Field(description="Среднее использование CPU")
    avg_memory_usage: float = Field(description="Среднее использование памяти")
    disk_usage: float = Field(description="Использование диска")
    
    # База данных
    db_connection_count: int = Field(description="Количество подключений к БД")
    db_query_time: float = Field(description="Среднее время запроса к БД")
    db_pool_utilization: float = Field(description="Использование пула БД")
    
    # Очереди
    active_tasks: int = Field(description="Активных задач")
    pending_tasks: int = Field(description="Задач в очереди")
    completed_tasks: int = Field(description="Завершенных задач")
    failed_tasks: int = Field(description="Неудачных задач")
    
    # Ошибки
    top_error_types: List[Dict[str, Any]] = Field(description="Топ типов ошибок")
    critical_errors: int = Field(description="Критических ошибок")

class RealtimeMetricsSchema(BaseModel):
    """Схема метрик в реальном времени"""
    timestamp: datetime = Field(description="Время метрики")
    active_users: int = Field(description="Активных пользователей сейчас")
    active_downloads: int = Field(description="Активных скачиваний")
    pending_downloads: int = Field(description="Скачиваний в очереди")
    requests_per_minute: int = Field(description="Запросов в минуту")
    errors_per_minute: int = Field(description="Ошибок в минуту")
    response_time_ms: float = Field(description="Время ответа в мс")
    cpu_usage_percent: float = Field(description="Использование CPU")
    memory_usage_percent: float = Field(description="Использование памяти")
    system_status: str = Field(description="Статус системы")

class AnalyticsReportSchema(BaseModel):
    """Схема аналитического отчета"""
    report_id: str = Field(description="ID отчета")
    title: str = Field(description="Название отчета")
    description: Optional[str] = Field(description="Описание")
    report_type: str = Field(description="Тип отчета")
    period_start: date = Field(description="Начало периода")
    period_end: date = Field(description="Конец периода")
    
    # Данные отчета
    user_analytics: Optional[UserAnalyticsSchema] = Field(description="Аналитика пользователей")
    download_analytics: Optional[DownloadAnalyticsSchema] = Field(description="Аналитика скачиваний")
    revenue_analytics: Optional[RevenueAnalyticsSchema] = Field(description="Аналитика доходов")
    system_analytics: Optional[SystemAnalyticsSchema] = Field(description="Системная аналитика")
    
    # Метаданные
    generated_at: datetime = Field(description="Время генерации")
    generated_by: Optional[str] = Field(description="Кем сгенерирован")
    format: str = Field(description="Формат отчета")
    
    @validator('report_type')
    def validate_report_type(cls, v):
        allowed = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly', 'custom']
        if v not in allowed:
            raise ValueError(f'Report type must be one of: {allowed}')
        return v

class KPISchema(BaseModel):
    """Схема ключевых показателей эффективности"""
    name: str = Field(description="Название KPI")
    value: float = Field(description="Текущее значение")
    target: Optional[float] = Field(description="Целевое значение")
    previous_value: Optional[float] = Field(description="Предыдущее значение")
    change_percent: Optional[float] = Field(description="Изменение в процентах")
    trend: str = Field(description="Тренд")
    status: str = Field(description="Статус достижения цели")
    unit: Optional[str] = Field(description="Единица измерения")
    description: Optional[str] = Field(description="Описание KPI")
    
    @validator('trend')
    def validate_trend(cls, v):
        allowed = ['up', 'down', 'stable', 'unknown']
        if v not in allowed:
            raise ValueError(f'Trend must be one of: {allowed}')
        return v
    
    @validator('status')
    def validate_status(cls, v):
        allowed = ['achieved', 'on_track', 'at_risk', 'missed', 'unknown']
        if v not in allowed:
            raise ValueError(f'Status must be one of: {allowed}')
        return v

class DashboardSchema(BaseModel):
    """Схема данных дашборда"""
    overview: Dict[str, Any] = Field(description="Обзор")
    kpis: List[KPISchema] = Field(description="Ключевые показатели")
    charts_data: Dict[str, Any] = Field(description="Данные для графиков")
    recent_activity: List[Dict[str, Any]] = Field(description="Недавняя активность")
    alerts: List[Dict[str, Any]] = Field(description="Уведомления и алерты")
    system_health: Dict[str, Any] = Field(description="Здоровье системы")
    last_updated: datetime = Field(description="Время последнего обновления")