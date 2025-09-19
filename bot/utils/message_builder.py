"""
VideoBot Pro - Message Builder
Утилиты для формирования сообщений
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta


def build_welcome_message(
    user_name: str,
    user_type: str,
    is_new: bool = False
) -> str:
    """
    Построить приветственное сообщение
    
    Args:
        user_name: Имя пользователя
        user_type: Тип пользователя
        is_new: Новый ли пользователь
        
    Returns:
        Текст приветствия
    """
    if is_new:
        message = f"🎉 Добро пожаловать, {user_name}!\n\n"
        message += "🎬 <b>VideoBot Pro</b> - лучший бот для скачивания видео!\n\n"
        message += "📱 <b>Поддерживаемые платформы:</b>\n"
        message += "• YouTube Shorts\n"
        message += "• TikTok\n"
        message += "• Instagram Reels\n\n"
        message += "💡 Просто отправьте ссылку на видео!"
        
        if user_type == "free":
            message += "\n\n🎁 У вас есть бесплатный пробный период на 60 минут!"
    else:
        message = f"👋 С возвращением, {user_name}!\n\n"
        
        if user_type == "premium":
            message += "💎 Ваш Premium статус активен\n"
        elif user_type == "trial":
            message += "🔥 Пробный период активен\n"
        else:
            message += "🆓 Бесплатный аккаунт\n"
        
        message += "\n💡 Отправьте ссылку для скачивания"
    
    return message


def build_status_message(user_stats: Dict[str, Any]) -> str:
    """
    Построить сообщение со статусом пользователя
    
    Args:
        user_stats: Статистика пользователя
        
    Returns:
        Текст статуса
    """
    lines = ["📊 <b>Ваш статус</b>\n"]
    
    # Тип аккаунта
    user_type_emoji = {
        "free": "🆓",
        "trial": "🔥",
        "premium": "💎",
        "admin": "👑"
    }
    emoji = user_type_emoji.get(user_stats['user_type'], "👤")
    lines.append(f"{emoji} Тип: {user_stats['user_type'].title()}")
    
    # Лимиты
    if user_stats['daily_limit'] < 999:
        lines.append(f"📥 Скачиваний сегодня: {user_stats['downloads_today']}/{user_stats['daily_limit']}")
    else:
        lines.append(f"📥 Скачиваний сегодня: {user_stats['downloads_today']} (без лимита)")
    
    lines.append(f"📊 Всего скачано: {user_stats.get('total_downloads', 0)}")
    
    # Trial информация
    if user_stats.get('trial_active'):
        remaining = user_stats.get('trial_remaining')
        if remaining:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            lines.append(f"⏰ Trial: {hours}ч {minutes}м")
    
    # Premium информация
    if user_stats.get('premium_active'):
        expires = user_stats.get('premium_remaining')
        if expires:
            days = expires.days
            lines.append(f"💎 Premium: {days} дней")
    
    # Предупреждения
    if user_stats.get('is_banned'):
        lines.append("\n⚠️ Ваш аккаунт заблокирован")
    elif not user_stats.get('can_download'):
        lines.append("\n⚠️ Достигнут дневной лимит")
    
    return "\n".join(lines)


def build_error_message(
    error_type: str,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Построить сообщение об ошибке
    
    Args:
        error_type: Тип ошибки
        context: Контекст ошибки
        
    Returns:
        Текст ошибки
    """
    messages = {
        "invalid_url": "❌ Неверная ссылка. Поддерживаются только YouTube Shorts, TikTok и Instagram Reels.",
        "platform_not_supported": "❌ Эта платформа не поддерживается. Используйте YouTube, TikTok или Instagram.",
        "daily_limit_exceeded": "⏰ Достигнут дневной лимит загрузок ({limit}). Попробуйте завтра или купите Premium.",
        "file_too_large": "📦 Файл слишком большой. Максимальный размер: {max_size}MB",
        "download_failed": "❌ Ошибка загрузки. Попробуйте еще раз или используйте другую ссылку.",
        "subscription_required": "🔒 Необходима подписка на обязательные каналы.",
        "premium_required": "💎 Эта функция доступна только для Premium пользователей.",
        "banned": "🚫 Ваш аккаунт заблокирован. Причина: {reason}",
        "maintenance": "🔧 Бот на техническом обслуживании. Попробуйте позже.",
        "rate_limit": "⚡ Слишком много запросов. Подождите {seconds} секунд.",
        "network_error": "🌐 Ошибка сети. Проверьте соединение и попробуйте снова.",
        "general": "❌ Произошла ошибка. Попробуйте позже или обратитесь в поддержку."
    }
    
    base_message = messages.get(error_type, messages["general"])
    
    # Форматируем с контекстом если есть
    if context:
        try:
            base_message = base_message.format(**context)
        except KeyError:
            pass
    
    return base_message


