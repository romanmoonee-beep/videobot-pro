"""
VideoBot Pro - Admin API Module
Инициализация API модуля с регистрацией всех роутеров
"""

from fastapi import APIRouter
from .auth import router as auth_router
from .users import router as users_router
from .analytics import router as analytics_router
from .downloads import router as downloads_router
from .settings import router as settings_router
from .channels import router as channels_router
from .broadcast import router as broadcast_router
from .payments import router as payments_router
from .system import router as system_router

# Создаем главный роутер для API
api_router = APIRouter(prefix="/api/v1")

# Регистрируем все роутеры
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(downloads_router, prefix="/downloads", tags=["Downloads"])
api_router.include_router(settings_router, prefix="/settings", tags=["Settings"])
api_router.include_router(channels_router, prefix="/channels", tags=["Channels"])
api_router.include_router(broadcast_router, prefix="/broadcast", tags=["Broadcast"])
api_router.include_router(payments_router, prefix="/payments", tags=["Payments"])
api_router.include_router(system_router, prefix="/system", tags=["System"])

__all__ = ["api_router"]


