"""
VideoBot Pro - YouTube Downloader
Загрузчик для YouTube видео
"""

import re
import os
import asyncio
from typing import Optional, List, Callable
from urllib.parse import urlparse, parse_qs
import structlog

from .base import BaseDownloader, VideoInfo, DownloadResult

logger = structlog.get_logger(__name__)

class YouTubeDownloader(BaseDownloader):
    """Загрузчик для YouTube видео"""
    
    @property
    def platform_name(self) -> str:
        return "youtube"
    
    @property
    def supported_domains(self) -> List[str]:
        return [
            "youtube.com",
            "www.youtube.com", 
            "youtu.be",
            "www.youtu.be",
            "m.youtube.com",
            "music.youtube.com"
        ]
    
    async def validate_url(self, url: str) -> bool:
        """Валидация YouTube URL"""
        try:
            parsed = urlparse(url.lower())
            
            # Проверяем домен
            if not any(domain in parsed.netloc for domain in self.supported_domains):
                return False
            
            # Извлекаем video ID
            video_id = self._extract_video_id(url)
            return video_id is not None and len(video_id) == 11
            
        except Exception:
            return False
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Извлечение YouTube video ID"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    async def get_video_info(self, url: str) -> Optional[VideoInfo]:
        """Получение информации о YouTube видео"""
        try:
            import yt_dlp
            
            # Настройки для yt-dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'user-agent': self.user_agent,
            }
            
            # Добавляем cookies если есть
            if self.session_cookies:
                ydl_opts['cookiefile'] = self.session_cookies
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Получаем информацию без скачивания
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                if not info:
                    return None
                
                # Проверяем доступность видео
                if info.get('availability') not in [None, 'public', 'unlisted']:
                    self.logger.warning(f"Video not available: {info.get('availability')}")
                    return None
                
                # Получаем доступные качества
                formats = info.get('formats', [])
                available_qualities = self._extract_available_qualities(formats)
                
                # Вычисляем примерный размер файла
                filesize_mb = self._estimate_file_size(formats)
                
                return VideoInfo(
                    title=info.get('title', 'Unknown'),
                    author=info.get('uploader', 'Unknown'),
                    duration_seconds=info.get('duration', 0),
                    view_count=info.get('view_count'),
                    like_count=info.get('like_count'),
                    description=info.get('description'),
                    thumbnail_url=self._get_best_thumbnail(info.get('thumbnails', [])),
                    upload_date=info.get('upload_date'),
                    filesize_mb=filesize_mb,
                    available_qualities=available_qualities,
                    is_live=info.get('is_live', False),
                    is_age_restricted=info.get('age_limit', 0) > 0,
                )
                
        except Exception as e:
            self.logger.error(f"Error getting YouTube video info: {e}")
            return None
    
    async def download_video(
        self,
        url: str,
        quality: str = "auto",
        format_preference: str = "mp4",
        progress_callback: Optional[Callable] = None,
        **kwargs
    ) -> DownloadResult:
        """Скачивание YouTube видео"""
        try:
            import yt_dlp
            
            # Нормализуем качество
            quality = self._normalize_quality(quality)
            
            # Генерируем имя выходного файла
            output_template = self._generate_temp_filename(url, "%(ext)s")
            
            # Настройки для скачивания
            ydl_opts = {
                'outtmpl': output_template,
                'format': self._build_format_selector(quality, format_preference),
                'user-agent': self.user_agent,
                'noplaylist': True,
                'extractaudio': format_preference == 'mp3',
                'audioformat': 'mp3' if format_preference == 'mp3' else None,
                'embed_subs': True,
                'writesubtitles': False,
                'writeautomaticsub': False,
                'ignoreerrors': False,
                'no_warnings': True,
                'retries': 3,
                'file_access_retries': 3,
                'fragment_retries': 3,
            }
            
            # Добавляем cookies если есть
            if self.session_cookies:
                ydl_opts['cookiefile'] = self.session_cookies
            
            # Настройка прогресса
            if progress_callback:
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        downloaded = d.get('downloaded_bytes', 0)
                        
                        if total:
                            percent = (downloaded / total) * 100
                            speed = d.get('speed', 0)
                            speed_str = f" ({speed/1024/1024:.1f} MB/s)" if speed else ""
                            progress_callback(
                                percent, 
                                f"Downloading {percent:.1f}%{speed_str}"
                            )
                    elif d['status'] == 'finished':
                        progress_callback(95, "Processing file...")
                
                ydl_opts['progress_hooks'] = [progress_hook]
            
            # Выполняем скачивание
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Получаем информацию для финального имени файла
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                if not info:
                    return DownloadResult(success=False, error_message="Could not extract video info")
                
                # Проверяем размер файла
                estimated_size = self._estimate_file_size(info.get('formats', []))
                if estimated_size and estimated_size > self.max_file_size_mb:
                    return DownloadResult(
                        success=False,
                        error_message=f"File too large: {estimated_size:.1f}MB > {self.max_file_size_mb}MB"
                    )
                
                # Скачиваем файл
                await asyncio.to_thread(ydl.download, [url])
                
                # Находим скачанный файл
                downloaded_file = self._find_downloaded_file(output_template, info)
                
                if not downloaded_file or not os.path.exists(downloaded_file):
                    return DownloadResult(success=False, error_message="Downloaded file not found")
                
                # Валидируем размер файла
                if not self._validate_file_size(downloaded_file):
                    os.remove(downloaded_file)
                    return DownloadResult(
                        success=False,
                        error_message=f"File size exceeds limit: {self.max_file_size_mb}MB"
                    )
                
                # Получаем информацию о файле
                file_info = self._get_file_info(downloaded_file)
                
                # Извлекаем миниатюру (опционально)
                thumbnail_path = None
                if format_preference != 'mp3':
                    thumbnail_path = await self._extract_thumbnail(downloaded_file)
                
                return DownloadResult(
                    success=True,
                    file_path=downloaded_file,
                    filename=file_info.get('filename'),
                    file_size_bytes=file_info.get('size_bytes'),
                    actual_quality=self._detect_actual_quality(info, ydl_opts['format']),
                    format=file_info.get('format'),
                    duration_seconds=info.get('duration'),
                    thumbnail_path=thumbnail_path,
                )
                
        except Exception as e:
            self.logger.error(f"YouTube download failed: {e}")
            
            # Очищаем частично скачанные файлы
            await self.cleanup_temp_files([f"*{self._extract_video_id(url)}*"])
            
            return DownloadResult(success=False, error_message=str(e))
    
    def _build_format_selector(self, quality: str, format_preference: str) -> str:
        """Построение селектора формата для yt-dlp"""
        if format_preference == 'mp3':
            return 'bestaudio/best'
        
        # Мапинг качества на высоту видео
        quality_map = {
            '240p': '240',
            '360p': '360', 
            '480p': '480',
            '720p': '720',
            '1080p': '1080',
            '1440p': '1440',
            '2160p': '2160',
            '4K': '2160',
            'auto': 'best',
        }
        
        if quality == 'auto' or quality not in quality_map:
            return f'best[ext={format_preference}]/best'
        
        height = quality_map[quality]
        
        # Пытаемся найти нужное качество, иначе берем лучшее доступное
        return (
            f'best[height<={height}][ext={format_preference}]/'
            f'best[height<={height}]/'
            f'best[ext={format_preference}]/'
            f'best'
        )
    
    def _extract_available_qualities(self, formats: List[dict]) -> List[str]:
        """Извлечение доступных качеств из форматов"""
        qualities = set()
        
        for fmt in formats:
            height = fmt.get('height')
            if height:
                if height <= 240:
                    qualities.add('240p')
                elif height <= 360:
                    qualities.add('360p')
                elif height <= 480:
                    qualities.add('480p')
                elif height <= 720:
                    qualities.add('720p')
                elif height <= 1080:
                    qualities.add('1080p')
                elif height <= 1440:
                    qualities.add('1440p')
                elif height <= 2160:
                    qualities.add('2160p')
        
        # Сортируем по возрастанию качества
        quality_order = ['240p', '360p', '480p', '720p', '1080p', '1440p', '2160p']
        return [q for q in quality_order if q in qualities]
    
    def _estimate_file_size(self, formats: List[dict]) -> Optional[float]:
        """Оценка размера файла в MB"""
        try:
            # Ищем лучший формат с известным размером
            for fmt in sorted(formats, key=lambda x: x.get('quality', 0), reverse=True):
                filesize = fmt.get('filesize') or fmt.get('filesize_approx')
                if filesize:
                    return filesize / (1024 * 1024)
            
            # Если размер неизвестен, оцениваем по битрейту
            for fmt in formats:
                tbr = fmt.get('tbr')  # total bitrate
                duration = fmt.get('duration')
                if tbr and duration:
                    # Битрейт в kbps * длительность в секундах / 8 / 1024
                    return (tbr * duration) / (8 * 1024)
                    
        except Exception:
            pass
        
        return None
    
    def _get_best_thumbnail(self, thumbnails: List[dict]) -> Optional[str]:
        """Получение лучшей миниатюры"""
        if not thumbnails:
            return None
        
        # Сортируем по качеству (предпочитаем высокое разрешение)
        sorted_thumbs = sorted(
            thumbnails,
            key=lambda x: (x.get('width', 0) * x.get('height', 0)),
            reverse=True
        )
        
        return sorted_thumbs[0].get('url')
    
    def _find_downloaded_file(self, template: str, info: dict) -> Optional[str]:
        """Поиск скачанного файла"""
        import glob
        
        # Удаляем %(ext)s из шаблона для поиска
        base_template = template.replace('%(ext)s', '*')
        
        # Ищем файлы по шаблону
        files = glob.glob(base_template)
        
        if files:
            # Берем самый новый файл
            return max(files, key=os.path.getctime)
        
        return None
    
    def _detect_actual_quality(self, info: dict, format_selector: str) -> Optional[str]:
        """Определение фактического качества скачанного видео"""
        try:
            # Получаем выбранный формат
            requested_format = info.get('requested_formats', [])
            if requested_format:
                height = requested_format[0].get('height')
            else:
                height = info.get('height')
            
            if height:
                if height <= 240:
                    return '240p'
                elif height <= 360:
                    return '360p'
                elif height <= 480:
                    return '480p'
                elif height <= 720:
                    return '720p'
                elif height <= 1080:
                    return '1080p'
                elif height <= 1440:
                    return '1440p'
                elif height <= 2160:
                    return '2160p'
                    
        except Exception:
            pass
        
        return None

# Дополнительные утилиты для YouTube

class YouTubePlaylistDownloader(YouTubeDownloader):
    """Расширение для скачивания плейлистов YouTube"""
    
    async def get_playlist_info(self, url: str) -> Optional[dict]:
        """Получение информации о плейлисте"""
        try:
            import yt_dlp
            
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,  # Только метаданные
                'user-agent': self.user_agent,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                if info and info.get('_type') == 'playlist':
                    return {
                        'title': info.get('title'),
                        'uploader': info.get('uploader'),
                        'video_count': len(info.get('entries', [])),
                        'videos': [
                            {
                                'title': entry.get('title'),
                                'url': entry.get('url'),
                                'duration': entry.get('duration'),
                            }
                            for entry in info.get('entries', [])
                            if entry.get('url')
                        ]
                    }
                    
        except Exception as e:
            self.logger.error(f"Error getting playlist info: {e}")
        
        return None

# Экспорт
__all__ = ['YouTubeDownloader', 'YouTubePlaylistDownloader']