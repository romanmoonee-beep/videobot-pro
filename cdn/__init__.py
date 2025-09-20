"""
VideoBot Pro - CDN Module
Модуль CDN для доставки контента с облачными хранилищами
"""

from .config import CDNConfig, cdn_config
from .main import app, create_app, main

# Новые компоненты для интеграции с облачными хранилищами
try:
    from .storage_integration import CDNStorageManager, cdn_storage_manager
    STORAGE_INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Storage integration not available: {e}")
    CDNStorageManager = None
    cdn_storage_manager = None
    STORAGE_INTEGRATION_AVAILABLE = False

# Сервисы
try:
    from .services import FileService, CleanupService
    SERVICES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: CDN services not available: {e}")
    FileService = None
    CleanupService = None
    SERVICES_AVAILABLE = False

# API роутеры
try:
    from .api import files_router, auth_router, stats_router
    API_AVAILABLE = True
except ImportError as e:
    print(f"Warning: CDN API not available: {e}")
    files_router = None
    auth_router = None
    stats_router = None
    API_AVAILABLE = False

# Middleware
try:
    from .middleware import (
        AuthMiddleware, 
        RateLimitMiddleware, 
        LoggingMiddleware,
        CORSMiddleware,
        create_cors_middleware
    )
    MIDDLEWARE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: CDN middleware not available: {e}")
    AuthMiddleware = None
    RateLimitMiddleware = None
    LoggingMiddleware = None
    CORSMiddleware = None
    create_cors_middleware = None
    MIDDLEWARE_AVAILABLE = False

__version__ = "2.1.0"

# Основные экспорты
__all__ = [
    # Core components
    'CDNConfig',
    'cdn_config',
    'app', 
    'create_app',
    'main',
    
    # Storage integration
    'CDNStorageManager',
    'cdn_storage_manager',
    
    # Services
    'FileService',
    'CleanupService',
    
    # API
    'files_router',
    'auth_router', 
    'stats_router',
    
    # Middleware
    'AuthMiddleware',
    'RateLimitMiddleware',
    'LoggingMiddleware',
    'CORSMiddleware',
    'create_cors_middleware',
    
    # Feature flags
    'STORAGE_INTEGRATION_AVAILABLE',
    'SERVICES_AVAILABLE',
    'API_AVAILABLE',
    'MIDDLEWARE_AVAILABLE',
]

# Информация о CDN модуле
CDN_INFO = {
    'version': __version__,
    'description': 'VideoBot Pro CDN with multi-cloud storage support',
    'features': {
        'storage_integration': STORAGE_INTEGRATION_AVAILABLE,
        'api_endpoints': API_AVAILABLE,
        'middleware': MIDDLEWARE_AVAILABLE,
        'services': SERVICES_AVAILABLE,
        'multi_cloud_support': STORAGE_INTEGRATION_AVAILABLE,
        'intelligent_routing': STORAGE_INTEGRATION_AVAILABLE,
        'automatic_cleanup': SERVICES_AVAILABLE,
        'range_requests': API_AVAILABLE,
        'rate_limiting': MIDDLEWARE_AVAILABLE,
    },
    'supported_storage_providers': [
        'Wasabi S3',
        'DigitalOcean Spaces',
        'Backblaze B2',
        'Local Storage'
    ] if STORAGE_INTEGRATION_AVAILABLE else ['Local Storage'],
    'endpoints': {
        'files': '/api/v1/files',
        'auth': '/api/v1/auth',
        'stats': '/api/v1/stats',
        'admin': '/api/v1/admin',
        'health': '/health'
    } if API_AVAILABLE else {}
}

def get_cdn_info():
    """Получить информацию о CDN модуле"""
    return CDN_INFO.copy()

