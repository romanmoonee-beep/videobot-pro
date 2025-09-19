"""
VideoBot Pro - Filters Package
Пакет фильтров для aiogram бота
"""

# Admin Filters
from .admin_filter import (
    AdminFilter,
    SuperAdminFilter,
    AdminCommandFilter,
    BroadcastFilter,
    MaintenanceFilter,
    AdminCallbackFilter,
    OwnerFilter,
    AdminLevelFilter,
    
    # Предопределенные экземпляры
    is_admin,
    is_super_admin,
    is_owner,
    is_admin_command,
    is_broadcast_command,
    is_admin_callback,
    
    # Фабричные функции
    maintenance_mode,
    admin_level,
    admin_commands,
    admin_callbacks
)

# Premium/User Type Filters
from .premium_filter import (
    PremiumFilter,
    TrialFilter,
    FreeUserFilter,
    UserTypeFilter,
    LimitCheckFilter,
    SubscriptionRequiredFilter,
    BannedUserFilter,
    PremiumFeatureFilter,
    DownloadPermissionFilter,
    
    # Предопределенные экземпляры
    is_premium,
    is_trial,
    is_free,
    subscription_required,
    not_banned,
    download_allowed,
    
    # Фабричные функции
    user_type,
    limit_check,
    premium_feature,
    download_permission,
    banned_only
)

# URL Filters
from .url_filter import (
    URLFilter,
    PlatformFilter,
    BatchFilter,
    SingleURLFilter,
    YouTubeFilter,
    TikTokFilter,
    InstagramFilter,
    ShortsFilter,
    
    # Предопределенные экземпляры
    has_url,
    has_single_url,
    has_batch_urls,
    has_youtube,
    has_tiktok,
    has_instagram,
    has_shorts,
    
    # Фабричные функции
    has_supported_urls,
    has_platform_urls,
    has_batch_from_platform
)

# Rate Limit Filters
from .rate_limit_filter import (
    RateLimitFilter,
    SpamFilter,
    DownloadRateLimitFilter,
    CallbackRateLimitFilter,
    FloodProtectionFilter,
    UserThrottleFilter,
    BulkActionFilter,
    GlobalRateLimitFilter,
    MainRateLimitFilter,
    
    # Предопределенные экземпляры
    general_rate_limit,
    download_rate_limit,
    spam_filter,
    callback_rate_limit,
    flood_protection,
    user_throttle,
    bulk_action_limit,
    global_rate_limit,
    main_rate_limit,
    
    # Фабричные функции
    custom_rate_limit,
    user_type_rate_limit,
    strict_spam_filter,
    lenient_rate_limit
)

# Комбинированные фильтры для частых случаев использования
from aiogram.filters import BaseFilter
from typing import Union

class DownloadFilter(BaseFilter):
    """
    Комплексный фильтр для разрешения скачивания
    Объединяет проверки: URL + Permissions + Rate Limits
    """
    
    async def __call__(self, message) -> Union[bool, dict]:
        """Комплексная проверка возможности скачивания"""
        # Проверяем наличие URL
        url_result = await has_supported_urls(min_urls=1, max_urls=20)(message)
        if not url_result:
            return False
        
        # Проверяем разрешения
        permission_result = await download_allowed(message)
        if not permission_result:
            return False
        
        # Проверяем rate limits
        rate_result = await download_rate_limit(message)
        if not rate_result:
            return False
        
        # Объединяем результаты
        combined_result = {
            'download_allowed': True,
            'urls': url_result.get('urls', []),
            'urls_count': url_result.get('urls_count', 0),
            'platforms': url_result.get('platforms', []),
            'user_id': message.from_user.id if message.from_user else None
        }
        
        # Добавляем данные о пользователе если есть
        if isinstance(permission_result, dict):
            combined_result.update(permission_result)
        
        return combined_result

class AdminDownloadFilter(BaseFilter):
    """Фильтр для админского скачивания (без ограничений)"""
    
    async def __call__(self, message) -> Union[bool, dict]:
        """Проверка админского доступа к скачиванию"""
        # Проверяем админа
        admin_result = await is_admin(message)
        if not admin_result:
            return False
        
        # Проверяем URL
        url_result = await has_supported_urls(min_urls=1, max_urls=50)(message)  # Увеличенный лимит для админов
        if not url_result:
            return False
        
        return {
            'admin_download_allowed': True,
            'is_admin': True,
            'urls': url_result.get('urls', []),
            'urls_count': url_result.get('urls_count', 0),
            'platforms': url_result.get('platforms', []),
            'user_id': message.from_user.id if message.from_user else None
        }

