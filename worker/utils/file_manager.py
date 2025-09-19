"""
VideoBot Pro - File Manager
Управление файлами и директориями для worker'а
"""

import os
import shutil
import hashlib
import tempfile
import mimetypes
import structlog
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, BinaryIO
from datetime import datetime, timedelta
import aiofiles
import aiofiles.os

logger = structlog.get_logger(__name__)

class FileManagerError(Exception):
    """Ошибки файл менеджера"""
    pass

class FileManager:
    """Менеджер файлов для worker'а"""
    
    def __init__(self, base_dir: str = None, max_file_size_mb: int = 2048):
        """
        Инициализация файл менеджера
        
        Args:
            base_dir: Базовая директория для работы с файлами
            max_file_size_mb: Максимальный размер файла в МБ
        """
        self.base_dir = Path(base_dir or tempfile.gettempdir()) / "videobot_worker"
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        
        # Создаем рабочие директории
        self.downloads_dir = self.base_dir / "downloads"
        self.temp_dir = self.base_dir / "temp"  
        self.processing_dir = self.base_dir / "processing"
        self.archives_dir = self.base_dir / "archives"
        
        # Инициализация директорий
        self._ensure_directories()
        
        # Поддерживаемые форматы
        self.supported_video_formats = {
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp'
        }
        
        self.supported_audio_formats = {
            '.mp3', '.aac', '.wav', '.flac', '.ogg', '.wma', '.m4a'
        }
        
        # Настройки очистки
        self.cleanup_after_hours = 24
        
    def _ensure_directories(self):
        """Создание необходимых директорий"""
        try:
            for directory in [self.base_dir, self.downloads_dir, 
                             self.temp_dir, self.processing_dir, self.archives_dir]:
                directory.mkdir(parents=True, exist_ok=True)
                
            logger.info(f"File manager directories initialized: {self.base_dir}")
            
        except Exception as e:
            logger.error(f"Failed to create directories: {e}")
            raise FileManagerError(f"Cannot initialize file manager: {e}")
    
    def generate_unique_filename(self, original_name: str, 
                                add_timestamp: bool = True) -> str:
        """
        Генерация уникального имени файла
        
        Args:
            original_name: Оригинальное имя файла
            add_timestamp: Добавлять временную метку
            
        Returns:
            Уникальное имя файла
        """
        try:
            path = Path(original_name)
            name = self._sanitize_filename(path.stem)
            extension = path.suffix.lower()
            
            # Добавляем временную метку
            if add_timestamp:
                timestamp = int(datetime.utcnow().timestamp())
                name = f"{name}_{timestamp}"
            
            # Добавляем хеш для уникальности
            hash_suffix = hashlib.md5(
                f"{name}_{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:8]
            
            return f"{name}_{hash_suffix}{extension}"
            
        except Exception as e:
            logger.error(f"Error generating unique filename: {e}")
            raise FileManagerError(f"Cannot generate unique filename: {e}")
    
    def _sanitize_filename(self, filename: str) -> str:
        """Санитизация имени файла"""
        # Удаляем недопустимые символы
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Убираем пробелы в начале и конце
        filename = filename.strip()
        
        # Заменяем множественные подчеркивания
        while '__' in filename:
            filename = filename.replace('__', '_')
        
        # Ограничиваем длину
        if len(filename) > 100:
            filename = filename[:97] + "..."
        
        return filename
    
    def get_temp_file_path(self, filename: str, category: str = "temp") -> Path:
        """
        Получить путь для временного файла
        
        Args:
            filename: Имя файла
            category: Категория (temp, downloads, processing, archives)
            
        Returns:
            Путь к файлу
        """
        category_dirs = {
            'temp': self.temp_dir,
            'downloads': self.downloads_dir,
            'processing': self.processing_dir,
            'archives': self.archives_dir
        }
        
        directory = category_dirs.get(category, self.temp_dir)
        return directory / filename
    
    def validate_file(self, file_path: Union[str, Path]) -> bool:
        """
        Валидация файла
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            True если файл валиден
            
        Raises:
            FileManagerError: При ошибках валидации
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                raise FileManagerError(f"File not found: {file_path}")
            
            if not file_path.is_file():
                raise FileManagerError(f"Path is not a file: {file_path}")
            
            # Проверяем размер файла
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size_bytes:
                raise FileManagerError(
                    f"File too large: {file_size / (1024*1024):.1f}MB > {self.max_file_size_mb}MB"
                )
            
            # Проверяем расширение файла
            extension = file_path.suffix.lower()
            if extension not in (self.supported_video_formats | self.supported_audio_formats):
                logger.warning(f"Unsupported file format: {extension}")
            
            return True
            
        except FileManagerError:
            raise
        except Exception as e:
            raise FileManagerError(f"File validation error: {e}")
    
    def get_file_info(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Получение информации о файле
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Словарь с информацией о файле
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                return {'exists': False, 'error': 'File not found'}
            
            stat = file_path.stat()
            
            # Определяем MIME тип
            mime_type, _ = mimetypes.guess_type(str(file_path))
            
            # Определяем категорию файла
            extension = file_path.suffix.lower()
            if extension in self.supported_video_formats:
                file_category = 'video'
            elif extension in self.supported_audio_formats:
                file_category = 'audio'
            else:
                file_category = 'unknown'
            
            return {
                'exists': True,
                'name': file_path.name,
                'stem': file_path.stem,
                'extension': extension,
                'size_bytes': stat.st_size,
                'size_mb': stat.st_size / (1024 * 1024),
                'size_gb': stat.st_size / (1024 * 1024 * 1024),
                'created_at': datetime.fromtimestamp(stat.st_ctime),
                'modified_at': datetime.fromtimestamp(stat.st_mtime),
                'mime_type': mime_type,
                'category': file_category,
                'is_supported': extension in (self.supported_video_formats | self.supported_audio_formats),
                'relative_path': str(file_path.relative_to(self.base_dir)) if self._is_under_base_dir(file_path) else None
            }
            
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return {'exists': False, 'error': str(e)}
    
    def _is_under_base_dir(self, file_path: Path) -> bool:
        """Проверяет находится ли файл в базовой директории"""
        try:
            file_path.relative_to(self.base_dir)
            return True
        except ValueError:
            return False
    
    def calculate_file_hash(self, file_path: Union[str, Path], 
                           algorithm: str = 'md5') -> str:
        """
        Вычисление хеша файла
        
        Args:
            file_path: Путь к файлу
            algorithm: Алгоритм хеширования (md5, sha1, sha256)
            
        Returns:
            Хеш файла в hex формате
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                raise FileManagerError(f"File not found: {file_path}")
            
            hash_obj = hashlib.new(algorithm)
            
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    hash_obj.update(chunk)
            
            return hash_obj.hexdigest()
            
        except Exception as e:
            logger.error(f"Error calculating file hash: {e}")
            raise FileManagerError(f"Cannot calculate file hash: {e}")
    
    async def copy_file_async(self, source: Union[str, Path], 
                             destination: Union[str, Path]) -> bool:
        """
        Асинхронное копирование файла
        
        Args:
            source: Путь к исходному файлу
            destination: Путь назначения
            
        Returns:
            True если файл скопирован успешно
        """
        try:
            source = Path(source)
            destination = Path(destination)
            
            # Создаем родительскую директорию если нужно
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Проверяем исходный файл
            if not source.exists():
                raise FileManagerError(f"Source file not found: {source}")
            
            # Копируем файл асинхронно
            async with aiofiles.open(source, 'rb') as src:
                async with aiofiles.open(destination, 'wb') as dst:
                    while chunk := await src.read(8192):
                        await dst.write(chunk)
            
            logger.info(f"File copied: {source} -> {destination}")
            return True
            
        except Exception as e:
            logger.error(f"Error copying file: {e}")
            raise FileManagerError(f"Cannot copy file: {e}")
    
    async def move_file_async(self, source: Union[str, Path], 
                             destination: Union[str, Path]) -> bool:
        """
        Асинхронное перемещение файла
        
        Args:
            source: Путь к исходному файлу
            destination: Путь назначения
            
        Returns:
            True если файл перемещен успешно
        """
        try:
            # Сначала копируем
            await self.copy_file_async(source, destination)
            
            # Затем удаляем оригинал
            await aiofiles.os.remove(source)
            
            logger.info(f"File moved: {source} -> {destination}")
            return True
            
        except Exception as e:
            logger.error(f"Error moving file: {e}")
            raise FileManagerError(f"Cannot move file: {e}")
    
    def cleanup_old_files(self, max_age_hours: int = None) -> Dict[str, Any]:
        """
        Очистка старых файлов
        
        Args:
            max_age_hours: Максимальный возраст файлов в часах
            
        Returns:
            Статистика очистки
        """
        max_age_hours = max_age_hours or self.cleanup_after_hours
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        stats = {
            'deleted_files': 0,
            'freed_space_mb': 0.0,
            'errors': []
        }
        
        try:
            # Очищаем каждую категорию
            for category_dir in [self.temp_dir, self.downloads_dir, 
                               self.processing_dir, self.archives_dir]:
                if not category_dir.exists():
                    continue
                
                for file_path in category_dir.rglob('*'):
                    if not file_path.is_file():
                        continue
                    
                    try:
                        file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if file_time < cutoff_time:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            
                            stats['deleted_files'] += 1
                            stats['freed_space_mb'] += file_size / (1024 * 1024)
                            
                    except Exception as e:
                        stats['errors'].append(f"Error deleting {file_path}: {e}")
                        continue
            
            # Удаляем пустые директории
            self._cleanup_empty_directories()
            
            logger.info(f"Cleanup completed", 
                       deleted_files=stats['deleted_files'],
                       freed_space_mb=round(stats['freed_space_mb'], 2))
            
            return stats
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            stats['errors'].append(str(e))
            return stats
    
    def _cleanup_empty_directories(self):
        """Удаление пустых директорий"""
        try:
            for category_dir in [self.temp_dir, self.downloads_dir, 
                               self.processing_dir, self.archives_dir]:
                if not category_dir.exists():
                    continue
                
                # Обходим директории в обратном порядке (снизу вверх)
                for dir_path in sorted(category_dir.rglob('*'), reverse=True):
                    if dir_path.is_dir() and not any(dir_path.iterdir()):
                        try:
                            dir_path.rmdir()
                        except OSError:
                            # Директория не пуста или другая ошибка
                            pass
                            
        except Exception as e:
            logger.error(f"Error cleaning empty directories: {e}")
    
    def get_directory_stats(self, directory: Union[str, Path] = None) -> Dict[str, Any]:
        """
        Получение статистики директории
        
        Args:
            directory: Директория для анализа (по умолчанию base_dir)
            
        Returns:
            Статистика директории
        """
        try:
            directory = Path(directory) if directory else self.base_dir
            
            if not directory.exists():
                return {'exists': False, 'error': 'Directory not found'}
            
            stats = {
                'exists': True,
                'path': str(directory),
                'total_files': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0.0,
                'total_size_gb': 0.0,
                'file_types': {},
                'largest_file': None,
                'oldest_file': None,
                'newest_file': None
            }
            
            oldest_time = datetime.max
            newest_time = datetime.min
            largest_size = 0
            largest_file = None
            
            for file_path in directory.rglob('*'):
                if not file_path.is_file():
                    continue
                
                try:
                    file_stat = file_path.stat()
                    file_size = file_stat.st_size
                    file_time = datetime.fromtimestamp(file_stat.st_mtime)
                    file_extension = file_path.suffix.lower()
                    
                    stats['total_files'] += 1
                    stats['total_size_bytes'] += file_size
                    
                    # Статистика по типам файлов
                    if file_extension in stats['file_types']:
                        stats['file_types'][file_extension]['count'] += 1
                        stats['file_types'][file_extension]['size'] += file_size
                    else:
                        stats['file_types'][file_extension] = {
                            'count': 1,
                            'size': file_size
                        }
                    
                    # Самый большой файл
                    if file_size > largest_size:
                        largest_size = file_size
                        largest_file = str(file_path.relative_to(directory))
                    
                    # Самый старый файл
                    if file_time < oldest_time:
                        oldest_time = file_time
                        stats['oldest_file'] = {
                            'path': str(file_path.relative_to(directory)),
                            'modified_at': file_time.isoformat(),
                            'size': file_size
                        }
                    
                    # Самый новый файл
                    if file_time > newest_time:
                        newest_time = file_time
                        stats['newest_file'] = {
                            'path': str(file_path.relative_to(directory)),
                            'modified_at': file_time.isoformat(),
                            'size': file_size
                        }
                        
                except Exception as e:
                    logger.warning(f"Error processing file {file_path}: {e}")
                    continue
            
            # Конвертируем размеры
            stats['total_size_mb'] = stats['total_size_bytes'] / (1024 * 1024)
            stats['total_size_gb'] = stats['total_size_mb'] / 1024
            
            if largest_file:
                stats['largest_file'] = {
                    'path': largest_file,
                    'size': largest_size,
                    'size_mb': largest_size / (1024 * 1024)
                }
            
            # Конвертируем размеры в file_types
            for ext, info in stats['file_types'].items():
                info['size_mb'] = info['size'] / (1024 * 1024)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting directory stats: {e}")
            return {'exists': False, 'error': str(e)}
    
    def find_files_by_pattern(self, pattern: str, 
                             directory: Union[str, Path] = None) -> List[Path]:
        """
        Поиск файлов по паттерну
        
        Args:
            pattern: Паттерн для поиска (glob-стиль)
            directory: Директория для поиска
            
        Returns:
            Список найденных файлов
        """
        try:
            directory = Path(directory) if directory else self.base_dir
            
            if not directory.exists():
                return []
            
            return list(directory.rglob(pattern))
            
        except Exception as e:
            logger.error(f"Error finding files by pattern: {e}")
            return []
    
    def ensure_free_space(self, required_mb: float = 1000) -> bool:
        """
        Обеспечение свободного места
        
        Args:
            required_mb: Требуемое свободное место в МБ
            
        Returns:
            True если достаточно места или удалось освободить
        """
        try:
            # Проверяем текущее свободное место
            disk_usage = shutil.disk_usage(self.base_dir)
            free_mb = disk_usage.free / (1024 * 1024)
            
            if free_mb >= required_mb:
                return True
            
            logger.warning(f"Low disk space: {free_mb:.1f}MB < {required_mb}MB")
            
            # Пытаемся освободить место
            cleanup_stats = self.cleanup_old_files(max_age_hours=1)  # Агрессивная очистка
            
            # Проверяем снова
            disk_usage = shutil.disk_usage(self.base_dir)
            free_mb_after = disk_usage.free / (1024 * 1024)
            
            if free_mb_after >= required_mb:
                logger.info(f"Successfully freed space: {cleanup_stats['freed_space_mb']:.1f}MB")
                return True
            else:
                logger.error(f"Still not enough space: {free_mb_after:.1f}MB < {required_mb}MB")
                return False
                
        except Exception as e:
            logger.error(f"Error ensuring free space: {e}")
            return False
    
    def get_storage_summary(self) -> Dict[str, Any]:
        """
        Получение сводной информации о хранилище
        
        Returns:
            Сводная информация
        """
        try:
            summary = {
                'base_directory': str(self.base_dir),
                'max_file_size_mb': self.max_file_size_mb,
                'directories': {},
                'total_stats': {
                    'total_files': 0,
                    'total_size_mb': 0.0
                }
            }
            
            # Статистика по каждой директории
            for name, directory in [
                ('downloads', self.downloads_dir),
                ('temp', self.temp_dir),
                ('processing', self.processing_dir),
                ('archives', self.archives_dir)
            ]:
                dir_stats = self.get_directory_stats(directory)
                summary['directories'][name] = dir_stats
                
                if dir_stats.get('exists'):
                    summary['total_stats']['total_files'] += dir_stats.get('total_files', 0)
                    summary['total_stats']['total_size_mb'] += dir_stats.get('total_size_mb', 0)
            
            # Информация о диске
            try:
                disk_usage = shutil.disk_usage(self.base_dir)
                summary['disk_usage'] = {
                    'total_gb': disk_usage.total / (1024**3),
                    'used_gb': disk_usage.used / (1024**3),
                    'free_gb': disk_usage.free / (1024**3),
                    'free_percent': (disk_usage.free / disk_usage.total) * 100
                }
            except Exception as e:
                summary['disk_usage'] = {'error': str(e)}
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting storage summary: {e}")
            return {'error': str(e)}
    
    def __del__(self):
        """Деструктор - очистка при удалении объекта"""
        try:
            # Очищаем временные файлы при удалении объекта
            if hasattr(self, 'temp_dir') and self.temp_dir.exists():
                for temp_file in self.temp_dir.iterdir():
                    if temp_file.is_file():
                        try:
                            temp_file.unlink()
                        except:
                            pass
        except:
            pass