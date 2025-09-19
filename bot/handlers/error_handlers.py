"""
VideoBot Pro - Error Handlers
Обработчики ошибок и исключений для бота
"""

import asyncio
import structlog
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Union

from aiogram import BaseMiddleware, Router
from aiogram.types import ErrorEvent, Update, Message, CallbackQuery, InlineQuery
from aiogram.exceptions import (
    TelegramBadRequest, 
    TelegramForbiddenError, 
    TelegramNotFound,
    TelegramUnauthorizedError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramNetworkError
)
from aiogram.fsm.context import FSMContext

from shared.config.database import get_async_session
from shared.models import User, EventType
from shared.models.analytics import track_user_event
from bot.config import bot_config

logger = structlog.get_logger(__name__)

router = Router(name="error_handlers")


class ErrorHandlerMiddleware(BaseMiddleware):
    """Middleware для обработки ошибок на уровне обновлений"""
    
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            await self.handle_middleware_error(event, e, data)
            return None
    
    async def handle_middleware_error(self, update: Update, error: Exception, data: Dict[str, Any]):
        """Обработка ошибок в middleware"""
        user_id = None
        chat_id = None
        
        # Извлекаем информацию о пользователе
        if update.message:
            user_id = update.message.from_user.id if update.message.from_user else None
            chat_id = update.message.chat.id
        elif update.callback_query:
            user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
            chat_id = update.callback_query.message.chat.id if update.callback_query.message else None
        elif update.inline_query:
            user_id = update.inline_query.from_user.id if update.inline_query.from_user else None
        
        logger.error(
            f"Middleware error: {type(error).__name__}: {error}",
            user_id=user_id,
            chat_id=chat_id,
            update_type=type(update).__name__
        )
        
        # Логируем в аналитику если есть пользователь
        if user_id:
            try:
                async with get_async_session() as session:
                    user = await session.get(User, user_id)
                    if user:
                        await track_user_event(
                            event_type=EventType.ERROR_OCCURRED,
                            user_id=user.id,
                            telegram_user_id=user_id,
                            event_data={
                                "error_type": type(error).__name__,
                                "error_message": str(error),
                                "update_type": type(update).__name__
                            }
                        )
            except Exception as analytics_error:
                logger.error(f"Failed to log error to analytics: {analytics_error}")


@router.error()
async def global_error_handler(event: ErrorEvent):
    """
    Глобальный обработчик ошибок для всех типов обновлений
    """
    error = event.exception
    update = event.update
    
    # Извлекаем информацию о пользователе и чате
    user_id = None
    chat_id = None
    message_text = None
    
    if update.message:
        user_id = update.message.from_user.id if update.message.from_user else None
        chat_id = update.message.chat.id
        message_text = update.message.text or update.message.caption
    elif update.callback_query:
        user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
        chat_id = update.callback_query.message.chat.id if update.callback_query.message else None
        message_text = update.callback_query.data
    elif update.inline_query:
        user_id = update.inline_query.from_user.id if update.inline_query.from_user else None
        message_text = update.inline_query.query
    
    # Логируем ошибку
    logger.error(
        f"Global error handler: {type(error).__name__}: {error}",
        user_id=user_id,
        chat_id=chat_id,
        message_text=message_text,
        update_type=type(update).__name__
    )
    
    # Обрабатываем специфичные типы ошибок
    try:
        if isinstance(error, TelegramBadRequest):
            await handle_bad_request_error(update, error)
        elif isinstance(error, TelegramForbiddenError):
            await handle_forbidden_error(update, error)
        elif isinstance(error, TelegramNotFound):
            await handle_not_found_error(update, error)
        elif isinstance(error, TelegramUnauthorizedError):
            await handle_unauthorized_error(update, error)
        elif isinstance(error, TelegramRetryAfter):
            await handle_retry_after_error(update, error)
        elif isinstance(error, (TelegramServerError, TelegramNetworkError)):
            await handle_server_network_error(update, error)
        else:
            await handle_generic_error(update, error)
    
    except Exception as handler_error:
        logger.error(f"Error in error handler: {handler_error}")
    
    # Логируем в аналитику
    await log_error_to_analytics(user_id, error, update)