class BatchDownloadFilter(BaseFilter):
    """Фильтр для batch скачиваний"""
    
    async def __call__(self, message) -> Union[bool, dict]:
        """Проверка batch скачивания"""
        # Проверяем batch URLs
        batch_result = await has_batch_urls(message)
        if not batch_result:
            return False
        
        # Проверяем разрешения (для не-админов)
        admin_result = await is_admin(message)
        if not admin_result:
            permission_result = await download_permission(subscriptions=True, limits=True)(message)
            if not permission_result:
                return False
            
            # Проверяем Premium функцию batch архива
            batch_feature_result = await premium_feature('batch_archive')(message)
            if not batch_feature_result:
                return False
        
        return {
            'batch_download_allowed': True,
            'urls': batch_result.get('urls', []),
            'urls_count': batch_result.get('urls_count', 0),
            'platforms_count': batch_result.get('platforms_count', {}),
            'mixed_platforms': batch_result.get('mixed_platforms', False),
            'is_admin': bool(admin_result),
            'user_id': message.from_user.id if message.from_user else None
        }

class CallbackFilter(BaseFilter):
    """Комплексный фильтр для callback запросов"""
    
    async def __call__(self, callback) -> Union[bool, dict]:
        """Проверка callback запроса"""
        if not callback or not callback.from_user:
            return False
        
        # Проверяем rate limit для callback'ов
        rate_result = await callback_rate_limit(callback)
        if not rate_result:
            return False
        
        # Проверяем не забанен ли пользователь
        ban_result = await not_banned(callback)
        if not ban_result:
            return False
        
        return {
            'callback_allowed': True,
            'user_id': callback.from_user.id,
            'callback_data': callback.data
        }

# Создаем экземпляры комбинированных фильтров
can_download = DownloadFilter()
admin_can_download = AdminDownloadFilter()
can_batch_download = BatchDownloadFilter()
callback_allowed = CallbackFilter()

# Экспорт всех фильтров
__all__ = [
    # Admin фильтры
    'AdminFilter', 'SuperAdminFilter', 'AdminCommandFilter', 'BroadcastFilter',
    'MaintenanceFilter', 'AdminCallbackFilter', 'OwnerFilter', 'AdminLevelFilter',
    'is_admin', 'is_super_admin', 'is_owner', 'is_admin_command', 
    'is_broadcast_command', 'is_admin_callback',
    'maintenance_mode', 'admin_level', 'admin_commands', 'admin_callbacks',
    
    # Premium/User Type фильтры
    'PremiumFilter', 'TrialFilter', 'FreeUserFilter', 'UserTypeFilter',
    'LimitCheckFilter', 'SubscriptionRequiredFilter', 'BannedUserFilter',
    'PremiumFeatureFilter', 'DownloadPermissionFilter',
    'is_premium', 'is_trial', 'is_free', 'subscription_required', 
    'not_banned', 'download_allowed',
    'user_type', 'limit_check', 'premium_feature', 'download_permission', 'banned_only',
    
    # URL фильтры
    'URLFilter', 'PlatformFilter', 'BatchFilter', 'SingleURLFilter',
    'YouTubeFilter', 'TikTokFilter', 'InstagramFilter', 'ShortsFilter',
    'has_url', 'has_single_url', 'has_batch_urls', 'has_youtube',
    'has_tiktok', 'has_instagram', 'has_shorts',
    'has_supported_urls', 'has_platform_urls', 'has_batch_from_platform',
    
    # Rate Limit фильтры
    'RateLimitFilter', 'SpamFilter', 'DownloadRateLimitFilter',
    'CallbackRateLimitFilter', 'FloodProtectionFilter', 'UserThrottleFilter',
    'BulkActionFilter', 'GlobalRateLimitFilter', 'MainRateLimitFilter',
    'general_rate_limit', 'download_rate_limit', 'spam_filter',
    'callback_rate_limit', 'flood_protection', 'user_throttle',
    'bulk_action_limit', 'global_rate_limit', 'main_rate_limit',
    'custom_rate_limit', 'user_type_rate_limit', 'strict_spam_filter', 'lenient_rate_limit',
    
    # Комбинированные фильтры
    'DownloadFilter', 'AdminDownloadFilter', 'BatchDownloadFilter', 'CallbackFilter',
    'can_download', 'admin_can_download', 'can_batch_download', 'callback_allowed'
]

# Полезные комбинации фильтров для импорта
DOWNLOAD_FILTERS = [can_download, admin_can_download, can_batch_download]
ADMIN_FILTERS = [is_admin, is_super_admin, is_owner]
USER_TYPE_FILTERS = [is_premium, is_trial, is_free]
RATE_LIMIT_FILTERS = [main_rate_limit, download_rate_limit, spam_filter]
URL_FILTERS = [has_url, has_batch_urls, has_single_url]