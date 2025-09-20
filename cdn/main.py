"""
VideoBot Pro - Updated CDN Main Application
Обновленное основное приложение CDN с интеграцией облачных хранилищ
"""

import asyncio
import logging
import structlog
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
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
from .storage_integration import cdn_storage_manager

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
    logger.info("Starting VideoBot Pro CDN Service with Cloud Integration...")
    
    try:
        # Инициализация shared компонентов
        await initialize_shared_components()
        
        # Инициализация CDN конфигурации
        await cdn_config.initialize()
        
        # Инициализация менеджера облачных хранилищ
        await cdn_storage_manager.initialize()
        
        # Инициализация сервисов
        file_service = FileService()
        cleanup_service = CleanupService()
        
        await file_service.initialize()
        await cleanup_service.initialize()
        
        # Сохраняем сервисы в состояние приложения
        app.state.file_service = file_service
        app.state.cleanup_service = cleanup_service
        app.state.storage_manager = cdn_storage_manager
        
        # Запускаем фоновые задачи
        cleanup_task = asyncio.create_task(cleanup_service.start_cleanup_scheduler())
        storage_health_task = asyncio.create_task(_storage_health_monitor())
        
        app.state.cleanup_task = cleanup_task
        app.state.storage_health_task = storage_health_task
        
        logger.info("CDN Service with Cloud Integration started successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to start CDN service: {e}")
        raise
    finally:
        logger.info("Shutting down CDN Service...")
        
        # Останавливаем фоновые задачи
        for task_name in ['cleanup_task', 'storage_health_task']:
            if hasattr(app.state, task_name):
                task = getattr(app.state, task_name)
                task.cancel()
                try:
                    await task
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

async def _storage_health_monitor():
    """Мониторинг здоровья хранилищ"""
    while True:
        try:
            await asyncio.sleep(300)  # Проверяем каждые 5 минут
            
            health = await cdn_storage_manager.get_storage_statistics()
            
            # Логируем состояние хранилищ
            if 'error' not in health:
                logger.info("Storage health check completed", **health)
            else:
                logger.warning("Storage health check failed", error=health['error'])
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Storage health monitor error: {e}")
            await asyncio.sleep(60)  # Ждем минуту при ошибке

