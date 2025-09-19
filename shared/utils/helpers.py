"""
VideoBot Pro - Helper Utilities
Вспомогательные утилиты общего назначения
"""

import json
import uuid
import re
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union, Callable
from urllib.parse import urlparse, parse_qs, urlencode
from functools import wraps
import asyncio
import time
import pytz
import structlog

logger = structlog.get_logger(__name__)

def format_file_size(size_bytes: int, decimal_places: int = 2) -> str:
    """
    Форматирует размер файла в читаемый вид
    
    Args:
        size_bytes: Размер в байтах
        decimal_places: Количество знаков после запятой
        
    Returns:
        Отформатированный размер (например, "1.5 MB")
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    
    if i >= len(size_names):
        i = len(size_names) - 1
    
    p = math.pow(1024, i)
    s = round(size_bytes / p, decimal_places)
    
    return f"{s} {size_names[i]}"

def format_duration(seconds: int, include_hours: bool = True, 
                   short_format: bool = False) -> str:
    """
    Форматирует длительность в читаемый вид
    
    Args:
        seconds: Длительность в секундах
        include_hours: Включать ли часы
        short_format: Краткий формат (1:30 вместо 1 мин 30 сек)
        
    Returns:
        Отформатированная длительность
    """
    if seconds < 0:
        return "0:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if short_format:
        if include_hours and hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    else:
        parts = []
        if include_hours and hours > 0:
            parts.append(f"{hours} ч")
        if minutes > 0:
            parts.append(f"{minutes} мин")
        if secs > 0 or not parts:
            parts.append(f"{secs} сек")
        
        return " ".join(parts)

def format_date(dt: datetime, format_type: str = "full", 
               timezone_name: str = "UTC") -> str:
    """
    Форматирует дату в читаемый вид
    
    Args:
        dt: Дата и время
        format_type: Тип форматирования (full, short, relative, time_only)
        timezone_name: Название временной зоны
        
    Returns:
        Отформатированная дата
    """
    if not dt:
        return "Неизвестно"
    
    try:
        # Конвертируем в нужную временную зону
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        target_tz = pytz.timezone(timezone_name)
        dt_local = dt.astimezone(target_tz)
        
        if format_type == "full":
            return dt_local.strftime("%d.%m.%Y в %H:%M")
        elif format_type == "short":
            return dt_local.strftime("%d.%m.%Y")
        elif format_type == "time_only":
            return dt_local.strftime("%H:%M")
        elif format_type == "relative":
            return format_relative_time(dt)
        else:
            return dt_local.strftime("%d.%m.%Y в %H:%M")
            
    except Exception as e:
        logger.warning(f"Error formatting date: {e}")
        return str(dt)

def format_relative_time(dt: datetime, now: Optional[datetime] = None) -> str:
    """
    Форматирует время относительно текущего момента
    
    Args:
        dt: Дата и время
        now: Текущее время (если не указано, используется datetime.utcnow())
        
    Returns:
        Относительное время (например, "2 часа назад")
    """
    if not dt:
        return "Неизвестно"
    
    if now is None:
        now = datetime.utcnow()
    
    # Приводим к UTC если нужно
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    
    delta = now - dt
    
    if delta.total_seconds() < 60:
        return "только что"
    elif delta.total_seconds() < 3600:
        minutes = int(delta.total_seconds() // 60)
        return f"{minutes} мин назад"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() // 3600)
        return f"{hours} ч назад"
    elif delta.days < 7:
        return f"{delta.days} дн назад"
    elif delta.days < 30:
        weeks = delta.days // 7
        return f"{weeks} нед назад"
    elif delta.days < 365:
        months = delta.days // 30
        return f"{months} мес назад"
    else:
        years = delta.days // 365
        return f"{years} г назад"

def format_currency(amount: float, currency: str = "USD", 
                   locale: str = "en_US") -> str:
    """
    Форматирует денежную сумму
    
    Args:
        amount: Сумма
        currency: Код валюты
        locale: Локаль для форматирования
        
    Returns:
        Отформатированная сумма
    """
    currency_symbols = {
        "USD": "$",
        "EUR": "€",
        "RUB": "₽",
        "GBP": "£"
    }
    
    symbol = currency_symbols.get(currency, currency)
    
    if currency == "RUB":
        return f"{amount:,.0f} {symbol}"
    else:
        return f"{symbol}{amount:,.2f}"

def parse_url_params(url: str) -> Dict[str, str]:
    """
    Парсит параметры из URL
    
    Args:
        url: URL для парсинга
        
    Returns:
        Словарь параметров
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # Преобразуем списки в строки (берем первое значение)
        return {k: v[0] if v else '' for k, v in params.items()}
    except Exception:
        return {}

