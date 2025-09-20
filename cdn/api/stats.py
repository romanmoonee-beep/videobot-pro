"""
VideoBot Pro - CDN Stats API
API для получения статистики CDN
"""

import structlog
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from shared.models.user import User
from shared.services.auth import auth_service
from ..config import cdn_config

logger = structlog.get_logger(__name__)
security = HTTPBearer()

stats_router = APIRouter(prefix="/stats", tags=["stats"])

async def get_admin_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """Получение пользователя с правами администратора"""
    user = await auth_service.get_user_by_token(credentials.credentials)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    if user.user_type not in ['admin', 'owner']:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return user

@stats_router.get("/overview")
async def get_stats_overview(
    user: User = Depends(get_admin_user)
):
    """
    Получение общей статистики CDN
    """
    try:
        # Получаем базовую статистику
        storage_info = await cdn_config.get_storage_info()
        
        # Формируем обзор
        overview = {
            "summary": {
                "total_files": cdn_config.stats['total_files'],
                "total_size_gb": round(cdn_config.stats['total_size_gb'], 2),
                "total_requests": cdn_config.stats['requests_count'],
                "bandwidth_used_gb": round(cdn_config.stats['bandwidth_used_gb'], 2)
            },
            "cache": {
                "hits": cdn_config.stats['cache_hits'],
                "misses": cdn_config.stats['cache_misses'],
                "hit_ratio": cdn_config._calculate_cache_hit_ratio()
            },
            "storage": storage_info,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return overview
    
    except Exception as e:
        logger.error(f"Error getting stats overview: {e}")
        raise HTTPException(status_code=500, detail="Failed to get stats overview")

@stats_router.get("/bandwidth")
async def get_bandwidth_stats(
    user: User = Depends(get_admin_user),
    hours: int = Query(24, description="Количество часов для статистики"),
    granularity: str = Query("hour", description="Детализация: hour, day")
):
    """
    Получение статистики использования пропускной способности
    """
    try:
        # В реальной реализации здесь будет запрос к базе данных
        # или системе мониторинга для получения исторических данных
        
        # Заглушка для демонстрации структуры ответа
        bandwidth_data = {
            "period": {
                "start": (datetime.utcnow() - timedelta(hours=hours)).isoformat(),
                "end": datetime.utcnow().isoformat(),
                "granularity": granularity
            },
            "metrics": {
                "total_bandwidth_gb": round(cdn_config.stats['bandwidth_used_gb'], 2),
                "avg_requests_per_hour": cdn_config.stats['requests_count'] // max(hours, 1),
                "peak_bandwidth_mbps": cdn_config.bandwidth_settings['max_bandwidth_mbps'] * 0.8,
                "current_concurrent_connections": 0  # Реальное значение из мониторинга
            },
            "data_points": [
                # Здесь будут реальные данные по временным интервалам
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "bandwidth_mbps": 0,
                    "requests_count": 0,
                    "unique_ips": 0
                }
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return bandwidth_data
    
    except Exception as e:
        logger.error(f"Error getting bandwidth stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get bandwidth stats")

@stats_router.get("/files")
async def get_file_stats(
    user: User = Depends(get_admin_user),
    file_type: Optional[str] = Query(None, description="Тип файлов: video, audio, image"),
    top_count: int = Query(10, description="Количество топ файлов")
):
    """
    Получение статистики по файлам
    """
    try:
        # Базовая статистика по типам файлов
        file_type_stats = {}
        
        for ftype in ['video', 'audio', 'image', 'archive']:
            file_type_stats[ftype] = {
                "count": 0,  # Количество файлов этого типа
                "total_size_gb": 0.0,  # Общий размер
                "downloads": 0  # Количество скачиваний
            }
        
        # Топ скачиваемых файлов (заглушка)
        top_files = [
            {
                "file_path": "example/video.mp4",
                "downloads": 150,
                "size_mb": 25.6,
                "last_accessed": datetime.utcnow().isoformat()
            }
        ]
        
        stats = {
            "by_type": file_type_stats,
            "top_downloaded": top_files,
            "recent_uploads": [],  # Последние загруженные файлы
            "retention_info": {
                "files_expiring_24h": 0,  # Файлы, истекающие в ближайшие 24 часа
                "files_expiring_7d": 0    # Файлы, истекающие в ближайшие 7 дней
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return stats
    
    except Exception as e:
        logger.error(f"Error getting file stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get file stats")

@stats_router.get("/performance")
async def get_performance_stats(
    user: User = Depends(get_admin_user)
):
    """
    Получение статистики производительности CDN
    """
    try:
        # Проверка здоровья системы
        health_check = await cdn_config.health_check()
        
        performance_stats = {
            "health": health_check,
            "response_times": {
                "avg_response_ms": 0,  # Среднее время ответа
                "p95_response_ms": 0,  # 95-й перцентиль
                "p99_response_ms": 0   # 99-й перцентиль
            },
            "error_rates": {
                "total_errors": 0,
                "error_rate_percent": 0.0,
                "common_errors": []
            },
            "resource_usage": {
                "cpu_usage_percent": 0,
                "memory_usage_percent": 0,
                "disk_usage_percent": 0,
                "network_usage_mbps": 0
            },
            "concurrent_connections": {
                "current": 0,
                "max_allowed": cdn_config.bandwidth_settings['concurrent_downloads'],
                "peak_today": 0
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return performance_stats
    
    except Exception as e:
        logger.error(f"Error getting performance stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get performance stats")

@stats_router.get("/users")
async def get_user_stats(
    user: User = Depends(get_admin_user),
    period_days: int = Query(7, description="Период в днях")
):
    """
    Получение статистики по пользователям
    """
    try:
        user_stats = {
            "active_users": {
                "total": 0,
                "free": 0,
                "premium": 0,
                "trial": 0
            },
            "user_activity": {
                "downloads_by_user_type": {
                    "free": {"count": 0, "gb": 0.0},
                    "premium": {"count": 0, "gb": 0.0},
                    "trial": {"count": 0, "gb": 0.0}
                }
            },
            "top_users": [
                # Топ пользователей по активности
            ],
            "geographic_distribution": {
                # Распределение по странам/регионам
            },
            "period": {
                "start": (datetime.utcnow() - timedelta(days=period_days)).isoformat(),
                "end": datetime.utcnow().isoformat()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return user_stats
    
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user stats")

@stats_router.post("/reset")
async def reset_stats(
    user: User = Depends(get_admin_user),
    confirm: bool = Query(False, description="Подтверждение сброса")
):
    """
    Сброс статистики CDN (только для владельцев)
    """
    try:
        if user.user_type != 'owner':
            raise HTTPException(status_code=403, detail="Owner access required")
        
        if not confirm:
            raise HTTPException(status_code=400, detail="Confirmation required")
        
        # Сбрасываем статистику
        cdn_config.stats = {
            'total_files': 0,
            'total_size_gb': 0.0,
            'requests_count': 0,
            'bandwidth_used_gb': 0.0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # Пересчитываем базовую статистику
        await cdn_config._calculate_initial_stats()
        
        return {
            "message": "Statistics reset successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset stats")