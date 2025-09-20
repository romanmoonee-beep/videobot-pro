"""
VideoBot Pro - Admin Panel Backend
FastAPI приложение для администрирования системы
"""

import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import structlog

from shared.config import initialize_services, shutdown_services, settings
from shared.services import get_service_status
from .config import admin_settings
from .middleware.auth_middleware import AuthMiddleware
from .middleware.cors_middleware import setup_cors
from .middleware.logging_middleware import LoggingMiddleware

# API роутеры
from .api import (
    auth_router,
    users_router,
    analytics_router,
    downloads_router,
    settings_router,
    channels_router,
    broadcast_router,
    payments_router,
    system_router
)

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info("Starting VideoBot Pro Admin Panel...")
    
    try:
        # Инициализируем shared сервисы
        services = await initialize_services()
        app.state.services = services
        
        # Проверяем статус сервисов
        service_status = get_service_status()
        logger.info("Service status", **service_status)
        
        # Создаем таблицы если нужно
        if services.get('database'):
            await services['database'].migrate_database()
        
        logger.info("Admin panel started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start admin panel: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down admin panel...")
    await shutdown_services()
    logger.info("Admin panel shutdown completed")

# Создаем FastAPI приложение
app = FastAPI(
    title="VideoBot Pro Admin API",
    description="Administration API for VideoBot Pro",
    version="2.1.0",
    docs_url="/api/docs" if not settings.is_production() else None,
    redoc_url="/api/redoc" if not settings.is_production() else None,
    openapi_url="/api/openapi.json" if not settings.is_production() else None,
    lifespan=lifespan
)

# Настройка CORS
setup_cors(app)

# Добавляем middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)

# Trusted hosts для production
if settings.is_production():
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["admin.videobot.com", "*.videobot.com"]
    )

# API роутеры
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users_router, prefix="/api/users", tags=["Users"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(downloads_router, prefix="/api/downloads", tags=["Downloads"])
app.include_router(settings_router, prefix="/api/settings", tags=["Settings"])
app.include_router(channels_router, prefix="/api/channels", tags=["Channels"])
app.include_router(broadcast_router, prefix="/api/broadcast", tags=["Broadcast"])
app.include_router(payments_router, prefix="/api/payments", tags=["Payments"])
app.include_router(system_router, prefix="/api/system", tags=["System"])

# Статические файлы для фронтенда
if admin_settings.STATIC_FILES_PATH:
    try:
        app.mount("/static", StaticFiles(directory=admin_settings.STATIC_FILES_PATH), name="static")
    except Exception as e:
        logger.warning(f"Could not mount static files: {e}")

# Health check endpoint
@app.get("/health", include_in_schema=False)
async def health_check():
    """Проверка состояния админ панели"""
    try:
        service_status = get_service_status()
        
        # Проверяем критичные сервисы
        critical_services = ['database']
        all_healthy = all(service_status.get(service, False) for service in critical_services)
        
        status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "services": service_status,
            "timestamp": "2024-01-01T00:00:00Z"  # Placeholder
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed"
        )

# Корневая страница (SPA)
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def read_root():
    """Главная страница админ панели"""
    try:
        # Пытаемся загрузить index.html фронтенда
        index_path = f"{admin_settings.STATIC_FILES_PATH}/index.html"
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            # Если фронтенд не собран, показываем заглушку
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>VideoBot Pro Admin</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .container { max-width: 600px; margin: 0 auto; }
                    .status { background: #e3f2fd; padding: 20px; border-radius: 8px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🚀 VideoBot Pro Admin Panel</h1>
                    <div class="status">
                        <h2>Backend is running!</h2>
                        <p>Frontend is not built yet. Please run <code>npm run build</code> in the frontend directory.</p>
                        <p><a href="/api/docs">📖 API Documentation</a></p>
                    </div>
                </div>
            </body>
            </html>
            """
    except Exception as e:
        logger.error(f"Error serving root page: {e}")
        return "<h1>VideoBot Pro Admin - Error loading page</h1>"

# Catch-all для SPA роутинга
@app.get("/{path:path}", response_class=HTMLResponse, include_in_schema=False)
async def catch_all(path: str):
    """Catch-all для SPA роутинга"""
    # Если это API запрос, возвращаем 404
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    # Для всех остальных путей возвращаем index.html (SPA)
    return await read_root()

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Обработчик 404 ошибок"""
    if request.url.path.startswith("/api/"):
        return {"error": "API endpoint not found", "path": request.url.path}
    
    # Для не-API запросов возвращаем главную страницу (SPA)
    return await read_root()

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Обработчик внутренних ошибок"""
    logger.error(f"Internal server error: {exc}")
    return {
        "error": "Internal server error",
        "message": "Something went wrong. Please try again later."
    }

# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request, call_next):
    """Логирование HTTP запросов"""
    start_time = asyncio.get_event_loop().time()
    
    response = await call_next(request)
    
    process_time = asyncio.get_event_loop().time() - start_time
    
    logger.info(
        "HTTP request",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code,
        process_time=round(process_time * 1000, 2)
    )
    
    return response

# Development server
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=admin_settings.ADMIN_HOST,
        port=admin_settings.ADMIN_PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug"
    )