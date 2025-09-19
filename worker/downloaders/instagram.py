"""
VideoBot Pro - Instagram Downloader
Загрузчик для Instagram (посты, reels, stories)
"""

import re
import json
import requests
import structlog
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, parse_qs
from datetime import datetime

from .base import BaseDownloader, DownloadResult, VideoInfo, DownloadError
from worker.config import get_downloader_config

logger = structlog.get_logger(__name__)

class InstagramDownloader(BaseDownloader):
    """Downloader для Instagram"""
    
    PLATFORM = "instagram"
    
    # Паттерны URL для Instagram
    URL_PATTERNS = [
        r'https?://(?:www\.)?instagram\.com/p/([^/?#&]+)',
        r'https?://(?:www\.)?instagram\.com/reel/([^/?#&]+)',
        r'https?://(?:www\.)?instagram\.com/tv/([^/?#&]+)',
        r'https?://(?:www\.)?instagram\.com/stories/([^/?#&]+)/([^/?#&]+)',
    ]
    
    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self._setup_session()
    
    def _setup_session(self):
        """Настройка сессии для Instagram"""
        self.session.headers.update({
            'User-Agent': 'Instagram 123.0.0.21.114 (iPhone; CPU iPhone OS 13_3 like Mac OS X; en_US; en-US; scale=2.00; 1125x2436) AppleWebKit/605.1.15',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': '',
            'X-Instagram-AJAX': '1',
            'Referer': 'https://www.instagram.com/',
            'Origin': 'https://www.instagram.com',
        })
    
    def can_download(self, url: str) -> bool:
        """Проверка поддержки URL"""
        return any(re.match(pattern, url) for pattern in self.URL_PATTERNS)
    
    def extract_video_id(self, url: str) -> Optional[str]:
        """Извлечение ID из Instagram URL"""
        for pattern in self.URL_PATTERNS:
            match = re.match(pattern, url)
            if match:
                if 'stories' in url:
                    return f"{match.group(1)}_{match.group(2)}"
                return match.group(1)
        return None
    
    def get_video_info(self, url: str) -> VideoInfo:
        """Получение информации о видео"""
        try:
            video_id = self.extract_video_id(url)
            if not video_id:
                raise DownloadError(f"Cannot extract video ID from URL: {url}")
            
            # Определяем тип контента
            if '/stories/' in url:
                return self._get_story_info(url, video_id)
            elif '/reel/' in url:
                return self._get_reel_info(url, video_id)
            elif '/tv/' in url:
                return self._get_igtv_info(url, video_id)
            else:
                return self._get_post_info(url, video_id)
                
        except Exception as e:
            logger.error(f"Error getting Instagram video info: {e}", url=url)
            raise DownloadError(f"Failed to get video info: {e}")
    
    def _get_post_info(self, url: str, video_id: str) -> VideoInfo:
        """Получение информации о посте"""
        try:
            # Получаем страницу поста
            response = self.session.get(url)
            response.raise_for_status()
            
            # Извлекаем JSON данные из страницы
            data = self._extract_json_data(response.text)
            
            if not data:
                raise DownloadError("Failed to extract post data")
            
            # Находим медиа данные
            media_data = self._find_media_data(data, video_id)
            if not media_data:
                raise DownloadError("Media data not found")
            
            return self._parse_media_info(media_data, url)
            
        except requests.RequestException as e:
            logger.error(f"HTTP error getting post info: {e}")
            raise DownloadError(f"HTTP error: {e}")
    
    def _get_reel_info(self, url: str, video_id: str) -> VideoInfo:
        """Получение информации о Reel"""
        try:
            # Reels имеют специальный API endpoint
            api_url = f"https://www.instagram.com/api/v1/media/{video_id}/info/"
            
            response = self.session.get(api_url)
            if response.status_code == 200:
                data = response.json()
                return self._parse_api_media_info(data, url)
            
            # Fallback к обычному методу
            return self._get_post_info(url, video_id)
            
        except Exception as e:
            logger.warning(f"API method failed, trying fallback: {e}")
            return self._get_post_info(url, video_id)
    
    def _get_igtv_info(self, url: str, video_id: str) -> VideoInfo:
        """Получение информации об IGTV"""
        return self._get_post_info(url, video_id)  # IGTV обрабатывается как обычный пост
    
    def _get_story_info(self, url: str, video_id: str) -> VideoInfo:
        """Получение информации о Story"""
        # Stories требуют аутентификации и имеют ограниченное время жизни
        raise DownloadError("Instagram Stories download requires authentication")
    
    def _extract_json_data(self, html_content: str) -> Optional[Dict]:
        """Извлечение JSON данных из HTML страницы"""
        try:
            # Ищем window._sharedData
            pattern = r'window\._sharedData\s*=\s*({.+?});'
            match = re.search(pattern, html_content)
            
            if match:
                return json.loads(match.group(1))
            
            # Альтернативный поиск
            pattern = r'<script type="application/ld\+json">({.+?})</script>'
            match = re.search(pattern, html_content)
            
            if match:
                return json.loads(match.group(1))
            
            return None
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return None
    
    def _find_media_data(self, data: Dict, video_id: str) -> Optional[Dict]:
        """Поиск медиа данных в JSON"""
        try:
            # Проверяем entry_data
            entry_data = data.get('entry_data', {})
            
            # PostPage
            if 'PostPage' in entry_data:
                posts = entry_data['PostPage'][0]['graphql']['shortcode_media']
                return posts
            
            # Поиск в других местах
            if 'graphql' in data:
                return data['graphql'].get('shortcode_media')
            
            return None
            
        except (KeyError, IndexError, TypeError):
            return None
    
    def _parse_media_info(self, media_data: Dict, url: str) -> VideoInfo:
        """Парсинг информации о медиа"""
        try:
            # Основная информация
            title = media_data.get('edge_media_to_caption', {}).get('edges', [])
            title = title[0]['node']['text'] if title else "Instagram Video"
            
            author = media_data.get('owner', {}).get('username', 'Unknown')
            
            # Проверяем тип медиа
            is_video = media_data.get('is_video', False)
            if not is_video:
                raise DownloadError("This post contains only images, no video")
            
            # URL видео
            video_url = media_data.get('video_url')
            if not video_url:
                raise DownloadError("Video URL not found")
            
            # Дополнительная информация
            view_count = media_data.get('video_view_count', 0)
            like_count = media_data.get('edge_media_preview_like', {}).get('count', 0)
            
            # Длительность (может отсутствовать)
            duration = media_data.get('video_duration', 0)
            
            # Превью изображение
            thumbnail_url = media_data.get('display_url')
            
            # Дата публикации
            timestamp = media_data.get('taken_at_timestamp')
            upload_date = datetime.fromtimestamp(timestamp) if timestamp else None
            
            return VideoInfo(
                id=media_data.get('shortcode', ''),
                title=title[:100],  # Ограничиваем длину
                description=title,
                uploader=author,
                duration=duration,
                view_count=view_count,
                like_count=like_count,
                upload_date=upload_date,
                thumbnail_url=thumbnail_url,
                webpage_url=url,
                direct_url=video_url,
                platform=self.PLATFORM,
                quality="original",
                file_size=None,  # Будет определен при скачивании
                format_info={
                    'format_id': 'instagram',
                    'ext': 'mp4',
                    'protocol': 'https'
                }
            )
            
        except KeyError as e:
            logger.error(f"Missing key in media data: {e}")
            raise DownloadError(f"Invalid media data structure: {e}")
    
    def _parse_api_media_info(self, api_data: Dict, url: str) -> VideoInfo:
        """Парсинг данных из API"""
        try:
            items = api_data.get('items', [])
            if not items:
                raise DownloadError("No media items found")
            
            media = items[0]
            
            # Проверяем наличие видео
            video_versions = media.get('video_versions', [])
            if not video_versions:
                raise DownloadError("No video versions found")
            
            # Берем лучшее качество
            best_video = max(video_versions, key=lambda x: x.get('width', 0))
            
            return VideoInfo(
                id=media.get('pk', ''),
                title=media.get('caption', {}).get('text', 'Instagram Reel')[:100],
                description=media.get('caption', {}).get('text', ''),
                uploader=media.get('user', {}).get('username', 'Unknown'),
                duration=media.get('video_duration', 0),
                view_count=media.get('view_count', 0),
                like_count=media.get('like_count', 0),
                upload_date=datetime.fromtimestamp(media.get('taken_at', 0)),
                thumbnail_url=media.get('image_versions2', {}).get('candidates', [{}])[0].get('url'),
                webpage_url=url,
                direct_url=best_video.get('url'),
                platform=self.PLATFORM,
                quality=f"{best_video.get('width', 0)}x{best_video.get('height', 0)}",
                file_size=None,
                format_info={
                    'format_id': 'instagram_api',
                    'ext': 'mp4',
                    'width': best_video.get('width'),
                    'height': best_video.get('height'),
                    'protocol': 'https'
                }
            )
            
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing API data: {e}")
            raise DownloadError(f"Invalid API response: {e}")
    
    def download_video(self, video_info: VideoInfo, output_path: str, 
                      quality: str = "best", progress_callback=None) -> DownloadResult:
        """Скачивание видео"""
        try:
            if not video_info.direct_url:
                raise DownloadError("No direct URL available")
            
            logger.info(f"Starting Instagram download", 
                       video_id=video_info.id, output_path=output_path)
            
            # Скачиваем файл
            response = self.session.get(video_info.direct_url, stream=True)
            response.raise_for_status()
            
            # Получаем размер файла
            total_size = int(response.headers.get('content-length', 0))
            
            # Скачиваем с прогресс-баром
            downloaded = 0
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_callback(progress)
            
            # Проверяем размер скачанного файла
            actual_size = Path(output_path).stat().st_size
            
            return DownloadResult(
                success=True,
                file_path=output_path,
                file_size=actual_size,
                duration=video_info.duration,
                quality=video_info.quality,
                format="mp4",
                video_info=video_info
            )
            
        except requests.RequestException as e:
            logger.error(f"Download error: {e}")
            raise DownloadError(f"Download failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            raise DownloadError(f"Unexpected error: {e}")
    
    def get_available_qualities(self, url: str) -> List[str]:
        """Получение доступных качеств видео"""
        try:
            video_info = self.get_video_info(url)
            # Instagram обычно предоставляет только одно качество
            return [video_info.quality or "original"]
        except Exception:
            return ["original"]
    
    def cleanup(self):
        """Очистка ресурсов"""
        if hasattr(self, 'session'):
            self.session.close()
    
    def _handle_private_account(self, url: str) -> VideoInfo:
        """Обработка приватных аккаунтов"""
        raise DownloadError("Cannot download from private Instagram accounts")
    
    def _handle_age_restricted(self, url: str) -> VideoInfo:
        """Обработка контента с возрастными ограничениями"""
        raise DownloadError("Age-restricted content cannot be downloaded")
    
    def _get_csrf_token(self) -> Optional[str]:
        """Получение CSRF токена"""
        try:
            response = self.session.get('https://www.instagram.com/')
            
            # Ищем csrf токен в cookies
            csrf_token = response.cookies.get('csrftoken')
            if csrf_token:
                self.session.headers['X-CSRFToken'] = csrf_token
                return csrf_token
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get CSRF token: {e}")
            return None