"""
VideoBot Pro - Validators
Валидаторы для различных типов данных
"""

import re
import validators
from typing import Optional, List, Dict, Any, Tuple, Union
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import phonenumbers
from phonenumbers import NumberParseException
import structlog

logger = structlog.get_logger(__name__)

class ValidationError(Exception):
    """Ошибка валидации"""
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(message)

def validate_url(url: str, allowed_schemes: List[str] = None) -> bool:
    """
    Проверяет валидность URL
    
    Args:
        url: URL для проверки
        allowed_schemes: Разрешенные схемы (http, https)
        
    Returns:
        True если URL валидный
    """
    if not url or not isinstance(url, str):
        return False
    
    try:
        result = urlparse(url)
        
        # Проверяем базовую структуру
        if not all([result.scheme, result.netloc]):
            return False
        
        # Проверяем разрешенные схемы
        if allowed_schemes and result.scheme not in allowed_schemes:
            return False
        
        # Используем библиотеку validators для дополнительной проверки
        return validators.url(url)
        
    except Exception:
        return False

def validate_video_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет URL видео и определяет платформу
    
    Args:
        url: URL видео
        
    Returns:
        Tuple (валидность, платформа)
    """
    if not validate_url(url):
        return False, None
    
    domain = urlparse(url).netloc.lower()
    
    # YouTube
    youtube_domains = ['youtube.com', 'www.youtube.com', 'youtu.be', 'm.youtube.com']
    if any(d in domain for d in youtube_domains):
        # Проверяем наличие video ID
        if 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[-1].split('?')[0]
        elif 'v=' in url:
            video_id = parse_qs(urlparse(url).query).get('v', [''])[0]
        else:
            return False, None
        
        if video_id and re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
            return True, 'youtube'
    
    # TikTok
    tiktok_domains = ['tiktok.com', 'www.tiktok.com', 'vm.tiktok.com', 'm.tiktok.com']
    if any(d in domain for d in tiktok_domains):
        # TikTok URLs имеют различные форматы
        if '/video/' in url or '/@' in url or 'vm.tiktok.com' in url:
            return True, 'tiktok'
    
    # Instagram
    instagram_domains = ['instagram.com', 'www.instagram.com']
    if any(d in domain for d in instagram_domains):
        # Instagram Reels, IGTV, обычные посты
        if any(path in url for path in ['/reel/', '/tv/', '/p/']):
            return True, 'instagram'
    
    return False, None

def validate_email(email: str) -> bool:
    """
    Проверяет email адрес
    
    Args:
        email: Email для проверки
        
    Returns:
        True если email валидный
    """
    if not email or not isinstance(email, str):
        return False
    
    try:
        return validators.email(email)
    except Exception:
        return False

def validate_phone(phone: str, region: str = None) -> bool:
    """
    Проверяет номер телефона
    
    Args:
        phone: Номер телефона
        region: Код региона (например, 'RU')
        
    Returns:
        True если номер валидный
    """
    if not phone or not isinstance(phone, str):
        return False
    
    try:
        parsed = phonenumbers.parse(phone, region)
        return phonenumbers.is_valid_number(parsed)
    except NumberParseException:
        return False

def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """
    Проверяет username
    
    Args:
        username: Имя пользователя
        
    Returns:
        Tuple (валидность, сообщение об ошибке)
    """
    if not username or not isinstance(username, str):
        return False, "Username не может быть пустым"
    
    if len(username) < 3:
        return False, "Username должен содержать минимум 3 символа"
    
    if len(username) > 30:
        return False, "Username не может содержать более 30 символов"
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username может содержать только буквы, цифры и знак подчеркивания"
    
    if username.startswith('_') or username.endswith('_'):
        return False, "Username не может начинаться или заканчиваться знаком подчеркивания"
    
    # Проверяем на зарезервированные слова
    reserved_words = [
        'admin', 'administrator', 'root', 'system', 'api', 'bot',
        'null', 'undefined', 'anonymous', 'guest', 'test'
    ]
    if username.lower() in reserved_words:
        return False, "Этот username зарезервирован"
    
    return True, None

def validate_password(password: str) -> Tuple[bool, List[str]]:
    """
    Проверяет пароль на соответствие требованиям
    
    Args:
        password: Пароль для проверки
        
    Returns:
        Tuple (валидность, список ошибок)
    """
    errors = []
    
    if not password or not isinstance(password, str):
        errors.append("Пароль не может быть пустым")
        return False, errors
    
    if len(password) < 8:
        errors.append("Пароль должен содержать минимум 8 символов")
    
    if len(password) > 128:
        errors.append("Пароль не может содержать более 128 символов")
    
    if not re.search(r'[a-z]', password):
        errors.append("Пароль должен содержать строчные буквы")
    
    if not re.search(r'[A-Z]', password):
        errors.append("Пароль должен содержать заглавные буквы")
    
    if not re.search(r'\d', password):
        errors.append("Пароль должен содержать цифры")
    
    # Проверяем на простые пароли
    common_passwords = [
        'password', '12345678', 'qwerty', 'abc123', 'password123',
        'admin', 'letmein', 'welcome', 'monkey', 'dragon'
    ]
    if password.lower() in common_passwords:
        errors.append("Этот пароль слишком простой")
    
    return len(errors) == 0, errors

def validate_telegram_id(telegram_id: Union[int, str]) -> bool:
    """
    Проверяет Telegram ID
    
    Args:
        telegram_id: Telegram ID
        
    Returns:
        True если ID валидный
    """
    try:
        tid = int(telegram_id)
        # Telegram ID должен быть положительным числом
        # и находиться в разумных пределах
        return 1 <= tid <= 9999999999
    except (ValueError, TypeError):
        return False

def validate_file_size(size_bytes: int, max_size_mb: int = 100) -> Tuple[bool, Optional[str]]:
    """
    Проверяет размер файла
    
    Args:
        size_bytes: Размер в байтах
        max_size_mb: Максимальный размер в МБ
        
    Returns:
        Tuple (валидность, сообщение об ошибке)
    """
    if not isinstance(size_bytes, int) or size_bytes < 0:
        return False, "Неверный размер файла"
    
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if size_bytes > max_size_bytes:
        return False, f"Файл слишком большой. Максимум {max_size_mb} МБ"
    
    if size_bytes == 0:
        return False, "Файл пустой"
    
    return True, None

def validate_video_duration(duration_seconds: int, max_duration_minutes: int = 60) -> Tuple[bool, Optional[str]]:
    """
    Проверяет длительность видео
    
    Args:
        duration_seconds: Длительность в секундах
        max_duration_minutes: Максимальная длительность в минутах
        
    Returns:
        Tuple (валидность, сообщение об ошибке)
    """
    if not isinstance(duration_seconds, int) or duration_seconds <= 0:
        return False, "Неверная длительность видео"
    
    max_duration_seconds = max_duration_minutes * 60
    
    if duration_seconds > max_duration_seconds:
        return False, f"Видео слишком длинное. Максимум {max_duration_minutes} минут"
    
    return True, None

def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Очищает имя файла от недопустимых символов
    
    Args:
        filename: Исходное имя файла
        max_length: Максимальная длина
        
    Returns:
        Очищенное имя файла
    """
    if not filename:
        return "file"
    
    # Убираем опасные символы
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    
    # Убираем точки в начале и конце
    filename = filename.strip('. ')
    
    # Обрезаем по длине, оставляя место для расширения
    if len(filename) > max_length:
        name_part = filename.rsplit('.', 1)[0]
        ext_part = '.' + filename.rsplit('.', 1)[1] if '.' in filename else ''
        max_name_length = max_length - len(ext_part)
        filename = name_part[:max_name_length] + ext_part
    
    return filename or "file"

