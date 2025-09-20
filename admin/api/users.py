"""
VideoBot Pro - Users Management API
API endpoints для управления пользователями
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import func, and_, or_, desc, asc
from sqlalchemy.orm import selectinload
import structlog

from shared.schemas.user import (
    UserSchema, UserDetailedSchema, UserSearchSchema, UserBanSchema,
    UserPremiumSchema, UserTrialSchema, UserListSchema
)
from shared.schemas.base import PaginationSchema
from shared.models import User, DownloadTask, Payment, AnalyticsEvent
from shared.services.database import get_db_session
from shared.services.analytics import AnalyticsService
from ..dependencies import get_current_admin, require_permission, get_analytics_service
from ..services.user_service import UserService
from ..utils.export import export_users_to_csv, export_users_to_excel

logger = structlog.get_logger(__name__)
router = APIRouter()

@router.get("/", response_model=UserListSchema)
async def get_users(
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Пользователей на странице"),
    search: Optional[str] = Query(None, description="Поиск по имени или username"),
    user_type: Optional[str] = Query(None, description="Фильтр по типу пользователя"),
    is_banned: Optional[bool] = Query(None, description="Фильтр по статусу блокировки"),
    is_premium: Optional[bool] = Query(None, description="Фильтр по Premium статусу"),
    registration_from: Optional[datetime] = Query(None, description="Зарегистрирован после"),
    registration_to: Optional[datetime] = Query(None, description="Зарегистрирован до"),
    last_active_from: Optional[datetime] = Query(None, description="Активен после"),
    last_active_to: Optional[datetime] = Query(None, description="Активен до"),
    sort_by: str = Query("created_at", description="Поле сортировки"),
    sort_order: str = Query("desc", description="Порядок сортировки"),
    current_admin = Depends(require_permission("user_view"))
):
    """
    Получение списка пользователей с фильтрацией и пагинацией
    """
    try:
        async with get_db_session() as session:
            # Базовый запрос
            query = session.query(User).filter(User.is_deleted == False)
            
            # Применяем фильтры
            if search:
                search_filter = or_(
                    User.first_name.ilike(f"%{search}%"),
                    User.last_name.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%"),
                    User.telegram_id.cast(str).ilike(f"%{search}%")
                )
                query = query.filter(search_filter)
            
            if user_type:
                query = query.filter(User.user_type == user_type)
            
            if is_banned is not None:
                query = query.filter(User.is_banned == is_banned)
            
            if is_premium is not None:
                query = query.filter(User.is_premium == is_premium)
            
            if registration_from:
                query = query.filter(User.created_at >= registration_from)
            
            if registration_to:
                query = query.filter(User.created_at <= registration_to)
            
            if last_active_from:
                query = query.filter(User.last_active_at >= last_active_from)
            
            if last_active_to:
                query = query.filter(User.last_active_at <= last_active_to)
            
            # Сортировка
            sort_column = getattr(User, sort_by, User.created_at)
            if sort_order == "desc":
                query = query.order_by(desc(sort_column))
            else:
                query = query.order_by(asc(sort_column))
            
            # Подсчет общего количества
            total = await query.count()
            
            # Пагинация
            offset = (page - 1) * per_page
            users = await query.offset(offset).limit(per_page).all()
            
            # Вычисляем дополнительные поля для каждого пользователя
            users_data = []
            for user in users:
                user_dict = user.to_dict_safe()
                
                # Добавляем вычисляемые поля
                user_dict.update({
                    "daily_limit": user.get_daily_limit(),
                    "is_trial_active": user.is_trial_active,
                    "is_premium_active": user.is_premium_active,
                    "current_user_type": user.current_user_type
                })
                
                users_data.append(UserSchema.model_validate(user_dict))
            
            pages = (total + per_page - 1) // per_page
            
            return UserListSchema(
                users=users_data,
                total=total,
                page=page,
                pages=pages,
                per_page=per_page
            )
            
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении списка пользователей"
        )

@router.get("/{user_id}", response_model=UserDetailedSchema)
async def get_user(
    user_id: int,
    current_admin = Depends(require_permission("user_view"))
):
    """
    Получение детальной информации о пользователе
    """
    try:
        async with get_db_session() as session:
            user = await session.get(User, user_id)
            
            if not user or user.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Пользователь не найден"
                )
            
            # Получаем дополнительную статистику
            downloads_count = await session.query(DownloadTask).filter(
                DownloadTask.user_id == user_id
            ).count()
            
            successful_downloads = await session.query(DownloadTask).filter(
                and_(
                    DownloadTask.user_id == user_id,
                    DownloadTask.status == "completed"
                )
            ).count()
            
            # Последние платежи
            recent_payments = await session.query(Payment).filter(
                Payment.user_id == user_id
            ).order_by(desc(Payment.created_at)).limit(5).all()
            
            user_dict = user.to_dict()
            user_dict.update({
                "downloads_count": downloads_count,
                "successful_downloads": successful_downloads,
                "recent_payments": [p.to_dict_safe() for p in recent_payments],
                "is_trial_active": user.is_trial_active,
                "is_premium_active": user.is_premium_active,
                "current_user_type": user.current_user_type,
                "daily_limit": user.get_daily_limit()
            })
            
            return UserDetailedSchema.model_validate(user_dict)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении информации о пользователе"
        )

@router.post("/{user_id}/ban")
async def ban_user(
    user_id: int,
    ban_data: UserBanSchema,
    background_tasks: BackgroundTasks,
    current_admin = Depends(require_permission("user_ban")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Блокировка пользователя
    """
    try:
        async with get_db_session() as session:
            user = await session.get(User, user_id)
            
            if not user or user.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Пользователь не найден"
                )
            
            if user.is_banned:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Пользователь уже заблокирован"
                )
            
            # Блокируем пользователя
            user.ban_user(
                reason=ban_data.reason,
                duration_days=ban_data.duration_days
            )
            
            await session.commit()
            
            # Записываем в аналитику
            background_tasks.add_task(
                analytics_service.track_user_event,
                event_type="user_banned",
                user_id=user_id,
                telegram_user_id=user.telegram_id,
                event_data={
                    "reason": ban_data.reason,
                    "duration_days": ban_data.duration_days,
                    "banned_by_admin": current_admin.id
                }
            )
            
            logger.info(
                f"User banned",
                user_id=user_id,
                reason=ban_data.reason,
                admin_id=current_admin.id
            )
            
            return {"message": "Пользователь заблокирован"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error banning user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при блокировке пользователя"
        )