def build_success_message(
    action: str,
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Построить сообщение об успешном действии
    
    Args:
        action: Тип действия
        context: Контекст
        
    Returns:
        Текст сообщения
    """
    messages = {
        "download_started": "⏳ Начинаю загрузку...\n📹 Платформа: {platform}\n🔗 ID: {video_id}",
        "download_completed": "✅ Загрузка завершена!\n📁 Размер: {size}\n⏱ Время: {duration}с",
        "batch_created": "📦 Пакетная загрузка создана\n📊 Файлов: {count}\n⏳ Обработка...",
        "trial_activated": "🎉 Пробный период активирован!\n⏰ Доступно: 60 минут\n🚀 Безлимитные загрузки",
        "premium_activated": "💎 Premium активирован!\n📅 Действует до: {expires}\n✨ Все функции разблокированы",
        "settings_saved": "✅ Настройки сохранены",
        "subscription_verified": "✅ Подписки проверены. Доступ открыт!"
    }
    
    base_message = messages.get(action, "✅ Операция выполнена успешно")
    
    if context:
        try:
            base_message = base_message.format(**context)
        except KeyError:
            pass
    
    return base_message


def format_file_size(size_bytes: int) -> str:
    """
    Форматировать размер файла
    
    Args:
        size_bytes: Размер в байтах
        
    Returns:
        Отформатированная строка
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_duration(seconds: int) -> str:
    """
    Форматировать длительность
    
    Args:
        seconds: Количество секунд
        
    Returns:
        Отформатированная строка
    """
    if seconds < 60:
        return f"{seconds}с"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}м {secs}с"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}ч {minutes}м"


def build_download_progress_message(
    progress: float,
    speed: Optional[float] = None,
    eta: Optional[int] = None
) -> str:
    """
    Построить сообщение прогресса загрузки
    
    Args:
        progress: Процент выполнения (0-100)
        speed: Скорость загрузки в байтах/сек
        eta: Оставшееся время в секундах
        
    Returns:
        Текст прогресса
    """
    # Прогресс-бар
    filled = int(progress / 10)
    bar = "█" * filled + "░" * (10 - filled)
    
    message = f"📥 Загрузка: {bar} {progress:.1f}%"
    
    if speed:
        message += f"\n⚡ Скорость: {format_file_size(int(speed))}/с"
    
    if eta:
        message += f"\n⏱ Осталось: {format_duration(eta)}"
    
    return message


def build_batch_summary_message(
    total_files: int,
    successful: int,
    failed: int,
    total_size: int,
    total_time: int
) -> str:
    """
    Построить сообщение итогов пакетной загрузки
    
    Args:
        total_files: Общее количество файлов
        successful: Успешно загружено
        failed: Ошибки
        total_size: Общий размер
        total_time: Общее время
        
    Returns:
        Текст итогов
    """
    lines = ["📊 <b>Итоги пакетной загрузки</b>\n"]
    
    lines.append(f"📁 Всего файлов: {total_files}")
    lines.append(f"✅ Успешно: {successful}")
    
    if failed > 0:
        lines.append(f"❌ Ошибки: {failed}")
    
    lines.append(f"💾 Общий размер: {format_file_size(total_size)}")
    lines.append(f"⏱ Время: {format_duration(total_time)}")
    
    # Статус
    if failed == 0:
        lines.append("\n✨ Все файлы успешно загружены!")
    elif successful > 0:
        lines.append(f"\n⚠️ Загружено {successful} из {total_files} файлов")
    else:
        lines.append("\n❌ Не удалось загрузить файлы")
    
    return "\n".join(lines)


