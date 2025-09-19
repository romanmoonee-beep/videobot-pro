#!/usr/bin/env python3
"""
VideoBot Pro - Main Bot Entry Point
Главный файл для запуска Telegram бота
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from shared.config.settings import settings
from shared.config.database import init_database, close_database
from shared.config.redis import init_redis, close_redis

# Импорты бота
from bot.config import bot_config
from bot.handlers import setup_handlers
from bot.middlewares import setup_middlewares
from bot.services import initialize_services, cleanup_services

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('videobot.log') if not settings.DEBUG else logging.NullHandler()
    ]
)

# Настройка структурированного логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class BotApplication:
    """Основное приложение бота"""
    
    def __init__(self):
        self.bot = None
        self.dp = None
        self.web_app = None
        self.runner = None
        self.site = None
        self._shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Инициализация всех компонентов"""
        logger.info("🚀 Starting VideoBot Pro v%s", settings.APP_VERSION)
        
        try:
            # 1. Инициализация базы данных
            logger.info("📊 Initializing database...")
            await init_database()
            
            # 2. Инициализация Redis
            logger.info("🔄 Initializing Redis...")
            await init_redis()
            
            # 3. Создание бота
            logger.info("🤖 Initializing Telegram bot...")
            self.bot = Bot(
                token=bot_config.bot_token,
                default=DefaultBotProperties(
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            )
            
            # 4. Создание диспетчера
            self.dp = Dispatcher()
            
            # 5. Настройка middleware
            logger.info("⚙️ Setting up middlewares...")
            setup_middlewares(self.dp)
            
            # 6. Настройка обработчиков
            logger.info("📋 Setting up handlers...")
            setup_handlers(self.dp)
            
            # 7. Инициализация сервисов
            logger.info("🔧 Initializing services...")
            await initialize_services(self.bot)
            
            # 8. Тестовое подключение к Telegram
            bot_info = await self.bot.get_me()
            logger.info("✅ Bot initialized successfully: @%s (%s)", bot_info.username, bot_info.full_name)
            
        except Exception as e:
            logger.error("❌ Failed to initialize bot: %s", e)
            raise
    
    async def start_polling(self):
        """Запуск в режиме polling"""
        logger.info("🔄 Starting polling mode...")
        
        try:
            await self.dp.start_polling(
                self.bot,
                allowed_updates=self.dp.resolve_used_update_types(),
                drop_pending_updates=True
            )
        except Exception as e:
            logger.error("❌ Polling error: %s", e)
            raise
    
    async def start_webhook(self):
        """Запуск в режиме webhook"""
        if not settings.WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL is required for webhook mode")
        
        logger.info("🌐 Starting webhook mode...")
        
        # Настройка webhook
        webhook_url = f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}"
        await self.bot.set_webhook(
            url=webhook_url,
            secret_token=settings.WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        
        # Создание web приложения
        self.web_app = web.Application()
        
        # Настройка webhook handler
        SimpleRequestHandler(
            dispatcher=self.dp,
            bot=self.bot,
            secret_token=settings.WEBHOOK_SECRET
        ).register(self.web_app, path=settings.WEBHOOK_PATH)
        
        # Добавление health check endpoint
        async def health_check(request):
            return web.json_response({"status": "ok", "bot": "VideoBot Pro"})
        
        self.web_app.router.add_get("/health", health_check)
        
        # Запуск web сервера
        self.runner = web.AppRunner(self.web_app)
        await self.runner.setup()
        
        self.site = web.TCPSite(
            self.runner, 
            host="0.0.0.0", 
            port=8000
        )
        await self.site.start()
        
        logger.info("✅ Webhook started on port 8000")
        logger.info("📡 Webhook URL: %s", webhook_url)
    
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("🛑 Shutting down VideoBot Pro...")
        
        try:
            # 1. Остановка webhook если запущен
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            
            # 2. Удаление webhook
            if self.bot:
                await self.bot.delete_webhook(drop_pending_updates=True)
                await self.bot.session.close()
            
            # 3. Очистка сервисов
            await cleanup_services()
            
            # 4. Закрытие подключений
            await close_redis()
            await close_database()
            
            logger.info("✅ Shutdown completed successfully")
            
        except Exception as e:
            logger.error("❌ Error during shutdown: %s", e)
    
    def setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""
        def signal_handler(signum, frame):
            logger.info("📨 Received signal %s", signum)
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Главная функция"""
    app = BotApplication()
    
    try:
        # Настройка обработчиков сигналов
        app.setup_signal_handlers()
        
        # Инициализация
        await app.initialize()
        
        # Выбор режима запуска
        if settings.WEBHOOK_URL and not settings.DEBUG:
            # Webhook режим для production
            await app.start_webhook()
            logger.info("🎯 VideoBot Pro is running in WEBHOOK mode")
        else:
            # Polling режим для разработки
            logger.info("🎯 VideoBot Pro is running in POLLING mode")
            
            # Запуск polling в отдельной задаче
            polling_task = asyncio.create_task(app.start_polling())
            
            # Ожидание сигнала завершения
            await app._shutdown_event.wait()
            
            # Отмена polling
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        
    except KeyboardInterrupt:
        logger.info("⏹️ Received keyboard interrupt")
    except Exception as e:
        logger.error("💥 Critical error: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        # Корректное завершение
        await app.shutdown()


def run():
    """Точка входа для запуска бота"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 VideoBot Pro stopped by user")
    except Exception as e:
        print(f"💥 Failed to start VideoBot Pro: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run()