def check_cdn_health():
    """Проверить здоровье CDN компонентов"""
    health = {
        'overall_status': 'healthy',
        'components': {}
    }
    
    # Проверяем основные компоненты
    try:
        if cdn_config:
            health['components']['config'] = 'healthy'
        else:
            health['components']['config'] = 'unavailable'
            health['overall_status'] = 'degraded'
    except Exception:
        health['components']['config'] = 'error'
        health['overall_status'] = 'unhealthy'
    
    # Проверяем интеграцию хранилищ
    try:
        if STORAGE_INTEGRATION_AVAILABLE and cdn_storage_manager:
            if cdn_storage_manager.initialized:
                health['components']['storage_integration'] = 'healthy'
            else:
                health['components']['storage_integration'] = 'not_initialized'
                health['overall_status'] = 'degraded'
        else:
            health['components']['storage_integration'] = 'unavailable'
            health['overall_status'] = 'degraded'
    except Exception:
        health['components']['storage_integration'] = 'error'
        health['overall_status'] = 'unhealthy'
    
    # Проверяем API
    health['components']['api'] = 'healthy' if API_AVAILABLE else 'unavailable'
    health['components']['middleware'] = 'healthy' if MIDDLEWARE_AVAILABLE else 'unavailable'
    health['components']['services'] = 'healthy' if SERVICES_AVAILABLE else 'unavailable'
    
    return health

def get_storage_providers_status():
    """Получить статус провайдеров хранилища"""
    if not STORAGE_INTEGRATION_AVAILABLE or not cdn_storage_manager:
        return {'error': 'Storage integration not available'}
    
    try:
        status = {}
        
        if cdn_storage_manager.primary_storage:
            status['primary'] = {
                'type': cdn_storage_manager.primary_storage.__class__.__name__,
                'available': True
            }
        else:
            status['primary'] = {'available': False}
        
        if cdn_storage_manager.backup_storage:
            status['backup'] = {
                'type': cdn_storage_manager.backup_storage.__class__.__name__,
                'available': True
            }
        else:
            status['backup'] = {'available': False}
        
        if cdn_storage_manager.local_storage:
            status['local'] = {
                'type': 'LocalStorage',
                'available': True
            }
        else:
            status['local'] = {'available': False}
        
        return status
        
    except Exception as e:
        return {'error': str(e)}

# Утилитарные функции для простого использования
async def upload_file_to_cdn(file_path: str, user=None, metadata=None):
    """Простая функция для загрузки файла в CDN"""
    if not STORAGE_INTEGRATION_AVAILABLE or not cdn_storage_manager:
        raise RuntimeError("Storage integration not available")
    
    return await cdn_storage_manager.upload_file(
        local_file_path=file_path,
        file_key=file_path.split('/')[-1],  # Используем имя файла как ключ
        user=user,
        metadata=metadata
    )

async def download_file_from_cdn(file_key: str, local_path: str, user=None):
    """Простая функция для скачивания файла из CDN"""
    if not STORAGE_INTEGRATION_AVAILABLE or not cdn_storage_manager:
        raise RuntimeError("Storage integration not available")
    
    return await cdn_storage_manager.download_file(
        file_key=file_key,
        local_path=local_path,
        user=user
    )

async def delete_file_from_cdn(file_key: str, user=None):
    """Простая функция для удаления файла из CDN"""
    if not STORAGE_INTEGRATION_AVAILABLE or not cdn_storage_manager:
        raise RuntimeError("Storage integration not available")
    
    return await cdn_storage_manager.delete_file(
        file_key=file_key,
        user=user
    )

# Инициализация при импорте
def _initialize_cdn():
    """Инициализация CDN компонентов"""
    try:
        # Проверяем доступность основных компонентов
        health = check_cdn_health()
        
        if health['overall_status'] == 'healthy':
            print(f"✅ VideoBot Pro CDN v{__version__} loaded successfully")
        elif health['overall_status'] == 'degraded':
            print(f"⚠️  VideoBot Pro CDN v{__version__} loaded with warnings")
            print("   Some components are not available, check configuration")
        else:
            print(f"❌ VideoBot Pro CDN v{__version__} loaded with errors")
            print("   Critical components failed to load")
        
        # Показываем доступные функции
        features = [name for name, available in CDN_INFO['features'].items() if available]
        if features:
            print(f"📋 Available features: {', '.join(features)}")
        
        # Показываем провайдеров хранилища
        if STORAGE_INTEGRATION_AVAILABLE:
            providers = CDN_INFO['supported_storage_providers']
            print(f"💾 Storage providers: {', '.join(providers)}")
        
    except Exception as e:
        print(f"❌ CDN initialization error: {e}")

# Запускаем инициализацию
_initialize_cdn()