async def handle_bad_request_error(update: Update, error: TelegramBadRequest):
    """Обработка ошибок Bad Request (400)"""
    error_text = str(error).lower()
    
    if "message is not modified" in error_text:
        # Попытка изменить сообщение на идентичное
        logger.debug("Message not modified error - ignoring")
        return
    
    if "message to edit not found" in error_text:
        # Сообщение для редактирования не найдено
        await send_error_to_user(update, "Сообщение не найдено или уже удалено.")
        return
    
    if "query is too old" in error_text:
        # Callback query слишком старый
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "Запрос устарел. Попробуйте еще раз.",
                    show_alert=True
                )
            except:
                pass
        return
    
    if "file is too big" in error_text:
        await send_error_to_user(update, "Файл слишком большой для отправки.")
        return
    
    if "button_url_invalid" in error_text:
        await send_error_to_user(update, "Неверная ссылка в кнопке.")
        return
    
    # Общая обработка Bad Request
    logger.warning(f"Bad Request error: {error}")


async def handle_forbidden_error(update: Update, error: TelegramForbiddenError):
    """Обработка ошибок Forbidden (403)"""
    error_text = str(error).lower()
    user_id = None
    
    if update.message and update.message.from_user:
        user_id = update.message.from_user.id
    elif update.callback_query and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id
    
    if "bot was blocked by the user" in error_text:
        # Пользователь заблокировал бота
        logger.info(f"User blocked the bot", user_id=user_id)
        await mark_user_as_blocked(user_id)
        return
    
    if "chat not found" in error_text:
        # Чат не найден
        logger.warning(f"Chat not found", user_id=user_id)
        return
    
    if "not enough rights" in error_text:
        # Недостаточно прав
        await send_error_to_user(update, "У бота недостаточно прав для выполнения этого действия.")
        return
    
    logger.warning(f"Forbidden error: {error}", user_id=user_id)


async def handle_not_found_error(update: Update, error: TelegramNotFound):
    """Обработка ошибок Not Found (404)"""
    logger.warning(f"Not Found error: {error}")
    
    # Обычно это означает что чат/пользователь/сообщение не существует
    # Просто логируем, пользователю ничего не отправляем


async def handle_unauthorized_error(update: Update, error: TelegramUnauthorizedError):
    """Обработка ошибок Unauthorized (401)"""
    logger.critical(f"Bot token is invalid: {error}")
    
    # Критическая ошибка - неверный токен бота
    # Здесь можно добавить уведомление администраторов


async def handle_retry_after_error(update: Update, error: TelegramRetryAfter):
    """Обработка ошибок Rate Limit (429)"""
    retry_after = error.retry_after
    
    logger.warning(f"Rate limit hit, retry after {retry_after} seconds")
    
    # Можно добавить логику повторной отправки через указанное время
    # или уведомить пользователя о временной недоступности
    
    await send_error_to_user(
        update, 
        f"Слишком много запросов. Попробуйте через {retry_after} секунд."
    )


async def handle_server_network_error(update: Update, error: Union[TelegramServerError, TelegramNetworkError]):
    """Обработка серверных ошибок и ошибок сети"""
    logger.error(f"Server/Network error: {type(error).__name__}: {error}")
    
    await send_error_to_user(
        update,
        "Временные проблемы с сервером. Попробуйте позже."
    )


async def handle_generic_error(update: Update, error: Exception):
    """Обработка всех остальных ошибок"""
    logger.error(f"Unhandled error: {type(error).__name__}: {error}")
    
    await send_error_to_user(
        update,
        "Произошла неожиданная ошибка. Попробуйте позже или обратитесь в поддержку."
    )


async def send_error_to_user(update: Update, message: str):
    """Отправить сообщение об ошибке пользователю"""
    try:
        if update.message:
            await update.message.answer(f"⚠ {message}")
        elif update.callback_query:
            try:
                await update.callback_query.answer(message, show_alert=True)
            except:
                # Если callback_query не удалось, попробуем отправить сообщение
                if update.callback_query.message:
                    await update.callback_query.message.answer(f"⚠ {message}")
    except Exception as send_error:
        logger.error(f"Failed to send error message to user: {send_error}")


async def mark_user_as_blocked(user_id: int):
    """Отметить пользователя как заблокировавшего бота"""
    if not user_id:
        return
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if user:
                user.is_bot_blocked = True
                user.bot_blocked_at = datetime.utcnow()
                await session.commit()
                
                logger.info(f"Marked user as blocked", user_id=user_id)
    except Exception as e:
        logger.error(f"Failed to mark user as blocked: {e}", user_id=user_id)


