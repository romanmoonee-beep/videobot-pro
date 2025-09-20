"""
VideoBot Pro - Admin Panel Configuration
Конфигурация для админ панели
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Dict, Any
from shared.config.settings import settings as shared_settings

class AdminSettings(BaseSettings):
    """Настройки админ панели"""
    
    # Server Configuration
    ADMIN_HOST: str = Field(default="0.0.0.0", description="Admin panel host")
    ADMIN_PORT: int = Field(default=8080, description="Admin panel port")
    
    # API Configuration
    API_PREFIX: str = Field(default="/api", description="API prefix")
    API_VERSION: str = Field(default="v1", description="API version")
    
    # Security
    ADMIN_SECRET_KEY: str = Field(default=shared_settings.JWT_SECRET, description="Admin secret key")
    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:3001", 
            "https://admin.videobot.com",
            "https://videobot-admin.netlify.app"
        ],
        description="CORS allowed origins"
    )
    CORS_CREDENTIALS: bool = Field(default=True, description="Allow CORS credentials")
    CORS_METHODS: List[str] = Field(default=["GET", "POST", "PUT", "DELETE", "PATCH"], description="CORS allowed methods")
    CORS_HEADERS: List[str] = Field(default=["*"], description="CORS allowed headers")
    
    # Session & Auth
    SESSION_EXPIRE_MINUTES: int = Field(default=480, description="Session expiration (8 hours)")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Refresh token expiration")
    MAX_LOGIN_ATTEMPTS: int = Field(default=5, description="Max failed login attempts")
    LOCKOUT_DURATION_MINUTES: int = Field(default=30, description="Account lockout duration")
    
    # Frontend Configuration
    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Frontend URL")
    STATIC_FILES_PATH: str = Field(default="./admin/frontend/build", description="Static files path")
    SERVE_STATIC_FILES: bool = Field(default=True, description="Serve static files")
    
    # File Upload
    MAX_UPLOAD_SIZE: int = Field(default=100 * 1024 * 1024, description="Max upload size (100MB)")
    ALLOWED_FILE_TYPES: List[str] = Field(
        default=[".jpg", ".jpeg", ".png", ".gif", ".mp4", ".csv", ".xlsx", ".zip"],
        description="Allowed file types"
    )
    UPLOAD_PATH: str = Field(default="./uploads", description="Upload directory")
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = Field(default=20, description="Default pagination size")
    MAX_PAGE_SIZE: int = Field(default=1000, description="Maximum pagination size")
    
    # Cache
    CACHE_TTL_SECONDS: int = Field(default=300, description="Cache TTL (5 minutes)")
    CACHE_USER_DATA: bool = Field(default=True, description="Cache user data")
    CACHE_ANALYTICS: bool = Field(default=True, description="Cache analytics data")
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, description="Enable rate limiting")
    RATE_LIMIT_REQUESTS: int = Field(default=100, description="Rate limit requests per window")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Rate limit window in seconds")
    
    # Monitoring & Logging
    LOG_REQUESTS: bool = Field(default=True, description="Log HTTP requests")
    LOG_RESPONSES: bool = Field(default=False, description="Log HTTP responses")
    ENABLE_METRICS: bool = Field(default=True, description="Enable metrics collection")
    METRICS_ENDPOINT: str = Field(default="/metrics", description="Metrics endpoint")
    
    # Admin Features
    ENABLE_USER_CREATION: bool = Field(default=True, description="Allow creating users from admin")
    ENABLE_BULK_OPERATIONS: bool = Field(default=True, description="Enable bulk operations")
    ENABLE_DATA_EXPORT: bool = Field(default=True, description="Enable data export")
    ENABLE_SYSTEM_LOGS: bool = Field(default=True, description="Enable system logs viewing")
    
    # Backup & Maintenance
    AUTO_BACKUP_ENABLED: bool = Field(default=False, description="Enable automatic backups")
    BACKUP_INTERVAL_HOURS: int = Field(default=24, description="Backup interval")
    BACKUP_RETENTION_DAYS: int = Field(default=30, description="Backup retention")
    
    # Notifications
    ADMIN_NOTIFICATIONS_ENABLED: bool = Field(default=True, description="Enable admin notifications")
    EMAIL_NOTIFICATIONS: bool = Field(default=False, description="Send email notifications")
    TELEGRAM_NOTIFICATIONS: bool = Field(default=True, description="Send Telegram notifications")
    NOTIFICATION_CHANNELS: List[str] = Field(default=[], description="Notification channel IDs")
    
    # External Services
    SMTP_SERVER: str = Field(default="", description="SMTP server")
    SMTP_PORT: int = Field(default=587, description="SMTP port")
    SMTP_USERNAME: str = Field(default="", description="SMTP username")
    SMTP_PASSWORD: str = Field(default="", description="SMTP password")
    SMTP_USE_TLS: bool = Field(default=True, description="Use TLS for SMTP")
    
    # Analytics
    ANALYTICS_RETENTION_DAYS: int = Field(default=365, description="Analytics data retention")
    REALTIME_ANALYTICS: bool = Field(default=True, description="Enable realtime analytics")
    ANALYTICS_BATCH_SIZE: int = Field(default=1000, description="Analytics batch processing size")
    
    # UI Configuration
    UI_THEME: str = Field(default="dark", description="Default UI theme")
    UI_LANGUAGE: str = Field(default="en", description="Default UI language")
    UI_TIMEZONE: str = Field(default="UTC", description="Default timezone")
    UI_DATE_FORMAT: str = Field(default="YYYY-MM-DD", description="Date format")
    UI_TIME_FORMAT: str = Field(default="24h", description="Time format")
    
    # Dashboard Configuration
    DASHBOARD_REFRESH_INTERVAL: int = Field(default=30, description="Dashboard refresh interval (seconds)")
    DASHBOARD_WIDGETS: List[str] = Field(
        default=[
            "user_stats",
            "download_stats", 
            "revenue_stats",
            "system_health",
            "recent_activity"
        ],
        description="Default dashboard widgets"
    )
    
    # Security Headers
    SECURITY_HEADERS: Dict[str, str] = Field(
        default={
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
        },
        description="Security headers"
    )
    
    class Config:
        env_prefix = "ADMIN_"
        env_file = ".env"
        case_sensitive = True

# Глобальный экземпляр настроек
admin_settings = AdminSettings()

# Feature flags для различных ролей
ROLE_PERMISSIONS = {
    "super_admin": {
        "users": ["view", "create", "edit", "delete", "ban", "premium"],
        "downloads": ["view", "retry", "cancel", "delete"],
        "analytics": ["view", "export", "detailed"],
        "settings": ["view", "edit", "system"],
        "channels": ["view", "create", "edit", "delete"],
        "broadcast": ["view", "create", "send", "schedule"],
        "payments": ["view", "refund", "export"],
        "system": ["logs", "health", "maintenance", "backup"],
        "admin": ["view", "create", "edit", "delete", "roles"]
    },
    "admin": {
        "users": ["view", "edit", "ban", "premium"],
        "downloads": ["view", "retry", "cancel"],
        "analytics": ["view", "export"],
        "settings": ["view", "edit"],
        "channels": ["view", "edit"],
        "broadcast": ["view", "create", "send"],
        "payments": ["view", "export"],
        "system": ["logs", "health"],
        "admin": ["view"]
    },
    "moderator": {
        "users": ["view", "ban"],
        "downloads": ["view"],
        "analytics": ["view"],
        "settings": ["view"],
        "channels": ["view"],
        "broadcast": ["view"],
        "payments": ["view"],
        "system": ["health"],
        "admin": []
    },
    "support": {
        "users": ["view"],
        "downloads": ["view"],
        "analytics": ["view"],
        "settings": ["view"],
        "channels": ["view"],
        "broadcast": [],
        "payments": [],
        "system": ["health"],
        "admin": []
    },
    "viewer": {
        "users": ["view"],
        "downloads": ["view"],
        "analytics": ["view"],
        "settings": ["view"],
        "channels": ["view"],
        "broadcast": [],
        "payments": [],
        "system": [],
        "admin": []
    }
}

# UI конфигурация для различных ролей
ROLE_UI_CONFIG = {
    "super_admin": {
        "sidebar_items": [
            "dashboard", "users", "downloads", "analytics", 
            "channels", "broadcast", "payments", "settings", "system", "admins"
        ],
        "dashboard_widgets": [
            "user_stats", "download_stats", "revenue_stats", 
            "system_health", "recent_activity", "error_logs"
        ]
    },
    "admin": {
        "sidebar_items": [
            "dashboard", "users", "downloads", "analytics",
            "channels", "broadcast", "payments", "settings"
        ],
        "dashboard_widgets": [
            "user_stats", "download_stats", "revenue_stats", 
            "system_health", "recent_activity"
        ]
    },
    "moderator": {
        "sidebar_items": [
            "dashboard", "users", "downloads", "analytics", "channels"
        ],
        "dashboard_widgets": [
            "user_stats", "download_stats", "recent_activity"
        ]
    },
    "support": {
        "sidebar_items": [
            "dashboard", "users", "downloads"
        ],
        "dashboard_widgets": [
            "user_stats", "recent_activity"
        ]
    },
    "viewer": {
        "sidebar_items": [
            "dashboard", "analytics"
        ],
        "dashboard_widgets": [
            "user_stats", "download_stats"
        ]
    }
}

def get_user_permissions(role: str) -> Dict[str, List[str]]:
    """Получить права доступа для роли"""
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["viewer"])

def get_user_ui_config(role: str) -> Dict[str, Any]:
    """Получить UI конфигурацию для роли"""
    return ROLE_UI_CONFIG.get(role, ROLE_UI_CONFIG["viewer"])

def check_permission(role: str, resource: str, action: str) -> bool:
    """Проверить права доступа"""
    permissions = get_user_permissions(role)
    resource_permissions = permissions.get(resource, [])
    return action in resource_permissions

# Константы для UI
class UIConstants:
    """UI константы"""
    
    # Цвета статусов
    STATUS_COLORS = {
        "active": "#4CAF50",
        "inactive": "#9E9E9E", 
        "pending": "#FF9800",
        "failed": "#F44336",
        "success": "#4CAF50",
        "warning": "#FF9800",
        "error": "#F44336",
        "info": "#2196F3"
    }
    
    # Иконки статусов
    STATUS_ICONS = {
        "active": "✅",
        "inactive": "⭕", 
        "pending": "⏳",
        "failed": "❌",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "info": "ℹ️"
    }
    
    # Размеры файлов
    FILE_SIZE_LIMITS = {
        "avatar": 5 * 1024 * 1024,  # 5MB
        "document": 50 * 1024 * 1024,  # 50MB
        "video": 500 * 1024 * 1024,  # 500MB
        "export": 100 * 1024 * 1024  # 100MB
    }
    
    # Форматы дат
    DATE_FORMATS = {
        "short": "DD/MM/YYYY",
        "medium": "DD MMM YYYY",
        "long": "DD MMMM YYYY, HH:mm",
        "iso": "YYYY-MM-DD HH:mm:ss"
    }

# Настройки по умолчанию для новых админов
DEFAULT_ADMIN_SETTINGS = {
    "theme": "dark",
    "language": "en",
    "timezone": "UTC",
    "notifications": {
        "email": False,
        "telegram": True,
        "browser": True,
        "sound": False
    },
    "dashboard": {
        "refresh_interval": 30,
        "widgets": ["user_stats", "download_stats", "recent_activity"],
        "layout": "grid"
    },
    "table": {
        "page_size": 20,
        "dense": False,
        "show_icons": True
    }
}

# Валидаторы конфигурации
def validate_admin_config():
    """Валидация конфигурации админ панели"""
    errors = []
    
    # Проверяем обязательные настройки
    if not admin_settings.ADMIN_SECRET_KEY:
        errors.append("ADMIN_SECRET_KEY is required")
    
    if admin_settings.SESSION_EXPIRE_MINUTES < 5:
        errors.append("SESSION_EXPIRE_MINUTES must be at least 5 minutes")
    
    if admin_settings.DEFAULT_PAGE_SIZE > admin_settings.MAX_PAGE_SIZE:
        errors.append("DEFAULT_PAGE_SIZE cannot be greater than MAX_PAGE_SIZE")
    
    # Проверяем пути к файлам
    import os
    if admin_settings.SERVE_STATIC_FILES:
        if not os.path.exists(admin_settings.STATIC_FILES_PATH):
            errors.append(f"Static files path does not exist: {admin_settings.STATIC_FILES_PATH}")
    
    if errors:
        raise ValueError(f"Admin configuration errors: {', '.join(errors)}")
    
    return True

# Экспорт для удобного импорта
__all__ = [
    "admin_settings",
    "ROLE_PERMISSIONS", 
    "ROLE_UI_CONFIG",
    "UIConstants",
    "DEFAULT_ADMIN_SETTINGS",
    "get_user_permissions",
    "get_user_ui_config", 
    "check_permission",
    "validate_admin_config"
]