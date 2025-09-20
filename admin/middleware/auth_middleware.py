"""
VideoBot Pro - Auth Middleware
Middleware для проверки аутентификации администраторов
"""

from typing import Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
import structlog

from ..config import admin_settings

logger = structlog.get_logger(__name__)

class AuthMiddleware:
    """
    Middleware для обработки аутентификации
    """
    
    # Публичные пути, не требующие аутентификации
    PUBLIC_PATHS = {
        "/health",
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/auth/reset-password",
        "/api/auth/verify-invite",
        "/api/auth/accept-invite",
        "/",
        "/static",
        "/favicon.ico"
    }
    
    # Пути API документации (только в dev режиме)
    DEV_PATHS = {
        "/api/docs",
        "/api/redoc", 
        "/api/openapi.json"
    }
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Обработка HTTP запроса"""
        
        try:
            # Проверяем, является ли путь публичным
            if self._is_public_path(request.url.path):
                return await call_next(request)
            
            # Проверяем, является ли это статический файл
            if self._is_static_file(request.url.path):
                return await call_next(request)
            
            # Проверяем dev пути в режиме разработки
            if not admin_settings.ADMIN_SECRET_KEY.startswith("prod") and self._is_dev_path(request.url.path):
                return await call_next(request)
            
            # Для API endpoints проверяем токен в headers
            if request.url.path.startswith("/api/"):
                auth_header = request.headers.get("Authorization")
                
                if not auth_header:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={
                            "error": "Authorization header required",
                            "detail": "Please provide a valid Bearer token"
                        }
                    )
                
                # Проверяем формат Bearer токена
                if not auth_header.startswith("Bearer "):
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={
                            "error": "Invalid authorization format",
                            "detail": "Authorization header must be: Bearer <token>"
                        }
                    )
            
            # Проверяем rate limiting
            if admin_settings.RATE_LIMIT_ENABLED:
                rate_limit_result = await self._check_rate_limit(request)
                if rate_limit_result:
                    return rate_limit_result
            
            # Добавляем security headers
            response = await call_next(request)
            self._add_security_headers(response)
            
            return response
            
        except Exception as e:
            logger.error(f"Auth middleware error: {e}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal server error",
                    "detail": "Authentication middleware failed"
                }
            )
    
    def _is_public_path(self, path: str) -> bool:
        """Проверить, является ли путь публичным"""
        # Точное совпадение
        if path in self.PUBLIC_PATHS:
            return True
        
        # Проверяем префиксы
        for public_path in self.PUBLIC_PATHS:
            if path.startswith(public_path + "/") or path.startswith(public_path):
                return True
        
        return False
    
    def _is_static_file(self, path: str) -> bool:
        """Проверить, является ли файл статическим"""
        static_extensions = {
            ".js", ".css", ".html", ".png", ".jpg", ".jpeg", 
            ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", 
            ".eot", ".map", ".json"
        }
        
        return any(path.endswith(ext) for ext in static_extensions)
    
    def _is_dev_path(self, path: str) -> bool:
        """Проверить, является ли путь dev-путем"""
        return any(path.startswith(dev_path) for dev_path in self.DEV_PATHS)
    
    async def _check_rate_limit(self, request: Request) -> Optional[JSONResponse]:
        """
        Проверка rate limiting
        TODO: Реализовать с использованием Redis
        """
        # Пока что просто заглушка
        # В будущем здесь будет проверка через Redis
        return None
    
    def _add_security_headers(self, response: Response):
        """Добавить security headers"""
        for header, value in admin_settings.SECURITY_HEADERS.items():
            response.headers[header] = value
        
        # CORS headers (если нужно)
        if hasattr(response, 'headers'):
            response.headers["X-Admin-Version"] = "2.1.0"