async def log_error_to_analytics(user_id: int, error: Exception, update: Update):
    """Логирование ошибки в аналитику"""
    if not user_id:
        return
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if user:
                await track_user_event(
                    event_type=EventType.ERROR_OCCURRED,
                    user_id=user.id,
                    telegram_user_id=user_id,
                    event_data={
                        "error_type": type(error).__name__,
                        "error_message": str(error)[:500],  # Ограничиваем длину
                        "update_type": type(update).__name__,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
    except Exception as analytics_error:
        logger.error(f"Failed to log error analytics: {analytics_error}")


# Специальные обработчики для конкретных ошибок приложения

async def handle_database_error(error: Exception, context: str = ""):
    """Обработка ошибок базы данных"""
    logger.error(f"Database error in {context}: {error}")
    
    # Здесь можно добавить специфичную логику:
    # - Повторные попытки подключения
    # - Уведомление администраторов
    # - Переключение на резервную БД


async def handle_api_error(error: Exception, service: str = "", context: str = ""):
    """Обработка ошибок внешних API"""
    logger.error(f"API error for {service} in {context}: {error}")
    
    # Специфичная обработка API ошибок:
    # - Повторные запросы с экспоненциальной задержкой
    # - Переключение на альтернативные сервисы
    # - Кэширование результатов


async def handle_file_operation_error(error: Exception, operation: str = "", file_path: str = ""):
    """Обработка ошибок файловых операций"""
    logger.error(f"File operation error during {operation} for {file_path}: {error}")
    
    # Обработка файловых ошибок:
    # - Проверка свободного места
    # - Очистка временных файлов
    # - Создание отсутствующих директорий


# Декораторы для обработки ошибок

def handle_errors(error_message: str = "Произошла ошибка"):
    """
    Декоратор для автоматической обработки ошибок в хендлерах
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {func.__name__}: {e}")
                
                # Пытаемся найти объект сообщения или callback в аргументах
                message_or_callback = None
                for arg in args:
                    if isinstance(arg, (Message, CallbackQuery)):
                        message_or_callback = arg
                        break
                
                if message_or_callback:
                    try:
                        if isinstance(message_or_callback, Message):
                            await message_or_callback.answer(f"⚠ {error_message}")
                        elif isinstance(message_or_callback, CallbackQuery):
                            await message_or_callback.answer(error_message, show_alert=True)
                    except:
                        pass  # Если не удалось отправить, просто игнорируем
                
                return None
        return wrapper
    return decorator


def handle_database_errors(func):
    """Декоратор для обработки ошибок базы данных"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            await handle_database_error(e, func.__name__)
            raise
    return wrapper


def handle_api_errors(service_name: str):
    """Декоратор для обработки ошибок API"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                await handle_api_error(e, service_name, func.__name__)
                raise
        return wrapper
    return decorator


# Утилиты для мониторинга

class ErrorMetrics:
    """Класс для сбора метрик ошибок"""
    
    def __init__(self):
        self.error_counts = {}
        self.last_reset = datetime.utcnow()
    
    def increment_error(self, error_type: str):
        """Увеличить счетчик ошибок"""
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
    
    def get_error_rate(self, error_type: str) -> float:
        """Получить частоту ошибок"""
        total_errors = sum(self.error_counts.values())
        if total_errors == 0:
            return 0.0
        return self.error_counts.get(error_type, 0) / total_errors
    
    def reset_metrics(self):
        """Сбросить метрики"""
        self.error_counts.clear()
        self.last_reset = datetime.utcnow()
    
    def get_top_errors(self, limit: int = 10) -> list:
        """Получить топ ошибок"""
        return sorted(
            self.error_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]


# Глобальный объект для метрик
error_metrics = ErrorMetrics()


async def setup_error_handlers(dp):
    """Настройка обработчиков ошибок"""
    # Регистрируем middleware
    dp.message.middleware(ErrorHandlerMiddleware())
    dp.callback_query.middleware(ErrorHandlerMiddleware())
    
    # Регистрируем роутер с обработчиками ошибок
    dp.include_router(router)
    
    logger.info("Error handlers configured")


# Периодическая задача для сброса метрик
async def reset_error_metrics_periodically():
    """Периодический сброс метрик ошибок"""
    while True:
        await asyncio.sleep(3600)  # Каждый час
        error_metrics.reset_metrics()
        logger.info("Error metrics reset")