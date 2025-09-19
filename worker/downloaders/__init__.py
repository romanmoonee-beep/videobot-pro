"""
VideoBot Pro - Downloaders Package
Пакет для скачивания видео с различных платформ
"""

# Базовые классы
from .base import (
    BaseDownloader,
    DownloadResult,
    VideoInfo,
    DownloadError,
    UnsupportedPlatformError,
    VideoNotFoundError,
    DownloadTimeoutError,
    QualityNotAvailableError,
)

# Реализации downloaders
from .youtube import YouTubeDownloader
from .tiktok import TikTokDownloader
from .instagram import InstagramDownloader

# Фабрика и утилиты
from .factory import (
    DownloaderFactory,
    download_video,
    get_video_info,
    get_available_qualities,
)

import structlog

logger = structlog.get_logger(__name__)

# Версия пакета downloaders
__version__ = "2.1.0"

# Поддерживаемые платформы
SUPPORTED_PLATFORMS = [
    "youtube",
    "tiktok", 
    "instagram",
]

# Поддерживаемые качества
SUPPORTED_QUALITIES = [
    "4k", "2160p",
    "1440p", 
    "1080p",
    "720p",
    "480p",
    "360p",
    "best",
    "worst",
]

# Поддерживаемые форматы
SUPPORTED_FORMATS = [
    "mp4",
    "webm",
    "mp3",
    "m4a",
]

def get_platform_downloaders():
    """Получить словарь всех доступных downloaders"""
    return {
        'youtube': YouTubeDownloader,
        'tiktok': TikTokDownloader,
        'instagram': InstagramDownloader,
    }

def validate_quality(quality: str) -> bool:
    """Проверить поддерживается ли качество"""
    return quality.lower() in [q.lower() for q in SUPPORTED_QUALITIES]

def validate_format(format_str: str) -> bool:
    """Проверить поддерживается ли формат"""
    return format_str.lower() in [f.lower() for f in SUPPORTED_FORMATS]

def get_downloader_stats():
    """Получить статистику downloaders"""
    stats = {
        'total_platforms': len(SUPPORTED_PLATFORMS),
        'platforms': SUPPORTED_PLATFORMS,
        'supported_qualities': SUPPORTED_QUALITIES,
        'supported_formats': SUPPORTED_FORMATS,
        'factory_stats': DownloaderFactory.get_statistics(),
    }
    
    # Тестируем доступность downloaders
    try:
        test_results = DownloaderFactory.test_downloaders()
        stats['test_results'] = test_results
        stats['working_platforms'] = [p for p, working in test_results.items() if working]
    except Exception as e:
        logger.error(f"Error testing downloaders: {e}")
        stats['test_results'] = {}
        stats['working_platforms'] = []
    
    return stats

def cleanup_downloaders():
    """Очистка всех downloaders"""
    try:
        DownloaderFactory.cleanup_all()
        logger.info("All downloaders cleaned up successfully")
    except Exception as e:
        logger.error(f"Error cleaning up downloaders: {e}")

def initialize_downloaders():
    """Инициализация пакета downloaders"""
    logger.info(f"Initializing VideoBot Pro Downloaders v{__version__}")
    logger.info(f"Supported platforms: {', '.join(SUPPORTED_PLATFORMS)}")
    
    # Проверяем доступность всех downloaders
    test_results = DownloaderFactory.test_downloaders()
    working_count = sum(1 for working in test_results.values() if working)
    
    logger.info(f"Working downloaders: {working_count}/{len(SUPPORTED_PLATFORMS)}")
    
    for platform, working in test_results.items():
        status = "✅ Working" if working else "❌ Failed"
        logger.info(f"  {platform}: {status}")
    
    if working_count == 0:
        logger.error("No working downloaders found!")
    elif working_count < len(SUPPORTED_PLATFORMS):
        logger.warning("Some downloaders are not working properly")
    else:
        logger.info("All downloaders initialized successfully")
    
    return test_results

# Convenience functions для быстрого использования

def quick_download(url: str, output_dir: str = "./downloads", 
                  quality: str = "best", filename: str = None) -> DownloadResult:
    """
    Быстрое скачивание видео с минимальными настройками
    
    Args:
        url: URL видео
        output_dir: Директория для сохранения
        quality: Качество видео
        filename: Имя файла (опционально)
    
    Returns:
        Результат скачивания
    """
    import os
    from pathlib import Path
    
    # Создаем директорию если не существует
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Получаем информацию о видео
    video_info = get_video_info(url)
    
    # Генерируем имя файла если не указано
    if not filename:
        safe_title = "".join(c for c in video_info.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"{safe_title[:50]}.{video_info.format_info.get('ext', 'mp4')}"
    
    output_path = os.path.join(output_dir, filename)
    
    # Скачиваем
    return download_video(url, output_path, quality)

def batch_download(urls: list, output_dir: str = "./downloads",
                  quality: str = "best", max_concurrent: int = 3) -> list:
    """
    Массовое скачивание видео
    
    Args:
        urls: Список URL для скачивания
        output_dir: Директория для сохранения
        quality: Качество видео
        max_concurrent: Максимальное количество одновременных загрузок
    
    Returns:
        Список результатов скачивания
    """
    import asyncio
    import concurrent.futures
    from pathlib import Path
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results = []
    
    def download_single(url):
        try:
            return quick_download(url, output_dir, quality)
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return DownloadResult(
                success=False,
                error=str(e),
                file_path=None,
                file_size=0,
                duration=0,
                quality=quality,
                format="unknown",
                video_info=None
            )
    
    # Используем ThreadPoolExecutor для параллельного скачивания
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        future_to_url = {executor.submit(download_single, url): url for url in urls}
        
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"Completed download: {url}")
            except Exception as e:
                logger.error(f"Exception downloading {url}: {e}")
                results.append(DownloadResult(
                    success=False,
                    error=str(e),
                    file_path=None,
                    file_size=0,
                    duration=0,
                    quality=quality,
                    format="unknown",
                    video_info=None
                ))
    
    return results

