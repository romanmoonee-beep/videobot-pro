"""
VideoBot Pro - Base Storage
Базовый класс для всех типов хранилищ
"""

import os
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union, BinaryIO
from dataclasses import dataclass
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)

class StorageError(Exception):
    """Базовое исключение для ошибок хранилища"""
    pass

class StorageConnectionError(StorageError):
    """Ошибка подключения к хранилищу"""
    pass

class StorageUploadError(StorageError):
    """Ошибка загрузки файла"""
    pass

class StorageDownloadError(StorageError):
    """Ошибка скачивания файла"""
    pass

class StorageNotFoundError(StorageError):
    """Файл не найден в хранилище"""
    pass

class StorageQuotaExceededError(StorageError):
    """Превышена квота хранилища"""
    pass

@dataclass
class StorageConfig:
    """Конфигурация хранилища"""
    bucket_name: str
    region: str = "us-east-1"
    endpoint_url: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    max_file_size_mb: int = 500
    allowed_extensions: List[str] = None
    encryption: bool = False
    compression: bool = False
    public_read: bool = False
    cdn_domain: Optional[str] = None
    
    def __post_init__(self):
        if self.allowed_extensions is None:
            self.allowed_extensions = ['.mp4', '.webm', '.mp3', '.wav', '.zip']

@dataclass
class StorageFileInfo:
    """Информация о файле в хранилище"""
    key: str
    size: int
    last_modified: datetime
    etag: str
    content_type: str
    metadata: Dict[str, str] = None
    public_url: Optional[str] = None
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None

