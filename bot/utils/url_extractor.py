"""
VideoBot Pro - URL Extractor
Утилиты для работы с URL видео
"""

import re
from typing import List, Optional, Tuple, Dict
from urllib.parse import urlparse, parse_qs
import structlog

logger = structlog.get_logger(__name__)

# Паттерны для различных платформ
URL_PATTERNS = {
    'youtube': [
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([\w-]+)',
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([\w-]+)',
        r'(?:https?://)?(?:www\.)?youtu\.be/([\w-]+)',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([\w-]+)',
        r'(?:https?://)?(?:www\.)?m\.youtube\.com/watch\?v=([\w-]+)'
    ],
    'tiktok': [
        r'(?:https?://)?(?:www\.)?tiktok\.com/@[\w.-]+/video/(\d+)',
        r'(?:https?://)?(?:www\.)?tiktok\.com/@[\w.-]+/video/(\d+)',
        r'(?:https?://)?vm\.tiktok\.com/([\w-]+)',
        r'(?:https?://)?(?:www\.)?vt\.tiktok\.com/([\w-]+)',
        r'(?:https?://)?(?:www\.)?tiktok\.com/t/([\w-]+)'
    ],
    'instagram': [
        r'(?:https?://)?(?:www\.)?instagram\.com/reel/([\w-]+)',
        r'(?:https?://)?(?:www\.)?instagram\.com/reels/([\w-]+)',
        r'(?:https?://)?(?:www\.)?instagram\.com/p/([\w-]+)',
        r'(?:https?://)?(?:www\.)?instagram\.com/tv/([\w-]+)',
        r'(?:https?://)?(?:www\.)?instagr\.am/p/([\w-]+)'
    ]
}


def extract_video_urls(text: str) -> List[str]:
    """
    Извлечь все поддерживаемые URL из текста
    
    Args:
        text: Текст для анализа
        
    Returns:
        Список найденных URL
    """
    urls = []
    
    # Общий паттерн для поиска любых URL
    general_url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    potential_urls = re.findall(general_url_pattern, text)
    
    for url in potential_urls:
        # Убираем возможные символы в конце URL
        url = re.sub(r'[.,;!?]+$', '', url)
        
        if validate_url(url):
            if url not in urls:  # Избегаем дубликатов
                urls.append(url)
    
    logger.debug(f"Extracted {len(urls)} URLs from text")
    return urls


def validate_url(url: str) -> bool:
    """
    Проверить, является ли URL поддерживаемым
    
    Args:
        url: URL для проверки
        
    Returns:
        True если URL поддерживается
    """
    if not url:
        return False
    
    # Нормализуем URL
    url = url.lower().strip()
    
    # Проверяем каждую платформу
    for platform, patterns in URL_PATTERNS.items():
        for pattern in patterns:
            if re.match(pattern, url):
                return True
    
    return False


def detect_platform(url: str) -> Optional[str]:
    """
    Определить платформу по URL
    
    Args:
        url: URL для анализа
        
    Returns:
        Название платформы или None
    """
    if not url:
        return None
    
    url = url.lower().strip()
    
    # Проверяем каждую платформу
    for platform, patterns in URL_PATTERNS.items():
        for pattern in patterns:
            if re.match(pattern, url):
                logger.debug(f"Detected platform: {platform} for URL: {url}")
                return platform
    
    # Дополнительная проверка по домену
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    if 'youtube.com' in domain or 'youtu.be' in domain:
        return 'youtube'
    elif 'tiktok.com' in domain:
        return 'tiktok'
    elif 'instagram.com' in domain or 'instagr.am' in domain:
        return 'instagram'
    
    logger.warning(f"Could not detect platform for URL: {url}")
    return None


