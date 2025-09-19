"""
VideoBot Pro - Thumbnail Generator
Генерация превью изображений для видео
"""

import os
import tempfile
import subprocess
import structlog
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import asyncio
import aiofiles
import aiohttp

from .base import BaseProcessor
from ..utils.file_manager import FileManager

logger = structlog.get_logger(__name__)

class ThumbnailGenerator(BaseProcessor):
    """Генератор превью изображений для видео"""
    
    def __init__(self, storage_handler=None):
        """
        Инициализация генератора превью
        
        Args:
            storage_handler: Обработчик хранилища для загрузки превью
        """
        super().__init__()
        self.storage_handler = storage_handler
        self.file_manager = FileManager()
        
        # Настройки превью
        self.thumbnail_sizes = {
            'small': (320, 180),    # 16:9 small
            'medium': (640, 360),   # 16:9 medium  
            'large': (1280, 720),   # 16:9 large
            'square': (300, 300),   # Квадратное для соц. сетей
        }
        
        # Параметры извлечения кадров
        self.frame_positions = [0.1, 0.3, 0.5, 0.7, 0.9]  # Позиции в процентах
        
    async def generate_thumbnails(self, video_path: str, output_dir: str = None,
                                sizes: List[str] = None) -> Dict[str, str]:
        """
        Генерирует превью для видео
        
        Args:
            video_path: Путь к видеофайлу
            output_dir: Директория для сохранения превью
            sizes: Список размеров для генерации
            
        Returns:
            Словарь с путями к превью {size: path}
        """
        try:
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            if output_dir is None:
                output_dir = tempfile.mkdtemp(prefix="thumbnails_")
            
            os.makedirs(output_dir, exist_ok=True)
            
            if sizes is None:
                sizes = ['medium']  # По умолчанию средний размер
            
            # Получаем информацию о видео
            video_info = await self._get_video_info(video_path)
            if not video_info:
                raise ValueError("Could not extract video information")
            
            thumbnails = {}
            
            # Генерируем превью для каждого размера
            for size in sizes:
                if size not in self.thumbnail_sizes:
                    logger.warning(f"Unknown thumbnail size: {size}")
                    continue
                
                thumbnail_path = await self._generate_single_thumbnail(
                    video_path, output_dir, size, video_info
                )
                
                if thumbnail_path:
                    thumbnails[size] = thumbnail_path
            
            logger.info(f"Generated {len(thumbnails)} thumbnails", 
                       video_path=video_path, sizes=list(thumbnails.keys()))
            
            return thumbnails
            
        except Exception as e:
            logger.error(f"Error generating thumbnails: {e}", video_path=video_path)
            raise
    
    async def _generate_single_thumbnail(self, video_path: str, output_dir: str,
                                       size: str, video_info: Dict[str, Any]) -> Optional[str]:
        """Генерирует одно превью указанного размера"""
        try:
            width, height = self.thumbnail_sizes[size]
            duration = video_info.get('duration', 0)
            
            # Выбираем лучшую позицию для кадра (середина видео)
            timestamp = duration * 0.5 if duration > 0 else 0
            
            # Имя выходного файла
            output_filename = f"thumbnail_{size}_{int(timestamp)}s.jpg"
            output_path = os.path.join(output_dir, output_filename)
            
            # Извлекаем кадр с помощью ffmpeg
            success = await self._extract_frame_ffmpeg(
                video_path, output_path, timestamp, width, height
            )
            
            if success and os.path.exists(output_path):
                # Применяем постобработку
                await self._post_process_thumbnail(output_path, size)
                return output_path
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating single thumbnail: {e}", size=size)
            return None
    
    async def _extract_frame_ffmpeg(self, video_path: str, output_path: str,
                                  timestamp: float, width: int, height: int) -> bool:
        """Извлекает кадр из видео с помощью ffmpeg"""
        try:
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', str(timestamp),
                '-vframes', '1',
                '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                '-q:v', '2',  # Высокое качество
                '-y',  # Перезаписать файл
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return True
            else:
                logger.error(f"ffmpeg error: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Error extracting frame: {e}")
            return False
    
    async def _post_process_thumbnail(self, thumbnail_path: str, size: str):
        """Постобработка превью (улучшение качества, водяные знаки)"""
        try:
            with Image.open(thumbnail_path) as img:
                # Улучшение контраста и резкости
                from PIL import ImageEnhance
                
                # Увеличиваем контраст
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.1)
                
                # Увеличиваем резкость
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(1.1)
                
                # Добавляем водяной знак (опционально)
                if size in ['large', 'medium']:
                    img = await self._add_watermark(img)
                
                # Сохраняем с оптимизацией
                img.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
                
        except Exception as e:
            logger.error(f"Error post-processing thumbnail: {e}")
    
    async def _add_watermark(self, img: Image.Image) -> Image.Image:
        """Добавляет водяной знак на превью"""
        try:
            # Создаем копию для редактирования
            watermarked = img.copy()
            
            # Создаем прозрачный слой для водяного знака
            overlay = Image.new('RGBA', watermarked.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            
            # Настройки водяного знака
            watermark_text = "VideoBot Pro"
            
            try:
                # Пытаемся загрузить системный шрифт
                font_size = max(12, min(watermarked.size) // 40)
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except:
                # Используем стандартный шрифт если системный недоступен
                font = ImageFont.load_default()
            
            # Получаем размеры текста
            bbox = draw.textbbox((0, 0), watermark_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            
            # Позиционируем в правом нижнем углу
            x = watermarked.size[0] - text_width - 10
            y = watermarked.size[1] - text_height - 10
            
            # Рисуем полупрозрачный фон
            padding = 5
            draw.rectangle([
                x - padding, y - padding,
                x + text_width + padding, y + text_height + padding
            ], fill=(0, 0, 0, 128))
            
            # Рисуем текст
            draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, 200))
            
            # Накладываем водяной знак
            watermarked = Image.alpha_composite(watermarked.convert('RGBA'), overlay)
            return watermarked.convert('RGB')
            
        except Exception as e:
            logger.error(f"Error adding watermark: {e}")
            return img
    
    async def generate_multiple_frames(self, video_path: str, output_dir: str,
                                     count: int = 5) -> List[str]:
        """
        Генерирует несколько кадров из разных частей видео
        
        Args:
            video_path: Путь к видеофайлу
            output_dir: Директория для сохранения
            count: Количество кадров
            
        Returns:
            Список путей к сгенерированным кадрам
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            video_info = await self._get_video_info(video_path)
            duration = video_info.get('duration', 0)
            
            if duration <= 0:
                raise ValueError("Invalid video duration")
            
            frames = []
            width, height = self.thumbnail_sizes['medium']
            
            # Генерируем кадры в равномерно распределенных позициях
            for i in range(count):
                position = (i + 1) / (count + 1)  # Избегаем самого начала и конца
                timestamp = duration * position
                
                output_filename = f"frame_{i+1:02d}_{int(timestamp)}s.jpg"
                output_path = os.path.join(output_dir, output_filename)
                
                success = await self._extract_frame_ffmpeg(
                    video_path, output_path, timestamp, width, height
                )
                
                if success and os.path.exists(output_path):
                    frames.append(output_path)
            
            logger.info(f"Generated {len(frames)} frames from video", 
                       video_path=video_path)
            
            return frames
            
        except Exception as e:
            logger.error(f"Error generating multiple frames: {e}")
            return []
    
    async def create_preview_grid(self, frame_paths: List[str], output_path: str,
                                grid_size: Tuple[int, int] = (2, 3)) -> bool:
        """
        Создает сетку превью из нескольких кадров
        
        Args:
            frame_paths: Пути к кадрам
            output_path: Путь для сохранения сетки
            grid_size: Размер сетки (столбцы, строки)
            
        Returns:
            True если сетка создана успешно
        """
        try:
            cols, rows = grid_size
            total_cells = cols * rows
            
            if len(frame_paths) < total_cells:
                logger.warning(f"Not enough frames for grid: {len(frame_paths)} < {total_cells}")
                return False
            
            # Загружаем изображения
            images = []
            for frame_path in frame_paths[:total_cells]:
                try:
                    img = Image.open(frame_path)
                    images.append(img)
                except Exception as e:
                    logger.error(f"Error loading frame: {e}", frame_path=frame_path)
                    continue
            
            if not images:
                return False
            
            # Определяем размер каждой ячейки
            cell_width = 320
            cell_height = 180
            
            # Создаем сетку
            grid_width = cols * cell_width
            grid_height = rows * cell_height
            grid_image = Image.new('RGB', (grid_width, grid_height), (0, 0, 0))
            
            # Размещаем изображения в сетке
            for i, img in enumerate(images):
                if i >= total_cells:
                    break
                
                # Изменяем размер изображения
                img_resized = img.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
                
                # Вычисляем позицию в сетке
                col = i % cols
                row = i // cols
                x = col * cell_width
                y = row * cell_height
                
                # Вставляем в сетку
                grid_image.paste(img_resized, (x, y))
            
            # Добавляем рамки между ячейками
            draw = ImageDraw.Draw(grid_image)
            for i in range(1, cols):
                x = i * cell_width
                draw.line([(x, 0), (x, grid_height)], fill=(255, 255, 255), width=2)
            for i in range(1, rows):
                y = i * cell_height
                draw.line([(0, y), (grid_width, y)], fill=(255, 255, 255), width=2)
            
            # Сохраняем сетку
            grid_image.save(output_path, 'JPEG', quality=90, optimize=True)
            
            # Закрываем изображения
            for img in images:
                img.close()
            
            logger.info(f"Created preview grid", output_path=output_path)
            return True
            
        except Exception as e:
            logger.error(f"Error creating preview grid: {e}")
            return False
    
    async def extract_animated_gif(self, video_path: str, output_path: str,
                                 duration: float = 3.0, fps: int = 10,
                                 start_time: float = None) -> bool:
        """
        Создает анимированный GIF из части видео
        
        Args:
            video_path: Путь к видеофайлу
            output_path: Путь для сохранения GIF
            duration: Длительность GIF в секундах
            fps: Количество кадров в секунду
            start_time: Время начала (если None, то середина видео)
            
        Returns:
            True если GIF создан успешно
        """
        try:
            video_info = await self._get_video_info(video_path)
            video_duration = video_info.get('duration', 0)
            
            if start_time is None:
                # Начинаем с середины видео
                start_time = max(0, (video_duration - duration) / 2)
            
            # Ограничиваем размер для GIF
            max_width = 480
            max_height = 270
            
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', str(start_time),
                '-t', str(duration),
                '-vf', f'fps={fps},scale={max_width}:{max_height}:force_original_aspect_ratio=decrease',
                '-loop', '0',  # Бесконечный цикл
                '-y',  # Перезаписать файл
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(output_path):
                logger.info(f"Created animated GIF", output_path=output_path)
                return True
            else:
                logger.error(f"ffmpeg error creating GIF: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating animated GIF: {e}")
            return False
    
    async def upload_thumbnails(self, thumbnail_paths: Dict[str, str]) -> Dict[str, str]:
        """
        Загружает превью в облачное хранилище
        
        Args:
            thumbnail_paths: Словарь {size: local_path}
            
        Returns:
            Словарь {size: remote_url}
        """
        if not self.storage_handler:
            logger.warning("No storage handler configured for thumbnail upload")
            return {}
        
        try:
            uploaded_urls = {}
            
            for size, local_path in thumbnail_paths.items():
                if not os.path.exists(local_path):
                    continue
                
                # Генерируем имя файла для хранилища
                filename = f"thumbnails/{size}/{os.path.basename(local_path)}"
                
                # Загружаем в хранилище
                remote_url = await self.storage_handler.upload_file(
                    local_path, filename, content_type='image/jpeg'
                )
                
                if remote_url:
                    uploaded_urls[size] = remote_url
                    logger.info(f"Uploaded thumbnail", size=size, url=remote_url)
            
            return uploaded_urls
            
        except Exception as e:
            logger.error(f"Error uploading thumbnails: {e}")
            return {}
    
    async def cleanup_temp_files(self, paths: List[str]):
        """Очищает временные файлы"""
        for path in paths:
            try:
                if os.path.exists(path):
                    if os.path.isfile(path):
                        os.remove(path)
                    elif os.path.isdir(path):
                        import shutil
                        shutil.rmtree(path)
            except Exception as e:
                logger.error(f"Error cleaning up temp file: {e}", path=path)
    
    async def _get_video_info(self, video_path: str) -> Dict[str, Any]:
        """Получает информацию о видео с помощью ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                video_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                import json
                info = json.loads(stdout.decode())
                
                # Извлекаем основную информацию
                format_info = info.get('format', {})
                duration = float(format_info.get('duration', 0))
                
                # Ищем видео поток
                video_stream = None
                for stream in info.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        video_stream = stream
                        break
                
                video_info = {
                    'duration': duration,
                    'format': format_info.get('format_name'),
                    'size': int(format_info.get('size', 0)),
                }
                
                if video_stream:
                    video_info.update({
                        'width': video_stream.get('width'),
                        'height': video_stream.get('height'),
                        'fps': eval(video_stream.get('r_frame_rate', '0/1')),
                        'codec': video_stream.get('codec_name'),
                    })
                
                return video_info
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return {}