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

logger = structlog.get_logger(__name__)


def setup_handlers(dp: Dispatcher) -> None:
    """
    Регистрация всех обработчиков в диспетчере
    
    Args:
        dp: Диспетчер aiogram
    """
    
    # Порядок регистрации важен - более специфичные обработчики должны быть выше
    routers = [
        # Системные обработчики (высший приоритет)
        error_handlers_router,
        
        # Админские команды (высокий приоритет)
        admin_commands_router,
        
        # Основные команды (высокий приоритет)
        start_router,
        
        # Системы подписок и trial (средний приоритет)
        subscription_check_router,
        trial_system_router,
        
        # Premium система
        premium_router,
        
        # Настройки пользователя
        settings_router,
        
        # Основная функциональность (средний приоритет)
        batch_download_router,
        
        # Обработчики callback'ов (низкий приоритет - ловит все остальное)
        callback_handlers_router,
    ]
    
    # Регистрируем все роутеры
    for router in routers:
        dp.include_router(router)
        logger.info(f"Registered router: {router.name}")
    
    logger.info(f"Total routers registered: {len(routers)}")


async def setup_handler_dependencies(bot) -> None:
    """
    Инициализация зависимостей для обработчиков
    
    Args:
        bot: Экземпляр бота
    """
    
    # Инициализируем проверяльщик подписок
    init_subscription_checker(bot)
    
    # Настраиваем обработчики ошибок (регистрируем middleware)
    from aiogram import Dispatcher
    dp = Dispatcher.get_current()
    if dp:
        await setup_error_handlers(dp)
    
    logger.info("Handler dependencies initialized")


def get_all_routers():
    """Получить список всех роутеров"""
    return [
        start_router,
        batch_download_router,
        subscription_check_router,
        settings_router,
        trial_system_router,
        admin_commands_router,
        premium_router,
        callback_handlers_router,
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
        router_info = {
            "name": router.name,
            "handlers_count": len(router.observers),
            "middleware_count": len(router.message.middleware.data) if hasattr(router, 'message') else 0
        }
        info["routers"].append(router_info)
    
    return info


# Список всех доступных роутеров для экспорта
__all__ = [
    "setup_handlers",
    "setup_handler_dependencies",
    "get_all_routers",
    "get_handlers_info",
    "start_router",
    "batch_download_router", 
    "subscription_check_router",
    "settings_router",
    "trial_system_router",
    "admin_commands_router",
    "premium_router",
    "callback_handlers_router",
    "error_handlers_router",
]