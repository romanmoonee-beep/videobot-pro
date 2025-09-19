"""
VideoBot Pro - Base Processor
Базовый класс для всех процессоров
"""

import asyncio
import structlog
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

logger = structlog.get_logger(__name__)

class BaseProcessor(ABC):
    """Базовый класс для всех процессоров видео"""
    
    def __init__(self):
        """Инициализация базового процессора"""
        self.logger = logger.bind(processor=self.__class__.__name__)
        self._processing_start_time = None
        self._stats = {
            'processed_count': 0,
            'success_count': 0,
            'error_count': 0,
            'total_processing_time': 0.0
        }
    
    def start_processing(self):
        """Начинает отслеживание времени обработки"""
        self._processing_start_time = datetime.now()
    
    def end_processing(self, success: bool = True):
        """Завершает отслеживание времени и обновляет статистику"""
        if self._processing_start_time:
            processing_time = (datetime.now() - self._processing_start_time).total_seconds()
            self._stats['total_processing_time'] += processing_time
            self._processing_start_time = None
        
        self._stats['processed_count'] += 1
        if success:
            self._stats['success_count'] += 1
        else:
            self._stats['error_count'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику процессора"""
        stats = self._stats.copy()
        if stats['processed_count'] > 0:
            stats['average_processing_time'] = stats['total_processing_time'] / stats['processed_count']
            stats['success_rate'] = (stats['success_count'] / stats['processed_count']) * 100
        else:
            stats['average_processing_time'] = 0.0
            stats['success_rate'] = 0.0
        
        return stats
    
    def reset_stats(self):
        """Сбрасывает статистику"""
        self._stats = {
            'processed_count': 0,
            'success_count': 0,
            'error_count': 0,
            'total_processing_time': 0.0
        }
    
    async def validate_input(self, *args, **kwargs) -> bool:
        """
        Валидирует входные параметры
        
        Returns:
            True если параметры валидны
        """
        return True
    
    async def cleanup_resources(self):
        """Очищает ресурсы процессора"""
        pass
    
    def __enter__(self):
        """Контекстный менеджер - вход"""
        self.start_processing()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер - выход"""
        success = exc_type is None
        self.end_processing(success)
        return False  # Не подавляем исключения
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        self.start_processing()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        success = exc_type is None
        self.end_processing(success)
        await self.cleanup_resources()
        return False  # Не подавляем исключения

class ProcessingError(Exception):
    """Базовое исключение для ошибок обработки"""
    
    def __init__(self, message: str, processor: str = None, details: Dict[str, Any] = None):
        self.processor = processor
        self.details = details or {}
        super().__init__(message)

class ValidationError(ProcessingError):
    """Исключение для ошибок валидации"""
    pass

class ResourceError(ProcessingError):
    """Исключение для ошибок ресурсов"""
    pass

class TimeoutError(ProcessingError):
    """Исключение для таймаута обработки"""
    pass