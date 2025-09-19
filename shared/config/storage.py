"""
VideoBot Pro - Storage Configuration
Конфигурация файлового хранилища (Wasabi S3, Backblaze B2, CloudFlare CDN)
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import aiohttp
import boto3
import structlog
from botocore.exceptions import ClientError

from .settings import settings

logger = structlog.get_logger(__name__)

class StorageProvider:
    """Провайдеры хранилища"""
    WASABI = "wasabi"
    BACKBLAZE = "backblaze"
    LOCAL = "local"

class StorageConfig:
    """Конфигурация файлового хранилища"""
    
    def __init__(self):
        self.wasabi_client: Optional[boto3.client] = None
        self.b2_client: Optional[boto3.client] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
    
    async def initialize(self):
        """Инициализация хранилищ"""
        if self._initialized:
            return
            
        logger.info("Initializing storage services...")
        
        # Инициализация Wasabi S3
        if settings.WASABI_ACCESS_KEY and settings.WASABI_SECRET_KEY:
            try:
                self.wasabi_client = boto3.client(
                    's3',
                    endpoint_url=settings.WASABI_ENDPOINT,
                    aws_access_key_id=settings.WASABI_ACCESS_KEY,
                    aws_secret_access_key=settings.WASABI_SECRET_KEY,
                    region_name=settings.WASABI_REGION
                )
                
                # Проверяем подключение
                await self._test_wasabi_connection()
                logger.info("Wasabi S3 initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Wasabi: {e}")
                self.wasabi_client = None
        
        # Инициализация Backblaze B2
        if settings.B2_KEY_ID and settings.B2_APPLICATION_KEY:
            try:
                self.b2_client = boto3.client(
                    's3',
                    endpoint_url='https://s3.us-west-000.backblazeb2.com',
                    aws_access_key_id=settings.B2_KEY_ID,
                    aws_secret_access_key=settings.B2_APPLICATION_KEY
                )
                
                await self._test_b2_connection()
                logger.info("Backblaze B2 initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Backblaze B2: {e}")
                self.b2_client = None
        
        # HTTP сессия для CDN и API
        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300),  # 5 минут
            headers={'User-Agent': settings.USER_AGENT}
        )
        
        self._initialized = True
        logger.info("Storage services initialized")
    
    async def close(self):
        """Закрытие соединений"""
        if self.http_session:
            await self.http_session.close()
            self.http_session = None
        
        self.wasabi_client = None
        self.b2_client = None
        self._initialized = False
        logger.info("Storage services closed")
    
    async def _test_wasabi_connection(self):
        """Тестирование подключения к Wasabi"""
        try:
            # Проверяем доступ к bucket
            self.wasabi_client.head_bucket(Bucket=settings.WASABI_BUCKET_NAME)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket не существует, попробуем создать
                try:
                    self.wasabi_client.create_bucket(
                        Bucket=settings.WASABI_BUCKET_NAME,
                        CreateBucketConfiguration={'LocationConstraint': settings.WASABI_REGION}
                    )
                    logger.info(f"Created Wasabi bucket: {settings.WASABI_BUCKET_NAME}")
                except Exception as create_e:
                    logger.error(f"Failed to create Wasabi bucket: {create_e}")
                    raise
            else:
                raise
    
    async def _test_b2_connection(self):
        """Тестирование подключения к Backblaze B2"""
        try:
            self.b2_client.head_bucket(Bucket=settings.B2_BUCKET_NAME)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.warning(f"Backblaze B2 bucket {settings.B2_BUCKET_NAME} not found")
            else:
                raise
    
    async def upload_file(self, file_path: str, file_data: bytes, 
                         provider: str = StorageProvider.WASABI,
                         content_type: str = 'application/octet-stream',
                         metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Загрузка файла в хранилище
        
        Args:
            file_path: Путь к файлу в хранилище
            file_data: Данные файла
            provider: Провайдер хранилища
            content_type: MIME тип файла
            metadata: Дополнительные метаданные
            
        Returns:
            Информация о загруженном файле
        """
        if not self._initialized:
            await self.initialize()
        
        metadata = metadata or {}
        
        try:
            if provider == StorageProvider.WASABI and self.wasabi_client:
                return await self._upload_to_wasabi(file_path, file_data, content_type, metadata)
            elif provider == StorageProvider.BACKBLAZE and self.b2_client:
                return await self._upload_to_b2(file_path, file_data, content_type, metadata)
            else:
                raise ValueError(f"Provider {provider} not available or not configured")
        
        except Exception as e:
            logger.error(f"Failed to upload file to {provider}: {e}")
            raise
    
    async def _upload_to_wasabi(self, file_path: str, file_data: bytes,
                              content_type: str, metadata: Dict[str, str]) -> Dict[str, Any]:
        """Загрузка в Wasabi S3"""
        try:
            # Добавляем метаданные
            metadata.update({
                'uploaded-at': datetime.utcnow().isoformat(),
                'service': 'videobot-pro'
            })
            
            # Загружаем файл
            response = self.wasabi_client.put_object(
                Bucket=settings.WASABI_BUCKET_NAME,
                Key=file_path,
                Body=file_data,
                ContentType=content_type,
                Metadata=metadata,
                ServerSideEncryption='AES256'
            )
            
            # Генерируем URL
            file_url = f"{settings.WASABI_ENDPOINT}/{settings.WASABI_BUCKET_NAME}/{file_path}"
            cdn_url = f"https://{settings.CLOUDFLARE_CDN_DOMAIN}/{file_path}"
            
            return {
                'provider': StorageProvider.WASABI,
                'file_path': file_path,
                'file_url': file_url,
                'cdn_url': cdn_url,
                'etag': response.get('ETag', '').strip('"'),
                'size_bytes': len(file_data),
                'content_type': content_type,
                'metadata': metadata,
                'uploaded_at': datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Wasabi upload error: {e}")
            raise
    
    async def _upload_to_b2(self, file_path: str, file_data: bytes,
                          content_type: str, metadata: Dict[str, str]) -> Dict[str, Any]:
        """Загрузка в Backblaze B2"""
        try:
            response = self.b2_client.put_object(
                Bucket=settings.B2_BUCKET_NAME,
                Key=file_path,
                Body=file_data,
                ContentType=content_type,
                Metadata=metadata
            )
            
            file_url = f"https://f000.backblazeb2.com/file/{settings.B2_BUCKET_NAME}/{file_path}"
            
            return {
                'provider': StorageProvider.BACKBLAZE,
                'file_path': file_path,
                'file_url': file_url,
                'etag': response.get('ETag', '').strip('"'),
                'size_bytes': len(file_data),
                'content_type': content_type,
                'metadata': metadata,
                'uploaded_at': datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Backblaze B2 upload error: {e}")
            raise
    
    async def delete_file(self, file_path: str, provider: str = StorageProvider.WASABI) -> bool:
        """
        Удаление файла из хранилища
        
        Args:
            file_path: Путь к файлу
            provider: Провайдер хранилища
            
        Returns:
            True если файл удален успешно
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            if provider == StorageProvider.WASABI and self.wasabi_client:
                self.wasabi_client.delete_object(
                    Bucket=settings.WASABI_BUCKET_NAME,
                    Key=file_path
                )
            elif provider == StorageProvider.BACKBLAZE and self.b2_client:
                self.b2_client.delete_object(
                    Bucket=settings.B2_BUCKET_NAME,
                    Key=file_path
                )
            else:
                raise ValueError(f"Provider {provider} not available")
            
            logger.info(f"File deleted: {file_path} from {provider}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete file {file_path} from {provider}: {e}")
            return False
    
    async def generate_presigned_url(self, file_path: str, expires_in: int = 3600,
                                   provider: str = StorageProvider.WASABI) -> str:
        """
        Генерация presigned URL для скачивания
        
        Args:
            file_path: Путь к файлу
            expires_in: Время действия ссылки в секундах
            provider: Провайдер хранилища
            
        Returns:
            Presigned URL
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            if provider == StorageProvider.WASABI and self.wasabi_client:
                return self.wasabi_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': settings.WASABI_BUCKET_NAME,
                        'Key': file_path
                    },
                    ExpiresIn=expires_in
                )
            elif provider == StorageProvider.BACKBLAZE and self.b2_client:
                return self.b2_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': settings.B2_BUCKET_NAME,
                        'Key': file_path
                    },
                    ExpiresIn=expires_in
                )
            else:
                raise ValueError(f"Provider {provider} not available")
        
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    async def file_exists(self, file_path: str, provider: str = StorageProvider.WASABI) -> bool:
        """
        Проверка существования файла
        
        Args:
            file_path: Путь к файлу
            provider: Провайдер хранилища
            
        Returns:
            True если файл существует
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            if provider == StorageProvider.WASABI and self.wasabi_client:
                self.wasabi_client.head_object(
                    Bucket=settings.WASABI_BUCKET_NAME,
                    Key=file_path
                )
            elif provider == StorageProvider.BACKBLAZE and self.b2_client:
                self.b2_client.head_object(
                    Bucket=settings.B2_BUCKET_NAME,
                    Key=file_path
                )
            else:
                return False
            
            return True
        
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
        except Exception as e:
            logger.error(f"Error checking file existence: {e}")
            return False
    
    async def get_file_info(self, file_path: str, provider: str = StorageProvider.WASABI) -> Optional[Dict[str, Any]]:
        """
        Получение информации о файле
        
        Args:
            file_path: Путь к файлу
            provider: Провайдер хранилища
            
        Returns:
            Информация о файле или None
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            if provider == StorageProvider.WASABI and self.wasabi_client:
                response = self.wasabi_client.head_object(
                    Bucket=settings.WASABI_BUCKET_NAME,
                    Key=file_path
                )
            elif provider == StorageProvider.BACKBLAZE and self.b2_client:
                response = self.b2_client.head_object(
                    Bucket=settings.B2_BUCKET_NAME,
                    Key=file_path
                )
            else:
                return None
            
            return {
                'file_path': file_path,
                'size_bytes': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', ''),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag', '').strip('"'),
                'metadata': response.get('Metadata', {}),
                'provider': provider
            }
        
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return None
            raise
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return None
    
    async def list_files(self, prefix: str = "", max_keys: int = 1000,
                        provider: str = StorageProvider.WASABI) -> List[Dict[str, Any]]:
        """
        Получение списка файлов
        
        Args:
            prefix: Префикс для фильтрации
            max_keys: Максимальное количество файлов
            provider: Провайдер хранилища
            
        Returns:
            Список файлов
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            if provider == StorageProvider.WASABI and self.wasabi_client:
                response = self.wasabi_client.list_objects_v2(
                    Bucket=settings.WASABI_BUCKET_NAME,
                    Prefix=prefix,
                    MaxKeys=max_keys
                )
            elif provider == StorageProvider.BACKBLAZE and self.b2_client:
                response = self.b2_client.list_objects_v2(
                    Bucket=settings.B2_BUCKET_NAME,
                    Prefix=prefix,
                    MaxKeys=max_keys
                )
            else:
                return []
            
            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'file_path': obj['Key'],
                    'size_bytes': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag'].strip('"'),
                    'provider': provider
                })
            
            return files
        
        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []
    
    async def cleanup_old_files(self, older_than_days: int = 7, prefix: str = "temp/") -> int:
        """
        Очистка старых файлов
        
        Args:
            older_than_days: Файлы старше указанного количества дней
            prefix: Префикс файлов для очистки
            
        Returns:
            Количество удаленных файлов
        """
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        deleted_count = 0
        
        # Очищаем в Wasabi
        if self.wasabi_client:
            files = await self.list_files(prefix, provider=StorageProvider.WASABI)
            for file_info in files:
                if file_info['last_modified'] < cutoff_date:
                    if await self.delete_file(file_info['file_path'], StorageProvider.WASABI):
                        deleted_count += 1
        
        # Очищаем в Backblaze (если настроен)
        if self.b2_client:
            files = await self.list_files(prefix, provider=StorageProvider.BACKBLAZE)
            for file_info in files:
                if file_info['last_modified'] < cutoff_date:
                    if await self.delete_file(file_info['file_path'], StorageProvider.BACKBLAZE):
                        deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} old files")
        return deleted_count
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Получение статистики хранилища"""
        stats = {
            'providers': {
                'wasabi': {'available': bool(self.wasabi_client)},
                'backblaze': {'available': bool(self.b2_client)}
            },
            'total_files': 0,
            'total_size_bytes': 0
        }
        
        # Статистика Wasabi
        if self.wasabi_client:
            try:
                files = await self.list_files(provider=StorageProvider.WASABI)
                wasabi_stats = {
                    'files_count': len(files),
                    'total_size': sum(f['size_bytes'] for f in files)
                }
                stats['providers']['wasabi'].update(wasabi_stats)
                stats['total_files'] += wasabi_stats['files_count']
                stats['total_size_bytes'] += wasabi_stats['total_size']
            except Exception as e:
                logger.error(f"Error getting Wasabi stats: {e}")
        
        # Статистика Backblaze
        if self.b2_client:
            try:
                files = await self.list_files(provider=StorageProvider.BACKBLAZE)
                b2_stats = {
                    'files_count': len(files),
                    'total_size': sum(f['size_bytes'] for f in files)
                }
                stats['providers']['backblaze'].update(b2_stats)
            except Exception as e:
                logger.error(f"Error getting Backblaze stats: {e}")
        
        return stats


