"""
VideoBot Pro - Main Settings Configuration
Централизованная конфигурация для всех сервисов
"""

import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field, validator
from pydantic_settings import BaseSettings

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

class Config:
    env_file = str(ENV_PATH)
    env_file_encoding = 'utf-8'

class Settings(BaseSettings):
    """Main application settings"""
    
    # Application Info
    APP_NAME: str = "VideoBot Pro"
    APP_VERSION: str = "2.1.0"
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    ENVIRONMENT: str = Field(default="development", description="Environment: development, staging, production")
    
    # Database Configuration
    DATABASE_URL: str = Field(
        default="postgresql://videobot:password@localhost:5432/videobot",
        description="PostgreSQL database connection string (без драйвера, добавляется автоматически)"
    )
    DATABASE_ECHO: bool = Field(default=False, description="Enable SQLAlchemy query logging")
    DATABASE_POOL_SIZE: int = Field(default=20, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=30, description="Database max overflow connections")
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PREFIX: str = Field(default="videobot:", description="Redis key prefix")
    REDIS_EXPIRE_TIME: int = Field(default=3600, description="Default Redis expiration time")
    
    # Telegram Bot Configuration
    BOT_TOKEN: str
    WEBHOOK_URL: Optional[str] = Field(default=None, description="Webhook URL for production")
    WEBHOOK_PATH: str = Field(default="/webhook", description="Webhook endpoint path")
    WEBHOOK_SECRET: Optional[str] = Field(default=None, description="Webhook secret token")
    BOT_PARSE_MODE: str = Field(default="HTML", description="Default parse mode for messages")
    
    # Security Configuration
    JWT_SECRET: str
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    JWT_EXPIRE_MINUTES: int = Field(default=60 * 24 * 7, description="JWT token expiration (7 days)")
    RATE_LIMIT_REQUESTS: int = Field(default=10, description="Rate limit requests per minute")
    RATE_LIMIT_WINDOW: int = Field(default=60, description="Rate limit window in seconds")
    
    # Admin Configuration
    ADMIN_IDS: List[int] = Field(default_factory=list, description="Admin Telegram user IDs")
    SUPER_ADMIN_ID: Optional[int] = Field(default=None, description="Super admin Telegram ID")
    
    # CDN & Storage Configuration
    WASABI_ACCESS_KEY: str = Field(default="", description="Wasabi access key")
    WASABI_SECRET_KEY: str = Field(default="", description="Wasabi secret key")
    WASABI_BUCKET_NAME: str = Field(default="videobot-files", description="Wasabi bucket name")
    WASABI_REGION: str = Field(default="us-east-1", description="Wasabi region")
    WASABI_ENDPOINT: str = Field(default="https://s3.wasabisys.com", description="Wasabi endpoint")
    
    B2_KEY_ID: str = Field(default="", description="Backblaze B2 key ID")
    B2_APPLICATION_KEY: str = Field(default="", description="Backblaze B2 application key")
    B2_BUCKET_NAME: str = Field(default="videobot-backup", description="Backblaze B2 bucket name")
    
    CLOUDFLARE_CDN_DOMAIN: str = Field(default="cdn.videobot.com", description="CloudFlare CDN domain")
    CLOUDFLARE_ZONE_ID: str = Field(default="", description="CloudFlare zone ID")
    CLOUDFLARE_API_TOKEN: str = Field(default="", description="CloudFlare API token")
    
    # Feature Flags
    TRIAL_ENABLED: bool = Field(default=True, description="Enable trial system for new users")
    TRIAL_DURATION_MINUTES: int = Field(default=60, description="Trial duration in minutes")
    REQUIRED_SUBS_ENABLED: bool = Field(default=True, description="Enable required subscriptions")
    BATCH_PROCESSING_ENABLED: bool = Field(default=True, description="Enable batch downloads")
    PREMIUM_SYSTEM_ENABLED: bool = Field(default=True, description="Enable premium subscriptions")
    ANALYTICS_ENABLED: bool = Field(default=True, description="Enable analytics tracking")
    
    FREE_DAILY_LIMIT: int = Field(default=10, description="Free user daily download limit")
    TRIAL_DAILY_LIMIT: int = Field(default=999, description="Trial user daily limit (unlimited)")
    PREMIUM_DAILY_LIMIT: int = Field(default=999, description="Premium user daily limit (unlimited)")
    BATCH_THRESHOLD: int = Field(default=5, description="Minimum links for batch processing choice")
    MAX_BATCH_SIZE: int = Field(default=20, description="Maximum links in one batch")
    
    FREE_MAX_FILE_SIZE_MB: int = Field(default=50, description="Max file size for free users")
    PREMIUM_MAX_FILE_SIZE_MB: int = Field(default=500, description="Max file size for premium users")
    ADMIN_MAX_FILE_SIZE_MB: int = Field(default=2048, description="Max file size for admins")
    
    FREE_MAX_QUALITY: str = Field(default="720p", description="Max quality for free users")
    PREMIUM_MAX_QUALITY: str = Field(default="4K", description="Max quality for premium users")
    AUTO_QUALITY_SELECTION: bool = Field(default=True, description="Enable automatic quality selection")
    
    REQUIRED_CHANNELS: List[str] = Field(default_factory=list, description="Required subscription channels")
    SUBSCRIPTION_CHECK_INTERVAL: int = Field(default=300, description="Subscription check interval in seconds")
    
    FREE_FILE_RETENTION_HOURS: int = Field(default=24, description="Free user file retention")
    PREMIUM_FILE_RETENTION_HOURS: int = Field(default=720, description="Premium user file retention (30 days)")
    ADMIN_FILE_RETENTION_HOURS: int = Field(default=8760, description="Admin file retention (365 days)")
    
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_TASK_TIMEOUT: int = Field(default=300, description="Celery task timeout in seconds")
    CELERY_WORKER_CONCURRENCY: int = Field(default=4, description="Celery worker concurrency")
    
    YOUTUBE_API_KEY: Optional[str] = Field(default=None, description="YouTube Data API key")
    TIKTOK_SESSION_ID: Optional[str] = Field(default=None, description="TikTok session ID")
    INSTAGRAM_SESSION_ID: Optional[str] = Field(default=None, description="Instagram session ID")
    USER_AGENT: str = Field(default="VideoBot/2.1 (+https://videobot.com)", description="User agent for HTTP requests")
    
    PROMETHEUS_PORT: int = Field(default=9090, description="Prometheus metrics port")
    METRICS_ENABLED: bool = Field(default=True, description="Enable Prometheus metrics")
    HEALTH_CHECK_INTERVAL: int = Field(default=30, description="Health check interval in seconds")
    
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format")
    LOG_FILE_MAX_SIZE: int = Field(default=10 * 1024 * 1024, description="Max log file size in bytes")
    LOG_FILE_BACKUP_COUNT: int = Field(default=5, description="Number of log backup files")
    
    API_HOST: str = Field(default="0.0.0.0", description="API host")
    API_PORT: int = Field(default=8000, description="API port")
    API_WORKERS: int = Field(default=4, description="API worker processes")
    API_RELOAD: bool = Field(default=False, description="Enable API auto-reload")
    
    ADMIN_HOST: str = Field(default="0.0.0.0", description="Admin panel host")
    ADMIN_PORT: int = Field(default=8080, description="Admin panel port")
    ADMIN_CORS_ORIGINS: List[str] = Field(default=["http://localhost:3000", "https://admin.videobot.com"], description="CORS origins for admin panel")
    
    CDN_HOST: str = Field(default="0.0.0.0", description="CDN API host")
    CDN_PORT: int = Field(default=8090, description="CDN API port")
    CDN_MAX_BANDWIDTH_MBPS: int = Field(default=1000, description="Max CDN bandwidth in Mbps")
    
    STRIPE_PUBLIC_KEY: Optional[str] = Field(default=None, description="Stripe public key")
    STRIPE_SECRET_KEY: Optional[str] = Field(default=None, description="Stripe secret key")
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(default=None, description="Stripe webhook secret")
    PREMIUM_PRICE_USD: float = Field(default=3.99, description="Premium subscription price in USD")
    
    SUPPORTED_PLATFORMS: List[str] = Field(default=["youtube", "tiktok", "instagram"], description="Supported video platforms")

    WORKER_CONCURRENCY: int = 4
    WORKER_POOL: str = "prefork"
    TASK_TIMEOUT: int = 1800
    SOFT_TIMEOUT: int = 1500
    MAX_FILE_SIZE_MB: int = 500
    WORKER_BASE_DIR: str = "./worker_data"
    WORKER_TEMP_DIR: str = "./temp"
    WORKER_STORAGE_PATH: str = "./storage"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
    
    @validator('ADMIN_IDS', pre=True)
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        return v
    
    @validator('REQUIRED_CHANNELS', pre=True) 
    def parse_required_channels(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [x.strip() for x in v.split(",") if x.strip()]
        return v
    
    @validator('ADMIN_CORS_ORIGINS', pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v
    
    @validator('ENVIRONMENT')
    def validate_environment(cls, v):
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"Environment must be one of: {allowed}")
        return v
    
    @validator('LOG_LEVEL')
    def validate_log_level(cls, v):
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"Log level must be one of: {allowed}")
        return v.upper()
    
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
    
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"
    
    def get_database_url(self, async_driver: bool = True) -> str:
        """Возвращает URL базы с правильным драйвером"""
        base_url = self.DATABASE_URL
        if base_url.startswith("postgresql+"):
            base_url = "postgresql://" + base_url.split("+", 1)[1].split("://", 1)[1]
        
        if async_driver:
            return base_url.replace("postgresql://", "postgresql+asyncpg://")
        else:
            return base_url.replace("postgresql://", "postgresql+psycopg2://")
    
    def get_file_retention_hours(self, user_type: str) -> int:
        retention_map = {
            "free": self.FREE_FILE_RETENTION_HOURS,
            "trial": self.FREE_FILE_RETENTION_HOURS,
            "premium": self.PREMIUM_FILE_RETENTION_HOURS,
            "admin": self.ADMIN_FILE_RETENTION_HOURS,
        }
        return retention_map.get(user_type, self.FREE_FILE_RETENTION_HOURS)
    
    def get_max_file_size_mb(self, user_type: str) -> int:
        size_map = {
            "free": self.FREE_MAX_FILE_SIZE_MB,
            "trial": self.PREMIUM_MAX_FILE_SIZE_MB,
            "premium": self.PREMIUM_MAX_FILE_SIZE_MB,
            "admin": self.ADMIN_MAX_FILE_SIZE_MB,
        }
        return size_map.get(user_type, self.FREE_MAX_FILE_SIZE_MB)
    
    def get_daily_limit(self, user_type: str) -> int:
        limit_map = {
            "free": self.FREE_DAILY_LIMIT,
            "trial": self.TRIAL_DAILY_LIMIT,
            "premium": self.PREMIUM_DAILY_LIMIT,
            "admin": 999999,
        }
        return limit_map.get(user_type, self.FREE_DAILY_LIMIT)
    
    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.ADMIN_IDS or telegram_id == self.SUPER_ADMIN_ID


settings = Settings()


class DevelopmentSettings(Settings):
    DEBUG: bool = True
    DATABASE_ECHO: bool = True
    LOG_LEVEL: str = "DEBUG"
    API_RELOAD: bool = True


class ProductionSettings(Settings):
    DEBUG: bool = False
    DATABASE_ECHO: bool = False
    LOG_LEVEL: str = "INFO"
    API_RELOAD: bool = False
    

def get_settings() -> Settings:
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        return ProductionSettings()
    elif env == "development":
        return DevelopmentSettings()
    else:
        return Settings()


settings = get_settings()
