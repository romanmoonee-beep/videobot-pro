"""
VideoBot Pro - Analytics API
API endpoints для аналитики и метрик
"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import func, and_, or_, desc, text
import structlog

from shared.schemas.analytics import (
    DashboardSchema, AnalyticsQuerySchema, RealtimeMetricsSchema,
    UserAnalyticsSchema, DownloadAnalyticsSchema, RevenueAnalyticsSchema,
    SystemAnalyticsSchema, AnalyticsReportSchema, KPISchema
)
from shared.models import User, DownloadTask, Payment, AnalyticsEvent, DailyStats
from shared.services.database import get_db_session
from shared.services.analytics import AnalyticsService
from ..dependencies import get_current_admin, require_permission, get_analytics_service
from ..utils.export import export_analytics_to_csv, export_analytics_to_excel

logger = structlog.get_logger(__name__)
router = APIRouter()

@router.get("/dashboard", response_model=DashboardSchema)
async def get_dashboard_data(
    current_admin = Depends(require_permission("analytics_view")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Получение данных для главного дашборда
    Возвращает основные метрики, KPI, графики
    """
    try:
        # Получаем основные метрики
        overview = await _get_overview_metrics()
        
        # KPI показатели
        kpis = await _get_kpi_metrics()
        
        # Данные для графиков
        charts_data = await _get_charts_data()
        
        # Последняя активность
        recent_activity = await _get_recent_activity()
        
        # Алерты и уведомления
        alerts = await _get_system_alerts()
        
        # Здоровье системы
        system_health = await _get_system_health_summary()
        
        return DashboardSchema(
            overview=overview,
            kpis=kpis,
            charts_data=charts_data,
            recent_activity=recent_activity,
            alerts=alerts,
            system_health=system_health,
            last_updated=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении данных дашборда"
        )

@router.get("/realtime", response_model=RealtimeMetricsSchema)
async def get_realtime_metrics(
    current_admin = Depends(require_permission("analytics_view")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Получение метрик в реальном времени
    Обновляется каждые 30 секунд на фронтенде
    """
    try:
        realtime_data = await analytics_service.get_realtime_metrics()
        
        return RealtimeMetricsSchema(
            timestamp=datetime.utcnow(),
            active_users=realtime_data.get("active_users", 0),
            active_downloads=realtime_data.get("downloads_total", 0),
            pending_downloads=realtime_data.get("downloads_pending", 0),
            requests_per_minute=realtime_data.get("requests_per_minute", 0),
            errors_per_minute=realtime_data.get("errors_per_minute", 0),
            response_time_ms=realtime_data.get("response_time_ms", 0),
            cpu_usage_percent=realtime_data.get("cpu_usage", 0),
            memory_usage_percent=realtime_data.get("memory_usage", 0),
            system_status="healthy" if realtime_data.get("error") is None else "unhealthy"
        )
        
    except Exception as e:
        logger.error(f"Error getting realtime metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении метрик в реальном времени"
        )

@router.get("/users", response_model=UserAnalyticsSchema)
async def get_user_analytics(
    days: int = Query(30, ge=1, le=365, description="Период анализа в днях"),
    current_admin = Depends(require_permission("analytics_view"))
):
    """
    Аналитика пользователей
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Основные счетчики
            total_users = await session.query(User).filter(User.is_deleted == False).count()
            
            new_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.created_at >= start_date
                )
            ).count()
            
            active_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.last_active_at >= start_date
                )
            ).count()
            
            premium_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.is_premium == True
                )
            ).count()
            
            trial_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.user_type == "trial"
                )
            ).count()
            
            banned_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.is_banned == True
                )
            ).count()
            
            # Вычисляем метрики роста
            prev_period_start = start_date - timedelta(days=days)
            prev_new_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.created_at >= prev_period_start,
                    User.created_at < start_date
                )
            ).count()
            
            user_growth_rate = ((new_users - prev_new_users) / max(prev_new_users, 1)) * 100
            
            # Распределение по типам
            user_types = await session.query(
                User.user_type,
                func.count(User.id)
            ).filter(User.is_deleted == False).group_by(User.user_type).all()
            
            user_type_distribution = {user_type: count for user_type, count in user_types}
            
            # Источники регистрации
            registration_sources = await session.query(
                User.registration_source,
                func.count(User.id)
            ).filter(User.is_deleted == False).group_by(User.registration_source).all()
            
            registration_sources_dict = {
                source or "unknown": count for source, count in registration_sources
            }
            
            # Языковое распределение
            languages = await session.query(
                User.language_code,
                func.count(User.id)
            ).filter(User.is_deleted == False).group_by(User.language_code).all()
            
            language_distribution = {lang or "unknown": count for lang, count in languages}
            
            # Средние показатели активности
            avg_downloads_query = await session.query(
                func.avg(User.downloads_total)
            ).filter(User.is_deleted == False).scalar()
            
            avg_downloads_per_user = float(avg_downloads_query or 0)
            
            return UserAnalyticsSchema(
                total_users=total_users,
                new_users=new_users,
                active_users=active_users,
                premium_users=premium_users,
                trial_users=trial_users,
                banned_users=banned_users,
                user_growth_rate=round(user_growth_rate, 2),
                churn_rate=0.0,  # TODO: Вычислить на основе активности
                retention_rate=0.0,  # TODO: Вычислить на основе возвратов
                user_type_distribution=user_type_distribution,
                registration_sources=registration_sources_dict,
                language_distribution=language_distribution,
                avg_session_duration=0.0,  # TODO: Если добавим трекинг сессий
                avg_downloads_per_user=round(avg_downloads_per_user, 2),
                most_active_hours=[18, 19, 20, 21, 22]  # TODO: Вычислить реально
            )
            
    except Exception as e:
        logger.error(f"Error getting user analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении аналитики пользователей"
        )

