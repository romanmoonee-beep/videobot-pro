"""
VideoBot Pro - Worker Configuration
Конфигурация для worker процессов
"""

import os
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass

from shared.config.settings import settings

@dataclass
class WorkerConfig:
    """Конфигурация worker'а"""
    
    # Основные настройки
    worker_name: str = "videobot-worker"
    worker_concurrency: int = settings.CELERY_WORKER_CONCURRENCY
    worker_pool: str = "prefork"  # prefork, eventlet, gevent
    
    # Временные ограничения
    task_timeout: int = settings.CELERY_TASK_TIMEOUT
    soft_timeout: int = settings.CELERY_TASK_TIMEOUT - 60
    download_timeout: int = 1800  # 30 минут на скачивание
    
    # Ограничения ресурсов
    max_memory_per_child: int = 1024 * 1024 * 512  # 512MB
    max_tasks_per_child: int = 100
    prefetch_multiplier: int = 1
    
    # Директории
    temp_dir: Path = Path("/tmp/videobot")
    download_dir: Path = Path("/tmp/videobot/downloads")
    processing_dir: Path = Path("/tmp/videobot/processing")
    
    # Качество и форматы
    default_quality: str = "720p"
    fallback_quality: str = "480p"
    supported_formats: List[str] = None
    max_file_size_mb: int = 2048  # 2GB
    
    # Мониторинг
    enable_monitoring: bool = True
    metrics_port: int = 9091
    health_check_interval: int = 30
    
    # Retry настройки
    max_retries: int = 3
    retry_delay: int = 60  # секунды
    exponential_backoff: bool = True
    
    # CDN и storage
    cdn_upload_enabled: bool = True
    cdn_upload_timeout: int = 300
    storage_cleanup_enabled: bool = True
    
    # Безопасность
    validate_urls: bool = True
    scan_for_malware: bool = False
    max_url_length: int = 2000
    
    def __post_init__(self):
        """Пост-инициализация для настройки"""
        if self.supported_formats is None:
            self.supported_formats = ["mp4", "webm", "mp3"]
            
        # Создаем директории если их нет
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.processing_dir.mkdir(parents=True, exist_ok=True)
        
        # Переопределяем из переменных окружения
        self.worker_concurrency = int(os.getenv("WORKER_CONCURRENCY", self.worker_concurrency))
        self.max_file_size_mb = int(os.getenv("MAX_FILE_SIZE_MB", self.max_file_size_mb))

