"""
VideoBot Pro - URL Filter
Фильтр для проверки URL в сообщениях
"""

import re
from typing import Union, List, Optional
from aiogram import types
from aiogram.filters import BaseFilter

from bot.utils.url_extractor import extract_video_urls, validate_url, detect_platform

class URLFilter(BaseFilter):
    """Фильтр для сообщений с URL"""
    
    def __init__(
        self, 
        platforms: Optional[List[str]] = None,
        min_urls: int = 1,
        max_urls: int = 20,
        require_supported: bool = True
    ):
        """
        Инициализация фильтра URL
        
        Args:
            platforms: Список поддерживаемых платформ
            min_urls: Минимальное количество URL
            max_urls: Максимальное количество URL
            require_supported: Требовать поддерживаемые URL
        """
        self.platforms = platforms or ['youtube', 'tiktok', 'instagram']
        self.min_urls = min_urls
        self.max_urls = max_urls
        self.require_supported = require_supported
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка сообщения на наличие URL"""
        if not message.text and not message.caption:
            return False
        
        text = message.text or message.caption or ""
        
        # Извлекаем URL из текста
        urls = extract_video_urls(text)
        
        if not urls:
            return False
        
        # Проверяем количество URL
        if len(urls) < self.min_urls or len(urls) > self.max_urls:
            return False
        
        # Проверяем поддерживаемые URL
        if self.require_supported:
            valid_urls = []
            platforms_found = []
            
            for url in urls:
                if validate_url(url):
                    platform = detect_platform(url)
                    if platform in self.platforms:
                        valid_urls.append(url)
                        platforms_found.append(platform)
            
            if not valid_urls:
                return False
            
            return {
                'urls': valid_urls,
                'platforms': platforms_found,
                'urls_count': len(valid_urls),
                'all_urls': urls,
                'invalid_count': len(urls) - len(valid_urls)
            }
        
        return {
            'urls': urls,
            'urls_count': len(urls)
        }

class PlatformFilter(BaseFilter):
    """Фильтр для конкретной платформы"""
    
    def __init__(self, platform: str):
        """
        Args:
            platform: Название платформы (youtube, tiktok, instagram)
        """
        self.platform = platform.lower()
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка сообщения на URL конкретной платформы"""
        if not message.text and not message.caption:
            return False
        
        text = message.text or message.caption or ""
        urls = extract_video_urls(text)
        
        if not urls:
            return False
        
        platform_urls = []
        for url in urls:
            if validate_url(url):
                platform = detect_platform(url)
                if platform == self.platform:
                    platform_urls.append(url)
        
        if not platform_urls:
            return False
        
        return {
            'platform': self.platform,
            'urls': platform_urls,
            'urls_count': len(platform_urls)
        }

class BatchFilter(BaseFilter):
    """Фильтр для batch загрузок (много URL)"""
    
    def __init__(self, min_batch_size: int = 5):
        """
        Args:
            min_batch_size: Минимальный размер batch
        """
        self.min_batch_size = min_batch_size
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка на batch загрузку"""
        if not message.text and not message.caption:
            return False
        
        text = message.text or message.caption or ""
        urls = extract_video_urls(text)
        
        if len(urls) < self.min_batch_size:
            return False
        
        # Группируем по платформам
        platforms_count = {}
        valid_urls = []
        
        for url in urls:
            if validate_url(url):
                platform = detect_platform(url)
                platforms_count[platform] = platforms_count.get(platform, 0) + 1
                valid_urls.append(url)
        
        return {
            'urls': valid_urls,
            'urls_count': len(valid_urls),
            'platforms_count': platforms_count,
            'is_batch': True,
            'mixed_platforms': len(platforms_count) > 1
        }

class SingleURLFilter(BaseFilter):
    """Фильтр для одиночного URL"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка на одиночный URL"""
        if not message.text and not message.caption:
            return False
        
        text = message.text or message.caption or ""
        urls = extract_video_urls(text)
        
        # Должен быть ровно один валидный URL
        valid_urls = [url for url in urls if validate_url(url)]
        
        if len(valid_urls) != 1:
            return False
        
        url = valid_urls[0]
        platform = detect_platform(url)
        
        return {
            'url': url,
            'platform': platform,
            'is_single': True
        }

class YouTubeFilter(PlatformFilter):
    """Фильтр для YouTube URL"""
    def __init__(self):
        super().__init__('youtube')

class TikTokFilter(PlatformFilter):
    """Фильтр для TikTok URL"""
    def __init__(self):
        super().__init__('tiktok')

class InstagramFilter(PlatformFilter):
    """Фильтр для Instagram URL"""
    def __init__(self):
        super().__init__('instagram')

class ShortsFilter(BaseFilter):
    """Фильтр для коротких видео (Shorts, Reels)"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка на короткие видео"""
        if not message.text and not message.caption:
            return False
        
        text = message.text or message.caption or ""
        
        # Паттерны для коротких видео
        shorts_patterns = [
            r'youtube\.com/shorts/',
            r'instagram\.com/reel',
            r'tiktok\.com',
            r'vm\.tiktok\.com'
        ]
        
        shorts_urls = []
        for pattern in shorts_patterns:
            matches = re.findall(rf'https?://[^\s]*{pattern}[^\s]*', text, re.IGNORECASE)
            shorts_urls.extend(matches)
        
        if not shorts_urls:
            return False
        
        return {
            'shorts_urls': shorts_urls,
            'shorts_count': len(shorts_urls),
            'is_shorts': True
        }

# Предопределенные экземпляры фильтров для удобства
has_url = URLFilter()
has_single_url = SingleURLFilter() 
has_batch_urls = BatchFilter()
has_youtube = YouTubeFilter()
has_tiktok = TikTokFilter()
has_instagram = InstagramFilter()
has_shorts = ShortsFilter()

# Комбинированные фильтры
def has_supported_urls(min_urls: int = 1, max_urls: int = 20) -> URLFilter:
    """Фильтр для поддерживаемых URL с настраиваемыми лимитами"""
    return URLFilter(min_urls=min_urls, max_urls=max_urls)

def has_platform_urls(*platforms: str) -> URLFilter:
    """Фильтр для URL конкретных платформ"""
    return URLFilter(platforms=list(platforms))

def has_batch_from_platform(platform: str, min_size: int = 5) -> BaseFilter:
    """Фильтр для batch с конкретной платформы"""
    
    class PlatformBatchFilter(BaseFilter):
        async def __call__(self, message: types.Message) -> Union[bool, dict]:
            text = message.text or message.caption or ""
            urls = extract_video_urls(text)
            
            platform_urls = [
                url for url in urls 
                if validate_url(url) and detect_platform(url) == platform
            ]
            
            if len(platform_urls) < min_size:
                return False
            
            return {
                'platform': platform,
                'urls': platform_urls,
                'urls_count': len(platform_urls),
                'is_batch': True
            }
    
    return PlatformBatchFilter()