@router.get("/downloads", response_model=DownloadAnalyticsSchema)
async def get_download_analytics(
    days: int = Query(30, ge=1, le=365),
    current_admin = Depends(require_permission("analytics_view")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Аналитика скачиваний
    """
    try:
        downloads_data = await analytics_service.get_platform_analytics(days)
        
        if "error" in downloads_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка при получении аналитики скачиваний"
            )
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Основная статистика
            total_downloads = await session.query(DownloadTask).filter(
                DownloadTask.created_at >= start_date
            ).count()
            
            successful_downloads = await session.query(DownloadTask).filter(
                and_(
                    DownloadTask.created_at >= start_date,
                    DownloadTask.status == "completed"
                )
            ).count()
            
            failed_downloads = await session.query(DownloadTask).filter(
                and_(
                    DownloadTask.created_at >= start_date,
                    DownloadTask.status == "failed"
                )
            ).count()
            
            success_rate = (successful_downloads / max(total_downloads, 1)) * 100
            
            # Статистика по платформам из сервиса
            platform_stats = {
                platform["platform"]: {
                    "total": platform["total_downloads"],
                    "successful": platform["successful_downloads"],
                    "failed": platform["failed_downloads"],
                    "success_rate": platform["success_rate"],
                    "avg_file_size": platform["avg_file_size_mb"],
                    "total_size": platform["total_file_size_gb"]
                }
                for platform in downloads_data.get("platforms", [])
            }
            
            # Самая популярная платформа
            most_popular = max(
                downloads_data.get("platforms", []),
                key=lambda x: x["total_downloads"],
                default={"platform": "unknown"}
            )["platform"]
            
            # Распределение по качеству
            quality_stats = await session.query(
                DownloadTask.actual_quality,
                func.count(DownloadTask.id)
            ).filter(
                DownloadTask.created_at >= start_date
            ).group_by(DownloadTask.actual_quality).all()
            
            quality_distribution = {
                quality or "unknown": count for quality, count in quality_stats
            }
            
            # Общий размер и средний размер файла
            size_stats = await session.query(
                func.sum(DownloadTask.file_size_bytes),
                func.avg(DownloadTask.file_size_bytes)
            ).filter(
                and_(
                    DownloadTask.created_at >= start_date,
                    DownloadTask.file_size_bytes.isnot(None)
                )
            ).first()
            
            total_size_gb = (size_stats[0] or 0) / (1024**3)
            avg_file_size_mb = (size_stats[1] or 0) / (1024**2)
            
            # Трендовые данные по дням
            daily_downloads = []
            for i in range(days):
                day_start = start_date + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                day_count = await session.query(DownloadTask).filter(
                    and_(
                        DownloadTask.created_at >= day_start,
                        DownloadTask.created_at < day_end
                    )
                ).count()
                
                daily_downloads.append({
                    "date": day_start.date().isoformat(),
                    "downloads": day_count
                })
            
            return DownloadAnalyticsSchema(
                total_downloads=total_downloads,
                successful_downloads=successful_downloads,
                failed_downloads=failed_downloads,
                success_rate=round(success_rate, 2),
                platform_stats=platform_stats,
                most_popular_platform=most_popular,
                quality_distribution=quality_distribution,
                format_distribution={"mp4": total_downloads},  # TODO: Добавить в модель
                total_size_gb=round(total_size_gb, 2),
                avg_file_size_mb=round(avg_file_size_mb, 2),
                avg_processing_time=0.0,  # TODO: Вычислить
                daily_downloads=daily_downloads,
                hourly_distribution={},  # TODO: Добавить
                error_rate=round((failed_downloads / max(total_downloads, 1)) * 100, 2),
                top_errors=[]  # TODO: Собирать статистику ошибок
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting download analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении аналитики скачиваний"
        )

@router.get("/revenue", response_model=RevenueAnalyticsSchema)
async def get_revenue_analytics(
    days: int = Query(30, ge=1, le=365),
    current_admin = Depends(require_permission("finance_view"))
):
    """
    Аналитика доходов (только для ролей с правами finance_view)
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Основная финансовая статистика
            total_revenue = await session.query(
                func.sum(Payment.amount)
            ).filter(
                and_(
                    Payment.created_at >= start_date,
                    Payment.status == "completed"
                )
            ).scalar() or 0
            
            total_payments = await session.query(Payment).filter(
                Payment.created_at >= start_date
            ).count()
            
            successful_payments = await session.query(Payment).filter(
                and_(
                    Payment.created_at >= start_date,
                    Payment.status == "completed"
                )
            ).count()
            
            payment_success_rate = (successful_payments / max(total_payments, 1)) * 100
            
            # Предыдущий период для сравнения
            prev_start = start_date - timedelta(days=days)
            prev_revenue = await session.query(
                func.sum(Payment.amount)
            ).filter(
                and_(
                    Payment.created_at >= prev_start,
                    Payment.created_at < start_date,
                    Payment.status == "completed"
                )
            ).scalar() or 0
            
            revenue_growth = ((total_revenue - prev_revenue) / max(prev_revenue, 1)) * 100
            
            # Средние значения
            avg_payment_amount = total_revenue / max(successful_payments, 1)
            
            # ARPUper active user
            active_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.last_active_at >= start_date
                )
            ).count()
            
            avg_revenue_per_user = total_revenue / max(active_users, 1)
            
            # Распределение по планам подписки
            subscription_stats = await session.query(
                Payment.subscription_plan,
                func.count(Payment.id),
                func.sum(Payment.amount)
            ).filter(
                and_(
                    Payment.created_at >= start_date,
                    Payment.status == "completed"
                )
            ).group_by(Payment.subscription_plan).all()
            
            subscription_distribution = {}
            most_popular_plan = "monthly"
            max_count = 0
            
            for plan, count, revenue in subscription_stats:
                subscription_distribution[plan] = {
                    "count": count,
                    "revenue": float(revenue),
                    "avg_amount": float(revenue / max(count, 1))
                }
                if count > max_count:
                    max_count = count
                    most_popular_plan = plan
            
            # Конверсии (примерные расчеты)
            trial_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.trial_used == True
                )
            ).count()
            
            premium_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.is_premium == True
                )
            ).count()
            
            trial_to_premium_rate = (premium_users / max(trial_users, 1)) * 100
            
            # Дневная динамика доходов
            daily_revenue = []
            for i in range(min(days, 30)):  # Максимум 30 дней для графика
                day_start = start_date + timedelta(days=i)
                day_end = day_start + timedelta(days=1)
                
                day_revenue = await session.query(
                    func.sum(Payment.amount)
                ).filter(
                    and_(
                        Payment.created_at >= day_start,
                        Payment.created_at < day_end,
                        Payment.status == "completed"
                    )
                ).scalar() or 0
                
                day_payments = await session.query(Payment).filter(
                    and_(
                        Payment.created_at >= day_start,
                        Payment.created_at < day_end
                    )
                ).count()
                
                daily_revenue.append({
                    "date": day_start.date().isoformat(),
                    "revenue": float(day_revenue),
                    "payments": day_payments
                })
            
            # MRR (Monthly Recurring Revenue) - упрощенный расчет
            monthly_subscriptions = await session.query(
                func.sum(Payment.amount)
            ).filter(
                and_(
                    Payment.created_at >= start_date,
                    Payment.status == "completed",
                    Payment.subscription_plan == "monthly"
                )
            ).scalar() or 0
            
            return RevenueAnalyticsSchema(
                total_revenue=float(total_revenue),
                revenue_growth=round(revenue_growth, 2),
                total_payments=total_payments,
                successful_payments=successful_payments,
                payment_success_rate=round(payment_success_rate, 2),
                avg_payment_amount=round(avg_payment_amount, 2),
                avg_revenue_per_user=round(avg_revenue_per_user, 2),
                subscription_distribution=subscription_distribution,
                most_popular_plan=most_popular_plan,
                trial_to_premium_rate=round(trial_to_premium_rate, 2),
                free_to_premium_rate=0.0,  # TODO: Вычислить
                daily_revenue=daily_revenue,
                monthly_recurring_revenue=float(monthly_subscriptions)
            )
            
    except Exception as e:
        logger.error(f"Error getting revenue analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении аналитики доходов"
        )

