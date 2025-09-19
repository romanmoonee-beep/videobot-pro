"""
VideoBot Pro - Analytics Service
Сервис для сбора и анализа аналитики бота
"""

import structlog
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from collections import defaultdict

from shared.config.database import get_async_session
from shared.models import User, DownloadTask, DownloadBatch, Payment, EventType
from shared.models.analytics import (
UserEvent, SystemEvent, PaymentEvent, DownloadEvent,
    track_user_event, track_system_event, track_payment_event, track_download_event
)
from bot.config import bot_config

logger = structlog.get_logger(__name__)

class MetricType(Enum):
    """Типы метрик"""
    USER_REGISTRATION = "user_registration"
    USER_ACTIVITY = "user_activity" 
    DOWNLOAD_SUCCESS = "download_success"
    DOWNLOAD_FAILURE = "download_failure"
    PREMIUM_CONVERSION = "premium_conversion"
    TRIAL_CONVERSION = "trial_conversion"
    REVENUE = "revenue"
    PLATFORM_USAGE = "platform_usage"
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"

class TimeRange(Enum):
    """Временные диапазоны"""
    HOUR = "1h"
    DAY = "1d"
    WEEK = "7d"
    MONTH = "30d"
    QUARTER = "90d"
    YEAR = "365d"

class AnalyticsService:
    """Сервис аналитики"""
    
    def __init__(self):
        """Инициализация сервиса"""
        self.metric_cache = {}
        self.cache_ttl = 300  # 5 минут
    
    async def get_user_analytics(
        self,
        user_id: Optional[int] = None,
        time_range: TimeRange = TimeRange.MONTH
    ) -> Dict[str, Any]:
        """
        Получить аналитику пользователей
        
        Args:
            user_id: ID конкретного пользователя (None для всех)
            time_range: Временной диапазон
            
        Returns:
            Словарь с аналитикой
        """
        try:
            start_date = self._get_start_date(time_range)
            
            async with get_async_session() as session:
                # Базовые метрики пользователей
                if user_id:
                    user_filter = "AND u.telegram_id = :user_id"
                    params = {'start_date': start_date, 'user_id': user_id}
                else:
                    user_filter = ""
                    params = {'start_date': start_date}
                
                # Общие метрики
                user_metrics = await session.execute(f"""
                    SELECT 
                        COUNT(DISTINCT u.id) as total_users,
                        COUNT(DISTINCT CASE WHEN u.created_at >= :start_date THEN u.id END) as new_users,
                        COUNT(DISTINCT CASE WHEN u.last_active_at >= :start_date THEN u.id END) as active_users,
                        COUNT(DISTINCT CASE WHEN u.is_premium = true THEN u.id END) as premium_users,
                        COUNT(DISTINCT CASE WHEN u.user_type = 'trial' THEN u.id END) as trial_users,
                        AVG(CASE WHEN u.downloads_total > 0 THEN u.downloads_total END) as avg_downloads
                    FROM users u 
                    WHERE u.is_deleted = false {user_filter}
                """, params)
                
                user_stats = user_metrics.fetchone()
                
                # Метрики по типам пользователей
                user_type_stats = await session.execute(f"""
                    SELECT 
                        u.user_type,
                        COUNT(*) as count,
                        AVG(u.downloads_total) as avg_downloads,
                        SUM(u.downloads_today) as downloads_today
                    FROM users u 
                    WHERE u.is_deleted = false 
                    AND u.created_at >= :start_date {user_filter}
                    GROUP BY u.user_type
                    ORDER BY count DESC
                """, params)
                
                type_distribution = {
                    row.user_type: {
                        'count': row.count,
                        'avg_downloads': float(row.avg_downloads or 0),
                        'downloads_today': row.downloads_today or 0
                    }
                    for row in user_type_stats.fetchall()
                }
                
                # Динамика регистраций
                registration_dynamics = await self._get_registration_dynamics(
                    session, start_date, user_id
                )
                
                # Активность пользователей
                activity_metrics = await self._get_user_activity_metrics(
                    session, start_date, user_id
                )
                
                # Retention metrics
                retention_metrics = await self._get_retention_metrics(
                    session, start_date, user_id
                )
                
                return {
                    'period': time_range.value,
                    'start_date': start_date.isoformat(),
                    'end_date': datetime.utcnow().isoformat(),
                    'summary': {
                        'total_users': user_stats.total_users or 0,
                        'new_users': user_stats.new_users or 0,
                        'active_users': user_stats.active_users or 0,
                        'premium_users': user_stats.premium_users or 0,
                        'trial_users': user_stats.trial_users or 0,
                        'avg_downloads_per_user': float(user_stats.avg_downloads or 0)
                    },
                    'user_type_distribution': type_distribution,
                    'registration_dynamics': registration_dynamics,
                    'activity_metrics': activity_metrics,
                    'retention_metrics': retention_metrics
                }
                
        except Exception as e:
            logger.error(f"Error getting user analytics: {e}")
            return {'error': str(e)}
    
    async def get_download_analytics(
        self,
        time_range: TimeRange = TimeRange.MONTH
    ) -> Dict[str, Any]:
        """
        Получить аналитику загрузок
        
        Args:
            time_range: Временной диапазон
            
        Returns:
            Аналитика загрузок
        """
        try:
            start_date = self._get_start_date(time_range)
            
            async with get_async_session() as session:
                # Основные метрики загрузок
                download_stats = await session.execute("""
                    SELECT 
                        COUNT(*) as total_downloads,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_downloads,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_downloads,
                        COUNT(CASE WHEN status = 'processing' THEN 1 END) as processing_downloads,
                        AVG(CASE WHEN file_size_bytes > 0 THEN file_size_bytes END) as avg_file_size,
                        SUM(CASE WHEN file_size_bytes > 0 THEN file_size_bytes END) as total_file_size,
                        AVG(CASE WHEN duration_seconds > 0 THEN duration_seconds END) as avg_duration,
                        AVG(CASE WHEN processing_time_seconds > 0 THEN processing_time_seconds END) as avg_processing_time
                    FROM download_tasks 
                    WHERE created_at >= :start_date
                """, {'start_date': start_date})
                
                stats = download_stats.fetchone()
                
                # Статистика по платформам
                platform_stats = await session.execute("""
                    SELECT 
                        platform,
                        COUNT(*) as total_downloads,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                        AVG(CASE WHEN file_size_bytes > 0 THEN file_size_bytes END) as avg_size
                    FROM download_tasks 
                    WHERE created_at >= :start_date AND platform IS NOT NULL
                    GROUP BY platform
                    ORDER BY total_downloads DESC
                """, {'start_date': start_date})
                
                platform_distribution = {
                    row.platform: {
                        'total': row.total_downloads,
                        'successful': row.successful,
                        'failed': row.failed,
                        'success_rate': (row.successful / row.total_downloads * 100) if row.total_downloads > 0 else 0,
                        'avg_file_size_mb': float(row.avg_size or 0) / (1024 * 1024)
                    }
                    for row in platform_stats.fetchall()
                }
                
                # Динамика загрузок по времени
                download_dynamics = await self._get_download_dynamics(session, start_date)
                
                # Топ ошибок
                error_analysis = await self._get_error_analysis(session, start_date)
                
                # Качество и размеры файлов
                quality_stats = await self._get_quality_statistics(session, start_date)
                
                # Batch аналитика
                batch_stats = await self._get_batch_analytics(session, start_date)
                
                success_rate = (stats.successful_downloads / stats.total_downloads * 100) if stats.total_downloads > 0 else 0
                
                return {
                    'period': time_range.value,
                    'start_date': start_date.isoformat(),
                    'summary': {
                        'total_downloads': stats.total_downloads or 0,
                        'successful_downloads': stats.successful_downloads or 0,
                        'failed_downloads': stats.failed_downloads or 0,
                        'processing_downloads': stats.processing_downloads or 0,
                        'success_rate': round(success_rate, 2),
                        'avg_file_size_mb': round(float(stats.avg_file_size or 0) / (1024 * 1024), 2),
                        'total_file_size_gb': round(float(stats.total_file_size or 0) / (1024 * 1024 * 1024), 2),
                        'avg_duration_seconds': round(float(stats.avg_duration or 0), 1),
                        'avg_processing_time_seconds': round(float(stats.avg_processing_time or 0), 1)
                    },
                    'platform_distribution': platform_distribution,
                    'download_dynamics': download_dynamics,
                    'error_analysis': error_analysis,
                    'quality_statistics': quality_stats,
                    'batch_analytics': batch_stats
                }
                
        except Exception as e:
            logger.error(f"Error getting download analytics: {e}")
            return {'error': str(e)}
    
    async def get_financial_analytics(
        self,
        time_range: TimeRange = TimeRange.MONTH
    ) -> Dict[str, Any]:
        """
        Получить финансовую аналитику
        
        Args:
            time_range: Временной диапазон
            
        Returns:
            Финансовая аналитика
        """
        try:
            start_date = self._get_start_date(time_range)
            
            async with get_async_session() as session:
                # Основные финансовые метрики
                financial_stats = await session.execute("""
                    SELECT 
                        COUNT(*) as total_payments,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_payments,
                        SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END) as total_revenue,
                        AVG(CASE WHEN status = 'completed' THEN amount END) as avg_payment_amount,
                        COUNT(DISTINCT user_id) as paying_users
                    FROM payments 
                    WHERE created_at >= :start_date
                """, {'start_date': start_date})
                
                stats = financial_stats.fetchone()
                
                # Revenue по планам подписки
                subscription_revenue = await session.execute("""
                    SELECT 
                        subscription_plan,
                        COUNT(*) as payments_count,
                        SUM(amount) as revenue,
                        AVG(amount) as avg_amount
                    FROM payments 
                    WHERE created_at >= :start_date AND status = 'completed'
                    GROUP BY subscription_plan
                    ORDER BY revenue DESC
                """, {'start_date': start_date})
                
                plan_distribution = {
                    row.subscription_plan: {
                        'payments': row.payments_count,
                        'revenue': float(row.revenue),
                        'avg_amount': float(row.avg_amount)
                    }
                    for row in subscription_revenue.fetchall()
                }
                
                # Revenue динамика
                revenue_dynamics = await self._get_revenue_dynamics(session, start_date)
                
                # Конверсия из trial в premium
                conversion_metrics = await self._get_conversion_metrics(session, start_date)
                
                # LTV и churn анализ
                ltv_metrics = await self._get_ltv_metrics(session, start_date)
                
                return {
                    'period': time_range.value,
                    'start_date': start_date.isoformat(),
                    'summary': {
                        'total_payments': stats.total_payments or 0,
                        'successful_payments': stats.successful_payments or 0,
                        'total_revenue': float(stats.total_revenue or 0),
                        'avg_payment_amount': float(stats.avg_payment_amount or 0),
                        'paying_users': stats.paying_users or 0,
                        'conversion_rate': round(
                            (stats.paying_users / stats.total_payments * 100) if stats.total_payments > 0 else 0, 2
                        )
                    },
                    'subscription_plans': plan_distribution,
                    'revenue_dynamics': revenue_dynamics,
                    'conversion_metrics': conversion_metrics,
                    'ltv_metrics': ltv_metrics
                }
                
        except Exception as e:
            logger.error(f"Error getting financial analytics: {e}")
            return {'error': str(e)}
    
    async def get_system_analytics(
        self,
        time_range: TimeRange = TimeRange.DAY
    ) -> Dict[str, Any]:
        """
        Получить системную аналитику
        
        Args:
            time_range: Временной диапазон
            
        Returns:
            Системная аналитика
        """
        try:
            start_date = self._get_start_date(time_range)
            
            async with get_async_session() as session:
                # Системные события
                system_events = await session.execute("""
                    SELECT 
                        event_type,
                        COUNT(*) as count
                    FROM system_events 
                    WHERE created_at >= :start_date
                    GROUP BY event_type
                    ORDER BY count DESC
                """, {'start_date': start_date})
                
                events_distribution = {
                    row.event_type: row.count
                    for row in system_events.fetchall()
                }
                
                # Ошибки системы
                error_stats = await session.execute("""
                    SELECT 
                        COUNT(*) as total_errors,
                        COUNT(DISTINCT DATE(created_at)) as error_days
                    FROM system_events 
                    WHERE created_at >= :start_date 
                    AND event_type = 'error_occurred'
                """, {'start_date': start_date})
                
                error_data = error_stats.fetchone()
                
                # Performance метрики
                performance_stats = await self._get_performance_metrics(session, start_date)
                
                # Load балансировка
                load_metrics = await self._get_load_metrics(session, start_date)
                
                return {
                    'period': time_range.value,
                    'start_date': start_date.isoformat(),
                    'system_events': events_distribution,
                    'error_summary': {
                        'total_errors': error_data.total_errors or 0,
                        'error_days': error_data.error_days or 0,
                        'avg_errors_per_day': round(
                            (error_data.total_errors or 0) / max(error_data.error_days or 1, 1), 2
                        )
                    },
                    'performance_metrics': performance_stats,
                    'load_metrics': load_metrics
                }
                
        except Exception as e:
            logger.error(f"Error getting system analytics: {e}")
            return {'error': str(e)}
    
    async def track_custom_event(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        event_data: Optional[Dict] = None,
        value: Optional[float] = None
    ):
        """
        Отследить кастомное событие
        
        Args:
            event_type: Тип события
            user_id: ID пользователя
            event_data: Дополнительные данные
            value: Числовое значение
        """
        try:
            if user_id:
                await track_user_event(
                    event_type=EventType(event_type),
                    user_id=user_id,
                    telegram_user_id=None,
                    event_data=event_data,
                    value=value
                )
            else:
                await track_system_event(
                    event_type=EventType(event_type),
                    event_data=event_data,
                    value=value
                )
                
            logger.info(f"Custom event tracked: {event_type}")
            
        except Exception as e:
            logger.error(f"Error tracking custom event: {e}")
    
    async def generate_report(
        self,
        report_type: str,
        time_range: TimeRange = TimeRange.MONTH,
        format_type: str = "json"
    ) -> Dict[str, Any]:
        """
        Генерировать отчет
        
        Args:
            report_type: Тип отчета (users/downloads/financial/system)
            time_range: Временной диапазон
            format_type: Формат отчета (json/csv)
            
        Returns:
            Сгенерированный отчет
        """
        try:
            if report_type == "users":
                data = await self.get_user_analytics(time_range=time_range)
            elif report_type == "downloads":
                data = await self.get_download_analytics(time_range=time_range)
            elif report_type == "financial":
                data = await self.get_financial_analytics(time_range=time_range)
            elif report_type == "system":
                data = await self.get_system_analytics(time_range=time_range)
            else:
                # Комплексный отчет
                data = {
                    'users': await self.get_user_analytics(time_range=time_range),
                    'downloads': await self.get_download_analytics(time_range=time_range),
                    'financial': await self.get_financial_analytics(time_range=time_range),
                    'system': await self.get_system_analytics(time_range=time_range)
                }
            
            report = {
                'report_type': report_type,
                'generated_at': datetime.utcnow().isoformat(),
                'time_range': time_range.value,
                'data': data
            }
            
            if format_type == "csv":
                # Конвертация в CSV формат
                report['csv_data'] = self._convert_to_csv(data)
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return {'error': str(e)}
    
    # Вспомогательные методы
    
    def _get_start_date(self, time_range: TimeRange) -> datetime:
        """Получить дату начала периода"""
        now = datetime.utcnow()
        
        time_deltas = {
            TimeRange.HOUR: timedelta(hours=1),
            TimeRange.DAY: timedelta(days=1),
            TimeRange.WEEK: timedelta(days=7),
            TimeRange.MONTH: timedelta(days=30),
            TimeRange.QUARTER: timedelta(days=90),
            TimeRange.YEAR: timedelta(days=365)
        }
        
        return now - time_deltas.get(time_range, timedelta(days=30))
    
    async def _get_registration_dynamics(
        self, session, start_date: datetime, user_id: Optional[int]
    ) -> List[Dict]:
        """Получить динамику регистраций"""
        try:
            user_filter = "AND telegram_id = :user_id" if user_id else ""
            params = {'start_date': start_date}
            if user_id:
                params['user_id'] = user_id
                
            result = await session.execute(f"""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as registrations
                FROM users 
                WHERE created_at >= :start_date {user_filter}
                GROUP BY DATE(created_at)
                ORDER BY date
            """, params)
            
            return [
                {
                    'date': row.date.isoformat(),
                    'registrations': row.registrations
                }
                for row in result.fetchall()
            ]
            
        except Exception as e:
            logger.error(f"Error getting registration dynamics: {e}")
            return []
    
    async def _get_user_activity_metrics(
        self, session, start_date: datetime, user_id: Optional[int]
    ) -> Dict[str, Any]:
        """Получить метрики активности пользователей"""
        try:
            user_filter = "AND telegram_id = :user_id" if user_id else ""
            params = {'start_date': start_date}
            if user_id:
                params['user_id'] = user_id
                
            # Daily Active Users
            dau_result = await session.execute(f"""
                SELECT 
                    DATE(last_active_at) as date,
                    COUNT(DISTINCT id) as dau
                FROM users 
                WHERE last_active_at >= :start_date {user_filter}
                GROUP BY DATE(last_active_at)
                ORDER BY date
            """, params)
            
            dau_data = [
                {'date': row.date.isoformat(), 'dau': row.dau}
                for row in dau_result.fetchall()
            ]
            
            return {
                'daily_active_users': dau_data,
                'avg_dau': sum(item['dau'] for item in dau_data) / len(dau_data) if dau_data else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting user activity metrics: {e}")
            return {}
    
    async def _get_retention_metrics(
        self, session, start_date: datetime, user_id: Optional[int]
    ) -> Dict[str, Any]:
        """Получить метрики удержания пользователей"""
        try:
            # Этот метод довольно сложен для простой реализации
            # Возвращаем базовые метрики
            return {
                'day_1_retention': 0.0,
                'day_7_retention': 0.0,
                'day_30_retention': 0.0
            }
        except Exception as e:
            logger.error(f"Error getting retention metrics: {e}")
            return {}
    
    async def _get_download_dynamics(self, session, start_date: datetime) -> List[Dict]:
        """Получить динамику загрузок"""
        try:
            result = await session.execute("""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as total_downloads,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_downloads,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_downloads
                FROM download_tasks 
                WHERE created_at >= :start_date
                GROUP BY DATE(created_at)
                ORDER BY date
            """, {'start_date': start_date})
            
            return [
                {
                    'date': row.date.isoformat(),
                    'total': row.total_downloads,
                    'successful': row.successful_downloads,
                    'failed': row.failed_downloads,
                    'success_rate': (row.successful_downloads / row.total_downloads * 100) if row.total_downloads > 0 else 0
                }
                for row in result.fetchall()
            ]
            
        except Exception as e:
            logger.error(f"Error getting download dynamics: {e}")
            return []
    
    async def _get_error_analysis(self, session, start_date: datetime) -> Dict[str, Any]:
        """Анализ ошибок"""
        try:
            result = await session.execute("""
                SELECT 
                    error_message,
                    COUNT(*) as count
                FROM download_tasks 
                WHERE created_at >= :start_date AND status = 'failed'
                AND error_message IS NOT NULL
                GROUP BY error_message
                ORDER BY count DESC
                LIMIT 10
            """, {'start_date': start_date})
            
            top_errors = [
                {'error': row.error_message[:100], 'count': row.count}
                for row in result.fetchall()
            ]
            
            return {
                'top_errors': top_errors,
                'total_error_types': len(top_errors)
            }
            
        except Exception as e:
            logger.error(f"Error getting error analysis: {e}")
            return {}
    
    async def _get_quality_statistics(self, session, start_date: datetime) -> Dict[str, Any]:
        """Статистика качества"""
        try:
            result = await session.execute("""
                SELECT 
                    quality,
                    COUNT(*) as count,
                    AVG(file_size_bytes) as avg_size
                FROM download_tasks 
                WHERE created_at >= :start_date 
                AND status = 'completed' 
                AND quality IS NOT NULL
                GROUP BY quality
                ORDER BY count DESC
            """, {'start_date': start_date})
            
            quality_dist = {
                row.quality: {
                    'count': row.count,
                    'avg_size_mb': round(float(row.avg_size or 0) / (1024 * 1024), 2)
                }
                for row in result.fetchall()
            }
            
            return quality_dist
            
        except Exception as e:
            logger.error(f"Error getting quality statistics: {e}")
            return {}
    
    async def _get_batch_analytics(self, session, start_date: datetime) -> Dict[str, Any]:
        """Аналитика batch загрузок"""
        try:
            result = await session.execute("""
                SELECT 
                    COUNT(*) as total_batches,
                    AVG(total_urls) as avg_batch_size,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_batches
                FROM download_batches 
                WHERE created_at >= :start_date
            """, {'start_date': start_date})
            
            stats = result.fetchone()
            
            return {
                'total_batches': stats.total_batches or 0,
                'avg_batch_size': round(float(stats.avg_batch_size or 0), 1),
                'completed_batches': stats.completed_batches or 0,
                'completion_rate': round(
                    (stats.completed_batches / stats.total_batches * 100) if stats.total_batches > 0 else 0, 2
                )
            }
            
        except Exception as e:
            logger.error(f"Error getting batch analytics: {e}")
            return {}
    
    async def _get_revenue_dynamics(self, session, start_date: datetime) -> List[Dict]:
        """Динамика доходов"""
        try:
            result = await session.execute("""
                SELECT 
                    DATE(completed_at) as date,
                    SUM(amount) as revenue,
                    COUNT(*) as payments
                FROM payments 
                WHERE completed_at >= :start_date AND status = 'completed'
                GROUP BY DATE(completed_at)
                ORDER BY date
            """, {'start_date': start_date})
            
            return [
                {
                    'date': row.date.isoformat(),
                    'revenue': float(row.revenue),
                    'payments': row.payments
                }
                for row in result.fetchall()
            ]
            
        except Exception as e:
            logger.error(f"Error getting revenue dynamics: {e}")
            return []
    
    async def _get_conversion_metrics(self, session, start_date: datetime) -> Dict[str, Any]:
        """Метрики конверсии"""
        try:
            # Простая реализация - можно расширить
            trial_to_premium = await session.execute("""
                SELECT 
                    COUNT(DISTINCT u.id) as trial_users,
                    COUNT(DISTINCT CASE WHEN p.status = 'completed' THEN u.id END) as converted_users
                FROM users u
                LEFT JOIN payments p ON u.id = p.user_id
                WHERE u.trial_used = true AND u.created_at >= :start_date
            """, {'start_date': start_date})
            
            stats = trial_to_premium.fetchone()
            trial_users = stats.trial_users or 0
            converted_users = stats.converted_users or 0
            
            return {
                'trial_to_premium_rate': round(
                    (converted_users / trial_users * 100) if trial_users > 0 else 0, 2
                ),
                'total_trial_users': trial_users,
                'converted_users': converted_users
            }
            
        except Exception as e:
            logger.error(f"Error getting conversion metrics: {e}")
            return {}
    
    async def _get_ltv_metrics(self, session, start_date: datetime) -> Dict[str, Any]:
        """Метрики LTV (Lifetime Value)"""
        try:
result = await session.execute("""
                SELECT 
                    AVG(total_spent) as avg_ltv,
                    MAX(total_spent) as max_ltv,
                    COUNT(DISTINCT user_id) as paying_users
                FROM (
                    SELECT 
                        user_id,
                        SUM(amount) as total_spent
                    FROM payments 
                    WHERE status = 'completed' AND created_at >= :start_date
                    GROUP BY user_id
                ) user_totals
            """, {'start_date': start_date})
            
            stats = result.fetchone()
            
            return {
                'avg_ltv': round(float(stats.avg_ltv or 0), 2),
                'max_ltv': round(float(stats.max_ltv or 0), 2),
                'paying_users_count': stats.paying_users or 0
            }
            
        except Exception as e:
            logger.error(f"Error getting LTV metrics: {e}")
            return {}
    
    async def _get_performance_metrics(self, session, start_date: datetime) -> Dict[str, Any]:
        """Получить метрики производительности"""
        try:
            # Получаем данные из системных событий
            result = await session.execute("""
                SELECT 
                    AVG(CAST(event_data->>'response_time' AS FLOAT)) as avg_response_time,
                    MAX(CAST(event_data->>'response_time' AS FLOAT)) as max_response_time,
                    COUNT(*) as total_requests
                FROM system_events 
                WHERE created_at >= :start_date 
                AND event_data->>'response_time' IS NOT NULL
            """, {'start_date': start_date})
            
            stats = result.fetchone()
            
            # Медленные запросы
            slow_requests = await session.execute("""
                SELECT COUNT(*) as slow_count
                FROM system_events 
                WHERE created_at >= :start_date 
                AND event_type = 'slow_request'
            """, {'start_date': start_date})
            
            slow_stats = slow_requests.fetchone()
            
            return {
                'avg_response_time_ms': round(float(stats.avg_response_time or 0), 2),
                'max_response_time_ms': round(float(stats.max_response_time or 0), 2),
                'total_requests': stats.total_requests or 0,
                'slow_requests': slow_stats.slow_count or 0,
                'slow_requests_rate': round(
                    (slow_stats.slow_count / stats.total_requests * 100) if stats.total_requests > 0 else 0, 2
                )
            }
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}
    
    async def _get_load_metrics(self, session, start_date: datetime) -> Dict[str, Any]:
        """Получить метрики нагрузки"""
        try:
            # Загрузка по часам
            hourly_load = await session.execute("""
                SELECT 
                    EXTRACT(HOUR FROM created_at) as hour,
                    COUNT(*) as requests_count
                FROM user_events 
                WHERE created_at >= :start_date
                GROUP BY EXTRACT(HOUR FROM created_at)
                ORDER BY hour
            """, {'start_date': start_date})
            
            load_by_hour = [
                {'hour': int(row.hour), 'requests': row.requests_count}
                for row in hourly_load.fetchall()
            ]
            
            # Пиковая нагрузка
            peak_hour = max(load_by_hour, key=lambda x: x['requests']) if load_by_hour else {'hour': 0, 'requests': 0}
            
            return {
                'hourly_distribution': load_by_hour,
                'peak_hour': peak_hour['hour'],
                'peak_requests': peak_hour['requests'],
                'avg_hourly_requests': round(
                    sum(item['requests'] for item in load_by_hour) / len(load_by_hour) if load_by_hour else 0, 2
                )
            }
            
        except Exception as e:
            logger.error(f"Error getting load metrics: {e}")
            return {}
    
    def _convert_to_csv(self, data: Dict[str, Any]) -> str:
        """Конвертировать данные в CSV формат"""
        try:
            import io
            import csv
            
            output = io.StringIO()
            
            # Простая реализация - можно расширить
            if 'summary' in data:
                writer = csv.writer(output)
                writer.writerow(['Metric', 'Value'])
                
                for key, value in data['summary'].items():
                    writer.writerow([key.replace('_', ' ').title(), value])
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error converting to CSV: {e}")
            return "Error converting data to CSV"
    
    async def get_realtime_metrics(self) -> Dict[str, Any]:
        """Получить метрики в реальном времени"""
        try:
            async with get_async_session() as session:
                # Текущая активность (последний час)
                current_activity = await session.execute("""
                    SELECT 
                        COUNT(DISTINCT user_id) as active_users,
                        COUNT(*) as total_events
                    FROM user_events 
                    WHERE created_at >= NOW() - INTERVAL '1 HOUR'
                """)
                
                activity_stats = current_activity.fetchone()
                
                # Активные загрузки
                active_downloads = await session.execute("""
                    SELECT 
                        COUNT(*) as processing_downloads,
                        COUNT(*) FILTER (WHERE status = 'pending') as pending_downloads
                    FROM download_tasks 
                    WHERE status IN ('processing', 'pending')
                """)
                
                download_stats = active_downloads.fetchone()
                
                # Системная нагрузка (последние 5 минут)
                recent_load = await session.execute("""
                    SELECT COUNT(*) as recent_requests
                    FROM system_events 
                    WHERE created_at >= NOW() - INTERVAL '5 MINUTES'
                """)
                
                load_stats = recent_load.fetchone()
                
                return {
                    'timestamp': datetime.utcnow().isoformat(),
                    'active_users_last_hour': activity_stats.active_users or 0,
                    'total_events_last_hour': activity_stats.total_events or 0,
                    'processing_downloads': download_stats.processing_downloads or 0,
                    'pending_downloads': download_stats.pending_downloads or 0,
                    'requests_last_5_min': load_stats.recent_requests or 0,
                    'system_health': 'healthy'  # Можно добавить логику определения здоровья
                }
                
        except Exception as e:
            logger.error(f"Error getting realtime metrics: {e}")
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'error': str(e),
                'system_health': 'error'
            }
    
    async def get_top_users(self, limit: int = 10, metric: str = 'downloads') -> List[Dict[str, Any]]:
        """
        Получить топ пользователей по метрике
        
        Args:
            limit: Количество пользователей
            metric: Метрика для сортировки (downloads/revenue/activity)
        
        Returns:
            Список топ пользователей
        """
        try:
            async with get_async_session() as session:
                if metric == 'downloads':
                    query = """
                        SELECT 
                            u.telegram_id,
                            u.username,
                            u.user_type,
                            u.downloads_total,
                            u.downloads_today
                        FROM users u
                        WHERE u.downloads_total > 0
                        ORDER BY u.downloads_total DESC
                        LIMIT :limit
                    """
                elif metric == 'revenue':
                    query = """
                        SELECT 
                            u.telegram_id,
                            u.username,
                            u.user_type,
                            COALESCE(SUM(p.amount), 0) as total_spent,
                            COUNT(p.id) as payments_count
                        FROM users u
                        LEFT JOIN payments p ON u.id = p.user_id AND p.status = 'completed'
                        GROUP BY u.id, u.telegram_id, u.username, u.user_type
                        HAVING COALESCE(SUM(p.amount), 0) > 0
                        ORDER BY total_spent DESC
                        LIMIT :limit
                    """
                else:  # activity
                    query = """
                        SELECT 
                            u.telegram_id,
                            u.username,
                            u.user_type,
                            u.last_active_at,
                            u.session_count
                        FROM users u
                        WHERE u.last_active_at IS NOT NULL
                        ORDER BY u.last_active_at DESC
                        LIMIT :limit
                    """
                
                result = await session.execute(query, {'limit': limit})
                
                top_users = []
                for row in result.fetchall():
                    user_data = {
                        'telegram_id': row.telegram_id,
                        'username': row.username,
                        'user_type': row.user_type
                    }
                    
                    if metric == 'downloads':
                        user_data.update({
                            'total_downloads': row.downloads_total,
                            'downloads_today': row.downloads_today
                        })
                    elif metric == 'revenue':
                        user_data.update({
                            'total_spent': float(row.total_spent),
                            'payments_count': row.payments_count
                        })
                    else:  # activity
                        user_data.update({
                            'last_active': row.last_active_at.isoformat() if row.last_active_at else None,
                            'session_count': row.session_count or 0
                        })
                    
                    top_users.append(user_data)
                
                return top_users
                
        except Exception as e:
            logger.error(f"Error getting top users: {e}")
            return []
    
    async def cleanup_old_events(self, days_old: int = 30) -> int:
        """
        Очистка старых аналитических событий
        
        Args:
            days_old: Возраст событий в днях
            
        Returns:
            Количество удаленных записей
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            total_deleted = 0
            
            async with get_async_session() as session:
                # Удаляем старые пользовательские события
                user_events_result = await session.execute(
                    "DELETE FROM user_events WHERE created_at < :cutoff",
                    {'cutoff': cutoff_date}
                )
                total_deleted += user_events_result.rowcount
                
                # Удаляем старые системные события
                system_events_result = await session.execute(
                    "DELETE FROM system_events WHERE created_at < :cutoff",
                    {'cutoff': cutoff_date}
                )
                total_deleted += system_events_result.rowcount
                
                # Удаляем старые события загрузок
                download_events_result = await session.execute(
                    "DELETE FROM download_events WHERE created_at < :cutoff",
                    {'cutoff': cutoff_date}
                )
                total_deleted += download_events_result.rowcount
                
                await session.commit()
                
                logger.info(f"Cleaned up {total_deleted} old analytics events")
                return total_deleted
                
        except Exception as e:
            logger.error(f"Error cleaning up old events: {e}")
            return 0

# Глобальный экземпляр сервиса
analytics_service = AnalyticsService()

# Функции для удобства использования
async def get_user_stats(user_id: Optional[int] = None, time_range: TimeRange = TimeRange.MONTH):
    """Получить статистику пользователей"""
    return await analytics_service.get_user_analytics(user_id, time_range)

async def get_download_stats(time_range: TimeRange = TimeRange.MONTH):
    """Получить статистику загрузок"""
    return await analytics_service.get_download_analytics(time_range)

async def get_financial_stats(time_range: TimeRange = TimeRange.MONTH):
    """Получить финансовую статистику"""
    return await analytics_service.get_financial_analytics(time_range)

async def get_system_stats(time_range: TimeRange = TimeRange.DAY):
    """Получить системную статистику"""
    return await analytics_service.get_system_analytics(time_range)

async def track_event(event_type: str, user_id: Optional[int] = None, event_data: Optional[Dict] = None):
    """Отследить событие"""
    return await analytics_service.track_custom_event(event_type, user_id, event_data)

async def generate_analytics_report(report_type: str = "comprehensive", time_range: TimeRange = TimeRange.MONTH):
    """Сгенерировать аналитический отчет"""
    return await analytics_service.generate_report(report_type, time_range)

async def get_realtime_dashboard():
    """Получить данные для dashboard в реальном времени"""
    return await analytics_service.get_realtime_metrics()

async def get_top_performers(metric: str = "downloads", limit: int = 10):
    """Получить топ пользователей"""
    return await analytics_service.get_top_users(limit, metric)
    