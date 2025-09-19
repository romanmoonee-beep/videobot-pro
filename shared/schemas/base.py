from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


class BaseSchema(BaseModel):
    """Базовая схема для всех моделей"""
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        use_enum_values=True
    )


class TimestampSchema(BaseSchema):
    """Схема с временными метками"""
    created_at: Optional[datetime] = Field(None, description="Дата создания")
    updated_at: Optional[datetime] = Field(None, description="Дата обновления")


class IDSchema(BaseSchema):
    """Схема с ID"""
    id: int = Field(description="Уникальный идентификатор")


class ResponseSchema(BaseModel):
    """Стандартная схема ответа API"""
    success: bool = Field(True, description="Успешность операции")
    message: Optional[str] = Field(None, description="Сообщение")
    data: Optional[Any] = Field(None, description="Данные ответа")
    errors: Optional[Dict[str, List[str]]] = Field(None, description="Ошибки валидации")

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )


class PaginationSchema(BaseModel):
    """Схема пагинации"""
    page: int = Field(1, ge=1, description="Номер страницы")
    per_page: int = Field(20, ge=1, le=1000, description="Элементов на странице")
    total: int = Field(0, ge=0, description="Общее количество элементов")
    pages: int = Field(0, ge=0, description="Общее количество страниц")
    has_prev: bool = Field(False, description="Есть ли предыдущая страница")
    has_next: bool = Field(False, description="Есть ли следующая страница")