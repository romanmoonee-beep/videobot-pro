"""
VideoBot Pro - Pagination Utilities
Утилиты для работы с пагинацией
"""

from typing import Any, List, Dict, Optional, TypeVar, Generic
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Query
import math

from ..config import admin_settings

T = TypeVar('T')

class PaginationInfo(BaseModel):
    """Информация о пагинации"""
    page: int = Field(..., ge=1, description="Текущая страница")
    per_page: int = Field(..., ge=1, le=1000, description="Элементов на странице")
    total: int = Field(..., ge=0, description="Общее количество элементов")
    pages: int = Field(..., ge=0, description="Общее количество страниц")
    has_prev: bool = Field(..., description="Есть ли предыдущая страница")
    has_next: bool = Field(..., description="Есть ли следующая страница")
    prev_page: Optional[int] = Field(None, description="Номер предыдущей страницы")
    next_page: Optional[int] = Field(None, description="Номер следующей страницы")

class PaginatedResponse(BaseModel, Generic[T]):
    """Стандартный ответ с пагинацией"""
    items: List[T] = Field(..., description="Элементы текущей страницы")
    pagination: PaginationInfo = Field(..., description="Информация о пагинации")
    
class PaginationParams:
    """Параметры пагинации"""
    
    def __init__(
        self, 
        page: int = 1, 
        per_page: int = None,
        max_per_page: int = None
    ):
        self.page = max(1, page)
        
        if per_page is None:
            per_page = admin_settings.DEFAULT_PAGE_SIZE
        
        if max_per_page is None:
            max_per_page = admin_settings.MAX_PAGE_SIZE
            
        self.per_page = min(max(1, per_page), max_per_page)
    
    @property
    def offset(self) -> int:
        """Вычислить offset для SQL запроса"""
        return (self.page - 1) * self.per_page
    
    @property
    def limit(self) -> int:
        """Получить limit для SQL запроса"""
        return self.per_page

def paginate_query(
    query: Query,
    page: int = 1,
    per_page: int = None,
    max_per_page: int = None,
    count_query: Optional[Query] = None
) -> Dict[str, Any]:
    """
    Пагинация SQLAlchemy запроса
    
    Args:
        query: SQLAlchemy запрос
        page: Номер страницы
        per_page: Элементов на странице
        max_per_page: Максимум элементов на странице
        count_query: Отдельный запрос для подсчета (опционально)
    
    Returns:
        Словарь с результатами и информацией о пагинации
    """
    params = PaginationParams(page, per_page, max_per_page)
    
    # Подсчет общего количества
    if count_query is not None:
        total = count_query.scalar()
    else:
        total = query.count()
    
    # Вычисляем общее количество страниц
    pages = math.ceil(total / params.per_page) if total > 0 else 0
    
    # Корректируем номер страницы если он превышает максимум
    if pages > 0 and page > pages:
        page = pages
        params.page = page
    
    # Применяем пагинацию к запросу
    items = query.offset(params.offset).limit(params.limit).all()
    
    # Создаем информацию о пагинации
    pagination_info = PaginationInfo(
        page=params.page,
        per_page=params.per_page,
        total=total,
        pages=pages,
        has_prev=params.page > 1,
        has_next=params.page < pages,
        prev_page=params.page - 1 if params.page > 1 else None,
        next_page=params.page + 1 if params.page < pages else None
    )
    
    return {
        "items": items,
        "pagination": pagination_info
    }

async def paginate_async_query(
    query,
    page: int = 1,
    per_page: int = None,
    max_per_page: int = None,
    count_query = None
) -> Dict[str, Any]:
    """
    Асинхронная пагинация SQLAlchemy запроса
    
    Args:
        query: Асинхронный SQLAlchemy запрос
        page: Номер страницы
        per_page: Элементов на странице
        max_per_page: Максимум элементов на странице
        count_query: Отдельный запрос для подсчета (опционально)
    
    Returns:
        Словарь с результатами и информацией о пагинации
    """
    params = PaginationParams(page, per_page, max_per_page)
    
    # Подсчет общего количества
    if count_query is not None:
        result = await count_query.execute()
        total = result.scalar()
    else:
        count_result = await query.count()
        total = count_result
    
    # Вычисляем общее количество страниц
    pages = math.ceil(total / params.per_page) if total > 0 else 0
    
    # Корректируем номер страницы если он превышает максимум
    if pages > 0 and page > pages:
        page = pages
        params.page = page
    
    # Применяем пагинацию к запросу
    items_result = await query.offset(params.offset).limit(params.limit).all()
    items = items_result
    
    # Создаем информацию о пагинации
    pagination_info = PaginationInfo(
        page=params.page,
        per_page=params.per_page,
        total=total,
        pages=pages,
        has_prev=params.page > 1,
        has_next=params.page < pages,
        prev_page=params.page - 1 if params.page > 1 else None,
        next_page=params.page + 1 if params.page < pages else None
    )
    
    return {
        "items": items,
        "pagination": pagination_info
    }

