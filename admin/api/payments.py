"""
VideoBot Pro - Admin Payments API
API для управления платежами и Premium подписками
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, func, desc, asc, text
from sqlalchemy.orm import AsyncSession
import structlog
import io
import csv

from shared.config.database import get_async_session
from shared.models import (
    Payment, User, PaymentStatus, PaymentMethod, SubscriptionPlan, 
    Currency, AnalyticsEvent, EventType
)
from shared.schemas.admin import ResponseSchema, PaginationSchema
from shared.utils.helpers import format_date, format_currency, format_relative_time
from ..config import get_admin_settings
from ..dependencies import get_current_admin, require_permission, get_pagination

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

@router.get("/", response_model=ResponseSchema)
async def get_payments(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin),
    pagination = Depends(get_pagination),
    # Фильтры
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    payment_method: Optional[str] = Query(None, description="Фильтр по методу платежа"),
    currency: Optional[str] = Query(None, description="Фильтр по валюте"),
    subscription_plan: Optional[str] = Query(None, description="Фильтр по плану"),
    user_id: Optional[int] = Query(None, description="Фильтр по пользователю"),
    amount_from: Optional[float] = Query(None, description="Минимальная сумма"),
    amount_to: Optional[float] = Query(None, description="Максимальная сумма"),
    date_from: Optional[datetime] = Query(None, description="Дата начала"),
    date_to: Optional[datetime] = Query(None, description="Дата окончания"),
    search: Optional[str] = Query(None, description="Поиск по ID платежа"),
    sort_by: str = Query("created_at", description="Поле сортировки"),
    sort_order: str = Query("desc", description="Порядок сортировки")
):
    """Получить список платежей с фильтрацией"""
    try:
        # Базовый запрос с джойном к пользователям
        query = session.query(Payment).join(User, Payment.user_id == User.id)
        
        # Применяем фильтры
        if status:
            query = query.filter(Payment.status == status)
        
        if payment_method:
            query = query.filter(Payment.payment_method == payment_method)
        
        if currency:
            query = query.filter(Payment.currency == currency)
        
        if subscription_plan:
            query = query.filter(Payment.subscription_plan == subscription_plan)
        
        if user_id:
            query = query.filter(Payment.user_id == user_id)
        
        if amount_from:
            query = query.filter(Payment.amount >= amount_from)
        
        if amount_to:
            query = query.filter(Payment.amount <= amount_to)
        
        if date_from:
            query = query.filter(Payment.created_at >= date_from)
        
        if date_to:
            query = query.filter(Payment.created_at <= date_to)
        
        if search:
            query = query.filter(
                or_(
                    Payment.payment_id.ilike(f"%{search}%"),
                    Payment.external_payment_id.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%")
                )
            )
        
        # Сортировка
        if sort_by == "user":
            sort_column = User.username
        elif sort_by == "amount":
            sort_column = Payment.amount
        else:
            sort_column = getattr(Payment, sort_by, Payment.created_at)
        
        if sort_order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Подсчёт общего количества
        total = await query.count()
        
        # Применяем пагинацию
        offset = (pagination.page - 1) * pagination.per_page
        payments = await query.offset(offset).limit(pagination.per_page).all()
        
        # Формируем данные платежей
        payments_data = []
        for payment in payments:
            payment_dict = payment.to_dict_admin()
            
            # Добавляем информацию о пользователе
            user = await session.query(User).filter(User.id == payment.user_id).first()
            if user:
                payment_dict['user'] = {
                    "id": user.id,
                    "telegram_id": user.telegram_id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "user_type": user.user_type
                }
            
            payments_data.append(payment_dict)
        
        # Формируем пагинацию
        pages = (total + pagination.per_page - 1) // pagination.per_page
        pagination_data = PaginationSchema(
            page=pagination.page,
            per_page=pagination.per_page,
            total=total,
            pages=pages,
            has_prev=pagination.page > 1,
            has_next=pagination.page < pages
        )
        
        return ResponseSchema(
            success=True,
            data={
                "payments": payments_data,
                "pagination": pagination_data.dict()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get payments: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения платежей")

@router.get("/{payment_id}", response_model=ResponseSchema)
async def get_payment(
    payment_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin)
):
    """Получить детальную информацию о платеже"""
    try:
        payment = await session.query(Payment).filter(
            Payment.id == payment_id
        ).first()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Платёж не найден")
        
        # Получаем полную информацию
        payment_data = payment.to_dict_admin()
        
        # Добавляем информацию о пользователе
        user = await session.query(User).filter(User.id == payment.user_id).first()
        if user:
            payment_data['user'] = user.to_dict_safe()
        
        # История платежей пользователя
        user_payments = await session.query(Payment).filter(
            Payment.user_id == payment.user_id,
            Payment.id != payment.id
        ).order_by(desc(Payment.created_at)).limit(5).all()
        
        payment_data['user_payment_history'] = [
            {
                "id": p.id,
                "payment_id": p.payment_id,
                "amount": float(p.amount),
                "currency": p.currency,
                "status": p.status,
                "created_at": format_date(p.created_at)
            }
            for p in user_payments
        ]
        
        # Связанные события аналитики
        analytics_events = await session.query(AnalyticsEvent).filter(
            AnalyticsEvent.payment_id == payment.id
        ).order_by(desc(AnalyticsEvent.created_at)).all()
        
        payment_data['analytics_events'] = [
            {
                "event_type": event.event_type,
                "created_at": format_date(event.created_at),
                "event_data": event.event_data
            }
            for event in analytics_events
        ]
        
        return ResponseSchema(
            success=True,
            data=payment_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get payment {payment_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения платежа")

@router.post("/{payment_id}/refund", response_model=ResponseSchema)
async def refund_payment(
    payment_id: int,
    refund_amount: Optional[Decimal] = None,
    reason: str = "Admin refund",
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("finance_manage")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Вернуть платёж"""
    try:
        payment = await session.query(Payment).filter(
            Payment.id == payment_id
        ).first()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Платёж не найден")
        
        if payment.status != PaymentStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail="Можно вернуть только завершённые платежи"
            )
        
        if payment.is_refunded:
            raise HTTPException(
                status_code=400,
                detail="Платёж уже возвращён"
            )
        
        # Определяем сумму возврата
        if refund_amount is None:
            refund_amount = payment.amount
        elif refund_amount > payment.amount:
            raise HTTPException(
                status_code=400,
                detail="Сумма возврата не может превышать сумму платежа"
            )
        
        # Обрабатываем возврат
        payment.process_refund(refund_amount, reason)
        
        # Если полный возврат Premium подписки, отключаем её
        if refund_amount >= payment.amount and payment.subscription_plan:
            user = await session.query(User).filter(User.id == payment.user_id).first()
            if user and user.is_premium:
                user.deactivate_premium()
                background_tasks.add_task(
                    notify_user_premium_cancelled, 
                    user.telegram_id,
                    "Подписка отменена в связи с возвратом платежа"
                )
        
        await session.commit()
        
        # Запускаем обработку возврата в платёжной системе
        background_tasks.add_task(process_payment_refund, payment_id, refund_amount)
        
        logger.info(
            f"Payment refund initiated",
            payment_id=payment_id,
            admin_id=current_admin['admin_id'],
            refund_amount=float(refund_amount),
            reason=reason
        )
        
        return ResponseSchema(
            success=True,
            message="Возврат обработан",
            data={
                "refund_amount": float(refund_amount),
                "new_status": payment.status
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refund payment {payment_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обработки возврата")

@router.post("/{payment_id}/mark-completed", response_model=ResponseSchema)
async def mark_payment_completed(
    payment_id: int,
    external_payment_id: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("finance_manage")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Вручную пометить платёж как завершённый"""
    try:
        payment = await session.query(Payment).filter(
            Payment.id == payment_id
        ).first()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Платёж не найден")
        
        if payment.status not in [PaymentStatus.PENDING, PaymentStatus.PROCESSING]:
            raise HTTPException(
                status_code=400,
                detail=f"Нельзя завершить платёж со статусом {payment.status}"
            )
        
        # Завершаем платёж
        payment.complete_payment(external_payment_id=external_payment_id)
        
        # Активируем Premium подписку
        user = await session.query(User).filter(User.id == payment.user_id).first()
        if user and payment.subscription_plan:
            duration_days = payment.subscription_duration_days
            user.activate_premium(duration_days)
            
            background_tasks.add_task(
                notify_user_premium_activated,
                user.telegram_id,
                payment.subscription_plan,
                duration_days
            )
        
        await session.commit()
        
        logger.info(
            f"Payment manually completed",
            payment_id=payment_id,
            admin_id=current_admin['admin_id'],
            external_payment_id=external_payment_id
        )
        
        return ResponseSchema(
            success=True,
            message="Платёж помечен как завершённый",
            data=payment.to_dict_admin()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark payment completed {payment_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка завершения платежа")

@router.post("/{payment_id}/mark-failed", response_model=ResponseSchema)
async def mark_payment_failed(
    payment_id: int,
    reason: str = "Admin action",
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("finance_manage"))
):
    """Вручную пометить платёж как неудачный"""
    try:
        payment = await session.query(Payment).filter(
            Payment.id == payment_id
        ).first()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Платёж не найден")
        
        if payment.status not in [PaymentStatus.PENDING, PaymentStatus.PROCESSING]:
            raise HTTPException(
                status_code=400,
                detail=f"Нельзя отменить платёж со статусом {payment.status}"
            )
        
        # Помечаем как неудачный
        payment.fail_payment(reason)
        await session.commit()
        
        logger.info(
            f"Payment manually failed",
            payment_id=payment_id,
            admin_id=current_admin['admin_id'],
            reason=reason
        )
        
        return ResponseSchema(
            success=True,
            message="Платёж помечен как неудачный"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to mark payment failed {payment_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка отмены платежа")

@router.post("/grant-premium", response_model=ResponseSchema)
async def grant_premium_manually(
    user_id: int,
    duration_days: int,
    reason: str = "Admin grant",
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("finance_manage")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Вручную выдать Premium подписку"""
    try:
        user = await session.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        
        # Создаём "платёж" для отслеживания
        payment = Payment.create_payment(
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            amount=Decimal('0.00'),
            subscription_plan=SubscriptionPlan.MONTHLY if duration_days <= 31 else SubscriptionPlan.YEARLY,
            payment_method=PaymentMethod.ADMIN_GRANT,
            currency=Currency.USD
        )
        
        payment.subscription_duration_days = duration_days
        payment.complete_payment()
        payment.notes = f"Manual grant by admin: {reason}"
        
        session.add(payment)
        
        # Активируем Premium
        user.activate_premium(duration_days)
        
        await session.commit()
        
        # Уведомляем пользователя
        background_tasks.add_task(
            notify_user_premium_activated,
            user.telegram_id,
            f"admin_grant_{duration_days}d",
            duration_days
        )
        
        logger.info(
            f"Premium manually granted",
            user_id=user_id,
            admin_id=current_admin['admin_id'],
            duration_days=duration_days,
            reason=reason
        )
        
        return ResponseSchema(
            success=True,
            message=f"Premium на {duration_days} дней выдан пользователю",
            data={
                "user_id": user_id,
                "duration_days": duration_days,
                "expires_at": user.premium_expires_at.isoformat(),
                "payment_id": payment.id
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to grant premium to user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка выдачи Premium")

@router.get("/stats/overview", response_model=ResponseSchema)
async def get_payments_overview(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("finance_view")),
    days: int = Query(30, description="Количество дней для статистики")
):
    """Получить общую статистику платежей"""
    try:
        date_from = datetime.utcnow() - timedelta(days=days)
        
        # Основные метрики
        total_payments = await session.query(Payment).count()
        
        period_payments = await session.query(Payment).filter(
            Payment.created_at >= date_from
        ).count()
        
        # Статистика по статусам
        status_stats = {}
        for status in PaymentStatus.ALL:
            count = await session.query(Payment).filter(
                Payment.status == status
            ).count()
            status_stats[status] = count
        
        # Финансовая статистика
        revenue_query = session.query(
            func.sum(Payment.amount).label('total_revenue'),
            func.sum(Payment.net_amount).label('total_net'),
            func.sum(Payment.fee_amount).label('total_fees'),
            func.count(Payment.id).label('completed_count')
        ).filter(
            Payment.status == PaymentStatus.COMPLETED,
            Payment.created_at >= date_from
        )
        
        revenue_stats = await revenue_query.first()
        
        # Статистика по методам платежа
        payment_methods_query = session.query(
            Payment.payment_method,
            func.count(Payment.id).label('count'),
            func.sum(Payment.amount).label('total_amount')
        ).filter(
            Payment.status == PaymentStatus.COMPLETED,
            Payment.created_at >= date_from
        ).group_by(Payment.payment_method)
        
        payment_methods_result = await payment_methods_query.all()
        payment_methods_stats = {
            method.payment_method: {
                "count": method.count,
                "total_amount": float(method.total_amount or 0)
            }
            for method in payment_methods_result
        }
        
        # Статистика по планам подписки
        plans_query = session.query(
            Payment.subscription_plan,
            func.count(Payment.id).label('count'),
            func.sum(Payment.amount).label('total_amount')
        ).filter(
            Payment.status == PaymentStatus.COMPLETED,
            Payment.created_at >= date_from
        ).group_by(Payment.subscription_plan)
        
        plans_result = await plans_query.all()
        plans_stats = {
            plan.subscription_plan: {
                "count": plan.count,
                "total_amount": float(plan.total_amount or 0)
            }
            for plan in plans_result
        }
        
        # Динамика по дням
        daily_stats_query = text("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as payments_count,
                SUM(amount) as revenue,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_payments
            FROM payments
            WHERE created_at >= :date_from
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
        """)
        
        daily_stats_result = await session.execute(daily_stats_query, {"date_from": date_from})
        daily_stats = [
            {
                "date": row.date.isoformat(),
                "payments_count": row.payments_count,
                "revenue": float(row.revenue or 0),
                "successful_payments": row.successful_payments
            }
            for row in daily_stats_result.fetchall()
        ]
        
        # Топ пользователей по суммам платежей
        top_payers_query = session.query(
            Payment.user_id,
            User.username,
            User.telegram_id,
            func.sum(Payment.amount).label('total_spent'),
            func.count(Payment.id).label('payments_count')
        ).join(User, Payment.user_id == User.id).filter(
            Payment.status == PaymentStatus.COMPLETED,
            Payment.created_at >= date_from
        ).group_by(
            Payment.user_id, User.username, User.telegram_id
        ).order_by(
            desc('total_spent')
        ).limit(10)
        
        top_payers_result = await top_payers_query.all()
        top_payers = [
            {
                "user_id": payer.user_id,
                "username": payer.username,
                "telegram_id": payer.telegram_id,
                "total_spent": float(payer.total_spent),
                "payments_count": payer.payments_count
            }
            for payer in top_payers_result
        ]
        
        # Недавние платежи
        recent_payments = await session.query(Payment).order_by(
            desc(Payment.created_at)
        ).limit(10).all()
        
        recent_payments_data = []
        for payment in recent_payments:
            user = await session.query(User).filter(User.id == payment.user_id).first()
            recent_payments_data.append({
                "id": payment.id,
                "payment_id": payment.payment_id,
                "amount": float(payment.amount),
                "currency": payment.currency,
                "status": payment.status,
                "payment_method": payment.payment_method,
                "user": {
                    "username": user.username if user else None,
                    "telegram_id": payment.telegram_user_id
                },
                "created_at": format_date(payment.created_at)
            })
        
        # Общая статистика за всё время
        lifetime_stats_query = session.query(
            func.sum(Payment.amount).label('lifetime_revenue'),
            func.count(Payment.id).label('total_payments'),
            func.count(func.distinct(Payment.user_id)).label('paying_users')
        ).filter(Payment.status == PaymentStatus.COMPLETED)
        
        lifetime_stats = await lifetime_stats_query.first()
        
        return ResponseSchema(
            success=True,
            data={
                "overview": {
                    "total_payments": total_payments,
                    "period_payments": period_payments,
                    "period_days": days,
                    "lifetime_revenue": float(lifetime_stats.lifetime_revenue or 0),
                    "total_payments_count": lifetime_stats.total_payments or 0,
                    "paying_users": lifetime_stats.paying_users or 0
                },
                "status_stats": status_stats,
                "period_revenue": {
                    "total_revenue": float(revenue_stats.total_revenue or 0),
                    "total_net": float(revenue_stats.total_net or 0),
                    "total_fees": float(revenue_stats.total_fees or 0),
                    "completed_payments": revenue_stats.completed_count or 0,
                    "success_rate": round(
                        (revenue_stats.completed_count or 0) / max(period_payments, 1) * 100, 2
                    )
                },
                "payment_methods": payment_methods_stats,
                "subscription_plans": plans_stats,
                "daily_stats": daily_stats,
                "top_payers": top_payers,
                "recent_payments": recent_payments_data
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get payments overview: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения обзора платежей")

@router.get("/export", response_model=None)
async def export_payments(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("finance_view")),
    format: str = Query("csv", description="Формат экспорта: csv, xlsx"),
    date_from: Optional[datetime] = Query(None, description="Дата начала"),
    date_to: Optional[datetime] = Query(None, description="Дата окончания"),
    status: Optional[str] = Query(None, description="Фильтр по статусу")
):
    """Экспорт платежей в CSV/Excel"""
    try:
        # Формируем запрос
        query = session.query(Payment).join(User, Payment.user_id == User.id)
        
        if date_from:
            query = query.filter(Payment.created_at >= date_from)
        
        if date_to:
            query = query.filter(Payment.created_at <= date_to)
        
        if status:
            query = query.filter(Payment.status == status)
        
        # Ограничиваем количество записей
        payments = await query.order_by(desc(Payment.created_at)).limit(10000).all()
        
        if format.lower() == "csv":
            return await export_payments_csv(payments, session)
        elif format.lower() == "xlsx":
            return await export_payments_xlsx(payments, session)
        else:
            raise HTTPException(status_code=400, detail="Неподдерживаемый формат")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export payments: {e}")
        raise HTTPException(status_code=500, detail="Ошибка экспорта платежей")

@router.get("/fraud-detection", response_model=ResponseSchema)
async def get_fraud_detection(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("finance_manage")),
    days: int = Query(7, description="Количество дней для анализа")
):
    """Анализ подозрительных платежей"""
    try:
        date_from = datetime.utcnow() - timedelta(days=days)
        
        # Подозрительные платежи
        suspicious_payments = await session.query(Payment).filter(
            and_(
                Payment.created_at >= date_from,
                or_(
                    Payment.is_suspicious == True,
                    Payment.risk_score > 70,
                    and_(
                        Payment.status == PaymentStatus.FAILED,
                        Payment.retry_count > 3
                    )
                )
            )
        ).order_by(desc(Payment.risk_score)).all()
        
        # Множественные платежи от одного IP
        duplicate_ip_query = text("""
            SELECT 
                client_ip,
                COUNT(*) as payments_count,
                COUNT(DISTINCT user_id) as unique_users,
                SUM(amount) as total_amount
            FROM payments
            WHERE created_at >= :date_from 
            AND client_ip IS NOT NULL
            GROUP BY client_ip
            HAVING COUNT(*) > 5 OR COUNT(DISTINCT user_id) > 3
            ORDER BY payments_count DESC
        """)
        
        duplicate_ip_result = await session.execute(duplicate_ip_query, {"date_from": date_from})
        duplicate_ips = [
            {
                "ip": row.client_ip,
                "payments_count": row.payments_count,
                "unique_users": row.unique_users,
                "total_amount": float(row.total_amount)
            }
            for row in duplicate_ip_result.fetchall()
        ]
        
        # Быстрые повторные платежи
        rapid_payments_query = text("""
            SELECT 
                p1.user_id,
                u.username,
                COUNT(*) as rapid_payments
            FROM payments p1
            JOIN payments p2 ON p1.user_id = p2.user_id 
                AND p2.created_at BETWEEN p1.created_at AND p1.created_at + INTERVAL '10 minutes'
                AND p1.id != p2.id
            JOIN users u ON p1.user_id = u.id
            WHERE p1.created_at >= :date_from
            GROUP BY p1.user_id, u.username
            HAVING COUNT(*) > 2
            ORDER BY rapid_payments DESC
        """)
        
        rapid_payments_result = await session.execute(rapid_payments_query, {"date_from": date_from})
        rapid_payments = [
            {
                "user_id": row.user_id,
                "username": row.username,
                "rapid_payments": row.rapid_payments
            }
            for row in rapid_payments_result.fetchall()
        ]
        
        # Статистика fraud detection
        fraud_stats = {
            "suspicious_payments": len(suspicious_payments),
            "duplicate_ips": len(duplicate_ips),
            "rapid_payment_users": len(rapid_payments),
            "high_risk_payments": len([p for p in suspicious_payments if p.risk_score and p.risk_score > 80])
        }
        
        suspicious_payments_data = [
            {
                "id": payment.id,
                "payment_id": payment.payment_id,
                "amount": float(payment.amount),
                "risk_score": payment.risk_score,
                "is_suspicious": payment.is_suspicious,
                "client_ip": payment.client_ip,
                "status": payment.status,
                "created_at": format_date(payment.created_at)
            }
            for payment in suspicious_payments[:20]  # Топ 20
        ]
        
        return ResponseSchema(
            success=True,
            data={
                "fraud_stats": fraud_stats,
                "suspicious_payments": suspicious_payments_data,
                "duplicate_ips": duplicate_ips[:10],
                "rapid_payments": rapid_payments[:10],
                "period_days": days
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get fraud detection: {e}")
        raise HTTPException(status_code=500, detail="Ошибка анализа мошенничества")

# Вспомогательные функции

async def export_payments_csv(payments: List[Payment], session: AsyncSession) -> StreamingResponse:
    """Экспорт платежей в CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовки
    headers = [
        "ID", "Payment ID", "User ID", "Username", "Amount", "Currency",
        "Status", "Payment Method", "Subscription Plan", "Created At",
        "Completed At", "External ID", "Country", "Risk Score"
    ]
    writer.writerow(headers)
    
    # Данные
    for payment in payments:
        user = await session.query(User).filter(User.id == payment.user_id).first()
        
        row = [
            payment.id,
            payment.payment_id,
            payment.user_id,
            user.username if user else "",
            float(payment.amount),
            payment.currency,
            payment.status,
            payment.payment_method,
            payment.subscription_plan,
            payment.created_at.isoformat(),
            payment.completed_at.isoformat() if payment.completed_at else "",
            payment.external_payment_id or "",
            payment.country_code or "",
            payment.risk_score or ""
        ]
        writer.writerow(row)
    
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=payments_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

async def export_payments_xlsx(payments: List[Payment], session: AsyncSession) -> StreamingResponse:
    """Экспорт платежей в Excel"""
    try:
        import pandas as pd
        
        # Подготавливаем данные
        data = []
        for payment in payments:
            user = await session.query(User).filter(User.id == payment.user_id).first()
            
            data.append({
                "ID": payment.id,
                "Payment ID": payment.payment_id,
                "User ID": payment.user_id,
                "Username": user.username if user else "",
                "Amount": float(payment.amount),
                "Currency": payment.currency,
                "Status": payment.status,
                "Payment Method": payment.payment_method,
                "Subscription Plan": payment.subscription_plan,
                "Created At": payment.created_at,
                "Completed At": payment.completed_at,
                "External ID": payment.external_payment_id or "",
                "Country": payment.country_code or "",
                "Risk Score": payment.risk_score or ""
            })
        
        # Создаём DataFrame и Excel файл
        df = pd.DataFrame(data)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Payments', index=False)
        
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=payments_{datetime.now().strftime('%Y%m%d')}.xlsx"}
        )
        
    except ImportError:
        # Если pandas не установлен, используем CSV
        return await export_payments_csv(payments, session)

async def process_payment_refund(payment_id: int, refund_amount: Decimal):
    """Фоновая задача обработки возврата в платёжной системе"""
    try:
        # Здесь должна быть логика обращения к API платёжной системы
        # Например, Stripe, PayPal и т.д.
        
        logger.info(f"Processing refund for payment {payment_id}, amount: {refund_amount}")
        
        # Симуляция обработки
        import asyncio
        await asyncio.sleep(2)
        
        # Здесь обновили бы статус возврата в БД после ответа от платёжной системы
        
    except Exception as e:
        logger.error(f"Failed to process refund for payment {payment_id}: {e}")

async def notify_user_premium_activated(telegram_id: int, plan: str, duration_days: int):
    """Уведомление пользователя об активации Premium"""
    try:
        # Здесь должна быть отправка уведомления через бот
        logger.info(
            f"Premium activated notification sent",
            telegram_id=telegram_id,
            plan=plan,
            duration_days=duration_days
        )
        
    except Exception as e:
        logger.error(f"Failed to notify user {telegram_id} about premium activation: {e}")

async def notify_user_premium_cancelled(telegram_id: int, reason: str):
    """Уведомление пользователя об отмене Premium"""
    try:
        # Здесь должна быть отправка уведомления через бот
        logger.info(
            f"Premium cancelled notification sent",
            telegram_id=telegram_id,
            reason=reason
        )
        
    except Exception as e:
        logger.error(f"Failed to notify user {telegram_id} about premium cancellation: {e}")