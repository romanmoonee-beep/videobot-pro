"""
VideoBot Pro - Base Downloader
Базовый класс для всех загрузчиков видео
"""

import os
import asyncio
import tempfile
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)

# Исключения
class DownloadError(Exception):
    """Базовая ошибка скачивания"""
    pass

class UnsupportedPlatformError(DownloadError):
    """Платформа не поддерживается"""
    pass

class VideoNotFoundError(DownloadError):
    """Видео не найдено"""
    pass

class DownloadTimeoutError(DownloadError):
    """Таймаут скачивания"""
    pass

class QualityNotAvailableError(DownloadError):
    """Качество недоступно"""
    pass

@dataclass
class VideoInfo:
    """Информация о видео"""
    id: str
    title: str
    description: Optional[str] = None
    uploader: str = "Unknown"
    duration: int = 0  # в секундах
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    upload_date: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    webpage_url: Optional[str] = None
    direct_url: Optional[str] = None
    platform: str = "unknown"
    quality: Optional[str] = None
    file_size: Optional[int] = None
    format_info: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.format_info is None:
            self.format_info = {}

@dataclass 
class DownloadResult:
    """Результат скачивания"""
    success: bool
    file_path: Optional[str] = None
    filename: Optional[str] = None
    file_size: Optional[int] = None  # в байтах
    duration: Optional[int] = None  # в секундах
    quality: Optional[str] = None
    format: Optional[str] = None
    error: Optional[str] = None
    thumbnail_path: Optional[str] = None
    video_info: Optional[VideoInfo] = None

