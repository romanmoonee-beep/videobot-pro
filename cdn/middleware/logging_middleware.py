"""
VideoBot Pro - CDN Logging Middleware
Middleware для логирования запросов к CDN
"""

import time
import structlog
from datetime import datetime
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования HTTP запросов"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Пути, которые не нужно логировать подробно
        self.skip_detailed_logging = {
            '/health',
            '/metrics'
        }
        
        # Максимальный размер тела запроса для логирования
        self.max_body_size = 1024  # 1KB
    
    async def dispatch(self, request: Request, call_next):
        """Обработка запроса с логированием"""
        start_time = time.time()
        
        # Подготавливаем базовую информацию о запросе
        request_info = await self._prepare_request_info(request)
        
        # Логируем начало запроса
        if not self._should_skip_detailed_logging(request.url.path):
            logger.info("Request started", **request_info)
        
        try:
            # Выполняем запрос
            response = await call_next(request)
            
            # Вычисляем время выполнения
            process_time = time.time() - start_time
            
            # Подготавливаем информацию об ответе
            response_info = self._prepare_response_info(response, process_time)
            
            # Объединяем информацию
            log_data = {**request_info, **response_info}
            
            # Логируем результат
            if response.status_code >= 500:
                logger.error("Request failed", **log_data)
            elif response.status_code >= 400:
                logger.warning("Request error", **log_data)
            elif not self._should_skip_detailed_logging(request.url.path):
                logger.info("Request completed", **log_data)
            
            # Добавляем заголовки с временем выполнения
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Request-ID"] = request_info.get("request_id", "unknown")
            
            return response
            
        except Exception as e:
            # Логируем ошибки
            process_time = time.time() - start_time
            error_info = {
                **request_info,
                "error": str(e),
                "error_type": type(e).__name__,
                "process_time": process_time,
                "status_code": 500
            }
            
            logger.error("Request exception", **error_info)
            raise
    
    async def _prepare_request_info(self, request: Request) -> dict:
        """Подготовка информации о запросе"""
        try:
            # Базовая информация
            info = {
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Информация о клиенте
            if request.client:
                info["client_ip"] = request.client.host
                info["client_port"] = request.client.port
            
            # Заголовки (фильтруем чувствительные)
            headers = dict(request.headers)
            sensitive_headers = {'authorization', 'cookie', 'x-access-token'}
            
            filtered_headers = {}
            for key, value in headers.items():
                if key.lower() in sensitive_headers:
                    filtered_headers[key] = "***"
                else:
                    filtered_headers[key] = value
            
            info["headers"] = filtered_headers
            
            # User Agent
            info["user_agent"] = request.headers.get("user-agent", "unknown")
            
            # Referer
            referer = request.headers.get("referer")
            if referer:
                info["referer"] = referer
            
            # Реальный IP (через прокси)
            real_ip = (
                request.headers.get("x-real-ip") or
                request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            )
            if real_ip:
                info["real_ip"] = real_ip
            
            # Информация о пользователе (если доступна)
            user = getattr(request.state, 'user', None)
            if user:
                info["user_id"] = user.id
                info["user_type"] = user.user_type
                info["username"] = user.username
            
            # Генерируем ID запроса
            import uuid
            info["request_id"] = str(uuid.uuid4())[:8]
            
            # Размер контента
            content_length = request.headers.get("content-length")
            if content_length:
                info["content_length"] = int(content_length)
            
            # Тип контента
            content_type = request.headers.get("content-type")
            if content_type:
                info["content_type"] = content_type
            
            # Дополнительная информация для файловых запросов
            if request.url.path.startswith("/api/v1/files/"):
                info["file_path"] = request.url.path[14:]  # Убираем префикс
                
                # Range запросы
                range_header = request.headers.get("range")
                if range_header:
                    info["range_request"] = True
                    info["range"] = range_header
            
            return info
            
        except Exception as e:
            logger.error(f"Failed to prepare request info: {e}")
            return {
                "method": request.method,
                "path": request.url.path,
                "error": "failed_to_parse_request"
            }
    
    def _prepare_response_info(self, response: Response, process_time: float) -> dict:
        """Подготовка информации об ответе"""
        try:
            info = {
                "status_code": response.status_code,
                "process_time": round(process_time, 4)
            }
            
            # Размер ответа
            content_length = response.headers.get("content-length")
            if content_length:
                info["response_size"] = int(content_length)
            
            # Тип контента
            content_type = response.headers.get("content-type")
            if content_type:
                info["response_type"] = content_type
            
            # Заголовки кэширования
            cache_control = response.headers.get("cache-control")
            if cache_control:
                info["cache_control"] = cache_control
            
            # Информация о Range ответах
            content_range = response.headers.get("content-range")
            if content_range:
                info["content_range"] = content_range
                info["partial_response"] = True
            
            # Категоризация времени ответа
            if process_time > 10:
                info["performance"] = "very_slow"
            elif process_time > 5:
                info["performance"] = "slow"
            elif process_time > 1:
                info["performance"] = "normal"
            else:
                info["performance"] = "fast"
            
            return info
            
        except Exception as e:
            logger.error(f"Failed to prepare response info: {e}")
            return {
                "status_code": getattr(response, 'status_code', 500),
                "process_time": process_time,
                "error": "failed_to_parse_response"
            }
    
    def _should_skip_detailed_logging(self, path: str) -> bool:
        """Проверка, нужно ли пропустить подробное логирование"""
        return any(path.startswith(skip_path) for skip_path in self.skip_detailed_logging)
    
    async def _get_request_body(self, request: Request) -> Optional[str]:
        """Получение тела запроса для логирования (если небольшое)"""
        try:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.max_body_size:
                return f"<body too large: {content_length} bytes>"
            
            body = await request.body()
            if len(body) > self.max_body_size:
                return f"<body too large: {len(body)} bytes>"
            
            # Проверяем, что это текстовый контент
            content_type = request.headers.get("content-type", "")
            if any(ct in content_type.lower() for ct in ["json", "text", "xml", "form"]):
                return body.decode("utf-8", errors="replace")
            
            return f"<binary content: {len(body)} bytes>"
            
        except Exception as e:
            logger.error(f"Failed to read request body: {e}")
            return "<failed to read body>"