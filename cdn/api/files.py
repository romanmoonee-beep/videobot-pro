"""
VideoBot Pro - CDN Files API
API для управления файлами в CDN
"""

import asyncio
import structlog
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from shared.models.user import User
from shared.services.auth import auth_service
from ..config import cdn_config
from ..services.file_service import FileService

logger = structlog.get_logger(__name__)
security = HTTPBearer(auto_error=False)

files_router = APIRouter(prefix="/files", tags=["files"])

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """Получение текущего пользователя из токена"""
    if not credentials:
        return None
    
    try:
        user = await auth_service.get_user_by_token(credentials.credentials)
        return user
    except Exception as e:
        logger.warning(f"Invalid token: {e}")
        return None

@files_router.get("/{file_path:path}")
async def download_file(
    file_path: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    range_header: Optional[str] = None
):
    """
    Скачивание файла с поддержкой Range запросов
    """
    try:
        file_service: FileService = request.app.state.file_service
        
        # Проверяем существование файла
        if not await file_service.file_exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Получаем информацию о файле
        file_info = await file_service.get_file_info(file_path)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Проверяем права доступа
        if not await file_service.check_access_permissions(file_path, user):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Проверяем, не истек ли срок хранения файла
        if await file_service.is_file_expired(file_path):
            raise HTTPException(status_code=410, detail="File expired")
        
        # Обновляем статистику
        await cdn_config.update_stats(
            'file_downloaded',
            size_gb=file_info['size'] / (1024**3)
        )
        
        # Получаем Range заголовок
        range_header = request.headers.get('range')
        
        if range_header:
            # Поддержка Range запросов для потокового воспроизведения
            return await file_service.serve_file_range(
                file_path, range_header, file_info
            )
        else:
            # Обычное скачивание файла
            return await file_service.serve_file(file_path, file_info)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@files_router.head("/{file_path:path}")
async def get_file_info(
    file_path: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user)
):
    """
    Получение информации о файле (HEAD запрос)
    """
    try:
        file_service: FileService = request.app.state.file_service
        
        # Проверяем существование файла
        if not await file_service.file_exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Получаем информацию о файле
        file_info = await file_service.get_file_info(file_path)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Проверяем права доступа
        if not await file_service.check_access_permissions(file_path, user):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Возвращаем заголовки с информацией о файле
        headers = {
            "Content-Length": str(file_info['size']),
            "Content-Type": file_info.get('content_type', 'application/octet-stream'),
            "Last-Modified": file_info.get('modified', datetime.utcnow()).strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            ),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600"
        }
        
        return Response(headers=headers)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file info {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@files_router.get("/info/{file_path:path}")
async def get_file_metadata(
    file_path: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user)
):
    """
    Получение детальной информации о файле
    """
    try:
        file_service: FileService = request.app.state.file_service
        
        # Проверяем существование файла
        if not await file_service.file_exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Проверяем права доступа
        if not await file_service.check_access_permissions(file_path, user):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Получаем детальную информацию
        metadata = await file_service.get_file_metadata(file_path)
        
        return {
            "file_path": file_path,
            "metadata": metadata,
            "cdn_url": cdn_config.get_file_url(file_path),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file metadata {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@files_router.delete("/{file_path:path}")
async def delete_file(
    file_path: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user)
):
    """
    Удаление файла (только для владельца или админа)
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        file_service: FileService = request.app.state.file_service
        
        # Проверяем существование файла
        if not await file_service.file_exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Проверяем права на удаление
        if not await file_service.check_delete_permissions(file_path, user):
            raise HTTPException(status_code=403, detail="Delete access denied")
        
        # Получаем размер файла для статистики
        file_info = await file_service.get_file_info(file_path)
        file_size_gb = file_info['size'] / (1024**3) if file_info else 0
        
        # Удаляем файл
        success = await file_service.delete_file(file_path)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete file")
        
        # Обновляем статистику
        await cdn_config.update_stats(
            'file_deleted',
            size_gb=file_size_gb
        )
        
        return {
            "message": "File deleted successfully",
            "file_path": file_path,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@files_router.get("/list/{directory:path}")
async def list_files(
    directory: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0
):
    """
    Получение списка файлов в директории
    """
    try:
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        file_service: FileService = request.app.state.file_service
        
        # Проверяем права доступа к директории
        if not await file_service.check_directory_access(directory, user):
            raise HTTPException(status_code=403, detail="Directory access denied")
        
        # Получаем список файлов
        files_list = await file_service.list_files(
            directory, limit=limit, offset=offset
        )
        
        return {
            "directory": directory,
            "files": files_list,
            "total": len(files_list),
            "limit": limit,
            "offset": offset,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files in {directory}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")