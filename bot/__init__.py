"""
VideoBot Pro - Bot Package
Telegram бот для скачивания видео из TikTok, YouTube Shorts, Instagram Reels
"""

from .config import (
    bot_config,
    BotConfig,
    BotMode,
    MessageType,
    BotLimits,

    # Константы
    ADMIN_IDS,
    MAX_FILE_SIZE_MB,
    MAX_BATCH_SIZE,
    RATE_LIMIT_PER_MINUTE,

    # Хелперы
    is_admin,
    get_message,
    get_user_limits
)

__version__ = "2.1.0"

__all__ = [
    "bot_config",
    "BotConfig",
    "BotMode",
    "MessageType",
    "BotLimits",
    "ADMIN_IDS",
    "MAX_FILE_SIZE_MB",
    "MAX_BATCH_SIZE",
    "RATE_LIMIT_PER_MINUTE",
    "is_admin",
    "get_message",
    "get_user_limits",
    "__version__"
]

__author__ = "VideoBot Team"
__description__ = "Advanced Telegram bot for video downloading with Premium features"
__license__ = "MIT"

SUPPORTED_PLATFORMS = ["youtube", "tiktok", "instagram"]
SUPPORTED_FORMATS = ["mp4", "webm"]
AVAILABLE_QUALITIES = ["2160p", "1080p", "720p", "480p", "audio"]

FEATURES = {
    "free": ["10 downloads per day", "720p HD quality", "3 platforms support", "Individual file delivery"],
    "trial": ["60 minutes unlimited", "1080p quality", "All platforms", "No subscriptions required"],
    "premium": ["Unlimited downloads", "4K quality", "Files up to 500MB", "Batch archives", "Priority processing", "No ads", "30-day storage"],
    "admin": ["All Premium features", "Files up to 2GB", "50 links per batch", "Admin panel access", "System monitoring", "User management"]
}

def get_bot_info() -> dict:
    return {
        "name": "VideoBot Pro",
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "supported_platforms": SUPPORTED_PLATFORMS,
        "supported_formats": SUPPORTED_FORMATS,
        "available_qualities": AVAILABLE_QUALITIES,
        "features": FEATURES
    }

def get_platform_info(platform: str = None) -> dict:
    platforms_info = {
        "youtube": {"name": "YouTube Shorts", "domains": ["youtube.com", "youtu.be"], "types": ["shorts", "regular videos"], "max_quality": "4K", "formats": ["mp4", "webm"]},
        "tiktok": {"name": "TikTok", "domains": ["tiktok.com", "vm.tiktok.com"], "types": ["videos", "compilations"], "max_quality": "1080p", "formats": ["mp4"]},
        "instagram": {"name": "Instagram Reels", "domains": ["instagram.com"], "types": ["reels", "videos"], "max_quality": "1080p", "formats": ["mp4"]}
    }
    if platform:
        return platforms_info.get(platform, {})
    return platforms_info

def check_bot_health() -> dict:
    return {
        "status": "healthy",
        "version": __version__,
        "config_loaded": bool(bot_config.token),
        "admin_configured": len(ADMIN_IDS) > 0,
        "features_enabled": {
            "trial": bot_config.trial_enabled,
            "premium": bot_config.premium_system_enabled,
            "batch": bot_config.batch_processing_enabled,
            "subscriptions": bot_config.required_subs_enabled
        }
    }

if not bot_config.token:
    import warnings
    warnings.warn("BOT_TOKEN не настроен! Бот не сможет работать.", UserWarning)

if not ADMIN_IDS:
    import warnings
    warnings.warn("ADMIN_IDS не настроены! Админ функции будут недоступны.", UserWarning)
