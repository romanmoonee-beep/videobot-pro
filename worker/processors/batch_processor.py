"""
VideoBot Pro - Batch Processor
Обработчик групповых операций над видео
"""

import os
import asyncio
import tempfile
import zipfile
import structlog
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime

from .base import BaseProcessor
from .video_processor import VideoProcessor
from .thumbnail_generator import ThumbnailGenerator
from .quality_optimizer import QualityOptimizer
from ..utils.progress_tracker import ProgressTracker
from ..utils.file_manager import FileManager

logger = structlog.get_logger(__name__)

class BatchProcessor(BaseProcessor):
    """Процессор для обработки множественных файлов"""
    
    def __init__(self, storage_handler=None):
        """
        Инициализация batch процессора
        
        Args:
            storage_handler: Обработчик хранилища для загрузки файлов
        """
        super().__init__()
        self.storage_handler = storage_handler
        self.video_processor = VideoProcessor()
        self.thumbnail_generator = ThumbnailGenerator(storage_handler)
        self.quality_optimizer = QualityOptimizer()
        self.file_manager = FileManager()
        self.progress_tracker = ProgressTracker()
        
        # Настройки параллельной обработки
        self.max_concurrent_downloads = 3
        self.max_concurrent_processing = 2
        
        # Настройки архивирования
        self.archive_compression_level = 6  # Баланс скорость/размер
        self.max_archive_size_mb = 2048     # Максимальный размер архива
    
    async def process_batch(self, batch_data: Dict[str, Any], 
                          output_dir: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обрабатывает batch загрузок
        
        Args:
            batch_data: Данные batch'а с URL и метаданными
            output_dir: Директория для сохранения результатов
            settings: Настройки обработки
            
        Returns:
            Результаты обработки batch'а
        """
        try:
            batch_id = batch_data.get('batch_id', 'unknown')
            urls = batch_data.get('urls', [])
            
            logger.info(f"Starting batch processing", batch_id=batch_id, urls_count=len(urls))
            
            # Создаем рабочие директории
            temp_dir = tempfile.mkdtemp(prefix=f"batch_{batch_id}_")
            downloads_dir = os.path.join(temp_dir, "downloads")
            processed_dir = os.path.join(temp_dir, "processed")
            thumbnails_dir = os.path.join(temp_dir, "thumbnails")
            
            for dir_path in [downloads_dir, processed_dir, thumbnails_dir]:
                os.makedirs(dir_path, exist_ok=True)
            
            # Инициализируем трекер прогресса
            total_steps = len(urls) * 3  # Скачивание, обработка, загрузка
            self.progress_tracker.start(batch_id, total_steps)
            
            # Результаты обработки
            results = {
                'batch_id': batch_id,
                'total_urls': len(urls),
                'successful': 0,
                'failed': 0,
                'files': [],
                'errors': [],
                'total_size_mb': 0,
                'processing_time_seconds': 0,
                'archive_created': False,
                'archive_path': None
            }
            
            start_time = datetime.now()
            
            # Этап 1: Параллельное скачивание файлов
            download_results = await self._download_batch_files(
                urls, downloads_dir, batch_id, settings
            )
            
            # Этап 2: Обработка скачанных файлов
            processing_results = await self._process_downloaded_files(
                download_results, processed_dir, thumbnails_dir, settings
            )
            
            # Этап 3: Создание архива если нужно
            if settings.get('create_archive', False) and processing_results['successful_files']:
                archive_result = await self._create_archive(
                    processing_results['successful_files'], 
                    thumbnails_dir, 
                    output_dir, 
                    batch_id
                )
                results.update(archive_result)
            
            # Этап 4: Загрузка в хранилище
            if self.storage_handler:
                upload_results = await self._upload_batch_files(
                    processing_results['successful_files'], batch_id
                )
                results['upload_results'] = upload_results
            
            # Компилируем финальные результаты
            results.update({
                'successful': processing_results['successful_count'],
                'failed': processing_results['failed_count'],
                'files': processing_results['successful_files'],
                'errors': processing_results['errors'],
                'total_size_mb': processing_results['total_size_mb'],
                'processing_time_seconds': (datetime.now() - start_time).total_seconds()
            })
            
            # Очищаем временные файлы
            await self._cleanup_temp_directory(temp_dir)
            
            self.progress_tracker.complete(batch_id)
            
            logger.info(f"Batch processing completed", 
                       batch_id=batch_id, 
                       successful=results['successful'],
                       failed=results['failed'])
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch processing: {e}", batch_id=batch_id)
            if 'batch_id' in locals():
                self.progress_tracker.fail(batch_id, str(e))
            raise
    
    async def _download_batch_files(self, urls: List[str], downloads_dir: str,
                                  batch_id: str, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Параллельное скачивание файлов"""
        try:
            # Создаем семафор для ограничения параллельных загрузок
            semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
            
            async def download_single_file(url_data, index):
                async with semaphore:
                    try:
                        url = url_data if isinstance(url_data, str) else url_data.get('url')
                        
                        # Используем video_processor для скачивания
                        download_result = await self.video_processor.download_video(
                            url, downloads_dir, settings
                        )
                        
                        if download_result.get('success'):
                            self.progress_tracker.update(batch_id, f"Downloaded {index+1}")
                            return {
                                'index': index,
                                'url': url,
                                'success': True,
                                'file_path': download_result['file_path'],
                                'metadata': download_result.get('metadata', {}),
                                'file_size_mb': download_result.get('file_size_mb', 0)
                            }
                        else:
                            return {
                                'index': index,
                                'url': url,
                                'success': False,
                                'error': download_result.get('error', 'Unknown download error')
                            }
                    
                    except Exception as e:
                        return {
                            'index': index,
                            'url': url_data,
                            'success': False,
                            'error': str(e)
                        }
            
            # Запускаем параллельные загрузки
            download_tasks = [
                download_single_file(url, i) for i, url in enumerate(urls)
            ]
            
            download_results = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            # Обрабатываем исключения
            processed_results = []
            for result in download_results:
                if isinstance(result, Exception):
                    processed_results.append({
                        'success': False,
                        'error': str(result)
                    })
                else:
                    processed_results.append(result)
            
            successful_downloads = [r for r in processed_results if r.get('success')]
            failed_downloads = [r for r in processed_results if not r.get('success')]
            
            logger.info(f"Downloads completed", 
                       batch_id=batch_id,
                       successful=len(successful_downloads),
                       failed=len(failed_downloads))
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Error in batch download: {e}")
            return []
    
    async def _process_downloaded_files(self, download_results: List[Dict[str, Any]],
                                      processed_dir: str, thumbnails_dir: str,
                                      settings: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка скачанных файлов"""
        try:
            successful_files = []
            errors = []
            total_size_mb = 0
            
            # Фильтруем успешные загрузки
            successful_downloads = [r for r in download_results if r.get('success')]
            
            # Создаем семафор для ограничения параллельной обработки
            semaphore = asyncio.Semaphore(self.max_concurrent_processing)
            
            async def process_single_file(download_result):
                async with semaphore:
                    try:
                        file_path = download_result['file_path']
                        index = download_result['index']
                        
                        if not os.path.exists(file_path):
                            return {
                                'success': False,
                                'error': f'Downloaded file not found: {file_path}'
                            }
                        
                        # Генерируем имя выходного файла
                        base_name = Path(file_path).stem
                        output_path = os.path.join(processed_dir, f"{base_name}_processed.mp4")
                        
                        # Оптимизируем качество если нужно
                        if settings.get('optimize_quality', True):
                            optimization_result = await self.quality_optimizer.optimize_video(
                                file_path, 
                                output_path,
                                target_quality=settings.get('quality', 'auto'),
                                user_type=settings.get('user_type', 'free'),
                                mobile_optimized=settings.get('mobile_optimized', False)
                            )
                            
                            if not optimization_result.get('success', True):
                                # Если оптимизация не удалась, используем оригинальный файл
                                import shutil
                                shutil.copy2(file_path, output_path)
                        else:
                            # Просто копируем без оптимизации
                            import shutil
                            shutil.copy2(file_path, output_path)
                        
                        # Генерируем превью если нужно
                        thumbnails = {}
                        if settings.get('generate_thumbnails', True):
                            try:
                                thumbnail_subdir = os.path.join(thumbnails_dir, f"video_{index}")
                                os.makedirs(thumbnail_subdir, exist_ok=True)
                                
                                thumbnails = await self.thumbnail_generator.generate_thumbnails(
                                    output_path, 
                                    thumbnail_subdir,
                                    sizes=['medium', 'small']
                                )
                            except Exception as e:
                                logger.warning(f"Thumbnail generation failed: {e}")
                        
                        # Получаем информацию о файле
                        file_info = await self._get_file_info(output_path)
                        
                        return {
                            'success': True,
                            'index': index,
                            'original_url': download_result['url'],
                            'file_path': output_path,
                            'file_name': os.path.basename(output_path),
                            'file_size_mb': file_info.get('size_mb', 0),
                            'duration_seconds': file_info.get('duration', 0),
                            'thumbnails': thumbnails,
                            'metadata': download_result.get('metadata', {}),
                            'processing_info': file_info
                        }
                        
                    except Exception as e:
                        logger.error(f"Error processing file {download_result.get('url', 'unknown')}: {e}")
                        return {
                            'success': False,
                            'error': str(e),
                            'url': download_result.get('url', 'unknown')
                        }
            
            # Обрабатываем файлы параллельно
            processing_tasks = [
                process_single_file(download_result) 
                for download_result in successful_downloads
            ]
            
            processing_results = await asyncio.gather(*processing_tasks, return_exceptions=True)
            
            # Разделяем успешные и неудачные результаты
            for result in processing_results:
                if isinstance(result, Exception):
                    errors.append({
                        'error': str(result),
                        'stage': 'processing'
                    })
                elif result.get('success'):
                    successful_files.append(result)
                    total_size_mb += result.get('file_size_mb', 0)
                else:
                    errors.append(result)
            
            # Добавляем ошибки скачивания
            for download_result in download_results:
                if not download_result.get('success'):
                    errors.append({
                        'url': download_result.get('url', 'unknown'),
                        'error': download_result.get('error', 'Download failed'),
                        'stage': 'download'
                    })
            
            return {
                'successful_files': successful_files,
                'successful_count': len(successful_files),
                'failed_count': len(errors),
                'errors': errors,
                'total_size_mb': total_size_mb
            }
            
        except Exception as e:
            logger.error(f"Error in file processing: {e}")
            return {
                'successful_files': [],
                'successful_count': 0,
                'failed_count': len(download_results),
                'errors': [{'error': str(e), 'stage': 'processing'}],
                'total_size_mb': 0
            }
    
    async def _create_archive(self, files: List[Dict[str, Any]], thumbnails_dir: str,
                            output_dir: str, batch_id: str) -> Dict[str, Any]:
        """Создает ZIP архив с обработанными файлами"""
        try:
            archive_name = f"batch_{batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            archive_path = os.path.join(output_dir, archive_name)
            
            # Проверяем общий размер файлов
            total_size_mb = sum(f.get('file_size_mb', 0) for f in files)
            if total_size_mb > self.max_archive_size_mb:
                return {
                    'archive_created': False,
                    'error': f'Total size {total_size_mb:.1f}MB exceeds limit {self.max_archive_size_mb}MB'
                }
            
            # Создаем архив в отдельном потоке для неблокирующего выполнения
            def create_zip_archive():
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, 
                                   compresslevel=self.archive_compression_level) as zipf:
                    
                    # Добавляем видеофайлы
                    for file_info in files:
                        file_path = file_info['file_path']
                        if os.path.exists(file_path):
                            # Используем читаемое имя в архиве
                            archive_filename = self._get_archive_filename(file_info)
                            zipf.write(file_path, archive_filename)
                    
                    # Добавляем превью
                    for file_info in files:
                        thumbnails = file_info.get('thumbnails', {})
                        for size, thumbnail_path in thumbnails.items():
                            if os.path.exists(thumbnail_path):
                                base_name = Path(file_info['file_name']).stem
                                thumb_name = f"thumbnails/{base_name}_{size}.jpg"
                                zipf.write(thumbnail_path, thumb_name)
                    
                    # Добавляем метаданные
                    metadata = {
                        'batch_id': batch_id,
                        'created_at': datetime.now().isoformat(),
                        'files_count': len(files),
                        'total_size_mb': total_size_mb,
                        'files': [
                            {
                                'name': self._get_archive_filename(f),
                                'original_url': f.get('original_url'),
                                'duration_seconds': f.get('duration_seconds'),
                                'file_size_mb': f.get('file_size_mb')
                            }
                            for f in files
                        ]
                    }
                    
                    zipf.writestr('metadata.json', json.dumps(metadata, indent=2))
                
                return os.path.getsize(archive_path)
            
            # Выполняем в executor для неблокирующего создания архива
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                archive_size = await loop.run_in_executor(executor, create_zip_archive)
            
            if os.path.exists(archive_path):
                logger.info(f"Archive created", 
                           batch_id=batch_id, 
                           archive_path=archive_path,
                           size_mb=archive_size / (1024 * 1024))
                
                return {
                    'archive_created': True,
                    'archive_path': archive_path,
                    'archive_size_mb': archive_size / (1024 * 1024),
                    'compression_ratio': self._calculate_compression_ratio(total_size_mb * 1024 * 1024, archive_size)
                }
            else:
                return {
                    'archive_created': False,
                    'error': 'Archive file was not created'
                }
                
        except Exception as e:
            logger.error(f"Error creating archive: {e}")
            return {
                'archive_created': False,
                'error': str(e)
            }
    
    def _get_archive_filename(self, file_info: Dict[str, Any]) -> str:
        """Генерирует читаемое имя файла для архива"""
        try:
            metadata = file_info.get('metadata', {})
            title = metadata.get('title', '')
            
            if title:
                # Очищаем название от недопустимых символов
                import re
                clean_title = re.sub(r'[<>:"/\\|?*]', '_', title)
                clean_title = clean_title[:50]  # Ограничиваем длину
                
                # Добавляем индекс если есть
                index = file_info.get('index')
                if index is not None:
                    return f"{index+1:02d}_{clean_title}.mp4"
                else:
                    return f"{clean_title}.mp4"
            else:
                # Используем оригинальное имя файла
                return file_info.get('file_name', f"video_{file_info.get('index', 0)}.mp4")
                
        except Exception as e:
            logger.warning(f"Error generating archive filename: {e}")
            return file_info.get('file_name', 'video.mp4')
    
    async def _upload_batch_files(self, files: List[Dict[str, Any]], 
                                batch_id: str) -> Dict[str, Any]:
        """Загружает обработанные файлы в хранилище"""
        try:
            if not self.storage_handler:
                return {'uploaded': False, 'reason': 'no_storage_handler'}
            
            uploaded_files = []
            upload_errors = []
            
            for file_info in files:
                try:
                    file_path = file_info['file_path']
                    if not os.path.exists(file_path):
                        continue
                    
                    # Генерируем путь в хранилище
                    storage_filename = f"batches/{batch_id}/{file_info['file_name']}"
                    
                    # Загружаем файл
                    upload_url = await self.storage_handler.upload_file(
                        file_path, storage_filename, content_type='video/mp4'
                    )
                    
                    if upload_url:
                        uploaded_files.append({
                            'original_filename': file_info['file_name'],
                            'storage_url': upload_url,
                            'storage_path': storage_filename,
                            'file_size_mb': file_info.get('file_size_mb', 0)
                        })
                    
                    # Загружаем превью
                    thumbnails = file_info.get('thumbnails', {})
                    for size, thumbnail_path in thumbnails.items():
                        if os.path.exists(thumbnail_path):
                            thumb_storage_path = f"batches/{batch_id}/thumbnails/{Path(file_info['file_name']).stem}_{size}.jpg"
                            thumb_url = await self.storage_handler.upload_file(
                                thumbnail_path, thumb_storage_path, content_type='image/jpeg'
                            )
                            
                            if thumb_url:
                                uploaded_files[-1].setdefault('thumbnails', {})[size] = thumb_url
                
                except Exception as e:
                    upload_errors.append({
                        'file': file_info.get('file_name', 'unknown'),
                        'error': str(e)
                    })
            
            return {
                'uploaded': True,
                'uploaded_files': uploaded_files,
                'successful_uploads': len(uploaded_files),
                'upload_errors': upload_errors,
                'error_count': len(upload_errors)
            }
            
        except Exception as e:
            logger.error(f"Error uploading batch files: {e}")
            return {
                'uploaded': False,
                'error': str(e)
            }
    
    async def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Получает информацию о файле"""
        try:
            if not os.path.exists(file_path):
                return {}
            
            file_size = os.path.getsize(file_path)
            
            # Получаем информацию о видео
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', file_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            info = {
                'size_mb': file_size / (1024 * 1024),
                'size_bytes': file_size
            }
            
            if process.returncode == 0:
                try:
                    probe_data = json.loads(stdout.decode())
                    format_info = probe_data.get('format', {})
                    
                    info.update({
                        'duration': float(format_info.get('duration', 0)),
                        'bitrate': int(format_info.get('bit_rate', 0)),
                        'format': format_info.get('format_name', '')
                    })
                    
                    # Ищем видео поток
                    for stream in probe_data.get('streams', []):
                        if stream.get('codec_type') == 'video':
                            info.update({
                                'width': int(stream.get('width', 0)),
                                'height': int(stream.get('height', 0)),
                                'codec': stream.get('codec_name', ''),
                                'fps': self._parse_fps(stream.get('r_frame_rate', '0/1'))
                            })
                            break
                except:
                    pass
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            return {'size_mb': 0, 'size_bytes': 0}
    
    def _parse_fps(self, fps_str: str) -> float:
        """Парсит FPS из строки вида '30/1'"""
        try:
            if '/' in fps_str:
                numerator, denominator = fps_str.split('/')
                return float(numerator) / float(denominator)
            return float(fps_str)
        except:
            return 0.0
    
    def _calculate_compression_ratio(self, original_size: int, compressed_size: int) -> float:
        """Рассчитывает коэффициент сжатия архива"""
        if original_size == 0:
            return 0.0
        return ((original_size - compressed_size) / original_size) * 100
    
    async def _cleanup_temp_directory(self, temp_dir: str):
        """Очищает временную директорию"""
        try:
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Error cleaning up temp directory: {e}")
    
    async def get_batch_progress(self, batch_id: str) -> Dict[str, Any]:
        """Получает прогресс обработки batch'а"""
        return self.progress_tracker.get_progress(batch_id)
    
    async def cancel_batch(self, batch_id: str) -> bool:
        """Отменяет обработку batch'а"""
        try:
            # Помечаем как отмененный в трекере прогресса
            self.progress_tracker.cancel(batch_id)
            
            # TODO: Здесь можно добавить логику отмены активных задач
            # Например, отмена загрузок или обработки файлов
            
            return True
        except Exception as e:
            logger.error(f"Error canceling batch: {e}")
            return False
    
    async def estimate_batch_processing_time(self, urls: List[str], 
                                           settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Оценивает время обработки batch'а
        
        Args:
            urls: Список URL для обработки
            settings: Настройки обработки
            
        Returns:
            Оценка времени и ресурсов
        """
        try:
            # Базовые оценки времени на операцию (в секундах)
            base_times = {
                'download_per_minute': 20,    # 20 секунд на минуту видео
                'processing_per_minute': 30,  # 30 секунд на минуту видео
                'thumbnail_per_file': 5,      # 5 секунд на файл
                'upload_per_mb': 1           # 1 секунда на МБ
            }
            
            # Коэффициенты в зависимости от качества
            quality_factors = {
                '360p': 0.7,
                '480p': 0.8,
                '720p': 1.0,
                '1080p': 1.3,
                '1440p': 1.8,
                '2160p': 2.5
            }
            
            quality = settings.get('quality', '720p')
            quality_factor = quality_factors.get(quality, 1.0)
            
            # Оценка для среднего видео (предполагаем 3 минуты)
            avg_duration_minutes = 3
            avg_file_size_mb = 50
            
            total_files = len(urls)
            
            # Расчет времени
            download_time = total_files * avg_duration_minutes * base_times['download_per_minute']
            processing_time = total_files * avg_duration_minutes * base_times['processing_per_minute'] * quality_factor
            thumbnail_time = total_files * base_times['thumbnail_per_file'] if settings.get('generate_thumbnails') else 0
            upload_time = total_files * avg_file_size_mb * base_times['upload_per_mb'] if self.storage_handler else 0
            
            # Учитываем параллелизм
            download_time /= self.max_concurrent_downloads
            processing_time /= self.max_concurrent_processing
            
            total_time = download_time + processing_time + thumbnail_time + upload_time
            
            # Добавляем запас на непредвиденные задержки (20%)
            total_time *= 1.2
            
            return {
                'estimated_total_seconds': int(total_time),
                'estimated_total_minutes': int(total_time / 60),
                'breakdown': {
                    'download_seconds': int(download_time),
                    'processing_seconds': int(processing_time),
                    'thumbnail_seconds': int(thumbnail_time),
                    'upload_seconds': int(upload_time)
                },
                'estimated_output_size_mb': total_files * avg_file_size_mb * quality_factor,
                'parallel_downloads': self.max_concurrent_downloads,
                'parallel_processing': self.max_concurrent_processing
            }
            
        except Exception as e:
            logger.error(f"Error estimating batch processing time: {e}")
            return {
                'estimated_total_seconds': 0,
                'error': str(e)
            }