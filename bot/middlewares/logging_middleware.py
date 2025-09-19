"""
VideoBot Pro - Logging Middleware
Логирование всех событий бота
"""

import structlog
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update

logger = structlog.get_logger(__name__)

class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования событий"""
    
    def __init__(self):
        """Инициализация middleware"""
        pass
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка события"""
        start_time = time.time()
        
        # Извлекаем информацию о событии
        event_info = self._extract_event_info(event)
        
        logger.info(
            "Processing event",
            event_type=event_info['type'],
            user_id=event_info.get('user_id'),
            username=event_info.get('username')
        )
        
        try:
            # Выполняем handler
            result = await handler(event, data)
            
            execution_time = time.time() - start_time
            
            logger.info(
                "Event processed successfully",
                event_type=event_info['type'],
                user_id=event_info.get('user_id'),
                execution_time=round(execution_time, 3)
            )
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            logger.error(
                "Error processing event",
                event_type=event_info['type'],
                user_id=event_info.get('user_id'),
                error=str(e),
                execution_time=round(execution_time, 3)
            )
            
            raise
    
    def _extract_event_info(self, event: Update) -> Dict[str, Any]:
        """Извлечь информацию о событии"""
        info = {
            'type': type(event).__name__
        }
        
        if isinstance(event, Message):
            info.update({
                'user_id': event.from_user.id if event.from_user else None,
                'username': event.from_user.username if event.from_user else None,
                'chat_type': event.chat.type,
                'has_text': bool(event.text),
                'has_media': bool(event.photo or event.video or event.document)
            })
            
            if event.text and event.text.startswith('/'):
                info['command'] = event.text.split()[0]
        
        elif isinstance(event, CallbackQuery):
            info.update({
                'user_id': event.from_user.id if event.from_user else None,
                'username': event.from_user.username if event.from_user else None,
                'callback_data': event.data
            })
        
        return info