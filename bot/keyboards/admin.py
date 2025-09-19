"""
VideoBot Pro - Admin Keyboards
Административные клавиатуры
"""

from typing import Optional, List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def create_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ панели"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
        ],
        [
            InlineKeyboardButton(text="📋 Каналы", callback_data="admin_channels"),
            InlineKeyboardButton(text="💰 Финансы", callback_data="admin_finance")
        ],
        [
            InlineKeyboardButton(text="🔧 Система", callback_data="admin_system"),
            InlineKeyboardButton(text="📜 Логи", callback_data="admin_logs")
        ],
        [
            InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_main")
        ]
    ])


def create_user_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления пользователями"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Поиск пользователя", callback_data="admin_user_search"),
            InlineKeyboardButton(text="📊 Топ пользователи", callback_data="admin_top_users")
        ],
        [
            InlineKeyboardButton(text="🆕 Новые", callback_data="admin_new_users"),
            InlineKeyboardButton(text="💎 Premium", callback_data="admin_premium_users")
        ],
        [
            InlineKeyboardButton(text="🚫 Заблокированные", callback_data="admin_banned_users"),
            InlineKeyboardButton(text="📈 Активность", callback_data="admin_user_activity")
        ],
        [
            InlineKeyboardButton(text="📤 Экспорт данных", callback_data="admin_export_users"),
            InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")
        ]
    ])


def create_broadcast_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для рассылки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 Создать рассылку", callback_data="admin_create_broadcast")
        ],
        [
            InlineKeyboardButton(text="📊 Статистика рассылок", callback_data="admin_broadcast_stats"),
            InlineKeyboardButton(text="📜 История", callback_data="admin_broadcast_history")
        ],
        [
            InlineKeyboardButton(text="⏱️ Запланированные", callback_data="admin_scheduled_broadcasts"),
            InlineKeyboardButton(text="📝 Шаблоны", callback_data="admin_broadcast_templates")
        ],
        [
            InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")
        ]
    ])


def create_channel_management_keyboard(channels: Optional[List] = None) -> InlineKeyboardMarkup:
    """
    Клавиатура управления обязательными каналами
    
    Args:
        channels: Список текущих каналов
    """
    keyboard = []
    
    # Показываем существующие каналы
    if channels:
        for channel in channels[:5]:  # Максимум 5 каналов в превью
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📢 {channel.get('name', 'Канал')}",
                    callback_data=f"admin_channel_{channel.get('id', 0)}"
                )
            ])
    
    # Управляющие кнопки
    keyboard.extend([
        [
            InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_add_channel"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_channels_stats")
        ],
        [
            InlineKeyboardButton(text="⚙️ Настройки проверки", callback_data="admin_subscription_settings"),
            InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_stats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура статистики"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📈 Графики", callback_data="admin_charts"),
            InlineKeyboardButton(text="📋 Отчеты", callback_data="admin_reports")
        ],
        [
            InlineKeyboardButton(text="💰 Доходы", callback_data="admin_revenue"),
            InlineKeyboardButton(text="📥 Загрузки", callback_data="admin_downloads_stats")
        ],
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_stats"),
            InlineKeyboardButton(text="🌍 География", callback_data="admin_geo_stats")
        ],
        [
            InlineKeyboardButton(text="📤 Экспорт", callback_data="admin_export_stats"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh_stats")
        ],
        [
            InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")
        ]
    ])


def create_user_action_keyboard(user_id: int, is_banned: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура действий с конкретным пользователем
    
    Args:
        user_id: ID пользователя
        is_banned: Заблокирован ли пользователь
    """
    keyboard = [
        [
            InlineKeyboardButton(text="💎 Выдать Premium", callback_data=f"admin_grant_premium_{user_id}"),
            InlineKeyboardButton(text="🎁 Дать Trial", callback_data=f"admin_grant_trial_{user_id}")
        ],
        [
            InlineKeyboardButton(
                text="🚫 Заблокировать" if not is_banned else "✅ Разблокировать",
                callback_data=f"admin_{'ban' if not is_banned else 'unban'}_{user_id}"
            ),
            InlineKeyboardButton(text="📧 Сообщение", callback_data=f"admin_message_{user_id}")
        ],
        [
            InlineKeyboardButton(text="📊 Подробная статистика", callback_data=f"admin_user_stats_{user_id}"),
            InlineKeyboardButton(text="💳 История платежей", callback_data=f"admin_user_payments_{user_id}")
        ],
        [
            InlineKeyboardButton(text="📥 История загрузок", callback_data=f"admin_user_downloads_{user_id}"),
            InlineKeyboardButton(text="🔄 Сбросить лимиты", callback_data=f"admin_reset_limits_{user_id}")
        ],
        [
            InlineKeyboardButton(text="🔙 К списку", callback_data="admin_users")
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_system_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура системных настроек"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Перезагрузить бота", callback_data="admin_restart"),
            InlineKeyboardButton(text="🧹 Очистить кэш", callback_data="admin_clear_cache")
        ],
        [
            InlineKeyboardButton(text="💾 Резервная копия БД", callback_data="admin_backup"),
            InlineKeyboardButton(text="🔧 Режим обслуживания", callback_data="admin_maintenance")
        ],
        [
            InlineKeyboardButton(text="📊 Health Check", callback_data="admin_health"),
            InlineKeyboardButton(text="⚡ Тест производительности", callback_data="admin_performance")
        ],
        [
            InlineKeyboardButton(text="📝 Переменные окружения", callback_data="admin_env"),
            InlineKeyboardButton(text="🔄 Обновить конфиг", callback_data="admin_reload_config")
        ],
        [
            InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")
        ]
    ])


def create_finance_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура финансового раздела"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Доходы", callback_data="admin_revenue_details"),
            InlineKeyboardButton(text="💳 Платежи", callback_data="admin_payments_list")
        ],
        [
            InlineKeyboardButton(text="📊 Аналитика продаж", callback_data="admin_sales_analytics"),
            InlineKeyboardButton(text="💹 Конверсия", callback_data="admin_conversion_rate")
        ],
        [
            InlineKeyboardButton(text="🎁 Промокоды", callback_data="admin_promo_codes"),
            InlineKeyboardButton(text="💸 Возвраты", callback_data="admin_refunds")
        ],
        [
            InlineKeyboardButton(text="📤 Экспорт отчета", callback_data="admin_export_finance"),
            InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")
        ]
    ])