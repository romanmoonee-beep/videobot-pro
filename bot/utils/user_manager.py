"""
VideoBot Pro - User Manager
Утилиты для управления пользователями
"""

import structlog
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from shared.models import User, UserType, EventType
from shared.models.analytics import track_user_event
from bot.config import bot_config

logger = structlog.get_logger(__name__)


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    language_code: Optional[str] = None
) -> User:
    """
    Получить или создать пользователя
    
    Args:
        session: Сессия базы данных
        telegram_id: Telegram ID пользователя
        username: Username пользователя
        first_name: Имя пользователя
        last_name: Фамилия пользователя
        language_code: Код языка пользователя
        
    Returns:
        Объект пользователя
    """
    # Пытаемся найти существующего пользователя
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        # Обновляем информацию если она изменилась
        updated = False
        
        if username and user.username != username:
            user.username = username
            updated = True
        
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            updated = True
        
        if last_name and user.last_name != last_name:
            user.last_name = last_name
            updated = True
        
        if language_code and user.language_code != language_code:
            user.language_code = language_code
            updated = True
        
        if updated:
            await session.flush()
            logger.info(f"Updated user info", user_id=telegram_id)
    
    else:
        # Создаем нового пользователя
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            user_type=UserType.FREE,
            created_at=datetime.now(timezone.utc),
            last_active_at=datetime.now(timezone.utc)
            # УБРАЛИ is_active=True - это поле отсутствует в модели
        )
        
        # Проверяем, является ли пользователь админом
        if bot_config.is_admin(telegram_id):
            user.user_type = UserType.ADMIN
            # УБРАЛИ user.is_admin = True - используем user_type
        
        session.add(user)
        await session.flush()
        
        logger.info(f"Created new user", user_id=telegram_id, username=username)
        
        # Трекаем событие регистрации
        await track_user_event(
            event_type=EventType.USER_REGISTERED,
            user_id=user.id,
            telegram_user_id=telegram_id,
            user_type=user.current_user_type
        )
    
    return user


async def update_user_activity(
    session: AsyncSession,
    user: User,
    message_id: Optional[int] = None
) -> None:
    """
    Обновить активность пользователя
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        message_id: ID последнего сообщения
    """
    user.last_active_at = datetime.now(timezone.utc)
    
    if message_id:
        user.last_message_id = message_id
    
    # Увеличиваем счетчик сессий если прошло больше часа
    if not user.last_session_at or (datetime.now(timezone.utc) - user.last_session_at) > timedelta(hours=1):
        user.session_count = (user.session_count or 0) + 1
        user.last_session_at = datetime.now(timezone.utc)
    
    await session.flush()


async def check_user_limits(user: User) -> Dict[str, Any]:
    """
    Проверить лимиты пользователя
    
    Args:
        user: Объект пользователя
        
    Returns:
        Словарь с информацией о лимитах
    """
    user_type = user.current_user_type
    
    # Получаем лимиты для типа пользователя
    daily_limit = bot_config.get_user_daily_limit(user_type)
    file_size_limit = bot_config.get_user_file_limit(user_type)
    batch_size_limit = bot_config.limits.max_batch_size
    
    # Проверяем дневной лимит
    can_download = user.can_download_today()
    downloads_remaining = max(0, daily_limit - user.downloads_today) if daily_limit < 999 else 999
    
    # Проверяем trial статус
    trial_active = user.is_trial_active
    trial_remaining = None
    if trial_active and user.trial_expires_at:
        trial_remaining = user.trial_expires_at - datetime.now(timezone.utc)
    
    # Проверяем premium статус
    premium_active = user.is_premium_active
    premium_remaining = None
    if premium_active and user.premium_expires_at:
        premium_remaining = user.premium_expires_at - datetime.now(timezone.utc)
    
    return {
        'can_download': can_download,
        'daily_limit': daily_limit,
        'downloads_today': user.downloads_today,
        'downloads_remaining': downloads_remaining,
        'file_size_limit': file_size_limit,
        'batch_size_limit': batch_size_limit,
        'user_type': user_type,
        'is_banned': user.is_banned,
        'trial_active': trial_active,
        'trial_remaining': trial_remaining,
        'premium_active': premium_active,
        'premium_remaining': premium_remaining
    }


async def increment_user_downloads(
    session: AsyncSession,
    user: User,
    count: int = 1
) -> bool:
    """
    Увеличить счетчик загрузок пользователя
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        count: Количество загрузок
        
    Returns:
        True если успешно
    """
    try:
        user.increment_downloads(count)
        await session.flush()
        
        # Трекаем событие
        await track_user_event(
            event_type=EventType.DOWNLOAD_COMPLETED,
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            value=count
        )
        
        logger.info(f"Incremented downloads", user_id=user.telegram_id, count=count)
        return True
    
    except Exception as e:
        logger.error(f"Error incrementing downloads: {e}", user_id=user.telegram_id)
        return False