def get_video_metadata(url: str) -> dict:
    """
    Получить только метаданные видео (без скачивания)
    
    Args:
        url: URL видео
    
    Returns:
        Словарь с метаданными
    """
    try:
        video_info = get_video_info(url)
        return {
            'id': video_info.id,
            'title': video_info.title,
            'description': video_info.description,
            'uploader': video_info.uploader,
            'duration': video_info.duration,
            'view_count': video_info.view_count,
            'like_count': video_info.like_count,
            'upload_date': video_info.upload_date.isoformat() if video_info.upload_date else None,
            'thumbnail_url': video_info.thumbnail_url,
            'platform': video_info.platform,
            'quality': video_info.quality,
            'format_info': video_info.format_info,
            'available_qualities': get_available_qualities(url),
        }
    except Exception as e:
        logger.error(f"Error getting metadata for {url}: {e}")
        return {'error': str(e)}

# Экспорт всех публичных компонентов
__all__ = [
    # Базовые классы
    'BaseDownloader',
    'DownloadResult', 
    'VideoInfo',
    'DownloadError',
    'UnsupportedPlatformError',
    'VideoNotFoundError',
    'DownloadTimeoutError',
    'QualityNotAvailableError',
    
    # Downloaders
    'YouTubeDownloader',
    'TikTokDownloader',
    'InstagramDownloader',
    
    # Фабрика и основные функции
    'DownloaderFactory',
    'download_video',
    'get_video_info',
    'get_available_qualities',
    
    # Утилиты
    'quick_download',
    'batch_download',
    'get_video_metadata',
    'get_downloader_stats',
    'cleanup_downloaders',
    'initialize_downloaders',
    'validate_quality',
    'validate_format',
    
    # Константы
    'SUPPORTED_PLATFORMS',
    'SUPPORTED_QUALITIES', 
    'SUPPORTED_FORMATS',
    '__version__',
]

# Автоматическая инициализация при импорте
try:
    _init_results = initialize_downloaders()
    logger.debug("Downloaders package initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize downloaders package: {e}")

# Информация о пакете
def print_package_info():
    """Вывести информацию о пакете"""
    print("=" * 60)
    print(f"VideoBot Pro Downloaders v{__version__}")
    print("=" * 60)
    print(f"Supported Platforms: {', '.join(SUPPORTED_PLATFORMS)}")
    print(f"Supported Qualities: {', '.join(SUPPORTED_QUALITIES)}")
    print(f"Supported Formats: {', '.join(SUPPORTED_FORMATS)}")
    print("-" * 60)
    
    stats = get_downloader_stats()
    test_results = stats.get('test_results', {})
    
    print("Platform Status:")
    for platform in SUPPORTED_PLATFORMS:
        status = "✅ Working" if test_results.get(platform, False) else "❌ Failed"
        print(f"  {platform.ljust(12)}: {status}")
    
    print("-" * 60)
    print(f"Factory Stats: {stats['factory_stats']}")
    print("=" * 60)

# Функция для проверки здоровья системы
def health_check() -> dict:
    """Проверка здоровья downloaders системы"""
    health = {
        'status': 'healthy',
        'timestamp': logger.info.__globals__.get('datetime', __import__('datetime')).datetime.utcnow().isoformat(),
        'version': __version__,
        'issues': []
    }
    
    try:
        # Тестируем каждый downloader
        test_results = DownloaderFactory.test_downloaders()
        
        failed_platforms = [p for p, working in test_results.items() if not working]
        if failed_platforms:
            health['status'] = 'degraded'
            health['issues'].extend([f"{p}_downloader_failed" for p in failed_platforms])
        
        health['platforms'] = {
            'total': len(SUPPORTED_PLATFORMS),
            'working': len([p for p, working in test_results.items() if working]),
            'failed': len(failed_platforms),
            'details': test_results
        }
        
        # Проверяем доступность зависимостей
        try:
            import yt_dlp
            health['dependencies'] = health.get('dependencies', {})
            health['dependencies']['yt_dlp'] = 'available'
        except ImportError:
            health['issues'].append('yt_dlp_missing')
            health['status'] = 'unhealthy'
        
        if len(failed_platforms) == len(SUPPORTED_PLATFORMS):
            health['status'] = 'unhealthy'
            health['issues'].append('all_downloaders_failed')
        
    except Exception as e:
        health['status'] = 'unhealthy'
        health['issues'].append(f'health_check_error: {str(e)}')
    
    return health