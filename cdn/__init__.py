"""
VideoBot Pro - CDN Module
Модуль CDN для доставки контента
"""

from .config import CDNConfig, cdn_config
from .main import app, create_app, main

__version__ = "2.1.0"

__all__ = [
    'CDNConfig',
    'cdn_config',
    'app', 
    'create_app',
    'main'
]