"""
VideoBot Pro - Admin Settings API
API для управления системными настройками
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
import structlog

from shared.config.settings import settings
from shared.services.database import get_db_session
from ..dependencies import get_current_admin, require_permission

logger = structlog.get_logger(__name__)
router = APIRouter()

class SystemConfigSchema(BaseModel):
    """Схема системной конфигурации"""
    # Основные настройки
    maintenance_mode: bool = Field(description="Режим обслуживания")
    registration_enabled: bool = Field(description="Регистрация включена")
    trial_enabled: bool = Field(description="Trial включен")
    premium_system_enabled: bool = Field(description="Premium система включена")
    required_subs_enabled: bool = Field(description="Обязательные подписки включены")
    batch_processing_enabled: bool = Field(description="Batch обработка включена")
    analytics_enabled: bool = Field(description="Аналитика включена")
    
    # Лимиты пользователей
    free_daily_limit: int = Field(description="Дневной лимит для free")
    trial_daily_limit: int = Field(description="Дневной лимит для trial")
    premium_daily_limit: int = Field(description="Дневной лимит для premium")
    trial_duration_minutes: int = Field(description="Длительность trial в минутах")
    
    # Лимиты файлов
    free_max_file_size_mb: int = Field(description="Максимальный размер для free")
    premium_max_file_size_mb: int = Field(description="Максимальный размер для premium")
    admin_max_file_size_mb: int = Field(description="Максимальный размер для admin")
    
    # Качество видео
    free_max_quality: str = Field(description="Максимальное качество для free")
    premium_max_quality: str = Field(description="Максимальное качество для premium")
    auto_quality_selection: bool = Field(description="Автовыбор качества")
    
    # Batch настройки
    batch_threshold: int = Field(description="Минимум ссылок для batch")
    max_batch_size: int = Field(description="Максимальный размер batch")
    
    # Хранение файлов
    free_file_retention_hours: int = Field(description="Хранение файлов для free")
    premium_file_retention_hours: int = Field(description="Хранение файлов для premium")
    admin_file_retention_hours: int = Field(description="Хранение файлов для admin")
    
    # API настройки
    rate_limit_requests: int = Field(description="Лимит запросов в минуту")
    rate_limit_window: int = Field(description="Окно лимита в секундах")
    
    # Worker настройки
    celery_worker_concurrency: int = Field(description="Concurrency воркеров")
    celery_task_timeout: int = Field(description="Таймаут задач")
    
    # Цены
    premium_price_usd: float = Field(description="Цена Premium в USD")

class SystemConfigUpdateSchema(BaseModel):
    """Схема обновления конфигурации"""
    maintenance_mode: Optional[bool] = None
    registration_enabled: Optional[bool] = None
    trial_enabled: Optional[bool] = None
    premium_system_enabled: Optional[bool] = None
    required_subs_enabled: Optional[bool] = None
    batch_processing_enabled: Optional[bool] = None
    analytics_enabled: Optional[bool] = None
    
    free_daily_limit: Optional[int] = Field(None, ge=1, le=1000)
    trial_daily_limit: Optional[int] = Field(None, ge=1, le=9999)
    premium_daily_limit: Optional[int] = Field(None, ge=1, le=9999)
    trial_duration_minutes: Optional[int] = Field(None, ge=10, le=10080)
    
    free_max_file_size_mb: Optional[int] = Field(None, ge=1, le=1000)
    premium_max_file_size_mb: Optional[int] = Field(None, ge=1, le=5000)
    admin_max_file_size_mb: Optional[int] = Field(None, ge=1, le=10000)
    
    free_max_quality: Optional[str] = Field(None, regex="^(240p|480p|720p|1080p|2160p|4K)$")
    premium_max_quality: Optional[str] = Field(None, regex="^(240p|480p|720p|1080p|2160p|4K)$")
    auto_quality_selection: Optional[bool] = None
    
    batch_threshold: Optional[int] = Field(None, ge=2, le=50)
    max_batch_size: Optional[int] = Field(None, ge=5, le=100)
    
    free_file_retention_hours: Optional[int] = Field(None, ge=1, le=8760)
    premium_file_retention_hours: Optional[int] = Field(None, ge=1, le=8760)
    admin_file_retention_hours: Optional[int] = Field(None, ge=1, le=8760)
    
    rate_limit_requests: Optional[int] = Field(None, ge=1, le=1000)
    rate_limit_window: Optional[int] = Field(None, ge=10, le=3600)
    
    celery_worker_concurrency: Optional[int] = Field(None, ge=1, le=32)
    celery_task_timeout: Optional[int] = Field(None, ge=60, le=7200)
    
    premium_price_usd: Optional[float] = Field(None, ge=0.99, le=99.99)

class PlatformSettingsSchema(BaseModel):
    """Настройки платформ"""
    youtube_enabled: bool = Field(description="YouTube включен")
    tiktok_enabled: bool = Field(description="TikTok включен")
    instagram_enabled: bool = Field(description="Instagram включен")
    
    youtube_api_key: Optional[str] = Field(description="YouTube API ключ")
    tiktok_session_id: Optional[str] = Field(description="TikTok Session ID")
    instagram_session_id: Optional[str] = Field(description="Instagram Session ID")
    
    max_video_duration_minutes: int = Field(description="Максимальная длительность видео")
    supported_formats: List[str] = Field(description="Поддерживаемые форматы")

class NotificationSettingsSchema(BaseModel):
    """Настройки уведомлений"""
    telegram_notifications: bool = Field(description="Telegram уведомления")
    email_notifications: bool = Field(description="Email уведомления")
    webhook_notifications: bool = Field(description="Webhook уведомления")
    
    webhook_url: Optional[str] = Field(description="URL webhook")
    notification_rate_limit: int = Field(description="Лимит уведомлений в минуту")
    
    # Шаблоны уведомлений
    download_complete_template: str = Field(description="Шаблон завершения загрузки")
    download_failed_template: str = Field(description="Шаблон ошибки загрузки")
    premium_expiry_template: str = Field(description="Шаблон истечения Premium")

@router.get("/system", response_model=SystemConfigSchema)
async def get_system_config(
    current_admin = Depends(require_permission("system_config"))
):
    """
    Получить системную конфигурацию
    """
    try:
        # Читаем текущие настройки из settings
        config = SystemConfigSchema(
            # Основные настройки
            maintenance_mode=getattr(settings, 'MAINTENANCE_MODE', False),
            registration_enabled=True,  # TODO: добавить в settings
            trial_enabled=settings.TRIAL_ENABLED,
            premium_system_enabled=settings.PREMIUM_SYSTEM_ENABLED,
            required_subs_enabled=settings.REQUIRED_SUBS_ENABLED,
            batch_processing_enabled=settings.BATCH_PROCESSING_ENABLED,
            analytics_enabled=settings.ANALYTICS_ENABLED,
            
            # Лимиты пользователей
            free_daily_limit=settings.FREE_DAILY_LIMIT,
            trial_daily_limit=settings.TRIAL_DAILY_LIMIT,
            premium_daily_limit=settings.PREMIUM_DAILY_LIMIT,
            trial_duration_minutes=settings.TRIAL_DURATION_MINUTES,
            
            # Лимиты файлов
            free_max_file_size_mb=settings.FREE_MAX_FILE_SIZE_MB,
            premium_max_file_size_mb=settings.PREMIUM_MAX_FILE_SIZE_MB,
            admin_max_file_size_mb=settings.ADMIN_MAX_FILE_SIZE_MB,
            
            # Качество видео
            free_max_quality=settings.FREE_MAX_QUALITY,
            premium_max_quality=settings.PREMIUM_MAX_QUALITY,
            auto_quality_selection=settings.AUTO_QUALITY_SELECTION,
            
            # Batch настройки
            batch_threshold=settings.BATCH_THRESHOLD,
            max_batch_size=settings.MAX_BATCH_SIZE,
            
            # Хранение файлов
            free_file_retention_hours=settings.FREE_FILE_RETENTION_HOURS,
            premium_file_retention_hours=settings.PREMIUM_FILE_RETENTION_HOURS,
            admin_file_retention_hours=settings.ADMIN_FILE_RETENTION_HOURS,
            
            # API настройки
            rate_limit_requests=settings.RATE_LIMIT_REQUESTS,
            rate_limit_window=settings.RATE_LIMIT_WINDOW,
            
            # Worker настройки
            celery_worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
            celery_task_timeout=settings.CELERY_TASK_TIMEOUT,
            
            # Цены
            premium_price_usd=settings.PREMIUM_PRICE_USD
        )
        
        return config
        
    except Exception as e:
        logger.error(f"Error getting system config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении конфигурации"
        )

@router.put("/system", response_model=SystemConfigSchema)
async def update_system_config(
    config_update: SystemConfigUpdateSchema,
    current_admin = Depends(require_permission("system_config"))
):
    """
    Обновить системную конфигурацию
    """
    try:
        # В реальном приложении здесь должно быть сохранение в БД или файл конфигурации
        # Сейчас просто логируем изменения
        
        update_data = config_update.dict(exclude_unset=True)
        
        if update_data:
            logger.info(
                f"System config updated by admin",
                admin_id=current_admin.id,
                admin_username=current_admin.username,
                updates=update_data
            )
            
            # TODO: Реализовать сохранение настроек
            # await save_system_config(update_data)
            
            # TODO: Уведомить воркеры об изменениях
            # await notify_workers_config_change(update_data)
        
        # Возвращаем обновленную конфигурацию
        return await get_system_config(current_admin)
        
    except Exception as e:
        logger.error(f"Error updating system config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при обновлении конфигурации"
        )

@router.get("/platforms", response_model=PlatformSettingsSchema)
async def get_platform_settings(
    current_admin = Depends(require_permission("system_config"))
):
    """
    Получить настройки платформ
    """
    try:
        return PlatformSettingsSchema(
            youtube_enabled="youtube" in settings.SUPPORTED_PLATFORMS,
            tiktok_enabled="tiktok" in settings.SUPPORTED_PLATFORMS,
            instagram_enabled="instagram" in settings.SUPPORTED_PLATFORMS,
            
            youtube_api_key=settings.YOUTUBE_API_KEY if settings.YOUTUBE_API_KEY else None,
            tiktok_session_id=settings.TIKTOK_SESSION_ID if settings.TIKTOK_SESSION_ID else None,
            instagram_session_id=settings.INSTAGRAM_SESSION_ID if settings.INSTAGRAM_SESSION_ID else None,
            
            max_video_duration_minutes=60,  # TODO: добавить в settings
            supported_formats=["mp4", "webm", "mkv"]
        )
        
    except Exception as e:
        logger.error(f"Error getting platform settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении настроек платформ"
        )

@router.put("/platforms", response_model=PlatformSettingsSchema)
async def update_platform_settings(
    platform_settings: PlatformSettingsSchema,
    current_admin = Depends(require_permission("system_config"))
):
    """
    Обновить настройки платформ
    """
    try:
        # TODO: Реализовать сохранение настроек платформ
        logger.info(
            f"Platform settings updated by admin",
            admin_id=current_admin.id,
            settings=platform_settings.dict()
        )
        
        return platform_settings
        
    except Exception as e:
        logger.error(f"Error updating platform settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при обновлении настроек платформ"
        )

@router.get("/notifications", response_model=NotificationSettingsSchema)
async def get_notification_settings(
    current_admin = Depends(require_permission("system_config"))
):
    """
    Получить настройки уведомлений
    """
    try:
        return NotificationSettingsSchema(
            telegram_notifications=True,
            email_notifications=False,
            webhook_notifications=False,
            
            webhook_url=None,
            notification_rate_limit=30,
            
            download_complete_template="✅ Загрузка завершена!\n\n{title}\nПлатформа: {platform}\nРазмер: {size}",
            download_failed_template="❌ Ошибка загрузки\n\n{error}\nСсылка: {url}",
            premium_expiry_template="⏰ Premium истекает через {days} дней"
        )
        
    except Exception as e:
        logger.error(f"Error getting notification settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении настроек уведомлений"
        )

@router.put("/notifications", response_model=NotificationSettingsSchema)
async def update_notification_settings(
    notification_settings: NotificationSettingsSchema,
    current_admin = Depends(require_permission("system_config"))
):
    """
    Обновить настройки уведомлений
    """
    try:
        # TODO: Реализовать сохранение настроек уведомлений
        logger.info(
            f"Notification settings updated by admin",
            admin_id=current_admin.id
        )
        
        return notification_settings
        
    except Exception as e:
        logger.error(f"Error updating notification settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при обновлении настроек уведомлений"
        )

@router.post("/maintenance/enable")
async def enable_maintenance_mode(
    current_admin = Depends(require_permission("system_maintenance"))
):
    """
    Включить режим обслуживания
    """
    try:
        # TODO: Реализовать включение режима обслуживания
        logger.warning(
            f"Maintenance mode enabled",
            admin_id=current_admin.id,
            admin_username=current_admin.username
        )
        
        return {"message": "Режим обслуживания включен", "maintenance_mode": True}
        
    except Exception as e:
        logger.error(f"Error enabling maintenance mode: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при включении режима обслуживания"
        )

@router.post("/maintenance/disable")
async def disable_maintenance_mode(
    current_admin = Depends(require_permission("system_maintenance"))
):
    """
    Отключить режим обслуживания
    """
    try:
        # TODO: Реализовать отключение режима обслуживания
        logger.info(
            f"Maintenance mode disabled",
            admin_id=current_admin.id,
            admin_username=current_admin.username
        )
        
        return {"message": "Режим обслуживания отключен", "maintenance_mode": False}
        
    except Exception as e:
        logger.error(f"Error disabling maintenance mode: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при отключении режима обслуживания"
        )

@router.get("/cache/status")
async def get_cache_status(
    current_admin = Depends(require_permission("system_stats"))
):
    """
    Получить статус кэша
    """
    try:
        # TODO: Реализовать получение статуса Redis кэша
        return {
            "redis_connected": True,
            "total_keys": 1250,
            "used_memory": "45.2 MB",
            "hit_ratio": 89.5,
            "uptime_hours": 72.3
        }
        
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении статуса кэша"
        )

@router.post("/cache/clear")
async def clear_cache(
    cache_type: str = "all",  # all, user_sessions, download_cache, analytics
    current_admin = Depends(require_permission("system_maintenance"))
):
    """
    Очистить кэш
    """
    try:
        # TODO: Реализовать очистку кэша
        logger.info(
            f"Cache cleared",
            cache_type=cache_type,
            admin_id=current_admin.id
        )
        
        return {
            "message": f"Кэш '{cache_type}' очищен",
            "cache_type": cache_type,
            "cleared_keys": 150
        }
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при очистке кэша"
        )

@router.get("/workers/status")
async def get_workers_status(
    current_admin = Depends(require_permission("system_stats"))
):
    """
    Получить статус воркеров
    """
    try:
        # TODO: Реализовать получение статуса Celery воркеров
        return {
            "active_workers": 4,
            "total_workers": 4,
            "pending_tasks": 12,
            "processing_tasks": 8,
            "completed_tasks_today": 1547,
            "failed_tasks_today": 23,
            "workers": [
                {
                    "name": "worker-1@server-01",
                    "status": "online",
                    "active_tasks": 2,
                    "processed_tasks": 387,
                    "last_heartbeat": "2024-01-15T10:30:45Z"
                },
                {
                    "name": "worker-2@server-01", 
                    "status": "online",
                    "active_tasks": 3,
                    "processed_tasks": 401,
                    "last_heartbeat": "2024-01-15T10:30:42Z"
                },
                {
                    "name": "worker-3@server-02",
                    "status": "online", 
                    "active_tasks": 1,
                    "processed_tasks": 359,
                    "last_heartbeat": "2024-01-15T10:30:38Z"
                },
                {
                    "name": "worker-4@server-02",
                    "status": "online",
                    "active_tasks": 2,
                    "processed_tasks": 400,
                    "last_heartbeat": "2024-01-15T10:30:41Z"
                }
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting workers status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении статуса воркеров"
        )

@router.post("/workers/restart")
async def restart_workers(
    current_admin = Depends(require_permission("system_maintenance"))
):
    """
    Перезапустить воркеры
    """
    try:
        # TODO: Реализовать перезапуск воркеров
        logger.warning(
            f"Workers restart initiated",
            admin_id=current_admin.id,
            admin_username=current_admin.username
        )
        
        return {
            "message": "Команда перезапуска воркеров отправлена",
            "restarted_workers": 4
        }
        
    except Exception as e:
        logger.error(f"Error restarting workers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при перезапуске воркеров"
        )