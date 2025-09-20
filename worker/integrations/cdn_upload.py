"""
VideoBot Pro - Worker CDN Integration
Интеграция Worker'а с CDN для загрузки файлов в облачные хранилища
"""

import asyncio
import aiohttp
import aiofiles
import structlog
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from shared.config.settings import settings
from shared.models.user import User
from shared.models.download_task import DownloadTask
from worker.storage.local import local_storage

logger = structlog.get_logger(__name__)

class CDNUploadClient:
    """Клиент для загрузки файлов в CDN"""
    
    def __init__(self):
        self.cdn_base_url = f"http://{settings.CDN_HOST}:{settings.CDN_PORT}"
        self.timeout = aiohttp.ClientTimeout(total=600)  # 10 минут на загрузку
        self.max_retries = 3
    
    async def upload_file(
        self,
        file_path: str,
        task: DownloadTask,
        user: User,
        file_type: str = "video",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Загрузка файла в CDN
        
        Args:
            file_path: Путь к локальному файлу
            task: Задача загрузки
            user: Пользователь
            file_type: Тип файла (video, audio, archive)
            metadata: Дополнительные метаданные
            
        Returns:
            Результат загрузки с URL'ами
        """
        try:
            if not Path(file_path).exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Подготавливаем метаданные
            upload_metadata = {
                'task_id': str(task.id),
                'platform': task.platform,
                'video_url': task.url,
                'file_type': file_type,
                'upload_source': 'worker',
                'worker_version': '2.1.0'
            }
            
            if metadata:
                upload_metadata.update(metadata)
            
            # Получаем токен аутентификации для системных операций
            auth_token = await self._get_system_auth_token()
            
            # Загружаем файл
            result = await self._upload_with_retry(
                file_path=file_path,
                filename=Path(file_path).name,
                user=user,
                metadata=upload_metadata,
                auth_token=auth_token
            )
            
            if result.get('success'):
                logger.info(
                    "File uploaded to CDN",
                    task_id=task.id,
                    file_size=result.get('file_size'),
                    storage_type=result.get('storage_type'),
                    cdn_url=result.get('cdn_url')
                )
                
                # Удаляем локальный файл после успешной загрузки
                await self._cleanup_local_file(file_path)
            
            return result
            
        except Exception as e:
            logger.error(f"CDN upload failed: {e}", task_id=task.id, file_path=file_path)
            return {
                'success': False,
                'error': str(e)
            }
    
    async def upload_multiple_files(
        self,
        files: List[Dict[str, Any]],
        task: DownloadTask,
        user: User
    ) -> Dict[str, Any]:
        """
        Загрузка нескольких файлов в CDN
        
        Args:
            files: Список файлов [{'path': str, 'type': str, 'metadata': dict}]
            task: Задача загрузки
            user: Пользователь
            
        Returns:
            Результат загрузки всех файлов
        """
        try:
            results = {
                'uploaded_files': [],
                'failed_files': [],
                'total_files': len(files),
                'success_count': 0,
                'failed_count': 0
            }
            
            # Загружаем файлы параллельно (но с ограничением)
            semaphore = asyncio.Semaphore(3)  # Максимум 3 одновременные загрузки
            
            async def upload_single_file(file_info):
                async with semaphore:
                    result = await self.upload_file(
                        file_path=file_info['path'],
                        task=task,
                        user=user,
                        file_type=file_info.get('type', 'video'),
                        metadata=file_info.get('metadata', {})
                    )
                    
                    if result.get('success'):
                        results['uploaded_files'].append({
                            'local_path': file_info['path'],
                            'file_type': file_info.get('type'),
                            'cdn_result': result
                        })
                        results['success_count'] += 1
                    else:
                        results['failed_files'].append({
                            'local_path': file_info['path'],
                            'error': result.get('error')
                        })
                        results['failed_count'] += 1
            
            # Запускаем загрузки
            await asyncio.gather(*[
                upload_single_file(file_info) for file_info in files
            ])
            
            results['overall_success'] = results['success_count'] > 0
            
            logger.info(
                "Multiple files upload completed",
                task_id=task.id,
                success_count=results['success_count'],
                failed_count=results['failed_count']
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Multiple files upload failed: {e}", task_id=task.id)
            return {
                'overall_success': False,
                'error': str(e)
            }
    
    async def create_archive_and_upload(
        self,
        files: List[str],
        archive_name: str,
        task: DownloadTask,
        user: User
    ) -> Dict[str, Any]:
        """
        Создание архива и загрузка в CDN
        
        Args:
            files: Список путей к файлам для архивирования
            archive_name: Имя архива
            task: Задача загрузки
            user: Пользователь
            
        Returns:
            Результат создания и загрузки архива
        """
        try:
            # Создаем архив
            archive_path = await self._create_archive(files, archive_name)
            
            if not archive_path:
                return {
                    'success': False,
                    'error': 'Failed to create archive'
                }
            
            # Загружаем архив в CDN
            result = await self.upload_file(
                file_path=archive_path,
                task=task,
                user=user,
                file_type='archive',
                metadata={
                    'files_count': len(files),
                    'archive_type': 'zip',
                    'created_by': 'worker'
                }
            )
            
            # Очищаем временные файлы
            await self._cleanup_local_file(archive_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Archive creation and upload failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _upload_with_retry(
        self,
        file_path: str,
        filename: str,
        user: User,
        metadata: Dict[str, Any],
        auth_token: str
    ) -> Dict[str, Any]:
        """Загрузка файла с повторными попытками"""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return await self._do_upload(
                    file_path, filename, user, metadata, auth_token
                )
                
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Upload attempt {attempt + 1} failed, retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All upload attempts failed: {e}")
        
        return {
            'success': False,
            'error': f"Upload failed after {self.max_retries} attempts: {last_error}"
        }
    
    async def _do_upload(
        self,
        file_path: str,
        filename: str,
        user: User,
        metadata: Dict[str, Any],
        auth_token: str
    ) -> Dict[str, Any]:
        """Выполнение загрузки файла"""
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Подготавливаем данные для загрузки
            data = aiohttp.FormData()
            
            # Добавляем файл
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
                data.add_field(
                    'file',
                    file_content,
                    filename=filename,
                    content_type='application/octet-stream'
                )
            
            # Добавляем метаданные
            data.add_field('user_type', user.user_type)
            data.add_field('public', 'false')
            
            for key, value in metadata.items():
                data.add_field(f'metadata_{key}', str(value))
            
            # Заголовки
            headers = {
                'Authorization': f'Bearer {auth_token}',
                'X-User-ID': str(user.id),
                'X-Upload-Source': 'worker'
            }
            
            # Выполняем загрузку
            upload_url = f"{self.cdn_base_url}/api/v1/admin/upload"
            
            async with session.post(upload_url, data=data, headers=headers) as response:
                result = await response.json()
                
                if response.status != 200:
                    raise aiohttp.ClientError(
                        f"Upload failed with status {response.status}: {result.get('error', 'Unknown error')}"
                    )
                
                return result
    
    async def _get_system_auth_token(self) -> str:
        """Получение системного токена аутентификации"""
        try:
            # В реальной реализации здесь будет получение токена из auth сервиса
            # Пока возвращаем фиктивный токен для системных операций
            return "system-worker-token-" + str(int(datetime.utcnow().timestamp()))
            
        except Exception as e:
            logger.error(f"Failed to get auth token: {e}")
            return "fallback-system-token"
    
    async def _create_archive(self, files: List[str], archive_name: str) -> Optional[str]:
        """Создание ZIP архива из файлов"""
        try:
            import zipfile
            
            # Создаем временный архив
            archive_path = local_storage.create_temp_file(
                suffix='.zip',
                prefix=f'archive_{archive_name}_'
            )
            
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in files:
                    if Path(file_path).exists():
                        # Добавляем файл в архив с его именем (без полного пути)
                        arcname = Path(file_path).name
                        zipf.write(file_path, arcname)
                    else:
                        logger.warning(f"File not found for archiving: {file_path}")
            
            logger.info(f"Archive created: {archive_path}")
            return archive_path
            
        except Exception as e:
            logger.error(f"Failed to create archive: {e}")
            return None
    
    async def _cleanup_local_file(self, file_path: str):
        """Очистка локального файла после загрузки"""
        try:
            if Path(file_path).exists():
                Path(file_path).unlink()
                logger.debug(f"Local file cleaned up: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup local file {file_path}: {e}")

class CDNIntegrationService:
    """Сервис интеграции Worker'а с CDN"""
    
    def __init__(self):
        self.cdn_client = CDNUploadClient()
        self.enabled = self._check_cdn_availability()
    
    def _check_cdn_availability(self) -> bool:
        """Проверка доступности CDN"""
        try:
            # Проверяем, настроен ли CDN
            return bool(settings.CDN_HOST and settings.CDN_PORT)
        except Exception:
            return False
    
    async def handle_download_completion(
        self,
        task: DownloadTask,
        user: User,
        downloaded_files: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Обработка завершения загрузки - загрузка файлов в CDN
        
        Args:
            task: Задача загрузки
            user: Пользователь
            downloaded_files: Список загруженных файлов
            
        Returns:
            Результат загрузки в CDN
        """
        if not self.enabled:
            logger.warning("CDN integration disabled")
            return {'success': False, 'error': 'CDN not available'}
        
        try:
            # Определяем стратегию загрузки
            if len(downloaded_files) == 1:
                # Одиночный файл
                file_info = downloaded_files[0]
                return await self.cdn_client.upload_file(
                    file_path=file_info['path'],
                    task=task,
                    user=user,
                    file_type=file_info.get('type', 'video'),
                    metadata=file_info.get('metadata', {})
                )
            
            elif len(downloaded_files) > 1:
                # Множественные файлы - создаем архив
                file_paths = [f['path'] for f in downloaded_files]
                archive_name = f"batch_{task.id}_{int(datetime.utcnow().timestamp())}"
                
                return await self.cdn_client.create_archive_and_upload(
                    files=file_paths,
                    archive_name=archive_name,
                    task=task,
                    user=user
                )
            
            else:
                return {'success': False, 'error': 'No files to upload'}
                
        except Exception as e:
            logger.error(f"CDN integration failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def upload_thumbnail(
        self,
        thumbnail_path: str,
        task: DownloadTask,
        user: User
    ) -> Dict[str, Any]:
        """Загрузка превью в CDN"""
        if not self.enabled:
            return {'success': False, 'error': 'CDN not available'}
        
        try:
            return await self.cdn_client.upload_file(
                file_path=thumbnail_path,
                task=task,
                user=user,
                file_type='thumbnail',
                metadata={
                    'is_thumbnail': 'true',
                    'parent_task_id': str(task.id)
                }
            )
            
        except Exception as e:
            logger.error(f"Thumbnail upload failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_cdn_stats(self) -> Dict[str, Any]:
        """Получение статистики CDN"""
        if not self.enabled:
            return {'error': 'CDN not available'}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.cdn_client.cdn_base_url}/api/v1/stats/overview"
                
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {'error': f'CDN stats request failed: {response.status}'}
                        
        except Exception as e:
            logger.error(f"Failed to get CDN stats: {e}")
            return {'error': str(e)}

# Глобальный экземпляр сервиса интеграции
cdn_integration = CDNIntegrationService()

# Утилитарные функции для использования в Worker'е
async def upload_to_cdn(
    task: DownloadTask,
    user: User,
    downloaded_files: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Основная функция для загрузки файлов в CDN"""
    return await cdn_integration.handle_download_completion(task, user, downloaded_files)

async def upload_thumbnail_to_cdn(
    thumbnail_path: str,
    task: DownloadTask,
    user: User
) -> Dict[str, Any]:
    """Загрузка превью в CDN"""
    return await cdn_integration.upload_thumbnail(thumbnail_path, task, user)

async def is_cdn_available() -> bool:
    """Проверка доступности CDN"""
    return cdn_integration.enabled