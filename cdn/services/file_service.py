"""
VideoBot Pro - CDN File Service
Сервис для работы с файлами в CDN
"""

import os
import asyncio
import aiofiles
import structlog
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, FileResponse

from shared.models.user import User
from shared.config.storage import storage_config
from ..config import cdn_config

logger = structlog.get_logger(__name__)

class FileService:
    """Сервис для управления файлами в CDN"""
    
    def __init__(self):
        self.initialized = False
        self.storage_path = cdn_config.storage_path
        self.cache_path = cdn_config.cache_path
        
        # Размер чанка для потокового чтения
        self.chunk_size = 8192  # 8KB
        self.stream_chunk_size = 1024 * 1024  # 1MB для видео
    
    async def initialize(self):
        """Инициализация файлового сервиса"""
        if self.initialized:
            return
        
        logger.info("Initializing File Service...")
        
        try:
            # Проверяем доступность директорий
            self.storage_path.mkdir(parents=True, exist_ok=True)
            self.cache_path.mkdir(parents=True, exist_ok=True)
            
            self.initialized = True
            logger.info("File Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize File Service: {e}")
            raise
    
    async def shutdown(self):
        """Завершение работы сервиса"""
        logger.info("Shutting down File Service...")
        self.initialized = False
    
    async def file_exists(self, file_path: str) -> bool:
        """Проверка существования файла"""
        try:
            # Проверяем в локальном хранилище
            local_path = self.storage_path / file_path
            if local_path.exists() and local_path.is_file():
                return True
            
            # Проверяем во внешнем хранилище
            if storage_config and storage_config._initialized:
                return await storage_config.file_exists(file_path)
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking file existence {file_path}: {e}")
            return False
    
    async def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Получение информации о файле"""
        try:
            local_path = self.storage_path / file_path
            
            # Проверяем локальный файл
            if local_path.exists() and local_path.is_file():
                stat = local_path.stat()
                return {
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime),
                    'content_type': self._get_content_type(file_path),
                    'location': 'local'
                }
            
            # Проверяем внешнее хранилище
            if storage_config and storage_config._initialized:
                external_info = await storage_config.get_file_info(file_path)
                if external_info:
                    return {
                        'size': external_info.get('size', 0),
                        'modified': external_info.get('modified', datetime.utcnow()),
                        'content_type': self._get_content_type(file_path),
                        'location': 'external'
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting file info {file_path}: {e}")
            return None
    
    async def get_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """Получение расширенных метаданных файла"""
        try:
            base_info = await self.get_file_info(file_path)
            if not base_info:
                return {}
            
            metadata = {
                **base_info,
                'file_path': file_path,
                'file_name': Path(file_path).name,
                'file_extension': Path(file_path).suffix.lower(),
                'file_type': cdn_config.get_file_type(file_path),
                'is_cached': await self._is_file_cached(file_path),
                'cache_path': str(self.cache_path / file_path) if await self._is_file_cached(file_path) else None,
                'download_url': cdn_config.get_file_url(file_path),
                'expires_at': await self._get_file_expiry(file_path)
            }
            
            # Дополнительные метаданные для изображений и видео
            if metadata['file_type'] in ['image', 'video']:
                media_info = await self._get_media_info(file_path)
                metadata.update(media_info)
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error getting file metadata {file_path}: {e}")
            return {}
    
    async def serve_file(self, file_path: str, file_info: Dict[str, Any]) -> StreamingResponse:
        """Обслуживание файла (полная отдача)"""
        try:
            # Определяем источник файла
            file_source = await self._get_file_source(file_path)
            
            if not file_source:
                raise HTTPException(status_code=404, detail="File not found")
            
            # Подготавливаем заголовки
            headers = {
                "Content-Length": str(file_info['size']),
                "Content-Type": file_info.get('content_type', 'application/octet-stream'),
                "Last-Modified": file_info.get('modified', datetime.utcnow()).strftime(
                    "%a, %d %b %Y %H:%M:%S GMT"
                ),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600"
            }
            
            # Определяем имя файла для скачивания
            filename = Path(file_path).name
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
            
            # Создаем генератор для потокового чтения
            async def generate():
                async for chunk in self._read_file_chunks(file_source, file_info['size']):
                    yield chunk
            
            return StreamingResponse(
                generate(),
                status_code=200,
                headers=headers,
                media_type=file_info.get('content_type', 'application/octet-stream')
            )
            
        except Exception as e:
            logger.error(f"Error serving file {file_path}: {e}")
            raise HTTPException(status_code=500, detail="Failed to serve file")
    
    async def serve_file_range(self, file_path: str, range_header: str, file_info: Dict[str, Any]) -> StreamingResponse:
        """Обслуживание файла с поддержкой Range запросов"""
        try:
            # Парсим Range заголовок
            start, end = self._parse_range_header(range_header, file_info['size'])
            
            if start is None:
                raise HTTPException(status_code=416, detail="Range not satisfiable")
            
            # Получаем источник файла
            file_source = await self._get_file_source(file_path)
            
            if not file_source:
                raise HTTPException(status_code=404, detail="File not found")
            
            # Вычисляем размер части
            content_length = end - start + 1
            
            # Подготавливаем заголовки
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_info['size']}",
                "Content-Length": str(content_length),
                "Content-Type": file_info.get('content_type', 'application/octet-stream'),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600"
            }
            
            # Создаем генератор для чтения части файла
            async def generate():
                async for chunk in self._read_file_range(file_source, start, end):
                    yield chunk
            
            return StreamingResponse(
                generate(),
                status_code=206,  # Partial Content
                headers=headers,
                media_type=file_info.get('content_type', 'application/octet-stream')
            )
            
        except Exception as e:
            logger.error(f"Error serving file range {file_path}: {e}")
            raise HTTPException(status_code=500, detail="Failed to serve file range")
    
    async def check_access_permissions(self, file_path: str, user: Optional[User]) -> bool:
        """Проверка прав доступа к файлу"""
        try:
            # Если пользователь не авторизован
            if not user:
                return False
            
            # Админы и владельцы имеют доступ ко всем файлам
            if user.user_type in ['admin', 'owner']:
                return True
            
            # Проверяем, принадлежит ли файл пользователю
            if await self._is_user_file(file_path, user.id):
                return True
            
            # Проверяем публичные файлы
            if await self._is_public_file(file_path):
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking access permissions {file_path}: {e}")
            return False
    
    async def check_delete_permissions(self, file_path: str, user: User) -> bool:
        """Проверка прав на удаление файла"""
        try:
            # Админы и владельцы могут удалять любые файлы
            if user.user_type in ['admin', 'owner']:
                return True
            
            # Пользователи могут удалять только свои файлы
            return await self._is_user_file(file_path, user.id)
            
        except Exception as e:
            logger.error(f"Error checking delete permissions {file_path}: {e}")
            return False
    
    async def check_directory_access(self, directory: str, user: User) -> bool:
        """Проверка доступа к директории"""
        try:
            # Админы имеют доступ ко всем директориям
            if user.user_type in ['admin', 'owner']:
                return True
            
            # Пользователи имеют доступ только к своим директориям
            user_prefix = f"users/{user.id}/"
            return directory.startswith(user_prefix) or directory == f"users/{user.id}"
            
        except Exception as e:
            logger.error(f"Error checking directory access {directory}: {e}")
            return False
    
    async def delete_file(self, file_path: str) -> bool:
        """Удаление файла"""
        try:
            success = False
            
            # Удаляем из локального хранилища
            local_path = self.storage_path / file_path
            if local_path.exists():
                local_path.unlink()
                success = True
                logger.info(f"Deleted local file: {file_path}")
            
            # Удаляем из внешнего хранилища
            if storage_config and storage_config._initialized:
                if await storage_config.delete_file(file_path):
                    success = True
                    logger.info(f"Deleted external file: {file_path}")
            
            # Удаляем из кэша
            cache_path = self.cache_path / file_path
            if cache_path.exists():
                cache_path.unlink()
                logger.info(f"Deleted cached file: {file_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return False
    
    async def list_files(self, directory: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Получение списка файлов в директории"""
        try:
            files = []
            
            # Получаем файлы из локального хранилища
            local_dir = self.storage_path / directory
            if local_dir.exists() and local_dir.is_dir():
                for item in local_dir.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(self.storage_path)
                        file_info = await self.get_file_info(str(rel_path))
                        if file_info:
                            files.append({
                                'path': str(rel_path),
                                'name': item.name,
                                'size': file_info['size'],
                                'modified': file_info['modified'].isoformat(),
                                'type': cdn_config.get_file_type(item.name),
                                'location': 'local'
                            })
            
            # Получаем файлы из внешнего хранилища
            if storage_config and storage_config._initialized:
                try:
                    external_files = await storage_config.list_files(directory)
                    for ext_file in external_files:
                        # Избегаем дубликатов
                        if not any(f['path'] == ext_file['path'] for f in files):
                            files.append({
                                **ext_file,
                                'location': 'external'
                            })
                except Exception as e:
                    logger.warning(f"Failed to list external files: {e}")
            
            # Сортируем по дате изменения
            files.sort(key=lambda x: x.get('modified', ''), reverse=True)
            
            # Применяем пагинацию
            return files[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"Error listing files in {directory}: {e}")
            return []
    
    async def is_file_expired(self, file_path: str) -> bool:
        """Проверка, истек ли срок хранения файла"""
        try:
            # Получаем информацию о файле для определения владельца
            user_type = await self._get_file_owner_type(file_path)
            retention_hours = cdn_config.get_retention_hours(user_type)
            
            file_info = await self.get_file_info(file_path)
            if not file_info:
                return True
            
            # Проверяем срок истечения
            expiry_time = file_info['modified'] + timedelta(hours=retention_hours)
            return datetime.utcnow() > expiry_time
            
        except Exception as e:
            logger.error(f"Error checking file expiry {file_path}: {e}")
            return False
    
    # Приватные методы
    
    def _get_content_type(self, file_path: str) -> str:
        """Определение MIME типа файла"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(file_path)
        return content_type or 'application/octet-stream'
    
    def _parse_range_header(self, range_header: str, file_size: int) -> Tuple[Optional[int], Optional[int]]:
        """Парсинг Range заголовка"""
        try:
            if not range_header.startswith('bytes='):
                return None, None
            
            range_spec = range_header[6:]  # Убираем 'bytes='
            
            if '-' not in range_spec:
                return None, None
            
            start_str, end_str = range_spec.split('-', 1)
            
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
            
            # Проверяем валидность диапазона
            if start >= file_size or end >= file_size or start > end:
                return None, None
            
            return start, end
            
        except Exception:
            return None, None
    
    async def _get_file_source(self, file_path: str) -> Optional[str]:
        """Получение источника файла (локальный путь или URL)"""
        try:
            # Проверяем кэш
            cache_path = self.cache_path / file_path
            if cache_path.exists():
                await cdn_config.update_stats('cache_hit')
                return str(cache_path)
            
            await cdn_config.update_stats('cache_miss')
            
            # Проверяем локальное хранилище
            local_path = self.storage_path / file_path
            if local_path.exists():
                # Копируем в кэш для быстрого доступа
                await self._cache_file(local_path, cache_path)
                return str(cache_path)
            
            # Загружаем из внешнего хранилища
            if storage_config and storage_config._initialized:
                if await storage_config.file_exists(file_path):
                    # Загружаем файл в кэш
                    await self._download_to_cache(file_path, cache_path)
                    return str(cache_path)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting file source {file_path}: {e}")
            return None
    
    async def _read_file_chunks(self, file_path: str, file_size: int):
        """Генератор для чтения файла по частям"""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                while True:
                    chunk = await f.read(self.stream_chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            logger.error(f"Error reading file chunks {file_path}: {e}")
            raise
    
    async def _read_file_range(self, file_path: str, start: int, end: int):
        """Генератор для чтения части файла"""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                await f.seek(start)
                remaining = end - start + 1
                
                while remaining > 0:
                    chunk_size = min(self.stream_chunk_size, remaining)
                    chunk = await f.read(chunk_size)
                    
                    if not chunk:
                        break
                    
                    remaining -= len(chunk)
                    yield chunk
                    
        except Exception as e:
            logger.error(f"Error reading file range {file_path}: {e}")
            raise
    
    async def _cache_file(self, source_path: Path, cache_path: Path):
        """Копирование файла в кэш"""
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(source_path, 'rb') as src:
                async with aiofiles.open(cache_path, 'wb') as dst:
                    while True:
                        chunk = await src.read(self.chunk_size)
                        if not chunk:
                            break
                        await dst.write(chunk)
                        
        except Exception as e:
            logger.error(f"Error caching file {source_path}: {e}")
            raise
    
    async def _download_to_cache(self, file_path: str, cache_path: Path):
        """Загрузка файла из внешнего хранилища в кэш"""
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Загружаем файл из внешнего хранилища
            file_data = await storage_config.download_file(file_path)
            
            async with aiofiles.open(cache_path, 'wb') as f:
                await f.write(file_data)
                
        except Exception as e:
            logger.error(f"Error downloading to cache {file_path}: {e}")
            raise
    
    async def _is_file_cached(self, file_path: str) -> bool:
        """Проверка, есть ли файл в кэше"""
        cache_path = self.cache_path / file_path
        return cache_path.exists()
    
    async def _get_file_expiry(self, file_path: str) -> Optional[str]:
        """Получение времени истечения файла"""
        try:
            user_type = await self._get_file_owner_type(file_path)
            retention_hours = cdn_config.get_retention_hours(user_type)
            
            file_info = await self.get_file_info(file_path)
            if file_info:
                expiry_time = file_info['modified'] + timedelta(hours=retention_hours)
                return expiry_time.isoformat()
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting file expiry {file_path}: {e}")
            return None
    
    async def _get_media_info(self, file_path: str) -> Dict[str, Any]:
        """Получение информации о медиа файле"""
        # Заглушка для получения метаданных медиа
        # В реальной реализации здесь будет использоваться ffprobe или подобная библиотека
        return {
            'duration': None,
            'bitrate': None,
            'resolution': None,
            'codec': None
        }
    
    async def _is_user_file(self, file_path: str, user_id: int) -> bool:
        """Проверка, принадлежит ли файл пользователю"""
        # Простая проверка по пути (файлы пользователей в папке users/user_id/)
        return file_path.startswith(f"users/{user_id}/")
    
    async def _is_public_file(self, file_path: str) -> bool:
        """Проверка, является ли файл публичным"""
        # Публичные файлы в папке public/
        return file_path.startswith("public/")
    
    async def _get_file_owner_type(self, file_path: str) -> str:
        """Получение типа владельца файла"""
        # Упрощенная логика определения типа пользователя по пути
        if file_path.startswith("admin/"):
            return "admin"
        elif file_path.startswith("premium/"):
            return "premium"
        elif file_path.startswith("trial/"):
            return "trial"
        else:
            return "free"