"""
VideoBot Pro - Bot Configuration
Конфигурация и настройки специфичные для Telegram бота
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from shared.config.settings import settings


class BotMode(Enum):
    """Режимы работы бота"""
    POLLING = "polling"
    WEBHOOK = "webhook"


class MessageType(Enum):
    """Типы сообщений бота"""
    WELCOME = "welcome"
    HELP = "help"
    ERROR = "error"
    SUCCESS = "success"
    PROCESSING = "processing"
    PREMIUM_REQUIRED = "premium_required"
    SUBSCRIPTION_REQUIRED = "subscription_required"


@dataclass
class BotLimits:
    """Лимиты для бота"""
    max_message_length: int = 4096
    max_caption_length: int = 1024
    max_file_size_mb: int = 50
    max_batch_size: int = 20
    rate_limit_requests_per_minute: int = 20
    flood_control_delay_seconds: int = 1


class BotConfig:
    """Конфигурация Telegram бота"""
    
    def __init__(self):
        # Основные настройки
        self.bot_token = settings.BOT_TOKEN
        self.parse_mode = settings.BOT_PARSE_MODE
        self.webhook_url = settings.WEBHOOK_URL
        self.webhook_path = settings.WEBHOOK_PATH
        self.webhook_secret = settings.WEBHOOK_SECRET
        
        # Режим работы
        self.mode = BotMode.WEBHOOK if settings.WEBHOOK_URL else BotMode.POLLING
        
        # Лимиты
        self.limits = BotLimits(
            max_file_size_mb=settings.FREE_MAX_FILE_SIZE_MB,
            max_batch_size=settings.MAX_BATCH_SIZE,
            rate_limit_requests_per_minute=settings.RATE_LIMIT_REQUESTS
        )
        
        # Админы
        self.admin_ids = settings.ADMIN_IDS
        self.super_admin_id = settings.SUPER_ADMIN_ID
        
        # Feature flags
        self.trial_enabled = settings.TRIAL_ENABLED
        self.required_subs_enabled = settings.REQUIRED_SUBS_ENABLED
        self.batch_processing_enabled = settings.BATCH_PROCESSING_ENABLED
        self.premium_system_enabled = settings.PREMIUM_SYSTEM_ENABLED
        
        # Команды бота
        self.commands = self._setup_commands()
        
        # Сообщения
        self.messages = self._setup_messages()
        
        # Клавиатуры
        self.keyboards = self._setup_keyboard_configs()
    
    def is_admin(self, user_id: int) -> bool:
        """Проверить является ли пользователь админом"""
        return user_id in self.admin_ids or user_id == self.super_admin_id
    
    def is_super_admin(self, user_id: int) -> bool:
        """Проверить является ли пользователь супер-админом"""
        return user_id == self.super_admin_id
    
    def get_user_file_limit(self, user_type: str) -> int:
        """Получить лимит размера файла для типа пользователя"""
        return settings.get_max_file_size_mb(user_type)
    
    def get_user_daily_limit(self, user_type: str) -> int:
        """Получить дневной лимит скачиваний"""
        return settings.get_daily_limit(user_type)
    
    def _setup_commands(self) -> Dict[str, Dict]:
        """Настройка команд бота"""
        return {
            "start": {
                "description": "🚀 Запустить бота",
                "admin_only": False
            },
            "help": {
                "description": "❓ Помощь и инструкции",
                "admin_only": False
            },
            "status": {
                "description": "📊 Мой статус и статистика",
                "admin_only": False
            },
            "settings": {
                "description": "⚙️ Настройки",
                "admin_only": False
            },
            "premium": {
                "description": "💎 Premium подписка",
                "admin_only": False
            },
            "trial": {
                "description": "🎁 Пробный период",
                "admin_only": False
            },
            # Админские команды
            "admin": {
                "description": "👑 Админ панель",
                "admin_only": True
            },
            "stats": {
                "description": "📈 Статистика системы",
                "admin_only": True
            },
            "broadcast": {
                "description": "📢 Создать рассылку",
                "admin_only": True
            },
            "maintenance": {
                "description": "🔧 Режим обслуживания",
                "admin_only": True
            }
        }
    
    def _setup_messages(self) -> Dict[str, Dict]:
        """Настройка текстов сообщений"""
        return {
            MessageType.WELCOME.value: {
                "new_user":
                    """
                        🎉 <b>Добро пожаловать в VideoBot Pro!</b>
        
                        🚀 Я помогаю скачивать видео из:
                        • YouTube Shorts ✅
                        • TikTok ✅  
                        • Instagram Reels ✅
                        
                        💡 <b>Что я умею:</b>
                        • Скачивание до 20 ссылок сразу
                        • Высокое качество (до 4K для Premium)
                        • Быстрая обработка
                        • Удобная доставка файлов
                        
                        {trial_info}
                        
                        📝 <b>Как пользоваться:</b>
                        Просто отправьте мне ссылку на видео или несколько ссылок сразу!
                        
                        {subscription_info}
                    """,
                
                "returning_user":
                    """
                        👋 <b>С возвращением!</b>

                        📊 <b>Ваша статистика:</b>
                        • Скачано сегодня: {downloads_today}/{daily_limit}
                        • Всего скачано: {total_downloads}
                        • Тип аккаунта: {user_type}
                        
                        💡 Отправьте ссылку для скачивания видео!
                    """,
                
                "trial_available":
                    """
                        🎁 <b>Пробный период доступен!</b>

                        ⏰ {trial_duration} минут БЕСПЛАТНО:
                        • Безлимитные скачивания
                        • Все платформы
                        • HD качество
                        • Без подписок на каналы
                        
                        Хотите активировать пробный период?
                    """,
                
                "trial_active":
                    """
                        🔥 <b>Пробный период активен!</b>

                        ⏰ Осталось: {time_left}
                        • Безлимитные скачивания ✅
                        • Все платформы ✅
                        • HD качество ✅
                        
                        После окончания перейдете на бесплатный план.
                    """
            },
            
            MessageType.HELP.value: {
                "main":
                    """
                        ❓ <b>Справка VideoBot Pro</b>

                        🎬 <b>Поддерживаемые платформы:</b>
                        • YouTube Shorts (shorts, youtu.be)
                        • TikTok (tiktok.com, vm.tiktok.com)
                        • Instagram Reels (instagram.com/reel/)
                        
                        📝 <b>Как скачивать:</b>
                        1️⃣ Отправьте ссылку на видео
                        2️⃣ Или несколько ссылок сразу (до 20)
                        3️⃣ Выберите способ доставки
                        4️⃣ Получите файлы!
                        
                        ⚡ <b>Режимы доставки:</b>
                        • <b>В чат</b> - файлы по одному
                        • <b>Архивом</b> - ZIP файл через CDN
                        • <b>Выборочно</b> - выберите нужные
                        
                        💎 <b>Premium возможности:</b>
                        • Безлимитные скачивания
                        • 4K качество
                        • Файлы до 500MB
                        • Без обязательных подписок
                        • Хранение 30 дней
                        
                        🆘 <b>Проблемы?</b>
                        Напишите @support_bot
                    """,
                
                "formats":
                    """
                        📋 <b>Поддерживаемые форматы:</b>

                        🎬 <b>Видео:</b>
                        • MP4 (основной формат)
                        • WebM (при необходимости)
                        
                        📱 <b>Качество:</b>
                        • 4K (2160p) - Premium/Admin
                        • Full HD (1080p) - Premium/Admin  
                        • HD (720p) - Все пользователи
                        • SD (480p) - Fallback
                        
                        🔧 <b>Автоматический выбор:</b>
                        Система сама выберет лучшее доступное качество для вашего типа аккаунта.
                    """
            },
            
            MessageType.ERROR.value: {
                "general": "❌ Произошла ошибка. Попробуйте позже.",
                "invalid_url": "❌ Неподдерживаемая ссылка. Проверьте формат URL.",
                "file_too_large": "📏 Файл слишком большой ({size}MB). Лимит: {limit}MB.",
                "daily_limit_exceeded": "⏰ Дневной лимит исчерпан ({limit} скачиваний). Попробуйте завтра или купите Premium.",
                "download_failed": "💥 Не удалось скачать видео. Возможно, оно удалено или приватное.",
                "platform_error": "🔧 Временные проблемы с {platform}. Попробуйте позже.",
                "rate_limit": "⚡ Слишком много запросов. Подождите {seconds} секунд.",
                "maintenance": "🔧 Технические работы. Попробуйте через несколько минут."
            },
            
            MessageType.SUCCESS.value: {
                "download_started": "⏳ Начинаю скачивание...",
                "download_completed": "✅ Готово! Файл: {filename}",
                "batch_completed": "🎉 Batch завершен! {completed}/{total} файлов готово.",
                "settings_updated": "⚙️ Настройки сохранены!",
                "premium_activated": "💎 Premium активирован до {date}!"
            },
            
            MessageType.PROCESSING.value: {
                "analyzing": "🔍 Анализирую ссылки...",
                "downloading": "⬇️ Скачиваю ({progress}%)...",
                "uploading": "☁️ Загружаю в облако...",
                "preparing": "📦 Подготавливаю файлы..."
            },
            
            MessageType.PREMIUM_REQUIRED.value: {
                "file_size": """📏 <b>Файл слишком большой для бесплатного аккаунта</b>