@router.post("/{user_id}/unban")
async def unban_user(
    user_id: int,
    background_tasks: BackgroundTasks,
    current_admin = Depends(require_permission("user_ban")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Разблокировка пользователя
    """
    try:
        async with get_db_session() as session:
            user = await session.get(User, user_id)
            
            if not user or user.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Пользователь не найден"
                )
            
            if not user.is_banned:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Пользователь не заблокирован"
                )
            
            # Разблокируем пользователя
            user.unban_user()
            await session.commit()
            
            # Записываем в аналитику
            background_tasks.add_task(
                analytics_service.track_user_event,
                event_type="user_unbanned",
                user_id=user_id,
                telegram_user_id=user.telegram_id,
                event_data={"unbanned_by_admin": current_admin.id}
            )
            
            logger.info(f"User unbanned", user_id=user_id, admin_id=current_admin.id)
            
            return {"message": "Пользователь разблокирован"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unbanning user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при разблокировке пользователя"
        )

@router.post("/{user_id}/premium")
async def grant_premium(
    user_id: int,
    premium_data: UserPremiumSchema,
    background_tasks: BackgroundTasks,
    current_admin = Depends(require_permission("user_premium")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Выдача Premium статуса пользователю
    """
    try:
        async with get_db_session() as session:
            user = await session.get(User, user_id)
            
            if not user or user.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Пользователь не найден"
                )
            
            # Активируем Premium
            user.activate_premium(duration_days=premium_data.duration_days)
            user.premium_auto_renew = premium_data.auto_renew
            
            await session.commit()
            
            # Записываем в аналитику
            background_tasks.add_task(
                analytics_service.track_user_event,
                event_type="user_premium_granted",
                user_id=user_id,
                telegram_user_id=user.telegram_id,
                event_data={
                    "duration_days": premium_data.duration_days,
                    "auto_renew": premium_data.auto_renew,
                    "granted_by_admin": current_admin.id
                }
            )
            
            logger.info(
                f"Premium granted to user",
                user_id=user_id,
                duration_days=premium_data.duration_days,
                admin_id=current_admin.id
            )
            
            return {"message": "Premium статус выдан"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error granting premium to user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при выдаче Premium статуса"
        )

@router.post("/{user_id}/trial")
async def grant_trial(
    user_id: int,
    trial_data: UserTrialSchema,
    background_tasks: BackgroundTasks,
    current_admin = Depends(require_permission("user_premium")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Выдача Trial периода пользователю
    """
    try:
        async with get_db_session() as session:
            user = await session.get(User, user_id)
            
            if not user or user.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Пользователь не найден"
                )
            
            if user.trial_used:
                # Сбрасываем флаг использования trial для админской выдачи
                user.trial_used = False
            
            # Запускаем trial
            user.start_trial(duration_minutes=trial_data.duration_minutes)
            await session.commit()
            
            # Записываем в аналитику
            background_tasks.add_task(
                analytics_service.track_user_event,
                event_type="user_trial_granted",
                user_id=user_id,
                telegram_user_id=user.telegram_id,
                event_data={
                    "duration_minutes": trial_data.duration_minutes,
                    "granted_by_admin": current_admin.id
                }
            )
            
            logger.info(
                f"Trial granted to user",
                user_id=user_id,
                duration_minutes=trial_data.duration_minutes,
                admin_id=current_admin.id
            )
            
            return {"message": "Trial период выдан"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error granting trial to user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при выдаче Trial периода"
        )

@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_admin = Depends(require_permission("user_delete")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Мягкое удаление пользователя (только для суперадминов)
    """
    try:
        # Проверяем права суперадмина
        if not current_admin.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только суперадмин может удалять пользователей"
            )
        
        async with get_db_session() as session:
            user = await session.get(User, user_id)
            
            if not user or user.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Пользователь не найден"
                )
            
            # Мягкое удаление
            user.delete()
            await session.commit()
            
            # Записываем в аналитику
            await analytics_service.track_user_event(
                event_type="user_deleted",
                user_id=user_id,
                telegram_user_id=user.telegram_id,
                event_data={"deleted_by_admin": current_admin.id}
            )
            
            logger.warning(
                f"User deleted",
                user_id=user_id,
                admin_id=current_admin.id
            )
            
            return {"message": "Пользователь удален"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при удалении пользователя"
        )

@router.get("/{user_id}/analytics")
async def get_user_analytics(
    user_id: int,
    days: int = Query(30, ge=1, le=365, description="Количество дней для анализа"),
    current_admin = Depends(require_permission("user_view")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Получение аналитики конкретного пользователя
    """
    try:
        analytics_data = await analytics_service.get_user_analytics(user_id, days)
        
        if "error" in analytics_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Ошибка при получении аналитики пользователя"
            )
        
        return analytics_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user analytics {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении аналитики"
        )

@router.get("/export/csv")
async def export_users_csv(
    format_type: str = Query("csv", description="Формат экспорта"),
    user_type: Optional[str] = Query(None),
    is_banned: Optional[bool] = Query(None),
    is_premium: Optional[bool] = Query(None),
    current_admin = Depends(require_permission("user_view"))
):
    """
    Экспорт пользователей в CSV/Excel
    """
    try:
        async with get_db_session() as session:
            # Применяем те же фильтры что и в списке
            query = session.query(User).filter(User.is_deleted == False)
            
            if user_type:
                query = query.filter(User.user_type == user_type)
            if is_banned is not None:
                query = query.filter(User.is_banned == is_banned)
            if is_premium is not None:
                query = query.filter(User.is_premium == is_premium)
            
            users = await query.all()
            
            if format_type == "excel":
                return await export_users_to_excel(users)
            else:
                return await export_users_to_csv(users)
                
    except Exception as e:
        logger.error(f"Error exporting users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при экспорте данных"
        )

@router.post("/bulk-ban")
async def bulk_ban_users(
    user_ids: List[int],
    ban_data: UserBanSchema,
    background_tasks: BackgroundTasks,
    current_admin = Depends(require_permission("user_ban")),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Массовая блокировка пользователей
    """
    try:
        async with get_db_session() as session:
            banned_count = 0
            errors = []
            
            for user_id in user_ids:
                try:
                    user = await session.get(User, user_id)
                    if user and not user.is_deleted and not user.is_banned:
                        user.ban_user(
                            reason=ban_data.reason,
                            duration_days=ban_data.duration_days
                        )
                        banned_count += 1
                        
                        # Аналитика
                        background_tasks.add_task(
                            analytics_service.track_user_event,
                            event_type="user_banned",
                            user_id=user_id,
                            telegram_user_id=user.telegram_id,
                            event_data={
                                "reason": ban_data.reason,
                                "duration_days": ban_data.duration_days,
                                "banned_by_admin": current_admin.id,
                                "bulk_operation": True
                            }
                        )
                except Exception as e:
                    errors.append(f"User {user_id}: {str(e)}")
            
            await session.commit()
            
            logger.info(
                f"Bulk ban completed",
                banned_count=banned_count,
                total_requested=len(user_ids),
                admin_id=current_admin.id
            )
            
            return {
                "message": f"Заблокировано {banned_count} из {len(user_ids)} пользователей",
                "banned_count": banned_count,
                "errors": errors
            }
            
    except Exception as e:
        logger.error(f"Error in bulk ban: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при массовой блокировке"
        )

@router.get("/stats/overview")
async def get_users_overview(
    current_admin = Depends(require_permission("user_view"))
):
    """
    Общая статистика пользователей
    """
    try:
        async with get_db_session() as session:
            # Общие счетчики
            total_users = await session.query(User).filter(User.is_deleted == False).count()
            
            banned_users = await session.query(User).filter(
                and_(User.is_deleted == False, User.is_banned == True)
            ).count()
            
            premium_users = await session.query(User).filter(
                and_(User.is_deleted == False, User.is_premium == True)
            ).count()
            
            # Активные пользователи (за последние 30 дней)
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            active_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.last_active_at >= cutoff_date
                )
            ).count()
            
            # Новые пользователи (за последние 30 дней)
            new_users = await session.query(User).filter(
                and_(
                    User.is_deleted == False,
                    User.created_at >= cutoff_date
                )
            ).count()
            
            # Распределение по типам
            user_types = await session.query(
                User.user_type,
                func.count(User.id)
            ).filter(User.is_deleted == False).group_by(User.user_type).all()
            
            return {
                "total_users": total_users,
                "banned_users": banned_users,
                "premium_users": premium_users,
                "active_users_30d": active_users,
                "new_users_30d": new_users,
                "user_type_distribution": {
                    user_type: count for user_type, count in user_types
                },
                "stats_updated_at": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error getting users overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении статистики"
        )