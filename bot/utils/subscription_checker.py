"""
VideoBot Pro - Subscription Checker
Утилиты для проверки подписок на обязательные каналы
"""

import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from sqlalchemy.ext.asyncio import AsyncSession
from shared.models import User, RequiredChannel
from bot.config import bot_config

logger = structlog.get_logger(__name__)


class SubscriptionChecker:
    """Класс для проверки подписок пользователей"""
    
    def __init__(self, bot: Bot):
        """
        Инициализация проверяльщика подписок
        
        Args:
            bot: Экземпляр бота
        """
        self.bot = bot
        self._cache = {}
        self._cache_ttl = 300  # 5 минут
    
    async def check_user_subscriptions(
        self,
        user_id: int,
        session: AsyncSession,
        force_check: bool = False
    ) -> Dict:
        """
        Проверить подписки пользователя на все обязательные каналы
        
        Args:
            user_id: Telegram ID пользователя
            session: Сессия базы данных
            force_check: Принудительная проверка без кеша
            
        Returns:
            Результаты проверки
        """
        # Проверяем кеш
        cache_key = f"subs_{user_id}"
        if not force_check and cache_key in self._cache:
            cached = self._cache[cache_key]
            if datetime.utcnow() - cached['timestamp'] < timedelta(seconds=self._cache_ttl):
                return cached['result']
        
        try:
            # Получаем пользователя
            user = await session.get(User, user_id)
            if not user:
                return {
                    'error': 'user_not_found',
                    'all_subscribed': False
                }
            
            # Получаем активные каналы для типа пользователя
            channels = await self._get_required_channels(session, user.current_user_type)
            
            if not channels:
                result = {
                    'all_subscribed': True,
                    'subscribed_channels': [],
                    'missing_channels': [],
                    'error_channels': [],
                    'channels_checked': 0
                }
            else:
                # Проверяем каждый канал
                result = await self._check_channels(user_id, channels)
                
                # Обновляем данные пользователя
                user.subscribed_channels = result['subscribed_channels']
                user.last_subscription_check = datetime.utcnow()
                user.subscription_check_passed = result['all_subscribed']
                await session.flush()
            
            # Кешируем результат
            self._cache[cache_key] = {
                'timestamp': datetime.utcnow(),
                'result': result
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error checking subscriptions: {e}", user_id=user_id)
            return {
                'error': str(e),
                'all_subscribed': False
            }
    
    async def _get_required_channels(
        self,
        session: AsyncSession,
        user_type: str
    ) -> List[RequiredChannel]:
        """
        Получить список обязательных каналов для типа пользователя
        
        Args:
            session: Сессия базы данных
            user_type: Тип пользователя
            
        Returns:
            Список каналов
        """
        # Premium и admin пользователи освобождены от подписок
        if user_type in ['premium', 'admin']:
            return []
        
        # Получаем активные каналы
        result = await session.execute(
            """
            SELECT * FROM required_channels 
            WHERE is_active = true 
            AND (required_for_free = true OR required_for_trial = true)
            ORDER BY priority DESC
            """
        )
        
        channels = result.scalars().all()
        
        # Фильтруем по типу пользователя
        if user_type == 'trial':
            return [ch for ch in channels if ch.required_for_trial]
        else:  # free
            return [ch for ch in channels if ch.required_for_free]
    
    async def _check_channels(
        self,
        user_id: int,
        channels: List[RequiredChannel]
    ) -> Dict:
        """
        Проверить подписки на список каналов
        
        Args:
            user_id: Telegram ID пользователя
            channels: Список каналов для проверки
            
        Returns:
            Результаты проверки
        """
        subscribed = []
        missing = []
        errors = []
        
        for channel in channels:
            try:
                is_subscribed = await self._check_channel_subscription(
                    user_id,
                    channel.channel_id
                )
                
                if is_subscribed:
                    subscribed.append(channel.channel_id)
                else:
                    missing.append({
                        'channel_id': channel.channel_id,
                        'channel_name': channel.channel_name,
                        'url': channel.telegram_url or f"https://t.me/{channel.channel_id.replace('@', '')}",
                        'invite_link': channel.invite_link
                    })
            
            except Exception as e:
                logger.warning(
                    f"Error checking channel {channel.channel_id}: {e}",
                    user_id=user_id
                )
                errors.append({
                    'channel_id': channel.channel_id,
                    'channel_name': channel.channel_name,
                    'error': str(e)
                })
        
        return {
            'all_subscribed': len(missing) == 0 and len(errors) == 0,
            'subscribed_channels': subscribed,
            'missing_channels': missing,
            'error_channels': errors,
            'channels_checked': len(channels)
        }
    
    async def _check_channel_subscription(
        self,
        user_id: int,
        channel_id: str
    ) -> bool:
        """
        Проверить подписку на конкретный канал
        
        Args:
            user_id: Telegram ID пользователя
            channel_id: ID канала
            
        Returns:
            True если подписан
        """
        try:
            member = await self.bot.get_chat_member(channel_id, user_id)
            
            # Статусы, которые считаются подписанными
            subscribed_statuses = [
                ChatMemberStatus.CREATOR,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.RESTRICTED
            ]
            
            return member.status in subscribed_statuses
        
        except TelegramBadRequest as e:
            error_text = str(e).lower()
            if "chat not found" in error_text:
                logger.warning(f"Channel not found: {channel_id}")
                return False
            elif "user not found" in error_text:
                return False
            else:
                raise
        
        except TelegramForbiddenError:
            logger.warning(f"Bot has no access to channel: {channel_id}")
            return False
        
        except Exception as e:
            logger.error(f"Unexpected error checking channel: {e}")
            raise
    
    def clear_cache(self, user_id: Optional[int] = None):
        """
        Очистить кеш проверок
        
        Args:
            user_id: ID пользователя для очистки (None - очистить весь)
        """
        if user_id:
            cache_key = f"subs_{user_id}"
            self._cache.pop(cache_key, None)
        else:
            self._cache.clear()
    
    async def get_channel_members_count(self, channel_id: str) -> Optional[int]:
        """
        Получить количество подписчиков канала
        
        Args:
            channel_id: ID канала
            
        Returns:
            Количество подписчиков или None
        """
        try:
            chat = await self.bot.get_chat(channel_id)
            return chat.member_count
        except Exception as e:
            logger.error(f"Error getting channel members count: {e}")
            return None


async def check_required_subscriptions(
    bot: Bot,
    user_id: int,
    session: AsyncSession,
    force_check: bool = False
) -> Dict:
    """
    Утилита для быстрой проверки подписок
    
    Args:
        bot: Экземпляр бота
        user_id: Telegram ID пользователя
        session: Сессия базы данных
        force_check: Принудительная проверка
        
    Returns:
        Результаты проверки
    """
    checker = SubscriptionChecker(bot)
    return await checker.check_user_subscriptions(user_id, session, force_check)


async def is_user_subscribed_to_required_channels(
    bot: Bot,
    user_id: int,
    session: AsyncSession
) -> bool:
    """
    Проверить подписан ли пользователь на все обязательные каналы
    
    Args:
        bot: Экземпляр бота
        user_id: Telegram ID пользователя
        session: Сессия базы данных
        
    Returns:
        True если подписан на все
    """
    if not bot_config.required_subs_enabled:
        return True
    
    result = await check_required_subscriptions(bot, user_id, session)
    return result.get('all_subscribed', False)


async def get_missing_subscriptions(
    bot: Bot,
    user_id: int,
    session: AsyncSession
) -> List[Dict]:
    """
    Получить список каналов, на которые не подписан пользователь
    
    Args:
        bot: Экземпляр бота
        user_id: Telegram ID пользователя
        session: Сессия базы данных
        
    Returns:
        Список неподписанных каналов
    """
    result = await check_required_subscriptions(bot, user_id, session)
    return result.get('missing_channels', [])


async def validate_channel_for_bot(bot: Bot, channel_id: str) -> Dict:
    """
    Проверить, может ли бот работать с каналом
    
    Args:
        bot: Экземпляр бота
        channel_id: ID канала
        
    Returns:
        Результат проверки
    """
    try:
        # Получаем информацию о канале
        chat = await bot.get_chat(channel_id)
        
        # Проверяем статус бота в канале
        bot_member = await bot.get_chat_member(channel_id, bot.id)
        
        can_check = bot_member.status in [
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER
        ]
        
        return {
            'valid': True,
            'can_check_subscriptions': can_check,
            'chat_type': chat.type,
            'chat_title': chat.title,
            'member_count': chat.member_count,
            'bot_status': bot_member.status.value
        }
    
    except TelegramBadRequest as e:
        error_text = str(e).lower()
        if "chat not found" in error_text:
            return {
                'valid': False,
                'error': 'channel_not_found',
                'message': 'Канал не найден'
            }
        else:
            return {
                'valid': False,
                'error': 'bad_request',
                'message': str(e)
            }
    
    except TelegramForbiddenError:
        return {
            'valid': False,
            'error': 'no_access',
            'message': 'Бот не имеет доступа к каналу'
        }
    
    except Exception as e:
        logger.error(f"Error validating channel: {e}")
        return {
            'valid': False,
            'error': 'unknown',
            'message': str(e)
        }


async def bulk_check_subscriptions(
    bot: Bot,
    user_ids: List[int],
    channel_id: str
) -> Dict[int, bool]:
    """
    Массовая проверка подписок пользователей на канал
    
    Args:
        bot: Экземпляр бота
        user_ids: Список ID пользователей
        channel_id: ID канала
        
    Returns:
        Словарь {user_id: is_subscribed}
    """
    results = {}
    
    for user_id in user_ids:
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            results[user_id] = member.status not in [
                ChatMemberStatus.LEFT,
                ChatMemberStatus.KICKED
            ]
        except Exception:
            results[user_id] = False
    
    return results