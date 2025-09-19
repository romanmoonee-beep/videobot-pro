"""
VideoBot Pro - Analytics Middleware
Сбор аналитики и метрик
"""

import time
import structlog
from typing import Any, Awaitable, Callable, Dict, Optional
from datetime import datetime

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update, InlineQuery

from shared.config.database import get_async_session
from shared.models import User, EventType
from shared.models.analytics import track_user_event, track_system_event

logger = structlog.get_logger(__name__)


class AnalyticsMiddleware(BaseMiddleware):
    """Middleware для сбора аналитики"""
    
    def __init__(
        self,
        track_commands: bool = True,
        track_callbacks: bool = True,
        track_performance: bool = True
    ):
        """
        Инициализация middleware
        
        Args:
            track_commands: Отслеживать команды
            track_callbacks: Отслеживать callback запросы
            track_performance: Отслеживать производительность
        """
        self.track_commands = track_commands
        self.track_callbacks = track_callbacks
        self.track_performance = track_performance
        
        # Статистика для мониторинга
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_execution_time': 0.0,
            'commands': {},
            'callbacks': {},
            'errors': {}
        }
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        start_time = time.time()
        self.stats['total_requests'] += 1
        
        # Извлекаем информацию о событии
        event_info = self._extract_event_info(event)
        
        try:
            # Передаем управление следующему handler
            result = await handler(event, data)
            
            # Трекаем успешное выполнение
            self.stats['successful_requests'] += 1
            execution_time = time.time() - start_time
            self.stats['total_execution_time'] += execution_time
            
            # Отправляем в аналитику
            await self._track_success(event_info, execution_time)
            
            return result
        
        except Exception as e:
            # Трекаем ошибку
            self.stats['failed_requests'] += 1
            execution_time = time.time() - start_time
            
            error_type = type(e).__name__
            if error_type not in self.stats['errors']:
                self.stats['errors'][error_type] = 0
            self.stats['errors'][error_type] += 1
            
            # Отправляем в аналитику
            await self._track_error(event_info, e, execution_time)
            
            # Пробрасываем ошибку дальше
            raise
    
    def _extract_event_info(self, event: Update) -> Dict[str, Any]:
        """Извлечь информацию о событии"""
        info = {
            'timestamp': datetime.utcnow(),
            'event_type': type(event).__name__
        }
        
        if isinstance(event, Message):
            info.update({
                'user_id': event.from_user.id if event.from_user else None,
                'username': event.from_user.username if event.from_user else None,
                'chat_id': event.chat.id,
                'chat_type': event.chat.type,
                'message_type': 'command' if event.text and event.text.startswith('/') else 'message'
            })
            
            # Трекаем команду
            if event.text and event.text.startswith('/'):
                command = event.text.split()[0].lower()
                info['command'] = command
                
                if self.track_commands:
                    if command not in self.stats['commands']:
                        self.stats['commands'][command] = 0
                    self.stats['commands'][command] += 1
        
        elif isinstance(event, CallbackQuery):
            info.update({
                'user_id': event.from_user.id if event.from_user else None,
                'username': event.from_user.username if event.from_user else None,
                'callback_data': event.data,
                'message_type': 'callback'
            })
            
            # Трекаем callback
            if self.track_callbacks and event.data:
                # Извлекаем префикс callback данных
                callback_prefix = event.data.split('_')[0] if '_' in event.data else event.data
                
                if callback_prefix not in self.stats['callbacks']:
                    self.stats['callbacks'][callback_prefix] = 0
                self.stats['callbacks'][callback_prefix] += 1
        
        return info
    
    async def _track_success(self, event_info: Dict[str, Any], execution_time: float):
        """Отправить успешное событие в аналитику"""
        try:
            if not event_info.get('user_id'):
                return
            
            # Получаем пользователя из БД
            async with get_async_session() as session:
                user = await session.get(User, event_info['user_id'])
                if not user:
                    return
                
                # Определяем тип события
                if event_info.get('command'):
                    event_type = EventType.COMMAND_USED
                    event_data = {
                        'command': event_info['command'],
                        'execution_time': execution_time
                    }
                elif event_info.get('callback_data'):
                    event_type = EventType.CALLBACK_PRESSED
                    event_data = {
                        'callback': event_info['callback_data'],
                        'execution_time': execution_time
                    }
                else:
                    event_type = EventType.MESSAGE_RECEIVED
                    event_data = {
                        'chat_type': event_info.get('chat_type'),
                        'execution_time': execution_time
                    }
                
                # Отправляем событие
                await track_user_event(
                    event_type=event_type,
                    user_id=user.id,
                    telegram_user_id=event_info['user_id'],
                    user_type=user.current_user_type,
                    event_data=event_data
                )
                
                # Трекаем производительность
                if self.track_performance and execution_time > 1.0:
                    await track_system_event(
                        event_type=EventType.SLOW_REQUEST,
                        event_data={
                            'user_id': event_info['user_id'],
                            'command': event_info.get('command'),
                            'callback': event_info.get('callback_data'),
                            'execution_time': execution_time
                        }
                    )
        
        except Exception as e:
            logger.error(f"Error tracking analytics: {e}")
    
    async def _track_error(self, event_info: Dict[str, Any], error: Exception, execution_time: float):
        """Отправить ошибку в аналитику"""
        try:
            # Отправляем системное событие об ошибке
            await track_system_event(
                event_type=EventType.ERROR_OCCURRED,
                event_data={
                    'user_id': event_info.get('user_id'),
                    'error_type': type(error).__name__,
                    'error_message': str(error),
                    'command': event_info.get('command'),
                    'callback': event_info.get('callback_data'),
                    'execution_time': execution_time
                }
            )
            
            # Если есть пользователь, трекаем и для него
            if event_info.get('user_id'):
                async with get_async_session() as session:
                    user = await session.get(User, event_info['user_id'])
                    if user:
                        await track_user_event(
                            event_type=EventType.ERROR_OCCURRED,
                            user_id=user.id,
                            telegram_user_id=event_info['user_id'],
                            event_data={
                                'error_type': type(error).__name__,
                                'error_message': str(error)[:500]
                            }
                        )
        
        except Exception as e:
            logger.error(f"Error tracking error analytics: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику middleware"""
        return {
            'total_requests': self.stats['total_requests'],
            'successful_requests': self.stats['successful_requests'],
            'failed_requests': self.stats['failed_requests'],
            'success_rate': (
                self.stats['successful_requests'] / self.stats['total_requests'] * 100
                if self.stats['total_requests'] > 0 else 0
            ),
            'avg_execution_time': (
                self.stats['total_execution_time'] / self.stats['successful_requests']
                if self.stats['successful_requests'] > 0 else 0
            ),
            'top_commands': sorted(
                self.stats['commands'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            'top_callbacks': sorted(
                self.stats['callbacks'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            'top_errors': sorted(
                self.stats['errors'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }
    
    def reset_stats(self):
        """Сбросить статистику"""
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_execution_time': 0.0,
            'commands': {},
            'callbacks': {},
            'errors': {}
        }