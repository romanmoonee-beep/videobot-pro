"""
VideoBot Pro - Updated Worker Tasks with CDN Integration
Обновленные задачи Worker'а с интеграцией CDN
"""

import asyncio
import structlog
from datetime import datetime
from typing import Dict, Any, List, Optional
from celery import Task

from shared.models.download_task import DownloadTask
from shared.models.user import User
from shared.config.database import get_async_session
from worker.celery_app import celery_app
from worker.downloaders.factory import DownloaderFactory
from worker.processors.video_processor import VideoProcessor
from worker.processors.thumbnail_generator import ThumbnailGenerator
from worker.storage.local import local_storage
from worker.integrations.cdn_upload import upload_to_cdn, upload_thumbnail_to_cdn, is_cdn_available

logger = structlog.get_logger(__name__)

class BaseWorkerTask(Task):
    """Базовый класс для всех задач Worker'а"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Обработка ошибок задач"""
        logger.error(
            "Task failed",
            task_id=task_id,
            exception=str(exc),
            args=args,
            kwargs=kwargs
        )

@celery_app.task(bind=True, base=BaseWorkerTask, name='download_video')
async def download_video_task(
    self,
    task_id: int,
    user_id: int,
    url: str,
    quality: str = "best",
    extract_audio: bool = False,
    generate_thumbnail: bool = True
) -> Dict[str, Any]:
    """
    Основная задача загрузки видео с интеграцией CDN
    
    Args:
        task_id: ID задачи в базе данных
        user_id: ID пользователя
        url: URL видео
        quality: Качество видео
        extract_audio: Извлекать ли аудио
        generate_thumbnail: Генерировать ли превью
        
    Returns:
        Результат выполнения задачи
    """
    result = {
        'task_id': task_id,
        'success': False,
        'files': [],
        'cdn_urls': [],
        'errors': []
    }
    
    try:
        logger.info(f"Starting video download task", task_id=task_id, url=url)
        
        # Получаем задачу и пользователя из базы данных
        async with get_async_session() as session:
            task = await session.get(DownloadTask, task_id)
            user = await session.get(User, user_id)
            
            if not task or not user:
                raise ValueError("Task or user not found")
        
        # Обновляем статус задачи
        await _update_task_status(task_id, 'downloading', 'Starting download...')
        
        # 1. ЭТАП: Определяем платформу и создаем загрузчик
        downloader = DownloaderFactory.create_downloader(url)
        if not downloader:
            raise ValueError(f"Unsupported platform for URL: {url}")
        
        # 2. ЭТАП: Получаем информацию о видео
        await _update_task_status(task_id, 'downloading', 'Getting video info...')
        video_info = await downloader.get_video_info(url)
        
        if not video_info:
            raise ValueError("Failed to get video information")
        
        # 3. ЭТАП: Загружаем видео
        await _update_task_status(task_id, 'downloading', 'Downloading video file...')
        download_result = await downloader.download(
            url=url,
            quality=quality,
            output_path=local_storage.downloads_dir
        )
        
        if not download_result.get('success'):
            raise ValueError(f"Download failed: {download_result.get('error')}")
        
        downloaded_files = []
        video_file_path = download_result['file_path']
        
        # Основной видеофайл
        downloaded_files.append({
            'path': video_file_path,
            'type': 'video',
            'metadata': {
                'title': video_info.get('title'),
                'duration': video_info.get('duration'),
                'format': video_info.get('format'),
                'quality': quality
            }
        })
        
        # 4. ЭТАП: Обработка видео (если нужно)
        if user.user_type in ['premium', 'admin'] and quality != 'best':
            await _update_task_status(task_id, 'processing', 'Processing video...')
            processor = VideoProcessor()
            
            processed_file = await processor.process_video(
                input_path=video_file_path,
                quality=quality,
                user_type=user.user_type
            )
            
            if processed_file:
                downloaded_files.append({
                    'path': processed_file,
                    'type': 'video_processed',
                    'metadata': {
                        'processed_quality': quality,
                        'original_file': video_file_path
                    }
                })
        
        # 5. ЭТАП: Извлечение аудио (если нужно)
        if extract_audio:
            await _update_task_status(task_id, 'processing', 'Extracting audio...')
            processor = VideoProcessor()
            
            audio_file = await processor.extract_audio(
                video_path=video_file_path,
                output_format='mp3'
            )
            
            if audio_file:
                downloaded_files.append({
                    'path': audio_file,
                    'type': 'audio',
                    'metadata': {
                        'format': 'mp3',
                        'extracted_from': video_file_path
                    }
                })
        
        # 6. ЭТАП: Генерация превью (если нужно)
        thumbnail_cdn_url = None
        if generate_thumbnail:
            await _update_task_status(task_id, 'processing', 'Generating thumbnail...')
            thumbnail_generator = ThumbnailGenerator()
            
            thumbnail_path = await thumbnail_generator.generate_thumbnail(
                video_path=video_file_path,
                timestamp=30  # Превью на 30-й секунде
            )
            
            if thumbnail_path:
                # Загружаем превью в CDN отдельно
                if await is_cdn_available():
                    thumbnail_result = await upload_thumbnail_to_cdn(
                        thumbnail_path, task, user
                    )
                    
                    if thumbnail_result.get('success'):
                        thumbnail_cdn_url = thumbnail_result.get('cdn_url')
                
                downloaded_files.append({
                    'path': thumbnail_path,
                    'type': 'thumbnail',
                    'metadata': {
                        'timestamp': 30,
                        'format': 'jpg'
                    }
                })
        
        # 7. ЭТАП: Загрузка в CDN
        cdn_result = None
        if await is_cdn_available():
            await _update_task_status(task_id, 'uploading', 'Uploading to cloud storage...')
            
            cdn_result = await upload_to_cdn(task, user, downloaded_files)
            
            if cdn_result.get('success'):
                result['cdn_urls'] = [cdn_result.get('cdn_url')]
                result['direct_urls'] = [cdn_result.get('direct_url')]
                result['storage_type'] = cdn_result.get('storage_type')
                
                logger.info(
                    "Files uploaded to CDN",
                    task_id=task_id,
                    storage_type=cdn_result.get('storage_type'),
                    cdn_url=cdn_result.get('cdn_url')
                )
            else:
                logger.warning(f"CDN upload failed: {cdn_result.get('error')}")
                result['errors'].append(f"CDN upload failed: {cdn_result.get('error')}")
        else:
            logger.warning("CDN not available, files stored locally only")
            result['errors'].append("CDN not available")
        
        # 8. ЭТАП: Обновление базы данных
        await _update_task_completion(
            task_id=task_id,
            cdn_url=cdn_result.get('cdn_url') if cdn_result else None,
            direct_url=cdn_result.get('direct_url') if cdn_result else None,
            thumbnail_url=thumbnail_cdn_url,
            file_size=download_result.get('file_size', 0),
            video_info=video_info
        )
        
        # 9. ЭТАП: Очистка локальных файлов (если загружено в CDN)
        if cdn_result and cdn_result.get('success'):
            await _cleanup_local_files([f['path'] for f in downloaded_files])
        
        result['success'] = True
        result['files'] = downloaded_files
        result['video_info'] = video_info
        
        logger.info(f"Video download task completed successfully", task_id=task_id)
        
        return result
        
    except Exception as e:
        logger.error(f"Video download task failed", task_id=task_id, error=str(e))
        
        # Обновляем статус задачи как неудачной
        await _update_task_status(task_id, 'failed', f'Error: {str(e)}')
        
        result['errors'].append(str(e))
        return result

