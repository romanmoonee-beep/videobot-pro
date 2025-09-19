"""
VideoBot Pro - Wasabi Storage
Реализация хранилища для Wasabi (S3-совместимый)
"""

import asyncio
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

class WasabiStorage(BaseStorage):
    """
    Реализация хранилища для Wasabi
    
    Wasabi - это S3-совместимое облачное хранилище
    с низкими ценами и высокой производительностью
    """
    
    def __init__(self, config: Union[StorageConfig, dict]):
        """
        Инициализация Wasabi хранилища
        
        Args:
            config: Конфигурация хранилища
        """
        super().__init__(config)
        
        # Устанавливаем Wasabi endpoint если не указан
        if not self.config.endpoint_url:
            self.config.endpoint_url = f"https://s3.{self.config.region}.wasabisys.com"
        
        self._session = None
        self._s3_client = None
    
    async def connect(self) -> bool:
        """Установить соединение с Wasabi"""
        try:
            # Создаем сессию aioboto3
            self._session = aioboto3.Session()
            
            # Создаем S3 клиент
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
            logger.info("Connected to Wasabi storage", 
                       bucket=self.config.bucket_name)
            return True
            
        except NoCredentialsError:
            raise StorageConnectionError("Wasabi credentials not provided")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchBucket':
                raise StorageConnectionError(f"Bucket '{self.config.bucket_name}' not found")
            else:
                raise StorageConnectionError(f"Wasabi connection failed: {e}")
        except Exception as e:
            raise StorageConnectionError(f"Unexpected error connecting to Wasabi: {e}")
    
    async def disconnect(self):
        """Закрыть соединение с Wasabi"""
        if self._s3_client:
            await self._s3_client.close()
        self._connected = False
        logger.info("Disconnected from Wasabi storage")
    
    async def upload_file(
        self,
        local_path: str,
        key: str,
        metadata: Optional[Dict[str, str]] = None,
        content_type: Optional[str] = None,
        public: bool = False
    ) -> StorageFileInfo:
        """Загрузить файл в Wasabi"""
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
            
            # Устанавливаем ACL если файл публичный
            if public or self.config.public_read:
                extra_args['ACL'] = 'public-read'
            
            # Добавляем шифрование если включено
            if self.config.encryption:
                extra_args['ServerSideEncryption'] = 'AES256'
            
            async with self._s3_client as client:
                await client.upload_file(
                    Filename=local_path,
                    Bucket=self.config.bucket_name,
                    Key=key,
                    ExtraArgs=extra_args
                )
            
            # Получаем информацию о загруженном файле
            file_info = await self.get_file_info(key)
            
            logger.info("File uploaded to Wasabi",
                       key=key,
                       size=file_info.size,
                       content_type=content_type)
            
            return file_info
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            raise StorageUploadError(f"Failed to upload to Wasabi ({error_code}): {e}")
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
        """Загрузить байты в Wasabi"""
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
            
            if self.config.encryption:
                extra_args['ServerSideEncryption'] = 'AES256'
            
            async with self._s3_client as client:
                await client.put_object(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    Body=data,
                    **extra_args
                )
            
            file_info = await self.get_file_info(key)
            
            logger.info("Data uploaded to Wasabi",
                       key=key,
                       size=data_size)
            
            return file_info
            
        except ClientError as e:
            raise StorageUploadError(f"Failed to upload data to Wasabi: {e}")
        except Exception as e:
            raise StorageUploadError(f"Unexpected upload error: {e}")
    
    async def download_file(self, key: str, local_path: str) -> bool:
        """Скачать файл из Wasabi"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                await client.download_file(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    Filename=local_path
                )
            
            logger.info("File downloaded from Wasabi",
                       key=key,
                       local_path=local_path)
            
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchKey':
                raise StorageNotFoundError(f"File not found in Wasabi: {key}")
            else:
                raise StorageDownloadError(f"Failed to download from Wasabi: {e}")
        except Exception as e:
            raise StorageDownloadError(f"Unexpected download error: {e}")
    
    async def download_bytes(self, key: str) -> bytes:
        """Скачать файл как байты из Wasabi"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                response = await client.get_object(
                    Bucket=self.config.bucket_name,
                    Key=key
                )
                
                data = await response['Body'].read()
                
            logger.info("File downloaded as bytes from Wasabi",
                       key=key,
                       size=len(data))
            
            return data
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'NoSuchKey':
                raise StorageNotFoundError(f"File not found in Wasabi: {key}")
            else:
                raise StorageDownloadError(f"Failed to download from Wasabi: {e}")
    
    async def delete_file(self, key: str) -> bool:
        """Удалить файл из Wasabi"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                await client.delete_object(
                    Bucket=self.config.bucket_name,
                    Key=key
                )
            
            logger.info("File deleted from Wasabi", key=key)
            return True
            
        except ClientError as e:
            logger.error("Failed to delete file from Wasabi",
                        key=key,
                        error=str(e))
            return False
        except Exception as e:
            logger.error("Unexpected error deleting file",
                        key=key,
                        error=str(e))
            return False
    
    async def file_exists(self, key: str) -> bool:
        """Проверить существование файла в Wasabi"""
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
        """Получить информацию о файле в Wasabi"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                response = await client.head_object(
                    Bucket=self.config.bucket_name,
                    Key=key
                )
            
            # Генерируем публичный URL если файл публичный
            public_url = None
            if self.config.public_read:
                if self.config.cdn_domain:
                    public_url = f"https://{self.config.cdn_domain}/{key}"
                else:
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
                raise StorageNotFoundError(f"File not found in Wasabi: {key}")
            else:
                raise StorageError(f"Error getting file info: {e}")
    
    async def list_files(
        self,
        prefix: str = "",
        limit: Optional[int] = None
    ) -> List[StorageFileInfo]:
        """Получить список файлов в Wasabi"""
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
            raise StorageError(f"Error listing files in Wasabi: {e}")
    
    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        method: str = "GET"
    ) -> str:
        """Генерировать предподписанный URL для Wasabi"""
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
        """Получить статистику Wasabi хранилища"""
        if not self._connected:
            await self.connect()
        
        try:
            stats = {
                'storage_type': 'wasabi',
                'bucket': self.config.bucket_name,
                'region': self.config.region,
                'endpoint': self.config.endpoint_url,
                'total_objects': 0,
                'total_size': 0,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            async with self._s3_client as client:
                # Получаем общую статистику bucket'а
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
            raise StorageError(f"Error getting storage stats: {e}")
    
    async def copy_file(
        self,
        source_key: str,
        dest_key: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> StorageFileInfo:
        """Копировать файл внутри Wasabi (оптимизированная версия)"""
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
            
            async with self._s3_client as client:
                await client.copy_object(
                    Bucket=self.config.bucket_name,
                    Key=dest_key,
                    CopySource=copy_source,
                    **extra_args
                )
            
            return await self.get_file_info(dest_key)
            
        except ClientError as e:
            raise StorageError(f"Error copying file in Wasabi: {e}")
    
    async def create_multipart_upload(self, key: str, content_type: str = None) -> str:
        """Создать multipart загрузку для больших файлов"""
        if not self._connected:
            await self.connect()
        
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            if self.config.encryption:
                extra_args['ServerSideEncryption'] = 'AES256'
            
            async with self._s3_client as client:
                response = await client.create_multipart_upload(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    **extra_args
                )
            
            return response['UploadId']
            
        except ClientError as e:
            raise StorageUploadError(f"Error creating multipart upload: {e}")
    
    async def upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        data: bytes
    ) -> Dict[str, Any]:
        """Загрузить часть файла"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                response = await client.upload_part(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=data
                )
            
            return {
                'ETag': response['ETag'],
                'PartNumber': part_number
            }
            
        except ClientError as e:
            raise StorageUploadError(f"Error uploading part: {e}")
    
    async def complete_multipart_upload(
        self,
        key: str,
        upload_id: str,
        parts: List[Dict[str, Any]]
    ) -> StorageFileInfo:
        """Завершить multipart загрузку"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                await client.complete_multipart_upload(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={'Parts': parts}
                )
            
            return await self.get_file_info(key)
            
        except ClientError as e:
            raise StorageUploadError(f"Error completing multipart upload: {e}")
    
    async def abort_multipart_upload(self, key: str, upload_id: str) -> bool:
        """Прервать multipart загрузку"""
        if not self._connected:
            await self.connect()
        
        try:
            async with self._s3_client as client:
                await client.abort_multipart_upload(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    UploadId=upload_id
                )
            return True
            
        except ClientError:
            return False