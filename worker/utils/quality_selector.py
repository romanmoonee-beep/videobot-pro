"""
VideoBot Pro - Quality Selector
Селектор качества видео на основе параметров пользователя и доступных форматов
"""

import structlog
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import math

logger = structlog.get_logger(__name__)

@dataclass
class FormatInfo:
    """Информация о доступном формате видео"""
    format_id: str
    ext: str
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    filesize: Optional[int] = None
    filesize_approx: Optional[int] = None
    tbr: Optional[float] = None  # total bitrate
    vbr: Optional[float] = None  # video bitrate
    abr: Optional[float] = None  # audio bitrate
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    protocol: Optional[str] = None
    url: Optional[str] = None
    quality: Optional[str] = None
    
    @property
    def quality_score(self) -> int:
        """Вычисляет оценку качества формата"""
        if not self.height:
            return 0
            
        # Базовая оценка по разрешению
        if self.height >= 2160:
            score = 100
        elif self.height >= 1440:
            score = 85
        elif self.height >= 1080:
            score = 70
        elif self.height >= 720:
            score = 55
        elif self.height >= 480:
            score = 40
        elif self.height >= 360:
            score = 25
        else:
            score = 10
            
        # Бонусы за хорошие параметры
        if self.fps and self.fps >= 60:
            score += 10
        elif self.fps and self.fps >= 30:
            score += 5
            
        # Предпочитаем современные кодеки
        if self.vcodec:
            if 'av01' in self.vcodec.lower():
                score += 8
            elif 'vp9' in self.vcodec.lower():
                score += 5
            elif 'h264' in self.vcodec.lower() or 'avc' in self.vcodec.lower():
                score += 3
                
        # Штрафы за плохие параметры
        if self.protocol == 'http_dash_segments':
            score -= 5  # DASH может быть менее стабильным
            
        return max(0, score)
    
    @property 
    def estimated_size_mb(self) -> float:
        """Оценка размера файла в МБ"""
        if self.filesize:
            return self.filesize / (1024 * 1024)
        elif self.filesize_approx:
            return self.filesize_approx / (1024 * 1024)
        elif self.tbr and self.height:
            # Примерная оценка на основе битрейта
            # Предполагаем среднюю длительность 3 минуты
            duration_minutes = 3
            return (self.tbr * 1024 * duration_minutes * 60) / (8 * 1024 * 1024)
        else:
            # Очень грубая оценка по разрешению
            if self.height >= 1080:
                return 50  # ~50MB для 1080p
            elif self.height >= 720:
                return 25  # ~25MB для 720p  
            elif self.height >= 480:
                return 15  # ~15MB для 480p
            else:
                return 8   # ~8MB для низкого качества

