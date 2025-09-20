"""
VideoBot Pro - Admin Broadcast API
API для управления массовыми рассылками
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, UploadFile, File
from sqlalchemy import and_, or_, func, desc, asc
from sqlalchemy.orm import AsyncSession
import structlog
import json

from shared.config.database import get_async_session
from shared.models import (
    BroadcastMessage, User, BroadcastStatus, BroadcastTargetType,
    AnalyticsEvent, EventType
)
from shared.schemas.admin import (
    BroadcastSchema, BroadcastUpdateSchema, ResponseSchema, PaginationSchema
)
from shared.utils.helpers import format_date, format_relative_time
from ..config import get_admin_settings
from ..dependencies import get_current_admin, require_permission, get_pagination

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/broadcast", tags=["broadcast"])

@router.get("/", response_model=ResponseSchema)
async def get_broadcasts(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin),
    pagination = Depends(get_pagination),
    # Фильтры
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    target_type: Optional[str] = Query(None, description="Фильтр по типу аудитории"),
    created_by: Optional[int] = Query(None, description="Фильтр по создателю"),
    date_from: Optional[datetime] = Query(None, description="Дата начала"),
    date_to: Optional[datetime] = Query(None, description="Дата окончания"),
    search: Optional[str] = Query(None, description="Поиск по заголовку"),
    sort_by: str = Query("created_at", description="Поле сортировки"),
    sort_order: str = Query("desc", description="Порядок сортировки")
):
    """Получить список рассылок с фильтрацией"""
    try:
        # Базовый запрос
        query = session.query(BroadcastMessage)
        
        # Применяем фильтры
        if status:
            query = query.filter(BroadcastMessage.status == status)
        
        if target_type:
            query = query.filter(BroadcastMessage.target_type == target_type)
        
        if created_by:
            query = query.filter(BroadcastMessage.created_by_admin_id == created_by)
        
        if date_from:
            query = query.filter(BroadcastMessage.created_at >= date_from)
        
        if date_to:
            query = query.filter(BroadcastMessage.created_at <= date_to)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    BroadcastMessage.title.ilike(search_term),
                    BroadcastMessage.message_text.ilike(search_term)
                )
            )
        
        # Сортировка
        sort_column = getattr(BroadcastMessage, sort_by, BroadcastMessage.created_at)
        if sort_order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Подсчёт общего количества
        total = await query.count()
        
        # Применяем пагинацию
        offset = (pagination.page - 1) * pagination.per_page
        broadcasts = await query.offset(offset).limit(pagination.per_page).all()
        
        # Формируем данные рассылок
        broadcasts_data = []
        for broadcast in broadcasts:
            broadcast_dict = broadcast.to_dict_summary()
            
            # Добавляем информацию о создателе
            if broadcast.created_by_admin_id:
                creator_info = await get_admin_info(session, broadcast.created_by_admin_id)
                broadcast_dict['created_by'] = creator_info
            
            broadcasts_data.append(broadcast_dict)
        
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
                "broadcasts": broadcasts_data,
                "pagination": pagination_data.dict()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get broadcasts: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения рассылок")

@router.get("/{broadcast_id}", response_model=ResponseSchema)
async def get_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin)
):
    """Получить детальную информацию о рассылке"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        # Получаем детальную информацию
        broadcast_data = broadcast.to_dict_detailed()
        
        # Добавляем информацию о создателе и одобрившем
        if broadcast.created_by_admin_id:
            creator_info = await get_admin_info(session, broadcast.created_by_admin_id)
            broadcast_data['created_by'] = creator_info
        
        if broadcast.approved_by_admin_id:
            approver_info = await get_admin_info(session, broadcast.approved_by_admin_id)
            broadcast_data['approved_by'] = approver_info
        
        # Получаем статистику целевой аудитории
        if broadcast.target_type != BroadcastTargetType.SPECIFIC_USERS:
            audience_stats = await calculate_target_audience(session, broadcast)
            broadcast_data['audience_stats'] = audience_stats
        
        # Получаем детальную статистику доставки
        delivery_details = await get_delivery_details(session, broadcast_id)
        broadcast_data['delivery_details'] = delivery_details
        
        return ResponseSchema(
            success=True,
            data=broadcast_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения рассылки")

@router.post("/", response_model=ResponseSchema)
async def create_broadcast(
    broadcast_data: BroadcastSchema,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("broadcast_create")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Создать новую рассылку"""
    try:
        # Создаём рассылку
        broadcast = BroadcastMessage.create_broadcast(
            title=broadcast_data.title,
            message_text=broadcast_data.message_text,
            target_type=broadcast_data.target_type,
            created_by_admin_id=current_admin['admin_id'],
            target_user_ids=broadcast_data.target_user_ids,
            target_filters=broadcast_data.target_filters,
            scheduled_at=broadcast_data.scheduled_at,
            media_type=broadcast_data.media_type,
            media_file_id=broadcast_data.media_file_id,
            media_caption=broadcast_data.media_caption,
            inline_keyboard=broadcast_data.inline_keyboard,
            send_rate_per_minute=broadcast_data.send_rate_per_minute,
            disable_notification=broadcast_data.disable_notification,
            protect_content=broadcast_data.protect_content
        )
        
        session.add(broadcast)
        await session.commit()
        await session.refresh(broadcast)
        
        # Рассчитываем целевую аудиторию
        if broadcast.target_type != BroadcastTargetType.SPECIFIC_USERS:
            background_tasks.add_task(calculate_and_update_recipients, broadcast.id)
        else:
            broadcast.total_recipients = len(broadcast.target_user_ids or [])
            await session.commit()
        
        # Если рассылка запланирована на сейчас, запускаем её
        if (not broadcast.scheduled_at or 
            broadcast.scheduled_at <= datetime.utcnow()):
            background_tasks.add_task(start_broadcast_sending, broadcast.id)
        
        logger.info(
            f"Broadcast created",
            broadcast_id=broadcast.id,
            admin_id=current_admin['admin_id'],
            target_type=broadcast.target_type,
            scheduled_at=broadcast.scheduled_at
        )
        
        return ResponseSchema(
            success=True,
            message="Рассылка успешно создана",
            data=broadcast.to_dict_detailed()
        )
        
    except Exception as e:
        logger.error(f"Failed to create broadcast: {e}")
        raise HTTPException(status_code=500, detail="Ошибка создания рассылки")

@router.put("/{broadcast_id}", response_model=ResponseSchema)
async def update_broadcast(
    broadcast_id: int,
    broadcast_data: BroadcastUpdateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("broadcast_create"))
):
    """Обновить рассылку (только если не отправляется)"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        # Можно редактировать только draft и scheduled рассылки
        if broadcast.status not in [BroadcastStatus.DRAFT, BroadcastStatus.SCHEDULED]:
            raise HTTPException(
                status_code=400, 
                detail="Нельзя редактировать рассылку в процессе отправки или завершённую"
            )
        
        # Обновляем поля
        update_data = broadcast_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(broadcast, field, value)
        
        await session.commit()
        await session.refresh(broadcast)
        
        logger.info(
            f"Broadcast updated",
            broadcast_id=broadcast_id,
            admin_id=current_admin['admin_id'],
            updated_fields=list(update_data.keys())
        )
        
        return ResponseSchema(
            success=True,
            message="Рассылка успешно обновлена",
            data=broadcast.to_dict_detailed()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обновления рассылки")

@router.post("/{broadcast_id}/send", response_model=ResponseSchema)
async def send_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("broadcast_send")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Запустить отправку рассылки"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        # Проверяем статус
        if broadcast.status not in [BroadcastStatus.DRAFT, BroadcastStatus.SCHEDULED]:
            raise HTTPException(
                status_code=400,
                detail=f"Нельзя запустить рассылку со статусом {broadcast.status}"
            )
        
        # Если нужно одобрение и его нет
        admin_role = current_admin.get('role')
        if (admin_role not in ['super_admin', 'admin'] and 
            not broadcast.approved_by_admin_id):
            raise HTTPException(
                status_code=403,
                detail="Рассылка требует одобрения администратора"
            )
        
        # Запускаем отправку
        background_tasks.add_task(start_broadcast_sending, broadcast_id)
        
        logger.info(
            f"Broadcast sending started",
            broadcast_id=broadcast_id,
            admin_id=current_admin['admin_id']
        )
        
        return ResponseSchema(
            success=True,
            message="Отправка рассылки запущена"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка запуска рассылки")

@router.post("/{broadcast_id}/approve", response_model=ResponseSchema)
async def approve_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("broadcast_send"))
):
    """Одобрить рассылку"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        # Проверяем права (только админы могут одобрять)
        admin_role = current_admin.get('role')
        if admin_role not in ['super_admin', 'admin']:
            raise HTTPException(
                status_code=403,
                detail="Недостаточно прав для одобрения рассылки"
            )
        
        # Одобряем
        broadcast.approved_by_admin_id = current_admin['admin_id']
        broadcast.approved_at = datetime.utcnow()
        
        await session.commit()
        
        logger.info(
            f"Broadcast approved",
            broadcast_id=broadcast_id,
            admin_id=current_admin['admin_id']
        )
        
        return ResponseSchema(
            success=True,
            message="Рассылка одобрена",
            data={"approved_at": broadcast.approved_at.isoformat()}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка одобрения рассылки")

@router.post("/{broadcast_id}/cancel", response_model=ResponseSchema)
async def cancel_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("broadcast_send"))
):
    """Отменить рассылку"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        # Можно отменить только запланированные или отправляющиеся
        if broadcast.status not in [BroadcastStatus.SCHEDULED, BroadcastStatus.SENDING]:
            raise HTTPException(
                status_code=400,
                detail=f"Нельзя отменить рассылку со статусом {broadcast.status}"
            )
        
        broadcast.cancel_broadcast()
        await session.commit()
        
        logger.info(
            f"Broadcast cancelled",
            broadcast_id=broadcast_id,
            admin_id=current_admin['admin_id']
        )
        
        return ResponseSchema(
            success=True,
            message="Рассылка отменена"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка отмены рассылки")

@router.post("/{broadcast_id}/pause", response_model=ResponseSchema)
async def pause_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("broadcast_send"))
):
    """Приостановить рассылку"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        if broadcast.status != BroadcastStatus.SENDING:
            raise HTTPException(
                status_code=400,
                detail="Можно приостановить только отправляющуюся рассылку"
            )
        
        broadcast.pause_broadcast()
        await session.commit()
        
        logger.info(
            f"Broadcast paused",
            broadcast_id=broadcast_id,
            admin_id=current_admin['admin_id']
        )
        
        return ResponseSchema(
            success=True,
            message="Рассылка приостановлена"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка приостановки рассылки")

@router.post("/{broadcast_id}/resume", response_model=ResponseSchema)
async def resume_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("broadcast_send")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Возобновить рассылку"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        if broadcast.status != BroadcastStatus.PAUSED:
            raise HTTPException(
                status_code=400,
                detail="Можно возобновить только приостановленную рассылку"
            )
        
        broadcast.resume_broadcast()
        await session.commit()
        
        # Возобновляем отправку
        background_tasks.add_task(continue_broadcast_sending, broadcast_id)
        
        logger.info(
            f"Broadcast resumed",
            broadcast_id=broadcast_id,
            admin_id=current_admin['admin_id']
        )
        
        return ResponseSchema(
            success=True,
            message="Рассылка возобновлена"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка возобновления рассылки")

@router.delete("/{broadcast_id}", response_model=ResponseSchema)
async def delete_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("broadcast_send"))
):
    """Удалить рассылку"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        # Можно удалить только draft или завершённые рассылки
        if broadcast.status in [BroadcastStatus.SENDING, BroadcastStatus.SCHEDULED]:
            raise HTTPException(
                status_code=400,
                detail="Нельзя удалить активную или запланированную рассылку"
            )
        
        broadcast_title = broadcast.title
        
        # Мягкое удаление
        broadcast.delete()
        await session.commit()
        
        logger.info(
            f"Broadcast deleted",
            broadcast_id=broadcast_id,
            admin_id=current_admin['admin_id'],
            title=broadcast_title
        )
        
        return ResponseSchema(
            success=True,
            message="Рассылка удалена"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления рассылки")

@router.get("/{broadcast_id}/preview", response_model=ResponseSchema)
async def preview_broadcast(
    broadcast_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin),
    limit: int = Query(10, description="Количество пользователей для предпросмотра")
):
    """Предпросмотр целевой аудитории рассылки"""
    try:
        broadcast = await session.query(BroadcastMessage).filter(
            BroadcastMessage.id == broadcast_id
        ).first()
        
        if not broadcast:
            raise HTTPException(status_code=404, detail="Рассылка не найдена")
        
        # Получаем пользователей целевой аудитории
        target_users = await get_target_users_preview(session, broadcast, limit)
        
        # Статистика аудитории
        audience_stats = await calculate_target_audience(session, broadcast)
        
        return ResponseSchema(
            success=True,
            data={
                "broadcast": broadcast.to_dict_summary(),
                "audience_stats": audience_stats,
                "sample_users": target_users,
                "sample_size": len(target_users)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview broadcast {broadcast_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка предпросмотра рассылки")

@router.post("/upload-media", response_model=ResponseSchema)
async def upload_broadcast_media(
    file: UploadFile = File(...),
    current_admin = Depends(require_permission("broadcast_create"))
):
    """Загрузить медиафайл для рассылки"""
    try:
        # Проверяем тип файла
        allowed_types = {
            'image/jpeg', 'image/png', 'image/gif',
            'video/mp4', 'video/quicktime',
            'audio/mpeg', 'audio/ogg'
        }
        
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Неподдерживаемый тип файла"
            )
        
        # Проверяем размер (макс 50MB)
        max_size = 50 * 1024 * 1024  # 50MB
        content = await file.read()
        
        if len(content) > max_size:
            raise HTTPException(
                status_code=400,
                detail="Файл слишком большой (максимум 50MB)"
            )
        
        # Здесь должна быть логика загрузки файла в хранилище
        # и отправки в Telegram для получения file_id
        
        # Временно возвращаем заглушку
        file_id = f"temp_file_{datetime.utcnow().timestamp()}"
        
        logger.info(
            f"Media uploaded for broadcast",
            admin_id=current_admin['admin_id'],
            filename=file.filename,
            content_type=file.content_type,
            size=len(content)
        )
        
        return ResponseSchema(
            success=True,
            message="Медиафайл загружен",
            data={
                "file_id": file_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(content)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload media: {e}")
        raise HTTPException(status_code=500, detail="Ошибка загрузки медиафайла")

@router.get("/stats/overview", response_model=ResponseSchema)
async def get_broadcast_overview(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin),
    days: int = Query(30, description="Количество дней для статистики")
):
    """Получить общую статистику рассылок"""
    try:
        date_from = datetime.utcnow() - timedelta(days=days)
        
        # Общие метрики
        total_broadcasts = await session.query(BroadcastMessage).count()
        
        recent_broadcasts = await session.query(BroadcastMessage).filter(
            BroadcastMessage.created_at >= date_from
        ).count()
        
        # Статистика по статусам
        status_stats = {}
        for status in BroadcastStatus.ALL:
            count = await session.query(BroadcastMessage).filter(
                BroadcastMessage.status == status
            ).count()
            status_stats[status] = count
        
        # Статистика отправки за период
        sending_stats_query = session.query(
            func.sum(BroadcastMessage.sent_count).label('total_sent'),
            func.sum(BroadcastMessage.failed_count).label('total_failed'),
            func.sum(BroadcastMessage.blocked_count).label('total_blocked'),
            func.sum(BroadcastMessage.total_recipients).label('total_recipients')
        ).filter(
            BroadcastMessage.started_at >= date_from,
            BroadcastMessage.status.in_([BroadcastStatus.COMPLETED, BroadcastStatus.SENDING])
        )
        
        sending_stats = await sending_stats_query.first()
        
        # Топ администраторов по количеству рассылок
        top_creators_query = session.query(
            BroadcastMessage.created_by_admin_id,
            func.count(BroadcastMessage.id).label('broadcasts_count'),
            func.sum(BroadcastMessage.sent_count).label('total_sent')
        ).filter(
            BroadcastMessage.created_at >= date_from
        ).group_by(
            BroadcastMessage.created_by_admin_id
        ).order_by(
            desc('broadcasts_count')
        ).limit(5)
        
        top_creators_result = await top_creators_query.all()
        top_creators = []
        for creator in top_creators_result:
            admin_info = await get_admin_info(session, creator.created_by_admin_id)
            top_creators.append({
                "admin": admin_info,
                "broadcasts_count": creator.broadcasts_count,
                "total_sent": creator.total_sent or 0
            })
        
        # Недавние рассылки
        recent_broadcasts_query = session.query(BroadcastMessage).order_by(
            desc(BroadcastMessage.created_at)
        ).limit(10)
        
        recent_broadcasts_list = await recent_broadcasts_query.all()
        recent_data = [broadcast.to_dict_summary() for broadcast in recent_broadcasts_list]
        
        return ResponseSchema(
            success=True,
            data={
                "overview": {
                    "total_broadcasts": total_broadcasts,
                    "recent_broadcasts": recent_broadcasts,
                    "period_days": days
                },
                "status_stats": status_stats,
                "sending_stats": {
                    "total_sent": int(sending_stats.total_sent or 0),
                    "total_failed": int(sending_stats.total_failed or 0),
                    "total_blocked": int(sending_stats.total_blocked or 0),
                    "total_recipients": int(sending_stats.total_recipients or 0),
                    "success_rate": round(
                        (sending_stats.total_sent or 0) / max(sending_stats.total_recipients or 1, 1) * 100, 2
                    )
                },
                "top_creators": top_creators,
                "recent_broadcasts": recent_data
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get broadcast overview: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения обзора рассылок")

# Вспомогательные функции

async def get_admin_info(session: AsyncSession, admin_id: int) -> Dict[str, Any]:
    """Получить краткую информацию об администраторе"""
    try:
        from shared.models import AdminUser
        
        admin = await session.query(AdminUser).filter(
            AdminUser.id == admin_id
        ).first()
        
        if admin:
            return {
                "id": admin.id,
                "username": admin.username,
                "full_name": admin.full_name,
                "role": admin.role
            }
        return {"id": admin_id, "username": "Unknown", "role": "unknown"}
        
    except Exception:
        return {"id": admin_id, "username": "Unknown", "role": "unknown"}

async def calculate_target_audience(session: AsyncSession, broadcast: BroadcastMessage) -> Dict[str, Any]:
    """Рассчитать размер целевой аудитории"""
    try:
        query = broadcast.get_target_users_query(session)
        total_count = await query.count()
        
        # Статистика по типам пользователей
        user_type_stats = {}
        if broadcast.target_type != BroadcastTargetType.SPECIFIC_USERS:
            for user_type in ['free', 'trial', 'premium', 'admin']:
                type_query = query.filter(User.user_type == user_type)
                count = await type_query.count()
                if count > 0:
                    user_type_stats[user_type] = count
        
        return {
            "total_recipients": total_count,
            "user_type_distribution": user_type_stats,
            "target_type": broadcast.target_type
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate target audience: {e}")
        return {"total_recipients": 0, "user_type_distribution": {}}

async def get_target_users_preview(session: AsyncSession, broadcast: BroadcastMessage, limit: int) -> List[Dict[str, Any]]:
    """Получить примеры пользователей из целевой аудитории"""
    try:
        query = broadcast.get_target_users_query(session)
        users = await query.limit(limit).all()
        
        return [
            {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "display_name": user.display_name,
                "user_type": user.user_type,
                "username": user.username,
                "last_active_at": format_relative_time(user.last_active_at) if user.last_active_at else None
            }
            for user in users
        ]
        
    except Exception as e:
        logger.error(f"Failed to get target users preview: {e}")
        return []

async def get_delivery_details(session: AsyncSession, broadcast_id: int) -> Dict[str, Any]:
    """Получить детальную статистику доставки"""
    try:
        # Здесь можно добавить запросы к таблице доставки сообщений
        # Пока возвращаем базовую информацию
        return {
            "delivery_timeline": [],
            "error_breakdown": {},
            "platform_stats": {}
        }
        
    except Exception as e:
        logger.error(f"Failed to get delivery details: {e}")
        return {}

async def calculate_and_update_recipients(broadcast_id: int):
    """Фоновая задача для расчета количества получателей"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            broadcast = await session.query(BroadcastMessage).filter(
                BroadcastMessage.id == broadcast_id
            ).first()
            
            if not broadcast:
                return
            
            # Рассчитываем количество получателей
            audience_stats = await calculate_target_audience(session, broadcast)
            broadcast.total_recipients = audience_stats["total_recipients"]
            
            await session.commit()
            
            logger.info(
                f"Recipients calculated for broadcast",
                broadcast_id=broadcast_id,
                total_recipients=broadcast.total_recipients
            )
            
    except Exception as e:
        logger.error(f"Failed to calculate recipients for broadcast {broadcast_id}: {e}")

async def start_broadcast_sending(broadcast_id: int):
    """Фоновая задача для запуска отправки рассылки"""
    try:
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            broadcast = await session.query(BroadcastMessage).filter(
                BroadcastMessage.id == broadcast_id
            ).first()
            
            if not broadcast:
                return
            
            # Проверяем, можно ли запустить
            if broadcast.status not in [BroadcastStatus.DRAFT, BroadcastStatus.SCHEDULED]:
                return
            
            # Рассчитываем получателей если не рассчитано
            if broadcast.total_recipients == 0:
                audience_stats = await calculate_target_audience(session, broadcast)
                broadcast.total_recipients = audience_stats["total_recipients"]
            
            # Запускаем отправку
            broadcast.start_sending(
                total_recipients=broadcast.total_recipients,
                worker_id="admin_worker",
                task_id=f"broadcast_{broadcast_id}"
            )
            
            await session.commit()
            
            # Здесь должна быть логика отправки через Telegram Bot
            # Пока эмулируем процесс
            import asyncio
            await simulate_broadcast_sending(broadcast_id)
            
            logger.info(
                f"Broadcast sending started",
                broadcast_id=broadcast_id,
                total_recipients=broadcast.total_recipients
            )
            
    except Exception as e:
        logger.error(f"Failed to start broadcast sending {broadcast_id}: {e}")
        
        # Помечаем как неудачную
        try:
            async with get_async_session() as session:
                broadcast = await session.query(BroadcastMessage).filter(
                    BroadcastMessage.id == broadcast_id
                ).first()
                
                if broadcast:
                    broadcast.fail_broadcast(str(e))
                    await session.commit()
        except Exception:
            pass

async def continue_broadcast_sending(broadcast_id: int):
    """Продолжить отправку приостановленной рассылки"""
    try:
        # Аналогично start_broadcast_sending, но для возобновления
        await start_broadcast_sending(broadcast_id)
        
    except Exception as e:
        logger.error(f"Failed to continue broadcast sending {broadcast_id}: {e}")

async def simulate_broadcast_sending(broadcast_id: int):
    """Симуляция процесса отправки рассылки"""
    try:
        import asyncio
        import random
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            broadcast = await session.query(BroadcastMessage).filter(
                BroadcastMessage.id == broadcast_id
            ).first()
            
            if not broadcast or broadcast.status != BroadcastStatus.SENDING:
                return
            
            total_recipients = broadcast.total_recipients
            send_rate = broadcast.send_rate_per_minute
            
            # Симулируем отправку пакетами
            batch_size = min(send_rate, 50)  # Не больше 50 за раз
            sent = 0
            failed = 0
            blocked = 0
            
            while sent + failed + blocked < total_recipients:
                if broadcast.status != BroadcastStatus.SENDING:
                    break
                
                # Симулируем отправку batch
                current_batch = min(batch_size, total_recipients - sent - failed - blocked)
                
                # Случайное распределение результатов
                batch_sent = int(current_batch * random.uniform(0.85, 0.95))
                batch_failed = int((current_batch - batch_sent) * random.uniform(0.3, 0.7))
                batch_blocked = current_batch - batch_sent - batch_failed
                
                sent += batch_sent
                failed += batch_failed
                blocked += batch_blocked
                
                # Обновляем прогресс
                broadcast.update_progress(batch_sent, batch_failed, batch_blocked)
                await session.commit()
                
                # Пауза между пакетами (симуляция rate limit)
                await asyncio.sleep(60 / send_rate * current_batch)
                
                # Обновляем объект из БД
                await session.refresh(broadcast)
            
            # Завершаем рассылку
            if broadcast.status == BroadcastStatus.SENDING:
                broadcast.complete_successfully()
                await session.commit()
                
                logger.info(
                    f"Broadcast completed",
                    broadcast_id=broadcast_id,
                    sent=sent,
                    failed=failed,
                    blocked=blocked
                )
            
    except Exception as e:
        logger.error(f"Failed to simulate broadcast sending {broadcast_id}: {e}")
        
        # Помечаем как неудачную
        try:
            async with get_async_session() as session:
                broadcast = await session.query(BroadcastMessage).filter(
                    BroadcastMessage.id == broadcast_id
                ).first()
                
                if broadcast:
                    broadcast.fail_broadcast(str(e))
                    await session.commit()
        except Exception:
            pass