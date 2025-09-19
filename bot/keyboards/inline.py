"""
VideoBot Pro - Inline Keyboards
Inline клавиатуры для бота
"""

from typing import List, Dict, Optional, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def create_main_menu_keyboard(user_type: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    Создание главного меню в зависимости от типа пользователя
    
    Args:
        user_type: Тип пользователя (free, trial, premium, admin)
        is_admin: Является ли пользователь администратором
    """
    keyboard = []
    
    # Основные кнопки для всех
    keyboard.append([
        InlineKeyboardButton(text="📥 Скачать видео", callback_data="download"),
        InlineKeyboardButton(text="📊 Мой статус", callback_data="status")
    ])
    
    # Кнопки в зависимости от типа пользователя
    if user_type == "free":
        keyboard.append([
            InlineKeyboardButton(text="🎁 Пробный период", callback_data="trial"),
            InlineKeyboardButton(text="💎 Premium", callback_data="buy_premium")
        ])
    elif user_type == "trial":
        keyboard.append([
            InlineKeyboardButton(text="⏰ Осталось времени", callback_data="trial_status"),
            InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium")
        ])
    elif user_type == "premium":
        keyboard.append([
            InlineKeyboardButton(text="💎 Управление Premium", callback_data="premium_settings"),
            InlineKeyboardButton(text="🎁 Пригласить друзей", callback_data="referral")
        ])
    
    # Общие кнопки
    keyboard.append([
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="help")
    ])
    
    # Админская кнопка
    if is_admin:
        keyboard.append([
            InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_trial_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для пробного периода"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Активировать пробный период", callback_data="activate_trial")],
        [InlineKeyboardButton(text="💎 Сразу купить Premium", callback_data="buy_premium")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])


def create_batch_options_keyboard(files_count: int) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора способа доставки для batch загрузки
    
    Args:
        files_count: Количество файлов
    """
    keyboard = []
    
    # Показываем опции в зависимости от количества файлов
    if files_count <= 4:
        # Для малого количества - автоматически в чат
        keyboard.append([
            InlineKeyboardButton(
                text=f"📱 Отправить в чат ({files_count} файлов)",
                callback_data="batch_individual"
            )
        ])
    else:
        # Для большого количества - выбор
        keyboard.extend([
            [InlineKeyboardButton(
                text="📱 В чат по одному",
                callback_data="batch_individual"
            )],
            [InlineKeyboardButton(
                text="📦 Архивом через CDN",
                callback_data="batch_archive"
            )],
            [InlineKeyboardButton(
                text="🎛️ Выбрать файлы",
                callback_data="batch_selective"
            )]
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="batch_cancel")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_batch_selection_keyboard(urls_data: List[Dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура для выборочного скачивания файлов
    
    Args:
        urls_data: Список данных о файлах
    """
    keyboard = []
    
    # Кнопки для каждого файла (максимум 10)
    for i, url_data in enumerate(urls_data[:10]):
        status = "✅" if url_data.get("selected", True) else "❌"
        platform = url_data.get("platform", "Unknown")
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {i+1}. {platform}",
                callback_data=f"toggle_file_{i}"
            )
        ])
    
    # Управляющие кнопки
    keyboard.extend([
        [
            InlineKeyboardButton(text="✅ Все", callback_data="select_all"),
            InlineKeyboardButton(text="❌ Снять все", callback_data="deselect_all")
        ],
        [
            InlineKeyboardButton(text="⬇️ Скачать выбранные", callback_data="download_selected"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="batch_options")
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_premium_plans_keyboard(plans: Dict[str, Dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура с планами Premium подписки
    
    Args:
        plans: Словарь с планами подписки
    """
    keyboard = []
    
    for plan_id, plan_data in plans.items():
        # Формируем текст кнопки
        text = f"{plan_data['name']} - ${plan_data['price_usd']}"
        if plan_data.get('discount'):
            text += f" (-{plan_data['discount']}%)"
        if plan_data.get('popular'):
            text = f"⭐ {text}"
        
        keyboard.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"premium_plan_{plan_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_payment_methods_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора способа оплаты"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Telegram Payments", callback_data="payment_telegram")],
        [InlineKeyboardButton(text="💳 Банковская карта (Stripe)", callback_data="payment_stripe")],
        [InlineKeyboardButton(text="🪙 Криптовалюта", callback_data="payment_crypto")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_plans")]
    ])


def create_subscription_keyboard(
    channels: List[Dict[str, str]], 
    subscribed_channels: List[str]
) -> InlineKeyboardMarkup:
    """
    Клавиатура для проверки подписок на каналы
    
    Args:
        channels: Список обязательных каналов
        subscribed_channels: Список каналов, на которые подписан пользователь
    """
    keyboard = []
    
    # Добавляем кнопки для каждого канала
    for channel in channels:
        channel_id = channel.get("channel_id", "")
        channel_name = channel.get("channel_name", "Канал")
        channel_url = channel.get("url", f"https://t.me/{channel_id.replace('@', '')}")
        
        # Определяем статус подписки
        if channel_id in subscribed_channels:
            status = "✅"
        else:
            status = "❌"
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status} {channel_name}",
                url=channel_url
            )
        ])
    
    # Кнопки действий
    keyboard.extend([
        [InlineKeyboardButton(text="✅ Я подписался!", callback_data="check_subscriptions")],
        [InlineKeyboardButton(text="🔄 Проверить еще раз", callback_data="recheck_subscriptions")],
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="buy_premium")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_settings_keyboard(user_settings: Dict[str, Any]) -> InlineKeyboardMarkup:
    """
    Клавиатура настроек пользователя
    
    Args:
        user_settings: Текущие настройки пользователя
    """
    quality = user_settings.get("quality_mode", "auto")
    notifications = user_settings.get("notifications", True)
    language = user_settings.get("language", "ru")
    
    keyboard = [
        [InlineKeyboardButton(
            text=f"🎬 Качество: {quality}",
            callback_data="settings_quality"
        )],
        [InlineKeyboardButton(
            text=f"🔔 Уведомления: {'Вкл' if notifications else 'Выкл'}",
            callback_data="settings_notifications"
        )],
        [InlineKeyboardButton(
            text=f"🌍 Язык: {language.upper()}",
            callback_data="settings_language"
        )],
        [InlineKeyboardButton(
            text="📦 Способ доставки файлов",
            callback_data="settings_delivery"
        )],
        [InlineKeyboardButton(
            text="🔒 Приватность",
            callback_data="settings_privacy"
        )],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_quality_selector_keyboard(
    available_qualities: List[str],
    current_quality: Optional[str] = None
) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора качества видео
    
    Args:
        available_qualities: Список доступных качеств
        current_quality: Текущее выбранное качество
    """
    keyboard = []
    
    quality_labels = {
        "2160p": "🔥 4K (2160p)",
        "1080p": "🎬 Full HD (1080p)",
        "720p": "📺 HD (720p)",
        "480p": "📱 SD (480p)",
        "360p": "📞 Low (360p)",
        "audio": "🎵 Только аудио"
    }
    
    for quality in available_qualities:
        label = quality_labels.get(quality, quality)
        if quality == current_quality:
            label = f"✅ {label}"
        
        keyboard.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"select_quality_{quality}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="back")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_confirmation_keyboard(
    confirm_text: str = "✅ Да",
    cancel_text: str = "❌ Нет",
    confirm_data: str = "confirm",
    cancel_data: str = "cancel"
) -> InlineKeyboardMarkup:
    """
    Универсальная клавиатура подтверждения
    
    Args:
        confirm_text: Текст кнопки подтверждения
        cancel_text: Текст кнопки отмены
        confirm_data: Callback data для подтверждения
        cancel_data: Callback data для отмены
    """
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=confirm_text, callback_data=confirm_data),
        InlineKeyboardButton(text=cancel_text, callback_data=cancel_data)
    ]])


def create_back_keyboard(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    """
    Создать кнопку "Назад"
    
    Args:
        callback_data: Callback data для кнопки назад
    """
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)
    ]])