"""
VideoBot Pro - Middlewares Package
Middleware компоненты для бота
"""

from .rate_limit import RateLimitMiddleware, rate_limit
from .admin_only import AdminOnlyMiddleware, admin_only
from .subscription_check import SubscriptionCheckMiddleware
from .user_activity import UserActivityMiddleware
from .anti_flood import AntiFloodMiddleware
from .logging_middleware import LoggingMiddleware
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
from .maintenance import MaintenanceMiddleware

from aiogram import Dispatcher

def setup_middlewares(dp: Dispatcher) -> None:
    """
    Настройка всех middleware для диспетчера
    
    Args:
        dp: Диспетчер aiogram
    """
    # Порядок важен! Middleware выполняются в порядке регистрации
    
    # Logging (первым для логирования всех запросов)
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    
    # Maintenance mode check (проверяем до аутентификации)
    dp.message.middleware(MaintenanceMiddleware())
    dp.callback_query.middleware(MaintenanceMiddleware())
    
    # Authentication and user management (создаем/получаем пользователя)
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    
    # User activity tracking (после аутентификации)
    dp.message.middleware(UserActivityMiddleware())
    dp.callback_query.middleware(UserActivityMiddleware())
    
    # Anti-flood protection
    dp.message.middleware(AntiFloodMiddleware())
    dp.callback_query.middleware(AntiFloodMiddleware())
    
    # Rate limiting
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    
    # Subscription checking (только для сообщений, после аутентификации)
    dp.message.middleware(SubscriptionCheckMiddleware())
    
    # Analytics (последним для сбора полных данных)
    from .analytics import AnalyticsMiddleware
    dp.message.middleware(AnalyticsMiddleware())
    dp.callback_query.middleware(AnalyticsMiddleware())

__all__ = [
    'setup_middlewares',
    'RateLimitMiddleware',
    'rate_limit',
    'AdminOnlyMiddleware', 
    'admin_only',
    'SubscriptionCheckMiddleware',
    'UserActivityMiddleware',
    'AntiFloodMiddleware',
    'LoggingMiddleware',
    'AuthMiddleware',
    'RequireAuthMiddleware',
    'UserTypeMiddleware',
    'MaintenanceMiddleware',
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