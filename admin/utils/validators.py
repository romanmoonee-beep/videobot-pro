"""
VideoBot Pro - Admin Validators
Валидаторы данных для админ панели
"""

import re
from typing import Dict, List, Any, Optional
from email_validator import validate_email, EmailNotValidError
from pydantic import BaseModel, Field, validator
import structlog

logger = structlog.get_logger(__name__)

def validate_password_strength(password: str) -> Dict[str, Any]:
    """
    Проверить силу пароля администратора
    
    Returns:
        Dict с результатом валидации
    """
    issues = []
    
    # Минимальная длина
    if len(password) < 8:
        issues.append("Пароль должен содержать минимум 8 символов")
    
    # Максимальная длина
    if len(password) > 128:
        issues.append("Пароль не должен превышать 128 символов")
    
    # Содержит цифры
    if not re.search(r'\d', password):
        issues.append("Пароль должен содержать хотя бы одну цифру")
    
    # Содержит строчные буквы
    if not re.search(r'[a-z]', password):
        issues.append("Пароль должен содержать хотя бы одну строчную букву")
    
    # Содержит заглавные буквы
    if not re.search(r'[A-Z]', password):
        issues.append("Пароль должен содержать хотя бы одну заглавную букву")
    
    # Содержит специальные символы
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\?]', password):
        issues.append("Пароль должен содержать хотя бы один специальный символ")
    
    # Проверка на распространенные пароли
    common_passwords = {
        "password", "123456", "123456789", "qwerty", "abc123",
        "password123", "admin", "root", "user", "test"
    }
    
    if password.lower() in common_passwords:
        issues.append("Пароль слишком простой")
    
    # Проверка на повторяющиеся символы
    if len(set(password)) < len(password) / 2:
        issues.append("Пароль содержит слишком много повторяющихся символов")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "strength": _calculate_password_strength(password, issues)
    }

def _calculate_password_strength(password: str, issues: List[str]) -> str:
    """Вычислить силу пароля"""
    if len(issues) > 3:
        return "weak"
    elif len(issues) > 1:
        return "medium"
    elif len(issues) == 1:
        return "good"
    else:
        return "strong"

def validate_username(username: str) -> Dict[str, Any]:
    """
    Валидация username администратора
    """
    issues = []
    
    # Длина
    if len(username) < 3:
        issues.append("Username должен содержать минимум 3 символа")
    
    if len(username) > 32:
        issues.append("Username не должен превышать 32 символа")
    
    # Формат
    if not re.match(r'^[a-zA-Z0-9_.-]+, username):
        issues.append("Username может содержать только буквы, цифры, точки, дефисы и подчеркивания")
    
    # Не должен начинаться с цифры или специального символа
    if username[0] in '0123456789_.-':
        issues.append("Username не может начинаться с цифры или специального символа")
    
    # Зарезервированные имена
    reserved_names = {
        "admin", "root", "user", "test", "demo", "api", "www", 
        "mail", "ftp", "ssh", "system", "null", "undefined"
    }
    
    if username.lower() in reserved_names:
        issues.append("Это имя зарезервировано")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues
    }

def validate_email_address(email: str) -> Dict[str, Any]:
    """
    Валидация email адреса
    """
    try:
        # Используем email-validator для проверки
        validation_result = validate_email(email)
        return {
            "valid": True,
            "normalized_email": validation_result.email,
            "issues": []
        }
    except EmailNotValidError as e:
        return {
            "valid": False,
            "issues": [str(e)],
            "normalized_email": None
        }

def validate_telegram_id(telegram_id: str) -> Dict[str, Any]:
    """
    Валидация Telegram ID
    """
    issues = []
    
    try:
        # Преобразуем в число
        tid = int(telegram_id)
        
        # Telegram ID должен быть положительным
        if tid <= 0:
            issues.append("Telegram ID должен быть положительным числом")
        
        # Проверяем разумные границы (Telegram ID обычно 9-10 цифр)
        if tid < 10000000:  # Менее 8 цифр
            issues.append("Telegram ID слишком короткий")
        
        if tid > 9999999999:  # Более 10 цифр
            issues.append("Telegram ID слишком длинный")
            
    except ValueError:
        issues.append("Telegram ID должен быть числом")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues
    }

