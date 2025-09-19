"""
VideoBot Pro - Keyboards Package
Модуль клавиатур для бота
"""

from .inline import (
    create_main_menu_keyboard,
    create_trial_keyboard,
    create_batch_options_keyboard,
    create_batch_selection_keyboard,
    create_premium_plans_keyboard,
    create_payment_methods_keyboard,
    create_subscription_keyboard,
    create_settings_keyboard,
    create_quality_selector_keyboard,
    create_confirmation_keyboard,
    create_back_keyboard
)

from .reply import (
    create_main_reply_keyboard,
    create_cancel_keyboard,
    remove_keyboard
)

from .admin import (
    create_admin_panel_keyboard,
    create_user_management_keyboard,
    create_broadcast_keyboard,
    create_channel_management_keyboard,
    create_stats_keyboard
)

__all__ = [
    # Inline keyboards
    'create_main_menu_keyboard',
    'create_trial_keyboard',
    'create_batch_options_keyboard',
    'create_batch_selection_keyboard',
    'create_premium_plans_keyboard',
    'create_payment_methods_keyboard',
    'create_subscription_keyboard',
    'create_settings_keyboard',
    'create_quality_selector_keyboard',
    'create_confirmation_keyboard',
    'create_back_keyboard',
    
    # Reply keyboards
    'create_main_reply_keyboard',
    'create_cancel_keyboard',
    'remove_keyboard',
    
    # Admin keyboards
    'create_admin_panel_keyboard',
    'create_user_management_keyboard',
    'create_broadcast_keyboard',
    'create_channel_management_keyboard',
    'create_stats_keyboard'
]