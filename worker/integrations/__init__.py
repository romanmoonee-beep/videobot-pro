"""
VideoBot Pro - Worker Integrations Package
Интеграции Worker'а с внешними сервисами
"""

__version__ = "2.1.0"

# CDN интеграция
try:
    from .cdn_upload import (
        CDNUploadClient,
        CDNIntegrationService,
        cdn_integration,
        upload_to_cdn,
        upload_thumbnail_to_cdn,
        is_cdn_available
    )
    CDN_INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: CDN integration not available: {e}")
    CDNUploadClient = None
    CDNIntegrationService = None
    cdn_integration = None
    upload_to_cdn = None
    upload_thumbnail_to_cdn = None
    is_cdn_available = None
    CDN_INTEGRATION_AVAILABLE = False

# Будущие интеграции (заглушки)
try:
    # from .webhook_integration import WebhookClient
    # from .analytics_integration import AnalyticsClient
    # from .notification_integration import NotificationClient
    pass
except ImportError:
    pass

__all__ = [
    # CDN Integration
    'CDNUploadClient',
    'CDNIntegrationService',
    'cdn_integration',
    'upload_to_cdn',
    'upload_thumbnail_to_cdn',
    'is_cdn_available',
    
    # Feature flags
    'CDN_INTEGRATION_AVAILABLE',
    
    # Utility functions
    'get_available_integrations',
    'check_integrations_health',
]

def get_available_integrations():
    """Получить список доступных интеграций"""
    integrations = {}
    
    if CDN_INTEGRATION_AVAILABLE:
        integrations['cdn'] = {
            'name': 'CDN Upload Integration',
            'description': 'Автоматическая загрузка файлов в облачные хранилища',
            'status': 'available',
            'client': CDNUploadClient,
            'service': CDNIntegrationService
        }
    else:
        integrations['cdn'] = {
            'name': 'CDN Upload Integration',
            'description': 'Автоматическая загрузка файлов в облачные хранилища',
            'status': 'unavailable',
            'error': 'Import failed'
        }
    
    # Добавляем другие интеграции по мере их реализации
    integrations['webhooks'] = {
        'name': 'Webhook Integration',
        'description': 'Отправка уведомлений через webhooks',
        'status': 'planned'
    }
    
    integrations['analytics'] = {
        'name': 'Analytics Integration',
        'description': 'Сбор и отправка аналитических данных',
        'status': 'planned'
    }
    
    integrations['notifications'] = {
        'name': 'Push Notifications',
        'description': 'Отправка push уведомлений пользователям',
        'status': 'planned'
    }
    
    return integrations

async def check_integrations_health():
    """Проверить здоровье всех интеграций"""
    health = {
        'overall_status': 'healthy',
        'integrations': {},
        'timestamp': None
    }
    
    # Импортируем datetime здесь чтобы избежать циклических импортов
    from datetime import datetime
    health['timestamp'] = datetime.utcnow().isoformat()
    
    # Проверяем CDN интеграцию
    if CDN_INTEGRATION_AVAILABLE:
        try:
            if cdn_integration and hasattr(cdn_integration, 'enabled'):
                if cdn_integration.enabled:
                    # Проверяем доступность CDN
                    cdn_available = await is_cdn_available() if is_cdn_available else False
                    
                    if cdn_available:
                        health['integrations']['cdn'] = {
                            'status': 'healthy',
                            'message': 'CDN integration working properly'
                        }
                    else:
                        health['integrations']['cdn'] = {
                            'status': 'degraded',
                            'message': 'CDN integration enabled but CDN not available'
                        }
                        health['overall_status'] = 'degraded'
                else:
                    health['integrations']['cdn'] = {
                        'status': 'disabled',
                        'message': 'CDN integration disabled'
                    }
            else:
                health['integrations']['cdn'] = {
                    'status': 'error',
                    'message': 'CDN integration object not properly initialized'
                }
                health['overall_status'] = 'degraded'
                
        except Exception as e:
            health['integrations']['cdn'] = {
                'status': 'error',
                'message': f'CDN health check failed: {str(e)}'
            }
            health['overall_status'] = 'unhealthy'
    else:
        health['integrations']['cdn'] = {
            'status': 'unavailable',
            'message': 'CDN integration not imported'
        }
        health['overall_status'] = 'degraded'
    
    # Добавляем проверки других интеграций по мере их реализации
    health['integrations']['webhooks'] = {
        'status': 'not_implemented',
        'message': 'Webhook integration not yet implemented'
    }
    
    health['integrations']['analytics'] = {
        'status': 'not_implemented', 
        'message': 'Analytics integration not yet implemented'
    }
    
    health['integrations']['notifications'] = {
        'status': 'not_implemented',
        'message': 'Push notifications not yet implemented'
    }
    
    return health

