"""
VideoBot Pro - Bot CDN Client
Клиент для взаимодействия бота с CDN сервисом
"""

import asyncio
import aiohttp
import structlog
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from urllib.parse import urljoin

from shared.config.settings import settings
from shared.models import User, DownloadTask, DownloadBatch

logger = structlog.get_logger(__name__)


class CDNClientError(Exception):
    """Базовая ошибка CDN клиента"""
    pass


class CDNClient:
    """Клиент для взаимодействия с CDN"""
    
    def __init__(self):
        self.base_url = f"http://{settings.CDN_HOST}:{settings.CDN_PORT}"
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.max_retries = 3
        
        # Кэш токенов
        self._auth_cache = {}
        self._file_cache = {}
        
    async def get_file_info(self, file_path: str, user: Optional[User] = None) -> Optional[Dict[str, Any]]:
        """
        Получение информации о файле
        
        Args:
            file_path: Путь к файлу
            user: Пользователь для проверки прав доступа
            
        Returns:
            Информация о файле или None
        """
        try:
            # Проверяем кэш
            cache_key = f"{file_path}:{user.id if user else 'anonymous'}"
            if cache_key in self._file_cache:
                cached = self._file_cache[cache_key]
                if datetime.utcnow() - cached['timestamp'] < timedelta(minutes=5):
                    return cached['data']
            
            # Получаем токен аутентификации
            auth_token = await self._get_auth_token(user) if user else None
            
            # Выполняем запрос
            headers = {}
            if auth_token:
                headers['Authorization'] = f'Bearer {auth_token}'
            
            url = urljoin(self.base_url, f"/api/v1/files/info/{file_path}")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Кэшируем результат
                        self._file_cache[cache_key] = {
                            'data': data,
                            'timestamp': datetime.utcnow()
                        }
                        
                        return data
                    elif response.status == 404:
                        return None
                    else:
                        error_text = await response.text()
                        logger.warning(f"CDN file info request failed: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting file info from CDN: {e}")
            return None
    
    async def get_file_url(self, file_path: str, user: Optional[User] = None, expires_hours: int = 24) -> Optional[str]:
        """
        Получение URL для скачивания файла
        
        Args:
            file_path: Путь к файлу
            user: Пользователь
            expires_hours: Время жизни ссылки в часах
            
        Returns:
            URL для скачивания
        """
        try:
            # Получаем информацию о файле
            file_info = await self.get_file_info(file_path, user)
            if not file_info:
                return None
            
            # Если есть CDN URL - используем его
            if file_info.get('metadata', {}).get('cdn_url'):
                return file_info['metadata']['cdn_url']
            
            # Если есть публичный URL - используем его
            if file_info.get('metadata', {}).get('public_url'):
                return file_info['metadata']['public_url']
            
            # Создаем временный токен доступа
            if user:
                access_token = await self._create_file_access_token(file_path, user, expires_hours)
                if access_token:
                    return f"{self.base_url}/api/v1/files/{file_path}?token={access_token}"
            
            # Fallback на прямой URL
            return f"{self.base_url}/api/v1/files/{file_path}"
            
        except Exception as e:
            logger.error(f"Error getting file URL: {e}")
            return None
    
    async def check_file_availability(self, file_paths: List[str], user: Optional[User] = None) -> Dict[str, bool]:
        """
        Проверка доступности множества файлов
        
        Args:
            file_paths: Список путей к файлам
            user: Пользователь
            
        Returns:
            Словарь {file_path: available}
        """
        try:
            results = {}
            
            # Проверяем файлы батчами по 10
            batch_size = 10
            for i in range(0, len(file_paths), batch_size):
                batch = file_paths[i:i + batch_size]
                
                # Запускаем проверку параллельно для batch'а
                tasks = [self.get_file_info(path, user) for path in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for path, result in zip(batch, batch_results):
                    if isinstance(result, Exception):
                        results[path] = False
                    else:
                        results[path] = result is not None
                
                # Небольшая пауза между батчами
                if i + batch_size < len(file_paths):
                    await asyncio.sleep(0.1)
            
            return results
            
        except Exception as e:
            logger.error(f"Error checking files availability: {e}")
            return {path: False for path in file_paths}
    
    async def get_batch_download_info(self, batch_id: str, user: User) -> Optional[Dict[str, Any]]:
        """
        Получение информации о batch загрузке
        
        Args:
            batch_id: ID batch'а
            user: Пользователь
            
        Returns:
            Информация о batch'е
        """
        try:
            auth_token = await self._get_auth_token(user)
            if not auth_token:
                return None
            
            headers = {'Authorization': f'Bearer {auth_token}'}
            url = urljoin(self.base_url, f"/api/v1/batches/{batch_id}")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Batch info request failed: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting batch info: {e}")
            return None
    
    async def create_file_collection(
        self,
        files: List[Dict[str, Any]], 
        user: User,
        collection_name: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Создание коллекции файлов (для batch доставки)
        
        Args:
            files: Список файлов с метаданными
            user: Пользователь
            collection_name: Имя коллекции
            
        Returns:
            Информация о созданной коллекции
        """
        try:
            auth_token = await self._get_auth_token(user)
            if not auth_token:
                return None
            
            headers = {
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'files': files,
                'collection_name': collection_name or f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                'expires_hours': self._get_user_retention_hours(user),
                'user_type': user.user_type
            }
            
            url = urljoin(self.base_url, "/api/v1/collections")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 201:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"Collection creation failed: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error creating file collection: {e}")
            return None
    
    async def get_storage_stats(self, user: User) -> Optional[Dict[str, Any]]:
        """
        Получение статистики хранилища (для админов)
        
        Args:
            user: Пользователь (должен быть админом)
            
        Returns:
            Статистика хранилища
        """
        try:
            if user.user_type not in ['admin', 'owner']:
                return None
            
            auth_token = await self._get_auth_token(user)
            if not auth_token:
                return None
            
            headers = {'Authorization': f'Bearer {auth_token}'}
            url = urljoin(self.base_url, "/api/v1/admin/storage/stats")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return None
    
    async def cleanup_user_files(self, user: User, older_than_hours: int = None) -> bool:
        """
        Очистка файлов пользователя
        
        Args:
            user: Пользователь
            older_than_hours: Удалить файлы старше указанного времени
            
        Returns:
            True если очистка прошла успешно
        """
        try:
            auth_token = await self._get_auth_token(user)
            if not auth_token:
                return False
            
            headers = {'Authorization': f'Bearer {auth_token}'}
            params = {}
            if older_than_hours:
                params['older_than_hours'] = older_than_hours
            
            url = urljoin(self.base_url, f"/api/v1/users/{user.id}/cleanup")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, headers=headers, params=params) as response:
                    return response.status == 200
                    
        except Exception as e:
            logger.error(f"Error cleaning user files: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Проверка состояния CDN сервиса
        
        Returns:
            Статус здоровья CDN
        """
        try:
            url = urljoin(self.base_url, "/health")
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {
                            'status': 'unhealthy',
                            'error': f'HTTP {response.status}'
                        }
                        
        except Exception as e:
            return {
                'status': 'unreachable',
                'error': str(e)
            }
    
    # Приватные методы
    
    async def _get_auth_token(self, user: User) -> Optional[str]:
        """Получение токена аутентификации для CDN"""
        try:
            # Проверяем кэш
            cache_key = f"auth:{user.id}"
            if cache_key in self._auth_cache:
                cached = self._auth_cache[cache_key]
                if datetime.utcnow() < cached['expires_at']:
                    return cached['token']
            
            # Получаем новый токен
            from shared.services.auth import auth_service
            
            # Создаем временный токен для CDN
            cdn_token = await auth_service.create_cdn_token(
                user_id=user.id,
                expires_hours=24
            )
            
            if cdn_token:
                # Кэшируем токен
                self._auth_cache[cache_key] = {
                    'token': cdn_token,
                    'expires_at': datetime.utcnow() + timedelta(hours=23)  # На час меньше реального времени
                }
                
                return cdn_token
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting CDN auth token: {e}")
            return None
    
    async def _create_file_access_token(
        self, 
        file_path: str, 
        user: User, 
        expires_hours: int
    ) -> Optional[str]:
        """Создание временного токена доступа к файлу"""
        try:
            auth_token = await self._get_auth_token(user)
            if not auth_token:
                return None
            
            headers = {
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'file_path': file_path,
                'user_id': user.id,
                'duration_hours': expires_hours
            }
            
            url = urljoin(self.base_url, "/api/v1/auth/file-access")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('access_token')
                    else:
                        return None
                        
        except Exception as e:
            logger.error(f"Error creating file access token: {e}")
            return None
    
    def _get_user_retention_hours(self, user: User) -> int:
        """Получение времени хранения для типа пользователя"""
        retention_map = {
            'free': 24,
            'trial': 72,
            'premium': 168,  # 7 дней
            'admin': 720,    # 30 дней
            'owner': 8760    # 365 дней
        }
        return retention_map.get(user.user_type, 24)
    
    def clear_cache(self):
        """Очистка кэша клиента"""
        self._auth_cache.clear()
        self._file_cache.clear()


class CDNIntegration:
    """Главный класс интеграции бота с CDN"""
    
    def __init__(self):
        self.client = CDNClient()
        self.enabled = self._check_cdn_availability()
    
    def _check_cdn_availability(self) -> bool:
        """Проверка доступности CDN"""
        try:
            return bool(settings.CDN_HOST and settings.CDN_PORT)
        except Exception:
            return False
    
    async def process_download_completion(
        self,
        task: DownloadTask,
        user: User,
        file_paths: List[str]
    ) -> Dict[str, Any]:
        """
        Обработка завершения загрузки - получение ссылок из CDN
        
        Args:
            task: Задача загрузки
            user: Пользователь
            file_paths: Пути к файлам в CDN
            
        Returns:
            Результат с URL'ами для отправки пользователю
        """
        if not self.enabled:
            logger.warning("CDN integration disabled")
            return {'success': False, 'error': 'CDN not available'}
        
        try:
            result = {
                'success': True,
                'files': [],
                'delivery_method': 'individual',
                'total_files': len(file_paths)
            }
            
            # Получаем информацию и URL'ы для каждого файла
            for file_path in file_paths:
                file_info = await self.client.get_file_info(file_path, user)
                if file_info:
                    file_url = await self.client.get_file_url(file_path, user)
                    
                    result['files'].append({
                        'path': file_path,
                        'name': file_info.get('metadata', {}).get('original_filename', file_path.split('/')[-1]),
                        'size': file_info.get('size', 0),
                        'url': file_url,
                        'type': file_info.get('content_type', 'video/mp4'),
                        'expires_at': file_info.get('expires_at')
                    })
                else:
                    logger.warning(f"File not found in CDN: {file_path}")
            
            # Если файлов больше 3 - предлагаем коллекцию
            if len(result['files']) > 3:
                collection = await self.client.create_file_collection(
                    files=result['files'],
                    user=user,
                    collection_name=f"batch_{task.id}"
                )
                
                if collection:
                    result['collection'] = collection
                    result['delivery_method'] = 'collection'
            
            logger.info(
                f"CDN download completion processed",
                task_id=task.id,
                files_count=len(result['files']),
                delivery_method=result['delivery_method']
            )
            
            return result
            
        except Exception as e:
            logger.error(f"CDN download completion processing failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def process_batch_completion(
        self,
        batch: DownloadBatch,
        user: User,
        completed_files: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Обработка завершения batch загрузки
        
        Args:
            batch: Batch загрузки
            user: Пользователь
            completed_files: Список завершенных файлов
            
        Returns:
            Результат с URL'ами для batch доставки
        """
        if not self.enabled:
            return {'success': False, 'error': 'CDN not available'}
        
        try:
            # Определяем метод доставки
            if batch.delivery_method == 'archive':
                # Создаем коллекцию для архивной доставки
                collection = await self.client.create_file_collection(
                    files=completed_files,
                    user=user,
                    collection_name=f"batch_{batch.batch_id}"
                )
                
                return {
                    'success': True,
                    'delivery_method': 'archive',
                    'collection': collection,
                    'total_files': len(completed_files)
                }
            else:
                # Индивидуальная доставка
                files_with_urls = []
                
                for file_info in completed_files:
                    file_url = await self.client.get_file_url(file_info['path'], user)
                    if file_url:
                        files_with_urls.append({
                            **file_info,
                            'url': file_url
                        })
                
                return {
                    'success': True,
                    'delivery_method': 'individual',
                    'files': files_with_urls,
                    'total_files': len(files_with_urls)
                }
                
        except Exception as e:
            logger.error(f"CDN batch completion processing failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_file_for_telegram(
        self, 
        file_path: str, 
        user: User
    ) -> Optional[Dict[str, Any]]:
        """
        Получение файла для отправки в Telegram
        
        Args:
            file_path: Путь к файлу
            user: Пользователь
            
        Returns:
            Информация о файле для Telegram
        """
        try:
            file_info = await self.client.get_file_info(file_path, user)
            if not file_info:
                return None
            
            file_url = await self.client.get_file_url(file_path, user, expires_hours=1)
            if not file_url:
                return None
            
            return {
                'url': file_url,
                'filename': file_info.get('metadata', {}).get('original_filename', 'video.mp4'),
                'size': file_info.get('size', 0),
                'content_type': file_info.get('content_type', 'video/mp4'),
                'duration': file_info.get('metadata', {}).get('duration_seconds'),
                'thumbnail_url': file_info.get('metadata', {}).get('thumbnail_url')
            }
            
        except Exception as e:
            logger.error(f"Error getting file for Telegram: {e}")
            return None


# Глобальный экземпляр интеграции
cdn_integration = CDNIntegration()

# Утилитарные функции для использования в bot
async def get_file_download_url(file_path: str, user: User) -> Optional[str]:
    """Получение URL для скачивания файла"""
    return await cdn_integration.client.get_file_url(file_path, user)

async def check_files_availability(file_paths: List[str], user: User) -> Dict[str, bool]:
    """Проверка доступности файлов"""
    return await cdn_integration.client.check_file_availability(file_paths, user)

async def is_cdn_available() -> bool:
    """Проверка доступности CDN"""
    if not cdn_integration.enabled:
        return False
    
    try:
        health = await cdn_integration.client.health_check()
        return health.get('status') == 'healthy'
    except Exception:
        return False