"""
VideoBot Pro - Security Utilities
Утилиты для обеспечения безопасности
"""

import hashlib
import secrets
import hmac
import jwt
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import re
import html
import structlog

from ..config.settings import settings

logger = structlog.get_logger(__name__)

class SecurityError(Exception):
    """Базовая ошибка безопасности"""
    pass

class TokenError(SecurityError):
    """Ошибка токена"""
    pass

def hash_password(password: str) -> str:
    """
    Хеширует пароль с использованием bcrypt
    
    Args:
        password: Пароль для хеширования
        
    Returns:
        Хешированный пароль
    """
    import bcrypt
    
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """
    Проверяет пароль против хеша
    
    Args:
        password: Исходный пароль
        hashed: Хешированный пароль
        
    Returns:
        True если пароль правильный
    """
    import bcrypt
    
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        logger.warning(f"Password verification failed: {e}")
        return False

def generate_token(length: int = 32, url_safe: bool = True) -> str:
    """
    Генерирует криптографически стойкий токен
    
    Args:
        length: Длина токена в байтах
        url_safe: Использовать URL-safe кодирование
        
    Returns:
        Строковый токен
    """
    token_bytes = secrets.token_bytes(length)
    if url_safe:
        return base64.urlsafe_b64encode(token_bytes).decode('ascii').rstrip('=')
    else:
        return base64.b64encode(token_bytes).decode('ascii')

def verify_token(token: str, expected_length: int = 32) -> bool:
    """
    Проверяет валидность токена
    
    Args:
        token: Токен для проверки
        expected_length: Ожидаемая длина токена
        
    Returns:
        True если токен валидный
    """
    try:
        # Восстанавливаем padding если нужно
        missing_padding = len(token) % 4
        if missing_padding:
            token += '=' * (4 - missing_padding)
            
        decoded = base64.urlsafe_b64decode(token.encode('ascii'))
        return len(decoded) == expected_length
    except Exception:
        return False

def generate_api_key() -> str:
    """
    Генерирует API ключ
    
    Returns:
        API ключ в формате vb_xxxxxxxxxxxx
    """
    random_part = generate_token(16, url_safe=True)
    return f"vb_{random_part}"

def create_signature(data: str, secret: str) -> str:
    """
    Создает HMAC подпись для данных
    
    Args:
        data: Данные для подписи
        secret: Секретный ключ
        
    Returns:
        Hex-подпись
    """
    signature = hmac.new(
        secret.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    )
    return signature.hexdigest()

def verify_signature(data: str, signature: str, secret: str) -> bool:
    """
    Проверяет HMAC подпись
    
    Args:
        data: Исходные данные
        signature: Подпись для проверки
        secret: Секретный ключ
        
    Returns:
        True если подпись правильная
    """
    expected_signature = create_signature(data, secret)
    return hmac.compare_digest(signature, expected_signature)

class DataEncryption:
    """Класс для симметричного шифрования данных"""
    
    def __init__(self, key: Optional[bytes] = None):
        if key is None:
            key = self._derive_key_from_settings()
        self.fernet = Fernet(key)
    
    def _derive_key_from_settings(self) -> bytes:
        """Генерирует ключ из настроек"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=settings.JWT_SECRET[:16].encode(),
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(settings.JWT_SECRET.encode()))
        return key
    
    def encrypt(self, data: str) -> str:
        """Шифрует строку"""
        encrypted = self.fernet.encrypt(data.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted).decode('ascii')
    
    def decrypt(self, encrypted_data: str) -> str:
        """Расшифровывает строку"""
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('ascii'))
            decrypted = self.fernet.decrypt(encrypted_bytes)
            return decrypted.decode('utf-8')
        except Exception as e:
            raise SecurityError(f"Decryption failed: {e}")

# Глобальный экземпляр для шифрования
_encryptor = DataEncryption()

def encrypt_data(data: str) -> str:
    """Шифрует данные"""
    return _encryptor.encrypt(data)

def decrypt_data(encrypted_data: str) -> str:
    """Расшифровывает данные"""
    return _encryptor.decrypt(encrypted_data)

def sanitize_input(input_string: str, max_length: int = 1000, 
                  allow_html: bool = False) -> str:
    """
    Очищает пользовательский ввод
    
    Args:
        input_string: Строка для очистки
        max_length: Максимальная длина
        allow_html: Разрешить HTML теги
        
    Returns:
        Очищенная строка
    """
    if not isinstance(input_string, str):
        return ""
    
    # Обрезаем по длине
    cleaned = input_string[:max_length]
    
    # Убираем HTML если не разрешен
    if not allow_html:
        cleaned = html.escape(cleaned)
    
    # Убираем потенциально опасные символы
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)
    
    return cleaned.strip()

def validate_telegram_data(init_data: str, bot_token: str) -> Dict[str, Any]:
    """
    Проверяет данные от Telegram WebApp
    
    Args:
        init_data: Данные инициализации
        bot_token: Токен бота
        
    Returns:
        Распарсенные данные если валидны
        
    Raises:
        SecurityError: Если данные невалидны
    """
    try:
        # Парсим данные
        params = {}
        for item in init_data.split('&'):
            key, value = item.split('=', 1)
            params[key] = value
        
        # Извлекаем хеш
        received_hash = params.pop('hash', '')
        if not received_hash:
            raise SecurityError("Missing hash parameter")
        
        # Создаем строку для проверки
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(params.items()))
        
        # Создаем секретный ключ
        secret_key = hmac.new(
            b"WebAppData", 
            bot_token.encode(), 
            hashlib.sha256
        ).digest()
        
        # Проверяем подпись
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(received_hash, calculated_hash):
            raise SecurityError("Invalid hash")
        
        return params
        
    except Exception as e:
        raise SecurityError(f"Telegram data validation failed: {e}")

def create_jwt_token(payload: Dict[str, Any], expires_in: int = 3600) -> str:
    """
    Создает JWT токен
    
    Args:
        payload: Данные для токена
        expires_in: Время жизни в секундах
        
    Returns:
        JWT токен
    """
    now = datetime.utcnow()
    payload.update({
        'iat': now,
        'exp': now + timedelta(seconds=expires_in),
        'iss': 'videobot-pro'
    })
    
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Проверяет JWT токен
    
    Args:
        token: JWT токен
        
    Returns:
        Payload токена
        
    Raises:
        TokenError: Если токен невалидный
    """
    try:
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise TokenError(f"Invalid token: {e}")