@router.get("/system", response_model=SystemAnalyticsSchema)
async def get_system_analytics(
    days: int = Query(7, ge=1, le=30),
    current_admin = Depends(require_permission("system_stats"))
):
    """
    Системная аналитика и производительность
    """
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Статистика запросов из аналитических событий
            total_requests = await session.query(AnalyticsEvent).filter(
                AnalyticsEvent.created_at >= start_date
            ).count()
            
            error_events = await session.query(AnalyticsEvent).filter(
                and_(
                    AnalyticsEvent.created_at >= start_date,
                    AnalyticsEvent.event_type == "error_occurred"
                )
            ).count()
            
            successful_requests = total_requests - error_events
            error_rate = (error_events / max(total_requests, 1)) * 100
            
            # Средние показатели производительности
            avg_response_time = await session.query(
                func.avg(AnalyticsEvent.duration_seconds)
            ).filter(
                and_(
                    AnalyticsEvent.created_at >= start_date,
                    AnalyticsEvent.duration_seconds.isnot(None)
                )
            ).scalar() or 0
            
            max_response_time = await session.query(
                func.max(AnalyticsEvent.duration_seconds)
            ).filter(
                and_(
                    AnalyticsEvent.created_at >= start_date,
                    AnalyticsEvent.duration_seconds.isnot(None)
                )
            ).scalar() or 0
            
            # Пропускная способность (запросов в секунду)
            total_seconds = days * 24 * 3600
            throughput = total_requests / max(total_seconds, 1)
            
            # Статистика задач (примерные данные)
            active_tasks = await session.query(DownloadTask).filter(
                DownloadTask.status == "processing"
            ).count()
            
            pending_tasks = await session.query(DownloadTask).filter(
                DownloadTask.status == "pending"
            ).count()
            
            completed_tasks = await session.query(DownloadTask).filter(
                and_(
                    DownloadTask.created_at >= start_date,
                    DownloadTask.status == "completed"
                )
            ).count()
            
            failed_tasks = await session.query(DownloadTask).filter(
                and_(
                    DownloadTask.created_at >= start_date,
                    DownloadTask.status == "failed"
                )
            ).count()
            
            # Топ типов ошибок
            error_types = await session.query(
                AnalyticsEvent.event_data,
                func.count(AnalyticsEvent.id)
            ).filter(
                and_(
                    AnalyticsEvent.created_at >= start_date,
                    AnalyticsEvent.event_type == "error_occurred"
                )
            ).group_by(AnalyticsEvent.event_data).limit(10).all()
            
            top_error_types = []
            for error_data, count in error_types:
                error_type = "unknown"
                if error_data and isinstance(error_data, dict):
                    error_type = error_data.get("error_type", "unknown")
                
                top_error_types.append({
                    "error_type": error_type,
                    "count": count,
                    "percentage": (count / max(error_events, 1)) * 100
                })
            
            critical_errors = await session.query(AnalyticsEvent).filter(
                and_(
                    AnalyticsEvent.created_at >= start_date,
                    AnalyticsEvent.event_type == "error_occurred",
                    AnalyticsEvent.event_data.op("->>")(text("'level'")) == "CRITICAL"
                )
            ).count()
            
            return SystemAnalyticsSchema(
                total_requests=total_requests,
                successful_requests=successful_requests,
                failed_requests=error_events,
                error_rate=round(error_rate, 2),
                avg_response_time=round(float(avg_response_time), 3),
                max_response_time=round(float(max_response_time), 3),
                throughput=round(throughput, 2),
                avg_cpu_usage=0.0,  # TODO: Собирать метрики системы
                avg_memory_usage=0.0,  # TODO: Собирать метрики системы
                disk_usage=0.0,  # TODO: Собирать метрики системы
                db_connection_count=0,  # TODO: Получать из database service
                db_query_time=0.0,  # TODO: Собирать метрики БД
                db_pool_utilization=0.0,  # TODO: Собирать метрики БД
                active_tasks=active_tasks,
                pending_tasks=pending_tasks,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
                top_error_types=top_error_types,
                critical_errors=critical_errors
            )
            
    except Exception as e:
        logger.error(f"Error getting system analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении системной аналитики"
        )