def build_url(base_url: str, params: Dict[str, Any] = None, 
             fragment: str = None) -> str:
    """
    Строит URL с параметрами
    
    Args:
        base_url: Базовый URL
        params: Параметры запроса
        fragment: Фрагмент (#hash)
        
    Returns:
        Построенный URL
    """
    if params:
        # Фильтруем None значения
        clean_params = {k: v for k, v in params.items() if v is not None}
        query_string = urlencode(clean_params)
        
        if '?' in base_url:
            url = f"{base_url}&{query_string}"
        else:
            url = f"{base_url}?{query_string}"
    else:
        url = base_url
    
    if fragment:
        url = f"{url}#{fragment}"
    
    return url

def generate_uuid(short: bool = False) -> str:
    """
    Генерирует UUID
    
    Args:
        short: Генерировать короткий UUID (8 символов)
        
    Returns:
        UUID строка
    """
    full_uuid = str(uuid.uuid4())
    return full_uuid[:8] if short else full_uuid

def slugify(text: str, max_length: int = 50) -> str:
    """
    Создает slug из текста
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина slug
        
    Returns:
        Slug строка
    """
    if not text:
        return ""
    
    # Транслитерация кириллицы
    translit_dict = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
        'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
        'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
        'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
        'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    
    text = text.lower()
    
    # Транслитерируем
    result = ""
    for char in text:
        result += translit_dict.get(char, char)
    
    # Оставляем только буквы, цифры и дефисы
    result = re.sub(r'[^a-z0-9\-]', '-', result)
    
    # Убираем множественные дефисы
    result = re.sub(r'-+', '-', result)
    
    # Убираем дефисы в начале и конце
    result = result.strip('-')
    
    # Обрезаем по длине
    return result[:max_length]

def truncate_text(text: str, max_length: int = 100, 
                 suffix: str = "...") -> str:

    """
    Обрезает текст до указанной длины
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина
        suffix: Суффикс для обрезанного текста
        
    Returns:
        Обрезанный текст
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def extract_domain(url: str) -> Optional[str]:
    """
    Извлекает домен из URL
    
    Args:
        url: URL
        
    Returns:
        Домен или None
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return None

def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """
    Безопасно парсит JSON
    
    Args:
        json_str: JSON строка
        default: Значение по умолчанию при ошибке
        
    Returns:
        Распарсенные данные или default
    """
    if not json_str:
        return default
    
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default

def safe_json_dumps(obj: Any, default: str = "{}") -> str:
    """
    Безопасно сериализует объект в JSON
    
    Args:
        obj: Объект для сериализации
        default: Значение по умолчанию при ошибке
        
    Returns:
        JSON строка
    """
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return default

