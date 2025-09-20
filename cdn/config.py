"""
VideoBot Pro - Updated Settings with Cloud Storage Configuration
Обновленные настройки с конфигурацией облачных хранилищ
"""

import os
from typing import Optional, List
from pydantic import BaseSettings, validator

class Settings(BaseSettings):
    """Настройки приложения с поддержкой облачных хранилищ"""
    
    # Основные настройки
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "your-secret-key-here"
    
    # База данных
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost/videobot_pro"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # CDN настройки
    CDN_HOST: str = "0.0.0.0"
    CDN_PORT: int = 8003
    CDN_MAX_BANDWIDTH_MBPS: int = 1000
    
    # Основные лимиты файлов
    MAX_FILE_SIZE_MB: int = 500
    FREE_MAX_FILE_SIZE_MB: int = 100
    PREMIUM_MAX_FILE_SIZE_MB: int = 500
    ADMIN_MAX_FILE_SIZE_MB: int = 2000
    
    # Время хранения файлов (в часах)
    FREE_FILE_RETENTION_HOURS: int = 24
    PREMIUM_FILE_RETENTION_HOURS: int = 168  # 7 дней
    ADMIN_FILE_RETENTION_HOURS: int = 8760  # 365 дней
    
    # Пути хранения
    WORKER_STORAGE_PATH: str = "./storage"
    WORKER_TEMP_DIR: str = "./temp"
    
    # === WASABI S3 CONFIGURATION ===
    WASABI_ACCESS_KEY: Optional[str] = None
    WASABI_SECRET_KEY: Optional[str] = None
    WASABI_BUCKET_NAME: Optional[str] = None
    WASABI_REGION: str = "us-east-1"
    WASABI_CDN_DOMAIN: Optional[str] = None
    WASABI_ENDPOINT_URL: Optional[str] = None
    
    @validator('WASABI_ENDPOINT_URL', always=True)
    def set_wasabi_endpoint(cls, v, values):
        if v is None and values.get('WASABI_REGION'):
            return f"https://s3.{values['WASABI_REGION']}.wasabisys.com"
        return v
    
    # === DIGITALOCEAN SPACES CONFIGURATION ===
    DO_SPACES_KEY: Optional[str] = None
    DO_SPACES_SECRET: Optional[str] = None
    DO_SPACES_BUCKET: Optional[str] = None
    DO_SPACES_REGION: str = "nyc3"
    DO_SPACES_CDN_DOMAIN: Optional[str] = None
    DO_SPACES_ENDPOINT_URL: Optional[str] = None
    
    @validator('DO_SPACES_ENDPOINT_URL', always=True)
    def set_do_endpoint(cls, v, values):
        if v is None and values.get('DO_SPACES_REGION'):
            return f"https://{values['DO_SPACES_REGION']}.digitaloceanspaces.com"
        return v
    
    @validator('DO_SPACES_CDN_DOMAIN', always=True)
    def set_do_cdn_domain(cls, v, values):
        if v is None and values.get('DO_SPACES_BUCKET') and values.get('DO_SPACES_REGION'):
            return f"{values['DO_SPACES_BUCKET']}.{values['DO_SPACES_REGION']}.cdn.digitaloceanspaces.com"
        return v
    
    # === BACKBLAZE B2 CONFIGURATION ===
    B2_KEY_ID: Optional[str] = None
    B2_APPLICATION_KEY: Optional[str] = None
    B2_BUCKET_NAME: Optional[str] = None
    B2_REGION: str = "us-west-000"
    
    # === STORAGE PRIORITY CONFIGURATION ===
    # Приоритет хранилищ для разных типов пользователей
    PREMIUM_STORAGE_PRIORITY: List[str] = ["wasabi", "digitalocean", "backblaze"]
    FREE_STORAGE_PRIORITY: List[str] = ["backblaze", "digitalocean", "wasabi"] 
    TRIAL_STORAGE_PRIORITY: List[str] = ["digitalocean", "backblaze", "wasabi"]
    ADMIN_STORAGE_PRIORITY: List[str] = ["wasabi", "digitalocean", "backblaze"]
    
    # === STORAGE BEHAVIOR SETTINGS ===
    # Автоматическое резервное копирование
    ENABLE_BACKUP_STORAGE: bool = True
    
    # Автоматическая миграция на лучшее хранилище
    ENABLE_STORAGE_MIGRATION: bool = False
    
    # Максимальное количество попыток загрузки
    MAX_UPLOAD_RETRIES: int = 3
    
    # Время ожидания операций с хранилищем (секунды)
    STORAGE_TIMEOUT: int = 300
    
    # === CACHING SETTINGS ===
    # Размер локального кэша (ГБ)
    LOCAL_CACHE_SIZE_GB: int = 10
    
    # Время жизни кэша (часы)
    CACHE_TTL_HOURS: int = 24
    
    # Предварительное кэширование популярных файлов
    ENABLE_PREEMPTIVE_CACHING: bool = True
    
    # === CDN SETTINGS ===
    # Максимальная пропускная способность на пользователя (Мбит/с)
    MAX_BANDWIDTH_PER_USER: int = 50
    
    # Максимальное количество одновременных загрузок
    MAX_CONCURRENT_DOWNLOADS: int = 100
    
    # Поддержка Range запросов
    ENABLE_RANGE_REQUESTS: bool = True
    
    # === CLEANUP SETTINGS ===
    # Интервал автоматической очистки (часы)
    CLEANUP_INTERVAL_HOURS: int = 6
    
    # Очистка файлов без записей в БД
    CLEANUP_ORPHANED_FILES: bool = True
    
    # Удаление дубликатов файлов
    REMOVE_DUPLICATE_FILES: bool = True
    
    # === MONITORING SETTINGS ===
    # Мониторинг использования хранилища
    ENABLE_STORAGE_MONITORING: bool = True
    
    # Интервал проверки здоровья хранилищ (минуты)
    HEALTH_CHECK_INTERVAL_MINUTES: int = 5
    
    # Алерты при проблемах с хранилищем
    ENABLE_STORAGE_ALERTS: bool = True
    
    # === SECURITY SETTINGS ===
    # Шифрование файлов в хранилище
    ENABLE_STORAGE_ENCRYPTION: bool = True
    
    # Подписанные URL для доступа к файлам
    ENABLE_SIGNED_URLS: bool = True
    
    # Время жизни подписанных URL (часы)
    SIGNED_URL_EXPIRY_HOURS: int = 24
    
    # === PERFORMANCE SETTINGS ===
    # Размер чанка для загрузки (байты)
    UPLOAD_CHUNK_SIZE: int = 8 * 1024 * 1024  # 8MB
    
    # Размер чанка для скачивания (байты)
    DOWNLOAD_CHUNK_SIZE: int = 1024 * 1024  # 1MB
    
    # Параллельная загрузка частей файла
    ENABLE_MULTIPART_UPLOAD: bool = True
    
    # Минимальный размер файла для multipart загрузки (МБ)
    MULTIPART_THRESHOLD_MB: int = 100
    
    # === CORS SETTINGS ===
    ALLOWED_ORIGINS: List[str] = ["*"]  # В продакшене указать конкретные домены
    ALLOWED_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"]
    ALLOWED_HEADERS: List[str] = ["*"]
    
    # === API RATE LIMITING ===
    # Лимиты запросов в минуту для разных типов пользователей
    FREE_REQUESTS_PER_MINUTE: int = 10
    PREMIUM_REQUESTS_PER_MINUTE: int = 30
    ADMIN_REQUESTS_PER_MINUTE: int = 100
    
    # === LOGGING SETTINGS ===
    LOG_LEVEL: str = "INFO"
    ENABLE_ACCESS_LOGS: bool = True
    ENABLE_ERROR_TRACKING: bool = True
    
    # === WEBHOOK SETTINGS ===
    # Уведомления о событиях хранилища
    STORAGE_WEBHOOK_URL: Optional[str] = None
    ENABLE_UPLOAD_NOTIFICATIONS: bool = False
    ENABLE_DELETE_NOTIFICATIONS: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    def get_storage_config(self, storage_type: str) -> dict:
        """Получение конфигурации для конкретного типа хранилища"""
        configs = {
            'wasabi': {
                'access_key': self.WASABI_ACCESS_KEY,
                'secret_key': self.WASABI_SECRET_KEY,
                'bucket_name': self.WASABI_BUCKET_NAME,
                'region': self.WASABI_REGION,
                'endpoint_url': self.WASABI_ENDPOINT_URL,
                'cdn_domain': self.WASABI_CDN_DOMAIN,
                'max_file_size_mb': 5000,
                'public_read': True,
                'encryption': self.ENABLE_STORAGE_ENCRYPTION
            },
            'digitalocean': {
                'access_key': self.DO_SPACES_KEY,
                'secret_key': self.DO_SPACES_SECRET,
                'bucket_name': self.DO_SPACES_BUCKET,
                'region': self.DO_SPACES_REGION,
                'endpoint_url': self.DO_SPACES_ENDPOINT_URL,
                'cdn_domain': self.DO_SPACES_CDN_DOMAIN,
                'max_file_size_mb': 2000,
                'public_read': True,
                'encryption': False  # DigitalOcean Spaces не поддерживает server-side encryption
            },
            'backblaze': {
                'access_key': self.B2_KEY_ID,
                'secret_key': self.B2_APPLICATION_KEY,
                'bucket_name': self.B2_BUCKET_NAME,
                'region': self.B2_REGION,
                'max_file_size_mb': 1000,
                'public_read': False,  # B2 обычно используется для приватных файлов
                'encryption': False
            },
            'local': {
                'base_path': self.WORKER_STORAGE_PATH,
                'url_prefix': f"http://{self.CDN_HOST}:{self.CDN_PORT}/api/v1/files",
                'max_file_size_mb': self.MAX_FILE_SIZE_MB
            }
        }
        
        return configs.get(storage_type, {})
    
    def get_storage_priority(self, user_type: str) -> List[str]:
        """Получение приоритета хранилищ для типа пользователя"""
        priorities = {
            'free': self.FREE_STORAGE_PRIORITY,
            'trial': self.TRIAL_STORAGE_PRIORITY,
            'premium': self.PREMIUM_STORAGE_PRIORITY,
            'admin': self.ADMIN_STORAGE_PRIORITY,
            'owner': self.ADMIN_STORAGE_PRIORITY
        }
        
        return priorities.get(user_type, self.FREE_STORAGE_PRIORITY)
    
    def is_storage_configured(self, storage_type: str) -> bool:
        """Проверка, настроено ли хранилище"""
        config = self.get_storage_config(storage_type)
        
        if storage_type == 'wasabi':
            return bool(config.get('access_key') and config.get('secret_key') and config.get('bucket_name'))
        elif storage_type == 'digitalocean':
            return bool(config.get('access_key') and config.get('secret_key') and config.get('bucket_name'))
        elif storage_type == 'backblaze':
            return bool(config.get('access_key') and config.get('secret_key') and config.get('bucket_name'))
        elif storage_type == 'local':
            return True  # Локальное хранилище всегда доступно
        
        return False
    
    def get_configured_storages(self) -> List[str]:
        """Получение списка настроенных хранилищ"""
        storages = []
        
        for storage_type in ['wasabi', 'digitalocean', 'backblaze', 'local']:
            if self.is_storage_configured(storage_type):
                storages.append(storage_type)
        
        return storages

# Создаем глобальный экземпляр настроек
settings = Settings()