def normalize_url(url: str) -> str:
    """
    Нормализовать URL к стандартному формату
    
    Args:
        url: URL для нормализации
        
    Returns:
        Нормализованный URL
    """
    if not url:
        return url
    
    # Добавляем схему если нет
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Убираем tracking параметры для YouTube
    if 'youtube.com' in url or 'youtu.be' in url:
        parsed = urlparse(url)
        if parsed.query:
            params = parse_qs(parsed.query)
            # Оставляем только необходимые параметры
            clean_params = {}
            if 'v' in params:
                clean_params['v'] = params['v'][0]
            if 't' in params:  # Временная метка
                clean_params['t'] = params['t'][0]
            
            if clean_params:
                query_string = '&'.join([f"{k}={v}" for k, v in clean_params.items()])
                url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query_string}"
            else:
                url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    
    # Убираем мобильные версии
    url = url.replace('m.youtube.com', 'youtube.com')
    url = url.replace('mobile.twitter.com', 'twitter.com')
    
    return url


def extract_video_id(url: str) -> Optional[Tuple[str, str]]:
    """
    Извлечь ID видео из URL
    
    Args:
        url: URL видео
        
    Returns:
        Кортеж (platform, video_id) или None
    """
    if not url:
        return None
    
    platform = detect_platform(url)
    if not platform:
        return None
    
    url = url.lower().strip()
    
    # Проходим по паттернам платформы
    for pattern in URL_PATTERNS[platform]:
        match = re.match(pattern, url)
        if match:
            video_id = match.group(1)
            return (platform, video_id)
    
    # Дополнительная логика для YouTube
    if platform == 'youtube':
        parsed = urlparse(url)
        if parsed.query:
            params = parse_qs(parsed.query)
            if 'v' in params:
                return ('youtube', params['v'][0])
    
    logger.warning(f"Could not extract video ID from URL: {url}")
    return None


def is_shorts_url(url: str) -> bool:
    """
    Проверить, является ли URL коротким видео (Shorts/Reels)
    
    Args:
        url: URL для проверки
        
    Returns:
        True если это короткое видео
    """
    if not url:
        return False
    
    url = url.lower()
    
    # YouTube Shorts
    if 'youtube.com/shorts/' in url:
        return True
    
    # Instagram Reels
    if 'instagram.com/reel' in url or 'instagram.com/reels' in url:
        return True
    
    # TikTok - все видео короткие по определению
    if 'tiktok.com' in url:
        return True
    
    return False


def clean_url_for_display(url: str, max_length: int = 50) -> str:
    """
    Очистить и укоротить URL для отображения пользователю
    
    Args:
        url: URL для очистки
        max_length: Максимальная длина
        
    Returns:
        Очищенный URL
    """
    if not url:
        return url
    
    # Убираем схему
    display_url = re.sub(r'^https?://', '', url)
    display_url = re.sub(r'^www\.', '', display_url)
    
    # Укорачиваем если слишком длинный
    if len(display_url) > max_length:
        display_url = display_url[:max_length-3] + '...'
    
    return display_url


def batch_validate_urls(urls: List[str]) -> Tuple[List[str], List[str]]:
    """
    Валидировать список URL
    
    Args:
        urls: Список URL для проверки
        
    Returns:
        Кортеж (valid_urls, invalid_urls)
    """
    valid_urls = []
    invalid_urls = []
    
    for url in urls:
        if validate_url(url):
            valid_urls.append(normalize_url(url))
        else:
            invalid_urls.append(url)
    
    logger.info(f"Batch validation: {len(valid_urls)} valid, {len(invalid_urls)} invalid")
    return valid_urls, invalid_urls


def group_urls_by_platform(urls: List[str]) -> Dict[str, List[str]]:
    """
    Сгруппировать URL по платформам
    
    Args:
        urls: Список URL
        
    Returns:
        Словарь {platform: [urls]}
    """
    grouped = {}
    
    for url in urls:
        platform = detect_platform(url)
        if platform:
            if platform not in grouped:
                grouped[platform] = []
            grouped[platform].append(url)
    
    return grouped