class BaseStorage(ABC):
    """
    Базовый класс для всех хранилищ файлов
    
    Определяет интерфейс для работы с различными
    типами хранилищ (S3-совместимые, локальное)
    """
    
    def __init__(self, config: Union[StorageConfig, dict]):
        """
        Инициализация хранилища
        
        Args:
            config: Конфигурация хранилища
        """
        if isinstance(config, dict):
            config = StorageConfig(**config)
        
        self.config = config
        self._client = None
        self._connected = False
        
    @abstractmethod
    async def connect(self) -> bool:
        """
        Установить соединение с хранилищем
        
        Returns:
            True если соединение установлено
            
        Raises:
            StorageConnectionError: При ошибке подключения
        """
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Закрыть соединение с хранилищем"""
        pass
    
    @abstractmethod
    async def upload_file(
        self,
        local_path: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False
    ) -> StorageFileInfo:
        """
        Загрузить файл в хранилище
        
        Args:
            local_path: Путь к локальному файлу
            key: Ключ (путь) в хранилище
            metadata: Метаданные файла
            content_type: MIME-тип файла
            public: Сделать файл публично доступным
            
        Returns:
            Информация о загруженном файле
            
        Raises:
            StorageUploadError: При ошибке загрузки
        """
        pass
    
    @abstractmethod
    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False
    ) -> StorageFileInfo:
        """
        Загрузить данные в виде байтов
        
        Args:
            data: Данные для загрузки
            key: Ключ в хранилище
            metadata: Метаданные
            content_type: MIME-тип
            public: Публичный доступ
            
        Returns:
            Информация о загруженном файле
        """
        pass
    
    @abstractmethod
    async def download_file(
        self,
        key: str,
        local_path: str
    ) -> bool:
        """
        Скачать файл из хранилища
        
        Args:
            key: Ключ файла в хранилище
            local_path: Путь для сохранения файла
            
        Returns:
            True если файл скачан успешно
            
        Raises:
            StorageDownloadError: При ошибке скачивания
            StorageNotFoundError: Если файл не найден
        """
        pass
    
    @abstractmethod
    async def download_bytes(self, key: str) -> bytes:
        """
        Скачать файл как байты
        
        Args:
            key: Ключ файла
            
        Returns:
            Содержимое файла в виде байтов
        """
        pass
    
    @abstractmethod
    async def delete_file(self, key: str) -> bool:
        """
        Удалить файл из хранилища
        
        Args:
            key: Ключ файла
            
        Returns:
            True если файл удален
        """
        pass
    
    @abstractmethod
    async def file_exists(self, key: str) -> bool:
        """
        Проверить существование файла
        
        Args:
            key: Ключ файла
            
        Returns:
            True если файл существует
        """
        pass
    
    @abstractmethod
    async def get_file_info(self, key: str) -> StorageFileInfo:
        """
        Получить информацию о файле
        
        Args:
            key: Ключ файла
            
        Returns:
            Информация о файле
            
        Raises:
            StorageNotFoundError: Если файл не найден
        """
        pass
    
    @abstractmethod
    async def list_files(
        self,
        prefix: str = "",
        limit: Optional[int] = None
    ) -> List[StorageFileInfo]:
        """
        Получить список файлов
        
        Args:
            prefix: Префикс для фильтрации
            limit: Максимальное количество файлов
            
        Returns:
            Список информации о файлах
        """
        pass
    
    @abstractmethod
    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "GET"
    ) -> str:
        """
        Генерировать предподписанный URL
        
        Args:
            key: Ключ файла
            expires_in: Время жизни URL в секундах
            method: HTTP метод
            
        Returns:
            Предподписанный URL
        """
        pass
    
    @abstractmethod
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Получить статистику хранилища
        
        Returns:
            Словарь со статистикой
        """
        pass
    
    # Общие методы для всех хранилищ
    
    def generate_file_key(
        self,
        filename: str,
        user_id: Optional[int] = None,
        platform: Optional[str] = None,
        date_folder: bool = True
    ) -> str:
        """
        Генерировать ключ для файла
        
        Args:
            filename: Имя файла
            user_id: ID пользователя
            platform: Платформа
            date_folder: Создавать папку по дате
            
        Returns:
            Ключ файла в хранилище
        """
        parts = []
        
        # Добавляем дату
        if date_folder:
            today = datetime.utcnow()
            parts.append(f"{today.year:04d}/{today.month:02d}/{today.day:02d}")
        
        # Добавляем платформу
        if platform:
            parts.append(platform)
        
        # Добавляем пользователя
        if user_id:
            parts.append(f"user_{user_id}")
        
        # Добавляем имя файла
        parts.append(filename)
        
        return "/".join(parts)
    
    def generate_unique_filename(
        self,
        original_name: str,
        add_timestamp: bool = True
    ) -> str:
        """
        Генерировать уникальное имя файла
        
        Args:
            original_name: Оригинальное имя
            add_timestamp: Добавлять временную метку
            
        Returns:
            Уникальное имя файла
        """
        # Разбираем имя и расширение
        path = Path(original_name)
        name = path.stem
        extension = path.suffix
        
        # Санитизируем имя
        safe_name = self._sanitize_filename(name)
        
        # Добавляем временную метку
        if add_timestamp:
            timestamp = int(datetime.utcnow().timestamp())
            safe_name = f"{safe_name}_{timestamp}"
        
        # Добавляем хеш для уникальности
        hash_suffix = hashlib.md5(
            f"{safe_name}_{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:8]
        
        return f"{safe_name}_{hash_suffix}{extension}"
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Очистить имя файла от недопустимых символов
        
        Args:
            filename: Исходное имя файла
            
        Returns:
            Очищенное имя файла
        """
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
            filename = filename[:100]
        
        return filename
    
    def get_content_type(self, filename: str) -> str:
        """
        Определить MIME-тип файла по расширению
        
        Args:
            filename: Имя файла
            
        Returns:
            MIME-тип
        """
        extension = Path(filename).suffix.lower()
        
        content_types = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.avi': 'video/avi',
            '.mov': 'video/quicktime',
            '.mkv': 'video/x-matroska',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.m4a': 'audio/mp4',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.txt': 'text/plain',
            '.json': 'application/json',
        }
        
        return content_types.get(extension, 'application/octet-stream')
    
    def validate_file(self, filepath: str) -> bool:
        """
        Валидировать файл перед загрузкой
        
        Args:
            filepath: Путь к файлу
            
        Returns:
            True если файл валиден
            
        Raises:
            StorageError: При ошибках валидации
        """
        if not os.path.exists(filepath):
            raise StorageError(f"File not found: {filepath}")
        
        # Проверяем размер файла
        file_size = os.path.getsize(filepath)
        max_size = self.config.max_file_size_mb * 1024 * 1024
        
        if file_size > max_size:
            raise StorageError(
                f"File too large: {file_size} bytes, max: {max_size} bytes"
            )
        
        # Проверяем расширение
        extension = Path(filepath).suffix.lower()
        if extension not in self.config.allowed_extensions:
            raise StorageError(
                f"File type not allowed: {extension}"
            )
        
        return True
    
    async def copy_file(
        self,
        source_key: str,
        dest_key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageFileInfo:
        """
        Копировать файл внутри хранилища
        
        Args:
            source_key: Ключ исходного файла
            dest_key: Ключ нового файла
            metadata: Новые метаданные
            
        Returns:
            Информация о новом файле
        """
        # По умолчанию скачиваем и загружаем обратно
        # Наследники могут переопределить для оптимизации
        data = await self.download_bytes(source_key)
        source_info = await self.get_file_info(source_key)
        
        return await self.upload_bytes(
            data=data,
            key=dest_key,
            metadata=metadata or source_info.metadata,
            content_type=source_info.content_type
        )
    
    async def move_file(
        self,
        source_key: str,
        dest_key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageFileInfo:
        """
        Переместить файл внутри хранилища
        
        Args:
            source_key: Ключ исходного файла
            dest_key: Ключ нового расположения
            metadata: Новые метаданные
            
        Returns:
            Информация о перемещенном файле
        """
        # Копируем файл
        new_info = await self.copy_file(source_key, dest_key, metadata)
        
        # Удаляем оригинал
        await self.delete_file(source_key)
        
        return new_info
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(bucket={self.config.bucket_name})>"