"""
VideoBot Pro - Analytics Service
Сбор, обработка и анализ аналитических данных
"""

import asyncio
import structlog
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Union
from collections import defaultdict, deque
import json

from shared.models import (
    AnalyticsEvent, DailyStats, EventType, User, DownloadTask, 
    Payment, track_user_event, track_download_event, track_payment_event
)
from shared.services.database import DatabaseService
from shared.services.redis import RedisService

logger = structlog.get_logger(__name__)

class MetricsCollector:
    """Коллектор метрик в реальном времени"""
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
        self.metrics_buffer = defaultdict(lambda: defaultdict(int))
        self.events_buffer = deque(maxlen=1000)  # Буфер последних событий
        self.flush_interval = 60  # Сохранение в Redis каждую минуту
        self._running = False
        
    async def start(self):
        """Запустить коллектор метрик"""
        if self._running:
            return
            
        self._running = True
        
        # Запускаем задачу периодического сохранения
        asyncio.create_task(self._flush_metrics_loop())
        
        logger.info("Metrics collector started")
    
    async def stop(self):
        """Остановить коллектор метрик"""
        self._running = False
        await self._flush_metrics()
        logger.info("Metrics collector stopped")
    
    def record_event(self, event_type: str, value: float = 1, tags: Dict[str, str] = None):
        """Записать событие в метрики"""
        timestamp = datetime.utcnow()
        
        # Добавляем в буфер событий
        event_data = {
            "type": event_type,
            "value": value,
            "timestamp": timestamp.isoformat(),
            "tags": tags or {}
        }
        self.events_buffer.append(event_data)
        
        # Обновляем счетчики по часам
        hour_key = timestamp.strftime("%Y-%m-%d:%H")
        self.metrics_buffer[hour_key][event_type] += value
        
        # Если есть теги, создаем отдельные метрики
        if tags:
            for tag_key, tag_value in tags.items():
                tagged_key = f"{event_type}:{tag_key}:{tag_value}"
                self.metrics_buffer[hour_key][tagged_key] += value
    
    def record_user_activity(self, user_id: int, activity_type: str, user_type: str = None):
        """Записать активность пользователя"""
        tags = {"user_type": user_type} if user_type else {}
        self.record_event(f"user_activity:{activity_type}", 1, tags)
        
        # Уникальные активные пользователи
        hour_key = datetime.utcnow().strftime("%Y-%m-%d:%H")
        redis_key = f"active_users:{hour_key}"
        asyncio.create_task(self._add_active_user(redis_key, user_id))
    
    def record_download_event(self, event_type: str, platform: str, file_size_mb: float = 0):
        """Записать событие скачивания"""
        self.record_event("downloads:total", 1)
        self.record_event(f"downloads:{event_type}", 1)
        self.record_event(f"downloads:platform:{platform}", 1)
        
        if file_size_mb > 0:
            self.record_event("downloads:total_size_mb", file_size_mb)
    
    def record_payment_event(self, event_type: str, amount: float, currency: str = "USD"):
        """Записать событие платежа"""
        self.record_event("payments:total", 1)
        self.record_event(f"payments:{event_type}", 1)
        self.record_event(f"payments:amount_{currency}", amount)
    
    def record_system_metric(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """Записать системную метрику"""
        self.record_event(f"system:{metric_name}", value, tags)
    
    async def _add_active_user(self, redis_key: str, user_id: int):
        """Добавить активного пользователя в Redis set"""
        try:
            await self.redis.set_add(redis_key, user_id)
            await self.redis.expire(redis_key, 7200)  # 2 часа
        except Exception as e:
            logger.error(f"Failed to add active user: {e}")
    
    async def _flush_metrics_loop(self):
        """Цикл периодического сохранения метрик"""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self._flush_metrics()
            except Exception as e:
                logger.error(f"Error in metrics flush loop: {e}")
    
    async def _flush_metrics(self):
        """Сохранить накопленные метрики в Redis"""
        if not self.metrics_buffer:
            return
        
        try:
            # Копируем текущий буфер и очищаем его
            current_buffer = dict(self.metrics_buffer)
            self.metrics_buffer.clear()
            
            # Сохраняем метрики в Redis
            for hour_key, metrics in current_buffer.items():
                redis_key = f"metrics:{hour_key}"
                
                for metric_name, value in metrics.items():
                    await self.redis.hash_set(redis_key, metric_name, value)
                
                await self.redis.expire(redis_key, 86400 * 7)  # 7 дней
            
            logger.debug(f"Flushed metrics for {len(current_buffer)} hours")
            
        except Exception as e:
            logger.error(f"Failed to flush metrics: {e}")
    
    async def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получить последние события"""
        return list(self.events_buffer)[-limit:]
    
    async def get_hourly_metrics(self, hours_back: int = 24) -> Dict[str, Dict[str, float]]:
        """Получить почасовые метрики"""
        end_time = datetime.utcnow()
        metrics_data = {}
        
        for i in range(hours_back):
            hour_time = end_time - timedelta(hours=i)
            hour_key = hour_time.strftime("%Y-%m-%d:%H")
            
            redis_key = f"metrics:{hour_key}"
            hour_metrics = await self.redis.hash_get_all(redis_key)
            
            if hour_metrics:
                # Конвертируем строковые значения в числа
                metrics_data[hour_key] = {
                    k: float(v) for k, v in hour_metrics.items()
                }
        
        return metrics_data

class AnalyticsService:
    """Основной сервис аналитики"""
    
    def __init__(self, database_service: DatabaseService, redis_service: RedisService):
        self.db = database_service
        self.redis = redis_service
        self.metrics_collector = MetricsCollector(redis_service)
        self._running = False
        self._aggregation_task = None
        
    async def start(self):
        """Запустить сервис аналитики"""
        if self._running:
            return
            
        logger.info("Starting analytics service...")
        
        await self.metrics_collector.start()
        
        # Запускаем задачу агрегации данных
        self._aggregation_task = asyncio.create_task(self._aggregation_loop())
        
        self._running = True
        logger.info("Analytics service started")
    
    async def stop(self):
        """Остановить сервис аналитики"""
        self._running = False
        
        if self._aggregation_task:
            self._aggregation_task.cancel()
            try:
                await self._aggregation_task
            except asyncio.CancelledError:
                pass
        
        await self.metrics_collector.stop()
        logger.info("Analytics service stopped")
    
    def is_running(self) -> bool:
        """Проверить, запущен ли сервис"""
        return self._running
    
    async def track_user_event(self, event_type: str, user_id: int, 
                             telegram_user_id: int = None, user_type: str = None, 
                             event_data: Dict[str, Any] = None, value: float = None):
        """Отследить событие пользователя"""
        try:
            # Записываем в базу данных
            async with self.db.get_session() as session:
                event = track_user_event(
                    event_type=event_type,
                    user_id=user_id,
                    telegram_user_id=telegram_user_id,
                    user_type=user_type,
                    event_data=event_data,
                    value=value
                )
                session.add(event)
                await session.commit()
            
            # Записываем в метрики
            self.metrics_collector.record_event(
                f"user_events:{event_type}", 
                value or 1, 
                {"user_type": user_type} if user_type else None
            )
            
            logger.debug(f"Tracked user event: {event_type}", user_id=user_id)
            
        except Exception as e:
            logger.error(f"Failed to track user event: {e}", event_type=event_type, user_id=user_id)
    
    async def track_download_event(self, event_type: str, user_id: int, platform: str,
                                 file_size_mb: float = None, duration_seconds: int = None,
                                 event_data: Dict[str, Any] = None):
        """Отследить событие скачивания"""
        try:
            # Записываем в базу данных
            async with self.db.get_session() as session:
                event = track_download_event(
                    event_type=event_type,
                    user_id=user_id,
                    platform=platform,
                    file_size_mb=file_size_mb,
                    duration_seconds=duration_seconds,
                    event_data=event_data
                )
                session.add(event)
                await session.commit()
            
            # Записываем в метрики
            self.metrics_collector.record_download_event(
                event_type, platform, file_size_mb or 0
            )
            
            logger.debug(f"Tracked download event: {event_type}", user_id=user_id, platform=platform)
            
        except Exception as e:
            logger.error(f"Failed to track download event: {e}", event_type=event_type, user_id=user_id)
    
    async def track_payment_event(self, event_type: str, user_id: int, amount: float,
                                currency: str = "USD", payment_method: str = None,
                                event_data: Dict[str, Any] = None):
        """Отследить событие платежа"""
        try:
            # Записываем в базу данных
            async with self.db.get_session() as session:
                event = track_payment_event(
                    event_type=event_type,
                    user_id=user_id,
                    payment_amount=amount,
                    payment_method=payment_method,
                    event_data=event_data or {}
                )
                session.add(event)
                await session.commit()
            
            # Записываем в метрики
            self.metrics_collector.record_payment_event(event_type, amount, currency)
            
            logger.debug(f"Tracked payment event: {event_type}", user_id=user_id, amount=amount)
            
        except Exception as e:
            logger.error(f"Failed to track payment event: {e}", event_type=event_type, user_id=user_id)
    
    async def track_system_event(self, event_type: str, event_data: Dict[str, Any] = None,
                               value: float = None):
        """Отследить системное событие"""
        try:
            # Записываем в базу данных
            async with self.db.get_session() as session:
                event = AnalyticsEvent.track_event(
                    event_type=event_type,
                    event_data=event_data,
                    value=value,
                    source="system"
                )
                session.add(event)
                await session.commit()
            
            # Записываем в метрики
            self.metrics_collector.record_system_metric(event_type, value or 1)
            
            logger.debug(f"Tracked system event: {event_type}")
            
        except Exception as e:
            logger.error(f"Failed to track system event: {e}", event_type=event_type)
    
    async def get_daily_stats(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """Получить ежедневную статистику за период"""
        try:
            async with self.db.get_session() as session:
                stats = await session.query(DailyStats).filter(
                    DailyStats.stats_date >= start_date,
                    DailyStats.stats_date <= end_date
                ).order_by(DailyStats.stats_date).all()
                
                return [stat.to_dict() for stat in stats]
                
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return []
    
    async def get_realtime_metrics(self) -> Dict[str, Any]:
        """Получить метрики в реальном времени"""
        try:
            # Получаем метрики за последний час
            hourly_metrics = await self.metrics_collector.get_hourly_metrics(1)
            current_hour = datetime.utcnow().strftime("%Y-%m-%d:%H")
            
            current_metrics = hourly_metrics.get(current_hour, {})
            
            # Получаем активных пользователей
            active_users_key = f"active_users:{current_hour}"
            active_users_count = len(await self.redis.set_members(active_users_key))
            
            # Получаем последние события
            recent_events = await self.metrics_collector.get_recent_events(10)
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "active_users": active_users_count,
                "downloads_total": current_metrics.get("downloads:total", 0),
                "downloads_completed": current_metrics.get("downloads:completed", 0),
                "downloads_failed": current_metrics.get("downloads:failed", 0),
                "payments_total": current_metrics.get("payments:total", 0),
                "revenue_usd": current_metrics.get("payments:amount_USD", 0),
                "user_registrations": current_metrics.get("user_events:user_registered", 0),
                "recent_events": recent_events
            }
            
        except Exception as e:
            logger.error(f"Failed to get realtime metrics: {e}")
            return {"error": str(e)}
    
    async def get_user_analytics(self, user_id: int, days_back: int = 30) -> Dict[str, Any]:
        """Получить аналитику конкретного пользователя"""
        try:
            start_date = datetime.utcnow() - timedelta(days=days_back)
            
            async with self.db.get_session() as session:
                # Получаем события пользователя
                events = await session.query(AnalyticsEvent).filter(
                    AnalyticsEvent.user_id == user_id,
                    AnalyticsEvent.created_at >= start_date
                ).order_by(AnalyticsEvent.created_at.desc()).all()
                
                # Группируем события по типам
                events_by_type = defaultdict(int)
                events_by_date = defaultdict(int)
                
                for event in events:
                    events_by_type[event.event_type] += 1
                    event_date = event.created_at.date().isoformat()
                    events_by_date[event_date] += 1
                
                # Получаем статистику скачиваний
                downloads = await session.query(DownloadTask).filter(
                    DownloadTask.user_id == user_id,
                    DownloadTask.created_at >= start_date
                ).all()
                
                downloads_by_platform = defaultdict(int)
                total_file_size = 0
                
                for download in downloads:
                    downloads_by_platform[download.platform] += 1
                    if download.file_size_bytes:
                        total_file_size += download.file_size_bytes
                
                # Получаем платежи
                payments = await session.query(Payment).filter(
                    Payment.user_id == user_id,
                    Payment.created_at >= start_date
                ).all()
                
                total_spent = sum(p.amount for p in payments if p.status == "completed")
                
                return {
                    "user_id": user_id,
                    "period_days": days_back,
                    "total_events": len(events),
                    "events_by_type": dict(events_by_type),
                    "events_by_date": dict(events_by_date),
                    "downloads": {
                        "total": len(downloads),
                        "by_platform": dict(downloads_by_platform),
                        "total_size_mb": round(total_file_size / (1024 * 1024), 2)
                    },
                    "payments": {
                        "total": len(payments),
                        "total_spent": float(total_spent),
                        "successful": len([p for p in payments if p.status == "completed"])
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get user analytics: {e}")
            return {"error": str(e)}
    
    async def get_platform_analytics(self, days_back: int = 30) -> Dict[str, Any]:
        """Получить аналитику по платформам"""
        try:
            start_date = datetime.utcnow() - timedelta(days=days_back)
            
            async with self.db.get_session() as session:
                # Получаем статистику скачиваний по платформам
                downloads_query = """
                    SELECT 
                        platform,
                        COUNT(*) as total_downloads,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                        AVG(CASE WHEN file_size_bytes > 0 THEN file_size_bytes END) as avg_file_size,
                        SUM(CASE WHEN file_size_bytes > 0 THEN file_size_bytes END) as total_file_size
                    FROM download_tasks 
                    WHERE created_at >= :start_date 
                    GROUP BY platform
                    ORDER BY total_downloads DESC
                """
                
                result = await session.execute(downloads_query, {"start_date": start_date})
                platforms_data = []
                
                for row in result.fetchall():
                    platform_stats = {
                        "platform": row.platform,
                        "total_downloads": row.total_downloads,
                        "successful": row.successful,
                        "failed": row.failed,
                        "success_rate": round((row.successful / row.total_downloads) * 100, 2),
                        "avg_file_size_mb": round((row.avg_file_size or 0) / (1024 * 1024), 2),
                        "total_file_size_gb": round((row.total_file_size or 0) / (1024 * 1024 * 1024), 2)
                    }
                    platforms_data.append(platform_stats)
                
                return {
                    "period_days": days_back,
                    "platforms": platforms_data,
                    "summary": {
                        "total_platforms": len(platforms_data),
                        "most_popular": platforms_data[0]["platform"] if platforms_data else None,
                        "total_downloads": sum(p["total_downloads"] for p in platforms_data)
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get platform analytics: {e}")
            return {"error": str(e)}
    
    async def generate_report(self, report_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Генерировать аналитический отчет"""
        params = params or {}
        
        try:
            if report_type == "daily_summary":
                return await self._generate_daily_summary_report(params)
            elif report_type == "user_growth":
                return await self._generate_user_growth_report(params)
            elif report_type == "revenue":
                return await self._generate_revenue_report(params)
            elif report_type == "downloads":
                return await self._generate_downloads_report(params)
            elif report_type == "comprehensive":
                return await self._generate_comprehensive_report(params)
            else:
                return {"error": f"Unknown report type: {report_type}"}
                
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return {"error": str(e)}
    
    async def _generate_daily_summary_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Генерировать ежедневный сводный отчет"""
        target_date = params.get("date", date.today())
        
        async with self.db.get_session() as session:
            stats = await session.query(DailyStats).filter(
                DailyStats.stats_date == target_date
            ).first()
            
            if not stats:
                return {"error": "No data for the specified date"}
            
            return {
                "report_type": "daily_summary",
                "date": target_date.isoformat(),
                "generated_at": datetime.utcnow().isoformat(),
                **stats.to_dict()
            }
    
    async def _generate_user_growth_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Генерировать отчет о росте пользователей"""
        days_back = params.get("days", 30)
        start_date = date.today() - timedelta(days=days_back)
        
        async with self.db.get_session() as session:
            daily_stats = await session.query(DailyStats).filter(
                DailyStats.stats_date >= start_date
            ).order_by(DailyStats.stats_date).all()
            
            growth_data = []
            total_users = 0
            
            for stat in daily_stats:
                total_users += stat.new_users
                growth_data.append({
                    "date": stat.stats_date.isoformat(),
                    "new_users": stat.new_users,
                    "total_users": total_users,
                    "active_users": stat.active_users
                })
            
            return {
                "report_type": "user_growth",
                "period_days": days_back,
                "generated_at": datetime.utcnow().isoformat(),
                "growth_data": growth_data,
                "summary": {
                    "total_new_users": sum(s.new_users for s in daily_stats),
                    "avg_daily_growth": round(sum(s.new_users for s in daily_stats) / len(daily_stats), 2),
                    "peak_day": max(daily_stats, key=lambda x: x.new_users).stats_date.isoformat()
                }
            }
    
    async def _generate_revenue_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Генерировать отчет о доходах"""
        days_back = params.get("days", 30)
        start_date = date.today() - timedelta(days=days_back)
        
        async with self.db.get_session() as session:
            daily_stats = await session.query(DailyStats).filter(
                DailyStats.stats_date >= start_date
            ).order_by(DailyStats.stats_date).all()
            
            revenue_data = []
            for stat in daily_stats:
                revenue_data.append({
                    "date": stat.stats_date.isoformat(),
                    "revenue": float(stat.revenue_usd),
                    "payments": stat.total_payments,
                    "successful_payments": stat.successful_payments
                })
            
            total_revenue = sum(s.revenue_usd for s in daily_stats)
            total_payments = sum(s.total_payments for s in daily_stats)
            
            return {
                "report_type": "revenue",
                "period_days": days_back,
                "generated_at": datetime.utcnow().isoformat(),
                "revenue_data": revenue_data,
                "summary": {
                    "total_revenue": float(total_revenue),
                    "avg_daily_revenue": round(float(total_revenue) / len(daily_stats), 2),
                    "total_payments": total_payments,
                    "avg_payment_amount": round(float(total_revenue) / max(total_payments, 1), 2)
                }
            }
    
    async def _generate_downloads_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Генерировать отчет о скачиваниях"""
        days_back = params.get("days", 30)
        start_date = date.today() - timedelta(days=days_back)
        
        async with self.db.get_session() as session:
            daily_stats = await session.query(DailyStats).filter(
                DailyStats.stats_date >= start_date
            ).order_by(DailyStats.stats_date).all()
            
            downloads_data = []
            for stat in daily_stats:
                downloads_data.append({
                    "date": stat.stats_date.isoformat(),
                    "total_downloads": stat.total_downloads,
                    "successful": stat.successful_downloads,
                    "failed": stat.failed_downloads,
                    "success_rate": stat.download_success_rate,
                    "youtube": stat.youtube_downloads,
                    "tiktok": stat.tiktok_downloads,
                    "instagram": stat.instagram_downloads
                })
            
            total_downloads = sum(s.total_downloads for s in daily_stats)
            successful_downloads = sum(s.successful_downloads for s in daily_stats)
            
            return {
                "report_type": "downloads",
                "period_days": days_back,
                "generated_at": datetime.utcnow().isoformat(),
                "downloads_data": downloads_data,
                "summary": {
                    "total_downloads": total_downloads,
                    "successful_downloads": successful_downloads,
                    "overall_success_rate": round((successful_downloads / max(total_downloads, 1)) * 100, 2),
                    "avg_daily_downloads": round(total_downloads / len(daily_stats), 2),
                    "platform_totals": {
                        "youtube": sum(s.youtube_downloads for s in daily_stats),
                        "tiktok": sum(s.tiktok_downloads for s in daily_stats),
                        "instagram": sum(s.instagram_downloads for s in daily_stats)
                    }
                }
            }
    
    async def _generate_comprehensive_report(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Генерировать комплексный отчет"""
        days_back = params.get("days", 30)
        
        # Получаем все типы отчетов
        user_growth = await self._generate_user_growth_report(params)
        revenue = await self._generate_revenue_report(params)
        downloads = await self._generate_downloads_report(params)
        platform_analytics = await self.get_platform_analytics(days_back)
        
        return {
            "report_type": "comprehensive",
            "period_days": days_back,
            "generated_at": datetime.utcnow().isoformat(),
            "user_growth": user_growth,
            "revenue": revenue,
            "downloads": downloads,
            "platform_analytics": platform_analytics
        }
    
    async def _aggregation_loop(self):
        """Основной цикл агрегации данных"""
        while self._running:
            try:
                await self._aggregate_daily_stats()
                await asyncio.sleep(3600)  # Агрегация каждый час
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in aggregation loop: {e}")
                await asyncio.sleep(60)  # При ошибке подождать минуту
    
    async def _aggregate_daily_stats(self):
        """Агрегировать данные в ежедневную статистику"""
        try:
            target_date = date.today()
            
            async with self.db.get_session() as session:
                # Получаем или создаем запись за сегодня
                daily_stats = await session.query(DailyStats).filter(
                    DailyStats.stats_date == target_date
                ).first()
                
                if not daily_stats:
                    daily_stats = DailyStats(stats_date=target_date)
                    session.add(daily_stats)
                
                # Агрегируем данные пользователей
                await self._aggregate_user_metrics(session, daily_stats, target_date)
                
                # Агрегируем данные скачиваний
                await self._aggregate_download_metrics(session, daily_stats, target_date)
                
                # Агрегируем финансовые данные
                await self._aggregate_payment_metrics(session, daily_stats, target_date)
                
                await session.commit()
                
                logger.debug(f"Aggregated daily stats for {target_date}")
                
        except Exception as e:
            logger.error(f"Failed to aggregate daily stats: {e}")
    
    async def _aggregate_user_metrics(self, session, daily_stats: DailyStats, target_date: date):
        """Агрегировать метрики пользователей"""
        # Новые пользователи
        new_users_query = """
            SELECT COUNT(*) FROM users 
            WHERE DATE(created_at) = :target_date
        """
        result = await session.execute(new_users_query, {"target_date": target_date})
        daily_stats.new_users = result.scalar()
        
        # Активные пользователи
        active_users_query = """
            SELECT COUNT(DISTINCT user_id) FROM analytics_events 
            WHERE DATE(created_at) = :target_date
        """
        result = await session.execute(active_users_query, {"target_date": target_date})
        daily_stats.active_users = result.scalar()
        
        # Trial пользователи
        trial_users_query = """
            SELECT COUNT(*) FROM analytics_events 
            WHERE DATE(created_at) = :target_date 
            AND event_type = 'user_trial_started'
        """
        result = await session.execute(trial_users_query, {"target_date": target_date})
        daily_stats.trial_users_started = result.scalar()
        
        # Premium покупки
        premium_query = """
            SELECT COUNT(*) FROM analytics_events 
            WHERE DATE(created_at) = :target_date 
            AND event_type = 'user_premium_purchased'
        """
        result = await session.execute(premium_query, {"target_date": target_date})
        daily_stats.premium_purchases = result.scalar()
    
    async def _aggregate_download_metrics(self, session, daily_stats: DailyStats, target_date: date):
        """Агрегировать метрики скачиваний"""
        downloads_query = """
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN platform = 'youtube' THEN 1 END) as youtube,
                COUNT(CASE WHEN platform = 'tiktok' THEN 1 END) as tiktok,
                COUNT(CASE WHEN platform = 'instagram' THEN 1 END) as instagram,
                SUM(CASE WHEN file_size_bytes > 0 THEN file_size_bytes ELSE 0 END) as total_size
            FROM download_tasks 
            WHERE DATE(created_at) = :target_date
        """
        result = await session.execute(downloads_query, {"target_date": target_date})
        row = result.fetchone()
        
        daily_stats.total_downloads = row.total
        daily_stats.successful_downloads = row.successful
        daily_stats.failed_downloads = row.failed
        daily_stats.youtube_downloads = row.youtube
        daily_stats.tiktok_downloads = row.tiktok
        daily_stats.instagram_downloads = row.instagram
        daily_stats.total_file_size_mb = (row.total_size or 0) / (1024 * 1024)
    
    async def _aggregate_payment_metrics(self, session, daily_stats: DailyStats, target_date: date):
        """Агрегировать финансовые метрики"""
        payments_query = """
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
                SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END) as revenue
            FROM payments 
            WHERE DATE(created_at) = :target_date
        """
        result = await session.execute(payments_query, {"target_date": target_date})
        row = result.fetchone()
        
        daily_stats.total_payments = row.total
        daily_stats.successful_payments = row.successful
        daily_stats.revenue_usd = float(row.revenue or 0)
    
    async def shutdown(self):
        """Корректное завершение работы сервиса"""
        await self.stop()