@celery_app.task(bind=True, base=BaseWorkerTask, name='download_batch')
async def download_batch_task(
    self,
    batch_id: int,
    user_id: int,
    urls: List[str],
    quality: str = "best",
    create_archive: bool = True
) -> Dict[str, Any]:
    """
    Задача пакетной загрузки видео
    
    Args:
        batch_id: ID пакета в базе данных
        user_id: ID пользователя
        urls: Список URL для загрузки
        quality: Качество видео
        create_archive: Создавать ли архив
        
    Returns:
        Результат выполнения пакетной загрузки
    """
    result = {
        'batch_id': batch_id,
        'success': False,
        'completed_downloads': 0,
        'failed_downloads': 0,
        'files': [],
        'archive_url': None,
        'errors': []
    }
    
    try:
        logger.info(f"Starting batch download", batch_id=batch_id, urls_count=len(urls))
        
        # Получаем пользователя
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                raise ValueError("User not found")
        
        # Обновляем статус пакета
        await _update_batch_status(batch_id, 'downloading', 'Starting batch download...')
        
        all_downloaded_files = []
        
        # Загружаем каждое видео
        for i, url in enumerate(urls):
            try:
                await _update_batch_status(
                    batch_id, 'downloading', 
                    f'Downloading {i+1}/{len(urls)}: {url[:50]}...'
                )
                
                # Создаем временную задачу для загрузки
                temp_task = DownloadTask(
                    id=f"batch_{batch_id}_{i}",
                    url=url,
                    user_id=user_id,
                    platform=_detect_platform(url)
                )
                
                # Загружаем видео
                download_result = await download_video_task.apply_async(
                    args=[temp_task.id, user_id, url, quality, False, True],
                    countdown=0
                ).get()
                
                if download_result.get('success'):
                    all_downloaded_files.extend(download_result.get('files', []))
                    result['completed_downloads'] += 1
                else:
                    result['failed_downloads'] += 1
                    result['errors'].extend(download_result.get('errors', []))
                    
            except Exception as e:
                logger.error(f"Failed to download {url}: {e}")
                result['failed_downloads'] += 1
                result['errors'].append(f"URL {url}: {str(e)}")
        
        # Если есть загруженные файлы и нужно создать архив
        if all_downloaded_files and create_archive:
            await _update_batch_status(batch_id, 'processing', 'Creating archive...')
            
            try:
                from worker.integrations.cdn_upload import cdn_integration
                
                # Создаем архив и загружаем в CDN
                file_paths = [f['path'] for f in all_downloaded_files if f.get('type') == 'video']
                archive_name = f"batch_{batch_id}_{int(datetime.utcnow().timestamp())}"
                
                archive_result = await cdn_integration.cdn_client.create_archive_and_upload(
                    files=file_paths,
                    archive_name=archive_name,
                    task=temp_task,  # Используем последнюю временную задачу
                    user=user
                )
                
                if archive_result.get('success'):
                    result['archive_url'] = archive_result.get('cdn_url')
                    logger.info(f"Batch archive created", batch_id=batch_id, archive_url=result['archive_url'])
                else:
                    result['errors'].append(f"Archive creation failed: {archive_result.get('error')}")
                    
            except Exception as e:
                logger.error(f"Archive creation failed: {e}")
                result['errors'].append(f"Archive creation failed: {str(e)}")
        
        # Обновляем результат
        result['success'] = result['completed_downloads'] > 0
        result['files'] = all_downloaded_files
        
        # Обновляем статус пакета в базе данных
        final_status = 'completed' if result['success'] else 'failed'
        status_message = f"Completed: {result['completed_downloads']}, Failed: {result['failed_downloads']}"
        
        await _update_batch_status(batch_id, final_status, status_message)
        await _update_batch_completion(
            batch_id=batch_id,
            archive_url=result.get('archive_url'),
            completed_count=result['completed_downloads'],
            failed_count=result['failed_downloads']
        )
        
        # Очистка локальных файлов
        if result.get('archive_url'):
            await _cleanup_local_files([f['path'] for f in all_downloaded_files])
        
        logger.info(f"Batch download completed", batch_id=batch_id, **result)
        
        return result
        
    except Exception as e:
        logger.error(f"Batch download task failed", batch_id=batch_id, error=str(e))
        
        await _update_batch_status(batch_id, 'failed', f'Error: {str(e)}')
        
        result['errors'].append(str(e))
        return result