# Утилитарные функции для упрощения использования
async def quick_upload_to_cdn(file_path: str, task_id: int = None, user_id: int = None):
    """Быстрая загрузка файла в CDN без сложной настройки"""
    if not CDN_INTEGRATION_AVAILABLE or not upload_to_cdn:
        raise RuntimeError("CDN integration not available")
    
    # Создаем минимальные объекты для совместимости
    class SimpleTask:
        def __init__(self, task_id):
            self.id = task_id or 1
            self.platform = "worker"
            self.url = "direct_upload"
    
    class SimpleUser:
        def __init__(self, user_id):
            self.id = user_id or 1
            self.user_type = "free"
    
    task = SimpleTask(task_id)
    user = SimpleUser(user_id)
    
    files = [{
        'path': file_path,
        'type': 'video',
        'metadata': {'source': 'worker_integration'}
    }]
    
    return await upload_to_cdn(task, user, files)

async def upload_multiple_files_to_cdn(file_paths: list, task_id: int = None, user_id: int = None):
    """Загрузка нескольких файлов в CDN"""
    if not CDN_INTEGRATION_AVAILABLE or not cdn_integration:
        raise RuntimeError("CDN integration not available")
    
    class SimpleTask:
        def __init__(self, task_id):
            self.id = task_id or 1
            self.platform = "worker"
            self.url = "batch_upload"
    
    class SimpleUser:
        def __init__(self, user_id):
            self.id = user_id or 1
            self.user_type = "free"
    
    task = SimpleTask(task_id)
    user = SimpleUser(user_id)
    
    files = []
    for file_path in file_paths:
        files.append({
            'path': file_path,
            'type': 'video',
            'metadata': {'source': 'worker_batch_integration'}
        })
    
    return await cdn_integration.handle_download_completion(task, user, files)

def get_integration_status(integration_name: str):
    """Получить статус конкретной интеграции"""
    integrations = get_available_integrations()
    return integrations.get(integration_name, {
        'status': 'unknown',
        'error': 'Integration not found'
    })

# Информация о пакете интеграций
INTEGRATIONS_INFO = {
    'version': __version__,
    'description': 'Worker integrations with external services',
    'available_integrations': len([i for i in get_available_integrations().values() if i.get('status') == 'available']),
    'total_integrations': len(get_available_integrations()),
    'features': {
        'cdn_upload': CDN_INTEGRATION_AVAILABLE,
        'multi_cloud_support': CDN_INTEGRATION_AVAILABLE,
        'automatic_failover': CDN_INTEGRATION_AVAILABLE,
        'health_monitoring': True,
        'async_operations': True,
    }
}

def get_integrations_info():
    """Получить информацию о пакете интеграций"""
    return INTEGRATIONS_INFO.copy()

# Инициализация при импорте
print(f"🔌 VideoBot Pro Worker Integrations v{__version__}")
integrations = get_available_integrations()
available_count = len([i for i in integrations.values() if i.get('status') == 'available'])
total_count = len(integrations)

if available_count > 0:
    print(f"   ✅ {available_count}/{total_count} integrations available")
    available_names = [name for name, info in integrations.items() if info.get('status') == 'available']
    print(f"   📋 Available: {', '.join(available_names)}")
else:
    print(f"   ⚠️  No integrations available")

if CDN_INTEGRATION_AVAILABLE:
    print(f"   🌐 CDN integration ready for multi-cloud uploads")