class DownloaderConfig:
    """Конфигурация для downloaders"""
    
    # YouTube настройки
    YOUTUBE_CONFIG = {
        "extract_flat": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "ignoreerrors": True,
        "no_warnings": True,
        "extractaudio": False,
        "audioformat": "mp3",
        "audioquality": "192",
        "format": "best[height<=?{quality}][ext=mp4]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],
        "cookiefile": None,  # Путь к cookies если нужно
        "user_agent": settings.USER_AGENT,
        "socket_timeout": 60,
        "retries": 3,
    }
    
    # TikTok настройки
    TIKTOK_CONFIG = {
        "extract_flat": False,
        "writesubtitles": False,
        "ignoreerrors": True,
        "no_warnings": True,
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15",
        "http_headers": {
            "Referer": "https://www.tiktok.com/",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "extractor_args": {
            "tiktok": {
                "webpage_download": True,
            }
        },
        "socket_timeout": 30,
        "retries": 5,
    }
    
    # Instagram настройки
    INSTAGRAM_CONFIG = {
        "extract_flat": False,
        "writesubtitles": False,
        "ignoreerrors": True,
        "no_warnings": True,
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "user_agent": "Instagram 123.0.0.21.114 (iPhone; CPU iPhone OS 13_3 like Mac OS X)",
        "http_headers": {
            "Accept-Language": "en-US,en;q=0.9",
        },
        "socket_timeout": 45,
        "retries": 3,
    }
    
    @classmethod
    def get_config_for_platform(cls, platform: str, quality: str = "720p") -> Dict[str, Any]:
        """Получить конфигурацию для платформы"""
        configs = {
            "youtube": cls.YOUTUBE_CONFIG.copy(),
            "tiktok": cls.TIKTOK_CONFIG.copy(),
            "instagram": cls.INSTAGRAM_CONFIG.copy(),
        }
        
        config = configs.get(platform, {})
        
        # Настраиваем качество для YouTube
        if platform == "youtube" and "format" in config:
            quality_num = quality.replace("p", "") if quality.endswith("p") else quality
            config["format"] = config["format"].format(quality=quality_num)
        
        return config

class StorageConfig:
    """Конфигурация для storage providers"""
    
    # Wasabi S3 (основное хранилище)
    WASABI_CONFIG = {
        "endpoint_url": settings.WASABI_ENDPOINT,
        "aws_access_key_id": settings.WASABI_ACCESS_KEY,
        "aws_secret_access_key": settings.WASABI_SECRET_KEY,
        "region_name": settings.WASABI_REGION,
        "bucket_name": settings.WASABI_BUCKET_NAME,
        "use_ssl": True,
        "verify": True,
        "timeout": 300,
        "max_pool_connections": 50,
    }
    
    # Backblaze B2 (backup)
    BACKBLAZE_CONFIG = {
        "key_id": settings.B2_KEY_ID,
        "application_key": settings.B2_APPLICATION_KEY,
        "bucket_name": settings.B2_BUCKET_NAME,
        "timeout": 300,
    }
    
    # DigitalOcean Spaces
    DIGITALOCEAN_CONFIG = {
        "endpoint_url": "https://fra1.digitaloceanspaces.com",  # Можно вынести в settings
        "aws_access_key_id": os.getenv("DO_SPACES_KEY", ""),
        "aws_secret_access_key": os.getenv("DO_SPACES_SECRET", ""),
        "region_name": "fra1",
        "bucket_name": os.getenv("DO_SPACES_BUCKET", "videobot-files"),
    }
    
    # Локальное хранилище
    LOCAL_CONFIG = {
        "base_path": Path("/var/www/videobot/files"),
        "create_subdirs": True,
        "permissions": 0o644,
        "url_prefix": "https://files.videobot.com",
    }

class ProcessorConfig:
    """Конфигурация для процессоров"""
    
    # FFmpeg настройки
    FFMPEG_CONFIG = {
        "binary_path": "ffmpeg",
        "audio_codec": "aac",
        "video_codec": "libx264",
        "audio_bitrate": "128k",
        "video_bitrate": "1000k",
        "preset": "fast",
        "tune": "zerolatency",
        "profile": "baseline",
        "level": "3.0",
        "threads": 2,
    }
    
    # Настройки thumbnail
    THUMBNAIL_CONFIG = {
        "width": 320,
        "height": 180,
        "quality": 85,
        "format": "jpg",
        "seek_time": "00:00:03",  # Берем кадр с 3-й секунды
    }
    
    # Оптимизация качества
    QUALITY_CONFIG = {
        "4k": {"width": 3840, "height": 2160, "bitrate": "8000k"},
        "2160p": {"width": 3840, "height": 2160, "bitrate": "8000k"},
        "1440p": {"width": 2560, "height": 1440, "bitrate": "4000k"},
        "1080p": {"width": 1920, "height": 1080, "bitrate": "2500k"},
        "720p": {"width": 1280, "height": 720, "bitrate": "1500k"},
        "480p": {"width": 854, "height": 480, "bitrate": "800k"},
        "360p": {"width": 640, "height": 360, "bitrate": "400k"},
    }

# Глобальные экземпляры конфигураций
worker_config = WorkerConfig()
downloader_config = DownloaderConfig()
storage_config = StorageConfig()
processor_config = ProcessorConfig()

# Функции для получения конфигураций
def get_worker_config() -> WorkerConfig:
    """Получить конфигурацию worker'а"""
    return worker_config

def get_downloader_config(platform: str, quality: str = "720p") -> Dict[str, Any]:
    """Получить конфигурацию downloader'а"""
    return downloader_config.get_config_for_platform(platform, quality)

def get_storage_config(provider: str) -> Dict[str, Any]:
    """Получить конфигурацию storage provider'а"""
    configs = {
        "wasabi": storage_config.WASABI_CONFIG,
        "backblaze": storage_config.BACKBLAZE_CONFIG,
        "digitalocean": storage_config.DIGITALOCEAN_CONFIG,
        "local": storage_config.LOCAL_CONFIG,
    }
    return configs.get(provider, {})

def get_processor_config(processor_type: str = "ffmpeg") -> Dict[str, Any]:
    """Получить конфигурацию процессора"""
    configs = {
        "ffmpeg": processor_config.FFMPEG_CONFIG,
        "thumbnail": processor_config.THUMBNAIL_CONFIG,
        "quality": processor_config.QUALITY_CONFIG,
    }
    return configs.get(processor_type, {})

def validate_config() -> List[str]:
    """Валидация конфигурации worker'а"""
    errors = []
    
    # Проверяем директории
    if not worker_config.temp_dir.exists():
        errors.append(f"Temp directory does not exist: {worker_config.temp_dir}")
    
    # Проверяем доступность FFmpeg
    import shutil
    if not shutil.which("ffmpeg"):
        errors.append("FFmpeg not found in PATH")
    
    # Проверяем настройки Celery
    if not settings.CELERY_BROKER_URL:
        errors.append("CELERY_BROKER_URL not configured")
    
    # Проверяем storage настройки
    if not settings.WASABI_ACCESS_KEY:
        errors.append("Wasabi credentials not configured")
    
    return errors

def print_config_summary():
    """Выводит сводку конфигурации"""
    print("=" * 50)
    print("VideoBot Pro Worker Configuration")
    print("=" * 50)
    print(f"Worker Name: {worker_config.worker_name}")
    print(f"Concurrency: {worker_config.worker_concurrency}")
    print(f"Pool Type: {worker_config.worker_pool}")
    print(f"Task Timeout: {worker_config.task_timeout}s")
    print(f"Temp Directory: {worker_config.temp_dir}")
    print(f"Max File Size: {worker_config.max_file_size_mb}MB")
    print(f"CDN Upload: {'Enabled' if worker_config.cdn_upload_enabled else 'Disabled'}")
    print(f"Monitoring: {'Enabled' if worker_config.enable_monitoring else 'Disabled'}")
    
    # Проверяем конфигурацию
    errors = validate_config()
    if errors:
        print("\n⚠️  Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n✅ Configuration is valid")
    
    print("=" * 50)