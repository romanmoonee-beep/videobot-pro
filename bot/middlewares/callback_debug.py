"""
VideoBot Pro - Debug Callback Middleware
Middleware для отслеживания необработанных callback'ов
"""

import structlog
from typing import Any, Awaitable, Callable, Dict, List
from collections import defaultdict, Counter
from datetime import datetime, timedelta

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Update

logger = structlog.get_logger(__name__)


class CallbackDebugMiddleware(BaseMiddleware):
    """Middleware для debug callback'ов"""
    
    def __init__(self):
        """Инициализация middleware"""
        self.unhandled_callbacks = Counter()
        self.callback_stats = defaultdict(int)
        self.last_reset = datetime.utcnow()
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]], 
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка callback query"""
        
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)
        
        callback_data = event.data
        user_id = event.from_user.id if event.from_user else None
        
        # Запоминаем все callback'и
        self.callback_stats[callback_data] += 1
        
        try:
            # Выполняем handler
            result = await handler(event, data)
            
            # Если handler вернул None, возможно callback не обработан
            if result is None:
                self.unhandled_callbacks[callback_data] += 1
                
                logger.warning(
                    f"Potentially unhandled callback: {callback_data}",
                    user_id=user_id,
                    count=self.unhandled_callbacks[callback_data]
                )
                
                # Если callback повторяется много раз, логируем как критическую ошибку
                if self.unhandled_callbacks[callback_data] >= 5:
                    logger.error(
                        f"CRITICAL: Callback '{callback_data}' unhandled {self.unhandled_callbacks[callback_data]} times!",
                        user_id=user_id
                    )
            
            return result
            
        except Exception as e:
            # Логируем ошибки в callback'ах
            logger.error(
                f"Error processing callback '{callback_data}': {e}",
                user_id=user_id,
                error_type=type(e).__name__
            )
            raise
    
    def get_debug_stats(self) -> Dict[str, Any]:
        """Получить статистику debug'а"""
        return {
            'total_callbacks': sum(self.callback_stats.values()),
            'unique_callbacks': len(self.callback_stats),
            'unhandled_count': sum(self.unhandled_callbacks.values()),
            'unhandled_unique': len(self.unhandled_callbacks),
            'top_callbacks': self.callback_stats.most_common(10),
            'top_unhandled': self.unhandled_callbacks.most_common(10),
            'last_reset': self.last_reset.isoformat()
        }
    
    def reset_stats(self):
        """Сбросить статистику"""
        self.unhandled_callbacks.clear()
        self.callback_stats.clear()
        self.last_reset = datetime.utcnow()
        logger.info("Debug stats reset")
    
    def get_recommendations(self) -> List[str]:
        """Получить рекомендации по исправлению"""
        recommendations = []
        
        # Проверяем наиболее часто необработанные callback'и
        top_unhandled = self.unhandled_callbacks.most_common(5)
        
        for callback, count in top_unhandled:
            if count >= 3:
                recommendations.append(
                    f"🔴 CRITICAL: Добавить обработчик для '{callback}' (необработан {count} раз)"
                )
            elif count >= 2:
                recommendations.append(
                    f"🟡 WARNING: Проверить обработчик для '{callback}' (необработан {count} раз)"
                )
        
        # Проверяем паттерны
        prefixes = defaultdict(int)
        for callback in self.unhandled_callbacks:
            if '_' in callback:
                prefix = callback.split('_')[0] + '_'
                prefixes[prefix] += 1
        
        for prefix, count in prefixes.items():
            if count >= 2:
                recommendations.append(
                    f"💡 SUGGEST: Создать prefix handler для '{prefix}*' ({count} разных callback'ов)"
                )
        
        return recommendations


# Глобальный экземпляр middleware
debug_middleware = CallbackDebugMiddleware()


def get_callback_debug_info() -> Dict[str, Any]:
    """Получить debug информацию о callback'ах"""
    stats = debug_middleware.get_debug_stats()
    recommendations = debug_middleware.get_recommendations()
    
    return {
        **stats,
        'recommendations': recommendations,
        'health_score': calculate_callback_health_score(stats)
    }


def calculate_callback_health_score(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Рассчитать 'здоровье' callback системы"""
    
    total = stats['total_callbacks']
    unhandled = stats['unhandled_count']
    
    if total == 0:
        return {'score': 100, 'status': 'No callbacks processed'}
    
    success_rate = ((total - unhandled) / total) * 100
    
    if success_rate >= 95:
        status = 'EXCELLENT'
        color = '🟢'
    elif success_rate >= 90:
        status = 'GOOD'
        color = '🟡'
    elif success_rate >= 80:
        status = 'WARNING'
        color = '🟠'
    else:
        status = 'CRITICAL'
        color = '🔴'
    
    return {
        'score': round(success_rate, 1),
        'status': f"{color} {status}",
        'total_processed': total,
        'successful': total - unhandled,
        'failed': unhandled
    }


# Декоратор для debug callback обработчиков
def debug_callback(callback_name: str):
    """Декоратор для debug callback обработчиков"""
    def decorator(func):
        async def wrapper(callback, *args, **kwargs):
            logger.debug(f"Processing callback: {callback_name}", user_id=callback.from_user.id)
            
            try:
                result = await func(callback, *args, **kwargs)
                logger.debug(f"Callback {callback_name} processed successfully")
                return result
            except Exception as e:
                logger.error(f"Error in callback {callback_name}: {e}")
                await callback.answer("Произошла ошибка", show_alert=True)
                raise
        
        return wrapper
    return decorator