def paginate_list(
    items: List[Any],
    page: int = 1,
    per_page: int = None,
    max_per_page: int = None
) -> Dict[str, Any]:
    """
    Пагинация списка в памяти
    
    Args:
        items: Список элементов
        page: Номер страницы
        per_page: Элементов на странице
        max_per_page: Максимум элементов на странице
    
    Returns:
        Словарь с результатами и информацией о пагинации
    """
    params = PaginationParams(page, per_page, max_per_page)
    
    total = len(items)
    pages = math.ceil(total / params.per_page) if total > 0 else 0
    
    # Корректируем номер страницы если он превышает максимум
    if pages > 0 and page > pages:
        page = pages
        params.page = page
    
    # Применяем пагинацию к списку
    start_idx = params.offset
    end_idx = start_idx + params.per_page
    paginated_items = items[start_idx:end_idx]
    
    # Создаем информацию о пагинации
    pagination_info = PaginationInfo(
        page=params.page,
        per_page=params.per_page,
        total=total,
        pages=pages,
        has_prev=params.page > 1,
        has_next=params.page < pages,
        prev_page=params.page - 1 if params.page > 1 else None,
        next_page=params.page + 1 if params.page < pages else None
    )
    
    return {
        "items": paginated_items,
        "pagination": pagination_info
    }

def create_pagination_links(
    base_url: str,
    pagination: PaginationInfo,
    query_params: Dict[str, Any] = None
) -> Dict[str, Optional[str]]:
    """
    Создать ссылки для навигации по страницам
    
    Args:
        base_url: Базовый URL
        pagination: Информация о пагинации
        query_params: Дополнительные query параметры
    
    Returns:
        Словарь со ссылками
    """
    if query_params is None:
        query_params = {}
    
    def build_url(page_num: int) -> str:
        params = query_params.copy()
        params['page'] = page_num
        params['per_page'] = pagination.per_page
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base_url}?{query_string}"
    
    links = {
        "first": build_url(1) if pagination.pages > 0 else None,
        "last": build_url(pagination.pages) if pagination.pages > 0 else None,
        "prev": build_url(pagination.prev_page) if pagination.has_prev else None,
        "next": build_url(pagination.next_page) if pagination.has_next else None,
        "current": build_url(pagination.page)
    }
    
    return links

def get_page_range(
    current_page: int,
    total_pages: int,
    max_pages: int = 10
) -> List[int]:
    """
    Получить диапазон страниц для отображения в пагинации
    
    Args:
        current_page: Текущая страница
        total_pages: Общее количество страниц
        max_pages: Максимум страниц для отображения
    
    Returns:
        Список номеров страниц
    """
    if total_pages <= max_pages:
        return list(range(1, total_pages + 1))
    
    # Вычисляем диапазон вокруг текущей страницы
    half_range = max_pages // 2
    
    start = max(1, current_page - half_range)
    end = min(total_pages, current_page + half_range)
    
    # Корректируем диапазон если он слишком короткий
    if end - start + 1 < max_pages:
        if start == 1:
            end = min(total_pages, start + max_pages - 1)
        else:
            start = max(1, end - max_pages + 1)
    
    return list(range(start, end + 1))

class PaginationHelper:
    """Помощник для работы с пагинацией"""
    
    def __init__(
        self,
        default_per_page: int = None,
        max_per_page: int = None
    ):
        self.default_per_page = default_per_page or admin_settings.DEFAULT_PAGE_SIZE
        self.max_per_page = max_per_page or admin_settings.MAX_PAGE_SIZE
    
    def paginate_query(
        self,
        query: Query,
        page: int = 1,
        per_page: int = None
    ) -> Dict[str, Any]:
        """Пагинация запроса с настройками по умолчанию"""
        return paginate_query(
            query=query,
            page=page,
            per_page=per_page or self.default_per_page,
            max_per_page=self.max_per_page
        )
    
    def paginate_list(
        self,
        items: List[Any],
        page: int = 1,
        per_page: int = None
    ) -> Dict[str, Any]:
        """Пагинация списка с настройками по умолчанию"""
        return paginate_list(
            items=items,
            page=page,
            per_page=per_page or self.default_per_page,
            max_per_page=self.max_per_page
        )

# Глобальный экземпляр помощника
pagination_helper = PaginationHelper()

def validate_pagination_params(page: int, per_page: int) -> Dict[str, Any]:
    """
    Валидация параметров пагинации
    
    Returns:
        Словарь с результатом валидации
    """
    errors = []
    
    # Проверяем page
    if page < 1:
        errors.append("Номер страницы должен быть больше 0")
    
    if page > 100000:  # Разумное ограничение
        errors.append("Номер страницы слишком большой")
    
    # Проверяем per_page
    if per_page < 1:
        errors.append("Количество элементов на странице должно быть больше 0")
    
    if per_page > admin_settings.MAX_PAGE_SIZE:
        errors.append(f"Максимум элементов на странице: {admin_settings.MAX_PAGE_SIZE}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "corrected_page": max(1, min(page, 100000)),
        "corrected_per_page": max(1, min(per_page, admin_settings.MAX_PAGE_SIZE))
    }

def calculate_pagination_stats(pagination: PaginationInfo) -> Dict[str, Any]:
    """
    Вычислить дополнительную статистику по пагинации
    
    Returns:
        Словарь со статистикой
    """
    start_item = (pagination.page - 1) * pagination.per_page + 1 if pagination.total > 0 else 0
    end_item = min(pagination.page * pagination.per_page, pagination.total)
    
    return {
        "start_item": start_item,
        "end_item": end_item,
        "showing_count": end_item - start_item + 1 if end_item >= start_item else 0,
        "percentage_shown": (end_item / pagination.total * 100) if pagination.total > 0 else 0,
        "items_remaining": max(0, pagination.total - end_item)
    }