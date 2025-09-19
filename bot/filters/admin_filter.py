"""
VideoBot Pro - Admin Filter
Фильтры для проверки административных прав
"""

from typing import Union, List, Optional
from aiogram import types
from aiogram.filters import BaseFilter

from bot.config import bot_config

class AdminFilter(BaseFilter):
    """Фильтр для проверки административных прав"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка является ли пользователь админом"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        is_admin = bot_config.is_admin(user_id)
        
        if not is_admin:
            return False
        
        return {
            'user_id': user_id,
            'is_admin': True,
            'is_super_admin': bot_config.is_super_admin(user_id)
        }

class SuperAdminFilter(BaseFilter):
    """Фильтр для проверки прав супер-администратора"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка является ли пользователь супер-админом"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        is_super_admin = bot_config.is_super_admin(user_id)
        
        if not is_super_admin:
            return False
        
        return {
            'user_id': user_id,
            'is_super_admin': True
        }

class AdminCommandFilter(BaseFilter):
    """Фильтр для админских команд"""
    
    def __init__(self, commands: Optional[List[str]] = None):
        """
        Args:
            commands: Список админских команд
        """
        self.admin_commands = commands or [
            'admin', 'stats', 'broadcast', 'maintenance',
            'ban', 'unban', 'premium', 'users', 'logs'
        ]
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка админской команды"""
        if not message.text or not message.text.startswith('/'):
            return False
        
        if not message.from_user or not bot_config.is_admin(message.from_user.id):
            return False
        
        command = message.text.split()[0][1:].lower()  # Убираем '/' и приводим к нижнему регистру
        
        if command not in self.admin_commands:
            return False
        
        return {
            'command': command,
            'user_id': message.from_user.id,
            'is_admin_command': True
        }

class BroadcastFilter(BaseFilter):
    """Фильтр для команд рассылки"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка команды рассылки"""
        if not message.text or not message.from_user:
            return False
        
        if not bot_config.is_admin(message.from_user.id):
            return False
        
        # Проверяем является ли это командой рассылки
        text = message.text.lower()
        broadcast_keywords = ['broadcast', 'рассылка', 'send_all', 'announce']
        
        is_broadcast = any(keyword in text for keyword in broadcast_keywords)
        
        if not is_broadcast:
            return False
        
        return {
            'user_id': message.from_user.id,
            'is_broadcast': True,
            'message_text': message.text
        }

class MaintenanceFilter(BaseFilter):
    """Фильтр для режима обслуживания"""
    
    def __init__(self, allow_admins: bool = True):
        """
        Args:
            allow_admins: Разрешить админам использовать бота в режиме обслуживания
        """
        self.allow_admins = allow_admins
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка режима обслуживания"""
        # Если режим обслуживания отключен, пропускаем всех
        if not bot_config.maintenance_mode:
            return True
        
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        # Админы могут работать в режиме обслуживания
        if self.allow_admins and bot_config.is_admin(user_id):
            return {
                'user_id': user_id,
                'maintenance_mode': True,
                'admin_access': True
            }
        
        # Обычные пользователи не могут
        return False

class AdminCallbackFilter(BaseFilter):
    """Фильтр для админских callback запросов"""
    
    def __init__(self, admin_prefixes: Optional[List[str]] = None):
        """
        Args:
            admin_prefixes: Префиксы админских callback'ов
        """
        self.admin_prefixes = admin_prefixes or [
            'admin_', 'stats_', 'broadcast_', 'user_manage_',
            'ban_', 'unban_', 'premium_grant_', 'maintenance_'
        ]
    
    async def __call__(self, callback: types.CallbackQuery) -> Union[bool, dict]:
        """Проверка админского callback"""
        if not callback.data or not callback.from_user:
            return False
        
        if not bot_config.is_admin(callback.from_user.id):
            return False
        
        # Проверяем префикс
        is_admin_callback = any(
            callback.data.startswith(prefix) 
            for prefix in self.admin_prefixes
        )
        
        if not is_admin_callback:
            return False
        
        return {
            'callback_data': callback.data,
            'user_id': callback.from_user.id,
            'is_admin_callback': True
        }

class OwnerFilter(BaseFilter):
    """Фильтр только для владельца бота"""
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка является ли пользователь владельцем"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        # Владелец - это первый админ в списке
        if not bot_config.admin_ids or user_id != bot_config.admin_ids[0]:
            return False
        
        return {
            'user_id': user_id,
            'is_owner': True
        }

class AdminLevelFilter(BaseFilter):
    """Фильтр по уровню администратора"""
    
    def __init__(self, min_level: int = 1):
        """
        Args:
            min_level: Минимальный уровень админа (1-обычный, 2-супер, 3-владелец)
        """
        self.min_level = min_level
    
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        """Проверка уровня админа"""
        if not message.from_user:
            return False
        
        user_id = message.from_user.id
        
        # Определяем уровень пользователя
        if not bot_config.is_admin(user_id):
            level = 0
        elif bot_config.admin_ids and user_id == bot_config.admin_ids[0]:
            level = 3  # Владелец
        elif bot_config.is_super_admin(user_id):
            level = 2  # Супер-админ
        else:
            level = 1  # Обычный админ
        
        if level < self.min_level:
            return False
        
        return {
            'user_id': user_id,
            'admin_level': level,
            'meets_requirement': True
        }

# Предопределенные экземпляры фильтров
is_admin = AdminFilter()
is_super_admin = SuperAdminFilter()
is_owner = OwnerFilter()
is_admin_command = AdminCommandFilter()
is_broadcast_command = BroadcastFilter()
is_admin_callback = AdminCallbackFilter()

# Фильтры с параметрами
def maintenance_mode(allow_admins: bool = True) -> MaintenanceFilter:
    """Фильтр режима обслуживания"""
    return MaintenanceFilter(allow_admins)

def admin_level(min_level: int) -> AdminLevelFilter:
    """Фильтр по уровню админа"""
    return AdminLevelFilter(min_level)

def admin_commands(*commands: str) -> AdminCommandFilter:
    """Фильтр для конкретных админских команд"""
    return AdminCommandFilter(list(commands))

def admin_callbacks(*prefixes: str) -> AdminCallbackFilter:
    """Фильтр для админских callback'ов с конкретными префиксами"""
    return AdminCallbackFilter(list(prefixes))