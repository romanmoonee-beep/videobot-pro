"""
VideoBot Pro - Utils Package
Вспомогательные утилиты для бота
"""

from .url_extractor import (
    extract_video_urls,
    validate_url,
    detect_platform,
    normalize_url,
    extract_video_id
)

from .user_manager import (
    get_or_create_user,
    update_user_activity,
    check_user_limits,
    increment_user_downloads,
    reset_user_daily_limits
)

from .subscription_checker import (
    SubscriptionChecker,
    check_required_subscriptions,
    is_user_subscribed_to_required_channels
)

from .message_builder import (
    build_welcome_message,
    build_status_message,
    build_error_message,
    build_success_message,
    format_file_size,
    format_duration
)

from .trial_manager import (
    activate_trial,
    check_trial_status,
    get_trial_time_remaining,
    expire_trial
)

from .premium_manager import (
    activate_premium,
    check_premium_status,
    process_premium_payment,
    cancel_premium_subscription
)

__all__ = [
    # URL utilities
    'extract_video_urls',
    'validate_url',
    'detect_platform',
    'normalize_url',
    'extract_video_id',
    
    # User management
    'get_or_create_user',
    'update_user_activity',
    'check_user_limits',
    'increment_user_downloads',
    'reset_user_daily_limits',
    
    # Subscription checking
    'SubscriptionChecker',
    'check_required_subscriptions',
    'is_user_subscribed_to_required_channels',
    
    # Message building
    'build_welcome_message',
    'build_status_message',
    'build_error_message',
    'build_success_message',
    'format_file_size',
    'format_duration',
    
    # Trial management
    'activate_trial',
    'check_trial_status',
    'get_trial_time_remaining',
    'expire_trial',
    
    # Premium management
    'activate_premium',
    'check_premium_status',
    'process_premium_payment',
    'cancel_premium_subscription'
]