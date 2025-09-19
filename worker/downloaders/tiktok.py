"""
VideoBot Pro - TikTok Downloader
Загрузчик для TikTok видео
"""

import re
import os
import asyncio
import aiohttp
from typing import Optional, List, Callable, Dict, Any
from urllib.parse import urlparse
import structlog

from .base import BaseDownloader, VideoInfo, DownloadResult

logger = structlog.get_logger(__name__)

class TikTokDownloader(BaseDownloader):
    """Загрузчик для TikTok видео"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_endpoints = [
            "https://api.tikmate.app",
            "https://tikdown.org/api",
            "https://ssstik.io/abc",
        ]
        self.session = None
    
    @property
    def platform_name(self) -> str:
        return "tiktok"
    
    @property
    def supported_domains(self) -> List[str]:
        return [
            "tiktok.com",
            "www.tiktok.com",
            "vm.tiktok.com",
            "vt.tiktok.com", 
            "m.tiktok.com",
        ]
    
    async def validate_url(self, url: str) -> bool:
        """Валидация TikTok URL"""
        try:
            # Разворачиваем короткие ссылки
            expanded_url = await self._expand_short_url(url)
            if expanded_url:
                url = expanded_url
            
            parsed = urlparse(url.lower())
            
            # Проверяем домен
            if not any(domain in parsed.netloc for domain in self.supported_domains):
                return False
            
            # Проверяем наличие video ID
            video_id = self._extract_video_id(url)
            return video_id is not None
            
        except Exception:
            return False
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Извлечение TikTok video ID"""
        patterns = [
            r'tiktok\.com.*?/video/(\d+)',
            r'tiktok\.com.*?/@[\w.-]+/video/(\d+)',
            r'vm\.tiktok\.com/([A-Za-z0-9]+)',
            r'vt\.tiktok\.com/([A-Za-z0-9]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    async def _expand_short_url(self, url: str) -> Optional[str]:
        """Разворачивание коротких TikTok ссылок"""
        if "vm.tiktok.com" not in url and "vt.tiktok.com" not in url:
            return url
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True) as response:
                    return str(response.url)
        except Exception:
            return url
    
    async def get_video_info(self, url: str) -> Optional[VideoInfo]:
        """Получение информации о TikTok видео"""
        try:
            # Разворачиваем URL если нужно
            expanded_url = await self._expand_short_url(url)
            if expanded_url:
                url = expanded_url
            
            # Пытаемся получить информацию через разные методы
            for method in [self._get_info_via_yt_dlp, self._get_info_via_api]:
                try:
                    info = await method(url)
                    if info:
                        return info
                except Exception as e:
                    self.logger.debug(f"Method {method.__name__} failed: {e}")
                    continue
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting TikTok video info: {e}")
            return None
    
    async def _get_info_via_yt_dlp(self, url: str) -> Optional[VideoInfo]:
        """Получение информации через yt-dlp"""
        try:
            import yt_dlp
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'user-agent': self.user_agent,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                if not info:
                    return None
                
                return VideoInfo(
                    title=info.get('title', 'TikTok Video'),
                    author=info.get('uploader', 'Unknown'),
                    duration_seconds=info.get('duration', 0),
                    view_count=info.get('view_count'),
                    like_count=info.get('like_count'),
                    description=info.get('description'),
                    thumbnail_url=info.get('thumbnail'),
                    upload_date=info.get('upload_date'),
                    filesize_mb=self._estimate_tiktok_size(info),
                    available_qualities=['720p', '480p'],  # TikTok обычно 720p
                    is_live=False,
                    is_age_restricted=False,
                )
                
        except Exception as e:
            self.logger.debug(f"yt-dlp method failed: {e}")
            raise
    
    async def _get_info_via_api(self, url: str) -> Optional[VideoInfo]:
        """Получение информации через API"""
        for api_url in self.api_endpoints:
            try:
                info = await self._fetch_from_api(api_url, url)
                if info:
                    return info
            except Exception as e:
                self.logger.debug(f"API {api_url} failed: {e}")
                continue
        
        raise Exception("All API methods failed")
    
    async def _fetch_from_api(self, api_url: str, video_url: str) -> Optional[VideoInfo]:
        """Получение данных от конкретного API"""
        # Реализация зависит от конкретного API
        # Здесь базовая структура
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"url": video_url}
                async with session.post(f"{api_url}/analyze", json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self._parse_api_response(data)
        except Exception:
            pass
        
        return None
    
    def _parse_api_response(self, data: dict) -> Optional[VideoInfo]:
        """Парсинг ответа API"""
        try:
            return VideoInfo(
                title=data.get('title', 'TikTok Video'),
                author=data.get('author', 'Unknown'),
                duration_seconds=data.get('duration', 0),
                view_count=data.get('play_count'),
                like_count=data.get('digg_count'),
                description=data.get('desc'),
                thumbnail_url=data.get('cover'),
                filesize_mb=None,
                available_qualities=['720p'],
                is_live=False,
            )
        except Exception:
            return None
    
    async def download_video(
        self,
        url: str,
        quality: str = "auto",
        format_preference: str = "mp4",
        progress_callback: Optional[Callable] = None,
        **kwargs
    ) -> DownloadResult:
        """Скачивание TikTok видео"""
        try:
            # Разворачиваем URL
            expanded_url = await self._expand_short_url(url)
            if expanded_url:
                url = expanded_url
            
            # Пытаемся скачать через разные методы
            for method in [self._download_via_yt_dlp, self._download_via_api]:
                try:
                    result = await method(
                        url, quality, format_preference, progress_callback, **kwargs
                    )
                    if result.success:
                        return result
                except Exception as e:
                    self.logger.debug(f"Download method {method.__name__} failed: {e}")
                    continue
            
            return DownloadResult(success=False, error_message="All download methods failed")
            
        except Exception as e:
            self.logger.error(f"TikTok download failed: {e}")
            return DownloadResult(success=False, error_message=str(e))
    
    async def _download_via_yt_dlp(
        self,
        url: str,
        quality: str,
        format_preference: str,
        progress_callback: Optional[Callable],
        **kwargs
    ) -> DownloadResult:
        """Скачивание через yt-dlp"""
        try:
            import yt_dlp
            
            # Генерируем имя файла
            output_template = self._generate_temp_filename(url, "%(ext)s")
            
            ydl_opts = {
                'outtmpl': output_template,
                'format': 'best',  # TikTok обычно имеет одно качество
                'user-agent': self.user_agent,
                'noplaylist': True,
                'ignoreerrors': False,
                'no_warnings': True,
                'retries': 3,
            }
            
            # Настройка прогресса
            if progress_callback:
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        downloaded = d.get('downloaded_bytes', 0)
                        
                        if total:
                            percent = (downloaded / total) * 100
                            progress_callback(percent, f"Downloading {percent:.1f}%")
                    elif d['status'] == 'finished':
                        progress_callback(95, "Processing...")
                
                ydl_opts['progress_hooks'] = [progress_hook]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Получаем информацию
                info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                
                if not info:
                    raise Exception("Could not extract video info")
                
                # Скачиваем
                await asyncio.to_thread(ydl.download, [url])
                
                # Находим скачанный файл
                downloaded_file = self._find_downloaded_file(output_template)
                
                if not downloaded_file or not os.path.exists(downloaded_file):
                    raise Exception("Downloaded file not found")
                
                # Валидируем размер
                if not self._validate_file_size(downloaded_file):
                    os.remove(downloaded_file)
                    raise Exception("File size exceeds limit")
                
                # Получаем информацию о файле
                file_info = self._get_file_info(downloaded_file)
                
                # Извлекаем миниатюру
                thumbnail_path = await self._extract_thumbnail(downloaded_file)
                
                return DownloadResult(
                    success=True,
                    file_path=downloaded_file,
                    filename=file_info.get('filename'),
                    file_size_bytes=file_info.get('size_bytes'),
                    actual_quality='720p',  # TikTok обычно 720p
                    format=file_info.get('format'),
                    duration_seconds=info.get('duration'),
                    thumbnail_path=thumbnail_path,
                )
                
        except Exception as e:
            self.logger.error(f"yt-dlp download failed: {e}")
            raise
    
    async def _download_via_api(
        self,
        url: str,
        quality: str,
        format_preference: str,
        progress_callback: Optional[Callable],
        **kwargs
    ) -> DownloadResult:
        """Скачивание через API"""
        for api_url in self.api_endpoints:
            try:
                result = await self._download_from_api(
                    api_url, url, progress_callback
                )
                if result:
                    return result
            except Exception as e:
                self.logger.debug(f"API download from {api_url} failed: {e}")
                continue
        
        raise Exception("All API download methods failed")
    
    async def _download_from_api(
        self,
        api_url: str,
        video_url: str,
        progress_callback: Optional[Callable]
    ) -> Optional[DownloadResult]:
        """Скачивание с конкретного API"""
        try:
            async with aiohttp.ClientSession() as session:
                # Получаем ссылку для скачивания
                payload = {"url": video_url}
                async with session.post(f"{api_url}/analyze", json=payload) as response:
                    if response.status != 200:
                        return None
                    
                    data = await response.json()
                    download_url = data.get('download_url')
                    
                    if not download_url:
                        return None
                
                # Скачиваем файл
                output_path = self._generate_temp_filename(video_url, "mp4")
                
                async with session.get(download_url) as response:
                    if response.status != 200:
                        return None
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if progress_callback and total_size:
                                percent = (downloaded / total_size) * 100
                                progress_callback(percent, f"Downloading {percent:.1f}%")
                
                # Валидируем файл
                if not os.path.exists(output_path) or not self._validate_file_size(output_path):
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    return None
                
                file_info = self._get_file_info(output_path)
                thumbnail_path = await self._extract_thumbnail(output_path)
                
                return DownloadResult(
                    success=True,
                    file_path=output_path,
                    filename=file_info.get('filename'),
                    file_size_bytes=file_info.get('size_bytes'),
                    actual_quality='720p',
                    format='mp4',
                    thumbnail_path=thumbnail_path,
                )
                
        except Exception as e:
            self.logger.debug(f"API download error: {e}")
            return None
    
    def _find_downloaded_file(self, template: str) -> Optional[str]:
        """Поиск скачанного файла"""
        import glob
        
        base_template = template.replace('%(ext)s', '*')
        files = glob.glob(base_template)
        
        if files:
            return max(files, key=os.path.getctime)
        
        return None
    
    def _estimate_tiktok_size(self, info: dict) -> Optional[float]:
        """Оценка размера TikTok файла"""
        try:
            filesize = info.get('filesize') or info.get('filesize_approx')
            if filesize:
                return filesize / (1024 * 1024)
            
            # TikTok видео обычно 15-60 секунд и ~5-20 MB
            duration = info.get('duration', 30)
            estimated_mb = min(duration * 0.5, 50)  # ~0.5 MB/секунда, макс 50MB
            return estimated_mb
            
        except Exception:
            return None
    
    async def cleanup_temp_files(self, file_patterns: List[str] = None):
        """Очистка временных файлов TikTok"""
        if not file_patterns:
            file_patterns = [
                "tiktok_*.mp4",
                "tiktok_*.tmp",
                "tiktok_*.part",
            ]
        
        await super().cleanup_temp_files(file_patterns)

# Экспорт
__all__ = ['TikTokDownloader']