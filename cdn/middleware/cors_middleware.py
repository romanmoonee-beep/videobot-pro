"""
VideoBot Pro - CDN CORS Middleware
Middleware для настройки CORS заголовков
"""

import structlog
from typing import List, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

class CORSMiddleware(BaseHTTPMiddleware):
    """Кастомный CORS middleware для CDN"""
    
    def __init__(
        self,
        app,
        allow_origins: List[str] = None,
        allow_methods: List[str] = None,
        allow_headers: List[str] = None,
        allow_credentials: bool = True,
        expose_headers: List[str] = None,
        max_age: int = 600
    ):
        super().__init__(app)
        
        # Настройки CORS
        self.allow_origins = allow_origins or self._get_default_origins()
        self.allow_methods = allow_methods or [
            "GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"
        ]
        self.allow_headers = allow_headers or [
            "Accept", "Accept-Language", "Content-Language", "Content-Type",
            "Authorization", "X-Access-Token", "X-Request-ID", "Range",
            "Cache-Control", "If-None-Match", "If-Modified-Since"
        ]
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers or [
            "Content-Range", "Content-Length", "Accept-Ranges",
            "X-Process-Time", "X-Request-ID", "X-RateLimit-Limit",
            "X-RateLimit-Remaining", "X-RateLimit-Reset"
        ]
        self.max_age = max_age
    
    async def dispatch(self, request: Request, call_next):
        """Обработка запроса с добавлением CORS заголовков"""
        
        # Получаем origin из заголовков
        origin = request.headers.get("origin")
        
        # Обрабатываем preflight запросы
        if request.method == "OPTIONS":
            return self._build_preflight_response(origin)
        
        # Выполняем основной запрос
        response = await call_next(request)
        
        # Добавляем CORS заголовки к ответу
        self._add_cors_headers(response, origin)
        
        return response
    
    def _get_default_origins(self) -> List[str]:
        """Получение списка разрешенных origins по умолчанию"""
        origins = ["*"]  # В продакшене следует ограничить
        
        # Добавляем домены из настроек
        if hasattr(settings, 'ALLOWED_ORIGINS'):
            origins.extend(settings.ALLOWED_ORIGINS)
        
        # Добавляем localhost для разработки
        if settings.DEBUG:
            origins.extend([
                "http://localhost:3000",
                "http://localhost:8080",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8080"
            ])
        
        return origins
    
    def _is_origin_allowed(self, origin: str) -> bool:
        """Проверка, разрешен ли origin"""
        if not origin:
            return True
        
        # Проверяем точные совпадения
        if origin in self.allow_origins:
            return True
        
        # Проверяем wildcard
        if "*" in self.allow_origins:
            return True
        
        # Проверяем паттерны (простая реализация)
        for allowed_origin in self.allow_origins:
            if allowed_origin.endswith("*"):
                pattern = allowed_origin[:-1]
                if origin.startswith(pattern):
                    return True
        
        return False
    
    def _build_preflight_response(self, origin: str) -> StarletteResponse:
        """Создание ответа на preflight запрос"""
        headers = {}
        
        # Проверяем origin
        if self._is_origin_allowed(origin):
            headers["Access-Control-Allow-Origin"] = origin or "*"
        
        # Добавляем остальные заголовки
        if self.allow_credentials:
            headers["Access-Control-Allow-Credentials"] = "true"
        
        headers["Access-Control-Allow-Methods"] = ", ".join(self.allow_methods)
        headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)
        headers["Access-Control-Max-Age"] = str(self.max_age)
        
        if self.expose_headers:
            headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
        
        return StarletteResponse(
            status_code=200,
            headers=headers
        )
    
    def _add_cors_headers(self, response: Response, origin: str):
        """Добавление CORS заголовков к ответу"""
        try:
            # Проверяем origin
            if self._is_origin_allowed(origin):
                response.headers["Access-Control-Allow-Origin"] = origin or "*"
            
            # Добавляем credentials если разрешено
            if self.allow_credentials:
                response.headers["Access-Control-Allow-Credentials"] = "true"
            
            # Добавляем exposed headers
            if self.expose_headers:
                response.headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
            
            # Добавляем Vary заголовок для кэширования
            vary_headers = ["Origin"]
            if "Vary" in response.headers:
                existing_vary = response.headers["Vary"]
                vary_headers.extend([h.strip() for h in existing_vary.split(",") if h.strip()])
            
            response.headers["Vary"] = ", ".join(set(vary_headers))
            
        except Exception as e:
            logger.error(f"Error adding CORS headers: {e}")
    
    def configure_for_development(self):
        """Настройка для разработки"""
        self.allow_origins = ["*"]
        self.allow_credentials = True
        logger.info("CORS configured for development (allow all origins)")
    
    def configure_for_production(self, allowed_domains: List[str]):
        """Настройка для продакшена"""
        self.allow_origins = allowed_domains
        self.allow_credentials = True
        logger.info(f"CORS configured for production: {allowed_domains}")

# Создание экземпляра middleware для использования в приложении
def create_cors_middleware():
    """Создание CORS middleware с настройками по умолчанию"""
    if settings.DEBUG:
        # Разработка - разрешаем все
        return CORSMiddleware(
            app=None,  # Будет установлено FastAPI
            allow_origins=["*"],
            allow_credentials=True
        )
    else:
        # Продакшен - ограничиваем домены
        allowed_origins = getattr(settings, 'ALLOWED_ORIGINS', [])
        return CORSMiddleware(
            app=None,
            allow_origins=allowed_origins,
            allow_credentials=True
        )