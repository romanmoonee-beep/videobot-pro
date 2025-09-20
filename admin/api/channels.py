"""
VideoBot Pro - Admin Channels API
API для управления обязательными каналами для подписки
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import and_, or_, func, desc, asc
from sqlalchemy.orm import AsyncSession
import structlog

from shared.config.database import get_async_session
from shared.models import RequiredChannel, User, AnalyticsEvent
from shared.schemas.admin import (
    ChannelSchema, ChannelCreateSchema, ChannelUpdateSchema,
    ResponseSchema, PaginationSchema
)
from shared.utils.helpers import format_date, chunk_list
from ..config import get_admin_settings
from ..dependencies import get_current_admin, require_permission, get_pagination

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/channels", tags=["channels"])

@router.get("/", response_model=ResponseSchema)
async def get_channels(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin),
    pagination = Depends(get_pagination),
    # Фильтры
    search: Optional[str] = Query(None, description="Поиск по названию канала"),
    is_active: Optional[bool] = Query(None, description="Фильтр по активности"),
    is_required: Optional[bool] = Query(None, description="Фильтр по обязательности"),
    platform_type: Optional[str] = Query(None, description="Тип платформы"),
    sort_by: str = Query("priority", description="Поле сортировки"),
    sort_order: str = Query("asc", description="Порядок сортировки")
):
    """Получить список каналов с фильтрацией"""
    try:
        # Базовый запрос
        query = session.query(RequiredChannel)
        
        # Применяем фильтры
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    RequiredChannel.channel_name.ilike(search_term),
                    RequiredChannel.channel_username.ilike(search_term),
                    RequiredChannel.description.ilike(search_term)
                )
            )
        
        if is_active is not None:
            query = query.filter(RequiredChannel.is_active == is_active)
        
        if is_required is not None:
            query = query.filter(RequiredChannel.is_required == is_required)
        
        # Сортировка
        sort_column = getattr(RequiredChannel, sort_by, RequiredChannel.priority)
        if sort_order.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Подсчёт общего количества
        total = await query.count()
        
        # Применяем пагинацию
        offset = (pagination.page - 1) * pagination.per_page
        channels = await query.offset(offset).limit(pagination.per_page).all()
        
        # Получаем статистику подписок для каждого канала
        channels_data = []
        for channel in channels:
            channel_dict = channel.to_dict_for_admin()
            
            # Добавляем статистику подписок пользователей
            subscription_stats = await get_channel_subscription_stats(session, channel.id)
            channel_dict.update(subscription_stats)
            
            channels_data.append(channel_dict)
        
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
                "channels": channels_data,
                "pagination": pagination_data.dict()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get channels: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения каналов")

@router.get("/{channel_id}", response_model=ResponseSchema)
async def get_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin)
):
    """Получить детальную информацию о канале"""
    try:
        channel = await session.query(RequiredChannel).filter(
            RequiredChannel.id == channel_id
        ).first()
        
        if not channel:
            raise HTTPException(status_code=404, detail="Канал не найден")
        
        # Получаем детальную статистику
        channel_data = channel.to_dict_for_admin()
        
        # Статистика подписок
        subscription_stats = await get_channel_subscription_stats(session, channel_id)
        channel_data.update(subscription_stats)
        
        # История подписок за последние 30 дней
        subscription_history = await get_channel_subscription_history(session, channel_id, 30)
        channel_data['subscription_history'] = subscription_history
        
        # Топ пользователей, не подписанных на канал
        unsubscribed_users = await get_unsubscribed_users(session, channel_id, limit=10)
        channel_data['unsubscribed_users_sample'] = unsubscribed_users
        
        return ResponseSchema(
            success=True,
            data=channel_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get channel {channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения канала")

@router.post("/", response_model=ResponseSchema)
async def create_channel(
    channel_data: ChannelCreateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("channel_manage")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Создать новый обязательный канал"""
    try:
        # Проверяем, не существует ли уже канал с таким channel_id
        existing_channel = await session.query(RequiredChannel).filter(
            RequiredChannel.channel_id == channel_data.channel_id
        ).first()
        
        if existing_channel:
            raise HTTPException(
                status_code=400, 
                detail="Канал с таким ID уже существует"
            )
        
        # Создаём канал
        channel = RequiredChannel.create_from_channel_info(
            channel_id=channel_data.channel_id,
            channel_name=channel_data.channel_name,
            username=channel_data.channel_id if not channel_data.channel_id.startswith('-') else None,
            description=channel_data.description,
            invite_link=channel_data.invite_link,
            priority=channel_data.priority,
            check_interval_minutes=channel_data.check_interval_minutes
        )
        
        channel.added_by_admin_id = current_admin['admin_id']
        
        session.add(channel)
        await session.commit()
        await session.refresh(channel)
        
        # Запускаем задачу обновления информации о канале
        background_tasks.add_task(update_channel_info, channel.id)
        
        # Логируем создание
        logger.info(
            f"Channel created",
            channel_id=channel.id,
            admin_id=current_admin['admin_id'],
            channel_name=channel.channel_name
        )
        
        return ResponseSchema(
            success=True,
            message="Канал успешно создан",
            data=channel.to_dict_for_admin()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create channel: {e}")
        raise HTTPException(status_code=500, detail="Ошибка создания канала")

@router.put("/{channel_id}", response_model=ResponseSchema)
async def update_channel(
    channel_id: int,
    channel_data: ChannelUpdateSchema,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("channel_manage")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Обновить канал"""
    try:
        channel = await session.query(RequiredChannel).filter(
            RequiredChannel.id == channel_id
        ).first()
        
        if not channel:
            raise HTTPException(status_code=404, detail="Канал не найден")
        
        # Обновляем поля
        update_data = channel_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(channel, field, value)
        
        channel.last_modified_by = current_admin['admin_id']
        
        await session.commit()
        await session.refresh(channel)
        
        # Если изменились критические настройки, обновляем информацию
        if any(field in update_data for field in ['channel_id', 'channel_name']):
            background_tasks.add_task(update_channel_info, channel.id)
        
        logger.info(
            f"Channel updated",
            channel_id=channel.id,
            admin_id=current_admin['admin_id'],
            updated_fields=list(update_data.keys())
        )
        
        return ResponseSchema(
            success=True,
            message="Канал успешно обновлён",
            data=channel.to_dict_for_admin()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update channel {channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обновления канала")

@router.delete("/{channel_id}", response_model=ResponseSchema)
async def delete_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("channel_delete"))
):
    """Удалить канал"""
    try:
        channel = await session.query(RequiredChannel).filter(
            RequiredChannel.id == channel_id
        ).first()
        
        if not channel:
            raise HTTPException(status_code=404, detail="Канал не найден")
        
        channel_name = channel.channel_name
        
        await session.delete(channel)
        await session.commit()
        
        logger.info(
            f"Channel deleted",
            channel_id=channel_id,
            admin_id=current_admin['admin_id'],
            channel_name=channel_name
        )
        
        return ResponseSchema(
            success=True,
            message="Канал успешно удалён"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete channel {channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка удаления канала")

@router.post("/{channel_id}/toggle-active", response_model=ResponseSchema)
async def toggle_channel_active(
    channel_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("channel_manage"))
):
    """Переключить активность канала"""
    try:
        channel = await session.query(RequiredChannel).filter(
            RequiredChannel.id == channel_id
        ).first()
        
        if not channel:
            raise HTTPException(status_code=404, detail="Канал не найден")
        
        channel.is_active = not channel.is_active
        channel.last_modified_by = current_admin['admin_id']
        
        await session.commit()
        
        action = "активирован" if channel.is_active else "деактивирован"
        
        logger.info(
            f"Channel {action}",
            channel_id=channel_id,
            admin_id=current_admin['admin_id'],
            is_active=channel.is_active
        )
        
        return ResponseSchema(
            success=True,
            message=f"Канал {action}",
            data={"is_active": channel.is_active}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to toggle channel {channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка изменения статуса канала")

@router.post("/{channel_id}/update-info", response_model=ResponseSchema)
async def update_channel_info_endpoint(
    channel_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("channel_manage")),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Обновить информацию о канале (подписчики, название)"""
    try:
        channel = await session.query(RequiredChannel).filter(
            RequiredChannel.id == channel_id
        ).first()
        
        if not channel:
            raise HTTPException(status_code=404, detail="Канал не найден")
        
        # Запускаем обновление в фоне
        background_tasks.add_task(update_channel_info, channel_id)
        
        return ResponseSchema(
            success=True,
            message="Обновление информации о канале запущено"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update channel info {channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обновления информации о канале")

@router.get("/{channel_id}/subscribers", response_model=ResponseSchema)
async def get_channel_subscribers(
    channel_id: int,
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin),
    pagination = Depends(get_pagination),
    subscribed: bool = Query(True, description="True - подписанные, False - неподписанные")
):
    """Получить пользователей подписанных/неподписанных на канал"""
    try:
        channel = await session.query(RequiredChannel).filter(
            RequiredChannel.id == channel_id
        ).first()
        
        if not channel:
            raise HTTPException(status_code=404, detail="Канал не найден")
        
        # Формируем запрос пользователей
        query = session.query(User).filter(User.is_deleted == False)
        
        if subscribed:
            # Подписанные пользователи
            query = query.filter(
                User.subscribed_channels.contains([channel.channel_id])
            )
        else:
            # Неподписанные пользователи (только те, кто должен быть подписан)
            applies_to_types = channel.applies_to_user_types or ['free']
            query = query.filter(
                and_(
                    User.user_type.in_(applies_to_types),
                    ~User.subscribed_channels.contains([channel.channel_id])
                )
            )
        
        # Сортировка по последней активности
        query = query.order_by(desc(User.last_active_at))
        
        # Подсчёт общего количества
        total = await query.count()
        
        # Применяем пагинацию
        offset = (pagination.page - 1) * pagination.per_page
        users = await query.offset(offset).limit(pagination.per_page).all()
        
        # Формируем данные пользователей
        users_data = []
        for user in users:
            user_dict = user.to_dict_safe()
            user_dict['display_name'] = user.display_name
            user_dict['subscription_status'] = channel.channel_id in (user.subscribed_channels or [])
            users_data.append(user_dict)
        
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
                "users": users_data,
                "pagination": pagination_data.dict(),
                "channel": channel.to_dict_for_admin(),
                "filter": "subscribed" if subscribed else "unsubscribed"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get channel subscribers {channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения подписчиков канала")

@router.post("/bulk-actions", response_model=ResponseSchema)
async def bulk_channel_actions(
    action: str,
    channel_ids: List[int],
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(require_permission("channel_manage"))
):
    """Массовые операции с каналами"""
    try:
        if not channel_ids:
            raise HTTPException(status_code=400, detail="Список каналов не может быть пустым")
        
        channels = await session.query(RequiredChannel).filter(
            RequiredChannel.id.in_(channel_ids)
        ).all()
        
        if not channels:
            raise HTTPException(status_code=404, detail="Каналы не найдены")
        
        results = []
        
        for channel in channels:
            try:
                if action == "activate":
                    channel.is_active = True
                elif action == "deactivate":
                    channel.is_active = False
                elif action == "require":
                    channel.is_required = True
                elif action == "unrequire":
                    channel.is_required = False
                elif action == "delete":
                    await session.delete(channel)
                    results.append({
                        "channel_id": channel.id,
                        "status": "deleted",
                        "name": channel.channel_name
                    })
                    continue
                else:
                    raise HTTPException(status_code=400, detail=f"Неизвестное действие: {action}")
                
                channel.last_modified_by = current_admin['admin_id']
                
                results.append({
                    "channel_id": channel.id,
                    "status": "updated",
                    "name": channel.channel_name
                })
                
            except Exception as e:
                results.append({
                    "channel_id": channel.id,
                    "status": "error",
                    "error": str(e),
                    "name": getattr(channel, 'channel_name', 'Unknown')
                })
        
        await session.commit()
        
        logger.info(
            f"Bulk channel action performed",
            action=action,
            admin_id=current_admin['admin_id'],
            channels_count=len(channel_ids),
            results=results
        )
        
        return ResponseSchema(
            success=True,
            message=f"Массовое действие '{action}' выполнено",
            data={"results": results}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to perform bulk channel action: {e}")
        raise HTTPException(status_code=500, detail="Ошибка выполнения массового действия")

@router.get("/stats/overview", response_model=ResponseSchema)
async def get_channels_overview(
    session: AsyncSession = Depends(get_async_session),
    current_admin = Depends(get_current_admin)
):
    """Получить общую статистику каналов"""
    try:
        # Общая статистика каналов
        total_channels = await session.query(RequiredChannel).count()
        active_channels = await session.query(RequiredChannel).filter(
            RequiredChannel.is_active == True
        ).count()
        required_channels = await session.query(RequiredChannel).filter(
            RequiredChannel.is_required == True
        ).count()
        
        # Статистика по типам пользователей
        user_type_stats = {}
        for user_type in ['free', 'trial', 'premium']:
            # Пользователи этого типа
            users_count = await session.query(User).filter(
                and_(
                    User.user_type == user_type,
                    User.is_deleted == False
                )
            ).count()
            
            # Пользователи, прошедшие проверку подписок
            subscribed_count = await session.query(User).filter(
                and_(
                    User.user_type == user_type,
                    User.is_deleted == False,
                    User.subscription_check_passed == True
                )
            ).count()
            
            user_type_stats[user_type] = {
                'total_users': users_count,
                'subscribed_users': subscribed_count,
                'subscription_rate': round(
                    (subscribed_count / users_count * 100) if users_count > 0 else 0, 2
                )
            }
        
        # Топ каналов по количеству подписчиков
        top_channels_query = """
            SELECT 
                rc.id,
                rc.channel_name,
                rc.subscribers_count,
                COUNT(CASE WHEN u.subscribed_channels ? rc.channel_id THEN 1 END) as bot_subscribers
            FROM required_channels rc
            LEFT JOIN users u ON u.subscribed_channels ? rc.channel_id AND u.is_deleted = false
            WHERE rc.is_active = true
            GROUP BY rc.id, rc.channel_name, rc.subscribers_count
            ORDER BY rc.subscribers_count DESC NULLS LAST
            LIMIT 10
        """
        
        top_channels_result = await session.execute(top_channels_query)
        top_channels = [
            {
                'id': row[0],
                'name': row[1],
                'subscribers_count': row[2] or 0,
                'bot_subscribers': row[3] or 0
            }
            for row in top_channels_result.fetchall()
        ]
        
        # Недавние изменения в каналах
        recent_changes = await session.query(RequiredChannel).filter(
            RequiredChannel.updated_at >= datetime.utcnow() - timedelta(days=7)
        ).order_by(desc(RequiredChannel.updated_at)).limit(10).all()
        
        recent_changes_data = [
            {
                'id': channel.id,
                'name': channel.channel_name,
                'action': 'updated',
                'updated_at': format_date(channel.updated_at),
                'is_active': channel.is_active
            }
            for channel in recent_changes
        ]
        
        return ResponseSchema(
            success=True,
            data={
                'overview': {
                    'total_channels': total_channels,
                    'active_channels': active_channels,
                    'required_channels': required_channels,
                    'inactive_channels': total_channels - active_channels
                },
                'user_type_stats': user_type_stats,
                'top_channels': top_channels,
                'recent_changes': recent_changes_data
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get channels overview: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения обзора каналов")

# Вспомогательные функции

async def get_channel_subscription_stats(session: AsyncSession, channel_id: int) -> Dict[str, Any]:
    """Получить статистику подписок для канала"""
    try:
        channel = await session.query(RequiredChannel).filter(
            RequiredChannel.id == channel_id
        ).first()
        
        if not channel:
            return {}
        
        # Количество пользователей бота, подписанных на канал
        bot_subscribers_query = """
            SELECT COUNT(*) 
            FROM users 
            WHERE subscribed_channels ? :channel_id 
            AND is_deleted = false
        """
        
        result = await session.execute(
            bot_subscribers_query, 
            {"channel_id": channel.channel_id}
        )
        bot_subscribers = result.scalar() or 0
        
        # Пользователи, которые должны быть подписаны
        target_user_types = channel.applies_to_user_types or ['free']
        should_subscribe_query = """
            SELECT COUNT(*) 
            FROM users 
            WHERE user_type = ANY(:user_types)
            AND is_deleted = false
            AND is_banned = false
        """
        
        result = await session.execute(
            should_subscribe_query,
            {"user_types": target_user_types}
        )
        should_subscribe = result.scalar() or 0
        
        # Пользователи, не подписанные на канал
        not_subscribed = should_subscribe - bot_subscribers
        
        subscription_rate = (
            (bot_subscribers / should_subscribe * 100) 
            if should_subscribe > 0 else 0
        )
        
        return {
            'bot_subscribers': bot_subscribers,
            'should_subscribe': should_subscribe,
            'not_subscribed': not_subscribed,
            'subscription_rate': round(subscription_rate, 2)
        }
        
    except Exception as e:
        logger.error(f"Failed to get subscription stats for channel {channel_id}: {e}")
        return {}

async def get_channel_subscription_history(session: AsyncSession, channel_id: int, days: int) -> List[Dict[str, Any]]:
    """Получить историю подписок на канал"""
    try:
        # За отсутствием детальной истории, возвращаем заглушку
        # В реальном проекте здесь был бы запрос к таблице истории подписок
        return []
        
    except Exception as e:
        logger.error(f"Failed to get subscription history for channel {channel_id}: {e}")
        return []

async def get_unsubscribed_users(session: AsyncSession, channel_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Получить топ неподписанных пользователей"""
    try:
        channel = await session.query(RequiredChannel).filter(
            RequiredChannel.id == channel_id
        ).first()
        
        if not channel:
            return []
        
        target_user_types = channel.applies_to_user_types or ['free']
        
        query = session.query(User).filter(
            and_(
                User.user_type.in_(target_user_types),
                User.is_deleted == False,
                User.is_banned == False,
                ~User.subscribed_channels.contains([channel.channel_id])
            )
        ).order_by(desc(User.downloads_total)).limit(limit)
        
        users = await query.all()
        
        return [
            {
                'id': user.id,
                'telegram_id': user.telegram_id,
                'display_name': user.display_name,
                'user_type': user.user_type,
                'downloads_total': user.downloads_total,
                'last_active_at': format_date(user.last_active_at) if user.last_active_at else None
            }
            for user in users
        ]
        
    except Exception as e:
        logger.error(f"Failed to get unsubscribed users for channel {channel_id}: {e}")
        return []

async def update_channel_info(channel_id: int):
    """Фоновая задача обновления информации о канале"""
    try:
        # Здесь должна быть логика получения информации о канале через Telegram Bot API
        # Например: получение названия канала, количества подписчиков, проверка существования
        
        from shared.config.database import get_async_session
        
        async with get_async_session() as session:
            channel = await session.query(RequiredChannel).filter(
                RequiredChannel.id == channel_id
            ).first()
            
            if not channel:
                return
            
            # Здесь была бы логика запроса к Telegram API
            # Например:
            # bot_info = await telegram_bot.get_chat(channel.channel_id)
            # channel.channel_name = bot_info.title
            # channel.subscribers_count = await get_channel_members_count(channel.channel_id)
            
            channel.last_stats_update = datetime.utcnow()
            await session.commit()
            
            logger.info(f"Channel info updated", channel_id=channel_id)
            
    except Exception as e:
        logger.error(f"Failed to update channel info {channel_id}: {e}")