"""
VideoBot Pro - Services Package
Бизнес-логика и сервисы для бота
"""

from .download_service import download_service, DownloadService, DownloadError
from .batch_service import batch_service, BatchService, BatchError
from .notification_service import notification_service, NotificationService, NotificationType
from .analytics_service import (
    analytics_service, 
    AnalyticsService, 
    MetricType, 
    TimeRange,
    get_user_stats,
    get_download_stats,
    get_financial_stats,
    get_system_stats,
    track_event,
    generate_analytics_report,
    get_realtime_dashboard,
    get_top_performers
)

import structlog
from aiogram import Bot

logger = structlog.get_logger(__name__)

# Глобальные экземпляры сервисов
_services_initialized = False

async def initialize_services(bot: Bot) -> None:
    """
    Инициализация всех сервисов
    
    Args:
        bot: Экземпляр Telegram бота
    """
    global _services_initialized, notification_service
    
    if _services_initialized:
        return
    
    try:
        # Инициализация сервиса уведомлений
        from .notification_service import create_notification_service
        notification_service = create_notification_service(bot)
        
        # Можно добавить инициализацию других сервисов
        
        _services_initialized = True
        logger.info("All services initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing services: {e}")
        raise

async def cleanup_services() -> None:
    """Очистка ресурсов сервисов при завершении"""
    global _services_initialized
    
    try:
        # Очистка старых данных аналитики
        await analytics_service.cleanup_old_events(days_old=30)
        
        # Очистка старых задач загрузки
        await download_service.cleanup_old_tasks(days_old=7)
        
        # Очистка истекших batch'ей
        await batch_service.cleanup_expired_batches()
        
        _services_initialized = False
        logger.info("Services cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during services cleanup: {e}")

def get_service_status() -> dict:
    """Получить статус всех сервисов"""
    return {
        'initialized': _services_initialized,
        'services': {
            'download_service': bool(download_service),
            'batch_service': bool(batch_service), 
            'notification_service': bool(notification_service),
            'analytics_service': bool(analytics_service)
        }
    }

# Список всех экспортируемых объектов
__all__ = [
    # Основные сервисы
    'download_service',
    'batch_service', 
    'notification_service',
    'analytics_service',
    
    # Классы сервисов
    'DownloadService',
    'BatchService',
    'NotificationService', 
    'AnalyticsService',
    
    # Исключения
    'DownloadError',
    'BatchError',
    
    # Енумы и типы
    'NotificationType',
    'MetricType',
    'TimeRange',
    
    # Функции аналитики
    'get_user_stats',
    'get_download_stats', 
    'get_financial_stats',
    'get_system_stats',
    'track_event',
    'generate_analytics_report',
    'get_realtime_dashboard',
    'get_top_performers',
    
    # Функции управления
    'initialize_services',
    'cleanup_services',
    'get_service_status'
]