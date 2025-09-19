"""
VideoBot Pro - Premium Manager
Управление Premium подписками
"""

import structlog
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from shared.models import User, UserType, Payment, PaymentStatus, EventType
from shared.models.analytics import track_payment_event, track_user_event
from bot.config import bot_config

logger = structlog.get_logger(__name__)


async def activate_premium(
    session: AsyncSession,
    user: User,
    duration_days: int,
    payment_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Активировать Premium подписку
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        duration_days: Длительность в днях
        payment_id: ID платежа
        
    Returns:
        Результат активации
    """
    try:
        # Активируем premium
        user.activate_premium(duration_days)
        
        await session.flush()
        
        # Трекаем события
        await track_user_event(
            event_type=EventType.PREMIUM_ACTIVATED,
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            user_type=UserType.PREMIUM,
            event_data={
                'duration_days': duration_days,
                'payment_id': payment_id
            }
        )
        
        logger.info(
            f"Premium activated",
            user_id=user.telegram_id,
            duration_days=duration_days,
            payment_id=payment_id
        )
        
        return {
            'success': True,
            'expires_at': user.premium_expires_at,
            'duration_days': duration_days,
            'message': f'Premium активирован на {duration_days} дней!'
        }
    
    except Exception as e:
        logger.error(f"Error activating premium: {e}", user_id=user.telegram_id)
        return {
            'success': False,
            'error': 'activation_failed',
            'message': 'Ошибка активации Premium'
        }


async def check_premium_status(user: User) -> Dict[str, Any]:
    """
    Проверить статус Premium подписки
    
    Args:
        user: Объект пользователя
        
    Returns:
        Информация о статусе
    """
    if not user.is_premium and not user.is_premium_expired:
        return {
            'status': 'never_had',
            'can_purchase': True,
            'message': 'Premium не активирован'
        }
    
    if user.is_premium_active:
        remaining = user.premium_expires_at - datetime.utcnow() if user.premium_expires_at else None
        return {
            'status': 'active',
            'expires_at': user.premium_expires_at,
            'auto_renew': user.premium_auto_renew,
            'remaining_days': remaining.days if remaining else 0,
            'message': 'Premium активен'
        }
    
    return {
        'status': 'expired',
        'expired_at': user.premium_expires_at,
        'can_renew': True,
        'message': 'Premium истек'
    }


async def process_premium_payment(
    session: AsyncSession,
    user: User,
    payment: Payment
) -> Dict[str, Any]:
    """
    Обработать платеж за Premium
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        payment: Объект платежа
        
    Returns:
        Результат обработки
    """
    try:
        # Проверяем статус платежа
        if payment.status != PaymentStatus.COMPLETED:
            return {
                'success': False,
                'error': 'payment_not_completed',
                'message': 'Платеж не завершен'
            }
        
        # Определяем длительность по плану подписки
        duration_days = {
            'monthly': 30,
            'quarterly': 90,
            'yearly': 365
        }.get(payment.subscription_plan, 30)
        
        # Активируем premium
        result = await activate_premium(
            session=session,
            user=user,
            duration_days=duration_days,
            payment_id=payment.payment_id
        )
        
        if result['success']:
            # Обновляем платеж
            payment.mark_as_applied()
            await session.flush()
            
            # Трекаем событие платежа
            await track_payment_event(
                event_type=EventType.PAYMENT_COMPLETED,
                user_id=user.id,
                payment_amount=float(payment.amount),
                payment_method=payment.payment_method
            )
        
        return result
    
    except Exception as e:
        logger.error(f"Error processing payment: {e}", user_id=user.telegram_id)
        return {
            'success': False,
            'error': 'processing_failed',
            'message': 'Ошибка обработки платежа'
        }


async def cancel_premium_subscription(
    session: AsyncSession,
    user: User
) -> Dict[str, Any]:
    """
    Отменить автопродление Premium подписки
    
    Args:
        session: Сессия базы данных
        user: Объект пользователя
        
    Returns:
        Результат отмены
    """
    try:
        if not user.is_premium_active:
            return {
                'success': False,
                'error': 'no_active_subscription',
                'message': 'Нет активной подписки'
            }
        
        # Отключаем автопродление
        user.premium_auto_renew = False
        await session.flush()
        
        # Трекаем событие
        await track_user_event(
            event_type=EventType.PREMIUM_CANCELLED,
            user_id=user.id,
            telegram_user_id=user.telegram_id
        )
        
        logger.info(f"Premium auto-renew cancelled", user_id=user.telegram_id)
        
        return {
            'success': True,
            'expires_at': user.premium_expires_at,
            'message': 'Автопродление отключено'
        }
    
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}", user_id=user.telegram_id)
        return {
            'success': False,
            'error': 'cancellation_failed',
            'message': 'Ошибка отмены подписки'
        }


async def check_and_expire_premium(session: AsyncSession) -> int:
    """
    Проверить и завершить истекшие Premium подписки
    
    Args:
        session: Сессия базы данных
        
    Returns:
        Количество истекших подписок
    """
    try:
        # Находим пользователей с истекшим premium
        result = await session.execute(
            """
            UPDATE users 
            SET user_type = 'free', is_premium = false
            WHERE is_premium = true
            AND premium_expires_at < NOW()
            AND premium_auto_renew = false
            RETURNING id, telegram_id
            """
        )
        
        expired = result.fetchall()
        count = len(expired)
        
        if count > 0:
            await session.commit()
            
            # Трекаем события
            for user_id, telegram_id in expired:
                await track_user_event(
                    event_type=EventType.PREMIUM_EXPIRED,
                    user_id=user_id,
                    telegram_user_id=telegram_id
                )
            
            logger.info(f"Expired {count} premium subscriptions")
        
        return count
    
    except Exception as e:
        logger.error(f"Error checking premium expiry: {e}")
        return 0


async def send_premium_reminder(
    bot,
    user: User,
    days_remaining: int
) -> bool:
    """
    Отправить напоминание об истечении Premium
    
    Args:
        bot: Экземпляр бота
        user: Объект пользователя
        days_remaining: Дней осталось
        
    Returns:
        True если отправлено
    """
    try:
        message = f"""
💎 <b>Ваша Premium подписка скоро закончится!</b>

Осталось дней: {days_remaining}

{'🔄 Автопродление включено' if user.premium_auto_renew else '⚠️ Автопродление отключено'}

Продлите подписку чтобы сохранить:
- Безлимитные загрузки
- 4K качество
- Приоритетную поддержку

Используйте /premium для продления
"""
        
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode='HTML'
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Error sending premium reminder: {e}", user_id=user.telegram_id)
        return False