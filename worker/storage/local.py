"""
VideoBot Pro - Local Storage Handler
Локальное хранилище для временных файлов worker'а
"""

import os
import shutil
import hashlib
import tempfile
import structlog
from pathlib import Path
from typing import Optional, Dict, Any, BinaryIO
from datetime import datetime, timedelta
from contextlib import contextmanager

from shared.exceptions import StorageException, FileNotFoundError as CustomFileNotFoundError
from worker.config import worker_config

logger = structlog.get_logger(__name__)

class LocalStorage:
    """
    Локальное файловое хранилище
    
    Управляет временными файлами на диске перед их загрузкой в CDN
    """
    
    def __init__(self, base_path: str = None):
        """
        Инициализация локального хранилища
        
        Args:
            base_path: Базовый путь для хранения файлов
        """
        self.base_path = Path(base_path or worker_config.LOCAL_STORAGE_PATH)
        self.temp_dir = self.base_path / "temp"
        self.downloads_dir = self.base_path / "downloads"
        self.archives_dir = self.base_path / "archives"
        self.thumbnails_dir = self.base_path / "thumbnails"
        
        # Создаем директории если их нет
        self._ensure_directories()
        
        # Настройки
        self.max_file_size_mb = worker_config.MAX_FILE_SIZE_MB
        self.cleanup_after_hours = 24  # Удаляем файлы старше 24 часов
        self.max_total_size_gb = 50  # Максимальный размер всех файлов
        
    def _ensure_directories(self):
        """Создает необходимые директории"""
        try:
            for directory in [self.base_path, self.temp_dir, self.downloads_dir, 
                            self.archives_dir, self.thumbnails_dir]:
                directory.mkdir(parents=True, exist_ok=True)
                
            logger.info(f"Local storage initialized at {self.base_path}")
            
        except Exception as e:
            logger.error(f"Failed to create storage directories: {e}")
            raise StorageException(f"Cannot initialize local storage: {e}")
    
    def save_file(self, file_data: bytes, filename: str, 
                  category: str = "downloads") -> Dict[str, Any]:
        """
        Сохранить файл локально
        
        Args:
            file_data: Данные файла
            filename: Имя файла
            category: Категория (downloads, archives, thumbnails)
            
        Returns:
            Информация о сохраненном файле
            
        Raises:
            StorageException: При ошибке сохранения
        """
        try:
            # Выбираем директорию по категории
            target_dir = self._get_category_dir(category)
            
            # Генерируем безопасное имя файла
            safe_filename = self._sanitize_filename(filename)
            file_path = target_dir / safe_filename
            
            # Проверяем размер файла
            file_size_mb = len(file_data) / (1024 * 1024)
            if file_size_mb > self.max_file_size_mb:
                raise StorageException(
                    f"File too large: {file_size_mb:.1f}MB > {self.max_file_size_mb}MB"
                )
            
            # Проверяем свободное место
            self._check_disk_space(len(file_data))
            
            # Сохраняем файл
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            # Вычисляем хеш файла
            file_hash = self._calculate_file_hash(file_path)
            
            file_info = {
                'filename': safe_filename,
                'original_filename': filename,
                'path': str(file_path),
                'relative_path': str(file_path.relative_to(self.base_path)),
                'size_bytes': len(file_data),
                'size_mb': file_size_mb,
                'hash': file_hash,
                'category': category,
                'created_at': datetime.utcnow().isoformat(),
                'exists': True
            }
            
            logger.info(
                f"File saved locally",
                filename=safe_filename,
                size_mb=file_size_mb,
                path=str(file_path)
            )
            
            return file_info
            
        except Exception as e:
            logger.error(f"Failed to save file {filename}: {e}")
            raise StorageException(f"Cannot save file: {e}")
    
    def save_file_stream(self, file_stream: BinaryIO, filename: str,
                        category: str = "downloads") -> Dict[str, Any]:
        """
        Сохранить файл из потока
        
        Args:
            file_stream: Поток данных файла
            filename: Имя файла
            category: Категория файла
            
        Returns:
            Информация о сохраненном файле
        """
        try:
            target_dir = self._get_category_dir(category)
            safe_filename = self._sanitize_filename(filename)
            file_path = target_dir / safe_filename
            
            # Сохраняем файл чанками
            file_size = 0
            hash_obj = hashlib.sha256()
            
            with open(file_path, 'wb') as f:
                while True:
                    chunk = file_stream.read(8192)  # 8KB чанки
                    if not chunk:
                        break
                    
                    file_size += len(chunk)
                    
                    # Проверяем размер
                    if file_size > self.max_file_size_mb * 1024 * 1024:
                        f.close()
                        file_path.unlink(missing_ok=True)  # Удаляем частично сохраненный файл
                        raise StorageException(
                            f"File too large: >{self.max_file_size_mb}MB"
                        )
                    
                    f.write(chunk)
                    hash_obj.update(chunk)
            
            file_hash = hash_obj.hexdigest()
            file_size_mb = file_size / (1024 * 1024)
            
            file_info = {
                'filename': safe_filename,
                'original_filename': filename,
                'path': str(file_path),
                'relative_path': str(file_path.relative_to(self.base_path)),
                'size_bytes': file_size,
                'size_mb': file_size_mb,
                'hash': file_hash,
                'category': category,
                'created_at': datetime.utcnow().isoformat(),
                'exists': True
            }
            
            logger.info(
                f"File stream saved locally",
                filename=safe_filename,
                size_mb=file_size_mb
            )
            
            return file_info
            
        except Exception as e:
            logger.error(f"Failed to save file stream {filename}: {e}")
            raise StorageException(f"Cannot save file stream: {e}")
    
    def get_file(self, filename: str, category: str = "downloads") -> Optional[bytes]:
        """
        Получить содержимое файла
        
        Args:
            filename: Имя файла
            category: Категория файла
            
        Returns:
            Содержимое файла или None если не найден
        """
        try:
            file_path = self._get_file_path(filename, category)
            
            if not file_path.exists():
                return None
            
            with open(file_path, 'rb') as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Failed to read file {filename}: {e}")
            raise StorageException(f"Cannot read file: {e}")
    
    @contextmanager
    def get_file_stream(self, filename: str, category: str = "downloads"):
        """
        Получить поток чтения файла
        
        Args:
            filename: Имя файла
            category: Категория файла
            
        Yields:
            Поток чтения файла
        """
        file_path = self._get_file_path(filename, category)
        
        if not file_path.exists():
            raise CustomFileNotFoundError(f"File not found: {filename}")
        
        try:
            with open(file_path, 'rb') as f:
                yield f
        except Exception as e:
            logger.error(f"Failed to open file stream {filename}: {e}")
            raise StorageException(f"Cannot open file stream: {e}")
    
    def file_exists(self, filename: str, category: str = "downloads") -> bool:
        """
        Проверить существование файла
        
        Args:
            filename: Имя файла
            category: Категория файла
            
        Returns:
            True если файл существует
        """
        try:
            file_path = self._get_file_path(filename, category)
            return file_path.exists()
        except Exception:
            return False
    
    def get_file_info(self, filename: str, category: str = "downloads") -> Optional[Dict[str, Any]]:
        """
        Получить информацию о файле
        
        Args:
            filename: Имя файла
            category: Категория файла
            
        Returns:
            Информация о файле или None
        """
        try:
            file_path = self._get_file_path(filename, category)
            
            if not file_path.exists():
                return None
            
            stat = file_path.stat()
            
            return {
                'filename': filename,
                'path': str(file_path),
                'relative_path': str(file_path.relative_to(self.base_path)),
                'size_bytes': stat.st_size,
                'size_mb': stat.st_size / (1024 * 1024),
                'category': category,
                'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'exists': True
            }
            
        except Exception as e:
            logger.error(f"Failed to get file info {filename}: {e}")
            return None
    
    def delete_file(self, filename: str, category: str = "downloads") -> bool:
        """
        Удалить файл
        
        Args:
            filename: Имя файла
            category: Категория файла
            
        Returns:
            True если файл был удален
        """
        try:
            file_path = self._get_file_path(filename, category)
            
            if file_path.exists():
                file_path.unlink()
                logger.info(f"File deleted: {filename}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete file {filename}: {e}")
            return False
    
    def create_temp_file(self, suffix: str = None, prefix: str = "temp_") -> str:
        """
        Создать временный файл
        
        Args:
            suffix: Расширение файла
            prefix: Префикс имени файла
            
        Returns:
            Путь к временному файлу
        """
        try:
            fd, temp_path = tempfile.mkstemp(
                suffix=suffix,
                prefix=prefix,
                dir=self.temp_dir
            )
            os.close(fd)  # Закрываем файловый дескриптор
            
            logger.debug(f"Temporary file created: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to create temp file: {e}")
            raise StorageException(f"Cannot create temporary file: {e}")
    
    def cleanup_temp_files(self, max_age_hours: int = None) -> int:
        """
        Очистить временные файлы
        
        Args:
            max_age_hours: Максимальный возраст файлов в часах
            
        Returns:
            Количество удаленных файлов
        """
        max_age_hours = max_age_hours or self.cleanup_after_hours
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        deleted_count = 0
        
        try:
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        try:
                            file_path.unlink()
                            deleted_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to delete temp file {file_path}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} temporary files")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup temp files: {e}")
            return 0
    
    def cleanup_old_files(self, category: str = "downloads", max_age_hours: int = None) -> int:
        """
        Очистить старые файлы в категории
        
        Args:
            category: Категория файлов
            max_age_hours: Максимальный возраст файлов
            
        Returns:
            Количество удаленных файлов
        """
        max_age_hours = max_age_hours or self.cleanup_after_hours
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        deleted_count = 0
        freed_space_mb = 0
        
        try:
            target_dir = self._get_category_dir(category)
            
            for file_path in target_dir.iterdir():
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            deleted_count += 1
                            freed_space_mb += file_size / (1024 * 1024)
                        except Exception as e:
                            logger.warning(f"Failed to delete file {file_path}: {e}")
            
            if deleted_count > 0:
                logger.info(
                    f"Cleaned up {deleted_count} files in {category}",
                    freed_space_mb=round(freed_space_mb, 2)
                )
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup {category} files: {e}")
            return 0
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Получить статистику хранилища
        
        Returns:
            Статистика использования хранилища
        """
        try:
            stats = {
                'base_path': str(self.base_path),
                'categories': {},
                'total_files': 0,
                'total_size_mb': 0,
                'disk_usage': {}
            }
            
            # Статистика по категориям
            for category in ['downloads', 'archives', 'thumbnails', 'temp']:
                cat_stats = self._get_category_stats(category)
                stats['categories'][category] = cat_stats
                stats['total_files'] += cat_stats['file_count']
                stats['total_size_mb'] += cat_stats['size_mb']
            
            # Использование диска
            disk_usage = shutil.disk_usage(self.base_path)
            stats['disk_usage'] = {
                'total_gb': disk_usage.total / (1024**3),
                'used_gb': disk_usage.used / (1024**3),
                'free_gb': disk_usage.free / (1024**3),
                'free_percent': (disk_usage.free / disk_usage.total) * 100
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {'error': str(e)}
    
    def _get_category_dir(self, category: str) -> Path:
        """Получить директорию категории"""
        category_dirs = {
            'downloads': self.downloads_dir,
            'archives': self.archives_dir,
            'thumbnails': self.thumbnails_dir,
            'temp': self.temp_dir
        }
        
        if category not in category_dirs:
            raise StorageException(f"Unknown category: {category}")
        
        return category_dirs[category]
    
    def _get_file_path(self, filename: str, category: str) -> Path:
        """Получить полный путь к файлу"""
        target_dir = self._get_category_dir(category)
        return target_dir / filename
    
    def _get_category_stats(self, category: str) -> Dict[str, Any]:
        """Получить статистику категории"""
        try:
            target_dir = self._get_category_dir(category)
            file_count = 0
            total_size = 0
            
            for file_path in target_dir.iterdir():
                if file_path.is_file():
                    file_count += 1
                    total_size += file_path.stat().st_size
            
            return {
                'directory': str(target_dir),
                'file_count': file_count,
                'size_bytes': total_size,
                'size_mb': total_size / (1024 * 1024),
                'avg_file_size_mb': (total_size / file_count / (1024 * 1024)) if file_count > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get {category} stats: {e}")
            return {
                'directory': str(self._get_category_dir(category)),
                'file_count': 0,
                'size_bytes': 0,
                'size_mb': 0,
                'avg_file_size_mb': 0,
                'error': str(e)
            }
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Создать безопасное имя файла
        
        Args:
            filename: Исходное имя файла
            
        Returns:
            Безопасное имя файла
        """
        # Заменяем опасные символы
        safe_chars = []
        for char in filename:
            if char.isalnum() or char in '.-_':
                safe_chars.append(char)
            else:
                safe_chars.append('_')
        
        safe_filename = ''.join(safe_chars)
        
        # Ограничиваем длину
        if len(safe_filename) > 200:
            name, ext = os.path.splitext(safe_filename)
            safe_filename = name[:190] + ext
        
        # Добавляем timestamp если файл уже существует
        counter = 0
        original_name = safe_filename
        
        while True:
            test_paths = []
            for category in ['downloads', 'archives', 'thumbnails', 'temp']:
                test_path = self._get_category_dir(category) / safe_filename
                test_paths.append(test_path)
            
            if not any(path.exists() for path in test_paths):
                break
            
            counter += 1
            name, ext = os.path.splitext(original_name)
            safe_filename = f"{name}_{counter}{ext}"
            
            if counter > 1000:  # Защита от бесконечного цикла
                timestamp = int(datetime.utcnow().timestamp())
                safe_filename = f"{name}_{timestamp}{ext}"
                break
        
        return safe_filename
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Вычислить SHA-256 хеш файла"""
        try:
            hash_obj = hashlib.sha256()
            
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    hash_obj.update(chunk)
            
            return hash_obj.hexdigest()
            
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""
    
    def _check_disk_space(self, required_bytes: int):
        """
        Проверить доступное место на диске
        
        Args:
            required_bytes: Требуемое место в байтах
            
        Raises:
            StorageException: Если недостаточно места
        """
        try:
            disk_usage = shutil.disk_usage(self.base_path)
            
            # Проверяем свободное место (оставляем минимум 1GB)
            min_free_bytes = 1024 * 1024 * 1024  # 1GB
            available_bytes = disk_usage.free - min_free_bytes
            
            if required_bytes > available_bytes:
                raise StorageException(
                    f"Insufficient disk space: need {required_bytes/(1024*1024):.1f}MB, "
                    f"available {available_bytes/(1024*1024):.1f}MB"
                )
            
            # Проверяем общий лимит хранилища
            current_size = sum(
                self._get_category_stats(cat)['size_bytes'] 
                for cat in ['downloads', 'archives', 'thumbnails']
            )
            
            max_size_bytes = self.max_total_size_gb * 1024 * 1024 * 1024
            
            if current_size + required_bytes > max_size_bytes:
                raise StorageException(
                    f"Storage quota exceeded: {(current_size + required_bytes)/(1024**3):.1f}GB > "
                    f"{self.max_total_size_gb}GB"
                )
                
        except StorageException:
            raise
        except Exception as e:
            logger.warning(f"Could not check disk space: {e}")
            # Не блокируем операцию если не можем проверить место

# Глобальный экземпляр
local_storage = LocalStorage()

# Утилитарные функции
def save_downloaded_file(file_data: bytes, filename: str) -> Dict[str, Any]:
    """Сохранить скачанный файл"""
    return local_storage.save_file(file_data, filename, 'downloads')

def save_thumbnail(thumbnail_data: bytes, filename: str) -> Dict[str, Any]:
    """Сохранить превью"""
    return local_storage.save_file(thumbnail_data, filename, 'thumbnails')

def save_archive(archive_data: bytes, filename: str) -> Dict[str, Any]:
    """Сохранить архив"""
    return local_storage.save_file(archive_data, filename, 'archives')

def cleanup_old_downloads(hours: int = 24) -> int:
    """Очистить старые загруженные файлы"""
    return local_storage.cleanup_old_files('downloads', hours)

def get_file_for_upload(filename: str, category: str = 'downloads'):
    """Получить файл для загрузки в CDN"""
    return local_storage.get_file_stream(filename, category)

def ensure_storage_space():
    """Обеспечить наличие места в хранилище"""
    try:
        # Очищаем временные файлы
        local_storage.cleanup_temp_files()
        
        # Получаем статистику
        stats = local_storage.get_storage_stats()
        
        # Если места мало, очищаем старые файлы
        if stats.get('disk_usage', {}).get('free_percent', 100) < 10:
            logger.warning("Low disk space, cleaning up old files")
            
            # Очищаем в порядке приоритета
            local_storage.cleanup_old_files('temp', 1)  # Временные файлы старше 1 часа
            local_storage.cleanup_old_files('downloads', 12)  # Загрузки старше 12 часов
            local_storage.cleanup_old_files('thumbnails', 12)  # Превью старше 12 часов
            local_storage.cleanup_old_files('archives', 6)  # Архивы старше 6 часов
            
    except Exception as e:
        logger.error(f"Failed to ensure storage space: {e}")

# Автоматическая очистка при импорте модуля
try:
    ensure_storage_space()
except Exception as e:
    logger.warning(f"Could not perform initial cleanup: {e}")