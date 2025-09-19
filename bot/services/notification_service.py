"""
VideoBot Pro - Notification Service
Сервис для отправки уведомлений пользователям
"""

import structlog
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from enum import Enum
import asyncio

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from shared.config.database import get_async_session
from shared.models import User, DownloadTask, DownloadBatch, BroadcastMessage, EventType
from shared.models.analytics import track_system_event
from shared.config.settings import settings
from bot.config import bot_config
from bot.utils.message_builder import (
    build_success_message,
    build_error_message,
    format_file_size,
    format_duration
)

logger = structlog.get_logger(__name__)

class NotificationType(Enum):
    """Типы уведомлений"""
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    BATCH_COMPLETED = "batch_completed"
    BATCH_FAILED = "batch_failed"
    PREMIUM_EXPIRED = "premium_expired"
    TRIAL_EXPIRED = "trial_expired"
    SYSTEM_MAINTENANCE = "system_maintenance"
    BROADCAST = "broadcast"

class NotificationPriority(Enum):
    """Приоритеты уведомлений"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

class NotificationService:
    """Сервис для отправки уведомлений"""
    
    def __init__(self, bot: Bot):
        """
        Инициализация сервиса
        
        Args:
            bot: Экземпляр Telegram бота
        """
        self.bot = bot
        self.max_retries = 3
        self.retry_delays = [1, 5, 15]  # секунды между попытками
        self.rate_limit_delay = 1  # секунда между отправками для избежания flood
    
    async def notify_download_completed(
        self,
        user: User,
        task: DownloadTask,
        file_info: Optional[Dict] = None
    ) -> bool:
        """
        Уведомить о завершении загрузки
        
        Args:
            user: Пользователь
            task: Задача загрузки
            file_info: Информация о файле
            
        Returns:
            True если уведомление отправлено
        """
        # Проверяем настройки пользователя
        if not self._should_send_notification(user, NotificationType.DOWNLOAD_COMPLETED):
            return False
        
        try:
            # Формируем сообщение
            message_text = [
                "✅ <b>Загрузка завершена!</b>",
                "",
                f"🎬 Платформа: {task.platform.title() if task.platform else 'Неизвестно'}",
            ]
            
            if task.title:
                message_text.append(f"📝 Название: {task.title[:50]}...")
            
            if task.duration_seconds:
                message_text.append(f"⏱ Длительность: {format_duration(task.duration_seconds)}")
            
            if task.file_size_bytes:
                message_text.append(f"📊 Размер: {format_file_size(task.file_size_bytes)}")
            
            if task.quality:
                message_text.append(f"🎯 Качество: {task.quality}")
            
            # Добавляем информацию о CDN ссылке
            keyboard = None
            if task.cdn_url:
                message_text.extend([
                    "",
                    f"🔗 Файл доступен для скачивания"
                ])
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="📥 Скачать файл",
                        url=task.cdn_url
                    )
                ]])
            
            text = "\n".join(message_text)
            
            return await self._send_notification(
                user_id=user.telegram_id,
                text=text,
                keyboard=keyboard,
                notification_type=NotificationType.DOWNLOAD_COMPLETED
            )
            
        except Exception as e:
            logger.error(f"Error sending download completed notification: {e}")
            return False
    
    async def notify_download_failed(
        self,
        user: User,
        task: DownloadTask,
        error_message: str
    ) -> bool:
        """
        Уведомить о неудачной загрузке
        
        Args:
            user: Пользователь
            task: Задача загрузки
            error_message: Сообщение об ошибке
            
        Returns:
            True если уведомление отправлено
        """
        if not self._should_send_notification(user, NotificationType.DOWNLOAD_FAILED):
            return False
        
        try:
            # Определяем тип ошибки для пользователя
            user_friendly_error = self._get_user_friendly_error(error_message)
            
            message_text = [
                "❌ <b>Ошибка загрузки</b>",
                "",
                f"🔗 URL: {task.url[:50]}...",
                f"🎬 Платформа: {task.platform.title() if task.platform else 'Неизвестно'}",
                "",
                f"💬 Причина: {user_friendly_error}"
            ]
            
            # Предложения по решению
            suggestions = self._get_error_suggestions(error_message)
            if suggestions:
                message_text.extend(["", "💡 <b>Попробуйте:</b>"])
                message_text.extend([f"• {suggestion}" for suggestion in suggestions])
            
            # Кнопки для действий
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔄 Попробовать снова",
                        callback_data=f"retry_task_{task.id}"
                    ),
                    InlineKeyboardButton(
                        text="🆘 Поддержка",
                        callback_data="support"
                    )
                ]
            ])
            
            text = "\n".join(message_text)
            
            return await self._send_notification(
                user_id=user.telegram_id,
                text=text,
                keyboard=keyboard,
                notification_type=NotificationType.DOWNLOAD_FAILED,
                priority=NotificationPriority.HIGH
            )
            
        except Exception as e:
            logger.error(f"Error sending download failed notification: {e}")
            return False
    
    async def notify_batch_completed(
        self,
        user: User,
        batch: DownloadBatch,
        completed_count: int,
        failed_count: int,
        total_size_mb: float = 0
    ) -> bool:
        """
        Уведомить о завершении batch загрузки
        
        Args:
            user: Пользователь
            batch: Batch загрузки
            completed_count: Количество успешных загрузок
            failed_count: Количество неудачных загрузок
            total_size_mb: Общий размер файлов в МБ
            
        Returns:
            True если уведомление отправлено
        """
        if not self._should_send_notification(user, NotificationType.BATCH_COMPLETED):
            return False
        
        try:
            total_files = batch.total_urls
            success_rate = (completed_count / total_files) * 100 if total_files > 0 else 0
            
            message_text = [
                "🎉 <b>Групповая загрузка завершена!</b>",
                "",
                f"📊 Результат: {completed_count}/{total_files} файлов",
                f"📈 Успешность: {success_rate:.1f}%"
            ]
            
            if failed_count > 0:
                message_text.append(f"❌ Ошибок: {failed_count}")
            
            if total_size_mb > 0:
                message_text.append(f"💾 Общий размер: {total_size_mb:.1f} MB")
            
            # Информация о способе доставки
            delivery_info = self._get_delivery_info(batch)
            if delivery_info:
                message_text.extend(["", delivery_info])
            
            # Кнопки для действий
            keyboard_buttons = []
            
            if batch.archive_url:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="📦 Скачать архив",
                        url=batch.archive_url
                    )
                ])
            
            if failed_count > 0:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="🔄 Повторить неудачные",
                        callback_data=f"retry_batch_{batch.id}"
                    )
                ])
            
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="📊 Подробная статистика",
                    callback_data=f"batch_stats_{batch.id}"
                )
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None
            
            text = "\n".join(message_text)
            
            return await self._send_notification(
                user_id=user.telegram_id,
                text=text,
                keyboard=keyboard,
                notification_type=NotificationType.BATCH_COMPLETED
            )
            
        except Exception as e:
            logger.error(f"Error sending batch completed notification: {e}")
            return False
    
    async def notify_premium_expiring(
        self,
        user: User,
        days_remaining: int
    ) -> bool:
        """
        Уведомить об истечении Premium
        
        Args:
            user: Пользователь
            days_remaining: Дней до истечения
            
        Returns:
            True если уведомление отправлено
        """
        if not self._should_send_notification(user, NotificationType.PREMIUM_EXPIRED):
            return False
        
        try:
            if days_remaining > 1:
                message_text = [
                    "⏰ <b>Premium скоро закончится!</b>",
                    "",
                    f"📅 Осталось дней: {days_remaining}",
                    f"📆 Истекает: {user.premium_expires_at.strftime('%d.%m.%Y')}",
                ]
            else:
                message_text = [
                    "🚨 <b>Premium истекает сегодня!</b>",
                    "",
                    "⏰ Premium доступ заканчивается в течение дня.",
                ]
            
            message_text.extend([
                "",
                "💎 <b>Что вы потеряете:</b>",
                "• Безлимитные скачивания",
                "• 4K качество",
                "• Приоритетная обработка",
                "• Хранение файлов 30 дней",
                "",
                f"🔄 Автопродление: {'Включено' if user.premium_auto_renew else 'Отключено'}"
            ])
            
            keyboard_buttons = [
                [InlineKeyboardButton(
                    text="💎 Продлить Premium",
                    callback_data="renew_premium"
                )]
            ]
            
            if not user.premium_auto_renew:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="🔄 Включить автопродление",
                        callback_data="enable_auto_renew"
                    )
                ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            text = "\n".join(message_text)
            
            return await self._send_notification(
                user_id=user.telegram_id,
                text=text,
                keyboard=keyboard,
                notification_type=NotificationType.PREMIUM_EXPIRED,
                priority=NotificationPriority.HIGH
            )
            
        except Exception as e:
            logger.error(f"Error sending premium expiring notification: {e}")
            return False
    
    async def notify_trial_expiring(
        self,
        user: User,
        minutes_remaining: int
    ) -> bool:
        """
        Уведомить об истечении пробного периода
        
        Args:
            user: Пользователь
            minutes_remaining: Минут до истечения
            
        Returns:
            True если уведомление отправлено
        """
        if not self._should_send_notification(user, NotificationType.TRIAL_EXPIRED):
            return False
        
        try:
            message_text = [
                "⏰ <b>Пробный период скоро закончится!</b>",
                "",
                f"⏱ Осталось: {minutes_remaining} минут",
                "",
                "🎯 <b>Успейте воспользоваться:</b>",
                "• Безлимитными скачиваниями",
                "• HD качеством",
                "• Приоритетной обработкой",
                "",
                "💎 <b>Получите Premium со скидкой 20%!</b>"
            ]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="💎 Купить Premium (-20%)",
                    callback_data="buy_premium_trial_discount"
                )],
                [InlineKeyboardButton(
                    text="📊 Статистика пробного периода",
                    callback_data="trial_stats"
                )]
            ])
            
            text = "\n".join(message_text)
            
            return await self._send_notification(
                user_id=user.telegram_id,
                text=text,
                keyboard=keyboard,
                notification_type=NotificationType.TRIAL_EXPIRED,
                priority=NotificationPriority.HIGH
            )
            
        except Exception as e:
            logger.error(f"Error sending trial expiring notification: {e}")
            return False
    
    async def send_broadcast(
        self,
        broadcast: BroadcastMessage,
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Отправить рассылку
        
        Args:
            broadcast: Сообщение рассылки
            test_mode: Тестовый режим (отправка только админам)
            
        Returns:
            Статистика отправки
        """
        try:
            # Получаем список пользователей для рассылки
            target_users = await self._get_broadcast_targets(broadcast, test_mode)
            
            stats = {
                'total_targets': len(target_users),
                'sent': 0,
                'failed': 0,
                'blocked': 0,
                'errors': []
            }
            
            # Отправляем сообщения с задержкой
            for user_id in target_users:
                try:
                    success = await self._send_notification(
                        user_id=user_id,
                        text=broadcast.message_text,
                        parse_mode=broadcast.parse_mode,
                        keyboard=self._parse_broadcast_keyboard(broadcast.inline_buttons),
                        notification_type=NotificationType.BROADCAST
                    )
                    
                    if success:
                        stats['sent'] += 1
                    else:
                        stats['failed'] += 1
                    
                    # Задержка между отправками
                    await asyncio.sleep(self.rate_limit_delay)
                    
                except TelegramForbiddenError:
                    stats['blocked'] += 1
                except Exception as e:
                    stats['failed'] += 1
                    stats['errors'].append(str(e))
            
            # Обновляем статистику рассылки
            async with get_async_session() as session:
                db_broadcast = await session.get(BroadcastMessage, broadcast.id)
                if db_broadcast:
                    db_broadcast.mark_as_completed(
                        sent_count=stats['sent'],
                        failed_count=stats['failed'],
                        blocked_count=stats['blocked']
                    )
                    await session.commit()
            
            # Системная аналитика
            await track_system_event(
                event_type=EventType.BROADCAST_COMPLETED,
                event_data={
                    'broadcast_id': broadcast.id,
                    'target_type': broadcast.target_type,
                    **stats
                }
            )
            
            logger.info(
                "Broadcast completed",
                broadcast_id=broadcast.id,
                **stats
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Error sending broadcast: {e}")
            return {'error': str(e)}
    
    async def _send_notification(
        self,
        user_id: int,
        text: str,
        keyboard: Optional[InlineKeyboardMarkup] = None,
        parse_mode: str = "HTML",
        notification_type: NotificationType = NotificationType.SYSTEM_MAINTENANCE,
        priority: NotificationPriority = NotificationPriority.NORMAL
    ) -> bool:
        """
        Отправить уведомление с повторными попытками
        
        Args:
            user_id: ID пользователя
            text: Текст сообщения
            keyboard: Клавиатура
            parse_mode: Режим парсинга
            notification_type: Тип уведомления
            priority: Приоритет
            
        Returns:
            True если отправлено успешно
        """
        for attempt in range(self.max_retries):
            try:
                await self.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True
                )
                
                logger.debug(
                    "Notification sent",
                    user_id=user_id,
                    type=notification_type.value,
                    attempt=attempt + 1
                )
                
                return True
                
            except TelegramForbiddenError:
                # Пользователь заблокировал бота
                await self._mark_user_as_blocked(user_id)
                logger.info(f"User {user_id} blocked the bot")
                return False
                
            except TelegramBadRequest as e:
                # Невосстанавливаемая ошибка
                logger.warning(f"Bad request sending notification: {e}")
                return False
                
            except Exception as e:
                logger.warning(
                    f"Error sending notification (attempt {attempt + 1}): {e}",
                    user_id=user_id
                )
                
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delays[attempt])
                else:
                    logger.error(f"Failed to send notification after {self.max_retries} attempts")
                    return False
        
        return False
    
    def _should_send_notification(self, user: User, notification_type: NotificationType) -> bool:
        """Проверить нужно ли отправлять уведомление"""
        # Проверяем заблокирован ли пользователь
        if user.is_banned or user.is_bot_blocked:
            return False
        
        # Проверяем настройки уведомлений пользователя
        notification_settings = user.notification_settings or {}
        
        if not notification_settings.get('enabled', True):
            return False
        
        # Специфичные настройки для типов уведомлений
        type_settings = {
            NotificationType.DOWNLOAD_COMPLETED: notification_settings.get('download_complete', True),
            NotificationType.DOWNLOAD_FAILED: notification_settings.get('download_complete', True),
            NotificationType.BATCH_COMPLETED: notification_settings.get('download_complete', True),
            NotificationType.PREMIUM_EXPIRED: notification_settings.get('premium_expiry', True),
            NotificationType.TRIAL_EXPIRED: notification_settings.get('trial_expiry', True),
            NotificationType.SYSTEM_MAINTENANCE: notification_settings.get('system_updates', True),
            NotificationType.BROADCAST: notification_settings.get('broadcasts', True),
        }
        
        return type_settings.get(notification_type, True)
    
    def _get_user_friendly_error(self, error_message: str) -> str:
        """Преобразовать техническую ошибку в понятную пользователю"""
        error_lower = error_message.lower()
        
        if 'video unavailable' in error_lower or 'private' in error_lower:
            return "Видео недоступно или удалено"
        elif 'age restricted' in error_lower:
            return "Видео имеет возрастные ограничения"
        elif 'geo blocked' in error_lower or 'not available in your country' in error_lower:
            return "Видео недоступно в вашей стране"
        elif 'network' in error_lower or 'connection' in error_lower:
            return "Проблемы с сетевым соединением"
        elif 'timeout' in error_lower:
            return "Превышено время ожидания"
        elif 'file too large' in error_lower:
            return "Файл слишком большой"
        elif 'format not available' in error_lower:
            return "Нужное качество недоступно"
        else:
            return "Техническая ошибка сервиса"
    
    def _get_error_suggestions(self, error_message: str) -> List[str]:
        """Получить предложения по решению ошибки"""
        error_lower = error_message.lower()
        suggestions = []
        
        if 'video unavailable' in error_lower:
            suggestions.extend([
                "Проверьте доступность видео в браузере",
                "Попробуйте другую ссылку на то же видео"
            ])
        elif 'network' in error_lower:
            suggestions.extend([
                "Попробуйте еще раз через несколько минут",
                "Проверьте интернет соединение"
            ])
        elif 'file too large' in error_lower:
            suggestions.extend([
                "Выберите качество пониже",
                "Рассмотрите Premium для больших файлов"
            ])
        else:
            suggestions.append("Попробуйте загрузить видео позже")
        
        return suggestions
    
    def _get_delivery_info(self, batch: DownloadBatch) -> Optional[str]:
        """Получить информацию о способе доставки"""
        if batch.create_archive and batch.archive_url:
            expires_hours = 24 if batch.user.current_user_type == "free" else 30 * 24
            return f"📦 Файлы упакованы в архив (доступен {expires_hours}ч)"
        elif batch.send_to_chat:
            return "📱 Файлы отправлены в чат по одному"
        else:
            return None
    
    async def _get_broadcast_targets(
        self,
        broadcast: BroadcastMessage,
        test_mode: bool = False
    ) -> List[int]:
        """Получить список пользователей для рассылки"""
        try:
            async with get_async_session() as session:
                if test_mode:
                    # Отправляем только админам в тестовом режиме
                    query = """
                        SELECT telegram_id FROM users 
                        WHERE telegram_id = ANY(:admin_ids)
                        AND is_bot_blocked = false
                    """
                    params = {'admin_ids': bot_config.admin_ids}
                else:
                    # Формируем запрос в зависимости от типа аудитории
                    query = "SELECT telegram_id FROM users WHERE is_bot_blocked = false"
                    params = {}
                    
                    if broadcast.target_type == "premium_users":
                        query += " AND is_premium = true"
                    elif broadcast.target_type == "free_users":
                        query += " AND is_premium = false"
                    elif broadcast.target_type == "trial_users":
                        query += " AND user_type = 'trial'"
                    
                    # Дополнительные фильтры
                    if broadcast.target_filters:
                        filters = broadcast.target_filters
                        
                        if 'last_active_days' in filters:
                            query += " AND last_active_at > NOW() - INTERVAL :days DAY"
                            params['days'] = filters['last_active_days']
                        
                        if 'registration_days' in filters:
                            query += " AND created_at > NOW() - INTERVAL :reg_days DAY"
                            params['reg_days'] = filters['registration_days']
                
                result = await session.execute(query, params)
                user_ids = [row[0] for row in result.fetchall()]
                
                return user_ids
                
        except Exception as e:
            logger.error(f"Error getting broadcast targets: {e}")
            return []
    
    def _parse_broadcast_keyboard(self, buttons_data: Optional[Dict]) -> Optional[InlineKeyboardMarkup]:
        """Парсинг кнопок для рассылки"""
        if not buttons_data:
            return None
        
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            
            for row in buttons_data.get('inline_keyboard', []):
                button_row = []
                for button in row:
                    if 'url' in button:
                        button_row.append(InlineKeyboardButton(
                            text=button['text'],
                            url=button['url']
                        ))
                    elif 'callback_data' in button:
                        button_row.append(InlineKeyboardButton(
                            text=button['text'],
                            callback_data=button['callback_data']
                        ))
                
                if button_row:
                    keyboard.inline_keyboard.append(button_row)
            
            return keyboard if keyboard.inline_keyboard else None
            
        except Exception as e:
            logger.error(f"Error parsing broadcast keyboard: {e}")
            return None
    
    async def _mark_user_as_blocked(self, user_id: int):
        """Отметить что пользователь заблокировал бота"""
        try:
            async with get_async_session() as session:
                user = await session.get(User, user_id)
                if user:
                    user.is_bot_blocked = True
                    user.bot_blocked_at = datetime.utcnow()
                    await session.commit()
        except Exception as e:
            logger.error(f"Error marking user as blocked: {e}")

# Функция для создания глобального экземпляра
def create_notification_service(bot: Bot) -> NotificationService:
    """Создать экземпляр сервиса уведомлений"""
    return NotificationService(bot)

# Глобальная переменная (будет инициализирована при запуске бота)
notification_service: Optional[NotificationService] = None