def create_app() -> FastAPI:
    """Создание FastAPI приложения"""
    app = FastAPI(
        title="VideoBot Pro CDN",
        description="Content Delivery Network для VideoBot Pro с облачными хранилищами",
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
    
    # Дополнительные эндпоинты для управления облачными хранилищами
    @app.delete("/api/v1/admin/storage/file/{file_key:path}")
    async def admin_delete_file(request: Request, file_key: str):
        """Административное удаление файла из всех хранилищ"""
        try:
            user = getattr(request.state, 'user', None)
            if not user or user.user_type not in ['admin', 'owner']:
                raise HTTPException(status_code=403, detail="Admin access required")
            
            # Удаляем файл
            result = await cdn_storage_manager.delete_file(file_key, user)
            
            return {
                "success": result['success'],
                "file_key": file_key,
                "deletion_result": result,
                "timestamp": structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"]
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Admin file deletion failed: {e}")
            raise HTTPException(status_code=500, detail="File deletion failed")
    
    @app.get("/api/v1/admin/storage/health")
    async def get_storage_health(request: Request):
        """Проверка здоровья всех хранилищ"""
        try:
            user = getattr(request.state, 'user', None)
            if not user or user.user_type not in ['admin', 'owner']:
                raise HTTPException(status_code=403, detail="Admin access required")
            
            health_status = {}
            
            # Проверяем основное хранилище
            if cdn_storage_manager.primary_storage:
                try:
                    primary_health = await cdn_storage_manager.primary_storage.get_storage_stats()
                    health_status['primary_storage'] = {
                        'status': 'healthy',
                        'type': cdn_storage_manager.primary_storage.__class__.__name__,
                        'stats': primary_health
                    }
                except Exception as e:
                    health_status['primary_storage'] = {
                        'status': 'unhealthy',
                        'error': str(e)
                    }
            
            # Проверяем резервное хранилище
            if cdn_storage_manager.backup_storage:
                try:
                    backup_health = await cdn_storage_manager.backup_storage.get_storage_stats()
                    health_status['backup_storage'] = {
                        'status': 'healthy',
                        'type': cdn_storage_manager.backup_storage.__class__.__name__,
                        'stats': backup_health
                    }
                except Exception as e:
                    health_status['backup_storage'] = {
                        'status': 'unhealthy',
                        'error': str(e)
                    }
            
            # Проверяем локальное хранилище
            try:
                local_stats = await app.state.file_service._get_cache_statistics()
                health_status['local_storage'] = {
                    'status': 'healthy',
                    'type': 'LocalStorage',
                    'stats': local_stats
                }
            except Exception as e:
                health_status['local_storage'] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
            
            # Определяем общий статус
            healthy_count = sum(1 for storage in health_status.values() if storage.get('status') == 'healthy')
            total_count = len(health_status)
            
            overall_status = 'healthy'
            if healthy_count == 0:
                overall_status = 'critical'
            elif healthy_count < total_count:
                overall_status = 'degraded'
            
            return {
                'overall_status': overall_status,
                'healthy_storages': healthy_count,
                'total_storages': total_count,
                'storages': health_status,
                'timestamp': structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"]
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Storage health check failed: {e}")
            raise HTTPException(status_code=500, detail="Health check failed")
    
    @app.post("/api/v1/admin/migrate-to-cloud")
    async def migrate_local_files_to_cloud(request: Request):
        """Миграция локальных файлов в облачное хранилище"""
        try:
            user = getattr(request.state, 'user', None)
            if not user or user.user_type not in ['admin', 'owner']:
                raise HTTPException(status_code=403, detail="Admin access required")
            
            migration_result = {
                'started_at': structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"],
                'files_found': 0,
                'files_migrated': 0,
                'files_failed': 0,
                'errors': []
            }
            
            # Находим все локальные файлы
            local_files = []
            for file_path in cdn_config.storage_path.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith('.'):
                    relative_path = file_path.relative_to(cdn_config.storage_path)
                    local_files.append({
                        'path': str(relative_path),
                        'full_path': str(file_path),
                        'size': file_path.stat().st_size
                    })
            
            migration_result['files_found'] = len(local_files)
            
            # Мигрируем файлы порциями
            for file_info in local_files:
                try:
                    # Загружаем в облачное хранилище
                    upload_result = await cdn_storage_manager.upload_file(
                        local_file_path=file_info['full_path'],
                        file_key=file_info['path'],
                        user=user,
                        metadata={
                            'migrated_from_local': 'true',
                            'migration_date': structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"],
                            'original_size': str(file_info['size'])
                        }
                    )
                    
                    if upload_result.get('success'):
                        migration_result['files_migrated'] += 1
                        
                        # Удаляем локальный файл после успешной загрузки
                        try:
                            import os
                            os.unlink(file_info['full_path'])
                        except Exception as e:
                            logger.warning(f"Failed to delete local file after migration: {e}")
                    else:
                        migration_result['files_failed'] += 1
                        migration_result['errors'].append({
                            'file': file_info['path'],
                            'error': upload_result.get('error', 'Unknown error')
                        })
                        
                except Exception as e:
                    migration_result['files_failed'] += 1
                    migration_result['errors'].append({
                        'file': file_info['path'],
                        'error': str(e)
                    })
            
            migration_result['completed_at'] = structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"]
            
            return {
                'success': True,
                'migration_result': migration_result
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"File migration failed: {e}")
            raise HTTPException(status_code=500, detail="Migration failed")
    
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
            
            # Проверяем хранилища
            storage_health = "unknown"
            try:
                if cdn_storage_manager.primary_storage:
                    await cdn_storage_manager.primary_storage.get_storage_stats()
                    storage_health = "healthy"
            except Exception:
                storage_health = "unhealthy"
            
            return {
                "status": "healthy",
                "service": "cdn",
                "version": "2.1.0",
                "timestamp": structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"],
                "checks": {
                    "database": db_health,
                    "shared_components": shared_info,
                    "cdn_config": cdn_health,
                    "cloud_storage": storage_health
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
            "features": [
                "Multi-cloud storage support",
                "Intelligent file routing",
                "Automatic cleanup",
                "Range request support",
                "Content caching"
            ],
            "storage_providers": [
                "Wasabi S3",
                "DigitalOcean Spaces", 
                "Backblaze B2",
                "Local fallback"
            ],
            "endpoints": {
                "health": "/health",
                "docs": "/docs" if settings.DEBUG else "disabled",
                "api": "/api/v1",
                "admin": "/api/v1/admin"
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
    
    logger.info("Starting VideoBot Pro CDN Service with Cloud Integration...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"CDN Host: {settings.CDN_HOST}:{settings.CDN_PORT}")
    
    # Проверяем настройки хранилищ
    storage_configs = []
    if hasattr(settings, 'WASABI_ACCESS_KEY') and settings.WASABI_ACCESS_KEY:
        storage_configs.append("Wasabi S3")
    if hasattr(settings, 'DO_SPACES_KEY') and settings.DO_SPACES_KEY:
        storage_configs.append("DigitalOcean Spaces")
    if hasattr(settings, 'B2_KEY_ID') and settings.B2_KEY_ID:
        storage_configs.append("Backblaze B2")
    
    logger.info(f"Configured storage providers: {', '.join(storage_configs) if storage_configs else 'Local only'}")
    
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
    main()app.post("/api/v1/admin/upload")
    async def admin_upload_file(
        request: Request,
        file: UploadFile = File(...),
        user_type: str = Form("free"),
        public: bool = Form(False)
    ):
        """Административная загрузка файла в облачное хранилище"""
        try:
            user = getattr(request.state, 'user', None)
            if not user or user.user_type not in ['admin', 'owner']:
                raise HTTPException(status_code=403, detail="Admin access required")
            
            # Сохраняем временный файл
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                content = await file.read()
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            try:
                # Загружаем в облачное хранилище
                result = await cdn_storage_manager.upload_file(
                    local_file_path=temp_file_path,
                    file_key=file.filename,
                    user=user,
                    metadata={
                        'admin_upload': 'true',
                        'public': str(public),
                        'original_size': str(len(content))
                    }
                )
                
                return {
                    "success": True,
                    "filename": file.filename,
                    "size": len(content),
                    "upload_result": result
                }
                
            finally:
                # Удаляем временный файл
                import os
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                    
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Admin upload failed: {e}")
            raise HTTPException(status_code=500, detail="Upload failed")
    
    @app.get("/api/v1/admin/storage/stats")
    async def get_storage_statistics(request: Request):
        """Получение детальной статистики хранилищ"""
        try:
            user = getattr(request.state, 'user', None)
            if not user or user.user_type not in ['admin', 'owner']:
                raise HTTPException(status_code=403, detail="Admin access required")
            
            stats = await cdn_storage_manager.get_storage_statistics()
            return stats
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get storage stats failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to get storage statistics")
    
    @app.post("/api/v1/admin/storage/cleanup")
    async def cleanup_storage(request: Request):
        """Принудительная очистка всех хранилищ"""
        try:
            user = getattr(request.state, 'user', None)
            if not user or user.user_type not in ['admin', 'owner']:
                raise HTTPException(status_code=403, detail="Admin access required")
            
            # Запускаем очистку
            cleanup_result = await cdn_storage_manager.cleanup_expired_files()
            
            return {
                "success": True,
                "cleanup_result": cleanup_result,
                "timestamp": structlog.processors.TimeStamper(fmt="iso")(None, None, {})["timestamp"]
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Storage cleanup failed: {e}")
            raise HTTPException(status_code=500, detail="Cleanup failed")
    
    @