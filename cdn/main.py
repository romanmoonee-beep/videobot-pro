"""
VideoBot Pro - CDN Service Main Application
Основное приложение CDN сервиса для доставки файлов
"""

import asyncio
import logging
import structlog
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from shared import (
    settings, initialize_shared_components, cleanup_shared_components,
    DatabaseHealthCheck, get_shared_info
)
from .config import CDNConfig, cdn_config
from .api import files_router, auth_router, stats_router
from .middleware import AuthMiddleware, RateLimitMiddleware, LoggingMiddleware
from .services import FileService, CleanupService

# Настройка логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Starting VideoBot Pro CDN Service...")
    
    try:
        # Инициализация shared компонентов
        await initialize_shared_components()
        
        # Инициализация CDN конфигурации
        await cdn_config.initialize()
        
        # Инициализация сервисов
        file_service = FileService()
        cleanup_service = CleanupService()
        
        await file_service.initialize()
        await cleanup_service.initialize()
        
        # Сохраняем сервисы в состояние приложения
        app.state.file_service = file_service
        app.state.cleanup_service = cleanup_service
        
        # Запускаем фоновые задачи
        cleanup_task = asyncio.create_task(cleanup_service.start_cleanup_scheduler())
        app.state.cleanup_task = cleanup_task
        
        logger.info("CDN Service started successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to start CDN service: {e}")
        raise
    finally:
        logger.info("Shutting down CDN Service...")
        
        # Останавливаем фоновые задачи
        if hasattr(app.state, 'cleanup_task'):
            app.state.cleanup_task.cancel()
            try:
                await app.state.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Очистка сервисов
        if hasattr(app.state, 'file_service'):
            await app.state.file_service.shutdown()
        if hasattr(app.state, 'cleanup_service'):
            await app.state.cleanup_service.shutdown()
        
        # Очистка shared компонентов
        await cleanup_shared_components()
        
        logger.info("CDN Service shutdown completed")

def create_app() -> FastAPI:
    """Создание FastAPI приложения"""
    app = FastAPI(
        title="VideoBot Pro CDN",
        description="Content Delivery Network для VideoBot Pro",
        version="2.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # В продакшене ограничить
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Gzip middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Кастомные middleware
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    
    # Подключение роутеров
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    
    # Статические файлы (для локального хранения)
    if settings.DEBUG:
        app.mount("/static", StaticFiles(directory="storage"), name="static")
    
    # Обработчики ошибок
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "status_code": exc.status_code,
                "timestamp": structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"]
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unexpected error: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "status_code": 500,
                "timestamp": structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"]
            }
        )
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Проверка здоровья CDN сервиса"""
        try:
            # Проверяем базу данных
            db_health = await DatabaseHealthCheck.check_connection()
            
            # Проверяем shared компоненты
            shared_info = get_shared_info()
            
            # Проверяем CDN конфигурацию
            cdn_health = await cdn_config.health_check()
            
            return {
                "status": "healthy",
                "service": "cdn",
                "version": "2.1.0",
                "timestamp": structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"],
                "checks": {
                    "database": db_health,
                    "shared_components": shared_info,
                    "cdn_config": cdn_health
                }
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"]
                }
            )
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "service": "VideoBot Pro CDN",
            "version": "2.1.0",
            "status": "running",
            "endpoints": {
                "health": "/health",
                "docs": "/docs" if settings.DEBUG else "disabled",
                "api": "/api/v1"
            }
        }
    
    return app

# Создаем приложение
app = create_app()

def main():
    """Главная функция запуска CDN сервиса"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO if not settings.DEBUG else logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    logger.info("Starting VideoBot Pro CDN Service...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"CDN Host: {settings.CDN_HOST}:{settings.CDN_PORT}")
    
    # Запуск сервера
    uvicorn.run(
        "cdn.main:app",
        host=settings.CDN_HOST,
        port=settings.CDN_PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug",
        access_log=True,
        server_header=False,
        date_header=False,
    )

if __name__ == "__main__":
    main()