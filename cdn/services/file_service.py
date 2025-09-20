"""
VideoBot Pro - Updated CDN File Service
Обновленный файловый сервис с интеграцией облачных хранилищ
"""

import os
import asyncio
import aiofiles
import structlog
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse

from shared.models.user import User
from .config import cdn_config
from .storage_integration import cdn_storage_manager

logger = structlog.get_logger(__name__)

class FileService:
    """Обновленный сервис для управления файлами в CDN с облачными хранилищами"""
    
    def __init__(self):
        self.initialized = False
        self.storage_path = cdn_config.storage_path
        self.cache_path = cdn_config.cache_path
        
        # Размеры чанков для стриминга
        self.chunk_size = 8192  # 8KB
        self.stream_chunk_size = 1024 * 1024  # 1MB для видео
    
    async def initialize(self):
        """Инициализация файлового сервиса"""
        if self.initialized:
            return
        
        logger.info("Initializing Enhanced File Service...")
        
        try:
            # Инициализируем директории
            self.storage_path.mkdir(parents=True, exist_ok=True)
            self.cache_path.mkdir(parents=True, exist_ok=True)
            
            # Инициализируем менеджер хранилищ
            await cdn_storage_manager.initialize()
            
            self.initialized = True
            logger.info("Enhanced File Service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Enhanced File Service: {e}")
            raise
    
    async def shutdown(self):
        """Завершение работы сервиса"""
        logger.info("Shutting down Enhanced File Service...")
        self.initialized = False
    
    async def upload_file_to_cloud(
        self,
        local_file_path: str,
        filename: str,
        user: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Загрузка файла в облачное хранилище
        
        Args:
            local_file_path: Путь к локальному файлу
            filename: Имя файла
            user: Пользователь
            metadata: Дополнительные метаданные
            
        Returns:
            Результат загрузки с URL'ами
        """
        try:
            # Генерируем ключ файла
            file_key = self._generate_file_key(filename, user)
            
            # Подготавливаем метаданные
            upload_metadata = {
                'original_filename': filename,
                'content_type': self._get_content_type(filename),
                'uploaded_by': user.username if user else 'anonymous'
            }
            
            if metadata:
                upload_metadata.update(metadata)
            
            # Загружаем файл
            result = await cdn_storage_manager.upload_file(
                local_file_path=local_file_path,
                file_key=file_key,
                user=user,
                metadata=upload_metadata
            )
            
            if result['success']:
                logger.info(
                    "File uploaded to cloud storage",
                    filename=filename,
                    storage_type=result.get('storage_type'),
                    file_size=result.get('file_size')
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Cloud upload failed: {e}", filename=filename)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def file_exists(self, file_path: str) -> bool:
        """Проверка существования файла в любом хранилище"""
        try:
            # Проверяем в облачных хранилищах
            cloud_info = await cdn_storage_manager.get_file_info(file_path)
            if cloud_info:
                return True
            
            # Проверяем локально
            local_path = self.storage_path / file_path
            return local_path.exists()
            
        except Exception as e:
            logger.error(f"Error checking file existence {file_path}: {e}")
            return False
    
    async def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Получение информации о файле из любого хранилища"""
        try:
            # Сначала проверяем облачные хранилища
            cloud_info = await cdn_storage_manager.get_file_info(file_path)
            if cloud_info:
                return cloud_info
            
            # Проверяем локальное хранилище
            local_path = self.storage_path / file_path
            if local_path.exists():
                stat = local_path.stat()
                return {
                    'key': file_path,
                    'size': stat.st_size,
                    'last_modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'content_type': self._get_content_type(file_path),
                    'storage_type': 'local',
                    'local_path': str(local_path)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting file info {file_path}: {e}")
            return None
    
    async def serve_file(self, file_path: str, file_info: Dict[str, Any], user: Optional[User] = None) -> Any:
        """Обслуживание файла с умной маршрутизацией"""
        try:
            storage_type = file_info.get('storage_type', 'unknown')
            
            # Для облачных файлов с публичным URL - делаем редирект
            if storage_type in ['cloud'] and file_info.get('public_url'):
                public_url = file_info['public_url']
                logger.info(f"Redirecting to public URL: {public_url}")
                return RedirectResponse(url=public_url, status_code=302)
            
            # Для облачных файлов с CDN URL - делаем редирект
            if storage_type in ['cloud'] and file_info.get('cdn_url'):
                cdn_url = file_info['cdn_url']
                logger.info(f"Redirecting to CDN URL: {cdn_url}")
                return RedirectResponse(url=cdn_url, status_code=302)
            
            # Для локальных файлов - стримим напрямую
            if storage_type == 'local':
                return await self._serve_local_file(file_path, file_info)
            
            # Fallback - пытаемся скачать и отдать
            return await self._serve_cloud_file_direct(file_path, file_info, user)
            
        except Exception as e:
            logger.error(f"Error serving file {file_path}: {e}")
            raise HTTPException(status_code=500, detail="Failed to serve file")
    
    async def _serve_local_file(self, file_path: str, file_info: Dict[str, Any]) -> StreamingResponse:
        """Прямая подача локального файла"""
        try:
            local_path = file_info.get('local_path') or str(self.storage_path / file_path)
            
            # Подготавливаем заголовки
            headers = {
                "Content-Length": str(file_info['size']),
                "Content-Type": file_info.get('content_type', 'application/octet-stream'),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600"
            }
            
            # Определяем имя файла для скачивания
            filename = Path(file_path).name
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
            
            # Создаем генератор для потокового чтения
            async def generate():
                async with aiofiles.open(local_path, 'rb') as f:
                    while True:
                        chunk = await f.read(self.stream_chunk_size)
                        if not chunk:
                            break
                        yield chunk
            
            return StreamingResponse(
                generate(),
                status_code=200,
                headers=headers,
                media_type=file_info.get('content_type', 'application/octet-stream')
            )
            
        except Exception as e:
            logger.error(f"Error serving local file {file_path}: {e}")
            raise HTTPException(status_code=500, detail="Failed to serve local file")
    
    async def _serve_cloud_file_direct(self, file_path: str, file_info: Dict[str, Any], user: Optional[User]) -> StreamingResponse:
        """Прямая подача файла из облачного хранилища"""
        try:
            # Создаем временный файл для кэширования
            cache_path = self.cache_path / file_path
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Скачиваем файл если его нет в кэше
            if not cache_path.exists():
                success = await cdn_storage_manager.download_file(
                    file_key=file_path,
                    local_path=str(cache_path),
                    user=user
                )
                
                if not success:
                    raise HTTPException(status_code=404, detail="File not found in storage")
            
            # Обновляем информацию о файле
            cache_info = {
                **file_info,
                'local_path': str(cache_path),
                'size': cache_path.stat().st_size if cache_path.exists() else file_info.get('size', 0)
            }
            
            # Отдаем из кэша
            return await self._serve_local_file(file_path, cache_info)
            
        except Exception as e:
            logger.error(f"Error serving cloud file {file_path}: {e}")
            raise HTTPException(status_code=500, detail="Failed to serve cloud file")
    
    async def serve_file_range(self, file_path: str, range_header: str, file_info: Dict[str, Any], user: Optional[User] = None) -> StreamingResponse:
        """Обслуживание файла с поддержкой Range запросов"""
        try:
            # Парсим Range заголовок
            start, end = self._parse_range_header(range_header, file_info['size'])
            
            if start is None:
                raise HTTPException(status_code=416, detail="Range not satisfiable")
            
            storage_type = file_info.get('storage_type', 'unknown')
            
            # Для облачных файлов сначала кэшируем
            if storage_type == 'cloud':
                cache_path = self.cache_path / file_path
                if not cache_path.exists():
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    await cdn_storage_manager.download_file(file_path, str(cache_path), user)
                
                local_path = str(cache_path)
            else:
                local_path = file_info.get('local_path') or str(self.storage_path / file_path)
            
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
                async with aiofiles.open(local_path, 'rb') as f:
                    await f.seek(start)
                    remaining = content_length
                    
                    while remaining > 0:
                        chunk_size = min(self.stream_chunk_size, remaining)
                        chunk = await f.read(chunk_size)
                        
                        if not chunk:
                            break
                        
                        remaining -= len(chunk)
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
            # Если пользователь не авторизован - проверяем публичность
            if not user:
                file_info = await self.get_file_info(file_path)
                if file_info and file_info.get('public_url'):
                    return True
                return False
            
            # Админы и владельцы имеют доступ ко всем файлам
            if user.user_type in ['admin', 'owner']:
                return True
            
            # Проверяем, принадлежит ли файл пользователю
            if await self._is_user_file(file_path, user.id):
                return True
            
            # Проверяем публичные файлы
            file_info = await self.get_file_info(file_path)
            if file_info and file_info.get('public_url'):
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
    
    async def delete_file(self, file_path: str, user: Optional[User] = None) -> bool:
        """Удаление файла из всех хранилищ"""
        try:
            # Удаляем из облачных хранилищ
            cloud_result = await cdn_storage_manager.delete_file(file_path, user)
            
            # Удаляем локальную копию
            local_path = self.storage_path / file_path
            local_deleted = False
            if local_path.exists():
                local_path.unlink()
                local_deleted = True
            
            # Удаляем из кэша
            cache_path = self.cache_path / file_path
            if cache_path.exists():
                cache_path.unlink()
            
            success = cloud_result.get('success', False) or local_deleted
            
            if success:
                logger.info(f"File deleted: {file_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return False
    
    async def list_files(self, directory: str, limit: int = 100, offset: int = 0, user: Optional[User] = None) -> List[Dict[str, Any]]:
        """Получение списка файлов из всех хранилищ"""
        try:
            files = []
            
            # Получаем файлы из облачных хранилищ
            if cdn_storage_manager.primary_storage:
                try:
                    cloud_files = await cdn_storage_manager.primary_storage.list_files(
                        prefix=directory,
                        limit=limit * 2  # Больше лимит для фильтрации
                    )
                    
                    for file_info in cloud_files:
                        # Проверяем права доступа
                        if await self.check_access_permissions(file_info.key, user):
                            files.append({
                                'path': file_info.key,
                                'name': Path(file_info.key).name,
                                'size': file_info.size,
                                'modified': file_info.last_modified.isoformat(),
                                'type': cdn_config.get_file_type(file_info.key),
                                'storage_type': 'cloud',
                                'public_url': file_info.public_url,
                                'cdn_url': await cdn_storage_manager._generate_cdn_url(
                                    cdn_storage_manager.primary_storage, file_info.key, user
                                )
                            })
                            
                except Exception as e:
                    logger.warning(f"Failed to list cloud files: {e}")
            
            # Получаем файлы из локального хранилища
            local_dir = self.storage_path / directory
            if local_dir.exists() and local_dir.is_dir():
                for item in local_dir.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(self.storage_path)
                        
                        # Проверяем права доступа
                        if await self.check_access_permissions(str(rel_path), user):
                            # Избегаем дубликатов (приоритет у облачных файлов)
                            if not any(f['path'] == str(rel_path) for f in files):
                                stat = item.stat()
                                files.append({
                                    'path': str(rel_path),
                                    'name': item.name,
                                    'size': stat.st_size,
                                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                    'type': cdn_config.get_file_type(item.name),
                                    'storage_type': 'local'
                                })
            
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
            file_info = await self.get_file_info(file_path)
            if not file_info:
                return True
            
            # Проверяем срок истечения из метаданных
            expires_at_str = file_info.get('expires_at')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                return datetime.utcnow() > expires_at
            
            # Fallback на стандартную логику
            user_type = file_info.get('metadata', {}).get('user_type', 'free')
            retention_hours = cdn_config.get_retention_hours(user_type)
            
            last_modified_str = file_info.get('last_modified')
            if last_modified_str:
                last_modified = datetime.fromisoformat(last_modified_str)
                expiry_time = last_modified + timedelta(hours=retention_hours)
                return datetime.utcnow() > expiry_time
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking file expiry {file_path}: {e}")
            return False
    
    async def cleanup_expired_files(self) -> Dict[str, Any]:
        """Очистка просроченных файлов"""
        try:
            # Используем менеджер хранилищ для очистки
            result = await cdn_storage_manager.cleanup_expired_files()
            
            # Дополнительно очищаем локальный кэш
            local_deleted = 0
            local_freed_gb = 0.0
            
            try:
                for cache_file in self.cache_path.rglob("*"):
                    if cache_file.is_file():
                        # Удаляем файлы кэша старше 24 часов
                        file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
                        if file_age > timedelta(hours=24):
                            file_size = cache_file.stat().st_size
                            cache_file.unlink()
                            local_deleted += 1
                            local_freed_gb += file_size / (1024**3)
                            
            except Exception as e:
                logger.warning(f"Cache cleanup failed: {e}")
            
            result['cache_cleanup'] = {
                'deleted_files': local_deleted,
                'freed_gb': round(local_freed_gb, 2)
            }
            
            result['total_deleted_files'] += local_deleted
            result['total_freed_gb'] += local_freed_gb
            
            return result
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_storage_statistics(self) -> Dict[str, Any]:
        """Получение статистики хранилищ"""
        try:
            # Получаем статистику от менеджера хранилищ
            cloud_stats = await cdn_storage_manager.get_storage_statistics()
            
            # Добавляем статистику локального кэша
            cache_stats = await self._get_cache_statistics()
            
            return {
                'cloud_storage': cloud_stats,
                'local_cache': cache_stats,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting storage statistics: {e}")
            return {'error': str(e)}
    
    async def _get_cache_statistics(self) -> Dict[str, Any]:
        """Получение статистики локального кэша"""
        try:
            total_files = 0
            total_size = 0
            
            for cache_file in self.cache_path.rglob("*"):
                if cache_file.is_file():
                    total_files += 1
                    total_size += cache_file.stat().st_size
            
            return {
                'total_files': total_files,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'total_size_gb': round(total_size / (1024 * 1024 * 1024), 2),
                'cache_path': str(self.cache_path)
            }
            
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            return {'error': str(e)}
    
    # Вспомогательные методы
    
    def _generate_file_key(self, filename: str, user: Optional[User] = None) -> str:
        """Генерация ключа файла для хранилища"""
        # Определяем тип пользователя
        user_type = user.user_type if user else 'anonymous'
        user_id = user.id if user else 0
        
        # Создаем безопасное имя файла
        safe_filename = self._sanitize_filename(filename)
        
        # Добавляем временную метку для уникальности
        timestamp = int(datetime.utcnow().timestamp())
        
        # Формируем путь: user_type/year/month/user_id/timestamp_filename
        now = datetime.utcnow()
        year_month = now.strftime("%Y/%m")
        
        return f"{user_type}/{year_month}/{user_id}/{timestamp}_{safe_filename}"
    
    def _sanitize_filename(self, filename: str) -> str:
        """Создание безопасного имени файла"""
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
        
        return safe_filename
    
    def _get_content_type(self, filename: str) -> str:
        """Определение MIME типа файла"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(filename)
        return content_type or 'application/octet-stream'
    
    def _parse_range_header(self, range_header: str, file_size: int) -> Tuple[Optional[int], Optional[int]]:
        """Парсинг Range заголовка"""
        try:
            if not range_header.startswith('bytes='):
                return None, None
            
            range_spec = range_header[6:]
            
            if '-' not in range_spec:
                return None, None
            
            start_str, end_str = range_spec.split('-', 1)
            
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
            
            if start >= file_size or end >= file_size or start > end:
                return None, None
            
            return start, end
            
        except Exception:
            return None, None
    
    async def _is_user_file(self, file_path: str, user_id: int) -> bool:
        """Проверка, принадлежит ли файл пользователю"""
        try:
            # Проверяем по пути (файлы пользователей содержат user_id)
            if f"/{user_id}/" in file_path or file_path.startswith(f"{user_id}/"):
                return True
            
            # Проверяем метаданные файла
            file_info = await self.get_file_info(file_path)
            if file_info and file_info.get('metadata'):
                file_user_id = file_info['metadata'].get('user_id')
                if file_user_id:
                    return str(user_id) == str(file_user_id)
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking file ownership: {e}")
            return False