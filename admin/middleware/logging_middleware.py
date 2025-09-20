"""
VideoBot Pro - Logging Middleware
Middleware для логирования HTTP запросов
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import structlog

from ..config import admin_settings

logger = structlog.get_logger(__name__)

class LoggingMiddleware:
    """
    Middleware для логирования HTTP запросов и ответов
    """
    
    # Пути, которые не нужно логировать (слишком много шума)
    SKIP_LOGGING_PATHS = {
        "/health",
        "/metrics", 
        "/favicon.ico"
    }
    
    # Чувствительные заголовки, которые нужно скрыть
    SENSITIVE_HEADERS = {
        "authorization",
        "cookie",
        "x-api-key",
        "x-auth-token"
    }
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Обработка HTTP запроса с логированием"""
        
        # Генерируем уникальный ID запроса
        request_id = str(uuid.uuid4())[:8]
        
        # Добавляем request_id в контекст
        request.state.request_id = request_id
        
        # Проверяем, нужно ли логировать этот запрос
        if self._should_skip_logging(request.url.path):
            return await call_next(request)
        
        # Начинаем измерение времени
        start_time = time.time()
        
        # Логируем входящий запрос
        if admin_settings.LOG_REQUESTS:
            await self._log_request(request, request_id)
        
        try:
            # Выполняем запрос
            response = await call_next(request)
            
            # Вычисляем время выполнения
            process_time = time.time() - start_time
            
            # Добавляем headers в ответ
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}"
            
            # Логируем ответ
            if admin_settings.LOG_RESPONSES or response.status_code >= 400:
                await self._log_response(request, response, process_time, request_id)
            
            return response
            
        except Exception as e:
            # Логируем ошибку
            process_time = time.time() - start_time
            
            logger.error(
                "Request failed",
                request_id=request_id,
                method=request.method,
                url=str(request.url),
                error=str(e),
                process_time=round(process_time * 1000, 2),
                client_ip=self._get_client_ip(request)
            )
            
            # Возвращаем стандартную ошибку
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "request_id": request_id
                },
                headers={"X-Request-ID": request_id}
            )
    
    def _should_skip_logging(self, path: str) -> bool:
        """Проверить, нужно ли пропускать логирование"""
        return any(path.startswith(skip_path) for skip_path in self.SKIP_LOGGING_PATHS)
    
    async def _log_request(self, request: Request, request_id: str):
        """Логировать входящий запрос"""
        
        # Получаем информацию о клиенте
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "Unknown")
        
        # Получаем размер тела запроса
        content_length = request.headers.get("content-length")
        
        # Фильтруем заголовки
        headers = self._filter_sensitive_headers(dict(request.headers))
        
        logger.info(
            "HTTP request",
            request_id=request_id,
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            query_params=dict(request.query_params) if request.query_params else None,
            client_ip=client_ip,
            user_agent=user_agent,
            content_length=content_length,
            headers=headers if admin_settings.LOG_REQUESTS else None
        )
    
    async def _log_response(self, request: Request, response: Response, process_time: float, request_id: str):
        """Логировать ответ"""
        
        # Определяем уровень логирования по статус коду
        status_code = response.status_code
        
        if status_code >= 500:
            log_level = "error"
        elif status_code >= 400:
            log_level = "warning"
        else:
            log_level = "info"
        
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "status_code": status_code,
            "process_time_ms": round(process_time * 1000, 2),
            "client_ip": self._get_client_ip(request),
            "content_length": response.headers.get("content-length")
        }
        
        # Добавляем заголовки ответа если включено детальное логирование
        if admin_settings.LOG_RESPONSES:
            log_data["response_headers"] = dict(response.headers)
        
        # Логируем с соответствующим уровнем
        if log_level == "error":
            logger.error("HTTP response", **log_data)
        elif log_level == "warning":
            logger.warning("HTTP response", **log_data)
        else:
            logger.info("HTTP response", **log_data)
    
    def _get_client_ip(self, request: Request) -> str:
        """Получить IP адрес клиента"""
        # Проверяем X-Forwarded-For (за прокси/балансировщиком)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Проверяем X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Используем прямое подключение
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _filter_sensitive_headers(self, headers: dict) -> dict:
        """Фильтровать чувствительные заголовки"""
        filtered = {}
        
        for key, value in headers.items():
            if key.lower() in self.SENSITIVE_HEADERS:
                filtered[key] = "[FILTERED]"
            else:
                filtered[key] = value
        
        return filtered