def is_valid_platform(platform: str) -> bool:
    """
    Проверяет поддерживаемую платформу
    
    Args:
        platform: Название платформы
        
    Returns:
        True если платформа поддерживается
    """
    supported_platforms = ['youtube', 'tiktok', 'instagram']
    return platform.lower() in supported_platforms

class VideoURLValidator:
    """Класс для валидации URL видео"""
    
    def __init__(self):
        self.supported_platforms = {
            'youtube': self._validate_youtube,
            'tiktok': self._validate_tiktok,
            'instagram': self._validate_instagram
        }
    
    def validate(self, url: str) -> Dict[str, Any]:
        """
        Валидация URL видео
        
        Args:
            url: URL для проверки
            
        Returns:
            Словарь с результатами валидации
        """
        result = {
            'valid': False,
            'platform': None,
            'video_id': None,
            'error': None
        }
        
        if not validate_url(url):
            result['error'] = "Неверный формат URL"
            return result
        
        # Проверяем каждую платформу
        for platform, validator in self.supported_platforms.items():
            platform_result = validator(url)
            if platform_result['valid']:
                result.update(platform_result)
                result['platform'] = platform
                break
        else:
            result['error'] = "Неподдерживаемая платформа"
        
        return result
    
    def _validate_youtube(self, url: str) -> Dict[str, Any]:
        """Валидация YouTube URL"""
        result = {'valid': False, 'video_id': None}
        
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                result['valid'] = True
                result['video_id'] = match.group(1)
                break
        
        return result
    
    def _validate_tiktok(self, url: str) -> Dict[str, Any]:
        """Валидация TikTok URL"""
        result = {'valid': False, 'video_id': None}
        
        # TikTok URLs могут быть различных форматов
        tiktok_patterns = [
            r'tiktok\.com/@[\w.-]+/video/(\d+)',
            r'vm\.tiktok\.com/(\w+)',
            r'tiktok\.com/t/(\w+)',
        ]
        
        for pattern in tiktok_patterns:
            match = re.search(pattern, url)
            if match:
                result['valid'] = True
                result['video_id'] = match.group(1)
                break
        
        return result
    
    def _validate_instagram(self, url: str) -> Dict[str, Any]:
        """Валидация Instagram URL"""
        result = {'valid': False, 'video_id': None}
        
        instagram_patterns = [
            r'instagram\.com/reel/([A-Za-z0-9_-]+)',
            r'instagram\.com/tv/([A-Za-z0-9_-]+)',
            r'instagram\.com/p/([A-Za-z0-9_-]+)',
        ]
        
        for pattern in instagram_patterns:
            match = re.search(pattern, url)
            if match:
                result['valid'] = True
                result['video_id'] = match.group(1)
                break
        
        return result

