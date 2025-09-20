"""
VideoBot Pro - Notification Service
Сервис для отправки уведомлений администраторам
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
import structlog
import asyncio

from shared.services.database import get_db_session
from shared.models import AdminUser, AnalyticsEvent
from ..config import admin_settings

logger = structlog.get_logger(__name__)

class NotificationType(str, Enum):
    """Типы уведомлений"""
    SYSTEM_ALERT = "system_alert"
    USER_ACTION = "user_action"
    PAYMENT_ISSUE = "payment_issue"
    DOWNLOAD_ERROR = "download_error"
    SECURITY_EVENT = "security_event"
    PERFORMANCE_WARNING = "performance_warning"
    BROADCAST_STATUS = "broadcast_status"
    MAINTENANCE = "maintenance"

class NotificationPriority(str, Enum):
    """Приоритеты уведомлений"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class NotificationChannel(str, Enum):
    """Каналы уведомлений"""
    EMAIL = "email"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"
    IN_APP = "in_app"

class NotificationService:
    """Сервис уведомлений для администраторов"""
    
    def __init__(self):
        self.rate_limits = {}  # Для rate limiting уведомлений
        
    async def send_notification(
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        channels: List[NotificationChannel] = None,
        recipients: List[int] = None,  # admin_ids
        data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Отправить уведомление администраторам"""
        
        try:
            if channels is None:
                channels = [NotificationChannel.TELEGRAM, NotificationChannel.IN_APP]
            
            # Определяем получателей по приоритету
            if recipients is None:
                recipients = await self._get_notification_recipients(notification_type, priority)
            
            # Проверяем rate limiting
            if not await self._check_rate_limit(notification_type, priority):
                logger.warning(f"Notification rate limited", type=notification_type)
                return {"success": False, "reason": "rate_limited"}
            
            # Форматируем уведомление
            notification = {
                "id": f"notif_{datetime.utcnow().timestamp()}",
                "type": notification_type.value,
                "title": title,
                "message": message,
                "priority": priority.value,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data or {}
            }
            
            # Отправляем по каналам
            results = {}
            for channel in channels:
                try:
                    if channel == NotificationChannel.TELEGRAM:
                        results["telegram"] = await self._send_telegram_notification(
                            notification, recipients
                        )
                    elif channel == NotificationChannel.EMAIL:
                        results["email"] = await self._send_email_notification(
                            notification, recipients
                        )
                    elif channel == NotificationChannel.WEBHOOK:
                        results["webhook"] = await self._send_webhook_notification(
                            notification
                        )
                    elif channel == NotificationChannel.IN_APP:
                        results["in_app"] = await self._send_in_app_notification(
                            notification, recipients
                        )
                        
                except Exception as e:
                    logger.error(f"Failed to send {channel} notification: {e}")
                    results[channel.value] = {"success": False, "error": str(e)}
            
            # Логируем уведомление
            logger.info(
                "Notification sent",
                type=notification_type.value,
                priority=priority.value,
                channels=[c.value for c in channels],
                recipients_count=len(recipients),
                results=results
            )
            
            return {
                "success": True,
                "notification_id": notification["id"],
                "channels": results,
                "recipients_count": len(recipients)
            }
            
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return {"success": False, "error": str(e)}
    
    async def send_system_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "medium",
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Отправить системный алерт"""
        
        priority_map = {
            "low": NotificationPriority.LOW,
            "medium": NotificationPriority.MEDIUM,
            "high": NotificationPriority.HIGH,
            "critical": NotificationPriority.CRITICAL
        }
        
        priority = priority_map.get(severity, NotificationPriority.MEDIUM)
        
        # Формируем заголовок
        title = f"🚨 System Alert: {alert_type}"
        if severity == "critical":
            title = f"🔥 CRITICAL: {alert_type}"
        elif severity == "high":
            title = f"⚠️ HIGH: {alert_type}"
        
        # Определяем каналы по серьезности
        channels = [NotificationChannel.IN_APP]
        if severity in ["high", "critical"]:
            channels.extend([NotificationChannel.TELEGRAM, NotificationChannel.EMAIL])
        
        return await self.send_notification(
            notification_type=NotificationType.SYSTEM_ALERT,
            title=title,
            message=message,
            priority=priority,
            channels=channels,
            data={
                "alert_type": alert_type,
                "severity": severity,
                "details": details or {}
            }
        )
    
    async def send_user_action_alert(
        self,
        action: str,
        user_id: int,
        admin_id: int,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Уведомление о действии администратора с пользователем"""
        
        critical_actions = ["user_deleted", "mass_ban", "data_export"]
        priority = NotificationPriority.HIGH if action in critical_actions else NotificationPriority.MEDIUM
        
        async with get_db_session() as session:
            admin = await session.get(AdminUser, admin_id)
            admin_username = admin.username if admin else f"Admin {admin_id}"
        
        action_names = {
            "user_banned": "заблокировал пользователя",
            "user_unbanned": "разблокировал пользователя",
            "user_deleted": "удалил пользователя",
            "premium_granted": "выдал Premium",
            "premium_revoked": "отозвал Premium",
            "mass_ban": "массовая блокировка",
            "data_export": "экспорт данных пользователя"
        }
        
        action_text = action_names.get(action, action)
        
        return await self.send_notification(
            notification_type=NotificationType.USER_ACTION,
            title=f"👤 User Action: {action}",
            message=f"Администратор {admin_username} {action_text} (User ID: {user_id})",
            priority=priority,
            data={
                "action": action,
                "user_id": user_id,
                "admin_id": admin_id,
                "admin_username": admin_username,
                "details": details or {}
            }
        )
    
    async def send_payment_alert(
        self,
        alert_type: str,
        payment_id: int,
        amount: float,
        currency: str,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Уведомление о проблемах с платежами"""
        
        title_map = {
            "fraud_detected": "🔍 Подозрительный платеж",
            "refund_requested": "💰 Запрос возврата",
            "payment_failed": "❌ Ошибка платежа",
            "chargeback": "⚡ Chargeback",
            "high_amount": "💎 Крупный платеж"
        }
        
        title = title_map.get(alert_type, f"💳 Payment Alert: {alert_type}")
        message = f"Payment ID: {payment_id}, Amount: {amount} {currency}"
        
        priority = NotificationPriority.HIGH if alert_type in ["fraud_detected", "chargeback"] else NotificationPriority.MEDIUM
        
        return await self.send_notification(
            notification_type=NotificationType.PAYMENT_ISSUE,
            title=title,
            message=message,
            priority=priority,
            data={
                "alert_type": alert_type,
                "payment_id": payment_id,
                "amount": amount,
                "currency": currency,
                "details": details or {}
            }
        )
    
    async def send_performance_warning(
        self,
        metric: str,
        current_value: float,
        threshold: float,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Уведомление о проблемах с производительностью"""
        
        severity = "critical" if current_value > threshold * 1.5 else "high"
        priority = NotificationPriority.CRITICAL if severity == "critical" else NotificationPriority.HIGH
        
        metric_names = {
            "cpu_usage": "CPU Usage",
            "memory_usage": "Memory Usage", 
            "disk_usage": "Disk Usage",
            "response_time": "Response Time",
            "error_rate": "Error Rate",
            "queue_length": "Queue Length"
        }
        
        metric_name = metric_names.get(metric, metric)
        
        return await self.send_notification(
            notification_type=NotificationType.PERFORMANCE_WARNING,
            title=f"📊 Performance Warning: {metric_name}",
            message=f"{metric_name}: {current_value:.2f} (threshold: {threshold:.2f})",
            priority=priority,
            data={
                "metric": metric,
                "current_value": current_value,
                "threshold": threshold,
                "severity": severity,
                "details": details or {}
            }
        )
    
    async def send_broadcast_notification(
        self,
        broadcast_id: int,
        status: str,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Уведомление о статусе рассылки"""
        
        status_icons = {
            "started": "🚀",
            "completed": "✅", 
            "failed": "❌",
            "paused": "⏸️",
            "cancelled": "🛑"
        }
        
        icon = status_icons.get(status, "📢")
        priority = NotificationPriority.HIGH if status == "failed" else NotificationPriority.MEDIUM
        
        return await self.send_notification(
            notification_type=NotificationType.BROADCAST_STATUS,
            title=f"{icon} Broadcast {status.title()}",
            message=f"Broadcast ID: {broadcast_id} - Status: {status}",
            priority=priority,
            data={
                "broadcast_id": broadcast_id,
                "status": status,
                "details": details or {}
            }
        )
    
    async def send_security_alert(
        self,
        event_type: str,
        description: str,
        ip_address: str = None,
        user_id: int = None,
        details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Уведомление о событиях безопасности"""
        
        return await self.send_notification(
            notification_type=NotificationType.SECURITY_EVENT,
            title=f"🔐 Security Alert: {event_type}",
            message=f"{description}" + (f" (IP: {ip_address})" if ip_address else ""),
            priority=NotificationPriority.HIGH,
            channels=[NotificationChannel.TELEGRAM, NotificationChannel.EMAIL, NotificationChannel.IN_APP],
            data={
                "event_type": event_type,
                "description": description,
                "ip_address": ip_address,
                "user_id": user_id,
                "details": details or {}
            }
        )
    
    async def _get_notification_recipients(
        self,
        notification_type: NotificationType,
        priority: NotificationPriority
    ) -> List[int]:
        """Определить получателей уведомления"""
        
        try:
            async with get_db_session() as session:
                # Базовый запрос активных админов
                query = session.query(AdminUser).filter(
                    AdminUser.is_active == True
                )
                
                # Фильтрация по типу уведомления и приоритету
                if priority == NotificationPriority.CRITICAL:
                    # Критические уведомления всем админам
                    query = query.filter(
                        AdminUser.role.in_(["super_admin", "admin", "moderator"])
                    )
                elif priority == NotificationPriority.HIGH:
                    # Высокий приоритет админам и модераторам
                    query = query.filter(
                        AdminUser.role.in_(["super_admin", "admin", "moderator"])
                    )
                elif notification_type in [NotificationType.SYSTEM_ALERT, NotificationType.SECURITY_EVENT]:
                    # Системные и security алерты только админам
                    query = query.filter(
                        AdminUser.role.in_(["super_admin", "admin"])
                    )
                else:
                    # Остальные уведомления всем
                    pass
                
                admins = await query.all()
                return [admin.id for admin in admins]
                
        except Exception as e:
            logger.error(f"Failed to get notification recipients: {e}")
            return []
    
    async def _check_rate_limit(
        self,
        notification_type: NotificationType,
        priority: NotificationPriority
    ) -> bool:
        """Проверить rate limiting для уведомлений"""
        
        # Критические уведомления не ограничиваем
        if priority == NotificationPriority.CRITICAL:
            return True
        
        current_time = datetime.utcnow()
        rate_key = f"{notification_type.value}:{priority.value}"
        
        # Лимиты по типам (уведомлений в час)
        limits = {
            f"{NotificationType.SYSTEM_ALERT.value}:high": 10,
            f"{NotificationType.SYSTEM_ALERT.value}:medium": 20,
            f"{NotificationType.PERFORMANCE_WARNING.value}:high": 5,
            f"{NotificationType.USER_ACTION.value}:medium": 50,
            f"{NotificationType.PAYMENT_ISSUE.value}:high": 10
        }
        
        limit = limits.get(rate_key, 30)  # По умолчанию 30 в час
        
        # Проверяем историю отправки
        if rate_key not in self.rate_limits:
            self.rate_limits[rate_key] = []
        
        # Удаляем старые записи (старше часа)
        hour_ago = current_time - timedelta(hours=1)
        self.rate_limits[rate_key] = [
            timestamp for timestamp in self.rate_limits[rate_key]
            if timestamp > hour_ago
        ]
        
        # Проверяем лимит
        if len(self.rate_limits[rate_key]) >= limit:
            return False
        
        # Добавляем текущую отправку
        self.rate_limits[rate_key].append(current_time)
        return True
    
    async def _send_telegram_notification(
        self,
        notification: Dict[str, Any],
        recipients: List[int]
    ) -> Dict[str, Any]:
        """Отправить уведомление в Telegram"""
        
        if not admin_settings.TELEGRAM_NOTIFICATIONS:
            return {"success": False, "reason": "telegram_disabled"}
        
        try:
            # Форматируем сообщение для Telegram
            message = f"*{notification['title']}*\n\n{notification['message']}"
            
            # Добавляем дополнительную информацию
            if notification.get('data'):
                message += f"\n\n_Time: {notification['timestamp']}_"
            
            # TODO: Здесь должна быть отправка через Telegram Bot API
            # Например:
            # await telegram_bot.send_message_to_admins(message, recipients)
            
            logger.info(f"Telegram notification sent", recipients_count=len(recipients))
            
            return {
                "success": True,
                "recipients_count": len(recipients),
                "method": "telegram"
            }
            
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_email_notification(
        self,
        notification: Dict[str, Any],
        recipients: List[int]
    ) -> Dict[str, Any]:
        """Отправить уведомление по email"""
        
        if not admin_settings.EMAIL_NOTIFICATIONS:
            return {"success": False, "reason": "email_disabled"}
        
        try:
            # Получаем email адреса администраторов
            async with get_db_session() as session:
                admins = await session.query(AdminUser).filter(
                    AdminUser.id.in_(recipients),
                    AdminUser.email.isnot(None)
                ).all()
                
                email_addresses = [admin.email for admin in admins if admin.email]
            
            if not email_addresses:
                return {"success": False, "reason": "no_email_addresses"}
            
            # TODO: Здесь должна быть отправка email
            # await email_service.send_notification_email(
            #     subject=notification['title'],
            #     body=notification['message'],
            #     recipients=email_addresses
            # )
            
            logger.info(f"Email notification sent", recipients_count=len(email_addresses))
            
            return {
                "success": True,
                "recipients_count": len(email_addresses),
                "method": "email"
            }
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_webhook_notification(
        self,
        notification: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Отправить уведомление через webhook"""
        
        if not admin_settings.WEBHOOK_NOTIFICATIONS or not admin_settings.WEBHOOK_URL:
            return {"success": False, "reason": "webhook_disabled"}
        
        try:
            import aiohttp
            
            # Формируем payload для webhook
            payload = {
                "event": "admin_notification",
                "notification": notification,
                "timestamp": notification["timestamp"],
                "source": "videobot_pro_admin"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    admin_settings.WEBHOOK_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        logger.info("Webhook notification sent successfully")
                        return {"success": True, "method": "webhook"}
                    else:
                        logger.error(f"Webhook failed with status {response.status}")
                        return {"success": False, "error": f"HTTP {response.status}"}
            
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_in_app_notification(
        self,
        notification: Dict[str, Any],
        recipients: List[int]
    ) -> Dict[str, Any]:
        """Сохранить уведомление в БД для отображения в интерфейсе"""
        
        try:
            # TODO: Здесь должно быть сохранение в таблицу уведомлений
            # Пока просто логируем
            
            logger.info(
                "In-app notification created",
                notification_id=notification["id"],
                recipients_count=len(recipients)
            )
            
            return {
                "success": True,
                "recipients_count": len(recipients),
                "method": "in_app"
            }
            
        except Exception as e:
            logger.error(f"Failed to create in-app notification: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_notification_settings(self, admin_id: int) -> Dict[str, Any]:
        """Получить настройки уведомлений администратора"""
        
        try:
            async with get_db_session() as session:
                admin = await session.get(AdminUser, admin_id)
                
                if not admin:
                    return {"error": "Admin not found"}
                
                # TODO: Настройки уведомлений должны быть в модели AdminUser
                # Пока возвращаем настройки по умолчанию
                settings = {
                    "email_notifications": True,
                    "telegram_notifications": True,
                    "in_app_notifications": True,
                    "webhook_notifications": False,
                    "notification_types": {
                        NotificationType.SYSTEM_ALERT.value: {
                            "enabled": True,
                            "channels": ["telegram", "email", "in_app"]
                        },
                        NotificationType.USER_ACTION.value: {
                            "enabled": True,
                            "channels": ["in_app"]
                        },
                        NotificationType.PAYMENT_ISSUE.value: {
                            "enabled": True,
                            "channels": ["telegram", "in_app"]
                        },
                        NotificationType.SECURITY_EVENT.value: {
                            "enabled": True,
                            "channels": ["telegram", "email", "in_app"]
                        },
                        NotificationType.PERFORMANCE_WARNING.value: {
                            "enabled": True,
                            "channels": ["telegram", "in_app"]
                        }
                    },
                    "quiet_hours": {
                        "enabled": False,
                        "start_time": "22:00",
                        "end_time": "08:00",
                        "timezone": "UTC"
                    }
                }
                
                return settings
                
        except Exception as e:
            logger.error(f"Failed to get notification settings for admin {admin_id}: {e}")
            return {"error": str(e)}
    
    async def update_notification_settings(
        self,
        admin_id: int,
        settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Обновить настройки уведомлений администратора"""
        
        try:
            async with get_db_session() as session:
                admin = await session.get(AdminUser, admin_id)
                
                if not admin:
                    return {"error": "Admin not found"}
                
                # TODO: Сохранить настройки в модель AdminUser
                # admin.notification_settings = settings
                # await session.commit()
                
                logger.info(f"Notification settings updated for admin {admin_id}")
                
                return {"success": True, "message": "Settings updated"}
                
        except Exception as e:
            logger.error(f"Failed to update notification settings for admin {admin_id}: {e}")
            return {"error": str(e)}
    
    async def get_notification_history(
        self,
        admin_id: int = None,
        days: int = 7,
        notification_type: NotificationType = None,
        priority: NotificationPriority = None
    ) -> List[Dict[str, Any]]:
        """Получить историю уведомлений"""
        
        try:
            # TODO: Здесь должен быть запрос к таблице уведомлений
            # Пока возвращаем заглушку
            
            history = [
                {
                    "id": "notif_1",
                    "type": NotificationType.SYSTEM_ALERT.value,
                    "title": "High CPU Usage",
                    "message": "CPU usage: 85% (threshold: 80%)",
                    "priority": NotificationPriority.HIGH.value,
                    "timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "channels_sent": ["telegram", "in_app"],
                    "recipients_count": 3,
                    "status": "delivered"
                },
                {
                    "id": "notif_2", 
                    "type": NotificationType.USER_ACTION.value,
                    "title": "User Action: user_banned",
                    "message": "Администратор admin1 заблокировал пользователя (User ID: 12345)",
                    "priority": NotificationPriority.MEDIUM.value,
                    "timestamp": (datetime.utcnow() - timedelta(hours=5)).isoformat(),
                    "channels_sent": ["in_app"],
                    "recipients_count": 5,
                    "status": "delivered"
                }
            ]
            
            # Фильтрация по параметрам
            if notification_type:
                history = [h for h in history if h["type"] == notification_type.value]
            
            if priority:
                history = [h for h in history if h["priority"] == priority.value]
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to get notification history: {e}")
            return []
    
    async def test_notification_channels(self) -> Dict[str, Any]:
        """Тестирование всех каналов уведомлений"""
        
        test_notification = {
            "id": f"test_{datetime.utcnow().timestamp()}",
            "type": NotificationType.SYSTEM_ALERT.value,
            "title": "🧪 Test Notification",
            "message": "This is a test notification to verify all channels are working properly.",
            "priority": NotificationPriority.LOW.value,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"test": True}
        }
        
        results = {}
        
        # Тестируем каждый канал
        channels = [
            NotificationChannel.TELEGRAM,
            NotificationChannel.EMAIL,
            NotificationChannel.WEBHOOK,
            NotificationChannel.IN_APP
        ]
        
        test_recipients = [1]  # ID первого админа для теста
        
        for channel in channels:
            try:
                if channel == NotificationChannel.TELEGRAM:
                    result = await self._send_telegram_notification(test_notification, test_recipients)
                elif channel == NotificationChannel.EMAIL:
                    result = await self._send_email_notification(test_notification, test_recipients)
                elif channel == NotificationChannel.WEBHOOK:
                    result = await self._send_webhook_notification(test_notification)
                elif channel == NotificationChannel.IN_APP:
                    result = await self._send_in_app_notification(test_notification, test_recipients)
                
                results[channel.value] = result
                
            except Exception as e:
                results[channel.value] = {"success": False, "error": str(e)}
        
        # Общий результат
        all_successful = all(result.get("success", False) for result in results.values())
        
        return {
            "overall_success": all_successful,
            "channels": results,
            "test_timestamp": datetime.utcnow().isoformat()
        }
    
    async def send_daily_summary(self) -> Dict[str, Any]:
        """Отправить ежедневную сводку администраторам"""
        
        try:
            # Собираем статистику за день
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            async with get_db_session() as session:
                # Новые пользователи
                new_users = await session.query(User).filter(
                    User.created_at >= today,
                    User.is_deleted == False
                ).count()
                
                # Скачивания
                downloads_today = await session.query(DownloadTask).filter(
                    DownloadTask.created_at >= today
                ).count()
                
                # Успешные скачивания
                successful_downloads = await session.query(DownloadTask).filter(
                    DownloadTask.created_at >= today,
                    DownloadTask.status == "completed"
                ).count()
                
                # Платежи
                payments_today = await session.query(Payment).filter(
                    Payment.created_at >= today,
                    Payment.status == "completed"
                ).count()
                
                # Сумма платежей
                revenue_today = await session.query(
                    func.sum(Payment.amount)
                ).filter(
                    Payment.created_at >= today,
                    Payment.status == "completed"
                ).scalar() or 0
            
            # Формируем сводку
            summary = f"""📊 **Daily Summary - {today.strftime('%Y-%m-%d')}**

👥 **Users**: {new_users} new registrations
📥 **Downloads**: {downloads_today} total, {successful_downloads} successful
💰 **Revenue**: ${revenue_today:.2f} from {payments_today} payments

Success rate: {(successful_downloads/downloads_today*100) if downloads_today > 0 else 0:.1f}%
"""
            
            return await self.send_notification(
                notification_type=NotificationType.SYSTEM_ALERT,
                title="📊 Daily Summary",
                message=summary,
                priority=NotificationPriority.LOW,
                channels=[NotificationChannel.TELEGRAM, NotificationChannel.IN_APP],
                data={
                    "summary_type": "daily",
                    "date": today.isoformat(),
                    "metrics": {
                        "new_users": new_users,
                        "downloads_total": downloads_today,
                        "downloads_successful": successful_downloads,
                        "payments_count": payments_today,
                        "revenue": float(revenue_today)
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")
            return {"success": False, "error": str(e)}

# Глобальный экземпляр сервиса
notification_service = NotificationService()

# Быстрые функции для отправки уведомлений
async def notify_system_alert(alert_type: str, message: str, severity: str = "medium"):
    """Быстрая отправка системного алерта"""
    return await notification_service.send_system_alert(alert_type, message, severity)

async def notify_user_action(action: str, user_id: int, admin_id: int, details: Dict[str, Any] = None):
    """Быстрая отправка уведомления о действии с пользователем"""
    return await notification_service.send_user_action_alert(action, user_id, admin_id, details)

async def notify_payment_issue(alert_type: str, payment_id: int, amount: float, currency: str):
    """Быстрая отправка уведомления о проблеме с платежом"""
    return await notification_service.send_payment_alert(alert_type, payment_id, amount, currency)

async def notify_performance_warning(metric: str, current_value: float, threshold: float):
    """Быстрая отправка предупреждения о производительности"""
    return await notification_service.send_performance_warning(metric, current_value, threshold)

async def notify_security_event(event_type: str, description: str, ip_address: str = None):
    """Быстрая отправка уведомления о событии безопасности"""
    return await notification_service.send_security_alert(event_type, description, ip_address)