class QualitySelector:
    """Селектор оптимального качества видео"""
    
    def __init__(self):
        """Инициализация селектора"""
        self.logger = logger.bind(component="quality_selector")
        
        # Приоритеты качества по типу пользователя
        self.user_quality_limits = {
            'free': ['360p', '480p', '720p'],
            'trial': ['360p', '480p', '720p', '1080p'],
            'premium': ['360p', '480p', '720p', '1080p', '1440p', '2160p'],
            'admin': ['360p', '480p', '720p', '1080p', '1440p', '2160p', '4K']
        }
        
        # Максимальные размеры файлов (MB) по типу пользователя
        self.user_size_limits = {
            'free': 100,
            'trial': 250,
            'premium': 1000,
            'admin': 2000
        }
        
        # Предпочтительные расширения в порядке приоритета
        self.preferred_extensions = ['mp4', 'webm', 'mkv', 'avi', 'mov']
        
        # Предпочтительные кодеки в порядке приоритета
        self.preferred_video_codecs = [
            'h264', 'avc1', 'avc', 'vp9', 'av01', 'hevc', 'h265'
        ]
        
        self.preferred_audio_codecs = [
            'aac', 'mp3', 'opus', 'vorbis', 'm4a'
        ]

    def select_quality(self, 
                      available_formats: List[Dict[str, Any]],
                      requested_quality: str = 'auto',
                      user_type: str = 'free',
                      file_size_limit: Optional[int] = None,
                      prefer_audio_only: bool = False) -> Optional[Dict[str, Any]]:
        """
        Выбирает оптимальный формат из доступных
        
        Args:
            available_formats: Список доступных форматов
            requested_quality: Запрошенное качество ('auto', '720p', '1080p', etc.)
            user_type: Тип пользователя для ограничений
            file_size_limit: Лимит размера файла в байтах
            prefer_audio_only: Предпочитать аудио-только формат
            
        Returns:
            Лучший формат или None если не найден подходящий
        """
        try:
            if not available_formats:
                self.logger.warning("No formats available")
                return None
                
            # Конвертируем форматы в объекты FormatInfo
            formats = [self._parse_format(fmt) for fmt in available_formats]
            formats = [f for f in formats if f is not None]
            
            if not formats:
                self.logger.warning("No valid formats after parsing")
                return None
                
            self.logger.info(f"Selecting quality from {len(formats)} formats", 
                           requested_quality=requested_quality, user_type=user_type)
            
            # Фильтруем по типу пользователя
            allowed_formats = self._filter_by_user_type(formats, user_type)
            if not allowed_formats:
                self.logger.warning("No formats allowed for user type", user_type=user_type)
                # Fallback к самому низкому качеству
                allowed_formats = [min(formats, key=lambda f: f.height or 0)]
                
            # Фильтруем по размеру файла
            if file_size_limit:
                size_limit_mb = file_size_limit / (1024 * 1024)
                size_filtered = [f for f in allowed_formats 
                               if f.estimated_size_mb <= size_limit_mb]
                if size_filtered:
                    allowed_formats = size_filtered
                else:
                    self.logger.warning("No formats within size limit, using smallest available")
                    allowed_formats = [min(allowed_formats, 
                                         key=lambda f: f.estimated_size_mb)]
            
            # Если нужно только аудио
            if prefer_audio_only:
                audio_formats = [f for f in allowed_formats if not f.vcodec or f.vcodec == 'none']
                if audio_formats:
                    selected = self._select_best_audio(audio_formats)
                    if selected:
                        return self._format_to_dict(selected)
            
            # Выбираем лучший видео формат
            selected = self._select_best_video(allowed_formats, requested_quality)
            
            if selected:
                result = self._format_to_dict(selected)
                self.logger.info("Selected format", 
                               format_id=result['format_id'],
                               quality=result.get('quality'),
                               size_mb=result.get('estimated_size_mb'))
                return result
            else:
                self.logger.error("Failed to select any format")
                return None
                
        except Exception as e:
            self.logger.error(f"Error selecting quality: {e}")
            return None
    
    def _parse_format(self, format_dict: Dict[str, Any]) -> Optional[FormatInfo]:
        """Парсит словарь формата в объект FormatInfo"""
        try:
            return FormatInfo(
                format_id=format_dict.get('format_id', ''),
                ext=format_dict.get('ext', ''),
                width=format_dict.get('width'),
                height=format_dict.get('height'),
                fps=format_dict.get('fps'),
                filesize=format_dict.get('filesize'),
                filesize_approx=format_dict.get('filesize_approx'),
                tbr=format_dict.get('tbr'),
                vbr=format_dict.get('vbr'),
                abr=format_dict.get('abr'),
                vcodec=format_dict.get('vcodec'),
                acodec=format_dict.get('acodec'),
                protocol=format_dict.get('protocol'),
                url=format_dict.get('url'),
                quality=self._determine_quality_label(format_dict.get('height'))
            )
        except Exception as e:
            self.logger.error(f"Error parsing format: {e}")
            return None
    
    def _determine_quality_label(self, height: Optional[int]) -> Optional[str]:
        """Определяет метку качества по высоте"""
        if not height:
            return None
            
        if height >= 2160:
            return '2160p'
        elif height >= 1440:
            return '1440p'
        elif height >= 1080:
            return '1080p'
        elif height >= 720:
            return '720p'
        elif height >= 480:
            return '480p'
        elif height >= 360:
            return '360p'
        elif height >= 240:
            return '240p'
        else:
            return f'{height}p'
    
    def _filter_by_user_type(self, formats: List[FormatInfo], 
                           user_type: str) -> List[FormatInfo]:
        """Фильтрует форматы по ограничениям пользователя"""
        allowed_qualities = self.user_quality_limits.get(user_type, ['720p'])
        size_limit = self.user_size_limits.get(user_type, 100)
        
        filtered = []
        for fmt in formats:
            # Проверяем качество
            if fmt.quality and fmt.quality not in allowed_qualities:
                continue
                
            # Проверяем размер
            if fmt.estimated_size_mb > size_limit:
                continue
                
            filtered.append(fmt)
        
        return filtered
    
    def _select_best_video(self, formats: List[FormatInfo], 
                          requested_quality: str) -> Optional[FormatInfo]:
        """Выбирает лучший видео формат"""
        # Фильтруем только видео форматы
        video_formats = [f for f in formats 
                        if f.vcodec and f.vcodec != 'none' and f.height]
        
        if not video_formats:
            self.logger.warning("No video formats available")
            return None
        
        if requested_quality == 'auto':
            # Автоматический выбор - берем лучший по качеству с разумным размером
            return self._select_auto_quality(video_formats)
        elif requested_quality == 'best':
            # Лучшее качество независимо от размера
            return max(video_formats, key=lambda f: f.quality_score)
        elif requested_quality == 'worst':
            # Худшее качество (минимальный размер)
            return min(video_formats, key=lambda f: f.estimated_size_mb)
        else:
            # Конкретное качество
            return self._select_specific_quality(video_formats, requested_quality)
    
    def _select_auto_quality(self, formats: List[FormatInfo]) -> Optional[FormatInfo]:
        """Автоматический выбор качества"""
        if not formats:
            return None
            
        # Сортируем по оценке качества
        sorted_formats = sorted(formats, key=lambda f: f.quality_score, reverse=True)
        
        # Ищем оптимальный баланс качества и размера
        best_format = None
        best_score = 0
        
        for fmt in sorted_formats:
            # Комбинированная оценка: качество - штраф за размер
            quality_score = fmt.quality_score
            size_penalty = min(fmt.estimated_size_mb / 10, 50)  # Штраф до 50 баллов
            
            combined_score = quality_score - size_penalty
            
            # Бонус за предпочтительные кодеки и расширения
            if fmt.ext in self.preferred_extensions[:2]:  # mp4, webm
                combined_score += 10
                
            if fmt.vcodec and any(codec in fmt.vcodec.lower() 
                                for codec in self.preferred_video_codecs[:3]):
                combined_score += 5
            
            if combined_score > best_score:
                best_score = combined_score
                best_format = fmt
        
        return best_format
    
    def _select_specific_quality(self, formats: List[FormatInfo], 
                               requested_quality: str) -> Optional[FormatInfo]:
        """Выбирает конкретное качество"""
        # Сначала ищем точное соответствие
        exact_matches = [f for f in formats if f.quality == requested_quality]
        
        if exact_matches:
            # Из точных соответствий выбираем лучший по кодеку и размеру
            return self._select_best_from_candidates(exact_matches)
        
        # Если точного соответствия нет, ищем ближайшее
        target_height = self._quality_to_height(requested_quality)
        if not target_height:
            return self._select_auto_quality(formats)
        
        # Сортируем по близости к целевому разрешению
        def distance_score(fmt):
            if not fmt.height:
                return float('inf')
            return abs(fmt.height - target_height)
        
        closest_formats = sorted(formats, key=distance_score)[:5]  # Топ 5 ближайших
        
        return self._select_best_from_candidates(closest_formats)
    
    def _quality_to_height(self, quality: str) -> Optional[int]:
        """Конвертирует метку качества в высоту"""
        quality_map = {
            '240p': 240,
            '360p': 360,
            '480p': 480,
            '720p': 720,
            '1080p': 1080,
            '1440p': 1440,
            '2160p': 2160,
            '4K': 2160
        }
        return quality_map.get(quality)
    
    def _select_best_from_candidates(self, candidates: List[FormatInfo]) -> Optional[FormatInfo]:
        """Выбирает лучший формат из кандидатов"""
        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Оценка кандидатов по нескольким критериям
        best_format = None
        best_score = -1
        
        for fmt in candidates:
            score = 0
            
            # Предпочтительные расширения
            if fmt.ext in self.preferred_extensions:
                score += (len(self.preferred_extensions) - 
                         self.preferred_extensions.index(fmt.ext)) * 10
            
            # Предпочтительные кодеки
            if fmt.vcodec:
                for i, codec in enumerate(self.preferred_video_codecs):
                    if codec in fmt.vcodec.lower():
                        score += (len(self.preferred_video_codecs) - i) * 5
                        break
            
            # Предпочитаем более стабильные протоколы
            if fmt.protocol:
                if 'https' in fmt.protocol:
                    score += 15
                elif 'http' in fmt.protocol:
                    score += 10
            
            # Штраф за очень большие файлы
            if fmt.estimated_size_mb > 200:
                score -= (fmt.estimated_size_mb - 200) / 10
            
            if score > best_score:
                best_score = score
                best_format = fmt
        
        return best_format
    
    def _select_best_audio(self, formats: List[FormatInfo]) -> Optional[FormatInfo]:
        """Выбирает лучший аудио формат"""
        if not formats:
            return None
            
        # Сортируем по битрейту (выше = лучше)
        audio_formats = sorted(formats, 
                             key=lambda f: f.abr or f.tbr or 0, 
                             reverse=True)
        
        # Выбираем лучший по кодеку
        for fmt in audio_formats:
            if fmt.acodec and any(codec in fmt.acodec.lower() 
                                for codec in self.preferred_audio_codecs):
                return fmt
        
        # Если нет предпочтительных кодеков, берем с лучшим битрейтом
        return audio_formats[0] if audio_formats else None
    
    def _format_to_dict(self, format_info: FormatInfo) -> Dict[str, Any]:
        """Конвертирует FormatInfo в словарь"""
        return {
            'format_id': format_info.format_id,
            'ext': format_info.ext,
            'width': format_info.width,
            'height': format_info.height,
            'fps': format_info.fps,
            'filesize': format_info.filesize,
            'filesize_approx': format_info.filesize_approx,
            'tbr': format_info.tbr,
            'vbr': format_info.vbr,
            'abr': format_info.abr,
            'vcodec': format_info.vcodec,
            'acodec': format_info.acodec,
            'protocol': format_info.protocol,
            'url': format_info.url,
            'quality': format_info.quality,
            'quality_score': format_info.quality_score,
            'estimated_size_mb': format_info.estimated_size_mb
        }
    
    def get_quality_recommendations(self, 
                                  available_formats: List[Dict[str, Any]],
                                  user_type: str = 'free') -> Dict[str, Any]:
        """
        Получает рекомендации по качеству для пользователя
        
        Args:
            available_formats: Доступные форматы
            user_type: Тип пользователя
            
        Returns:
            Словарь с рекомендациями
        """
        try:
            formats = [self._parse_format(fmt) for fmt in available_formats]
            formats = [f for f in formats if f is not None and f.height]
            
            if not formats:
                return {'recommendations': []}
            
            allowed_formats = self._filter_by_user_type(formats, user_type)
            
            # Группируем по качеству
            quality_groups = {}
            for fmt in allowed_formats:
                quality = fmt.quality
                if quality not in quality_groups:
                    quality_groups[quality] = []
                quality_groups[quality].append(fmt)
            
            # Создаем рекомендации
            recommendations = []
            for quality, quality_formats in quality_groups.items():
                if not quality:
                    continue
                    
                best_in_quality = self._select_best_from_candidates(quality_formats)
                if best_in_quality:
                    recommendations.append({
                        'quality': quality,
                        'resolution': f"{best_in_quality.width}x{best_in_quality.height}" if best_in_quality.width else None,
                        'estimated_size_mb': round(best_in_quality.estimated_size_mb, 1),
                        'format': best_in_quality.ext,
                        'codec': best_in_quality.vcodec,
                        'recommended': quality == '720p'  # 720p как рекомендованное по умолчанию
                    })
            
            # Сортируем по качеству
            quality_order = ['240p', '360p', '480p', '720p', '1080p', '1440p', '2160p']
            recommendations.sort(key=lambda x: quality_order.index(x['quality']) 
                               if x['quality'] in quality_order else 999)
            
            return {
                'user_type': user_type,
                'size_limit_mb': self.user_size_limits.get(user_type, 100),
                'allowed_qualities': self.user_quality_limits.get(user_type, ['720p']),
                'recommendations': recommendations,
                'auto_selection': self.select_quality(available_formats, 'auto', user_type)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting quality recommendations: {e}")
            return {'recommendations': [], 'error': str(e)}
    
    def estimate_download_time(self, format_info: Dict[str, Any], 
                             connection_speed_mbps: float = 10.0) -> Dict[str, Any]:
        """
        Оценивает время скачивания для формата
        
        Args:
            format_info: Информация о формате
            connection_speed_mbps: Скорость соединения в Mbps
            
        Returns:
            Оценка времени скачивания
        """
        try:
            size_mb = format_info.get('estimated_size_mb', 0)
            if size_mb <= 0:
                return {'estimated_seconds': 0, 'estimated_minutes': 0}
            
            # Учитываем накладные расходы (обычно скачивание на 20-30% медленнее теоретической скорости)
            effective_speed_mbps = connection_speed_mbps * 0.75
            
            # Переводим в MB/s
            speed_mbs = effective_speed_mbps / 8
            
            estimated_seconds = size_mb / speed_mbs
            
            return {
                'estimated_seconds': round(estimated_seconds),
                'estimated_minutes': round(estimated_seconds / 60, 1),
                'file_size_mb': round(size_mb, 1),
                'connection_speed_mbps': connection_speed_mbps
            }
            
        except Exception as e:
            self.logger.error(f"Error estimating download time: {e}")
            return {'estimated_seconds': 0, 'estimated_minutes': 0, 'error': str(e)}