def build_subscription_check_message(
    channels: List[Dict[str, Any]],
    subscribed: List[str],
    missing: List[str]
) -> str:
    """
    Построить сообщение проверки подписок
    
    Args:
        channels: Список каналов
        subscribed: Подписанные каналы
        missing: Неподписанные каналы
        
    Returns:
        Текст сообщения
    """
    if not missing:
        return "✅ Вы подписаны на все обязательные каналы!"
    
    lines = ["📢 <b>Необходимо подписаться на каналы:</b>\n"]
    
    for channel in channels:
        channel_id = channel.get('channel_id', '')
        channel_name = channel.get('channel_name', 'Канал')
        
        if channel_id in subscribed:
            lines.append(f"✅ {channel_name}")
        else:
            lines.append(f"❌ {channel_name}")
    
    lines.append(f"\n📊 Прогресс: {len(subscribed)}/{len(channels)}")
    lines.append("\n💡 Подпишитесь на все каналы и нажмите 'Проверить'")
    
    return "\n".join(lines)


def build_premium_info_message(
    plan_name: str,
    price: float,
    duration_days: int,
    features: List[str]
) -> str:
    """
    Построить сообщение о Premium плане
    
    Args:
        plan_name: Название плана
        price: Цена
        duration_days: Длительность в днях
        features: Список возможностей
        
    Returns:
        Текст сообщения
    """
    lines = [f"💎 <b>{plan_name}</b>\n"]
    
    lines.append(f"💰 Цена: ${price:.2f}")
    lines.append(f"📅 Длительность: {duration_days} дней")
    lines.append(f"💵 Цена за день: ${price/duration_days:.2f}")
    
    lines.append("\n🎯 <b>Возможности:</b>")
    for feature in features:
        lines.append(f"• {feature}")
    
    return "\n".join(lines)


def build_admin_user_info_message(user_data: Dict[str, Any]) -> str:
    """
    Построить детальную информацию о пользователе для админа
    
    Args:
        user_data: Данные пользователя
        
    Returns:
        Текст сообщения
    """
    lines = ["👤 <b>Информация о пользователе</b>\n"]
    
    # Основная информация
    lines.append(f"🆔 ID: {user_data.get('telegram_id')}")
    lines.append(f"📝 Username: @{user_data.get('username', 'не указан')}")
    lines.append(f"👤 Имя: {user_data.get('first_name', 'не указано')}")
    lines.append(f"📊 Тип: {user_data.get('user_type', 'free')}")
    
    # Статистика
    lines.append("\n📈 <b>Статистика:</b>")
    lines.append(f"• Регистрация: {user_data.get('created_at', 'неизвестно')}")
    lines.append(f"• Последняя активность: {user_data.get('last_active', 'неизвестно')}")
    lines.append(f"• Всего загрузок: {user_data.get('total_downloads', 0)}")
    lines.append(f"• Загрузок сегодня: {user_data.get('downloads_today', 0)}")
    
    # Финансы
    if user_data.get('total_spent', 0) > 0:
        lines.append(f"\n💰 <b>Финансы:</b>")
        lines.append(f"• Потрачено: ${user_data.get('total_spent', 0):.2f}")
        lines.append(f"• Платежей: {user_data.get('payments_count', 0)}")
    
    # Статус
    lines.append("\n🔐 <b>Статус:</b>")
    if user_data.get('is_banned'):
        lines.append("🚫 Заблокирован")
        if user_data.get('ban_reason'):
            lines.append(f"Причина: {user_data['ban_reason']}")
    else:
        lines.append("✅ Активен")
    
    if user_data.get('is_premium'):
        lines.append(f"💎 Premium до: {user_data.get('premium_expires')}")
    
    return "\n".join(lines)
    