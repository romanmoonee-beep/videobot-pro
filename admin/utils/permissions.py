"""
VideoBot Pro - Permissions Utilities
Утилиты для работы с правами доступа
"""

from typing import Dict, List, Set, Any, Optional
from enum import Enum
from functools import wraps
from fastapi import HTTPException, status
import structlog

from ..config import ROLE_PERMISSIONS, check_permission

logger = structlog.get_logger(__name__)

class Resource(str, Enum):
    """Ресурсы системы"""
    USERS = "users"
    DOWNLOADS = "downloads"
    ANALYTICS = "analytics" 
    SETTINGS = "settings"
    CHANNELS = "channels"
    BROADCAST = "broadcast"
    PAYMENTS = "payments"
    SYSTEM = "system"
    ADMIN = "admin"

class Action(str, Enum):
    """Действия в системе"""
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    BAN = "ban"
    PREMIUM = "premium"
    RETRY = "retry"
    CANCEL = "cancel"
    EXPORT = "export"
    SEND = "send"
    SCHEDULE = "schedule"
    REFUND = "refund"
    LOGS = "logs"
    HEALTH = "health"
    MAINTENANCE = "maintenance"
    BACKUP = "backup"
    ROLES = "roles"
    MANAGE = "manage"
    STATS = "stats"

class AdminRole(str, Enum):
    """Роли администраторов"""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"
    SUPPORT = "support"
    VIEWER = "viewer"

class PermissionManager:
    """Менеджер прав доступа"""
    
    def __init__(self):
        self.permissions = ROLE_PERMISSIONS
    
    def has_permission(self, role: str, resource: str, action: str) -> bool:
        """Проверить наличие права"""
        return check_permission(role, resource, action)
    
    def get_role_permissions(self, role: str) -> Dict[str, List[str]]:
        """Получить все права роли"""
        return self.permissions.get(role, {})
    
    def get_user_resources(self, role: str) -> List[str]:
        """Получить список ресурсов доступных роли"""
        role_perms = self.get_role_permissions(role)
        return list(role_perms.keys())
    
    def get_resource_actions(self, role: str, resource: str) -> List[str]:
        """Получить список действий доступных роли для ресурса"""
        role_perms = self.get_role_permissions(role)
        return role_perms.get(resource, [])
    
    def can_access_resource(self, role: str, resource: str) -> bool:
        """Проверить доступ к ресурсу"""
        role_perms = self.get_role_permissions(role)
        return resource in role_perms and len(role_perms[resource]) > 0
    
    def get_all_permissions(self, role: str) -> Set[str]:
        """Получить все права в формате 'resource:action'"""
        permissions = set()
        role_perms = self.get_role_permissions(role)
        
        for resource, actions in role_perms.items():
            for action in actions:
                permissions.add(f"{resource}:{action}")
        
        return permissions
    
    def compare_roles(self, role1: str, role2: str) -> Dict[str, Any]:
        """Сравнить права двух ролей"""
        perms1 = self.get_all_permissions(role1)
        perms2 = self.get_all_permissions(role2)
        
        return {
            "role1_only": perms1 - perms2,
            "role2_only": perms2 - perms1,
            "common": perms1 & perms2,
            "role1_superior": perms1.issuperset(perms2),
            "role2_superior": perms2.issuperset(perms1)
        }
    
    def validate_role_change(self, current_role: str, new_role: str, actor_role: str) -> Dict[str, Any]:
        """Валидация смены роли"""
        errors = []
        
        # Суперадмин может менять любые роли
        if actor_role == AdminRole.SUPER_ADMIN:
            return {"valid": True, "errors": []}
        
        # Админ не может назначать суперадмина
        if new_role == AdminRole.SUPER_ADMIN and actor_role != AdminRole.SUPER_ADMIN:
            errors.append("Только суперадмин может назначать суперадминов")
        
        # Админ не может изменять роль другого админа или суперадмина
        if actor_role == AdminRole.ADMIN:
            if current_role in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]:
                errors.append("Админ не может изменять роли других администраторов")
        
        # Модератор и ниже не могут менять роли
        if actor_role in [AdminRole.MODERATOR, AdminRole.SUPPORT, AdminRole.VIEWER]:
            errors.append("Недостаточно прав для изменения ролей")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

# Глобальный экземпляр менеджера
permission_manager = PermissionManager()

