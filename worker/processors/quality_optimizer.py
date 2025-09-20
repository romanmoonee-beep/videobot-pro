"""
VideoBot Pro - Quality Optimizer
Оптимизация качества видео и аудио
"""

import os
import re
import tempfile
import asyncio
import structlog
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import json
import math

from .base import BaseProcessor
from ..utils.quality_selector import QualitySelector

logger = structlog.get_logger(__name__)

class QualityOptimizer(BaseProcessor):
    """Оптимизатор качества видео"""
    
    def __init__(self):
        """Инициализация оптимизатора"""
        super().__init__()
        self.quality_selector = QualitySelector()
        
        # Предустановки качества
        self.quality_presets = {
            '2160p': {
                'resolution': (3840, 2160),
                'video_bitrate': '15M',
                'audio_bitrate': '192k',
                'crf': 22,
                'preset': 'medium'
            },
            '1440p': {
                'resolution': (2560, 1440),
                'video_bitrate': '10M',
                'audio_bitrate': '192k',
                'crf': 23,
                'preset': 'medium'
            },
            '1080p': {
                'resolution': (1920, 1080),
                'video_bitrate': '6M',
                'audio_bitrate': '128k',
                'crf': 23,
                'preset': 'medium'
            },
            '720p': {
                'resolution': (1280, 720),
                'video_bitrate': '3M',
                'audio_bitrate': '128k',
                'crf': 24,
                'preset': 'medium'
            },
            '480p': {
                'resolution': (854, 480),
                'video_bitrate': '1.5M',
                'audio_bitrate': '96k',
                'crf': 25,
                'preset': 'fast'
            },
            '360p': {
                'resolution': (640, 360),
                'video_bitrate': '800k',
                'audio_bitrate': '96k',
                'crf': 26,
                'preset': 'fast'
            }
        }
        
        # Настройки для мобильных устройств
        self.mobile_presets = {
            '1080p_mobile': {
                'resolution': (1920, 1080),
                'video_bitrate': '4M',
                'audio_bitrate': '128k',
                'crf': 24,
                'preset': 'fast',
                'profile': 'baseline'
            },
            '720p_mobile': {
                'resolution': (1280, 720),
                'video_bitrate': '2M',
                'audio_bitrate': '96k',
                'crf': 25,
                'preset': 'fast',
                'profile': 'baseline'
            }
        }
    
    async def optimize_video(self, input_path: str, output_path: str,
                           target_quality: str = 'auto', user_type: str = 'free',
                           mobile_optimized: bool = False) -> Dict[str, Any]:
        """
        Оптимизирует видео под указанное качество
        
        Args:
            input_path: Путь к исходному файлу
            output_path: Путь для сохранения оптимизированного файла
            target_quality: Целевое качество или 'auto'
            user_type: Тип пользователя для ограничений качества
            mobile_optimized: Оптимизация для мобильных устройств
            
        Returns:
            Информация о результате оптимизации
        """
        try:
            # Получаем информацию об исходном видео
            video_info = await self._get_video_info(input_path)
            if not video_info:
                raise ValueError("Could not analyze input video")
            
            # Определяем оптимальное качество
            if target_quality == 'auto':
                target_quality = await self._determine_optimal_quality(
                    video_info, user_type, mobile_optimized
                )
            
            # Выбираем пресет
            preset = self._get_quality_preset(target_quality, mobile_optimized)
            if not preset:
                raise ValueError(f"Unknown quality preset: {target_quality}")
            
            # Проверяем, нужна ли оптимизация
            optimization_needed = await self._check_optimization_needed(
                video_info, preset
            )
            
            if not optimization_needed:
                # Просто копируем файл
                import shutil
                shutil.copy2(input_path, output_path)
                return {
                    'optimized': False,
                    'reason': 'optimization_not_needed',
                    'quality': target_quality,
                    'file_size': os.path.getsize(output_path),
                    'duration': video_info.get('duration', 0)
                }
            
            # Выполняем оптимизацию
            result = await self._perform_optimization(
                input_path, output_path, preset, video_info
            )
            
            # Получаем информацию о результате
            if os.path.exists(output_path):
                optimized_info = await self._get_video_info(output_path)
                result.update({
                    'optimized': True,
                    'quality': target_quality,
                    'original_size': video_info.get('size', 0),
                    'optimized_size': optimized_info.get('size', 0),
                    'compression_ratio': self._calculate_compression_ratio(
                        video_info.get('size', 0), optimized_info.get('size', 0)
                    ),
                    'duration': optimized_info.get('duration', 0)
                })
            
            logger.info(f"Video optimization completed", 
                       input_path=input_path, target_quality=target_quality)
            
            return result
            
        except Exception as e:
            logger.error(f"Error optimizing video: {e}", input_path=input_path)
            raise
    
    async def _determine_optimal_quality(self, video_info: Dict[str, Any],
                                       user_type: str, mobile_optimized: bool) -> str:
        """Определяет оптимальное качество на основе параметров видео и пользователя"""
        original_width = video_info.get('width', 0)
        original_height = video_info.get('height', 0)
        file_size_mb = video_info.get('size', 0) / (1024 * 1024)
        duration = video_info.get('duration', 0)
        
        # Ограничения по типу пользователя
        max_qualities = {
            'free': '720p',
            'trial': '1080p',
            'premium': '2160p',
            'admin': '2160p'
        }
        
        max_quality = max_qualities.get(user_type, '720p')
        
        # Определяем исходное качество
        if original_height >= 2160:
            source_quality = '2160p'
        elif original_height >= 1440:
            source_quality = '1440p'
        elif original_height >= 1080:
            source_quality = '1080p'
        elif original_height >= 720:
            source_quality = '720p'
        elif original_height >= 480:
            source_quality = '480p'
        else:
            source_quality = '360p'
        
        # Выбираем качество (не выше исходного и не выше лимита пользователя)
        quality_hierarchy = ['360p', '480p', '720p', '1080p', '1440p', '2160p']
        
        max_index = quality_hierarchy.index(max_quality)
        source_index = quality_hierarchy.index(source_quality)
        
        optimal_index = min(max_index, source_index)
        optimal_quality = quality_hierarchy[optimal_index]
        
        # Для мобильных устройств предпочитаем более низкое качество
        if mobile_optimized and optimal_quality in ['2160p', '1440p']:
            optimal_quality = '1080p'
        
        # Для очень больших файлов может потребоваться снижение качества
        if file_size_mb > 500 and duration > 300:  # > 500MB и > 5 минут
            if optimal_quality in ['2160p', '1440p']:
                optimal_quality = '1080p'
        
        logger.info(f"Determined optimal quality: {optimal_quality}", 
                   source_quality=source_quality, user_type=user_type)
        
        return optimal_quality
    
    def _get_quality_preset(self, quality: str, mobile_optimized: bool) -> Optional[Dict[str, Any]]:
        """Получает пресет качества"""
        if mobile_optimized:
            mobile_key = f"{quality}_mobile"
            if mobile_key in self.mobile_presets:
                return self.mobile_presets[mobile_key]
        
        return self.quality_presets.get(quality)
    
    async def _check_optimization_needed(self, video_info: Dict[str, Any],
                                       preset: Dict[str, Any]) -> bool:
        """Проверяет, нужна ли оптимизация видео"""
        try:
            original_width = video_info.get('width', 0)
            original_height = video_info.get('height', 0)
            target_width, target_height = preset['resolution']
            
            # Если исходное разрешение меньше или равно целевому
            if original_width <= target_width and original_height <= target_height:
                # Проверяем битрейт
                original_bitrate = video_info.get('bit_rate', 0)
                if original_bitrate > 0:
                    target_bitrate = self._parse_bitrate(preset['video_bitrate'])
                    if original_bitrate <= target_bitrate * 1.2:  # 20% запас
                        return False
            
            # Проверяем кодек
            original_codec = video_info.get('video_codec', '').lower()
            if original_codec in ['h264', 'h.264'] and preset.get('profile') != 'baseline':
                # Уже оптимальный кодек
                return original_width > target_width or original_height > target_height
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking optimization need: {e}")
            return True  # По умолчанию оптимизируем
    
    async def _perform_optimization(self, input_path: str, output_path: str,
                                  preset: Dict[str, Any], video_info: Dict[str, Any]) -> Dict[str, Any]:
        """Выполняет оптимизацию видео"""
        try:
            # Строим команду ffmpeg
            cmd = await self._build_ffmpeg_command(input_path, output_path, preset, video_info)
            
            # Выполняем оптимизацию с отслеживанием прогресса
            result = await self._execute_ffmpeg_with_progress(cmd, video_info.get('duration', 0))
            
            return result
            
        except Exception as e:
            logger.error(f"Error performing optimization: {e}")
            raise
    
    async def _build_ffmpeg_command(self, input_path: str, output_path: str,
                                  preset: Dict[str, Any], video_info: Dict[str, Any]) -> List[str]:
        """Строит команду ffmpeg для оптимизации"""
        cmd = ['ffmpeg', '-i', input_path]
        
        # Видео параметры
        target_width, target_height = preset['resolution']
        
        # Фильтр масштабирования с сохранением пропорций
        video_filters = []
        
        # Масштабирование
        scale_filter = f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease"
        video_filters.append(scale_filter)
        
        # Добавляем отступы если нужно
        pad_filter = f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2"
        video_filters.append(pad_filter)
        
        # Деинтерлейсинг если нужно
        if video_info.get('interlaced', False):
            video_filters.append('yadif')
        
        # Стабилизация если включена
        if preset.get('stabilize', False):
            video_filters.append('vidstabdetect=stepsize=6:shakiness=8:accuracy=9:result=/tmp/transforms.trf')
        
        # Применяем фильтры
        if video_filters:
            cmd.extend(['-vf', ','.join(video_filters)])
        
        # Кодек и настройки
        cmd.extend(['-c:v', 'libx264'])
        
        # CRF или битрейт
        if 'crf' in preset:
            cmd.extend(['-crf', str(preset['crf'])])
        else:
            cmd.extend(['-b:v', preset['video_bitrate']])
        
        # Пресет скорости
        cmd.extend(['-preset', preset.get('preset', 'medium')])
        
        # Профиль для совместимости
        if 'profile' in preset:
            cmd.extend(['-profile:v', preset['profile']])
            cmd.extend(['-level', '3.1'])
        
        # Аудио параметры
        cmd.extend(['-c:a', 'aac'])
        cmd.extend(['-b:a', preset['audio_bitrate']])
        cmd.extend(['-ar', '44100'])  # Частота дискретизации
        
        # Дополнительные параметры
        cmd.extend(['-movflags', '+faststart'])  # Для веб-воспроизведения
        cmd.extend(['-pix_fmt', 'yuv420p'])     # Совместимость
        cmd.extend(['-f', 'mp4'])               # Формат контейнера
        
        # Перезаписать выходной файл
        cmd.extend(['-y', output_path])
        
        return cmd
    
    async def _execute_ffmpeg_with_progress(self, cmd: List[str], duration: float) -> Dict[str, Any]:
        """Выполняет ffmpeg с отслеживанием прогресса"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Отслеживаем прогресс через stderr
            progress_data = {'progress': 0, 'speed': '1x', 'eta': None}
            
            stderr_output = b''
            while True:
                try:
                    line = await asyncio.wait_for(process.stderr.readline(), timeout=1.0)
                    if not line:
                        break
                    
                    stderr_output += line
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    
                    # Парсим прогресс
                    if 'time=' in line_str and duration > 0:
                        try:
                            time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line_str)
                            if time_match:
                                hours = int(time_match.group(1))
                                minutes = int(time_match.group(2))
                                seconds = float(time_match.group(3))
                                current_time = hours * 3600 + minutes * 60 + seconds
                                
                                progress = min(100, (current_time / duration) * 100)
                                progress_data['progress'] = progress
                                
                                # Извлекаем скорость
                                speed_match = re.search(r'speed=([0-9.]+)x', line_str)
                                if speed_match:
                                    progress_data['speed'] = f"{speed_match.group(1)}x"
                                
                                logger.debug(f"Optimization progress: {progress:.1f}%")
                        except:
                            pass
                
                except asyncio.TimeoutError:
                    # Проверяем, завершился ли процесс
                    if process.returncode is not None:
                        break
            
            # Ждем завершения
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return {
                    'success': True,
                    'progress': 100,
                    'returncode': 0
                }
            else:
                error_output = stderr_output.decode('utf-8', errors='ignore')
                return {
                    'success': False,
                    'error': error_output,
                    'returncode': process.returncode
                }
                
        except Exception as e:
            logger.error(f"Error executing ffmpeg: {e}")
            return {
                'success': False,
                'error': str(e),
                'returncode': -1
            }
    
    async def batch_optimize(self, input_files: List[str], output_dir: str,
                           quality_settings: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Пакетная оптимизация нескольких файлов
        
        Args:
            input_files: Список путей к исходным файлам
            output_dir: Директория для сохранения результатов
            quality_settings: Настройки качества для всех файлов
            
        Returns:
            Список результатов оптимизации
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            results = []
            
            for i, input_file in enumerate(input_files):
                if not os.path.exists(input_file):
                    results.append({
                        'input_file': input_file,
                        'success': False,
                        'error': 'File not found'
                    })
                    continue
                
                # Генерируем имя выходного файла
                input_name = Path(input_file).stem
                output_file = os.path.join(output_dir, f"{input_name}_optimized.mp4")
                
                try:
                    # Оптимизируем файл
                    result = await self.optimize_video(
                        input_file, output_file, **quality_settings
                    )
                    
                    result.update({
                        'input_file': input_file,
                        'output_file': output_file,
                        'batch_index': i
                    })
                    
                    results.append(result)
                    
                    logger.info(f"Batch optimization {i+1}/{len(input_files)} completed")
                    
                except Exception as e:
                    results.append({
                        'input_file': input_file,
                        'batch_index': i,
                        'success': False,
                        'error': str(e)
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch optimization: {e}")
            raise
    
    async def create_multiple_qualities(self, input_path: str, output_dir: str,
                                      qualities: List[str]) -> Dict[str, str]:
        """
        Создает файлы нескольких качеств из одного источника
        
        Args:
            input_path: Путь к исходному файлу
            output_dir: Директория для сохранения
            qualities: Список качеств для создания
            
        Returns:
            Словарь {quality: output_path}
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            results = {}
            
            input_name = Path(input_path).stem
            
            # Создаем задачи для параллельной обработки
            tasks = []
            for quality in qualities:
                output_file = os.path.join(output_dir, f"{input_name}_{quality}.mp4")
                task = self.optimize_video(input_path, output_file, target_quality=quality)
                tasks.append((quality, output_file, task))
            
            # Выполняем оптимизацию параллельно (но ограничиваем количество)
            semaphore = asyncio.Semaphore(2)  # Максимум 2 параллельные задачи
            
            async def process_quality(quality, output_file, task):
                async with semaphore:
                    try:
                        await task
                        if os.path.exists(output_file):
                            return quality, output_file
                    except Exception as e:
                        logger.error(f"Error creating {quality} version: {e}")
                    return quality, None
            
            # Запускаем все задачи
            quality_tasks = [
                process_quality(quality, output_file, task)
                for quality, output_file, task in tasks
            ]
            
            completed_tasks = await asyncio.gather(*quality_tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for result in completed_tasks:
                if isinstance(result, tuple):
                    quality, output_path = result
                    if output_path:
                        results[quality] = output_path
            
            logger.info(f"Created {len(results)} quality versions", qualities=list(results.keys()))
            
            return results
            
        except Exception as e:
            logger.error(f"Error creating multiple qualities: {e}")
            return {}
    
    def _parse_bitrate(self, bitrate_str: str) -> int:
        """Парсит строку битрейта в bps"""
        try:
            if bitrate_str.lower().endswith('k'):
                return int(float(bitrate_str[:-1]) * 1000)
            elif bitrate_str.lower().endswith('m'):
                return int(float(bitrate_str[:-1]) * 1000000)
            else:
                return int(bitrate_str)
        except:
            return 0
    
    def _calculate_compression_ratio(self, original_size: int, compressed_size: int) -> float:
        """Рассчитывает коэффициент сжатия"""
        if original_size == 0:
            return 0.0
        return (original_size - compressed_size) / original_size * 100
    
    async def _get_video_info(self, video_path: str) -> Dict[str, Any]:
        """Получает подробную информацию о видео"""
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
                info = json.loads(stdout.decode())
                
                format_info = info.get('format', {})
                video_stream = None
                audio_stream = None
                
                # Ищем видео и аудио потоки
                for stream in info.get('streams', []):
                    if stream.get('codec_type') == 'video' and video_stream is None:
                        video_stream = stream
                    elif stream.get('codec_type') == 'audio' and audio_stream is None:
                        audio_stream = stream
                
                result = {
                    'duration': float(format_info.get('duration', 0)),
                    'size': int(format_info.get('size', 0)),
                    'bit_rate': int(format_info.get('bit_rate', 0)),
                    'format': format_info.get('format_name'),
                }
                
                if video_stream:
                    result.update({
                        'width': int(video_stream.get('width', 0)),
                        'height': int(video_stream.get('height', 0)),
                        'video_codec': video_stream.get('codec_name'),
                        'video_bitrate': int(video_stream.get('bit_rate', 0)),
                        'fps': self._parse_fps(video_stream.get('r_frame_rate', '0/1')),
                        'pixel_format': video_stream.get('pix_fmt'),
                        'interlaced': video_stream.get('field_order', 'progressive') != 'progressive'
                    })
                
                if audio_stream:
                    result.update({
                        'audio_codec': audio_stream.get('codec_name'),
                        'audio_bitrate': int(audio_stream.get('bit_rate', 0)),
                        'sample_rate': int(audio_stream.get('sample_rate', 0)),
                        'channels': int(audio_stream.get('channels', 0))
                    })
                
                return result
            
            return {}
            
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return {}
    
    def _parse_fps(self, fps_str: str) -> float:
        """Парсит FPS из строки вида '30/1'"""
        try:
            if '/' in fps_str:
                numerator, denominator = fps_str.split('/')
                return float(numerator) / float(denominator)
            return float(fps_str)
        except:
            return 0.0
    
    async def estimate_output_size(self, input_path: str, target_quality: str) -> Dict[str, Any]:
        """
        Оценивает размер выходного файла без выполнения конвертации
        
        Args:
            input_path: Путь к исходному файлу
            target_quality: Целевое качество
            
        Returns:
            Оценка размера и времени обработки
        """
        try:
            video_info = await self._get_video_info(input_path)
            if not video_info:
                return {}
            
            preset = self.quality_presets.get(target_quality)
            if not preset:
                return {}
            
            duration = video_info.get('duration', 0)
            original_size = video_info.get('size', 0)
            
            # Оценка на основе битрейта
            target_bitrate = self._parse_bitrate(preset['video_bitrate'])
            audio_bitrate = self._parse_bitrate(preset['audio_bitrate'])
            
            estimated_size = (target_bitrate + audio_bitrate) * duration / 8  # В байтах
            
            # Коррекция на основе сложности видео
            complexity_factor = 1.0
            if video_info.get('fps', 0) > 30:
                complexity_factor *= 1.2
            if video_info.get('width', 0) * video_info.get('height', 0) > 2000000:  # > 2MP
                complexity_factor *= 1.1
            
            estimated_size *= complexity_factor
            
            # Оценка времени обработки (примерно)
            processing_speed_factor = {
                'fast': 0.3,      # 30% от длительности видео
                'medium': 0.5,    # 50% от длительности видео  
                'slow': 0.8       # 80% от длительности видео
            }
            
            preset_name = preset.get('preset', 'medium')
            estimated_time = duration * processing_speed_factor.get(preset_name, 0.5)
            
            return {
                'estimated_size_bytes': int(estimated_size),
                'estimated_size_mb': estimated_size / (1024 * 1024),
                'estimated_processing_time_seconds': int(estimated_time),
                'compression_ratio_estimate': (1 - estimated_size / original_size) * 100 if original_size > 0 else 0,
                'target_bitrate_bps': target_bitrate,
                'complexity_factor': complexity_factor
            }
            
        except Exception as e:
            logger.error(f"Error estimating output size: {e}")
            return {}