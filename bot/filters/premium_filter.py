"""
VideoBot Pro - Premium Filter
Фильтры для проверки Premium статуса и подписок
"""

from typing import Union, List, Optional
from datetime import datetime
from aiogram import types
from aiogram.filters import BaseFilter

from sqlalchemy import text

from shared.config.database import get_async_session
from shared.models import User
from bot.config import bot_config

class PremiumFilter(BaseFilter):
    """Фильтр для Premium пользователей"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка Premium статуса"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                is_premium = user.is_premium_active
                
                if not is_premium:
                    return False
                
                return {
                    'user_id': user_id,
                    'is_premium': True,
                    'premium_expires_at': user.premium_expires_at,
                    'auto_renew': user.premium_auto_renew
                }
                
        except Exception:
            return False

class TrialFilter(BaseFilter):
    """Фильтр для пользователей с активным Trial"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка активного Trial"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                is_trial = user.is_trial_active
                
                if not is_trial:
                    return False
                
                return {
                    'user_id': user_id,
                    'is_trial': True,
                    'trial_expires_at': user.trial_expires_at,
                    'trial_used': user.trial_used
                }
                
        except Exception:
            return False

class FreeUserFilter(BaseFilter):
    """Фильтр для бесплатных пользователей"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка бесплатного статуса"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                # Бесплатный = не Premium и не Trial
                is_free = (user.current_user_type == "free" and 
                          not user.is_premium_active and 
                          not user.is_trial_active)
                
                if not is_free:
                    return False
                
                return {
                    'user_id': user_id,
                    'is_free': True,
                    'downloads_today': user.downloads_today,
                    'daily_limit': bot_config.get_user_daily_limit('free')
                }
                
        except Exception:
            return False

class UserTypeFilter(BaseFilter):
    """Фильтр для конкретного типа пользователя"""
    
    def __init__(self, user_types: Union[str, List[str]]):
        """
        Args:
            user_types: Тип(ы) пользователя (free, trial, premium, admin)
        """
        if isinstance(user_types, str):
            self.user_types = [user_types]
        else:
            self.user_types = user_types
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка типа пользователя"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                user_type = user.current_user_type
                
                if user_type not in self.user_types:
                    return False
                
                return {
                    'user_id': user_id,
                    'user_type': user_type,
                    'matches_filter': True
                }
                
        except Exception:
            return False

class LimitCheckFilter(BaseFilter):
    """Фильтр для проверки лимитов пользователя"""
    
    def __init__(self, check_daily: bool = True, check_file_size: bool = False):
        """
        Args:
            check_daily: Проверять дневной лимит
            check_file_size: Проверять лимит размера файла
        """
        self.check_daily = check_daily
        self.check_file_size = check_file_size
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка лимитов"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                result = {
                    'user_id': user_id,
                    'user_type': user.current_user_type,
                    'can_download': True,
                    'limits': {}
                }
                
                # Проверка дневного лимита
                if self.check_daily:
                    daily_limit = bot_config.get_user_daily_limit(user.current_user_type)
                    can_download_today = user.can_download_today()
                    
                    result['limits']['daily'] = {
                        'limit': daily_limit,
                        'used': user.downloads_today,
                        'remaining': max(0, daily_limit - user.downloads_today) if daily_limit < 999 else 999,
                        'can_download': can_download_today
                    }
                    
                    if not can_download_today:
                        result['can_download'] = False
                
                # Проверка лимита размера файла
                if self.check_file_size:
                    file_limit = bot_config.get_user_file_limit(user.current_user_type)
                    result['limits']['file_size'] = {
                        'limit_mb': file_limit
                    }
                
                return result if result['can_download'] else False
                
        except Exception:
            return False

class SubscriptionRequiredFilter(BaseFilter):
    """Фильтр для проверки обязательных подписок"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка подписок на каналы"""
        if not message.from_user:
            return False
        
        # Если подписки не требуются
        if not bot_config.required_subs_enabled:
            return True
        
        user_id = message.from_user.id
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                # Premium и admin пользователи освобождены
                if user.current_user_type in ['premium', 'admin']:
                    return True
                
                # Проверяем последнюю проверку подписок
                subscription_passed = user.subscription_check_passed
                
                # Если проверка не пройдена или устарела
                if not subscription_passed:
                    return False
                
                # Проверяем время последней проверки (не старше 1 часа)
                if user.last_subscription_check:
                    time_since_check = datetime.utcnow() - user.last_subscription_check
                    if time_since_check.total_seconds() > 3600:  # 1 час
                        return False
                
                return {
                    'user_id': user_id,
                    'subscription_check_passed': True,
                    'last_check': user.last_subscription_check
                }
                
        except Exception:
            return False

class BannedUserFilter(BaseFilter):
    """Фильтр для проверки заблокированных пользователей"""
    
    def __init__(self, block_banned: bool = True):
        """
        Args:
            block_banned: True - блокировать заблокированных, False - пропускать только заблокированных
        """
        self.block_banned = block_banned
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка статуса блокировки"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                
                if not user:
                    return False
                
                is_banned = user.is_banned
                
                # Если нужно блокировать заблокированных
                if self.block_banned:
                    return not is_banned
                # Если нужно пропускать только заблокированных
                else:
                    if not is_banned:
                        return False
                    
                    return {
                        'user_id': user_id,
                        'is_banned': True,
                        'ban_reason': user.ban_reason,
                        'banned_until': user.banned_until
                    }
                
        except Exception:
            return False

class PremiumFeatureFilter(BaseFilter):
    """Фильтр для Premium функций"""
    
    def __init__(self, feature: str):
        """
        Args:
            feature: Название Premium функции
        """
        self.feature = feature
        self.premium_features = {
            '4k_quality': 'premium',
            'unlimited_downloads': 'premium', 
            'batch_archive': 'premium',
            'custom_quality': 'premium',
            'no_subscriptions': 'premium',
            'priority_queue': 'premium'
        }

    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        if not message.from_user:
            return False

        user_id = message.from_user.id

        if self.feature not in self.premium_features:
            return True

        try:
            async with get_async_session() as session:
                result = await session.execute(
                    text("SELECT * FROM users WHERE telegram_id = :user_id"),
                    {'user_id': user_id}
                )
                user = result.first()

                if not user or not user.is_premium_active:
                    return False

                return {
                    'user_id': user_id,
                    'feature_available': True,
                    'user_type': user.current_user_type
                }
        except Exception:
            return False

