"""
VideoBot Pro - Processors Package
Процессоры для обработки видео и связанных задач
"""

from .base import BaseProcessor, ProcessingError, ValidationError, ResourceError, TimeoutError
from .video_processor import VideoProcessor
from .thumbnail_generator import ThumbnailGenerator
from .quality_optimizer import QualityOptimizer
from .batch_processor import BatchProcessor

__all__ = [
    # Базовые классы
    'BaseProcessor',
    'ProcessingError',
    'ValidationError', 
    'ResourceError',
    'TimeoutError',
    
    # Процессоры
    'VideoProcessor',
    'ThumbnailGenerator',
    'QualityOptimizer',
    'BatchProcessor',
]

# Информация о пакете
PROCESSORS_VERSION = "1.0.0"

# Фабрика процессоров
def create_processor(processor_type: str, **kwargs):
    """
    Создает экземпляр процессора по типу
    
    Args:
        processor_type: Тип процессора ('video', 'thumbnail', 'quality', 'batch')
        **kwargs: Параметры для инициализации процессора
        
    Returns:
        Экземпляр процессора
    """
    processors = {
        'video': VideoProcessor,
        'thumbnail': ThumbnailGenerator,
        'quality': QualityOptimizer,
        'batch': BatchProcessor,
    }
    
    processor_class = processors.get(processor_type.lower())
    if not processor_class:
        raise ValueError(f"Unknown processor type: {processor_type}")
    
    return processor_class(**kwargs)

# Получение всех доступных процессоров
def get_available_processors():
    """Возвращает список доступных типов процессоров"""
    return ['video', 'thumbnail', 'quality', 'batch']

# Проверка зависимостей
def check_dependencies():
    """
    Проверяет наличие необходимых зависимостей для работы процессоров
    
    Returns:
        Dict с результатами проверки
    """
    dependencies = {
        'ffmpeg': False,
        'ffprobe': False,
        'PIL': False,
    }
    
    # Проверяем ffmpeg
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        dependencies['ffmpeg'] = result.returncode == 0
    except:
        pass
    
    # Проверяем ffprobe
    try:
        import subprocess
        result = subprocess.run(['ffprobe', '-version'], 
                              capture_output=True, text=True, timeout=5)
        dependencies['ffprobe'] = result.returncode == 0
    except:
        pass
    
    # Проверяем PIL
    try:
        from PIL import Image
        dependencies['PIL'] = True
    except ImportError:
        pass
    
    return dependencies