def validate_phone_number(phone: str) -> Dict[str, Any]:
    """
    Валидация номера телефона
    """
    issues = []
    
    # Убираем все кроме цифр и +
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Проверяем формат
    if not re.match(r'^\+?[1-9]\d{7,14}, cleaned):
        issues.append("Неверный формат номера телефона")
    
    # Проверяем длину
    digits_only = re.sub(r'[^\d]', '', cleaned)
    if len(digits_only) < 8:
        issues.append("Номер телефона слишком короткий")
    
    if len(digits_only) > 15:
        issues.append("Номер телефона слишком длинный")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "normalized": cleaned if len(issues) == 0 else None
    }

def validate_url(url: str) -> Dict[str, Any]:
    """
    Валидация URL
    """
    issues = []
    
    # Базовая проверка формата URL
    url_pattern = re.compile(
        r'^https?://'  # протокол
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # домен
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # порт
        r'(?:/?|[/?]\S+), re.IGNORECASE)
    
    if not url_pattern.match(url):
        issues.append("Неверный формат URL")
    
    # Проверяем длину
    if len(url) > 2048:
        issues.append("URL слишком длинный")
    
    # Проверяем на подозрительные схемы
    if url.lower().startswith(('javascript:', 'data:', 'vbscript:')):
        issues.append("Недопустимая схема URL")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues
    }

def validate_channel_id(channel_id: str) -> Dict[str, Any]:
    """
    Валидация Telegram Channel ID
    """
    issues = []
    
    # Проверяем формат
    if channel_id.startswith('@'):
        # Username формат
        username = channel_id[1:]
        if not re.match(r'^[a-zA-Z0-9_]{5,32}, username):
            issues.append("Неверный формат username канала")
    elif channel_id.startswith('-100'):
        # Numeric ID формат для супергрупп
        try:
            channel_num = int(channel_id)
            if channel_num >= -1000000000000:  # Слишком "новый" ID
                issues.append("Неверный числовой ID канала")
        except ValueError:
            issues.append("Неверный числовой ID канала")
    elif channel_id.startswith('-'):
        # Обычная группа
        try:
            int(channel_id)
        except ValueError:
            issues.append("Неверный ID группы")
    else:
        issues.append("Channel ID должен начинаться с @, -100 или -")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues
    }

def validate_file_upload(filename: str, content_type: str, file_size: int) -> Dict[str, Any]:
    """
    Валидация загружаемого файла
    """
    issues = []
    
    # Проверяем размер файла
    max_size = 100 * 1024 * 1024  # 100MB
    if file_size > max_size:
        issues.append(f"Файл слишком большой. Максимум: {max_size // (1024*1024)}MB")
    
    # Проверяем расширение файла
    allowed_extensions = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp',  # Изображения
        '.mp4', '.avi', '.mov', '.mkv', '.webm',   # Видео
        '.mp3', '.wav', '.ogg', '.m4a',            # Аудио
        '.pdf', '.doc', '.docx', '.txt',           # Документы
        '.csv', '.xlsx', '.xls',                   # Таблицы
        '.zip', '.rar', '.7z'                      # Архивы
    }
    
    file_ext = '.' + filename.lower().split('.')[-1] if '.' in filename else ''
    if file_ext not in allowed_extensions:
        issues.append(f"Неподдерживаемый тип файла: {file_ext}")
    
    # Проверяем MIME type
    allowed_mime_types = {
        'image/jpeg', 'image/png', 'image/gif', 'image/webp',
        'video/mp4', 'video/quicktime', 'video/x-msvideo',
        'audio/mpeg', 'audio/wav', 'audio/ogg',
        'application/pdf', 'text/plain', 'text/csv',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/zip', 'application/x-rar-compressed'
    }
    
    if content_type not in allowed_mime_types:
        issues.append(f"Неподдерживаемый MIME type: {content_type}")
    
    # Проверяем имя файла
    if not re.match(r'^[a-zA-Z0-9._-]+, filename):
        issues.append("Имя файла содержит недопустимые символы")
    
    if len(filename) > 255:
        issues.append("Имя файла слишком длинное")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues
    }

def validate_json_data(data: str) -> Dict[str, Any]:
    """
    Валидация JSON данных
    """
    issues = []
    parsed_data = None
    
    try:
        import json
        parsed_data = json.loads(data)
    except json.JSONDecodeError as e:
        issues.append(f"Неверный JSON формат: {str(e)}")
    except Exception as e:
        issues.append(f"Ошибка при парсинге JSON: {str(e)}")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "parsed_data": parsed_data
    }