@celery_app.task(bind=True, base=BaseWorkerTask, name='cleanup_old_files')
async def cleanup_old_files_task(self, max_age_hours: int = 24) -> Dict[str, Any]:
    """
    Задача очистки старых файлов
    
    Args:
        max_age_hours: Максимальный возраст файлов в часах
        
    Returns:
        Результат очистки
    """
    result = {
        'success': False,
        'local_cleanup': {},
        'cdn_cleanup': {},
        'total_freed_space_gb': 0.0,
        'errors': []
    }
    
    try:
        logger.info(f"Starting cleanup task", max_age_hours=max_age_hours)
        
        # 1. Очистка локальных файлов
        try:
            local_result = {
                'downloads': local_storage.cleanup_old_files('downloads', max_age_hours),
                'thumbnails': local_storage.cleanup_old_files('thumbnails', max_age_hours),
                'temp': local_storage.cleanup_temp_files(max_age_hours)
            }
            
            result['local_cleanup'] = local_result
            logger.info(f"Local cleanup completed", **local_result)
            
        except Exception as e:
            logger.error(f"Local cleanup failed: {e}")
            result['errors'].append(f"Local cleanup: {str(e)}")
        
        # 2. Очистка CDN (если доступен)
        if await is_cdn_available():
            try:
                from worker.integrations.cdn_upload import cdn_integration
                
                cdn_stats = await cdn_integration.get_cdn_stats()
                
                if 'error' not in cdn_stats:
                    # Запрашиваем очистку через CDN API
                    import aiohttp
                    
                    async with aiohttp.ClientSession() as session:
                        cleanup_url = f"{cdn_integration.cdn_client.cdn_base_url}/api/v1/admin/storage/cleanup"
                        headers = {
                            'Authorization': f'Bearer {await cdn_integration.cdn_client._get_system_auth_token()}'
                        }
                        
                        async with session.post(cleanup_url, headers=headers) as response:
                            if response.status == 200:
                                cdn_cleanup_result = await response.json()
                                result['cdn_cleanup'] = cdn_cleanup_result.get('cleanup_result', {})
                            else:
                                result['errors'].append(f"CDN cleanup request failed: {response.status}")
                
            except Exception as e:
                logger.error(f"CDN cleanup failed: {e}")
                result['errors'].append(f"CDN cleanup: {str(e)}")
        
        # Подсчитываем общее освобожденное место
        total_freed = 0.0
        if result['local_cleanup']:
            # Примерный расчет на основе количества файлов
            total_files = sum(result['local_cleanup'].values())
            total_freed += total_files * 0.1  # Примерно 100MB на файл
        
        if result['cdn_cleanup']:
            total_freed += result['cdn_cleanup'].get('total_freed_gb', 0.0)
        
        result['total_freed_space_gb'] = round(total_freed, 2)
        result['success'] = len(result['errors']) == 0
        
        logger.info(f"Cleanup task completed", **result)
        
        return result
        
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        result['errors'].append(str(e))
        return result