class UserDataValidator:
    """Валидатор данных пользователя"""
    
    @staticmethod
    def validate_registration_data(data: Dict[str, Any]) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Валидация данных регистрации
        
        Args:
            data: Данные для валидации
            
        Returns:
            Tuple (валидность, словарь ошибок по полям)
        """
        errors = {}
        
        # Telegram ID (обязательно)
        telegram_id = data.get('telegram_id')
        if not telegram_id:
            errors['telegram_id'] = ["Telegram ID обязателен"]
        elif not validate_telegram_id(telegram_id):
            errors['telegram_id'] = ["Неверный Telegram ID"]
        
        # Username (опционально)
        username = data.get('username')
        if username:
            valid, error = validate_username(username)
            if not valid:
                errors['username'] = [error]
        
        # Email (опционально)
        email = data.get('email')
        if email and not validate_email(email):
            errors['email'] = ["Неверный формат email"]
        
        # Имя и фамилия
        first_name = data.get('first_name', '').strip()
        if not first_name:
            errors['first_name'] = ["Имя обязательно"]
        elif len(first_name) > 100:
            errors['first_name'] = ["Имя слишком длинное"]
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_profile_update(data: Dict[str, Any]) -> Tuple[bool, Dict[str, List[str]]]:
        """Валидация данных обновления профиля"""
        errors = {}
        
        # Username
        username = data.get('username')
        if username is not None:  # Может быть пустой строкой для сброса
            if username:  # Если не пустая строка, валидируем
                valid, error = validate_username(username)
                if not valid:
                    errors['username'] = [error]
        
        # Email
        email = data.get('email')
        if email is not None:
            if email and not validate_email(email):
                errors['email'] = ["Неверный формат email"]
        
        # Телефон
        phone = data.get('phone')
        if phone is not None:
            if phone and not validate_phone(phone):
                errors['phone'] = ["Неверный формат телефона"]
        
        # Проверяем длину текстовых полей
        text_fields = {
            'first_name': 100,
            'last_name': 100,
            'bio': 500
        }
        
        for field, max_length in text_fields.items():
            value = data.get(field)
            if value and len(value) > max_length:
                errors[field] = [f"Максимальная длина: {max_length} символов"]
        
        return len(errors) == 0, errors

class PaymentDataValidator:
    """Валидатор платежных данных"""
    
    @staticmethod
    def validate_payment_data(data: Dict[str, Any]) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Валидация данных платежа
        
        Args:
            data: Данные платежа
            
        Returns:
            Tuple (валидность, словарь ошибок)
        """
        errors = {}
        
        # Сумма
        amount = data.get('amount')
        if not amount:
            errors['amount'] = ["Сумма обязательна"]
        else:
            try:
                amount_float = float(amount)
                if amount_float <= 0:
                    errors['amount'] = ["Сумма должна быть больше 0"]
                elif amount_float > 10000:  # Максимум $10,000
                    errors['amount'] = ["Сумма слишком большая"]
            except (ValueError, TypeError):
                errors['amount'] = ["Неверная сумма"]
        
        # Валюта
        currency = data.get('currency', '').upper()
        supported_currencies = ['USD', 'EUR', 'RUB']
        if currency not in supported_currencies:
            errors['currency'] = [f"Поддерживаемые валюты: {', '.join(supported_currencies)}"]
        
        # Метод платежа
        payment_method = data.get('payment_method')
        supported_methods = ['stripe', 'paypal', 'telegram_payments', 'crypto']
        if not payment_method:
            errors['payment_method'] = ["Метод платежа обязателен"]
        elif payment_method not in supported_methods:
            errors['payment_method'] = [f"Поддерживаемые методы: {', '.join(supported_methods)}"]
        
        # План подписки
        subscription_plan = data.get('subscription_plan')
        supported_plans = ['monthly', 'quarterly', 'yearly', 'lifetime']
        if subscription_plan and subscription_plan not in supported_plans:
            errors['subscription_plan'] = [f"Поддерживаемые планы: {', '.join(supported_plans)}"]
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_card_data(card_data: Dict[str, Any]) -> Tuple[bool, Dict[str, List[str]]]:
        """Валидация данных банковской карты"""
        errors = {}
        
        # Номер карты
        card_number = re.sub(r'\D', '', card_data.get('number', ''))
        if not card_number:
            errors['number'] = ["Номер карты обязателен"]
        elif len(card_number) < 13 or len(card_number) > 19:
            errors['number'] = ["Неверная длина номера карты"]
        elif not PaymentDataValidator._validate_luhn(card_number):
            errors['number'] = ["Неверный номер карты"]
        
        # Срок действия
        exp_month = card_data.get('exp_month')
        exp_year = card_data.get('exp_year')
        
        if not exp_month or not exp_year:
            errors['expiry'] = ["Срок действия обязателен"]
        else:
            try:
                month = int(exp_month)
                year = int(exp_year)
                
                if not 1 <= month <= 12:
                    errors['exp_month'] = ["Неверный месяц"]
                
                current_year = datetime.now().year
                if year < current_year or year > current_year + 20:
                    errors['exp_year'] = ["Неверный год"]
                
                # Проверяем что карта не истекла
                if year == current_year and month < datetime.now().month:
                    errors['expiry'] = ["Срок действия карты истек"]
                    
            except (ValueError, TypeError):
                errors['expiry'] = ["Неверный формат срока действия"]
        
        # CVC
        cvc = card_data.get('cvc', '')
        if not cvc:
            errors['cvc'] = ["CVC код обязателен"]
        elif not re.match(r'^\d{3,4}$', cvc):
            errors['cvc'] = ["CVC должен содержать 3-4 цифры"]
        
        return len(errors) == 0, errors
    
    @staticmethod
    def _validate_luhn(card_number: str) -> bool:
        """Проверка номера карты по алгоритму Луна"""
        def luhn_checksum(card_num):
            def digits_of(n):
                return [int(d) for d in str(n)]
            
            digits = digits_of(card_num)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d*2))
            return checksum % 10
        
        return luhn_checksum(card_number) == 0

def validate_batch_urls(urls: List[str], max_urls: int = 20) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """
    Валидация списка URL для batch загрузки
    
    Args:
        urls: Список URL
        max_urls: Максимальное количество URL
        
    Returns:
        Tuple (валидные URL, невалидные URL, статистика)
    """
    valid_urls = []
    invalid_urls = []
    platforms_count = {}
    
    if len(urls) > max_urls:
        # Обрезаем до максимального количества
        urls = urls[:max_urls]
    
    validator = VideoURLValidator()
    
    for url in urls:
        url = url.strip()
        if not url:
            continue
            
        result = validator.validate(url)
        if result['valid']:
            valid_urls.append(url)
            platform = result['platform']
            platforms_count[platform] = platforms_count.get(platform, 0) + 1
        else:
            invalid_urls.append(url)
    
    stats = {
        'total_urls': len(urls),
        'valid_count': len(valid_urls),
        'invalid_count': len(invalid_urls),
        'platforms': platforms_count,
        'is_mixed_platforms': len(platforms_count) > 1
    }
    
    return valid_urls, invalid_urls, stats