class BaseDownloader(ABC):
    """
    Базовый класс для всех загрузчиков видео
    
    Определяет общий интерфейс и базовую функциональность
    для скачивания видео с различных платформ
    """
    
    def __init__(self, temp_dir: str = None, **kwargs):
        """
        Инициализация загрузчика
        
        Args:
            temp_dir: Директория для временных файлов
            **kwargs: Дополнительные параметры
        """
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir()) / "videobot"
        self.session_cookies = kwargs.get("session_cookies")
        self.user_agent = kwargs.get("user_agent", self._get_default_user_agent())
        self.timeout = kwargs.get("timeout", 300)  # 5 минут
        self.max_file_size_mb = kwargs.get("max_file_size_mb", 500)
        self.logger = logger.bind(downloader=self.__class__.__name__)
        
        # Обеспечиваем существование временной директории
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Название платформы"""
        pass
    
    @property
    @abstractmethod
    def supported_domains(self) -> List[str]:
        """Поддерживаемые домены"""
        pass
    
    @abstractmethod
    def can_download(self, url: str) -> bool:
        """
        Проверка возможности скачивания URL
        
        Args:
            url: URL для проверки
            
        Returns:
            True если URL поддерживается
        """
        pass
    
    @abstractmethod
    def get_video_info(self, url: str) -> VideoInfo:
        """
        Получение информации о видео
        
        Args:
            url: URL видео
            
        Returns:
            Информация о видео
            
        Raises:
            DownloadError: При ошибке получения информации
        """
        pass
    
    @abstractmethod
    def download_video(
        self,
        video_info: VideoInfo,
        output_path: str,
        quality: str = "best",
        progress_callback: Optional[Callable] = None,
        **kwargs
    ) -> DownloadResult:
        """
        Скачивание видео
        
        Args:
            video_info: Информация о видео
            output_path: Путь для сохранения файла
            quality: Желаемое качество
            progress_callback: Функция для отслеживания прогресса
            **kwargs: Дополнительные параметры
            
        Returns:
            Результат скачивания
            
        Raises:
            DownloadError: При ошибке скачивания
        """
        pass
    
    def get_available_qualities(self, url: str) -> List[str]:
        """
        Получение доступных качеств видео
        
        Args:
            url: URL видео
            
        Returns:
            Список доступных качеств
        """
        try:
            video_info = self.get_video_info(url)
            # Базовая реализация - переопределяется в наследниках
            return ["best", "worst"]
        except Exception:
            return ["best"]
    
    def _get_default_user_agent(self) -> str:
        """Получить User-Agent по умолчанию"""
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    
    def _generate_temp_filename(self, url: str, extension: str = "tmp") -> str:
        """
        Генерация имени временного файла
        
        Args:
            url: URL для генерации уникального имени
            extension: Расширение файла
            
        Returns:
            Путь к временному файлу
        """
        import hashlib
        from datetime import datetime
        
        # Создаем уникальное имя на основе URL и времени
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        filename = f"{self.platform_name}_{timestamp}_{url_hash}.{extension}"
        return str(self.temp_dir / filename)
    
    def _normalize_quality(self, quality: str) -> str:
        """
        Нормализация качества видео
        
        Args:
            quality: Входное качество
            
        Returns:
            Нормализованное качество
        """
        quality_map = {
            "low": "480p",
            "medium": "720p", 
            "high": "1080p",
            "best": "2160p",
            "worst": "240p",
            "auto": "720p",  # По умолчанию
        }
        
        return quality_map.get(quality.lower(), quality)
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """
        Извлечение ID видео из URL
        
        Args:
            url: URL видео
            
        Returns:
            ID видео или None
        """
        # Базовая реализация - переопределяется в наследниках
        return None
    
    async def _download_with_progress(
        self,
        download_func: Callable,
        progress_callback: Optional[Callable] = None,
        **kwargs
    ) -> Any:
        """
        Обертка для скачивания с отслеживанием прогресса
        
        Args:
            download_func: Функция скачивания
            progress_callback: Функция обратного вызова для прогресса
            **kwargs: Параметры для функции скачивания
            
        Returns:
            Результат функции скачивания
        """
        if progress_callback:
            # Создаем wrapper для отслеживания прогресса
            def progress_hook(d):
                if d['status'] == 'downloading':
                    total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    
                    if total_bytes:
                        percent = (downloaded_bytes / total_bytes) * 100
                        progress_callback(percent, f"Downloading... {percent:.1f}%")
                elif d['status'] == 'finished':
                    progress_callback(100, "Download completed")
            
            kwargs['progress_hooks'] = [progress_hook]
        
        return await download_func(**kwargs)
    
    def _validate_file_size(self, file_path: str) -> bool:
        """
        Проверка размера файла
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            True если размер допустимый
        """
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            return file_size_mb <= self.max_file_size_mb
        except OSError:
            return False
    
    def _clean_filename(self, filename: str) -> str:
        """
        Очистка имени файла от недопустимых символов
        
        Args:
            filename: Исходное имя файла
            
        Returns:
            Очищенное имя файла
        """
        import re
        
        # Убираем недопустимые символы
        cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
        
        # Ограничиваем длину
        if len(cleaned) > 100:
            cleaned = cleaned[:97] + "..."
        
        return cleaned.strip()
    
    async def _extract_thumbnail(self, video_path: str) -> Optional[str]:
        """
        Извлечение миниатюры из видео
        
        Args:
            video_path: Путь к видеофайлу
            
        Returns:
            Путь к файлу миниатюры или None
        """
        try:
            import subprocess
            
            thumbnail_path = video_path.rsplit('.', 1)[0] + '_thumb.jpg'
            
            # Используем ffmpeg для извлечения кадра
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', '00:00:05',  # 5 секунд от начала
                '-vframes', '1',
                '-q:v', '2',
                '-y',  # Перезаписать если существует
                thumbnail_path
            ]
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await result.communicate()
            
            if result.returncode == 0 and os.path.exists(thumbnail_path):
                return thumbnail_path
                
        except Exception as e:
            self.logger.warning(f"Failed to extract thumbnail: {e}")
        
        return None
    
    def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Получение информации о файле
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Словарь с информацией о файле
        """
        try:
            stat_info = os.stat(file_path)
            filename = os.path.basename(file_path)
            file_extension = filename.split('.')[-1].lower()
            
            return {
                'filename': filename,
                'size_bytes': stat_info.st_size,
                'size_mb': stat_info.st_size / (1024 * 1024),
                'format': file_extension,
                'created_at': stat_info.st_ctime,
                'modified_at': stat_info.st_mtime,
            }
        except OSError as e:
            self.logger.error(f"Error getting file info: {e}")
            return {}
    
    async def cleanup_temp_files(self, file_patterns: List[str] = None):
        """
        Очистка временных файлов
        
        Args:
            file_patterns: Паттерны файлов для удаления
        """
        import glob
        
        if not file_patterns:
            file_patterns = [
                f"{self.platform_name}_*.tmp",
                f"{self.platform_name}_*.part",
                f"{self.platform_name}_*.temp",
            ]
        
        try:
            for pattern in file_patterns:
                files = glob.glob(str(self.temp_dir / pattern))
                for file_path in files:
                    try:
                        os.remove(file_path)
                        self.logger.debug(f"Removed temp file: {file_path}")
                    except OSError:
                        pass
        except Exception as e:
            self.logger.warning(f"Error cleaning temp files: {e}")
    
    def cleanup(self):
        """Очистка ресурсов downloader'а"""
        try:
            # Очищаем временные файлы
            asyncio.create_task(self.cleanup_temp_files())
        except Exception as e:
            self.logger.warning(f"Error during cleanup: {e}")
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(platform={self.platform_name})"
    
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"platform={self.platform_name}, "
            f"temp_dir={self.temp_dir})"
        )

# Экспорт всех классов и исключений
__all__ = [
    'BaseDownloader',
    'VideoInfo', 
    'DownloadResult',
    'DownloadError',
    'UnsupportedPlatformError',
    'VideoNotFoundError', 
    'DownloadTimeoutError',
    'QualityNotAvailableError',
]