@celery_app.task(bind=True, base=BaseWorkerTask, name='migrate_files_to_cdn')
async def migrate_files_to_cdn_task(self, limit: int = 100) -> Dict[str, Any]:
    """
    Задача миграции локальных файлов в CDN
    
    Args:
        limit: Максимальное количество файлов для миграции за раз
        
    Returns:
        Результат миграции
    """
    result = {
        'success': False,
        'migrated_files': 0,
        'failed_files': 0,
        'total_size_gb': 0.0,
        'errors': []
    }
    
    try:
        logger.info(f"Starting file migration to CDN", limit=limit)
        
        if not await is_cdn_available():
            raise ValueError("CDN is not available")
        
        # Получаем список локальных файлов
        local_files = []
        
        for category in ['downloads', 'thumbnails']:
            try:
                category_dir = local_storage._get_category_dir(category)
                
                for file_path in category_dir.rglob("*"):
                    if file_path.is_file() and len(local_files) < limit:
                        local_files.append({
                            'path': str(file_path),
                            'category': category,
                            'size': file_path.stat().st_size
                        })
            except Exception as e:
                logger.warning(f"Error scanning {category} directory: {e}")
        
        if not local_files:
            result['success'] = True
            logger.info("No local files found for migration")
            return result
        
        # Мигрируем файлы
        from worker.integrations.cdn_upload import cdn_integration
        
        for file_info in local_files:
            try:
                # Создаем фиктивную задачу для миграции
                migration_task = DownloadTask(
                    id=f"migration_{int(datetime.utcnow().timestamp())}",
                    url="local_migration",
                    user_id=1,  # Системный пользователь
                    platform="migration"
                )
                
                # Создаем фиктивного пользователя
                migration_user = User(
                    id=1,
                    username="system",
                    user_type="admin"
                )
                
                # Загружаем файл в CDN
                upload_result = await cdn_integration.cdn_client.upload_file(
                    file_path=file_info['path'],
                    task=migration_task,
                    user=migration_user,
                    file_type=file_info['category'],
                    metadata={
                        'migrated_from_local': 'true',
                        'migration_date': datetime.utcnow().isoformat(),
                        'original_category': file_info['category']
                    }
                )
                
                if upload_result.get('success'):
                    # Удаляем локальный файл после успешной загрузки
                    try:
                        import os
                        os.unlink(file_info['path'])
                        
                        result['migrated_files'] += 1
                        result['total_size_gb'] += file_info['size'] / (1024**3)
                        
                        logger.debug(f"Migrated file: {file_info['path']}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to delete local file after migration: {e}")
                else:
                    result['failed_files'] += 1
                    result['errors'].append(f"File {file_info['path']}: {upload_result.get('error')}")
                    
            except Exception as e:
                result['failed_files'] += 1
                result['errors'].append(f"File {file_info['path']}: {str(e)}")
                logger.error(f"Migration failed for {file_info['path']}: {e}")
        
        result['success'] = result['migrated_files'] > 0
        result['total_size_gb'] = round(result['total_size_gb'], 2)
        
        logger.info(f"File migration completed", **result)
        
        return result
        
    except Exception as e:
        logger.error(f"File migration task failed: {e}")
        result['errors'].append(str(e))
        return result