def validate_cron_expression(cron_expr: str) -> Dict[str, Any]:
    """
    Валидация cron выражения
    """
    issues = []
    
    # Базовая проверка формата (5 или 6 полей)
    fields = cron_expr.strip().split()
    
    if len(fields) not in [5, 6]:
        issues.append("Cron выражение должно содержать 5 или 6 полей")
        return {"valid": False, "issues": issues}
    
    # Проверяем каждое поле
    field_ranges = [
        (0, 59, "минуты"),      # минуты
        (0, 23, "часы"),        # часы  
        (1, 31, "дни"),         # дни месяца
        (1, 12, "месяцы"),      # месяцы
        (0, 6, "дни недели")    # дни недели (0=воскресенье)
    ]
    
    if len(fields) == 6:
        field_ranges.insert(0, (0, 59, "секунды"))  # секунды
    
    for i, (field, (min_val, max_val, field_name)) in enumerate(zip(fields, field_ranges)):
        if not _validate_cron_field(field, min_val, max_val):
            issues.append(f"Неверное значение для поля '{field_name}': {field}")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues
    }

def _validate_cron_field(field: str, min_val: int, max_val: int) -> bool:
    """Валидация отдельного поля cron выражения"""
    # Специальные символы
    if field in ['*', '?']:
        return True
    
    # Диапазоны (например: 1-5)
    if '-' in field:
        try:
            start, end = map(int, field.split('-'))
            return min_val <= start <= max_val and min_val <= end <= max_val and start <= end
        except ValueError:
            return False
    
    # Списки (например: 1,3,5)
    if ',' in field:
        try:
            values = [int(x) for x in field.split(',')]
            return all(min_val <= val <= max_val for val in values)
        except ValueError:
            return False
    
    # Шаги (например: */5 или 1-10/2)
    if '/' in field:
        try:
            base, step = field.split('/')
            step = int(step)
            if step <= 0:
                return False
            
            if base == '*':
                return True
            elif '-' in base:
                start, end = map(int, base.split('-'))
                return min_val <= start <= max_val and min_val <= end <= max_val
            else:
                start = int(base)
                return min_val <= start <= max_val
        except ValueError:
            return False
    
    # Простое число
    try:
        val = int(field)
        return min_val <= val <= max_val
    except ValueError:
        return False

# Pydantic модели для валидации

class AdminCreateSchema(BaseModel):
    """Схема для создания администратора"""
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=128)
    email: Optional[str] = None
    full_name: Optional[str] = Field(None, max_length=100)
    role: str = Field(..., regex=r'^(super_admin|admin|moderator|support|viewer))
    
    @validator('username')
    def validate_username_field(cls, v):
        result = validate_username(v)
        if not result["valid"]:
            raise ValueError("; ".join(result["issues"]))
        return v
    
    @validator('password')
    def validate_password_field(cls, v):
        result = validate_password_strength(v)
        if not result["valid"]:
            raise ValueError("; ".join(result["issues"]))
        return v
    
    @validator('email')
    def validate_email_field(cls, v):
        if v:
            result = validate_email_address(v)
            if not result["valid"]:
                raise ValueError("; ".join(result["issues"]))
        return v

class BroadcastMessageSchema(BaseModel):
    """Схема для создания рассылки"""
    title: str = Field(..., min_length=1, max_length=200)
    message_text: str = Field(..., min_length=1, max_length=4096)
    target_type: str = Field(..., regex=r'^(all|premium|free|trial|specific))
    scheduled_at: Optional[str] = None
    
    @validator('message_text')
    def validate_message_length(cls, v):
        # Telegram ограничение на длину сообщения
        if len(v) > 4096:
            raise ValueError("Сообщение не может превышать 4096 символов")
        return v

class ChannelSchema(BaseModel):
    """Схема для добавления канала"""
    channel_id: str = Field(..., min_length=1, max_length=100)
    channel_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    invite_link: Optional[str] = None
    
    @validator('channel_id')
    def validate_channel_id_field(cls, v):
        result = validate_channel_id(v)
        if not result["valid"]:
            raise ValueError("; ".join(result["issues"]))
        return v
    
    @validator('invite_link')
    def validate_invite_link_field(cls, v):
        if v:
            result = validate_url(v)
            if not result["valid"]:
                raise ValueError("; ".join(result["issues"]))
        return v