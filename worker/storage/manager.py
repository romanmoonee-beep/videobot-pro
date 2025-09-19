"""
VideoBot Pro - Storage Manager
Управление файловым хранилищем и CDN
"""

import os
import hashlib
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
import structlog
import aiofiles
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from shared.config.settings import settings
from worker.config import get_storage_config

logger = structlog.get_logger(__name__)

class StorageManager:
    """Менеджер для управления различными типами хранилищ"""
    
    def __init__(self):
        self.providers = {}
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Инициализация провайдеров хранилища"""
        try:
            # Wasabi S3 (основное хранилище)
            wasabi_config = get_storage_config("wasabi")
            if wasabi_config.get("aws_access_key_id"):
                self.providers["wasabi"] = WasabiStorage(wasabi_config)
                logger.info("Wasabi storage provider initialized")
            
            # Backblaze B2 (резервное хранилище)
            b2_config = get_storage_config("backblaze")
            if b2_config.get("key_id"):
                self.providers["backblaze"] = BackblazeStorage(b2_config)
                logger.info("Backblaze storage provider initialized")
            
            # DigitalOcean Spaces
            do_config = get_storage_config("digitalocean")
            if do_config.get("aws_access_key_id"):
                self.providers["digitalocean"] = DigitalOceanStorage(do_config)
                logger.info("DigitalOcean storage provider initialized")
            
            # Локальное хранилище (fallback)
            local_config = get_storage_config("local")
            self.providers["local"] = LocalStorage(local_config)
            logger.info("Local storage provider initialized")
            
        except Exception as e:
            logger.error(f"Error initializing storage providers: {e}")
    
    async def upload_file(
        self,
        file_path: str,
        task_id: int,
        user_type: str = "free",
        metadata: Optional[Dict[str, Any]] = None,
        preferred_provider: str = "wasabi"
    ) -> Dict[str, Any]:
        """
        Загрузка файла в облачное хранилище
        
        Args:
            file_path: Путь к локальному файлу
            task_id: ID задачи
            user_type: Тип пользователя
            metadata: Метаданные файла
            preferred_provider: Предпочтительный провайдер
            
        Returns:
            Результат загрузки с URL'ами
        """
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Выбираем провайдер
            provider = self._select_provider(preferred_provider, user_type)
            if not provider:
                raise ValueError("No storage provider available")
            
            # Генерируем ключ файла
            file_key = self._generate_file_key(file_path, task_id, user_type)
            
            # Подготавливаем метаданные
            upload_metadata = {
                "task_id": str(task_id),
                "user_type": user_type,
                "upload_date": datetime.utcnow().isoformat(),
                "original_filename": os.path.basename(file_path),
                "file_size": str(os.path.getsize(file_path))
            }
            
            if metadata:
                upload_metadata.update(metadata)
            
            # Загружаем файл
            upload_result = await provider.upload_file(
                local_path=file_path,
                remote_key=file_key,
                metadata=upload_metadata
            )
            
            if not upload_result.get("success"):
                # Пробуем резервный провайдер
                backup_provider = self._get_backup_provider(preferred_provider)
                if backup_provider:
                    logger.warning(f"Primary upload failed, trying backup provider")
                    upload_result = await backup_provider.upload_file(
                        local_path=file_path,
                        remote_key=file_key,
                        metadata=upload_metadata
                    )
                    upload_result["provider"] = "backup"
            
            if upload_result.get("success"):
                # Генерируем подписанные URL'ы
                cdn_url = await provider.generate_presigned_url(
                    file_key, 
                    expiration=self._get_expiration_time(user_type)
                )
                
                # Прямая ссылка для скачивания
                direct_url = upload_result.get("public_url") or cdn_url
                
                return {
                    "success": True,
                    "provider": upload_result.get("provider", preferred_provider),
                    "file_key": file_key,
                    "cdn_url": cdn_url,
                    "direct_url": direct_url,
                    "file_size": os.path.getsize(file_path),
                    "metadata": upload_metadata
                }
            else:
                raise Exception(f"Upload failed: {upload_result.get('error')}")
                
        except Exception as e:
            logger.error(f"File upload failed", error=str(e), file_path=file_path)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def delete_file(
        self,
        file_key: Optional[str] = None,
        cdn_url: Optional[str] = None,
        file_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Удаление файла из хранилища
        
        Args:
            file_key: Ключ файла в хранилище
            cdn_url: URL файла в CDN
            file_name: Имя файла
            
        Returns:
            Результат удаления
        """
        try:
            if not file_key and cdn_url:
                file_key = self._extract_key_from_url(cdn_url)
            
            if not file_key:
                raise ValueError("File key or CDN URL required")
            
            # Пробуем удалить из всех доступных провайдеров
            deletion_results = {}
            
            for provider_name, provider in self.providers.items():
                try:
                    result = await provider.delete_file(file_key)
                    deletion_results[provider_name] = result
                    
                    if result.get("success"):
                        logger.info(f"File deleted from {provider_name}", file_key=file_key)
                except Exception as e:
                    deletion_results[provider_name] = {"success": False, "error": str(e)}
            
            # Считаем успешным если удалили хотя бы из одного провайдера
            success_count = sum(1 for r in deletion_results.values() if r.get("success"))
            
            return {
                "success": success_count > 0,
                "deleted_from": success_count,
                "total_providers": len(self.providers),
                "results": deletion_results
            }
            
        except Exception as e:
            logger.error(f"File deletion failed", error=str(e), file_key=file_key)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Проверка состояния всех провайдеров хранилища
        
        Returns:
            Статус каждого провайдера
        """
        health_status = {
            "timestamp": datetime.utcnow().isoformat(),
            "providers": {},
            "overall_status": "healthy"
        }
        
        healthy_providers = 0
        
        for provider_name, provider in self.providers.items():
            try:
                provider_health = await provider.health_check()
                health_status["providers"][provider_name] = provider_health
                
                if provider_health.get("status") == "healthy":
                    healthy_providers += 1
                    
            except Exception as e:
                health_status["providers"][provider_name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        
        # Определяем общий статус
        if healthy_providers == 0:
            health_status["overall_status"] = "unhealthy"
        elif healthy_providers < len(self.providers) / 2:
            health_status["overall_status"] = "degraded"
        
        health_status["healthy_providers"] = healthy_providers
        health_status["total_providers"] = len(self.providers)
        
        return health_status
    
    async def get_usage_statistics(self) -> Dict[str, Any]:
        """
        Получение статистики использования хранилища
        
        Returns:
            Статистика по провайдерам
        """
        stats = {
            "timestamp": datetime.utcnow().isoformat(),
            "providers": {},
            "total_files": 0,
            "total_size_bytes": 0
        }
        
        for provider_name, provider in self.providers.items():
            try:
                provider_stats = await provider.get_usage_stats()
                stats["providers"][provider_name] = provider_stats
                
                # Суммируем общую статистику
                stats["total_files"] += provider_stats.get("file_count", 0)
                stats["total_size_bytes"] += provider_stats.get("total_size_bytes", 0)
                
            except Exception as e:
                stats["providers"][provider_name] = {
                    "error": str(e)
                }
        
        # Преобразуем в удобные единицы
        stats["total_size_mb"] = round(stats["total_size_bytes"] / (1024 * 1024), 2)
        stats["total_size_gb"] = round(stats["total_size_bytes"] / (1024 * 1024 * 1024), 2)
        
        return stats
    
    async def remove_duplicates(self) -> Dict[str, Any]:
        """
        Удаление дублирующихся файлов
        
        Returns:
            Результат операции
        """
        try:
            duplicates_found = 0
            duplicates_removed = 0
            space_freed = 0
            
            # Получаем список файлов от каждого провайдера
            all_files = {}
            
            for provider_name, provider in self.providers.items():
                try:
                    file_list = await provider.list_files()
                    for file_info in file_list:
                        file_hash = file_info.get("hash") or file_info.get("etag")
                        if file_hash:
                            if file_hash not in all_files:
                                all_files[file_hash] = []
                            all_files[file_hash].append({
                                "provider": provider_name,
                                "key": file_info["key"],
                                "size": file_info.get("size", 0),
                                "last_modified": file_info.get("last_modified")
                            })
                except Exception as e:
                    logger.error(f"Error listing files from {provider_name}: {e}")
            
            # Находим дубликаты
            for file_hash, files in all_files.items():
                if len(files) > 1:
                    duplicates_found += 1
                    
                    # Сортируем по дате (оставляем самый новый)
                    files.sort(key=lambda x: x.get("last_modified", ""), reverse=True)
                    
                    # Удаляем все кроме первого
                    for duplicate in files[1:]:
                        try:
                            provider = self.providers[duplicate["provider"]]
                            delete_result = await provider.delete_file(duplicate["key"])
                            
                            if delete_result.get("success"):
                                duplicates_removed += 1
                                space_freed += duplicate.get("size", 0)
                                
                        except Exception as e:
                            logger.error(f"Error removing duplicate: {e}")
            
            return {
                "success": True,
                "duplicates_found": duplicates_found,
                "duplicates_removed": duplicates_removed,
                "space_freed_bytes": space_freed,
                "space_freed_mb": round(space_freed / (1024 * 1024), 2)
            }
            
        except Exception as e:
            logger.error(f"Error removing duplicates: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def cleanup_orphaned_files(self) -> Dict[str, Any]:
        """
        Очистка файлов без записей в БД
        
        Returns:
            Результат очистки
        """
        try:
            from shared.config.database import get_async_session
            
            orphaned_files = 0
            removed_files = 0
            space_freed = 0
            
            # Получаем список всех файлов в БД
            async with get_async_session() as session:
                result = await session.execute("""
                    SELECT DISTINCT file_key FROM (
                        SELECT regexp_replace(cdn_url, '^.*/([^/]+), '\\1') as file_key
                        FROM download_tasks 
                        WHERE cdn_url IS NOT NULL
                        UNION
                        SELECT regexp_replace(archive_url, '^.*/([^/]+), '\\1') as file_key
                        FROM download_batches 
                        WHERE archive_url IS NOT NULL
                    ) as all_keys
                """)
                
                db_file_keys = {row.file_key for row in result.fetchall()}
            
            # Проверяем файлы в хранилищах
            for provider_name, provider in self.providers.items():
                try:
                    file_list = await provider.list_files()
                    
                    for file_info in file_list:
                        file_key = file_info["key"]
                        
                        # Извлекаем имя файла из ключа
                        file_name = os.path.basename(file_key)
                        
                        if file_name not in db_file_keys:
                            # Файл не найден в БД - это сирота
                            orphaned_files += 1
                            
                            try:
                                delete_result = await provider.delete_file(file_key)
                                if delete_result.get("success"):
                                    removed_files += 1
                                    space_freed += file_info.get("size", 0)
                                    
                            except Exception as e:
                                logger.error(f"Error removing orphaned file {file_key}: {e}")
                                
                except Exception as e:
                    logger.error(f"Error checking orphaned files in {provider_name}: {e}")
            
            return {
                "success": True,
                "orphaned_files_found": orphaned_files,
                "files_removed": removed_files,
                "space_freed_bytes": space_freed,
                "space_freed_mb": round(space_freed / (1024 * 1024), 2)
            }
            
        except Exception as e:
            logger.error(f"Error cleaning orphaned files: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def compress_old_archives(self) -> Dict[str, Any]:
        """
        Сжатие старых архивов для экономии места
        
        Returns:
            Результат сжатия
        """
        try:
            # Это заглушка - в реальной системе здесь будет логика
            # перекомпрессии старых файлов с более агрессивными настройками
            return {
                "success": True,
                "files_compressed": 0,
                "space_saved_bytes": 0,
                "space_saved_mb": 0.0
            }
            
        except Exception as e:
            logger.error(f"Error compressing old archives: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _select_provider(self, preferred: str, user_type: str):
        """Выбор провайдера хранилища"""
        # Для Premium пользователей предпочтительно Wasabi
        if user_type in ["premium", "trial"] and "wasabi" in self.providers:
            return self.providers["wasabi"]
        
        # Проверяем предпочтительный провайдер
        if preferred in self.providers:
            return self.providers[preferred]
        
        # Fallback на первый доступный
        return next(iter(self.providers.values())) if self.providers else None
    
    def _get_backup_provider(self, primary: str):
        """Получение резервного провайдера"""
        backup_order = {
            "wasabi": "backblaze",
            "backblaze": "digitalocean", 
            "digitalocean": "local",
            "local": None
        }
        
        backup_name = backup_order.get(primary)
        return self.providers.get(backup_name) if backup_name else None
    
    def _generate_file_key(self, file_path: str, task_id: int, user_type: str) -> str:
        """Генерация уникального ключа файла"""
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_name)[1]
        
        # Создаем хеш на основе содержимого файла
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()[:12]
        
        # Формируем путь: user_type/year/month/hash_taskid.ext
        now = datetime.utcnow()
        year_month = now.strftime("%Y/%m")
        
        return f"{user_type}/{year_month}/{file_hash}_{task_id}{file_ext}"
    
    def _get_expiration_time(self, user_type: str) -> int:
        """Получение времени истечения ссылки в секундах"""
        expiration_hours = {
            "premium": 7 * 24,  # 7 дней
            "trial": 3 * 24,    # 3 дня  
            "free": 24          # 1 день
        }
        
        return expiration_hours.get(user_type, 24) * 3600
    
    def _extract_key_from_url(self, url: str) -> Optional[str]:
        """Извлечение ключа файла из URL"""
        try:
            # Простое извлечение пути из URL
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.path.lstrip('/')
        except Exception:
            return None

# Базовый класс для провайдеров хранилища
class BaseStorageProvider:
    """Базовый класс для провайдеров хранилища"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logger.bind(provider=self.__class__.__name__)
    
    async def upload_file(self, local_path: str, remote_key: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
    
    async def delete_file(self, file_key: str) -> Dict[str, Any]:
        raise NotImplementedError
    
    async def generate_presigned_url(self, file_key: str, expiration: int) -> str:
        raise NotImplementedError
    
    async def health_check(self) -> Dict[str, Any]:
        raise NotImplementedError
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        raise NotImplementedError
    
    async def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        raise NotImplementedError

class WasabiStorage(BaseStorageProvider):
    """Провайдер для Wasabi S3"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=config.get('endpoint_url'),
                aws_access_key_id=config.get('aws_access_key_id'),
                aws_secret_access_key=config.get('aws_secret_access_key'),
                region_name=config.get('region_name', 'us-east-1')
            )
            self.bucket_name = config.get('bucket_name')
        except Exception as e:
            self.logger.error(f"Failed to initialize Wasabi client: {e}")
            self.s3_client = None
    
    async def upload_file(self, local_path: str, remote_key: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if not self.s3_client:
                return {"success": False, "error": "S3 client not initialized"}
            
            # Загружаем файл
            self.s3_client.upload_file(
                local_path,
                self.bucket_name,
                remote_key,
                ExtraArgs={
                    'Metadata': metadata,
                    'ServerSideEncryption': 'AES256'
                }
            )
            
            return {
                "success": True,
                "provider": "wasabi",
                "bucket": self.bucket_name,
                "key": remote_key
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            self.logger.error(f"Wasabi upload failed: {error_code}")
            return {"success": False, "error": f"AWS Error: {error_code}"}
        except Exception as e:
            self.logger.error(f"Wasabi upload failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def delete_file(self, file_key: str) -> Dict[str, Any]:
        try:
            if not self.s3_client:
                return {"success": False, "error": "S3 client not initialized"}
            
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=file_key
            )
            
            return {"success": True}
            
        except ClientError as e:
            return {"success": False, "error": e.response['Error']['Code']}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def generate_presigned_url(self, file_key: str, expiration: int) -> str:
        try:
            if not self.s3_client:
                return ""
            
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': file_key},
                ExpiresIn=expiration
            )
            
            return url
            
        except Exception as e:
            self.logger.error(f"Error generating presigned URL: {e}")
            return ""
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            if not self.s3_client:
                return {"status": "unhealthy", "error": "Client not initialized"}
            
            # Проверяем доступность bucket'а
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            
            return {
                "status": "healthy",
                "provider": "wasabi",
                "bucket": self.bucket_name
            }
            
        except ClientError as e:
            return {
                "status": "unhealthy",
                "error": e.response['Error']['Code']
            }
        except Exception as e:
            return {
                "status": "unhealthy", 
                "error": str(e)
            }
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        try:
            if not self.s3_client:
                return {"error": "Client not initialized"}
            
            # Получаем список объектов для подсчета
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            
            file_count = response.get('KeyCount', 0)
            total_size = sum(obj.get('Size', 0) for obj in response.get('Contents', []))
            
            return {
                "file_count": file_count,
                "total_size_bytes": total_size,
                "provider": "wasabi"
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        try:
            if not self.s3_client:
                return []
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            files = []
            for obj in response.get('Contents', []):
                files.append({
                    "key": obj['Key'],
                    "size": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat(),
                    "etag": obj['ETag'].strip('"')
                })
            
            return files
            
        except Exception as e:
            self.logger.error(f"Error listing files: {e}")
            return []

class LocalStorage(BaseStorageProvider):
    """Локальный провайдер хранилища"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_path = Path(config.get('base_path', './storage'))
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.url_prefix = config.get('url_prefix', 'http://localhost:8000/files')
    
    async def upload_file(self, local_path: str, remote_key: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        try:
            target_path = self.base_path / remote_key
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Копируем файл
            shutil.copy2(local_path, target_path)
            
            # Создаем файл метаданных
            metadata_path = target_path.with_suffix(target_path.suffix + '.meta')
            async with aiofiles.open(metadata_path, 'w') as f:
                import json
                await f.write(json.dumps(metadata))
            
            return {
                "success": True,
                "provider": "local",
                "path": str(target_path),
                "public_url": f"{self.url_prefix}/{remote_key}"
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def delete_file(self, file_key: str) -> Dict[str, Any]:
        try:
            file_path = self.base_path / file_key
            metadata_path = file_path.with_suffix(file_path.suffix + '.meta')
            
            # Удаляем файл
            if file_path.exists():
                file_path.unlink()
            
            # Удаляем метаданные
            if metadata_path.exists():
                metadata_path.unlink()
            
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def generate_presigned_url(self, file_key: str, expiration: int) -> str:
        # Для локального хранилища возвращаем обычный URL
        return f"{self.url_prefix}/{file_key}"
    
    async def health_check(self) -> Dict[str, Any]:
        try:
            # Проверяем доступность директории
            if not self.base_path.exists():
                return {"status": "unhealthy", "error": "Storage directory not found"}
            
            # Проверяем права записи
            test_file = self.base_path / '.health_check'
            test_file.write_text('test')
            test_file.unlink()
            
            return {
                "status": "healthy",
                "provider": "local",
                "path": str(self.base_path)
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        try:
            file_count = 0
            total_size = 0
            
            for file_path in self.base_path.rglob('*'):
                if file_path.is_file() and not file_path.name.endswith('.meta'):
                    file_count += 1
                    total_size += file_path.stat().st_size
            
            return {
                "file_count": file_count,
                "total_size_bytes": total_size,
                "provider": "local"
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        try:
            files = []
            search_path = self.base_path / prefix if prefix else self.base_path
            
            for file_path in search_path.rglob('*'):
                if file_path.is_file() and not file_path.name.endswith('.meta'):
                    stat_info = file_path.stat()
                    
                    # Вычисляем относительный путь
                    relative_path = file_path.relative_to(self.base_path)
                    
                    files.append({
                        "key": str(relative_path),
                        "size": stat_info.st_size,
                        "last_modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                        "hash": self._calculate_file_hash(file_path)
                    })
            
            return files
            
        except Exception as e:
            self.logger.error(f"Error listing local files: {e}")
            return []
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Вычисление хеша файла"""
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return ""

# Заглушки для других провайдеров
class BackblazeStorage(BaseStorageProvider):
    """Провайдер для Backblaze B2 (заглушка)"""
    
    async def upload_file(self, local_path: str, remote_key: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "Backblaze provider not implemented yet"}
    
    async def delete_file(self, file_key: str) -> Dict[str, Any]:
        return {"success": False, "error": "Backblaze provider not implemented yet"}
    
    async def generate_presigned_url(self, file_key: str, expiration: int) -> str:
        return ""
    
    async def health_check(self) -> Dict[str, Any]:
        return {"status": "not_implemented", "provider": "backblaze"}
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        return {"error": "Not implemented"}
    
    async def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        return []

class DigitalOceanStorage(BaseStorageProvider):
    """Провайдер для DigitalOcean Spaces (заглушка)"""
    
    async def upload_file(self, local_path: str, remote_key: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {"success": False, "error": "DigitalOcean provider not implemented yet"}
    
    async def delete_file(self, file_key: str) -> Dict[str, Any]:
        return {"success": False, "error": "DigitalOcean provider not implemented yet"}
    
    async def generate_presigned_url(self, file_key: str, expiration: int) -> str:
        return ""
    
    async def health_check(self) -> Dict[str, Any]:
        return {"status": "not_implemented", "provider": "digitalocean"}
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        return {"error": "Not implemented"}
    
    async def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        return []