def deep_merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Глубоко объединяет два словаря
    
    Args:
        dict1: Первый словарь
        dict2: Второй словарь (приоритетный)
        
    Returns:
        Объединенный словарь
    """
    result = dict1.copy()
    
    for key, value in dict2.items():
        if (key in result and 
            isinstance(result[key], dict) and 
            isinstance(value, dict)):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result

def flatten_dict(d: Dict[str, Any], parent_key: str = '', 
                sep: str = '.') -> Dict[str, Any]:
    """
    Преобразует вложенный словарь в плоский
    
    Args:
        d: Словарь для преобразования
        parent_key: Родительский ключ
        sep: Разделитель ключей
        
    Returns:
        Плоский словарь
    """
    items = []
    
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    
    return dict(items)

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Разбивает список на части
    
    Args:
        lst: Исходный список
        chunk_size: Размер части
        
    Returns:
        Список частей
    """
    if chunk_size <= 0:
        return [lst]
    
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def retry_on_exception(max_retries: int = 3, delay: float = 1.0, 
                      backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Декоратор для повторного выполнения функции при исключении
    
    Args:
        max_retries: Максимальное количество повторов
        delay: Задержка между попытками
        backoff: Множитель для увеличения задержки
        exceptions: Кортеж исключений для обработки
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        raise e
                    
                    logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {current_delay}s: {e}"
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            return None
        
        # Для асинхронных функций
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        raise e
                    
                    logger.warning(
                        f"Async attempt {attempt + 1} failed, retrying in {current_delay}s: {e}"
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            return None
        
        # Возвращаем правильную обертку в зависимости от типа функции
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper
    
    return decorator

class TimezoneHelper:
    """Помощник для работы с временными зонами"""
    
    @staticmethod
    def get_user_timezone(timezone_name: str = "UTC") -> pytz.BaseTzInfo:
        """
        Получает объект временной зоны
        
        Args:
            timezone_name: Название временной зоны
            
        Returns:
            Объект временной зоны
        """
        try:
            return pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone: {timezone_name}, using UTC")
            return pytz.UTC
    
    @staticmethod
    def convert_to_user_timezone(dt: datetime, 
                               user_timezone: str = "UTC") -> datetime:
        """
        Конвертирует время в пользовательскую временную зону
        
        Args:
            dt: Дата и время в UTC
            user_timezone: Пользовательская временная зона
            
        Returns:
            Время в пользовательской зоне
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.UTC)
        
        user_tz = TimezoneHelper.get_user_timezone(user_timezone)
        return dt.astimezone(user_tz)
    
    @staticmethod
    def get_common_timezones() -> List[Dict[str, str]]:
        """Возвращает список популярных временных зон"""
        return [
            {"name": "UTC", "display": "UTC (Coordinated Universal Time)"},
            {"name": "Europe/Moscow", "display": "Moscow (GMT+3)"},
            {"name": "Europe/Kiev", "display": "Kiev (GMT+2)"},
            {"name": "Europe/Minsk", "display": "Minsk (GMT+3)"},
            {"name": "Asia/Almaty", "display": "Almaty (GMT+6)"},
            {"name": "America/New_York", "display": "New York (GMT-5/-4)"},
            {"name": "America/Los_Angeles", "display": "Los Angeles (GMT-8/-7)"},
            {"name": "Europe/London", "display": "London (GMT+0/+1)"},
            {"name": "Europe/Berlin", "display": "Berlin (GMT+1/+2)"},
            {"name": "Asia/Tokyo", "display": "Tokyo (GMT+9)"},
        ]

def clean_html(html_text: str) -> str:
    """
    Очищает HTML теги из текста
    
    Args:
        html_text: HTML текст
        
    Returns:
        Очищенный текст
    """
    import re
    
    if not html_text:
        return ""
    
    # Убираем HTML теги
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', html_text)
    
    # Декодируем HTML entities
    import html
    text = html.unescape(text)
    
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def mask_sensitive_data(data: str, mask_char: str = "*", 
                       visible_chars: int = 4) -> str:
    """
    Маскирует чувствительные данные
    
    Args:
        data: Данные для маскировки
        mask_char: Символ маски
        visible_chars: Количество видимых символов в начале и конце
        
    Returns:
        Замаскированные данные
    """
    if not data or len(data) <= visible_chars * 2:
        return mask_char * len(data) if data else ""
    
    start = data[:visible_chars]
    end = data[-visible_chars:]
    middle = mask_char * (len(data) - visible_chars * 2)
    
    return f"{start}{middle}{end}"

def generate_filename(prefix: str = "", extension: str = "", 
                     timestamp: bool = True) -> str:
    """
    Генерирует уникальное имя файла
    
    Args:
        prefix: Префикс имени файла
        extension: Расширение файла (с точкой)
        timestamp: Добавлять ли timestamp
        
    Returns:
        Имя файла
    """
    parts = []
    
    if prefix:
        parts.append(prefix)
    
    if timestamp:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        parts.append(ts)
    
    # Добавляем короткий UUID для уникальности
    parts.append(generate_uuid(short=True))
    
    filename = "_".join(parts)
    
    if extension and not extension.startswith('.'):
        extension = f".{extension}"
    
    return f"{filename}{extension}"

def calculate_eta(processed: int, total: int, start_time: datetime) -> Optional[datetime]:
    """
    Рассчитывает примерное время завершения
    
    Args:
        processed: Количество обработанных элементов
        total: Общее количество элементов
        start_time: Время начала обработки
        
    Returns:
        Примерное время завершения или None
    """
    if processed <= 0 or total <= processed:
        return None
    
    elapsed = datetime.utcnow() - start_time
    rate = processed / elapsed.total_seconds()  # элементов в секунду
    
    if rate <= 0:
        return None
    
    remaining = total - processed
    eta_seconds = remaining / rate
    
    return datetime.utcnow() + timedelta(seconds=eta_seconds)

def normalize_phone_number(phone: str, country_code: str = "RU") -> Optional[str]:
    """
    Нормализует номер телефона
    
    Args:
        phone: Номер телефона
        country_code: Код страны
        
    Returns:
        Нормализованный номер или None
    """
    try:
        import phonenumbers
        
        parsed = phonenumbers.parse(phone, country_code)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass
    
    return None

def get_file_hash(file_content: bytes, algorithm: str = "sha256") -> str:
    """
    Вычисляет хеш содержимого файла
    
    Args:
        file_content: Содержимое файла
        algorithm: Алгоритм хеширования
        
    Returns:
        Хеш строка
    """
    import hashlib
    
    if algorithm == "md5":
        hasher = hashlib.md5()
    elif algorithm == "sha1":
        hasher = hashlib.sha1()
    elif algorithm == "sha256":
        hasher = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")
    
    hasher.update(file_content)
    return hasher.hexdigest()

class ProgressTracker:
    """Класс для отслеживания прогресса выполнения"""
    
    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.processed = 0
        self.description = description
        self.start_time = datetime.utcnow()
        self.errors = 0
    
    def update(self, increment: int = 1):
        """Обновляет прогресс"""
        self.processed += increment
    
    def add_error(self):
        """Добавляет ошибку"""
        self.errors += 1
    
    @property
    def progress_percent(self) -> float:
        """Прогресс в процентах"""
        if self.total == 0:
            return 100.0
        return (self.processed / self.total) * 100
    
    @property
    def eta(self) -> Optional[datetime]:
        """Примерное время завершения"""
        return calculate_eta(self.processed, self.total, self.start_time)
    
    @property
    def elapsed_time(self) -> timedelta:
        """Прошедшее время"""
        return datetime.utcnow() - self.start_time
    
    def get_status(self) -> Dict[str, Any]:
        """Получает статус прогресса"""
        return {
            'description': self.description,
            'total': self.total,
            'processed': self.processed,
            'progress_percent': round(self.progress_percent, 2),
            'errors': self.errors,
            'elapsed_seconds': int(self.elapsed_time.total_seconds()),
            'eta': self.eta.isoformat() if self.eta else None
        }