# Вспомогательные функции

async def _update_task_status(task_id: int, status: str, message: str = None):
    """Обновление статуса задачи в базе данных"""
    try:
        async with get_async_session() as session:
            task = await session.get(DownloadTask, task_id)
            if task:
                task.status = status
                if message:
                    task.progress_message = message
                task.updated_at = datetime.utcnow()
                
                await session.commit()
                
    except Exception as e:
        logger.error(f"Failed to update task status: {e}")

async def _update_task_completion(
    task_id: int,
    cdn_url: str = None,
    direct_url: str = None,
    thumbnail_url: str = None,
    file_size: int = 0,
    video_info: dict = None
):
    """Обновление завершенной задачи"""
    try:
        async with get_async_session() as session:
            task = await session.get(DownloadTask, task_id)
            if task:
                task.status = 'completed'
                task.cdn_url = cdn_url
                task.direct_url = direct_url
                task.thumbnail_url = thumbnail_url
                task.file_size = file_size
                task.completed_at = datetime.utcnow()
                
                if video_info:
                    task.title = video_info.get('title')
                    task.duration = video_info.get('duration')
                    task.format = video_info.get('format')
                
                await session.commit()
                
    except Exception as e:
        logger.error(f"Failed to update task completion: {e}")

async def _update_batch_status(batch_id: int, status: str, message: str = None):
    """Обновление статуса пакетной задачи"""
    try:
        async with get_async_session() as session:
            from shared.models.download_batch import DownloadBatch
            
            batch = await session.get(DownloadBatch, batch_id)
            if batch:
                batch.status = status
                if message:
                    batch.progress_message = message
                batch.updated_at = datetime.utcnow()
                
                await session.commit()
                
    except Exception as e:
        logger.error(f"Failed to update batch status: {e}")

async def _update_batch_completion(
    batch_id: int,
    archive_url: str = None,
    completed_count: int = 0,
    failed_count: int = 0
):
    """Обновление завершенного пакета"""
    try:
        async with get_async_session() as session:
            from shared.models.download_batch import DownloadBatch
            
            batch = await session.get(DownloadBatch, batch_id)
            if batch:
                batch.archive_url = archive_url
                batch.completed_count = completed_count
                batch.failed_count = failed_count
                batch.completed_at = datetime.utcnow()
                
                if completed_count > 0:
                    batch.status = 'completed'
                else:
                    batch.status = 'failed'
                
                await session.commit()
                
    except Exception as e:
        logger.error(f"Failed to update batch completion: {e}")

async def _cleanup_local_files(file_paths: List[str]):
    """Очистка локальных файлов"""
    try:
        for file_path in file_paths:
            try:
                import os
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"Cleaned up local file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {file_path}: {e}")
                
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

def _detect_platform(url: str) -> str:
    """Определение платформы по URL"""
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    elif 'tiktok.com' in url:
        return 'tiktok'
    elif 'instagram.com' in url:
        return 'instagram'
    else:
        return 'unknown'

# Периодические задачи

@celery_app.task(name='periodic_cleanup')
def periodic_cleanup():
    """Периодическая очистка файлов (запускается по расписанию)"""
    return cleanup_old_files_task.delay(max_age_hours=24)

@celery_app.task(name='periodic_migration')
def periodic_migration():
    """Периодическая миграция файлов в CDN"""
    return migrate_files_to_cdn_task.delay(limit=50)

@celery_app.task(name='cdn_health_check')
async def cdn_health_check():
    """Проверка здоровья CDN"""
    try:
        if await is_cdn_available():
            from worker.integrations.cdn_upload import cdn_integration
            stats = await cdn_integration.get_cdn_stats()
            
            logger.info("CDN health check completed", stats=stats)
            return {"status": "healthy", "stats": stats}
        else:
            logger.warning("CDN is not available")
            return {"status": "unavailable"}
            
    except Exception as e:
        logger.error(f"CDN health check failed: {e}")
        return {"status": "error", "error": str(e)}