# Глобальный экземпляр конфигурации
storage_config = StorageConfig()

# Основные функции для использования в приложении
async def init_storage():
    """Инициализация хранилища"""
    await storage_config.initialize()

async def close_storage():
    """Закрытие хранилища"""
    await storage_config.close()

# Утилитарные функции
def get_file_path(file_type: str, filename: str, user_id: int = None) -> str:
    """
    Генерация пути файла в хранилище
    
    Args:
        file_type: Тип файла (video, audio, image, archive)
        filename: Имя файла
        user_id: ID пользователя
        
    Returns:
        Путь к файлу в хранилище
    """
    date_prefix = datetime.utcnow().strftime("%Y/%m/%d")
    
    if user_id:
        return f"{file_type}/{date_prefix}/user_{user_id}/{filename}"
    else:
        return f"{file_type}/{date_prefix}/{filename}"

def get_temp_file_path(filename: str) -> str:
    """Путь для временного файла"""
    return f"temp/{datetime.utcnow().strftime('%Y%m%d')}/{filename}"

def get_user_file_path(user_id: int, filename: str) -> str:
    """Путь для пользовательского файла"""
    return get_file_path("user_files", filename, user_id)

def get_archive_file_path(batch_id: str, filename: str) -> str:
    """Путь для архива batch'а"""
    return f"archives/{datetime.utcnow().strftime('%Y/%m')}/{batch_id}/{filename}"