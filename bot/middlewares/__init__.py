"""
VideoBot Pro - Middlewares Package
Middleware компоненты для бота
"""

from .callback_debug import CallbackDebugMiddleware

from .rate_limit import RateLimitMiddleware, rate_limit
from .admin_only import AdminOnlyMiddleware, admin_only
from .auth import (
    AuthMiddleware, 
    RequireAuthMiddleware, 
    UserTypeMiddleware,
    require_auth,
    require_user_type,
    premium_required,
    admin_required,
    get_current_user,
    get_telegram_user,
    is_authenticated,
    has_user_type,
    is_premium,
    is_admin
)
from .analytics import AnalyticsMiddleware

from aiogram import Dispatcher

def setup_middlewares(dp: Dispatcher) -> None:
    """
    Настройка всех middleware для диспетчера
    
    Args:
        dp: Диспетчер aiogram
    """
    # Порядок важен! Middleware выполняются в порядке регистрации
    
    # Authentication and user management (создаем/получаем пользователя)
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    # Rate limiting
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    
    # Analytics (последним для сбора полных данных)
    dp.message.middleware(AnalyticsMiddleware())
    dp.callback_query.middleware(AnalyticsMiddleware())

    dp.callback_query.middleware(CallbackDebugMiddleware())

__all__ = [
    'setup_middlewares',
    'RateLimitMiddleware',
    'rate_limit',
    'AdminOnlyMiddleware', 
    'admin_only',
    'AuthMiddleware',
    'RequireAuthMiddleware',
    'UserTypeMiddleware',
    'AnalyticsMiddleware',
    # Декораторы аутентификации
    'require_auth',
    'require_user_type',
    'premium_required',
    'admin_required',
    # Утилиты аутентификации
    'get_current_user',
    'get_telegram_user',
    'is_authenticated',
    'has_user_type',
    'is_premium',
    'is_admin'
]