async def reset_user_daily_limits(session: AsyncSession) -> int:
    """
    Сбросить дневные лимиты всех пользователей
    
    Args:
        session: Сессия базы данных
        
    Returns:
        Количество обновленных пользователей
    """
    try:
        # Сбрасываем счетчики для всех пользователей
        result = await session.execute(
            text("UPDATE users SET downloads_today = 0 WHERE downloads_today > 0")
        )
        
        count = result.rowcount
        await session.commit()
        
        logger.info(f"Reset daily limits for {count} users")
        return count
    
    except Exception as e:
        logger.error(f"Error resetting daily limits: {e}")
        return 0


async def ban_user(
    session: AsyncSession,
    user: User,
    reason: str,
    duration_hours: Optional[int] = None,
    banned_by: Optional[int] = None
) -> bool:
    """
    Заблокировать пользователя
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        reason: Причина блокировки
        duration_hours: Длительность блокировки в часах
        banned_by: ID админа, заблокировавшего пользователя
        
    Returns:
        True если успешно
    """
    try:
        if duration_hours:
            # Временная блокировка
            user.ban_user_temporarily(reason, duration_hours)
        else:
            # Постоянная блокировка
            user.ban_user(reason)
        
        if banned_by:
            user.banned_by = banned_by
        
        await session.flush()
        
        # Трекаем событие
        await track_user_event(
            event_type=EventType.USER_BANNED,
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            event_data={
                'reason': reason,
                'duration_hours': duration_hours,
                'banned_by': banned_by
            }
        )
        
        logger.info(f"User banned", user_id=user.telegram_id, reason=reason)
        return True
    
    except Exception as e:
        logger.error(f"Error banning user: {e}", user_id=user.telegram_id)
        return False


async def unban_user(
    session: AsyncSession,
    user: User,
    unbanned_by: Optional[int] = None
) -> bool:
    """
    Разблокировать пользователя
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        unbanned_by: ID админа, разблокировавшего пользователя
        
    Returns:
        True если успешно
    """
    try:
        user.unban_user()
        
        await session.flush()
        
        # Трекаем событие
        await track_user_event(
            event_type=EventType.USER_UNBANNED,
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            event_data={'unbanned_by': unbanned_by}
        )
        
        logger.info(f"User unbanned", user_id=user.telegram_id)
        return True
    
    except Exception as e:
        logger.error(f"Error unbanning user: {e}", user_id=user.telegram_id)
        return False


async def get_user_statistics(user: User) -> Dict[str, Any]:
    """
    Получить подробную статистику пользователя
    
    Args:
        user: Объект пользователя
        
    Returns:
        Словарь со статистикой
    """
    stats = user.stats or {}
    
    # Базовая статистика
    base_stats = {
        'user_id': user.telegram_id,
        'username': user.username,
        'user_type': user.current_user_type,
        'registered_at': user.created_at,
        'last_active': user.last_active_at,
        'total_downloads': user.downloads_total,
        'downloads_today': user.downloads_today,
        'session_count': user.session_count or 0
    }
    
    # Расширенная статистика из JSON поля
    extended_stats = {
        'monthly_downloads': stats.get('monthly_downloads', 0),
        'total_size_mb': stats.get('total_size_mb', 0),
        'avg_file_size_mb': stats.get('avg_file_size_mb', 0),
        'platforms': stats.get('platforms', {}),
        'favorite_platform': max(stats.get('platforms', {'unknown': 0}).items(), 
                                key=lambda x: x[1])[0] if stats.get('platforms') else None,
        'peak_hour': stats.get('peak_hour'),
        'devices_used': stats.get('devices', [])
    }
    
    # Trial статистика
    trial_stats = {}
    if user.trial_used:
        trial_stats = {
            'trial_used': True,
            'trial_started': user.trial_started_at,
            'trial_expired': user.trial_expires_at,
            'trial_downloads': stats.get('trial_downloads', 0)
        }
    
    # Premium статистика
    premium_stats = {}
    if user.is_premium or user.is_premium_expired:
        premium_stats = {
            'premium_active': user.is_premium_active,
            'premium_started': user.premium_started_at,
            'premium_expires': user.premium_expires_at,
            'premium_auto_renew': user.premium_auto_renew,
            'premium_total_spent': stats.get('premium_total_spent', 0)
        }
    
    # Объединяем всю статистику
    return {
        **base_stats,
        **extended_stats,
        **trial_stats,
        **premium_stats
    }