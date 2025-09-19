"""
VideoBot Pro - DigitalOcean Spaces Storage  
Реализация хранилища для DigitalOcean Spaces
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from botocore.exceptions import ClientError, NoCredentialsError
import aioboto3
import structlog

from .base import (
    BaseStorage, StorageConfig, StorageFileInfo,
    StorageError, StorageConnectionError, StorageUploadError,
    StorageDownloadError, StorageNotFoundError
)

logger = structlog.get_logger(__name__)

class DigitalOceanStorage(BaseStorage):
    """
    Реализация хранилища для DigitalOcean Spaces
    
    DigitalOcean Spaces - это S3-совместимое объектное хранилище
    от DigitalOcean с интегрированным CDN
    """
    
    def __init__(self, config: Union[StorageConfig, dict]):
        """
        Инициализация DigitalOcean Spaces хранилища
        
        Args:
            config: Конфигурация хранилища
        """
        super().__init__(config)
        
        # Устанавливаем DigitalOcean Spaces endpoint
        if not self.config.endpoint_url:
            self.config.endpoint_url = f"https://{self.config.region}.digitaloceanspaces.com"
        
        # CDN endpoint для публичных файлов
        if not self.config.cdn_domain and self.config.public_read:
            self.config.cdn_domain = f"{self.config.bucket_name}.{self.config.region}.cdn.digitaloceanspaces.com"
        
        self._session = None
        self._s3_client = None
    
    async def connect(self) -> bool:
        """Установить соединение с DigitalOcean Spaces"""
        try:
            # Создаем сессию aioboto3
            self._session = aioboto3.Session()
            
            # Создаем S3-совместимый клиент для DigitalOcean Spaces
            self._s3_client = self._session.client(
                's3',
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=self.config.access_key,
                aws_secret_access_key=self.config.secret_key,
                region_name=self.config.region
            )
            
            # Проверяем подключение
            async with self._s3_client as client:
                await client.head_bucket(Bucket=self.config.bucket_name)
            
            self._connected = True
            logger.info("Connected to DigitalOcean Spaces", 
                       bucket=self.config.bucket_name,
                       region=self.config.region)
            return True
            
        except NoCredentialsError:
            raise StorageConnectionError("DigitalOcean Spaces credentials not provided")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchBucket':
                raise StorageConnectionError(f"Space '{self.config.bucket_name}' not found")
            else:
                raise StorageConnectionError(f"DigitalOcean Spaces connection failed: {e}")
        except Exception as e:
            raise StorageConnectionError(f"Unexpected error connecting to DigitalOcean Spaces: {e}")
    
    async def disconnect(self):
        """Закрыть соединение с DigitalOcean Spaces"""
        if self._s3_client:
            await self._s3_client.close()
        self._connected = False
        logger.info("Disconnected from DigitalOcean Spaces")
    
    async def upload_file(
        self,
        local_path: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False
    ) -> StorageFileInfo:
        """Загрузить файл в DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        # Валидируем файл
        self.validate_file(local_path)
        
        # Определяем content-type
        if not content_type:
            content_type = self.get_content_type(local_path)
        
        try:
            extra_args = {
                'ContentType': content_type,
                'Metadata': metadata or {},
            }
            
            # Устанавливаем ACL для публичных файлов
            if public or self.config.public_read:
                extra_args['ACL'] = 'public-read'
            
            # Добавляем кеширование для CDN
            if self.config.public_read:
                extra_args['CacheControl'] = 'public, max-age=31536000'  # 1 год
            
            async with self._s3_client as client:
                await client.upload_file(
                    Filename=local_path,
                    Bucket=self.config.bucket_name,
                    Key=key,
                    ExtraArgs=extra_args
                )
            
            # Получаем информацию о загруженном файле
            file_info = await self.get_file_info(key)
            
            logger.info("File uploaded to DigitalOcean Spaces",
                       key=key,
                       size=file_info.size,
                       content_type=content_type)
            
            return file_info
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            raise StorageUploadError(f"Failed to upload to DigitalOcean Spaces ({error_code}): {e}")
        except Exception as e:
            raise StorageUploadError(f"Unexpected upload error: {e}")
    
    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False
    ) -> StorageFileInfo:
        """Загрузить байты в DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        # Проверяем размер данных
        data_size = len(data)
        max_size = self.config.max_file_size_mb * 1024 * 1024
        if data_size > max_size:
            raise StorageUploadError(f"Data too large: {data_size} bytes")
        
        # Определяем content-type
        if not content_type:
            content_type = self.get_content_type(key)
        
        try:
            extra_args = {
                'ContentType': content_type,
                'Metadata': metadata or {},
            }
            
            if public or self.config.public_read:
                extra_args['ACL'] = 'public-read'
            
            if self.config.public_read:
                extra_args['CacheControl'] = 'public, max-age=31536000'
            
            async with self._s3_client as client:
                await client.put_object(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    Body=data,
                    **extra_args
                )
            
            file_info = await self.get_file_info(key)
            
            logger.info("Data uploaded to DigitalOcean Spaces",
                       key=key,
                       size=data_size)
            
            return file_info
            
        except ClientError as e:
            raise StorageUploadError(f"Failed to upload data to DigitalOcean Spaces: {e}")
        except Exception as e:
            raise StorageUploadError(f"Unexpected upload error: {e}")
    
    async def download_file(self, key: str, local_path: str) -> bool:
        """Скачать файл из DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                await client.download_file(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    Filename=local_path
                )
            
            logger.info("File downloaded from DigitalOcean Spaces",
                       key=key,
                       local_path=local_path)
            
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchKey':
                raise StorageNotFoundError(f"File not found in DigitalOcean Spaces: {key}")
            else:
                raise StorageDownloadError(f"Failed to download from DigitalOcean Spaces: {e}")
        except Exception as e:
            raise StorageDownloadError(f"Unexpected download error: {e}")
    
    async def download_bytes(self, key: str) -> bytes:
        """Скачать файл как байты из DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                response = await client.get_object(
                    Bucket=self.config.bucket_name,
                    Key=key
                )
                
                data = await response['Body'].read()
                
            logger.info("File downloaded as bytes from DigitalOcean Spaces",
                       key=key,
                       size=len(data))
            
            return data
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchKey':
                raise StorageNotFoundError(f"File not found in DigitalOcean Spaces: {key}")
            else:
                raise StorageDownloadError(f"Failed to download from DigitalOcean Spaces: {e}")
    
    async def delete_file(self, key: str) -> bool:
        """Удалить файл из DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                await client.delete_object(
                    Bucket=self.config.bucket_name,
                    Key=key
                )
            
            logger.info("File deleted from DigitalOcean Spaces", key=key)
            return True
            
        except ClientError as e:
            logger.error("Failed to delete file from DigitalOcean Spaces",
                        key=key,
                        error=str(e))
            return False
        except Exception as e:
            logger.error("Unexpected error deleting file",
                        key=key,
                        error=str(e))
            return False
    
    async def file_exists(self, key: str) -> bool:
        """Проверить существование файла в DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                await client.head_object(
                    Bucket=self.config.bucket_name,
                    Key=key
                )
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == '404':
                return False
            else:
                raise StorageError(f"Error checking file existence: {e}")
    
    async def get_file_info(self, key: str) -> StorageFileInfo:
        """Получить информацию о файле в DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                response = await client.head_object(
                    Bucket=self.config.bucket_name,
                    Key=key
                )
            
            # Генерируем публичный URL
            public_url = None
            if self.config.public_read:
                if self.config.cdn_domain:
                    # Используем CDN URL для лучшей производительности
                    public_url = f"https://{self.config.cdn_domain}/{key}"
                else:
                    # Стандартный Spaces URL
                    public_url = f"{self.config.endpoint_url}/{self.config.bucket_name}/{key}"
            
            return StorageFileInfo(
                key=key,
                size=response['ContentLength'],
                last_modified=response['LastModified'],
                etag=response['ETag'].strip('"'),
                content_type=response.get('ContentType', 'application/octet-stream'),
                metadata=response.get('Metadata', {}),
                public_url=public_url
            )
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == '404':
                raise StorageNotFoundError(f"File not found in DigitalOcean Spaces: {key}")
            else:
                raise StorageError(f"Error getting file info: {e}")
    
    async def list_files(
        self,
        prefix: str = "",
        limit: Optional[int] = None
    ) -> List[StorageFileInfo]:
        """Получить список файлов в DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        try:
            files = []
            kwargs = {
                'Bucket': self.config.bucket_name,
                'Prefix': prefix,
            }
            
            if limit:
                kwargs['MaxKeys'] = limit
            
            async with self._s3_client as client:
                response = await client.list_objects_v2(**kwargs)
                
                if 'Contents' in response:
                    for obj in response['Contents']:
                        # Генерируем публичный URL если нужно
                        public_url = None
                        if self.config.public_read:
                            if self.config.cdn_domain:
                                public_url = f"https://{self.config.cdn_domain}/{obj['Key']}"
                            else:
                                public_url = f"{self.config.endpoint_url}/{self.config.bucket_name}/{obj['Key']}"
                        
                        files.append(StorageFileInfo(
                            key=obj['Key'],
                            size=obj['Size'],
                            last_modified=obj['LastModified'],
                            etag=obj['ETag'].strip('"'),
                            content_type='application/octet-stream',  # Не доступно в list_objects
                            public_url=public_url
                        ))
            
            return files
            
        except ClientError as e:
            raise StorageError(f"Error listing files in DigitalOcean Spaces: {e}")
    
    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "GET"
    ) -> str:
        """Генерировать предподписанный URL для DigitalOcean Spaces"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                url = await client.generate_presigned_url(
                    'get_object' if method == 'GET' else 'put_object',
                    Params={
                        'Bucket': self.config.bucket_name,
                        'Key': key
                    },
                    ExpiresIn=expires_in
                )
            
            return url
            
        except ClientError as e:
            raise StorageError(f"Error generating presigned URL: {e}")
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Получить статистику DigitalOcean Spaces хранилища"""
        if not self._connected:
            await self.connect()
        
        try:
            stats = {
                'storage_type': 'digitalocean_spaces',
                'bucket': self.config.bucket_name,
                'region': self.config.region,
                'endpoint': self.config.endpoint_url,
                'cdn_domain': self.config.cdn_domain,
                'total_objects': 0,
                'total_size': 0,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            async with self._s3_client as client:
                # Получаем общую статистику Space
                paginator = client.get_paginator('list_objects_v2')
                page_iterator = paginator.paginate(Bucket=self.config.bucket_name)
                
                async for page in page_iterator:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            stats['total_objects'] += 1
                            stats['total_size'] += obj['Size']
            
            # Конвертируем размер в читаемый формат
            stats['total_size_mb'] = stats['total_size'] / (1024 * 1024)
            stats['total_size_gb'] = stats['total_size_mb'] / 1024
            
            return stats
            
        except ClientError as e:
            raise StorageError(f"Error getting DigitalOcean Spaces stats: {e}")
    
    async def copy_file(
        self,
        source_key: str,
        dest_key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageFileInfo:
        """Копировать файл внутри DigitalOcean Spaces (оптимизированная версия)"""
        if not self._connected:
            await self.connect()
        
        try:
            copy_source = {
                'Bucket': self.config.bucket_name,
                'Key': source_key
            }
            
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata
                extra_args['MetadataDirective'] = 'REPLACE'
            
            # Сохраняем публичность файла
            if self.config.public_read:
                extra_args['ACL'] = 'public-read'
                extra_args['CacheControl'] = 'public, max-age=31536000'
            
            async with self._s3_client as client:
                await client.copy_object(
                    Bucket=self.config.bucket_name,
                    Key=dest_key,
                    CopySource=copy_source,
                    **extra_args
                )
            
            return await self.get_file_info(dest_key)
            
        except ClientError as e:
            raise StorageError(f"Error copying file in DigitalOcean Spaces: {e}")
    
    async def set_file_public(self, key: str, public: bool = True) -> bool:
        """Изменить публичность файла"""
        if not self._connected:
            await self.connect()
        
        try:
            acl = 'public-read' if public else 'private'
            
            async with self._s3_client as client:
                await client.put_object_acl(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    ACL=acl
                )
            
            logger.info("File ACL updated in DigitalOcean Spaces",
                       key=key,
                       public=public)
            
            return True
            
        except ClientError as e:
            logger.error("Failed to update file ACL",
                        key=key,
                        error=str(e))
            return False
    
    async def get_cdn_url(self, key: str) -> Optional[str]:
        """Получить CDN URL для файла"""
        if self.config.cdn_domain:
            return f"https://{self.config.cdn_domain}/{key}"
        return None
    
    async def purge_cdn_cache(self, key: str) -> bool:
        """Очистить кеш CDN для файла (требует DigitalOcean API)"""
        # Для полной реализации нужен отдельный DigitalOcean API клиент
        # Здесь возвращаем True как placeholder
        logger.info("CDN cache purge requested", key=key)
        return True