def require_permissions(*required_perms: str):
    """
    Декоратор для проверки множественных прав
    
    Args:
        required_perms: Права в формате 'resource:action'
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Получаем текущего админа из kwargs или dependencies
            current_admin = kwargs.get('current_admin')
            if not current_admin:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user_role = current_admin.get("role", "viewer")
            
            # Суперадмин имеет все права
            if user_role == AdminRole.SUPER_ADMIN:
                return await func(*args, **kwargs)
            
            # Проверяем каждое требуемое право
            for perm in required_perms:
                try:
                    resource, action = perm.split(":", 1)
                except ValueError:
                    raise ValueError(f"Invalid permission format: {perm}. Use 'resource:action'")
                
                if not permission_manager.has_permission(user_role, resource, action):
                    logger.warning(
                        f"Access denied",
                        admin_id=current_admin.get("admin_id"),
                        role=user_role,
                        required_permission=perm
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Permission required: {perm}"
                    )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def check_admin_permissions(admin_data: Dict[str, Any], resource: str, action: str) -> bool:
    """Проверить права администратора"""
    role = admin_data.get("role", "viewer")
    return permission_manager.has_permission(role, resource, action)

def filter_admin_menu(role: str) -> List[Dict[str, Any]]:
    """Фильтровать меню админки по правам роли"""
    menu_items = [
        {
            "key": "dashboard",
            "title": "Dashboard",
            "icon": "dashboard",
            "path": "/dashboard",
            "required_permission": None  # Доступен всем
        },
        {
            "key": "users",
            "title": "Users",
            "icon": "users",
            "path": "/users",
            "required_permission": "users:view"
        },
        {
            "key": "downloads",
            "title": "Downloads",
            "icon": "download",
            "path": "/downloads",
            "required_permission": "downloads:view"
        },
        {
            "key": "analytics",
            "title": "Analytics",
            "icon": "analytics",
            "path": "/analytics",
            "required_permission": "analytics:view"
        },
        {
            "key": "channels",
            "title": "Channels",
            "icon": "channels",
            "path": "/channels",
            "required_permission": "channels:view"
        },
        {
            "key": "broadcast",
            "title": "Broadcast",
            "icon": "broadcast",
            "path": "/broadcast",
            "required_permission": "broadcast:view"
        },
        {
            "key": "payments",
            "title": "Payments",
            "icon": "payments",
            "path": "/payments",
            "required_permission": "payments:view"
        },
        {
            "key": "settings",
            "title": "Settings",
            "icon": "settings",
            "path": "/settings",
            "required_permission": "settings:view"
        },
        {
            "key": "system",
            "title": "System",
            "icon": "system",
            "path": "/system",
            "required_permission": "system:health"
        },
        {
            "key": "admins",
            "title": "Admins",
            "icon": "admin",
            "path": "/admins",
            "required_permission": "admin:view"
        }
    ]
    
    # Фильтруем пункты меню по правам
    filtered_menu = []
    for item in menu_items:
        if item["required_permission"] is None:
            # Пункт доступен всем
            filtered_menu.append(item)
        else:
            # Проверяем права
            resource, action = item["required_permission"].split(":", 1)
            if permission_manager.has_permission(role, resource, action):
                filtered_menu.append(item)
    
    return filtered_menu

def get_action_permissions(role: str, resource: str) -> Dict[str, bool]:
    """Получить права на действия для ресурса"""
    actions = [
        Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE,
        Action.BAN, Action.PREMIUM, Action.RETRY, Action.CANCEL,
        Action.EXPORT, Action.SEND, Action.SCHEDULE, Action.REFUND,
        Action.LOGS, Action.HEALTH, Action.MAINTENANCE, Action.BACKUP,
        Action.ROLES, Action.MANAGE, Action.STATS
    ]
    
    permissions = {}
    for action in actions:
        permissions[action.value] = permission_manager.has_permission(role, resource, action.value)
    
    return permissions

def validate_bulk_action(role: str, resource: str, action: str, count: int) -> Dict[str, Any]:
    """Валидация массовых операций"""
    errors = []
    
    # Проверяем базовое право
    if not permission_manager.has_permission(role, resource, action):
        errors.append(f"Нет прав на действие {action} для ресурса {resource}")
    
    # Ограничения для массовых операций
    max_bulk_counts = {
        AdminRole.SUPER_ADMIN: 10000,
        AdminRole.ADMIN: 1000,
        AdminRole.MODERATOR: 100,
        AdminRole.SUPPORT: 10,
        AdminRole.VIEWER: 0
    }
    
    max_count = max_bulk_counts.get(role, 0)
    if count > max_count:
        errors.append(f"Превышен лимит массовых операций для роли {role}: {max_count}")
    
    # Дополнительные ограничения для критических действий
    critical_actions = [Action.DELETE, Action.BAN]
    if action in [a.value for a in critical_actions]:
        critical_max = max_count // 10  # В 10 раз меньше для критических действий
        if count > critical_max:
            errors.append(f"Превышен лимит для критического действия {action}: {critical_max}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "max_allowed": max_count
    }

def get_resource_summary(role: str) -> Dict[str, Dict[str, Any]]:
    """Получить сводку доступов по всем ресурсам"""
    resources = [r.value for r in Resource]
    summary = {}
    
    for resource in resources:
        if permission_manager.can_access_resource(role, resource):
            actions = permission_manager.get_resource_actions(role, resource)
            summary[resource] = {
                "accessible": True,
                "actions": actions,
                "action_count": len(actions),
                "can_view": Action.VIEW.value in actions,
                "can_modify": any(a in actions for a in [Action.CREATE.value, Action.EDIT.value, Action.DELETE.value])
            }
        else:
            summary[resource] = {
                "accessible": False,
                "actions": [],
                "action_count": 0,
                "can_view": False,
                "can_modify": False
            }
    
    return summary

def audit_permission_change(
    admin_id: int,
    target_admin_id: int,
    old_role: str,
    new_role: str,
    actor_role: str
) -> Dict[str, Any]:
    """Аудит изменения прав"""
    
    # Получаем изменения в правах
    old_perms = permission_manager.get_all_permissions(old_role)
    new_perms = permission_manager.get_all_permissions(new_role)
    
    gained_perms = new_perms - old_perms
    lost_perms = old_perms - new_perms
    
    audit_record = {
        "timestamp": "2024-01-01T00:00:00Z",  # Заглушка
        "actor_admin_id": admin_id,
        "target_admin_id": target_admin_id,
        "actor_role": actor_role,
        "old_role": old_role,
        "new_role": new_role,
        "permissions_gained": list(gained_perms),
        "permissions_lost": list(lost_perms),
        "impact_level": _calculate_impact_level(gained_perms, lost_perms),
        "requires_approval": _requires_approval(old_role, new_role, actor_role)
    }
    
    logger.info(
        "Permission change audited",
        **audit_record
    )
    
    return audit_record

def _calculate_impact_level(gained_perms: Set[str], lost_perms: Set[str]) -> str:
    """Вычислить уровень воздействия изменения прав"""
    critical_perms = {
        "admin:create", "admin:delete", "admin:roles",
        "system:maintenance", "system:backup",
        "payments:refund", "users:delete"
    }
    
    # Проверяем критические права
    gained_critical = gained_perms & critical_perms
    lost_critical = lost_perms & critical_perms
    
    if gained_critical or lost_critical:
        return "critical"
    
    # Проверяем количество изменений
    total_changes = len(gained_perms) + len(lost_perms)
    
    if total_changes > 10:
        return "high"
    elif total_changes > 5:
        return "medium"
    else:
        return "low"

def _requires_approval(old_role: str, new_role: str, actor_role: str) -> bool:
    """Определить нужно ли одобрение для изменения роли"""
    
    # Назначение суперадмина всегда требует одобрения
    if new_role == AdminRole.SUPER_ADMIN:
        return True
    
    # Понижение админа требует одобрения
    if old_role == AdminRole.ADMIN and new_role != AdminRole.ADMIN:
        return True
    
    # Модератор не может самостоятельно повышать роли
    if actor_role in [AdminRole.MODERATOR, AdminRole.SUPPORT] and new_role in [AdminRole.ADMIN, AdminRole.SUPER_ADMIN]:
        return True
    
    return False

class PermissionContext:
    """Контекст для проверки прав в определенной ситуации"""
    
    def __init__(self, admin_data: Dict[str, Any]):
        self.admin_data = admin_data
        self.role = admin_data.get("role", "viewer")
        self.admin_id = admin_data.get("admin_id")
    
    def can(self, resource: str, action: str) -> bool:
        """Проверить право"""
        return permission_manager.has_permission(self.role, resource, action)
    
    def ensure(self, resource: str, action: str) -> None:
        """Проверить право или вызвать исключение"""
        if not self.can(resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {resource}:{action}"
            )
    
    def filter_items(self, items: List[Dict[str, Any]], required_permission: str) -> List[Dict[str, Any]]:
        """Фильтровать элементы по правам"""
        if not required_permission:
            return items
        
        resource, action = required_permission.split(":", 1)
        if self.can(resource, action):
            return items
        else:
            return []
    
    def get_accessible_resources(self) -> List[str]:
        """Получить список доступных ресурсов"""
        return permission_manager.get_user_resources(self.role)
    
    def is_super_admin(self) -> bool:
        """Проверить является ли суперадмином"""
        return self.role == AdminRole.SUPER_ADMIN
    
    def is_admin_or_higher(self) -> bool:
        """Проверить является ли админом или выше"""
        return self.role in [AdminRole.SUPER_ADMIN, AdminRole.ADMIN]