@router.post("/reports/generate")
async def generate_analytics_report(
    report_type: str = Query(..., description="Тип отчета"),
    date_from: date = Query(..., description="Начальная дата"),
    date_to: date = Query(..., description="Конечная дата"),
    format: str = Query("json", regex="^(json|csv|excel)$"),
    background_tasks: BackgroundTasks,
    current_admin = Depends(require_permission("analytics_export")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Генерация аналитических отчетов
    """
    try:
        # Валидация периода
        if date_to < date_from:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Конечная дата не может быть раньше начальной"
            )
        
        days_diff = (date_to - date_from).days
        if days_diff > 365:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Максимальный период отчета - 365 дней"
            )
        
        # Параметры для генерации отчета
        params = {
            "date_from": date_from,
            "date_to": date_to,
            "days": days_diff
        }
        
        # Генерируем отчет
        report_data = await analytics_service.generate_report(report_type, params)
        
        if "error" in report_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Ошибка генерации отчета: {report_data['error']}"
            )
        
        # Если запрошен JSON, возвращаем данные
        if format == "json":
            return report_data
        
        # Для CSV/Excel форматов генерируем файл в фоне
        background_tasks.add_task(
            _generate_report_file,
            report_data,
            format,
            current_admin.id
        )
        
        return {
            "message": f"Отчет '{report_type}' генерируется",
            "format": format,
            "estimated_time": "1-2 минуты"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating analytics report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при генерации отчета"
        )

@router.get("/kpis")
async def get_kpi_dashboard(
    current_admin = Depends(require_permission("analytics_view"))
):
    """
    Получение KPI показателей для дашборда
    """
    try:
        kpis = await _get_kpi_metrics()
        return {"kpis": kpis}
        
    except Exception as e:
        logger.error(f"Error getting KPIs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении KPI"
        )

# Вспомогательные функции

async def _get_overview_metrics() -> Dict[str, Any]:
    """Получение обзорных метрик"""
    async with get_db_session() as session:
        total_users = await session.query(User).filter(User.is_deleted == False).count()
        
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        new_users_today = await session.query(User).filter(
            and_(
                User.is_deleted == False,
                User.created_at >= today_start
            )
        ).count()
        
        active_downloads = await session.query(DownloadTask).filter(
            DownloadTask.status.in_(["pending", "processing"])
        ).count()
        
        premium_users = await session.query(User).filter(
            and_(User.is_deleted == False, User.is_premium == True)
        ).count()
        
        return {
            "total_users": total_users,
            "new_users_today": new_users_today,
            "active_downloads": active_downloads,
            "premium_users": premium_users
        }

async def _get_kpi_metrics() -> List[KPISchema]:
    """Получение KPI метрик"""
    async with get_db_session() as session:
        kpis = []
        
        # KPI: Общее количество пользователей
        total_users = await session.query(User).filter(User.is_deleted == False).count()
        yesterday = datetime.utcnow() - timedelta(days=1)
        users_yesterday = await session.query(User).filter(
            and_(
                User.is_deleted == False,
                User.created_at < yesterday
            )
        ).count()
        
        user_growth = ((total_users - users_yesterday) / max(users_yesterday, 1)) * 100
        
        kpis.append(KPISchema(
            name="Всего пользователей",
            value=total_users,
            previous_value=users_yesterday,
            change_percent=round(user_growth, 2),
            trend="up" if user_growth > 0 else "down" if user_growth < 0 else "stable",
            status="achieved",
            unit="чел",
            description="Общее количество зарегистрированных пользователей"
        ))
        
        # KPI: Конверсия в Premium
        premium_users = await session.query(User).filter(
            and_(User.is_deleted == False, User.is_premium == True)
        ).count()
        
        conversion_rate = (premium_users / max(total_users, 1)) * 100
        
        kpis.append(KPISchema(
            name="Конверсия в Premium",
            value=round(conversion_rate, 2),
            target=5.0,
            trend="up" if conversion_rate >= 5.0 else "down",
            status="achieved" if conversion_rate >= 5.0 else "at_risk",
            unit="%",
            description="Процент пользователей с Premium подпиской"
        ))
        
        # KPI: Успешность скачиваний
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        total_downloads_today = await session.query(DownloadTask).filter(
            DownloadTask.created_at >= today_start
        ).count()
        
        successful_downloads_today = await session.query(DownloadTask).filter(
            and_(
                DownloadTask.created_at >= today_start,
                DownloadTask.status == "completed"
            )
        ).count()
        
        success_rate = (successful_downloads_today / max(total_downloads_today, 1)) * 100
        
        kpis.append(KPISchema(
            name="Успешность скачиваний",
            value=round(success_rate, 2),
            target=95.0,
            trend="up" if success_rate >= 95.0 else "down",
            status="achieved" if success_rate >= 95.0 else "at_risk",
            unit="%",
            description="Процент успешных скачиваний за сегодня"
        ))
        
        return kpis

async def _get_charts_data() -> Dict[str, Any]:
    """Получение данных для графиков"""
    async with get_db_session() as session:
        # График регистраций за последние 30 дней
        user_registrations = []
        downloads_chart = []
        
        for i in range(30):
            day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=29-i)
            day_end = day_start + timedelta(days=1)
            
            # Регистрации
            registrations = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.created_at >= day_start,
                    User.created_at < day_end
                )
            ).count()
            
            user_registrations.append({
                "date": day_start.date().isoformat(),
                "value": registrations
            })
            
            # Скачивания
            downloads = await session.query(DownloadTask).filter(
                and_(
                    DownloadTask.created_at >= day_start,
                    DownloadTask.created_at < day_end
                )
            ).count()
            
            downloads_chart.append({
                "date": day_start.date().isoformat(),
                "value": downloads
            })
        
        return {
            "user_registrations": user_registrations,
            "downloads_trend": downloads_chart,
            "platform_distribution": await _get_platform_distribution(),
            "revenue_chart": await _get_revenue_chart()
        }

async def _get_platform_distribution() -> Dict[str, int]:
    """Распределение скачиваний по платформам"""
    async with get_db_session() as session:
        last_7_days = datetime.utcnow() - timedelta(days=7)
        
        platforms = await session.query(
            DownloadTask.platform,
            func.count(DownloadTask.id)
        ).filter(
            DownloadTask.created_at >= last_7_days
        ).group_by(DownloadTask.platform).all()
        
        return {platform: count for platform, count in platforms}

async def _get_revenue_chart() -> List[Dict[str, Any]]:
    """График доходов за последние 30 дней"""
    async with get_db_session() as session:
        revenue_data = []
        
        for i in range(30):
            day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=29-i)
            day_end = day_start + timedelta(days=1)
            
            daily_revenue = await session.query(
                func.sum(Payment.amount)
            ).filter(
                and_(
                    Payment.created_at >= day_start,
                    Payment.created_at < day_end,
                    Payment.status == "completed"
                )
            ).scalar() or 0
            
            revenue_data.append({
                "date": day_start.date().isoformat(),
                "value": float(daily_revenue)
            })
        
        return revenue_data

async def _get_recent_activity() -> List[Dict[str, Any]]:
    """Последняя активность в системе"""
    async with get_db_session() as session:
        recent_events = await session.query(AnalyticsEvent).order_by(
            desc(AnalyticsEvent.created_at)
        ).limit(10).all()
        
        activities = []
        for event in recent_events:
            activity = {
                "id": event.id,
                "type": event.event_type,
                "user_id": event.user_id,
                "timestamp": event.created_at.isoformat(),
                "description": _format_activity_description(event)
            }
            activities.append(activity)
        
        return activities

async def _get_system_alerts() -> List[Dict[str, Any]]:
    """Системные алерты и уведомления"""
    alerts = []
    
    async with get_db_session() as session:
        # Проверяем количество ошибок за последний час
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        error_count = await session.query(AnalyticsEvent).filter(
            and_(
                AnalyticsEvent.created_at >= hour_ago,
                AnalyticsEvent.event_type == "error_occurred"
            )
        ).count()
        
        if error_count > 50:  # Пороговое значение
            alerts.append({
                "type": "error",
                "title": "Высокая частота ошибок",
                "message": f"За последний час произошло {error_count} ошибок",
                "severity": "high",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Проверяем количество ожидающих задач
        pending_tasks = await session.query(DownloadTask).filter(
            DownloadTask.status == "pending"
        ).count()
        
        if pending_tasks > 100:  # Пороговое значение
            alerts.append({
                "type": "warning",
                "title": "Большая очередь задач",
                "message": f"В очереди {pending_tasks} задач на скачивание",
                "severity": "medium",
                "timestamp": datetime.utcnow().isoformat()
            })
    
    return alerts

async def _get_system_health_summary() -> Dict[str, Any]:
    """Сводка здоровья системы"""
    from shared.services import get_service_status
    
    service_status = get_service_status()
    
    # Определяем общий статус
    critical_services = ['database']
    all_critical_healthy = all(service_status.get(service, False) for service in critical_services)
    
    overall_status = "healthy" if all_critical_healthy else "unhealthy"
    
    return {
        "overall_status": overall_status,
        "database": "healthy" if service_status.get('database', False) else "unhealthy",
        "redis": "healthy" if service_status.get('redis', False) else "unhealthy",
        "analytics": "healthy" if service_status.get('analytics', False) else "unhealthy",
        "last_check": datetime.utcnow().isoformat()
    }

def _format_activity_description(event: AnalyticsEvent) -> str:
    """Форматирование описания активности"""
    descriptions = {
        "user_registered": "Новый пользователь зарегистрировался",
        "user_banned": "Пользователь заблокирован",
        "user_premium_purchased": "Пользователь купил Premium",
        "download_started": "Началось скачивание",
        "download_completed": "Скачивание завершено",
        "download_failed": "Скачивание не удалось",
        "payment_completed": "Платеж завершен",
        "error_occurred": "Произошла ошибка"
    }
    
    return descriptions.get(event.event_type, f"Событие: {event.event_type}")

async def _generate_report_file(report_data: Dict[str, Any], format: str, admin_id: int):
    """Генерация файла отчета в фоновом режиме"""
    try:
        if format == "csv":
            file_path = await export_analytics_to_csv(report_data)
        elif format == "excel":
            file_path = await export_analytics_to_excel(report_data)
        
        # TODO: Уведомить администратора о готовности файла
        logger.info(f"Report file generated", file_path=file_path, admin_id=admin_id)
        
    except Exception as e:
        logger.error(f"Error generating report file: {e}")

@router.get("/custom")
async def get_custom_analytics(
    query: AnalyticsQuerySchema = Depends(),
    current_admin = Depends(require_permission("analytics_view"))
):
    """
    Кастомная аналитика с гибкими параметрами
    """
    try:
        async with get_db_session() as session:
            # Базовый запрос к событиям аналитики
            base_query = session.query(AnalyticsEvent)
            
            # Применяем фильтры
            if query.date_from:
                base_query = base_query.filter(AnalyticsEvent.created_at >= query.date_from)
            
            if query.date_to:
                base_query = base_query.filter(AnalyticsEvent.created_at <= query.date_to)
            
            if query.event_type:
                base_query = base_query.filter(AnalyticsEvent.event_type == query.event_type)
            
            if query.event_category:
                base_query = base_query.filter(AnalyticsEvent.event_category == query.event_category)
            
            if query.user_id:
                base_query = base_query.filter(AnalyticsEvent.user_id == query.user_id)
            
            if query.platform:
                base_query = base_query.filter(AnalyticsEvent.platform == query.platform)
            
            if query.user_type:
                base_query = base_query.filter(AnalyticsEvent.user_type == query.user_type)
            
            # Группировка и агрегация
            if query.group_by == "date":
                results = await base_query.group_by(
                    func.date(AnalyticsEvent.created_at)
                ).with_entities(
                    func.date(AnalyticsEvent.created_at).label("group_key"),
                    func.count().label("count") if query.aggregation == "count" else func.sum(AnalyticsEvent.value).label("sum")
                ).limit(query.limit).all()
            
            elif query.group_by == "platform":
                results = await base_query.group_by(
                    AnalyticsEvent.platform
                ).with_entities(
                    AnalyticsEvent.platform.label("group_key"),
                    func.count().label("count") if query.aggregation == "count" else func.sum(AnalyticsEvent.value).label("sum")
                ).limit(query.limit).all()
            
            elif query.group_by == "event_type":
                results = await base_query.group_by(
                    AnalyticsEvent.event_type
                ).with_entities(
                    AnalyticsEvent.event_type.label("group_key"),
                    func.count().label("count") if query.aggregation == "count" else func.sum(AnalyticsEvent.value).label("sum")
                ).limit(query.limit).all()
            
            else:
                # Группировка по часам
                results = await base_query.group_by(
                    func.date_trunc('hour', AnalyticsEvent.created_at)
                ).with_entities(
                    func.date_trunc('hour', AnalyticsEvent.created_at).label("group_key"),
                    func.count().label("count") if query.aggregation == "count" else func.sum(AnalyticsEvent.value).label("sum")
                ).limit(query.limit).all()
            
            # Форматируем результаты
            formatted_results = []
            for result in results:
                group_key = result.group_key
                value = result.count if query.aggregation == "count" else result.sum
                
                # Форматируем ключ группировки
                if isinstance(group_key, datetime):
                    group_key = group_key.isoformat()
                elif hasattr(group_key, 'isoformat'):
                    group_key = group_key.isoformat()
                
                formatted_results.append({
                    "group": str(group_key) if group_key else "unknown",
                    "value": float(value) if value else 0
                })
            
            return {
                "results": formatted_results,
                "query_params": query.model_dump(),
                "total_results": len(formatted_results)
            }
            
    except Exception as e:
        logger.error(f"Error getting custom analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении кастомной аналитики"
        )