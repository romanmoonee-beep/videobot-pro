"""
VideoBot Pro - Reply Keyboards
Reply клавиатуры для бота
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


def create_main_reply_keyboard(user_type: str = "free") -> ReplyKeyboardMarkup:
    """
    Создание основной reply клавиатуры
    
    Args:
        user_type: Тип пользователя
    """
    keyboard = []
    
    # Первый ряд - основные действия
    keyboard.append([
        KeyboardButton(text="📥 Скачать видео"),
        KeyboardButton(text="📊 Мой статус")
    ])
    
    # Второй ряд - в зависимости от типа пользователя
    if user_type == "free":
        keyboard.append([
            KeyboardButton(text="🎁 Пробный период"),
            KeyboardButton(text="💎 Premium")
        ])
    elif user_type == "premium":
        keyboard.append([
            KeyboardButton(text="💎 Premium"),
            KeyboardButton(text="🎁 Реферальная программа")
        ])
    
    # Третий ряд - настройки и помощь
    keyboard.append([
        KeyboardButton(text="⚙️ Настройки"),
        KeyboardButton(text="❓ Помощь")
    ])
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def create_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Удаление reply клавиатуры"""
    return ReplyKeyboardRemove()