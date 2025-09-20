"""
VideoBot Pro - User Service
Сервис для работы с пользователями в админ панели
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import and_, or_, func, desc, text
from sqlalchemy.orm import AsyncSession
import structlog

from shared.models import User, DownloadTask, Payment, AnalyticsEvent
from shared.services.database import get_db_session
from shared.schemas.user import UserSchema, UserDetailedSchema

logger = structlog.get_logger(__name__)

class UserService:
    """Сервис для работы с пользователями"""
    
    def __init__(self):
        pass
    
    async def get_user_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Получить статистику пользователей"""
        try:
            date_from = datetime.utcnow() - timedelta(days=days)
            
            async with get_db_session() as session:
                # Основные метрики
                total_users = await session.query(User).filter(
                    User.is_deleted == False
                ).count()
                
                new_users = await session.query(User).filter(
                    and_(
                        User.is_deleted == False,
                        User.created_at >= date_from
                    )
                ).count()
                
                active_users = await session.query(User).filter(
                    and_(
                        User.is_deleted == False,
                        User.last_active_at >= date_from
                    )
                ).count()
                
                premium_users = await session.query(User).filter(
                    and_(
                        User.is_deleted == False,
                        User.is_premium == True
                    )
                ).count()
                
                banned_users = await session.query(User).filter(
                    and_(
                        User.is_deleted == False,
                        User.is_banned == True
                    )
                ).count()
                
                # Статистика по типам
                user_types = await session.query(
                    User.user_type,
                    func.count(User.id)
                ).filter(
                    User.is_deleted == False
                ).group_by(User.user_type).all()
                
                type_distribution = {user_type: count for user_type, count in user_types}
                
                # Конверсия в premium
                trial_users = await session.query(User).filter(
                    and_(
                        User.is_deleted == False,
                        User.trial_used == True
                    )
                ).count()
                
                conversion_rate = (premium_users / trial_users * 100) if trial_users > 0 else 0
                
                return {
                    "total_users": total_users,
                    "new_users": new_users,
                    "active_users": active_users,
                    "premium_users": premium_users,
                    "banned_users": banned_users,
                    "type_distribution": type_distribution,
                    "conversion_rate": round(conversion_rate, 2),
                    "period_days": days
                }
                
        except Exception as e:
            logger.error(f"Error getting user statistics: {e}")
            return {"error": str(e)}
    
    async def get_user_activity_timeline(self, user_id: int, days: int = 30) -> List[Dict[str, Any]]:
        """Получить временную шкалу активности пользователя"""
        try:
            date_from = datetime.utcnow() - timedelta(days=days)
            
            async with get_db_session() as session:
                # События аналитики
                events = await session.query(AnalyticsEvent).filter(
                    and_(
                        AnalyticsEvent.user_id == user_id,
                        AnalyticsEvent.created_at >= date_from
                    )
                ).order_by(desc(AnalyticsEvent.created_at)).limit(100).all()
                
                # Скачивания
                downloads = await session.query(DownloadTask).filter(
                    and_(
                        DownloadTask.user_id == user_id,
                        DownloadTask.created_at >= date_from
                    )
                ).order_by(desc(DownloadTask.created_at)).limit(50).all()
                
                # Платежи
                payments = await session.query(Payment).filter(
                    and_(
                        Payment.user_id == user_id,
                        Payment.created_at >= date_from
                    )
                ).order_by(desc(Payment.created_at)).limit(20).all()
                
                # Объединяем все события
                timeline = []
                
                for event in events:
                    timeline.append({
                        "type": "event",
                        "timestamp": event.created_at,
                        "event_type": event.event_type,
                        "description": self._format_event_description(event),
                        "data": event.event_data
                    })
                
                for download in downloads:
                    timeline.append({
                        "type": "download",
                        "timestamp": download.created_at,
                        "status": download.status,
                        "platform": download.platform,
                        "description": f"Скачивание с {download.platform}: {download.video_title or 'Unknown'}",
                        "url": download.original_url
                    })
                
                for payment in payments:
                    timeline.append({
                        "type": "payment",
                        "timestamp": payment.created_at,
                        "status": payment.status,
                        "amount": float(payment.amount),
                        "currency": payment.currency,
                        "description": f"Платеж {payment.amount} {payment.currency} - {payment.subscription_plan or 'Unknown'}"
                    })
                
                # Сортируем по времени
                timeline.sort(key=lambda x: x["timestamp"], reverse=True)
                
                return timeline[:100]  # Возвращаем последние 100 событий
                
        except Exception as e:
            logger.error(f"Error getting user activity timeline {user_id}: {e}")
            return []
    
    async def get_user_usage_stats(self, user_id: int) -> Dict[str, Any]:
        """Получить статистику использования пользователем"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                if not user:
                    return {"error": "User not found"}
                
                # Статистика скачиваний
                downloads_total = await session.query(DownloadTask).filter(
                    DownloadTask.user_id == user_id
                ).count()
                
                downloads_successful = await session.query(DownloadTask).filter(
                    and_(
                        DownloadTask.user_id == user_id,
                        DownloadTask.status == "completed"
                    )
                ).count()
                
                downloads_failed = await session.query(DownloadTask).filter(
                    and_(
                        DownloadTask.user_id == user_id,
                        DownloadTask.status == "failed"
                    )
                ).count()
                
                # Статистика по платформам
                platform_stats = await session.query(
                    DownloadTask.platform,
                    func.count(DownloadTask.id)
                ).filter(
                    DownloadTask.user_id == user_id
                ).group_by(DownloadTask.platform).all()
                
                platforms = {platform: count for platform, count in platform_stats}
                
                # Общий размер скачанных файлов
                total_size_query = await session.query(
                    func.sum(DownloadTask.file_size_bytes)
                ).filter(
                    and_(
                        DownloadTask.user_id == user_id,
                        DownloadTask.file_size_bytes.isnot(None)
                    )
                ).scalar()
                
                total_size_gb = (total_size_query or 0) / (1024**3)
                
                # Активность по дням недели
                daily_activity = await session.execute(text("""
                    SELECT 
                        EXTRACT(DOW FROM created_at) as day_of_week,
                        COUNT(*) as activity_count
                    FROM download_tasks 
                    WHERE user_id = :user_id
                    GROUP BY EXTRACT(DOW FROM created_at)
                    ORDER BY day_of_week
                """), {"user_id": user_id})
                
                daily_stats = {}
                for row in daily_activity.fetchall():
                    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
                    day_name = day_names[int(row.day_of_week)]
                    daily_stats[day_name] = row.activity_count
                
                # Статистика платежей
                payments_total = await session.query(Payment).filter(
                    Payment.user_id == user_id
                ).count()
                
                payments_amount = await session.query(
                    func.sum(Payment.amount)
                ).filter(
                    and_(
                        Payment.user_id == user_id,
                        Payment.status == "completed"
                    )
                ).scalar()
                
                return {
                    "downloads": {
                        "total": downloads_total,
                        "successful": downloads_successful,
                        "failed": downloads_failed,
                        "success_rate": (downloads_successful / downloads_total * 100) if downloads_total > 0 else 0
                    },
                    "platforms": platforms,
                    "total_size_gb": round(total_size_gb, 2),
                    "daily_activity": daily_stats,
                    "payments": {
                        "total_payments": payments_total,
                        "total_amount": float(payments_amount or 0)
                    },
                    "user_type": user.user_type,
                    "premium_active": user.is_premium,
                    "registration_date": user.created_at.isoformat() if user.created_at else None,
                    "last_active": user.last_active_at.isoformat() if user.last_active_at else None
                }
                
        except Exception as e:
            logger.error(f"Error getting user usage stats {user_id}: {e}")
            return {"error": str(e)}
    
    async def bulk_update_users(
        self, 
        user_ids: List[int], 
        updates: Dict[str, Any],
        admin_id: int
    ) -> Dict[str, Any]:
        """Массовое обновление пользователей"""
        try:
            async with get_db_session() as session:
                updated_count = 0
                errors = []
                
                for user_id in user_ids:
                    try:
                        user = await session.get(User, user_id)
                        if not user or user.is_deleted:
                            errors.append(f"User {user_id} not found")
                            continue
                        
                        # Применяем обновления
                        for field, value in updates.items():
                            if hasattr(user, field):
                                setattr(user, field, value)
                        
                        # Обновляем время модификации
                        user.updated_at = datetime.utcnow()
                        
                        updated_count += 1
                        
                    except Exception as e:
                        errors.append(f"Error updating user {user_id}: {str(e)}")
                
                await session.commit()
                
                logger.info(
                    f"Bulk user update completed",
                    updated_count=updated_count,
                    total_requested=len(user_ids),
                    admin_id=admin_id
                )
                
                return {
                    "success": True,
                    "updated_count": updated_count,
                    "total_requested": len(user_ids),
                    "errors": errors
                }
                
        except Exception as e:
            logger.error(f"Error in bulk user update: {e}")
            return {"success": False, "error": str(e)}
    
    async def search_users(
        self,
        query: str,
        search_type: str = "all",
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Поиск пользователей"""
        try:
            async with get_db_session() as session:
                base_query = session.query(User).filter(User.is_deleted == False)
                
                if search_type == "telegram_id":
                    # Поиск по Telegram ID
                    try:
                        telegram_id = int(query)
                        base_query = base_query.filter(User.telegram_id == telegram_id)
                    except ValueError:
                        return []
                        
                elif search_type == "username":
                    # Поиск по username
                    base_query = base_query.filter(
                        User.username.ilike(f"%{query}%")
                    )
                    
                elif search_type == "name":
                    # Поиск по имени
                    base_query = base_query.filter(
                        or_(
                            User.first_name.ilike(f"%{query}%"),
                            User.last_name.ilike(f"%{query}%")
                        )
                    )
                    
                else:
                    # Поиск по всем полям
                    search_filter = or_(
                        User.first_name.ilike(f"%{query}%"),
                        User.last_name.ilike(f"%{query}%"),
                        User.username.ilike(f"%{query}%")
                    )
                    
                    # Если query это число, ищем и по telegram_id
                    try:
                        telegram_id = int(query)
                        search_filter = or_(
                            search_filter,
                            User.telegram_id == telegram_id
                        )
                    except ValueError:
                        pass
                    
                    base_query = base_query.filter(search_filter)
                
                users = await base_query.limit(limit).all()
                
                # Форматируем результаты
                results = []
                for user in users:
                    results.append({
                        "id": user.id,
                        "telegram_id": user.telegram_id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "user_type": user.user_type,
                        "is_premium": user.is_premium,
                        "is_banned": user.is_banned,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                        "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Error searching users: {e}")
            return []
    
    async def get_user_recommendations(self, user_id: int) -> Dict[str, Any]:
        """Получить рекомендации по пользователю"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                if not user:
                    return {"error": "User not found"}
                
                recommendations = []
                warnings = []
                
                # Анализ активности
                if user.last_active_at:
                    days_inactive = (datetime.utcnow() - user.last_active_at).days
                    if days_inactive > 30:
                        warnings.append(f"Пользователь неактивен {days_inactive} дней")
                        if not user.is_premium:
                            recommendations.append("Отправить реактивационную кампанию")
                
                # Анализ скачиваний
                downloads_today = await session.query(DownloadTask).filter(
                    and_(
                        DownloadTask.user_id == user_id,
                        DownloadTask.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
                    )
                ).count()
                
                daily_limit = user.get_daily_limit()
                if downloads_today >= daily_limit * 0.8:
                    recommendations.append("Пользователь близок к лимиту - предложить Premium")
                
                # Анализ premium статуса
                if user.is_premium and user.premium_expires_at:
                    days_to_expire = (user.premium_expires_at - datetime.utcnow()).days
                    if days_to_expire <= 7:
                        recommendations.append("Premium истекает скоро - напомнить о продлении")
                    elif days_to_expire <= 3:
                        warnings.append("Premium истекает через 3 дня")
                
                # Анализ trial
                if not user.trial_used and not user.is_premium:
                    recommendations.append("Предложить trial период")
                
                # Анализ ошибок
                failed_downloads = await session.query(DownloadTask).filter(
                    and_(
                        DownloadTask.user_id == user_id,
                        DownloadTask.status == "failed",
                        DownloadTask.created_at >= datetime.utcnow() - timedelta(days=7)
                    )
                ).count()
                
                if failed_downloads > 5:
                    warnings.append(f"Много неудачных скачиваний за неделю: {failed_downloads}")
                    recommendations.append("Проверить технические проблемы пользователя")
                
                # Анализ платежей
                payment_attempts = await session.query(Payment).filter(
                    and_(
                        Payment.user_id == user_id,
                        Payment.status == "failed",
                        Payment.created_at >= datetime.utcnow() - timedelta(days=30)
                    )
                ).count()
                
                if payment_attempts > 2:
                    warnings.append("Множественные неудачные платежи")
                    recommendations.append("Предложить альтернативные способы оплаты")
                
                return {
                    "user_id": user_id,
                    "recommendations": recommendations,
                    "warnings": warnings,
                    "analysis_date": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting user recommendations {user_id}: {e}")
            return {"error": str(e)}
    
    async def calculate_user_value(self, user_id: int) -> Dict[str, Any]:
        """Вычислить ценность пользователя (LTV, активность и т.д.)"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                if not user:
                    return {"error": "User not found"}
                
                # Общая сумма платежей
                total_revenue = await session.query(
                    func.sum(Payment.amount)
                ).filter(
                    and_(
                        Payment.user_id == user_id,
                        Payment.status == "completed"
                    )
                ).scalar() or 0
                
                # Количество дней использования
                registration_date = user.created_at
                usage_days = (datetime.utcnow() - registration_date).days if registration_date else 0
                
                # Активность (скачивания)
                total_downloads = user.downloads_total or 0
                avg_downloads_per_day = total_downloads / max(usage_days, 1)
                
                # Последняя активность
                days_since_last_active = 0
                if user.last_active_at:
                    days_since_last_active = (datetime.utcnow() - user.last_active_at).days
                
                # Конверсия в premium
                has_premium = user.is_premium or user.trial_used
                
                # Расчет LTV (упрощенный)
                if user.is_premium:
                    # Premium пользователь
                    base_ltv = float(total_revenue) * 2  # Предполагаем что продлит еще раз
                elif has_premium:
                    # Бывший premium
                    base_ltv = float(total_revenue) * 1.5
                else:
                    # Никогда не был premium
                    base_ltv = 5.0  # Базовая ценность free пользователя
                
                # Корректировки LTV
                activity_multiplier = min(2.0, max(0.1, avg_downloads_per_day / 5))  # Норма 5 скачиваний в день
                recency_multiplier = max(0.1, 1 - (days_since_last_active / 365))  # Штраф за неактивность
                
                ltv = base_ltv * activity_multiplier * recency_multiplier
                
                # Категория пользователя
                if ltv > 50:
                    user_category = "high_value"
                elif ltv > 20:
                    user_category = "medium_value"
                elif ltv > 5:
                    user_category = "low_value"
                else:
                    user_category = "minimal_value"
                
                # Риск оттока
                churn_risk_factors = 0
                if days_since_last_active > 14:
                    churn_risk_factors += 1
                if not user.is_premium and user.trial_used:
                    churn_risk_factors += 1
                if avg_downloads_per_day < 0.5:
                    churn_risk_factors += 1
                
                churn_risk = ["low", "medium", "high", "critical"][min(churn_risk_factors, 3)]
                
                return {
                    "user_id": user_id,
                    "ltv": round(ltv, 2),
                    "total_revenue": float(total_revenue),
                    "user_category": user_category,
                    "usage_days": usage_days,
                    "avg_downloads_per_day": round(avg_downloads_per_day, 2),
                    "days_since_last_active": days_since_last_active,
                    "churn_risk": churn_risk,
                    "churn_risk_factors": churn_risk_factors,
                    "is_premium": user.is_premium,
                    "has_been_premium": has_premium
                }
                
        except Exception as e:
            logger.error(f"Error calculating user value {user_id}: {e}")
            return {"error": str(e)}
    
    async def get_user_cohort_analysis(self, cohort_period: str = "month") -> Dict[str, Any]:
        """Когортный анализ пользователей"""
        try:
            async with get_db_session() as session:
                # SQL запрос для когортного анализа
                if cohort_period == "month":
                    cohort_query = text("""
                        WITH user_cohorts AS (
                            SELECT 
                                user_id,
                                DATE_TRUNC('month', created_at) as cohort_month,
                                created_at
                            FROM users 
                            WHERE is_deleted = false
                        ),
                        activity_data AS (
                            SELECT 
                                uc.user_id,
                                uc.cohort_month,
                                DATE_TRUNC('month', dt.created_at) as activity_month,
                                COUNT(dt.id) as downloads
                            FROM user_cohorts uc
                            LEFT JOIN download_tasks dt ON uc.user_id = dt.user_id
                            GROUP BY uc.user_id, uc.cohort_month, DATE_TRUNC('month', dt.created_at)
                        )
                        SELECT 
                            cohort_month,
                            activity_month,
                            COUNT(DISTINCT user_id) as active_users,
                            SUM(downloads) as total_downloads
                        FROM activity_data
                        WHERE activity_month >= cohort_month
                        GROUP BY cohort_month, activity_month
                        ORDER BY cohort_month, activity_month
                    """)
                else:
                    # Недельные когорты
                    cohort_query = text("""
                        WITH user_cohorts AS (
                            SELECT 
                                user_id,
                                DATE_TRUNC('week', created_at) as cohort_week,
                                created_at
                            FROM users 
                            WHERE is_deleted = false
                        ),
                        activity_data AS (
                            SELECT 
                                uc.user_id,
                                uc.cohort_week,
                                DATE_TRUNC('week', dt.created_at) as activity_week,
                                COUNT(dt.id) as downloads
                            FROM user_cohorts uc
                            LEFT JOIN download_tasks dt ON uc.user_id = dt.user_id
                            GROUP BY uc.user_id, uc.cohort_week, DATE_TRUNC('week', dt.created_at)
                        )
                        SELECT 
                            cohort_week as cohort_month,
                            activity_week as activity_month,
                            COUNT(DISTINCT user_id) as active_users,
                            SUM(downloads) as total_downloads
                        FROM activity_data
                        WHERE activity_week >= cohort_week
                        GROUP BY cohort_week, activity_week
                        ORDER BY cohort_week, activity_week
                    """)
                
                result = await session.execute(cohort_query)
                cohort_data = result.fetchall()
                
                # Обрабатываем результаты
                cohorts = {}
                for row in cohort_data:
                    cohort_period_key = row.cohort_month.strftime('%Y-%m')
                    activity_period_key = row.activity_month.strftime('%Y-%m') if row.activity_month else None
                    
                    if cohort_period_key not in cohorts:
                        cohorts[cohort_period_key] = {
                            "cohort_period": cohort_period_key,
                            "periods": {},
                            "cohort_size": 0
                        }
                    
                    if activity_period_key:
                        period_number = self._calculate_period_number(row.cohort_month, row.activity_month, cohort_period)
                        cohorts[cohort_period_key]["periods"][period_number] = {
                            "active_users": row.active_users,
                            "total_downloads": row.total_downloads or 0,
                            "retention_rate": 0  # Будет вычислен позже
                        }
                        
                        # Размер когорты (период 0)
                        if period_number == 0:
                            cohorts[cohort_period_key]["cohort_size"] = row.active_users
                
                # Вычисляем retention rates
                for cohort_key, cohort_data in cohorts.items():
                    cohort_size = cohort_data["cohort_size"]
                    for period_num, period_data in cohort_data["periods"].items():
                        if cohort_size > 0:
                            retention_rate = period_data["active_users"] / cohort_size * 100
                            period_data["retention_rate"] = round(retention_rate, 2)
                
                return {
                    "cohort_period": cohort_period,
                    "cohorts": list(cohorts.values()),
                    "analysis_date": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error in cohort analysis: {e}")
            return {"error": str(e)}
    
    def _format_event_description(self, event: AnalyticsEvent) -> str:
        """Форматировать описание события"""
        descriptions = {
            "user_registered": "Пользователь зарегистрировался",
            "user_premium_purchased": "Приобрел Premium подписку",
            "download_started": "Начал скачивание",
            "download_completed": "Завершил скачивание",
            "download_failed": "Ошибка скачивания",
            "trial_started": "Запустил trial период",
            "user_banned": "Пользователь заблокирован",
            "user_unbanned": "Пользователь разблокирован"
        }
        
        return descriptions.get(event.event_type, f"Событие: {event.event_type}")
    
    def _calculate_period_number(self, cohort_date, activity_date, period_type: str) -> int:
        """Вычислить номер периода для когортного анализа"""
        if period_type == "month":
            return (activity_date.year - cohort_date.year) * 12 + (activity_date.month - cohort_date.month)
        else:  # week
            return (activity_date - cohort_date).days // 7
    
    async def export_user_data(self, user_id: int) -> Dict[str, Any]:
        """Экспорт всех данных пользователя (GDPR compliance)"""
        try:
            async with get_db_session() as session:
                user = await session.get(User, user_id)
                if not user:
                    return {"error": "User not found"}
                
                # Основные данные пользователя
                user_data = {
                    "user_info": {
                        "id": user.id,
                        "telegram_id": user.telegram_id,
                        "username": user.username,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "language_code": user.language_code,
                        "country_code": user.country_code,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                        "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None
                    }
                }
                
                # Скачивания
                downloads = await session.query(DownloadTask).filter(
                    DownloadTask.user_id == user_id
                ).all()
                
                user_data["downloads"] = [
                    {
                        "id": d.id,
                        "original_url": d.original_url,
                        "platform": d.platform,
                        "video_title": d.video_title,
                        "status": d.status,
                        "created_at": d.created_at.isoformat() if d.created_at else None,
                        "file_size_bytes": d.file_size_bytes
                    }
                    for d in downloads
                ]
                
                # Платежи
                payments = await session.query(Payment).filter(
                    Payment.user_id == user_id
                ).all()
                
                user_data["payments"] = [
                    {
                        "id": p.id,
                        "amount": float(p.amount),
                        "currency": p.currency,
                        "status": p.status,
                        "subscription_plan": p.subscription_plan,
                        "created_at": p.created_at.isoformat() if p.created_at else None
                    }
                    for p in payments
                ]
                
                # События аналитики
                events = await session.query(AnalyticsEvent).filter(
                    AnalyticsEvent.user_id == user_id
                ).limit(1000).all()  # Последние 1000 событий
                
                user_data["analytics_events"] = [
                    {
                        "event_type": e.event_type,
                        "created_at": e.created_at.isoformat() if e.created_at else None,
                        "event_data": e.event_data
                    }
                    for e in events
                ]
                
                user_data["export_info"] = {
                    "exported_at": datetime.utcnow().isoformat(),
                    "export_version": "1.0",
                    "total_downloads": len(user_data["downloads"]),
                    "total_payments": len(user_data["payments"]),
                    "total_events": len(user_data["analytics_events"])
                }
                
                return user_data
                
        except Exception as e:
            logger.error(f"Error exporting user data {user_id}: {e}")
            return {"error": str(e)}