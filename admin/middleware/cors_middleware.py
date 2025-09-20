"""
VideoBot Pro - CORS Middleware
Настройка CORS для админ панели
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from ..config import admin_settings

logger = structlog.get_logger(__name__)

def setup_cors(app: FastAPI):
    """
    Настройка CORS middleware для админ панели
    """
    
    # Определяем разрешенные origins в зависимости от окружения
    if admin_settings.ADMIN_SECRET_KEY.startswith("dev"):
        # Development режим - разрешаем localhost
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:8080"
        ]
    else:
        # Production режим - только настроенные домены
        allowed_origins = admin_settings.CORS_ORIGINS
    
    logger.info(f"CORS configured for origins: {allowed_origins}")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=admin_settings.CORS_CREDENTIALS,
        allow_methods=admin_settings.CORS_METHODS,
        allow_headers=admin_settings.CORS_HEADERS,
        expose_headers=[
            "X-Total-Count",
            "X-Page-Count", 
            "X-Current-Page",
            "X-Per-Page",
            "X-Admin-Version"
        ]
    )