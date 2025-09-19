"""
VideoBot Pro - Video Processor
Обработка видео файлов: конвертация, оптимизация, извлечение метаданных
"""

import structlog
import subprocess
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

logger = structlog.get_logger(__name__)

class VideoProcessorError(Exception):
    """Ошибки обработки видео"""
    pass

class VideoProcessor:
    """Основной класс для обработки видео файлов"""
    
    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        """
        Инициализация процессора
        
        Args:
            ffmpeg_path: Путь к FFmpeg
            ffprobe_path: Путь к FFprobe
        """
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.temp_dir = Path(tempfile.gettempdir()) / "videobot_processing"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Проверяем доступность инструментов
        self._check_tools_availability()
    
    def _check_tools_availability(self):
        """Проверка доступности FFmpeg и FFprobe"""
        try:
            subprocess.run([self.ffmpeg_path, "-version"], 
                         capture_output=True, check=True, timeout=10)
            subprocess.run([self.ffprobe_path, "-version"], 
                         capture_output=True, check=True, timeout=10)
            logger.info("FFmpeg and FFprobe are available")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"FFmpeg/FFprobe not available: {e}")
            raise VideoProcessorError("FFmpeg/FFprobe not found or not working")
    
    def get_video_info(self, file_path: str) -> Dict[str, Any]:
        """
        Получение информации о видео файле
        
        Args:
            file_path: Путь к видео файлу
            
        Returns:
            Словарь с информацией о видео
        """
        try:
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                raise VideoProcessorError(f"FFprobe failed: {result.stderr}")
            
            probe_data = json.loads(result.stdout)
            
            # Извлекаем информацию о видео
            video_info = self._extract_video_metadata(probe_data)
            
            logger.info(f"Extracted video info: {video_info}")
            return video_info
            
        except subprocess.TimeoutExpired:
            raise VideoProcessorError("Video analysis timeout")
        except json.JSONDecodeError as e:
            raise VideoProcessorError(f"Failed to parse FFprobe output: {e}")
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            raise VideoProcessorError(f"Failed to analyze video: {e}")
    
    def _extract_video_metadata(self, probe_data: Dict[str, Any]) -> Dict[str, Any]:
        """Извлечение метаданных из данных FFprobe"""
        try:
            format_info = probe_data.get('format', {})
            video_stream = None
            audio_stream = None
            
            # Находим видео и аудио потоки
            for stream in probe_data.get('streams', []):
                if stream.get('codec_type') == 'video' and not video_stream:
                    video_stream = stream
                elif stream.get('codec_type') == 'audio' and not audio_stream:
                    audio_stream = stream
            
            # Основная информация
            info = {
                'duration': float(format_info.get('duration', 0)),
                'file_size': int(format_info.get('size', 0)),
                'format_name': format_info.get('format_name', ''),
                'bit_rate': int(format_info.get('bit_rate', 0)),
            }
            
            # Информация о видео потоке
            if video_stream:
                info.update({
                    'width': int(video_stream.get('width', 0)),
                    'height': int(video_stream.get('height', 0)),
                    'video_codec': video_stream.get('codec_name', ''),
                    'video_bitrate': int(video_stream.get('bit_rate', 0)) if video_stream.get('bit_rate') else None,
                    'fps': self._parse_fps(video_stream.get('r_frame_rate', '0/1')),
                    'pixel_format': video_stream.get('pix_fmt', ''),
                    'aspect_ratio': video_stream.get('display_aspect_ratio', ''),
                    'video_duration': float(video_stream.get('duration', 0))
                })
                
                # Качество видео
                info['quality'] = self._determine_quality(info['width'], info['height'])
                
                # HDR информация
                if video_stream.get('color_space') or video_stream.get('color_transfer'):
                    info['is_hdr'] = self._detect_hdr(video_stream)
            
            # Информация об аудио потоке
            if audio_stream:
                info.update({
                    'audio_codec': audio_stream.get('codec_name', ''),
                    'audio_bitrate': int(audio_stream.get('bit_rate', 0)) if audio_stream.get('bit_rate') else None,
                    'sample_rate': int(audio_stream.get('sample_rate', 0)),
                    'channels': int(audio_stream.get('channels', 0)),
                    'audio_duration': float(audio_stream.get('duration', 0))
                })
            
            # Метаданные
            tags = format_info.get('tags', {})
            if tags:
                info['metadata'] = {
                    'title': tags.get('title', ''),
                    'artist': tags.get('artist', ''),
                    'description': tags.get('comment', tags.get('description', '')),
                    'creation_time': tags.get('creation_time', ''),
                    'encoder': tags.get('encoder', '')
                }
            
            return info
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            raise VideoProcessorError(f"Failed to extract video metadata: {e}")
    
    def _parse_fps(self, fps_string: str) -> float:
        """Парсинг FPS из строки вида '30/1'"""
        try:
            if '/' in fps_string:
                numerator, denominator = fps_string.split('/')
                return float(numerator) / float(denominator)
            return float(fps_string)
        except (ValueError, ZeroDivisionError):
            return 0.0
    
    def _determine_quality(self, width: int, height: int) -> str:
        """Определение качества по разрешению"""
        if height >= 2160:
            return "4K"
        elif height >= 1440:
            return "1440p"
        elif height >= 1080:
            return "1080p"
        elif height >= 720:
            return "720p"
        elif height >= 480:
            return "480p"
        elif height >= 360:
            return "360p"
        else:
            return "240p"
    
    def _detect_hdr(self, video_stream: Dict[str, Any]) -> bool:
        """Определение HDR контента"""
        color_space = video_stream.get('color_space', '').lower()
        color_transfer = video_stream.get('color_transfer', '').lower()
        
        hdr_indicators = ['rec2020', 'bt2020', 'smpte2084', 'arib-std-b67', 'hlg']
        
        return any(indicator in color_space or indicator in color_transfer 
                  for indicator in hdr_indicators)
    
    def optimize_video(self, input_path: str, output_path: str, 
                      target_quality: str = "720p", 
                      target_format: str = "mp4",
                      max_file_size_mb: Optional[int] = None) -> Dict[str, Any]:
        """
        Оптимизация видео для более эффективного хранения/передачи
        
        Args:
            input_path: Путь к исходному файлу
            output_path: Путь к выходному файлу
            target_quality: Целевое качество (480p, 720p, 1080p, etc.)
            target_format: Целевой формат (mp4, webm)
            max_file_size_mb: Максимальный размер файла в МБ
            
        Returns:
            Информация о результате оптимизации
        """
        try:
            logger.info(f"Starting video optimization: {input_path} -> {output_path}")
            
            # Получаем информацию об исходном файле
            input_info = self.get_video_info(input_path)
            
            # Определяем параметры кодирования
            encoding_params = self._get_encoding_params(
                input_info, target_quality, target_format, max_file_size_mb
            )
            
            # Строим команду FFmpeg
            cmd = self._build_ffmpeg_command(
                input_path, output_path, encoding_params
            )
            
            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
            
            # Запускаем конвертацию
            start_time = datetime.now()
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(timeout=3600)  # 1 час максимум
            
            if process.returncode != 0:
                logger.error(f"FFmpeg failed with stderr: {stderr}")
                raise VideoProcessorError(f"Video optimization failed: {stderr}")
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            # Получаем информацию о результате
            output_info = self.get_video_info(output_path)
            
            result = {
                'success': True,
                'input_file': input_path,
                'output_file': output_path,
                'processing_time_seconds': processing_time,
                'input_info': input_info,
                'output_info': output_info,
                'compression_ratio': input_info['file_size'] / output_info['file_size'] if output_info['file_size'] > 0 else 1,
                'size_reduction_percent': ((input_info['file_size'] - output_info['file_size']) / input_info['file_size'] * 100) if input_info['file_size'] > 0 else 0
            }
            
            logger.info(f"Video optimization completed: {result}")
            return result
            
        except subprocess.TimeoutExpired:
            logger.error("Video optimization timeout")
            raise VideoProcessorError("Video optimization timeout")
        except Exception as e:
            logger.error(f"Error optimizing video: {e}")
            raise VideoProcessorError(f"Failed to optimize video: {e}")
    
    def _get_encoding_params(self, input_info: Dict[str, Any], 
                           target_quality: str, target_format: str,
                           max_file_size_mb: Optional[int]) -> Dict[str, Any]:
        """Определение параметров кодирования"""
        
        # Целевые разрешения
        quality_resolutions = {
            "240p": (426, 240),
            "360p": (640, 360),
            "480p": (854, 480),
            "720p": (1280, 720),
            "1080p": (1920, 1080),
            "1440p": (2560, 1440),
            "4K": (3840, 2160)
        }
        
        target_width, target_height = quality_resolutions.get(target_quality, (1280, 720))
        
        # Если исходное разрешение меньше целевого, не увеличиваем
        input_width = input_info.get('width', 0)
        input_height = input_info.get('height', 0)
        
        if input_width > 0 and input_height > 0:
            if input_width < target_width or input_height < target_height:
                target_width = input_width
                target_height = input_height
        
        params = {
            'width': target_width,
            'height': target_height,
            'format': target_format,
            'video_codec': 'libx264' if target_format == 'mp4' else 'libvpx-vp9',
            'audio_codec': 'aac' if target_format == 'mp4' else 'libopus',
            'preset': 'medium',  # Баланс скорости и качества
            'crf': 23,  # Качество (18-28, меньше = лучше качество)
        }
        
        # Если указан максимальный размер файла, рассчитываем битрейт
        if max_file_size_mb and input_info.get('duration', 0) > 0:
            max_bitrate_kbps = (max_file_size_mb * 8 * 1024) / input_info['duration']
            # Оставляем место для аудио (128 kbps)
            video_bitrate_kbps = max_bitrate_kbps - 128
            
            if video_bitrate_kbps > 0:
                params['video_bitrate'] = f"{int(video_bitrate_kbps)}k"
                params['audio_bitrate'] = "128k"
                params['two_pass'] = True
        
        return params
    
    def _build_ffmpeg_command(self, input_path: str, output_path: str, 
                            params: Dict[str, Any]) -> List[str]:
        """Построение команды FFmpeg"""
        
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-y",  # Перезаписывать выходной файл
        ]
        
        # Видео параметры
        cmd.extend([
            "-c:v", params['video_codec'],
            "-preset", params['preset'],
        ])
        
        # Разрешение
        if params.get('width') and params.get('height'):
            cmd.extend(["-vf", f"scale={params['width']}:{params['height']}"])
        
        # Битрейт или CRF
        if params.get('video_bitrate'):
            cmd.extend(["-b:v", params['video_bitrate']])
            cmd.extend(["-maxrate", params['video_bitrate']])
            cmd.extend(["-bufsize", f"{int(params['video_bitrate'].rstrip('k')) * 2}k"])
        else:
            cmd.extend(["-crf", str(params['crf'])])
        
        # Аудио параметры
        cmd.extend([
            "-c:a", params['audio_codec'],
        ])
        
        if params.get('audio_bitrate'):
            cmd.extend(["-b:a", params['audio_bitrate']])
        
        # Формат-специфичные параметры
        if params['format'] == 'mp4':
            cmd.extend([
                "-movflags", "faststart",  # Для веб-проигрывания
                "-pix_fmt", "yuv420p"      # Совместимость
            ])
        elif params['format'] == 'webm':
            cmd.extend([
                "-deadline", "good",
                "-cpu-used", "2"
            ])
        
        cmd.append(output_path)
        
        return cmd
    
    def extract_thumbnail(self, video_path: str, output_path: str, 
                         timestamp: str = "00:00:05",
                         width: int = 320, height: int = 240) -> Dict[str, Any]:
        """
        Извлечение превью из видео
        
        Args:
            video_path: Путь к видео файлу
            output_path: Путь к файлу превью
            timestamp: Временная метка для извлечения (HH:MM:SS)
            width: Ширина превью
            height: Высота превью
            
        Returns:
            Информация о созданном превью
        """
        try:
            logger.info(f"Extracting thumbnail from {video_path}")
            
            cmd = [
                self.ffmpeg_path,
                "-i", video_path,
                "-ss", timestamp,
                "-vframes", "1",
                "-vf", f"scale={width}:{height}",
                "-q:v", "2",  # Высокое качество JPEG
                "-y",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                raise VideoProcessorError(f"Thumbnail extraction failed: {result.stderr}")
            
            # Проверяем что файл создан
            output_file = Path(output_path)
            if not output_file.exists():
                raise VideoProcessorError("Thumbnail file was not created")
            
            thumbnail_info = {
                'success': True,
                'thumbnail_path': output_path,
                'file_size': output_file.stat().st_size,
                'width': width,
                'height': height,
                'timestamp': timestamp
            }
            
            logger.info(f"Thumbnail extracted successfully: {thumbnail_info}")
            return thumbnail_info
            
        except subprocess.TimeoutExpired:
            raise VideoProcessorError("Thumbnail extraction timeout")
        except Exception as e:
            logger.error(f"Error extracting thumbnail: {e}")
            raise VideoProcessorError(f"Failed to extract thumbnail: {e}")
    
    def convert_to_audio(self, video_path: str, output_path: str,
                        audio_format: str = "mp3", 
                        bitrate: str = "192k") -> Dict[str, Any]:
        """
        Конвертация видео в аудио
        
        Args:
            video_path: Путь к видео файлу
            output_path: Путь к аудио файлу
            audio_format: Формат аудио (mp3, aac, ogg)
            bitrate: Битрейт аудио
            
        Returns:
            Информация о созданном аудио файле
        """
        try:
            logger.info(f"Converting video to audio: {video_path} -> {output_path}")
            
            # Определяем кодек по формату
            codec_map = {
                'mp3': 'libmp3lame',
                'aac': 'aac',
                'ogg': 'libvorbis',
                'm4a': 'aac'
            }
            
            codec = codec_map.get(audio_format.lower(), 'libmp3lame')
            
            cmd = [
                self.ffmpeg_path,
                "-i", video_path,
                "-vn",  # Убираем видео
                "-c:a", codec,
                "-b:a", bitrate,
                "-y",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                raise VideoProcessorError(f"Audio conversion failed: {result.stderr}")
            
            # Получаем информацию об аудио файле
            audio_info = self.get_video_info(output_path)
            
            conversion_result = {
                'success': True,
                'audio_path': output_path,
                'format': audio_format,
                'codec': codec,
                'bitrate': bitrate,
                'duration': audio_info.get('duration', 0),
                'file_size': audio_info.get('file_size', 0)
            }
            
            logger.info(f"Audio conversion completed: {conversion_result}")
            return conversion_result
            
        except subprocess.TimeoutExpired:
            raise VideoProcessorError("Audio conversion timeout")
        except Exception as e:
            logger.error(f"Error converting to audio: {e}")
            raise VideoProcessorError(f"Failed to convert to audio: {e}")
    
    def create_preview_gif(self, video_path: str, output_path: str,
                          start_time: str = "00:00:05", 
                          duration: int = 3,
                          width: int = 320, fps: int = 10) -> Dict[str, Any]:
        """
        Создание GIF превью из видео
        
        Args:
            video_path: Путь к видео файлу
            output_path: Путь к GIF файлу
            start_time: Время начала (HH:MM:SS)
            duration: Длительность в секундах
            width: Ширина GIF
            fps: Частота кадров
            
        Returns:
            Информация о созданном GIF
        """
        try:
            logger.info(f"Creating GIF preview from {video_path}")
            
            cmd = [
                self.ffmpeg_path,
                "-ss", start_time,
                "-t", str(duration),
                "-i", video_path,
                "-vf", f"fps={fps},scale={width}:-1:flags=lanczos",
                "-c:v", "gif",
                "-y",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                raise VideoProcessorError(f"GIF creation failed: {result.stderr}")
            
            output_file = Path(output_path)
            if not output_file.exists():
                raise VideoProcessorError("GIF file was not created")
            
            gif_info = {
                'success': True,
                'gif_path': output_path,
                'file_size': output_file.stat().st_size,
                'width': width,
                'duration': duration,
                'fps': fps,
                'start_time': start_time
            }
            
            logger.info(f"GIF preview created successfully: {gif_info}")
            return gif_info
            
        except subprocess.TimeoutExpired:
            raise VideoProcessorError("GIF creation timeout")
        except Exception as e:
            logger.error(f"Error creating GIF: {e}")
            raise VideoProcessorError(f"Failed to create GIF: {e}")
    
    def cleanup_temp_files(self):
        """Очистка временных файлов"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                self.temp_dir.mkdir(exist_ok=True)
            logger.info("Temporary files cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")
    
    def get_temp_path(self, filename: str) -> str:
        """Получить путь для временного файла"""
        return str(self.temp_dir / filename)
    
    def is_valid_video(self, file_path: str) -> bool:
        """Проверка является ли файл валидным видео"""
        try:
            info = self.get_video_info(file_path)
            return info.get('duration', 0) > 0 and info.get('width', 0) > 0
        except VideoProcessorError:
            return False