Размер файла: {size}MB
Лимит Free: {limit}MB

💎 <b>Premium решение:</b>
• Лимит: 500MB
• Цена: $3.99/месяц
• Первый месяц со скидкой!""",
                
                "quality": """🎬 <b>4K качество доступно только Premium</b>

Доступно:
• Free: до 720p HD
• Premium: до 4K UHD

💎 Получить Premium за $3.99/месяц?""",
                
                "daily_limit": """⏰ <b>Дневной лимит исчерпан</b>

Сегодня скачано: {used}/{limit}

💎 <b>Premium преимущества:</b>
• Безлимитные скачивания
• 4K качество  
• Приоритетная обработка
• Без рекламы"""
            },
            
            MessageType.SUBSCRIPTION_REQUIRED.value: {
                "main": """🔒 <b>Для продолжения подпишитесь на каналы</b>

{channels_list}

✅ После подписки нажмите "Я подписался!"

💎 Premium пользователи освобождены от этого требования."""
            }
        }
    
    def _setup_keyboard_configs(self) -> Dict:
        """Настройка конфигураций клавиатур"""
        return {
            "main_menu": {
                "free": [
                    [{"text": "📊 Мой статус", "callback": "status"}],
                    [{"text": "❓ Помощь", "callback": "help"}, {"text": "⚙️ Настройки", "callback": "settings"}],
                    [{"text": "🎁 Пробный период", "callback": "trial"}, {"text": "💎 Premium", "callback": "premium"}]
                ],
                "premium": [
                    [{"text": "📊 Мой статус", "callback": "status"}],
                    [{"text": "❓ Помощь", "callback": "help"}, {"text": "⚙️ Настройки", "callback": "settings"}],
                    [{"text": "💎 Premium активен", "callback": "premium_info"}]
                ],
                "admin": [
                    [{"text": "📊 Статус", "callback": "status"}, {"text": "👑 Админка", "callback": "admin"}],
                    [{"text": "📈 Статистика", "callback": "stats"}, {"text": "📢 Рассылка", "callback": "broadcast"}],
                    [{"text": "❓ Помощь", "callback": "help"}, {"text": "⚙️ Настройки", "callback": "settings"}]
                ]
            },
            
            "batch_options": [
                [{"text": "📱 Отправить в чат", "callback": "batch_individual"}],
                [{"text": "📦 Архивом через CDN", "callback": "batch_archive"}],
                [{"text": "⚙️ Выбрать файлы", "callback": "batch_selective"}],
                [{"text": "❌ Отмена", "callback": "batch_cancel"}]
            ],
            
            "premium_options": [
                [{"text": "💳 Купить Premium", "callback": "buy_premium"}],
                [{"text": "🎁 Пробный период", "callback": "trial_info"}],
                [{"text": "❓ Что дает Premium", "callback": "premium_benefits"}],
                [{"text": "🔙 Назад", "callback": "back_main"}]
            ],
            
            "admin_panel": [
                [{"text": "👥 Пользователи", "callback": "admin_users"}, {"text": "📊 Статистика", "callback": "admin_stats"}],
                [{"text": "📢 Рассылка", "callback": "admin_broadcast"}, {"text": "⚙️ Настройки", "callback": "admin_settings"}],
                [{"text": "📋 Каналы", "callback": "admin_channels"}, {"text": "💰 Финансы", "callback": "admin_finance"}],
                [{"text": "🔙 Назад", "callback": "back_main"}]
            ]
        }
    
    def get_commands_for_registration(self) -> List[Dict]:
        """Получить команды для регистрации в BotFather"""
        public_commands = []
        
        for cmd, config in self.commands.items():
            if not config.get("admin_only", False):
                public_commands.append({
                    "command": cmd,
                    "description": config["description"]
                })
        
        return public_commands
    
    def get_message_text(self, message_type: str, subtype: str = "main", **kwargs) -> str:
        """Получить текст сообщения с подстановкой переменных"""
        try:
            template = self.messages[message_type][subtype]
            return template.format(**kwargs)
        except (KeyError, ValueError) as e:
            return f"Ошибка в шаблоне сообщения: {e}"
    
    def format_user_status(self, user) -> str:
        """Форматировать статус пользователя"""
        status_parts = []
        
        # Тип аккаунта
        if user.current_user_type == "premium":
            status_parts.append("💎 Premium")
            if user.premium_expires_at:
                status_parts.append(f"до {user.premium_expires_at.strftime('%d.%m.%Y')}")
        elif user.current_user_type == "trial":
            status_parts.append("🔥 Пробный период")
            if user.trial_expires_at:
                remaining = user.trial_expires_at - user.created_at  # Упрощено
                status_parts.append(f"осталось {remaining}")
        elif user.current_user_type == "admin":
            status_parts.append("👑 Администратор")
        else:
            status_parts.append("🆓 Бесплатный")
        
        # Лимиты
        daily_limit = self.get_user_daily_limit(user.current_user_type)
        if daily_limit < 999:
            status_parts.append(f"Сегодня: {user.downloads_today}/{daily_limit}")
        else:
            status_parts.append("Безлимитные скачивания")
        
        return " | ".join(status_parts)


# Глобальный экземпляр конфигурации
bot_config = BotConfig()

# Константы для удобства
ADMIN_IDS = bot_config.admin_ids
MAX_FILE_SIZE_MB = bot_config.limits.max_file_size_mb
MAX_BATCH_SIZE = bot_config.limits.max_batch_size
RATE_LIMIT_PER_MINUTE = bot_config.limits.rate_limit_requests_per_minute

# Функции-хелперы
def is_admin(user_id: int) -> bool:
    """Проверить админа"""
    return bot_config.is_admin(user_id)

def get_message(message_type: MessageType, subtype: str = "main", **kwargs) -> str:
    """Получить сообщение"""
    return bot_config.get_message_text(message_type.value, subtype, **kwargs)

def get_user_limits(user_type: str) -> Dict:
    """Получить лимиты пользователя"""
    return {
        "daily_downloads": bot_config.get_user_daily_limit(user_type),
        "max_file_size_mb": bot_config.get_user_file_limit(user_type),
        "max_batch_size": MAX_BATCH_SIZE
    }