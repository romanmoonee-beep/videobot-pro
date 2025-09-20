"""
VideoBot Pro - CDN Storage Integration
Интеграция CDN с облачными хранилищами
"""

import asyncio
import structlog
from pathlib import Path
from typing import Dict, Any, Optional, Union
from datetime import datetime, timedelta

from shared.config.settings import settings
from shared.models.user import User
from worker.storage import create_storage, BaseStorage
from worker.storage.local import LocalStorage
from .config import cdn_config

logger = structlog.get_logger(__name__)

class CDNStorageManager:
    """Менеджер интеграции CDN с облачными хранилищами"""
    
    def __init__(self):
        self.initialized = False
        self.primary_storage: Optional[BaseStorage] = None
        self.backup_storage: Optional[BaseStorage] = None
        self.local_storage: LocalStorage = None
        
        # Настройки приоритетов хранилищ
        self.storage_priority = {
            'premium': ['wasabi', 'digitalocean', 'backblaze'],
            'trial': ['digitalocean', 'backblaze', 'wasabi'],
            'free': ['backblaze', 'digitalocean', 'wasabi'],
            'admin': ['wasabi', 'digitalocean', 'backblaze']
        }
    
    async def initialize(self):
        """Инициализация менеджера хранилищ"""
        if self.initialized:
            return
        
        logger.info("Initializing CDN Storage Manager...")
        
        try:
            # Инициализируем локальное хранилище
            self.local_storage = LocalStorage({
                'base_path': str(cdn_config.storage_path),
                'url_prefix': f"http://{settings.CDN_HOST}:{settings.CDN_PORT}/api/v1/files"
            })
            
            # Инициализируем облачные хранилища
            await self._initialize_cloud_storages()
            
            self.initialized = True
            logger.info("CDN Storage Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize CDN Storage Manager: {e}")
            raise
    
    async def _initialize_cloud_storages(self):
        """Инициализация облачных хранилищ"""
        storage_configs = {
            'wasabi': {
                'bucket_name': settings.WASABI_BUCKET_NAME,
                'region': settings.WASABI_REGION,
                'endpoint_url': f"https://s3.{settings.WASABI_REGION}.wasabisys.com",
                'access_key': settings.WASABI_ACCESS_KEY,
                'secret_key': settings.WASABI_SECRET_KEY,
                'max_file_size_mb': 5000,
                'public_read': True,
                'cdn_domain': settings.WASABI_CDN_DOMAIN
            },
            'digitalocean': {
                'bucket_name': settings.DO_SPACES_BUCKET,
                'region': settings.DO_SPACES_REGION,
                'endpoint_url': f"https://{settings.DO_SPACES_REGION}.digitaloceanspaces.com",
                'access_key': settings.DO_SPACES_KEY,
                'secret_key': settings.DO_SPACES_SECRET,
                'max_file_size_mb': 2000,
                'public_read': True,
                'cdn_domain': f"{settings.DO_SPACES_BUCKET}.{settings.DO_SPACES_REGION}.cdn.digitaloceanspaces.com"
            },
            'backblaze': {
                'bucket_name': settings.B2_BUCKET_NAME,
                'region': settings.B2_REGION,
                'access_key': settings.B2_KEY_ID,
                'secret_key': settings.B2_APPLICATION_KEY,
                'max_file_size_mb': 1000,
                'public_read': False
            }
        }
        
        # Пробуем подключиться к хранилищам в порядке приоритета
        for storage_type in ['wasabi', 'digitalocean', 'backblaze']:
            try:
                config = storage_configs.get(storage_type)
                if not config or not config.get('access_key'):
                    continue
                
                storage = create_storage(storage_type, config)
                await storage.connect()
                
                if not self.primary_storage:
                    self.primary_storage = storage
                    logger.info(f"Primary storage set to: {storage_type}")
                elif not self.backup_storage:
                    self.backup_storage = storage
                    logger.info(f"Backup storage set to: {storage_type}")
                
            except Exception as e:
                logger.warning(f"Failed to initialize {storage_type} storage: {e}")
        
        if not self.primary_storage:
            logger.warning("No cloud storage available, using local storage only")
    
    async def upload_file(
        self,
        local_file_path: str,
        file_key: str,
        user: Optional[User] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Загрузка файла в облачное хранилище с резервным копированием
        
        Args:
            local_file_path: Путь к локальному файлу
            file_key: Ключ файла в хранилище
            user: Пользователь (для определения приоритета хранилища)
            metadata: Дополнительные метаданные
            
        Returns:
            Результат загрузки с URL'ами
        """
        try:
            if not Path(local_file_path).exists():
                raise FileNotFoundError(f"Local file not found: {local_file_path}")
            
            # Определяем приоритетное хранилище
            storage = self._select_storage_for_user(user)
            
            if not storage:
                # Fallback на локальное хранилище
                return await self._upload_to_local(local_file_path, file_key, metadata)
            
            # Подготавливаем метаданные
            upload_metadata = {
                'upload_time': datetime.utcnow().isoformat(),
                'user_id': str(user.id) if user else 'anonymous',
                'user_type': user.user_type if user else 'free',
                'file_size': str(Path(local_file_path).stat().st_size),
                'cdn_service': 'videobot-pro'
            }
            
            if metadata:
                upload_metadata.update(metadata)
            
            # Загружаем в основное хранилище
            file_info = await storage.upload_file(
                local_path=local_file_path,
                key=file_key,
                metadata=upload_metadata,
                public=storage.config.public_read
            )
            
            # Генерируем URL'ы
            cdn_url = await self._generate_cdn_url(storage, file_key, user)
            direct_url = file_info.public_url or cdn_url
            
            # Асинхронно загружаем резервную копию
            if self.backup_storage and storage != self.backup_storage:
                asyncio.create_task(self._backup_file(local_file_path, file_key, upload_metadata))
            
            # Обновляем статистику CDN
            await cdn_config.update_stats(
                'file_uploaded',
                size_gb=file_info.size / (1024**3)
            )
            
            return {
                'success': True,
                'storage_type': storage.__class__.__name__.lower(),
                'file_key': file_key,
                'cdn_url': cdn_url,
                'direct_url': direct_url,
                'public_url': file_info.public_url,
                'file_size': file_info.size,
                'expires_at': self._calculate_expiry_time(user).isoformat() if user else None
            }
            
        except Exception as e:
            logger.error(f"File upload failed: {e}", file_path=local_file_path)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _upload_to_local(
        self,
        local_file_path: str,
        file_key: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Загрузка в локальное хранилище как fallback"""
        try:
            # Читаем файл
            with open(local_file_path, 'rb') as f:
                file_data = f.read()
            
            # Сохраняем в локальном хранилище
            file_info = await self.local_storage.upload_bytes(
                data=file_data,
                key=file_key,
                metadata=metadata
            )
            
            # Генерируем локальный URL
            local_url = f"http://{settings.CDN_HOST}:{settings.CDN_PORT}/api/v1/files/{file_key}"
            
            return {
                'success': True,
                'storage_type': 'local',
                'file_key': file_key,
                'cdn_url': local_url,
                'direct_url': local_url,
                'file_size': len(file_data),
                'local_fallback': True
            }
            
        except Exception as e:
            logger.error(f"Local upload failed: {e}")
            raise
    
    async def _backup_file(
        self,
        local_file_path: str,
        file_key: str,
        metadata: Dict[str, Any]
    ):
        """Асинхронное создание резервной копии"""
        try:
            if not self.backup_storage:
                return
            
            await self.backup_storage.upload_file(
                local_path=local_file_path,
                key=file_key,
                metadata={**metadata, 'backup_copy': 'true'},
                public=False
            )
            
            logger.info(f"Backup copy created: {file_key}")
            
        except Exception as e:
            logger.warning(f"Backup upload failed: {e}")
    
    async def download_file(
        self,
        file_key: str,
        local_path: str,
        user: Optional[User] = None
    ) -> bool:
        """
        Скачивание файла из хранилища
        
        Args:
            file_key: Ключ файла
            local_path: Путь для сохранения
            user: Пользователь
            
        Returns:
            True если файл скачан успешно
        """
        try:
            # Пробуем скачать из основного хранилища
            if self.primary_storage:
                try:
                    return await self.primary_storage.download_file(file_key, local_path)
                except Exception as e:
                    logger.warning(f"Primary storage download failed: {e}")
            
            # Пробуем резервное хранилище
            if self.backup_storage:
                try:
                    return await self.backup_storage.download_file(file_key, local_path)
                except Exception as e:
                    logger.warning(f"Backup storage download failed: {e}")
            
            # Пробуем локальное хранилище
            try:
                file_data = await self.local_storage.download_bytes(file_key)
                if file_data:
                    with open(local_path, 'wb') as f:
                        f.write(file_data)
                    return True
            except Exception as e:
                logger.warning(f"Local storage download failed: {e}")
            
            return False
            
        except Exception as e:
            logger.error(f"File download failed: {e}")
            return False
    
    async def delete_file(
        self,
        file_key: str,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Удаление файла из всех хранилищ
        
        Args:
            file_key: Ключ файла
            user: Пользователь
            
        Returns:
            Результат удаления
        """
        try:
            deletion_results = {}
            total_deleted = 0
            
            # Удаляем из всех хранилищ
            for storage_name, storage in [
                ('primary', self.primary_storage),
                ('backup', self.backup_storage),
                ('local', self.local_storage)
            ]:
                if storage:
                    try:
                        success = await storage.delete_file(file_key)
                        deletion_results[storage_name] = success
                        if success:
                            total_deleted += 1
                    except Exception as e:
                        deletion_results[storage_name] = False
                        logger.warning(f"Failed to delete from {storage_name}: {e}")
            
            return {
                'success': total_deleted > 0,
                'deleted_from': total_deleted,
                'results': deletion_results
            }
            
        except Exception as e:
            logger.error(f"File deletion failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_file_info(
        self,
        file_key: str,
        user: Optional[User] = None
    ) -> Optional[Dict[str, Any]]:
        """Получение информации о файле"""
        try:
            # Пробуем получить из основного хранилища
            if self.primary_storage:
                try:
                    file_info = await self.primary_storage.get_file_info(file_key)
                    return {
                        'key': file_info.key,
                        'size': file_info.size,
                        'last_modified': file_info.last_modified.isoformat(),
                        'content_type': file_info.content_type,
                        'metadata': file_info.metadata,
                        'public_url': file_info.public_url,
                        'storage_type': 'cloud',
                        'expires_at': self._calculate_expiry_time(user).isoformat() if user else None
                    }
                except Exception as e:
                    logger.warning(f"Primary storage info failed: {e}")
            
            # Пробуем локальное хранилище
            try:
                file_info = await self.local_storage.get_file_info(file_key)
                if file_info:
                    return {
                        **file_info,
                        'storage_type': 'local',
                        'expires_at': self._calculate_expiry_time(user).isoformat() if user else None
                    }
            except Exception as e:
                logger.warning(f"Local storage info failed: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"Get file info failed: {e}")
            return None
    
    async def cleanup_expired_files(self) -> Dict[str, Any]:
        """Очистка просроченных файлов из всех хранилищ"""
        try:
            total_deleted = 0
            total_freed_gb = 0.0
            results = {}
            
            # Очищаем каждое хранилище
            for storage_name, storage in [
                ('primary', self.primary_storage),
                ('backup', self.backup_storage),
                ('local', self.local_storage)
            ]:
                if storage:
                    try:
                        # Получаем список файлов
                        files = await storage.list_files()
                        deleted_count = 0
                        freed_space = 0.0
                        
                        for file_info in files:
                            # Проверяем срок истечения по метаданным
                            if await self._is_file_expired(file_info):
                                try:
                                    success = await storage.delete_file(file_info.key)
                                    if success:
                                        deleted_count += 1
                                        freed_space += file_info.size / (1024**3)
                                except Exception as e:
                                    logger.warning(f"Failed to delete expired file {file_info.key}: {e}")
                        
                        results[storage_name] = {
                            'deleted_files': deleted_count,
                            'freed_gb': freed_space
                        }
                        
                        total_deleted += deleted_count
                        total_freed_gb += freed_space
                        
                    except Exception as e:
                        results[storage_name] = {'error': str(e)}
            
            return {
                'success': True,
                'total_deleted_files': total_deleted,
                'total_freed_gb': round(total_freed_gb, 2),
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_storage_statistics(self) -> Dict[str, Any]:
        """Получение статистики всех хранилищ"""
        try:
            stats = {
                'timestamp': datetime.utcnow().isoformat(),
                'storages': {},
                'total_files': 0,
                'total_size_gb': 0.0
            }
            
            for storage_name, storage in [
                ('primary', self.primary_storage),
                ('backup', self.backup_storage),
                ('local', self.local_storage)
            ]:
                if storage:
                    try:
                        storage_stats = await storage.get_storage_stats()
                        stats['storages'][storage_name] = storage_stats
                        
                        # Суммируем только основное хранилище (чтобы не считать дубликаты)
                        if storage_name == 'primary':
                            stats['total_files'] += storage_stats.get('total_objects', 0)
                            stats['total_size_gb'] += storage_stats.get('total_size_gb', 0)
                            
                    except Exception as e:
                        stats['storages'][storage_name] = {'error': str(e)}
            
            return stats
            
        except Exception as e:
            logger.error(f"Get storage statistics failed: {e}")
            return {'error': str(e)}
    
    def _select_storage_for_user(self, user: Optional[User]) -> Optional[BaseStorage]:
        """Выбор хранилища в зависимости от типа пользователя"""
        if not user:
            user_type = 'free'
        else:
            user_type = user.user_type
        
        # Для админов и владельцев всегда основное хранилище
        if user_type in ['admin', 'owner']:
            return self.primary_storage
        
        # Для остальных в зависимости от приоритета и доступности
        storage_priority = self.storage_priority.get(user_type, ['primary', 'backup'])
        
        if 'primary' in storage_priority and self.primary_storage:
            return self.primary_storage
        elif 'backup' in storage_priority and self.backup_storage:
            return self.backup_storage
        
        return self.primary_storage or self.backup_storage
    
    async def _generate_cdn_url(
        self,
        storage: BaseStorage,
        file_key: str,
        user: Optional[User] = None
    ) -> str:
        """Генерация CDN URL с подписью"""
        try:
            # Вычисляем время истечения
            expiry_time = self._calculate_expiry_time(user)
            expires_in = int((expiry_time - datetime.utcnow()).total_seconds())
            
            # Генерируем подписанный URL
            return await storage.generate_presigned_url(
                file_key,
                expires_in=max(expires_in, 3600)  # Минимум 1 час
            )
            
        except Exception as e:
            logger.warning(f"Failed to generate CDN URL: {e}")
            # Fallback на публичный URL если есть
            if hasattr(storage, 'config') and storage.config.public_read:
                return f"https://{storage.config.cdn_domain}/{file_key}"
            return ""
    
    def _calculate_expiry_time(self, user: Optional[User]) -> datetime:
        """Вычисление времени истечения файла"""
        if not user:
            user_type = 'free'
        else:
            user_type = user.user_type
        
        retention_hours = cdn_config.get_retention_hours(user_type)
        return datetime.utcnow() + timedelta(hours=retention_hours)
    
    async def _is_file_expired(self, file_info) -> bool:
        """Проверка истечения срока файла"""
        try:
            # Проверяем по метаданным
            if hasattr(file_info, 'metadata') and file_info.metadata:
                upload_time_str = file_info.metadata.get('upload_time')
                user_type = file_info.metadata.get('user_type', 'free')
                
                if upload_time_str:
                    upload_time = datetime.fromisoformat(upload_time_str)
                    retention_hours = cdn_config.get_retention_hours(user_type)
                    expiry_time = upload_time + timedelta(hours=retention_hours)
                    
                    return datetime.utcnow() > expiry_time
            
            # Fallback на время последнего изменения
            if hasattr(file_info, 'last_modified'):
                retention_hours = cdn_config.get_retention_hours('free')  # Используем минимальный срок
                expiry_time = file_info.last_modified + timedelta(hours=retention_hours)
                return datetime.utcnow() > expiry_time
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking file expiry: {e}")
            return False

# Глобальный экземпляр менеджера
cdn_storage_manager = CDNStorageManager()