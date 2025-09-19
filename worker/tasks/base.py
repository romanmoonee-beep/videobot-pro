"""
VideoBot Pro - Base Task Utilities
Базовые утилиты для задач
"""

import asyncio
import structlog
from typing import Dict, Any, Callable, Optional
from functools import wraps
from datetime import datetime
import time

logger = structlog.get_logger(__name__)

def async_task_wrapper(async_func: Callable) -> Callable:
    """
    Декоратор для обертки async функций в Celery задачи
    
    Args:
        async_func: Асинхронная функция
        
    Returns:
        Синхронная обертка
    """
    @wraps(async_func)
    def sync_wrapper(*args, **kwargs):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(async_func(*args, **kwargs))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Error in async task wrapper: {e}")
            raise
    
    return sync_wrapper

class TaskTracker:
    """Отслеживание состояния задач"""
    
    def __init__(self, task_id: str, task_name: str = None):
        self.task_id = task_id
        self.task_name = task_name or "Unknown Task"
        self.start_time = time.time()
        self.logger = logger.bind(task_id=task_id, task_name=self.task_name)
    
    def log_start(self, message: str = None):
        """Логирование начала задачи"""
        msg = message or f"Starting {self.task_name}"
        self.logger.info(msg)
    
    def log_progress(self, progress: float, message: str = None):
        """Логирование прогресса"""
        msg = message or f"Progress: {progress:.1f}%"
        self.logger.info(msg, progress=progress)
    
    def log_success(self, result: Dict[str, Any] = None, message: str = None):
        """Логирование успешного завершения"""
        duration = time.time() - self.start_time
        msg = message or f"{self.task_name} completed successfully"
        self.logger.info(msg, duration=duration, result=result)
    
    def log_error(self, error: Exception, message: str = None):
        """Логирование ошибки"""
        duration = time.time() - self.start_time
        msg = message or f"{self.task_name} failed"
        self.logger.error(msg, error=str(error), duration=duration, exc_info=True)

def safe_db_operation(operation: Callable) -> Callable:
    """
    Декоратор для безопасных операций с БД
    
    Args:
        operation: Функция для выполнения
        
    Returns:
        Обернутая функция
    """
    @wraps(operation)
    async def wrapper(*args, **kwargs):
        try:
            from shared.config.database import get_async_session
            async with get_async_session() as session:
                return await operation(session, *args, **kwargs)
        except Exception as e:
            logger.error(f"Database operation failed: {e}")
            raise
    
    return wrapper

def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """
    Декоратор для повторных попыток при ошибке
    
    Args:
        max_retries: Максимальное количество попыток
        delay: Задержка между попытками в секундах
        
    Returns:
        Декоратор
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                        await asyncio.sleep(delay * (2 ** attempt))  # Exponential backoff
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed")
                        raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                        time.sleep(delay * (2 ** attempt))
                    else:
                        logger.error(f"All {max_retries + 1} attempts failed")
                        raise last_exception
        
        # Возвращаем подходящую обертку
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def task_timeout(timeout_seconds: int):
    """
    Декоратор для таймаута задач
    
    Args:
        timeout_seconds: Таймаут в секундах
        
    Returns:
        Декоратор
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(f"Task timed out after {timeout_seconds} seconds")
                raise
        
        # Для синхронных функций timeout не применяется
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

class BaseTaskResult:
    """Базовый класс для результатов задач"""
    
    def __init__(self, success: bool = True, error: str = None, data: Dict[str, Any] = None):
        self.success = success
        self.error = error
        self.data = data or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        return {
            'success': self.success,
            'error': self.error,
            'data': self.data,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def success_result(cls, data: Dict[str, Any] = None) -> 'BaseTaskResult':
        """Создать успешный результат"""
        return cls(success=True, data=data)
    
    @classmethod
    def error_result(cls, error: str, data: Dict[str, Any] = None) -> 'BaseTaskResult':
        """Создать результат с ошибкой"""
        return cls(success=False, error=error, data=data)

def validate_task_params(**validators):
    """
    Декоратор для валидации параметров задач
    
    Args:
        **validators: Словарь валидаторов {param_name: validator_func}
        
    Returns:
        Декоратор
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Валидируем параметры
            for param_name, validator in validators.items():
                if param_name in kwargs:
                    value = kwargs[param_name]
                    try:
                        if not validator(value):
                            raise ValueError(f"Invalid value for {param_name}: {value}")
                    except Exception as e:
                        raise ValueError(f"Validation failed for {param_name}: {e}")
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator

# Общие валидаторы
def validate_positive_int(value: Any) -> bool:
    """Валидатор для положительных чисел"""
    return isinstance(value, int) and value > 0

def validate_non_empty_string(value: Any) -> bool:
    """Валидатор для непустых строк"""
    return isinstance(value, str) and len(value.strip()) > 0

def validate_url(value: Any) -> bool:
    """Валидатор для URL"""
    import re
    if not isinstance(value, str):
        return False
    
    url_pattern = re.compile(
        r'^https?://'  # http:// или https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ip
        r'(?::\d+)?'  # port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return bool(url_pattern.match(value))

def validate_file_path(value: Any) -> bool:
    """Валидатор для путей к файлам"""
    import os
    return isinstance(value, str) and os.path.exists(value)

# Утилиты для работы с результатами задач
def standardize_task_result(func: Callable) -> Callable:
    """
    Декоратор для стандартизации результатов задач
    
    Args:
        func: Функция задачи
        
    Returns:
        Обернутая функция
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            
            # Если результат уже в нужном формате
            if isinstance(result, dict) and 'success' in result:
                return result
            
            # Стандартизируем результат
            return {
                'success': True,
                'data': result,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'timestamp': datetime.utcnow().isoformat()
            }
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            
            if isinstance(result, dict) and 'success' in result:
                return result
            
            return {
                'success': True,
                'data': result,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'timestamp': datetime.utcnow().isoformat()
            }
    
    import inspect
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
    
    return decorator

# Экспорт основных компонентов
__all__ = [
    'async_task_wrapper',
    'TaskTracker',
    'safe_db_operation',
    'retry_on_failure',
    'task_timeout',
    'BaseTaskResult',
    'validate_task_params',
    'standardize_task_result',
    'validate_positive_int',
    'validate_non_empty_string',
    'validate_url',
    'validate_file_path',
]