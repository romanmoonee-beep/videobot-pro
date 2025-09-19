"""
VideoBot Pro - Common Schemas
Общие схемы для различных компонентов
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

from .base import BaseSchema


class StatusEnum(str, Enum):
    """Общие статусы"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlatformEnum(str, Enum):
    """Поддерживаемые платформы"""
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"


class UserTypeEnum(str, Enum):
    """Типы пользователей"""
    FREE = "free"
    TRIAL = "trial"
    PREMIUM = "premium"
    ADMIN = "admin"


class QualityEnum(str, Enum):
    """Качество видео"""
    AUTO = "auto"
    Q480P = "480p"
    Q720P = "720p"
    Q1080P = "1080p"
    Q1440P = "1440p"
    Q2160P = "2160p"
    Q4K = "4K"