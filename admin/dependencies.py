"""
VideoBot Pro - Admin Dependencies
FastAPI зависимости для админ панели
"""

from typing import Optional, Dict, Any, Annotated
from fastapi import Depends, HTTPException, status, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import AsyncSession
import structlog

from shared.services.database import get_db_session
from shared.services.auth import AuthService
from shared.services.analytics import AnalyticsService
from shared.models import AdminUser
from .config import admin_settings, get_user_permissions, check_permission

logger = structlog.get_logger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)

class PaginationParams:
    """Параметры пагинации"""
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Номер страницы"),
        per_page: int = Query(20, ge=1, le=100, description="Элементов на странице")
    ):
        self.page = page
        self.per_page = per_page

async def get_auth_service() -> AuthService:
    """Получить сервис аутентификации"""
    try:
        return AuthService()
    except Exception as e:
        logger.error(f"Failed to get auth service: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable"
        )

async def get_analytics_service() -> AnalyticsService:
    """Получить сервис аналитики"""
    try:
        return AnalyticsService()
    except Exception as e:
        logger.error(f"Failed to get analytics service: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics service unavailable"
        )

async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> Dict[str, Any]:
    """
    Получить текущего администратора из JWT токена
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        # Проверяем и декодируем токен
        payload = auth_service.verify_admin_token(credentials.credentials)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Проверяем, что токен не отозван
        if auth_service.is_token_revoked(credentials.credentials):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Получаем информацию об администраторе из токена
        admin_data = {
            "admin_id": payload.get("admin_id"),
            "username": payload.get("username"),
            "role": payload.get("role"),
            "permissions": get_user_permissions(payload.get("role", "viewer")),
            "is_super_admin": payload.get("role") == "super_admin",
            "token_exp": payload.get("exp")
        }
        
        return admin_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current admin: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"}
        )

async def get_admin_user(
    current_admin: Dict[str, Any] = Depends(get_current_admin)
) -> AdminUser:
    """
    Получить полную модель администратора из БД
    """
    try:
        async with get_db_session() as session:
            admin = await session.get(AdminUser, current_admin["admin_id"])
            
            if not admin or not admin.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Admin account is inactive"
                )
            
            return admin
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get admin user"
        )

def require_permission(resource: str, action: str = "view"):
    """
    Декоратор для проверки прав доступа
    
    Args:
        resource: Ресурс (users, downloads, analytics, etc.)
        action: Действие (view, create, edit, delete, etc.)
    """
    def permission_checker(
        current_admin: Dict[str, Any] = Depends(get_current_admin)
    ) -> Dict[str, Any]:
        user_role = current_admin.get("role", "viewer")
        
        # Суперадмин имеет все права
        if user_role == "super_admin":
            return current_admin
        
        # Проверяем права доступа
        if not check_permission(user_role, resource, action):
            logger.warning(
                f"Access denied",
                admin_id=current_admin.get("admin_id"),
                role=user_role,
                resource=resource,
                action=action
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for {resource}:{action}"
            )
        
        return current_admin
    
    return permission_checker

async def get_pagination(
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Элементов на странице")
) -> PaginationParams:
    """Получить параметры пагинации"""
    return PaginationParams(page=page, per_page=per_page)

async def get_request_info(request: Request) -> Dict[str, Any]:
    """Получить информацию о запросе"""
    return {
        "ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers)
    }

def rate_limit(requests_per_minute: int = 60):
    """
    Rate limiting dependency
    
    Args:
        requests_per_minute: Максимум запросов в минуту
    """
    async def rate_limiter(
        request: Request,
        current_admin: Dict[str, Any] = Depends(get_current_admin)
    ):
        if not admin_settings.RATE_LIMIT_ENABLED:
            return
        
        # TODO: Реализовать rate limiting через Redis
        # Пока что просто пропускаем
        pass
    
    return rate_limiter

async def validate_admin_session(
    current_admin: Dict[str, Any] = Depends(get_current_admin),
    auth_service: AuthService = Depends(get_auth_service)
) -> Dict[str, Any]:
    """
    Проверить валидность сессии администратора
    """
    try:
        admin_id = current_admin["admin_id"]
        
        # Проверяем активность администратора в БД
        async with get_db_session() as session:
            admin = await session.get(AdminUser, admin_id)
            
            if not admin:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Admin user not found"
                )
            
            if not admin.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Admin account is disabled"
                )
            
            # Обновляем время последней активности
            admin.update_last_activity()
            await session.commit()
        
        return current_admin
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating admin session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session validation failed"
        )

def require_super_admin():
    """Требовать права суперадмина"""
    def super_admin_checker(
        current_admin: Dict[str, Any] = Depends(get_current_admin)
    ) -> Dict[str, Any]:
        if not current_admin.get("is_super_admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Super admin access required"
            )
        return current_admin
    
    return super_admin_checker

def require_role(*allowed_roles: str):
    """
    Требовать определенную роль
    
    Args:
        allowed_roles: Список разрешенных ролей
    """
    def role_checker(
        current_admin: Dict[str, Any] = Depends(get_current_admin)
    ) -> Dict[str, Any]:
        user_role = current_admin.get("role")
        
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {', '.join(allowed_roles)}"
            )
        
        return current_admin
    
    return role_checker

async def get_optional_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> Optional[Dict[str, Any]]:
    """
    Получить администратора если токен предоставлен (опционально)
    """
    if not credentials:
        return None
    
    try:
        return await get_current_admin(credentials, auth_service)
    except HTTPException:
        return None

# Commonly used permission dependencies
require_user_view = require_permission("users", "view")
require_user_edit = require_permission("users", "edit")
require_user_ban = require_permission("users", "ban")
require_user_premium = require_permission("users", "premium")
require_user_delete = require_permission("users", "delete")

require_downloads_view = require_permission("downloads", "view")
require_downloads_retry = require_permission("downloads", "retry")
require_downloads_cancel = require_permission("downloads", "cancel")

require_analytics_view = require_permission("analytics", "view")
require_analytics_export = require_permission("analytics", "export")

require_system_stats = require_permission("system", "stats")
require_system_maintenance = require_permission("system", "maintenance")

require_finance_view = require_permission("payments", "view")
require_finance_manage = require_permission("payments", "manage")

require_channel_manage = require_permission("channels", "manage")
require_channel_delete = require_permission("channels", "delete")

require_broadcast_create = require_permission("broadcast", "create")
require_broadcast_send = require_permission("broadcast", "send")

# Type annotations for commonly used dependencies
CurrentAdmin = Annotated[Dict[str, Any], Depends(get_current_admin)]
AdminUser = Annotated[AdminUser, Depends(get_admin_user)]
Pagination = Annotated[PaginationParams, Depends(get_pagination)]
RequestInfo = Annotated[Dict[str, Any], Depends(get_request_info)]