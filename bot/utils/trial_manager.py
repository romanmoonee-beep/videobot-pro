"""
VideoBot Pro - Trial Manager
Управление пробным периодом
"""

import structlog
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from shared.models import User, UserType, EventType
from shared.models.analytics import track_user_event
from bot.config import bot_config

logger = structlog.get_logger(__name__)


async def activate_trial(
    session: AsyncSession,
    user: User
) -> Dict[str, Any]:
    """
    Активировать пробный период для пользователя
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        
    Returns:
        Результат активации
    """
    # Проверяем возможность активации
    if not bot_config.trial_enabled:
        return {
            'success': False,
            'error': 'trial_disabled',
            'message': 'Пробный период временно недоступен'
        }
    
    if user.trial_used:
        return {
            'success': False,
            'error': 'already_used',
            'message': 'Вы уже использовали пробный период'
        }
    
    if user.is_premium_active:
        return {
            'success': False,
            'error': 'premium_active',
            'message': 'У вас уже активен Premium'
        }
    
    try:
        # Активируем trial
        duration_minutes = bot_config.trial_duration_minutes
        user.activate_trial(duration_minutes)
        
        await session.flush()
        
        # Трекаем событие
        await track_user_event(
            event_type=EventType.TRIAL_ACTIVATED,
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            user_type=UserType.TRIAL
        )
        
        logger.info(f"Trial activated", user_id=user.telegram_id, duration=duration_minutes)
        
        return {
            'success': True,
            'expires_at': user.trial_expires_at,
            'duration_minutes': duration_minutes,
            'message': f'Пробный период активирован на {duration_minutes} минут!'
        }
    
    except Exception as e:
        logger.error(f"Error activating trial: {e}", user_id=user.telegram_id)
        return {
            'success': False,
            'error': 'activation_failed',
            'message': 'Ошибка активации пробного периода'
        }


async def check_trial_status(user: User) -> Dict[str, Any]:
    """
    Проверить статус пробного периода
    
    Args:
        user: Объект пользователя
        
    Returns:
        Информация о статусе
    """
    if not user.trial_used:
        return {
            'status': 'available',
            'can_activate': True,
            'message': 'Пробный период доступен для активации'
        }
    
    if user.is_trial_active:
        remaining = get_trial_time_remaining(user)
        return {
            'status': 'active',
            'expires_at': user.trial_expires_at,
            'remaining_seconds': int(remaining.total_seconds()) if remaining else 0,
            'remaining_formatted': format_time_remaining(remaining) if remaining else 'истекает',
            'message': f'Пробный период активен'
        }
    
    return {
        'status': 'expired',
        'expired_at': user.trial_expires_at,
        'message': 'Пробный период использован'
    }


def get_trial_time_remaining(user: User) -> Optional[timedelta]:
    """
    Получить оставшееся время пробного периода
    
    Args:
        user: Объект пользователя
        
    Returns:
        Оставшееся время или None
    """
    if not user.is_trial_active or not user.trial_expires_at:
        return None
    
    remaining = user.trial_expires_at - datetime.utcnow()
    
    if remaining.total_seconds() <= 0:
        return None
    
    return remaining


async def expire_trial(
    session: AsyncSession,
    user: User
) -> bool:
    """
    Принудительно завершить пробный период
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        
    Returns:
        True если успешно
    """
    if not user.is_trial_active:
        return False
    
    try:
        # Устанавливаем время истечения на текущее
        user.trial_expires_at = datetime.utcnow()
        user.user_type = UserType.FREE
        
        await session.flush()
        
        # Трекаем событие
        await track_user_event(
            event_type=EventType.TRIAL_EXPIRED,
            user_id=user.id,
            telegram_user_id=user.telegram_id
        )
        
        logger.info(f"Trial expired", user_id=user.telegram_id)
        return True
    
    except Exception as e:
        logger.error(f"Error expiring trial: {e}", user_id=user.telegram_id)
        return False


async def check_and_expire_trials(session: AsyncSession) -> int:
    """
    Проверить и завершить истекшие пробные периоды
    
    Args:
        session: Сессия базы данных
        
    Returns:
        Количество завершенных периодов
    """
    try:
        # Находим пользователей с истекшим trial
        result = await session.execute(
            """
            UPDATE users 
            SET user_type = 'free'
            WHERE user_type = 'trial' 
            AND trial_expires_at < NOW()
            RETURNING id
            """
        )
        
        expired_ids = result.fetchall()
        count = len(expired_ids)
        
        if count > 0:
            await session.commit()
            
            # Трекаем события для каждого
            for user_id in expired_ids:
                await track_user_event(
                    event_type=EventType.TRIAL_EXPIRED,
                    user_id=user_id[0],
                    telegram_user_id=None
                )
            
            logger.info(f"Expired {count} trial periods")
        
        return count
    
    except Exception as e:
        logger.error(f"Error checking trial expiry: {e}")
        return 0


def format_time_remaining(remaining: Optional[timedelta]) -> str:
    """
    Форматировать оставшееся время
    
    Args:
        remaining: Оставшееся время
        
    Returns:
        Отформатированная строка
    """
    if not remaining:
        return "истекло"
    
    total_seconds = int(remaining.total_seconds())
    
    if total_seconds <= 0:
        return "истекло"
    
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours}ч {minutes}м"
    elif minutes > 0:
        return f"{minutes}м {seconds}с"
    else:
        return f"{seconds}с"


async def send_trial_reminder(
    bot,
    user: User,
    minutes_remaining: int
) -> bool:
    """
    Отправить напоминание об истечении пробного периода
    
    Args:
        bot: Экземпляр бота
        user: Объект пользователя
        minutes_remaining: Минут осталось
        
    Returns:
        True если отправлено
    """
    try:
        message = f"""
⏰ <b>Пробный период скоро закончится!</b>

Осталось: {minutes_remaining} минут

💎 Успейте оформить Premium со скидкой 20%!
Используйте команду /premium
"""
        
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode='HTML'
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Error sending trial reminder: {e}", user_id=user.telegram_id)
        return False