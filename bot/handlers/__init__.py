"""
VideoBot Pro - Handlers Package
Централизованная регистрация всех обработчиков бота
"""

import structlog
from aiogram import Dispatcher

# Импортируем все роутеры
from .start import router as start_router
from .batch_download import router as batch_download_router
from .subscription_check import router as subscription_check_router, init_subscription_checker
from .settings import router as settings_router
from .trial_system import router as trial_system_router
from .admin_commands import router as admin_commands_router
from .premium import router as premium_router
from .callback_handlers import router as callback_handlers_router
from .error_handlers import router as error_handlers_router, setup_error_handlers

# Импортируем новый универсальный обработчик
from .universal_callback import router as universal_callback_router

logger = structlog.get_logger(__name__)


def setup_handlers(dp: Dispatcher) -> None:
    """
    Регистрация всех обработчиков в диспетчере
    
    Args:
        dp: Диспетчер aiogram
    """
    
    # КРИТИЧЕСКИ ВАЖЕН ПОРЯДОК РЕГИСТРАЦИИ!
    # Более специфичные обработчики должны быть выше общих
    
    routers = [
        # 1. Системные обработчики (высший приоритет)
        error_handlers_router,
        
        # 2. Специфичные команды (высокий приоритет)
        start_router,                    # /start, /help
        admin_commands_router,           # Админские команды с декорато@admin_only
        
        # 3. Специфичные callback обработчики (средний приоритет)
        settings_router,                 # Все settings_* callback'и
        premium_router,                  # Все premium_* callback'и  
        trial_system_router,             # Все trial_* callback'и
        batch_download_router,           # Все batch_* callback'и
        subscription_check_router,       # Все sub_* callback'и
        
        # 4. Основные callback'и (средний приоритет)
        callback_handlers_router,        # Базовые callback'и (status, help, back_main)
        
        # 5. Универсальный обработчик (низкий приоритет - ловит все остальное)
        universal_callback_router,       # Универсальный роутер - ПОСЛЕДНИЙ!
    ]
    
    # Регистрируем все роутеры
    for i, router in enumerate(routers, 1):
        dp.include_router(router)
        logger.info(f"{i}. Registered router: {router.name}")
    
    logger.info(f"✅ Total routers registered: {len(routers)}")


async def setup_handler_dependencies(bot) -> None:
    """
    Инициализация зависимостей для обработчиков
    
    Args:
        bot: Экземпляр бота
    """
    
    try:
        # Инициализируем проверяльщик подписок
        init_subscription_checker(bot)
        logger.info("✅ Subscription checker initialized")
        
        # Настраиваем обработчики ошибок
        from aiogram import Dispatcher
        dp = Dispatcher.get_current()
        if dp:
            await setup_error_handlers(dp)
            logger.info("✅ Error handlers setup completed")
        
        # Инициализируем другие зависимости
        await _init_callback_dependencies()
        
        logger.info("✅ All handler dependencies initialized")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize handler dependencies: {e}")
        raise


async def _init_callback_dependencies():
    """Инициализация зависимостей для callback обработчиков"""
    
    # Здесь можно добавить инициализацию:
    # - Кэшей для callback'ов
    # - Валидаторов
    # - Других зависимостей
    
    pass


def get_all_routers():
    """Получить список всех роутеров"""
    return [
        start_router,
        admin_commands_router,
        settings_router, 
        premium_router,
        trial_system_router,
        batch_download_router,
        subscription_check_router,
        callback_handlers_router,
        universal_callback_router,
        error_handlers_router,
    ]


def get_handlers_info():
    """Получить информацию о всех обработчиках"""
    routers = get_all_routers()
    info = {
        "total_routers": len(routers),
        "routers": []
    }
    
    for router in routers:
        try:
            # Подсчитываем обработчики разных типов
            message_handlers = len([obs for obs in router.observers.get('message', [])])
            callback_handlers = len([obs for obs in router.observers.get('callback_query', [])])
            
            router_info = {
                "name": router.name,
                "message_handlers": message_handlers,
                "callback_handlers": callback_handlers,
                "total_handlers": message_handlers + callback_handlers
            }
            info["routers"].append(router_info)
            
        except Exception as e:
            logger.warning(f"Error getting info for router {router.name}: {e}")
            info["routers"].append({
                "name": router.name,
                "error": str(e)
            })
    
    return info


def debug_callback_routes():
    """Debug функция для проверки маршрутизации callback'ов"""
    
    from .universal_callback import CALLBACK_ROUTES, get_prefix_handlers
    
    debug_info = {
        "direct_routes": len(CALLBACK_ROUTES),
        "routes": CALLBACK_ROUTES,
        "prefix_handlers": list(get_prefix_handlers().keys()),
        "total_coverage": len(CALLBACK_ROUTES) + len(get_prefix_handlers())
    }
    
    return debug_info


# Список всех доступных роутеров для экспорта
__all__ = [
    "setup_handlers",
    "setup_handler_dependencies", 
    "get_all_routers",
    "get_handlers_info",
    "debug_callback_routes",
    # Отдельные роутеры
    "start_router",
    "batch_download_router", 
    "subscription_check_router",
    "settings_router",
    "trial_system_router",
    "admin_commands_router",
    "premium_router",
    "callback_handlers_router",
    "universal_callback_router",
    "error_handlers_router",
]