def generate_session_token(user_id: int, user_type: str = 'user') -> Dict[str, str]:
    """
    Генерирует токены сессии
    
    Args:
        user_id: ID пользователя
        user_type: Тип пользователя
        
    Returns:
        Словарь с access и refresh токенами
    """
    access_payload = {
        'user_id': user_id,
        'user_type': user_type,
        'type': 'access'
    }
    
    refresh_payload = {
        'user_id': user_id,
        'user_type': user_type,
        'type': 'refresh'
    }
    
    access_token = create_jwt_token(access_payload, expires_in=settings.JWT_EXPIRE_MINUTES * 60)
    refresh_token = create_jwt_token(refresh_payload, expires_in=settings.JWT_EXPIRE_MINUTES * 60 * 24 * 7)  # 7 дней
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token
    }

def create_password_reset_token(user_id: int) -> str:
    """
    Создает токен для сброса пароля
    
    Args:
        user_id: ID пользователя
        
    Returns:
        Токен сброса пароля
    """
    payload = {
        'user_id': user_id,
        'type': 'password_reset',
        'random': generate_token(8)
    }
    return create_jwt_token(payload, expires_in=3600)  # 1 час

def verify_password_reset_token(token: str) -> int:
    """
    Проверяет токен сброса пароля
    
    Args:
        token: Токен для проверки
        
    Returns:
        ID пользователя
        
    Raises:
        TokenError: Если токен невалидный
    """
    payload = verify_jwt_token(token)
    
    if payload.get('type') != 'password_reset':
        raise TokenError("Invalid token type")
    
    return payload['user_id']

class SecurityAudit:
    """Класс для аудита безопасности"""
    
    @staticmethod
    def check_password_strength(password: str) -> Dict[str, Any]:
        """
        Проверяет силу пароля
        
        Args:
            password: Пароль для проверки
            
        Returns:
            Словарь с результатами проверки
        """
        result = {
            'score': 0,
            'length_ok': len(password) >= 8,
            'has_upper': bool(re.search(r'[A-Z]', password)),
            'has_lower': bool(re.search(r'[a-z]', password)),
            'has_digit': bool(re.search(r'\d', password)),
            'has_special': bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
            'recommendations': []
        }
        
        # Подсчитываем очки
        if result['length_ok']:
            result['score'] += 2
        if result['has_upper']:
            result['score'] += 1
        if result['has_lower']:
            result['score'] += 1
        if result['has_digit']:
            result['score'] += 1
        if result['has_special']:
            result['score'] += 1
        
        # Дополнительные очки за длину
        if len(password) >= 12:
            result['score'] += 1
        if len(password) >= 16:
            result['score'] += 1
        
        # Рекомендации
        if not result['length_ok']:
            result['recommendations'].append("Используйте не менее 8 символов")
        if not result['has_upper']:
            result['recommendations'].append("Добавьте заглавные буквы")
        if not result['has_lower']:
            result['recommendations'].append("Добавьте строчные буквы")
        if not result['has_digit']:
            result['recommendations'].append("Добавьте цифры")
        if not result['has_special']:
            result['recommendations'].append("Добавьте специальные символы")
        
        # Определяем силу пароля
        if result['score'] >= 7:
            result['strength'] = 'strong'
        elif result['score'] >= 5:
            result['strength'] = 'medium'
        else:
            result['strength'] = 'weak'
        
        return result