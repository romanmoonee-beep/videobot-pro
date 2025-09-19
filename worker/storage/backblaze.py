"""
VideoBot Pro - Backblaze B2 Storage
Реализация хранилища для Backblaze B2
"""

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
import aiohttp
import structlog

from .base import (
    BaseStorage, StorageConfig, StorageFileInfo,
    StorageError, StorageConnectionError, StorageUploadError,
    StorageDownloadError, StorageNotFoundError
)

logger = structlog.get_logger(__name__)

class BackblazeStorage(BaseStorage):
    """
    Реализация хранилища для Backblaze B2
    
    Backblaze B2 - это облачное хранилище с простым API
    и низкими ценами на хранение данных
    """
    
    def __init__(self, config: Union[StorageConfig, dict]):
        """
        Инициализация Backblaze хранилища
        
        Args:
            config: Конфигурация хранилища
        """
        super().__init__(config)
        
        # Backblaze API endpoints
        self.api_url = "https://api.backblazeb2.com"
        self.account_id = self.config.access_key  # В B2 это называется applicationKeyId
        self.application_key = self.config.secret_key  # applicationKey
        
        # API токены и URL'ы
        self._auth_token = None
        self._api_url = None
        self._download_url = None
        self._bucket_id = None
        
        self._session = None
        self._upload_auth_token = None
        self._upload_url = None
    
    async def connect(self) -> bool:
        """Установить соединение с Backblaze B2"""
        try:
            # Создаем HTTP сессию
            self._session = aiohttp.ClientSession()
            
            # Авторизуемся в B2
            await self._authorize_account()
            
            # Получаем информацию о bucket'е
            await self._get_bucket_info()
            
            # Получаем URL для загрузки
            await self._get_upload_url()
            
            self._connected = True
            logger.info("Connected to Backblaze B2",
                       bucket=self.config.bucket_name,
                       bucket_id=self._bucket_id)
            return True
            
        except Exception as e:
            if self._session:
                await self._session.close()
            raise StorageConnectionError(f"Failed to connect to Backblaze B2: {e}")
    
    async def disconnect(self):
        """Закрыть соединение с Backblaze B2"""
        if self._session:
            await self._session.close()
            self._session = None
        
        self._connected = False
        self._auth_token = None
        self._api_url = None
        self._download_url = None
        self._bucket_id = None
        
        logger.info("Disconnected from Backblaze B2")
    
    async def _authorize_account(self):
        """Авторизоваться в Backblaze B2"""
        auth_url = f"{self.api_url}/b2api/v2/b2_authorize_account"
        
        # Создаем basic auth header
        import base64
        credentials = base64.b64encode(
            f"{self.account_id}:{self.application_key}".encode()
        ).decode()
        
        headers = {
            "Authorization": f"Basic {credentials}"
        }
        
        async with self._session.post(auth_url, headers=headers) as response:
            if response.status != 200:
                raise StorageConnectionError(
                    f"B2 authorization failed: {response.status}"
                )
            
            data = await response.json()
            
            self._auth_token = data["authorizationToken"]
            self._api_url = data["apiUrl"]
            self._download_url = data["downloadUrl"]
    
    async def _get_bucket_info(self):
        """Получить информацию о bucket'е"""
        url = f"{self._api_url}/b2api/v2/b2_list_buckets"
        
        headers = {
            "Authorization": self._auth_token
        }
        
        data = {
            "accountId": self.account_id
        }
        
        async with self._session.post(url, headers=headers, json=data) as response:
            if response.status != 200:
                raise StorageConnectionError(
                    f"Failed to get bucket info: {response.status}"
                )
            
            result = await response.json()
            
            # Ищем нужный bucket
            for bucket in result["buckets"]:
                if bucket["bucketName"] == self.config.bucket_name:
                    self._bucket_id = bucket["bucketId"]
                    return
            
            raise StorageConnectionError(
                f"Bucket '{self.config.bucket_name}' not found"
            )
    
    async def _get_upload_url(self):
        """Получить URL для загрузки файлов"""
        url = f"{self._api_url}/b2api/v2/b2_get_upload_url"
        
        headers = {
            "Authorization": self._auth_token
        }
        
        data = {
            "bucketId": self._bucket_id
        }
        
        async with self._session.post(url, headers=headers, json=data) as response:
            if response.status != 200:
                raise StorageConnectionError(
                    f"Failed to get upload URL: {response.status}"
                )
            
            result = await response.json()
            
            self._upload_url = result["uploadUrl"]
            self._upload_auth_token = result["authorizationToken"]
    
    async def upload_file(
        self,
        local_path: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False
    ) -> StorageFileInfo:
        """Загрузить файл в Backblaze B2"""
        if not self._connected:
            await self.connect()
        
        # Валидируем файл
        self.validate_file(local_path)
        
        # Определяем content-type
        if not content_type:
            content_type = self.get_content_type(local_path)
        
        # Читаем файл
        with open(local_path, 'rb') as f:
            data = f.read()
        
        return await self.upload_bytes(
            data=data,
            key=key,
            metadata=metadata,
            content_type=content_type,
            public=public
        )
    
    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False
    ) -> StorageFileInfo:
        """Загрузить байты в Backblaze B2"""
        if not self._connected:
            await self.connect()
        
        # Проверяем размер
        data_size = len(data)
        max_size = self.config.max_file_size_mb * 1024 * 1024
        if data_size > max_size:
            raise StorageUploadError(f"Data too large: {data_size} bytes")
        
        if not content_type:
            content_type = self.get_content_type(key)
        
        # Вычисляем SHA1 хеш
        sha1_hash = hashlib.sha1(data).hexdigest()
        
        try:
            headers = {
                "Authorization": self._upload_auth_token,
                "X-Bz-File-Name": key,
                "Content-Type": content_type,
                "Content-Length": str(data_size),
                "X-Bz-Content-Sha1": sha1_hash
            }
            
            # Добавляем метаданные
            if metadata:
                for k, v in metadata.items():
                    headers[f"X-Bz-Info-{k}"] = v
            
            async with self._session.post(
                self._upload_url,
                headers=headers,
                data=data
            ) as response:
                
                if response.status != 200:
                    # Если upload URL устарел, получаем новый
                    if response.status == 401:
                        await self._get_upload_url()
                        return await self.upload_bytes(
                            data, key, metadata, content_type, public
                        )
                    
                    raise StorageUploadError(
                        f"Upload failed: {response.status}"
                    )
                
                result = await response.json()
                
                # Создаем информацию о файле
                file_info = StorageFileInfo(
                    key=key,
                    size=data_size,
                    last_modified=datetime.utcnow(),
                    etag=result["contentSha1"],
                    content_type=content_type,
                    metadata=metadata or {}
                )
                
                # Добавляем публичный URL если bucket публичный
                if public:
                    file_info.public_url = f"{self._download_url}/file/{self.config.bucket_name}/{key}"
                
                logger.info("Data uploaded to Backblaze B2",
                           key=key,
                           size=data_size,
                           file_id=result.get("fileId"))
                
                return file_info
                
        except Exception as e:
            raise StorageUploadError(f"Upload to Backblaze B2 failed: {e}")
    
    async def download_file(self, key: str, local_path: str) -> bool:
        """Скачать файл из Backblaze B2"""
        data = await self.download_bytes(key)
        
        with open(local_path, 'wb') as f:
            f.write(data)
        
        logger.info("File downloaded from Backblaze B2",
                   key=key,
                   local_path=local_path)
        
        return True
    
    async def download_bytes(self, key: str) -> bytes:
        """Скачать файл как байты из Backblaze B2"""
        if not self._connected:
            await self.connect()
        
        download_url = f"{self._download_url}/file/{self.config.bucket_name}/{key}"
        
        try:
            async with self._session.get(download_url) as response:
                if response.status == 404:
                    raise StorageNotFoundError(f"File not found: {key}")
                elif response.status != 200:
                    raise StorageDownloadError(
                        f"Download failed: {response.status}"
                    )
                
                data = await response.read()
                
                logger.info("File downloaded as bytes from Backblaze B2",
                           key=key,
                           size=len(data))
                
                return data
                
        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageDownloadError(f"Download from Backblaze B2 failed: {e}")
    
    async def delete_file(self, key: str) -> bool:
        """Удалить файл из Backblaze B2"""
        if not self._connected:
            await self.connect()
        
        try:
            # Сначала нужно найти fileId
            file_info = await self._get_file_info_by_name(key)
            if not file_info:
                return False
            
            url = f"{self._api_url}/b2api/v2/b2_delete_file_version"
            
            headers = {
                "Authorization": self._auth_token
            }
            
            data = {
                "fileId": file_info["fileId"],
                "fileName": key
            }
            
            async with self._session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    logger.info("File deleted from Backblaze B2", key=key)
                    return True
                else:
                    logger.error("Failed to delete file from Backblaze B2",
                               key=key,
                               status=response.status)
                    return False
                    
        except Exception as e:
            logger.error("Error deleting file from Backblaze B2",
                        key=key,
                        error=str(e))
            return False
    
    async def file_exists(self, key: str) -> bool:
        """Проверить существование файла в Backblaze B2"""
        try:
            file_info = await self._get_file_info_by_name(key)
            return file_info is not None
        except:
            return False
    
    async def get_file_info(self, key: str) -> StorageFileInfo:
        """Получить информацию о файле в Backblaze B2"""
        file_info = await self._get_file_info_by_name(key)
        
        if not file_info:
            raise StorageNotFoundError(f"File not found: {key}")
        
        # Извлекаем метаданные
        metadata = {}
        for k, v in file_info.get("fileInfo", {}).items():
            if k.startswith("src_"):
                metadata[k[4:]] = v
        
        return StorageFileInfo(
            key=key,
            size=file_info["size"],
            last_modified=datetime.fromtimestamp(
                file_info["uploadTimestamp"] / 1000
            ),
            etag=file_info["contentSha1"],
            content_type=file_info["contentType"],
            metadata=metadata,
            public_url=f"{self._download_url}/file/{self.config.bucket_name}/{key}"
        )
    
    async def _get_file_info_by_name(self, key: str) -> Optional[Dict[str, Any]]:
        """Получить информацию о файле по имени"""
        if not self._connected:
            await self.connect()
        
        url = f"{self._api_url}/b2api/v2/b2_list_file_names"
        
        headers = {
            "Authorization": self._auth_token
        }
        
        data = {
            "bucketId": self._bucket_id,
            "startFileName": key,
            "maxFileCount": 1
        }
        
        try:
            async with self._session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    return None
                
                result = await response.json()
                
                files = result.get("files", [])
                if files and files[0]["fileName"] == key:
                    return files[0]
                
                return None
                
        except Exception:
            return None
    
    async def list_files(
        self,
        prefix: str = "",
        limit: Optional[int] = None
    ) -> List[StorageFileInfo]:
        """Получить список файлов в Backblaze B2"""
        if not self._connected:
            await self.connect()
        
        url = f"{self._api_url}/b2api/v2/b2_list_file_names"
        
        headers = {
            "Authorization": self._auth_token
        }
        
        data = {
            "bucketId": self._bucket_id,
            "startFileName": prefix,
            "maxFileCount": limit or 10000
        }
        
        try:
            files = []
            
            async with self._session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    raise StorageError(f"Failed to list files: {response.status}")
                
                result = await response.json()
                
                for file_data in result.get("files", []):
                    # Фильтруем по префиксу
                    if not file_data["fileName"].startswith(prefix):
                        continue
                    
                    # Извлекаем метаданные
                    metadata = {}
                    for k, v in file_data.get("fileInfo", {}).items():
                        if k.startswith("src_"):
                            metadata[k[4:]] = v
                    
                    files.append(StorageFileInfo(
                        key=file_data["fileName"],
                        size=file_data["size"],
                        last_modified=datetime.fromtimestamp(
                            file_data["uploadTimestamp"] / 1000
                        ),
                        etag=file_data["contentSha1"],
                        content_type=file_data["contentType"],
                        metadata=metadata,
                        public_url=f"{self._download_url}/file/{self.config.bucket_name}/{file_data['fileName']}"
                    ))
            
            return files
            
        except Exception as e:
            raise StorageError(f"Error listing files in Backblaze B2: {e}")
    
    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "GET"
    ) -> str:
        """
        Генерировать временную ссылку для скачивания
        В Backblaze B2 используем authorization token
        """
        if not self._connected:
            await self.connect()
        
        # В B2 нет предподписанных URL, используем стандартный download URL
        # с токеном авторизации (только для GET)
        if method == "GET":
            return f"{self._download_url}/file/{self.config.bucket_name}/{key}"
        else:
            raise StorageError("Backblaze B2 only supports GET presigned URLs")
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Получить статистику Backblaze B2 хранилища"""
        if not self._connected:
            await self.connect()
        
        try:
            files = await self.list_files()
            
            total_size = sum(f.size for f in files)
            
            stats = {
                'storage_type': 'backblaze_b2',
                'bucket': self.config.bucket_name,
                'bucket_id': self._bucket_id,
                'total_objects': len(files),
                'total_size': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'total_size_gb': total_size / (1024 * 1024 * 1024),
                'last_updated': datetime.utcnow().isoformat()
            }
            
            return stats
            
        except Exception as e:
            raise StorageError(f"Error getting Backblaze B2 stats: {e}")