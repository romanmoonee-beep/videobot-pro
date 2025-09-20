"""
VideoBot Pro - CDN Auth Middleware
Middleware для аутентификации запросов к CDN
"""

import structlog
from typing import Optional
from fastapi import Request, Response, HTTPException
from fastapi.security.utils import get_authorization_scheme_param
from starlette.middleware.base import BaseHTTPMiddleware

from shared.models.user import User
from shared.services.auth import auth_service

logger = structlog.get_logger(__name__)

class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для проверки аутентификации"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Пути, не требующие аутентификации
        self.public_paths = {
            "/health",
            "/",
            "/docs",
            "/redoc",
            "/openapi.json"
        }
        
        # Пути, требующие только базовой проверки токена
        self.basic_auth_paths = {
            "/api/v1/files/",  # Доступ к файлам
        }
        
        # Пути, требующие админских прав
        self.admin_paths = {
            "/api/v1/stats/",
            "/api/v1/auth/reset"
        }
    
    async def dispatch(self, request: Request, call_next):
        """Обработка запроса"""
        try:
            # Проверяем, нужна ли аутентификация
            if self._is_public_path(request.url.path):
                return await call_next(request)
            
            # Получаем токен из заголовка или параметра запроса
            token = self._extract_token(request)
            
            # Проверяем токен и получаем пользователя
            user = None
            if token:
                user = await self._validate_token(token, request)
            
            # Проверяем права доступа
            if not self._check_access_permissions(request.url.path, user):
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Добавляем пользователя в состояние запроса
            request.state.user = user
            request.state.authenticated = user is not None
            
            return await call_next(request)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Auth middleware error: {e}")
            raise HTTPException(status_code=500, detail="Authentication error")
    
    def _is_public_path(self, path: str) -> bool:
        """Проверка, является ли путь публичным"""
        return any(path.startswith(public_path) for public_path in self.public_paths)
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Извлечение токена из запроса"""
        # Проверяем заголовок Authorization
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, token = get_authorization_scheme_param(authorization)
            if scheme.lower() == "bearer":
                return token
        
        # Проверяем параметр запроса token
        token = request.query_params.get("token")
        if token:
            return token
        
        # Проверяем заголовок X-Access-Token
        token = request.headers.get("X-Access-Token")
        if token:
            return token
        
        return None
    
    async def _validate_token(self, token: str, request: Request) -> Optional[User]:
        """Валидация токена и получение пользователя"""
        try:
            # Проверяем обычный токен
            user = await auth_service.get_user_by_token(token)
            if user:
                return user
            
            # Проверяем CDN токен
            user = await auth_service.get_user_by_cdn_token(token)
            if user:
                return user
            
            # Проверяем токен доступа к файлу
            file_path = self._extract_file_path(request.url.path)
            if file_path:
                user = await auth_service.get_user_by_file_token(token, file_path)
                if user:
                    return user
            
            return None
            
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return None
    
    def _extract_file_path(self, url_path: str) -> Optional[str]:
        """Извлечение пути файла из URL"""
        if url_path.startswith("/api/v1/files/"):
            return url_path[14:]  # Убираем "/api/v1/files/"
        return None
    
    def _check_access_permissions(self, path: str, user: Optional[User]) -> bool:
        """Проверка прав доступа к пути"""
        # Публичные пути доступны всем
        if self._is_public_path(path):
            return True
        
        # Для админских путей требуется админ
        if any(path.startswith(admin_path) for admin_path in self.admin_paths):
            return user and user.user_type in ['admin', 'owner']
        
        # Для базовых путей требуется любой авторизованный пользователь
        if any(path.startswith(auth_path) for auth_path in self.basic_auth_paths):
            return user is not None
        
        # Остальные пути требуют аутентификации
        return user is not None
    
    async def _log_access_attempt(self, request: Request, user: Optional[User], success: bool):
        """Логирование попыток доступа"""
        try:
            client_ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("User-Agent", "unknown")
            
            log_data = {
                "path": request.url.path,
                "method": request.method,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "user_id": user.id if user else None,
                "user_type": user.user_type if user else None,
                "success": success
            }
            
            if success:
                logger.info("Access granted", **log_data)
            else:
                logger.warning("Access denied", **log_data)
                
        except Exception as e:
            logger.error(f"Access logging failed: {e}")