"""
VideoBot Pro - Downloader Factory
Фабрика для создания downloaders по платформе
"""

import re
from typing import Optional, Dict, Type, List
import structlog

from .base import BaseDownloader, DownloadError
from .youtube import YouTubeDownloader
from .tiktok import TikTokDownloader  
from .instagram import InstagramDownloader

logger = structlog.get_logger(__name__)

class DownloaderFactory:
    """Фабрика для создания downloaders"""
    
    # Реестр downloaders
    _downloaders: Dict[str, Type[BaseDownloader]] = {
        'youtube': YouTubeDownloader,
        'tiktok': TikTokDownloader,
        'instagram': InstagramDownloader,
    }
    
    # Кеш экземпляров downloaders
    _instances: Dict[str, BaseDownloader] = {}
    
    @classmethod
    def register_downloader(cls, platform: str, downloader_class: Type[BaseDownloader]):
        """Регистрация нового downloader'а"""
        if not issubclass(downloader_class, BaseDownloader):
            raise ValueError(f"Downloader must inherit from BaseDownloader")
        
        cls._downloaders[platform.lower()] = downloader_class
        logger.info(f"Registered downloader for platform: {platform}")
    
    @classmethod
    def get_downloader(cls, platform: str, reuse_instance: bool = True) -> BaseDownloader:
        """
        Получить downloader для платформы
        
        Args:
            platform: Название платформы
            reuse_instance: Использовать кешированный экземпляр
            
        Returns:
            Экземпляр downloader'а
            
        Raises:
            DownloadError: Если платформа не поддерживается
        """
        platform = platform.lower()
        
        if platform not in cls._downloaders:
            raise DownloadError(f"Unsupported platform: {platform}")
        
        # Возвращаем кешированный экземпляр
        if reuse_instance and platform in cls._instances:
            return cls._instances[platform]
        
        # Создаем новый экземпляр
        downloader_class = cls._downloaders[platform]
        downloader = downloader_class()
        
        if reuse_instance:
            cls._instances[platform] = downloader
        
        logger.debug(f"Created downloader for platform: {platform}")
        return downloader
    
    @classmethod
    def detect_platform(cls, url: str) -> Optional[str]:
        """
        Определить платформу по URL
        
        Args:
            url: URL для анализа
            
        Returns:
            Название платформы или None
        """
        url = url.lower().strip()
        
        # Проверяем каждый зарегистрированный downloader
        for platform, downloader_class in cls._downloaders.items():
            try:
                # Создаем временный экземпляр для проверки
                downloader = downloader_class()
                if downloader.can_download(url):
                    return platform
            except Exception as e:
                logger.warning(f"Error checking platform {platform}: {e}")
                continue
        
        return None
    
    @classmethod
    def get_downloader_for_url(cls, url: str) -> BaseDownloader:
        """
        Получить подходящий downloader для URL
        
        Args:
            url: URL для скачивания
            
        Returns:
            Экземпляр downloader'а
            
        Raises:
            DownloadError: Если платформа не поддерживается
        """
        platform = cls.detect_platform(url)
        
        if not platform:
            raise DownloadError(f"Unsupported URL: {url}")
        
        return cls.get_downloader(platform)
    
    @classmethod
    def get_supported_platforms(cls) -> List[str]:
        """Получить список поддерживаемых платформ"""
        return list(cls._downloaders.keys())
    
    @classmethod
    def is_supported_url(cls, url: str) -> bool:
        """Проверить поддерживается ли URL"""
        return cls.detect_platform(url) is not None
    
    @classmethod
    def validate_url(cls, url: str) -> bool:
        """
        Валидация URL
        
        Args:
            url: URL для проверки
            
        Returns:
            True если URL валидный
        """
        if not url or not isinstance(url, str):
            return False
        
        # Базовая проверка URL
        url_pattern = re.compile(
            r'^https?://'  # http:// или https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(url):
            return False
        
        # Проверяем поддержку платформы
        return cls.is_supported_url(url)
    
    @classmethod
    def get_platform_info(cls, platform: str) -> Dict[str, any]:
        """
        Получить информацию о платформе
        
        Args:
            platform: Название платформы
            
        Returns:
            Словарь с информацией о платформе
        """
        platform = platform.lower()
        
        if platform not in cls._downloaders:
            return {}
        
        downloader_class = cls._downloaders[platform]
        
        # Создаем временный экземпляр для получения информации
        try:
            downloader = downloader_class()
            return {
                'platform': platform,
                'class_name': downloader_class.__name__,
                'supported_qualities': getattr(downloader, 'SUPPORTED_QUALITIES', ['best']),
                'supported_formats': getattr(downloader, 'SUPPORTED_FORMATS', ['mp4']),
                'max_file_size': getattr(downloader, 'MAX_FILE_SIZE', None),
                'requires_auth': getattr(downloader, 'REQUIRES_AUTH', False),
                'description': downloader_class.__doc__ or f"Downloader for {platform}",
            }
        except Exception as e:
            logger.error(f"Error getting platform info for {platform}: {e}")
            return {'platform': platform, 'error': str(e)}
    
    @classmethod
    def cleanup_all(cls):
        """Очистка всех кешированных downloaders"""
        for platform, downloader in cls._instances.items():
            try:
                downloader.cleanup()
                logger.debug(f"Cleaned up downloader for {platform}")
            except Exception as e:
                logger.warning(f"Error cleaning up {platform} downloader: {e}")
        
        cls._instances.clear()
    
    @classmethod
    def test_downloaders(cls) -> Dict[str, bool]:
        """
        Тестирование всех downloaders
        
        Returns:
            Словарь с результатами тестов
        """
        results = {}
        
        for platform in cls._downloaders:
            try:
                downloader = cls.get_downloader(platform, reuse_instance=False)
                
                # Базовый тест создания экземпляра
                if hasattr(downloader, 'can_download'):
                    results[platform] = True
                else:
                    results[platform] = False
                    
            except Exception as e:
                logger.error(f"Test failed for {platform}: {e}")
                results[platform] = False
        
        return results
    
    @classmethod
    def get_statistics(cls) -> Dict[str, any]:
        """
        Получить статистику downloaders
        
        Returns:
            Статистика использования
        """
        return {
            'total_platforms': len(cls._downloaders),
            'platforms': list(cls._downloaders.keys()),
            'cached_instances': len(cls._instances),
            'cached_platforms': list(cls._instances.keys()),
        }

# Вспомогательные функции для удобства использования

def download_video(url: str, output_path: str, quality: str = "best", 
                  progress_callback=None) -> 'DownloadResult':
    """
    Удобная функция для скачивания видео
    
    Args:
        url: URL видео
        output_path: Путь для сохранения
        quality: Качество видео
        progress_callback: Callback для прогресса
        
    Returns:
        Результат скачивания
    """
    downloader = DownloaderFactory.get_downloader_for_url(url)
    video_info = downloader.get_video_info(url)
    return downloader.download_video(video_info, output_path, quality, progress_callback)

def get_video_info(url: str) -> 'VideoInfo':
    """
    Удобная функция для получения информации о видео
    
    Args:
        url: URL видео
        
    Returns:
        Информация о видео
    """
    downloader = DownloaderFactory.get_downloader_for_url(url)
    return downloader.get_video_info(url)

def get_available_qualities(url: str) -> List[str]:
    """
    Получить доступные качества для видео
    
    Args:
        url: URL видео
        
    Returns:
        Список доступных качеств
    """
    downloader = DownloaderFactory.get_downloader_for_url(url)
    return downloader.get_available_qualities(url)

# Автоматическая регистрация всех downloaders при импорте модуля
def _register_default_downloaders():
    """Регистрация стандартных downloaders"""
    try:
        # Downloaders регистрируются автоматически через свои PLATFORM атрибуты
        for platform, downloader_class in DownloaderFactory._downloaders.items():
            logger.debug(f"Default downloader registered: {platform}")
    except Exception as e:
        logger.error(f"Error registering default downloaders: {e}")

# Выполняем регистрацию при импорте
_register_default_downloaders()

# Экспорт основных функций
__all__ = [
    'DownloaderFactory',
    'download_video',
    'get_video_info', 
    'get_available_qualities',
]