"""
VideoBot Pro - Utils Package
Утилитарные модули для worker'а
"""

from .file_manager import FileManager, FileManagerError
from .progress_tracker import ProgressTracker, ProgressTrackerError
from .quality_selector import QualitySelector, QualitySelectorError

__all__ = [
    # File Manager
    'FileManager',
    'FileManagerError',
    
    # Progress Tracker
    'ProgressTracker', 
    'ProgressTrackerError',
    
    # Quality Selector
    'QualitySelector',
    'QualitySelectorError',
]

# Версия пакета utils
UTILS_VERSION = "1.0.0"

# Информация о пакете
def get_utils_info():
    """Получить информацию о пакете utils"""
    return {
        'version': UTILS_VERSION,
        'modules': [
            'file_manager',
            'progress_tracker', 
            'quality_selector'
        ],
        'description': 'VideoBot Pro Worker Utilities'
    }

# Проверка зависимостей utils
def check_utils_dependencies():
    """Проверяет доступность зависимостей для utils"""
    dependencies = {
        'aiofiles': False,
        'structlog': False,
        'pathlib': False,
    }
    
    # Проверяем aiofiles
    try:
        import aiofiles
        dependencies['aiofiles'] = True
    except ImportError:
        pass
    
    # Проверяем structlog
    try:
        import structlog
        dependencies['structlog'] = True
    except ImportError:
        pass
    
    # Проверяем pathlib (должен быть в стандартной библиотеке)
    try:
        from pathlib import Path
        dependencies['pathlib'] = True
    except ImportError:
        pass
    
    return dependencies

# Функция инициализации utils
def initialize_utils():
    """Инициализация пакета utils"""
    import structlog
    logger = structlog.get_logger(__name__)
    
    logger.info(f"Initializing VideoBot Pro Utils v{UTILS_VERSION}")
    
    # Проверяем зависимости
    deps = check_utils_dependencies()
    missing_deps = [dep for dep, available in deps.items() if not available]
    
    if missing_deps:
        logger.warning(f"Missing dependencies: {', '.join(missing_deps)}")
    else:
        logger.info("All utils dependencies are available")
    
    logger.info("Utils package initialized successfully")
    return True

# Автоматическая инициализация при импорте
try:
    initialize_utils()
except Exception as e:
    import structlog
    logger = structlog.get_logger(__name__)
    logger.error(f"Failed to initialize utils package: {e}")

print(f"📦 VideoBot Pro Utils v{UTILS_VERSION} loaded")