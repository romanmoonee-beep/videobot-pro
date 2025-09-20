"""
VideoBot Pro - CDN Auth API
API для аутентификации в CDN
"""

import structlog
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from shared.models.user import User
from shared.services.auth import auth_service
from shared.utils.security import generate_secure_token

logger = structlog.get_logger(__name__)
security = HTTPBearer()

auth_router = APIRouter(prefix="/auth", tags=["auth"])

class TokenRequest(BaseModel):
    token: str
    duration_hours: Optional[int] = 24

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user_info: dict

class FileAccessRequest(BaseModel):
    file_path: str
    user_id: int
    duration_hours: Optional[int] = 1

class FileAccessResponse(BaseModel):
    access_token: str
    file_url: str
    expires_at: str

@auth_router.post("/verify", response_model=dict)
async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Проверка токена доступа
    """
    try:
        user = await auth_service.get_user_by_token(credentials.credentials)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return {
            "valid": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "user_type": user.user_type,
                "is_premium": user.is_premium
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Token verification failed")

@auth_router.post("/exchange", response_model=TokenResponse)
async def exchange_token(
    request: TokenRequest
):
    """
    Обмен основного токена на CDN токен
    """
    try:
        # Проверяем основной токен
        user = await auth_service.get_user_by_token(request.token)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Генерируем CDN токен
        cdn_token = generate_secure_token()
        expires_in = request.duration_hours * 3600
        expires_at = datetime.utcnow() + timedelta(hours=request.duration_hours)
        
        # Сохраняем CDN токен
        await auth_service.store_cdn_token(
            token=cdn_token,
            user_id=user.id,
            expires_at=expires_at
        )
        
        return TokenResponse(
            access_token=cdn_token,
            token_type="bearer",
            expires_in=expires_in,
            user_info={
                "id": user.id,
                "username": user.username,
                "user_type": user.user_type,
                "is_premium": user.is_premium
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(status_code=500, detail="Token exchange failed")

@auth_router.post("/file-access", response_model=FileAccessResponse)
async def create_file_access_token(
    request: FileAccessRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Создание временного токена для доступа к конкретному файлу
    """
    try:
        # Проверяем основной токен
        user = await auth_service.get_user_by_token(credentials.credentials)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Проверяем права доступа к файлу
        from ..services.file_service import FileService
        file_service = FileService()
        
        if not await file_service.check_access_permissions(request.file_path, user):
            raise HTTPException(status_code=403, detail="Access denied to file")
        
        # Генерируем токен доступа к файлу
        access_token = generate_secure_token()
        expires_at = datetime.utcnow() + timedelta(hours=request.duration_hours)
        
        # Сохраняем токен доступа к файлу
        await auth_service.store_file_access_token(
            token=access_token,
            file_path=request.file_path,
            user_id=user.id,
            expires_at=expires_at
        )
        
        # Формируем URL файла с токеном
        from ..config import cdn_config
        file_url = f"{cdn_config.get_file_url(request.file_path)}?token={access_token}"
        
        return FileAccessResponse(
            access_token=access_token,
            file_url=file_url,
            expires_at=expires_at.isoformat()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File access token creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create file access token")

@auth_router.delete("/token")
async def revoke_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Отзыв токена доступа
    """
    try:
        # Удаляем токен из хранилища
        success = await auth_service.revoke_cdn_token(credentials.credentials)
        
        if not success:
            raise HTTPException(status_code=404, detail="Token not found")
        
        return {
            "message": "Token revoked successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token revocation failed: {e}")
        raise HTTPException(status_code=500, detail="Token revocation failed")

@auth_router.get("/permissions/{file_path:path}")
async def check_file_permissions(
    file_path: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Проверка прав доступа к файлу
    """
    try:
        user = await auth_service.get_user_by_token(credentials.credentials)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        from ..services.file_service import FileService
        file_service = FileService()
        
        # Проверяем различные права доступа
        can_read = await file_service.check_access_permissions(file_path, user)
        can_delete = await file_service.check_delete_permissions(file_path, user)
        
        return {
            "file_path": file_path,
            "permissions": {
                "can_read": can_read,
                "can_delete": can_delete
            },
            "user": {
                "id": user.id,
                "user_type": user.user_type,
                "is_premium": user.is_premium
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Permission check failed: {e}")
        raise HTTPException(status_code=500, detail="Permission check failed")