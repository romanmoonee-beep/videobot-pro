"""
VideoBot Pro - CDN API Module
Модуль API для CDN сервиса
"""

from .files import files_router
from .auth import auth_router
from .stats import stats_router

__all__ = [
    'files_router',
    'auth_router', 
    'stats_router'
]