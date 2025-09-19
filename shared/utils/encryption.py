"""
VideoBot Pro - Encryption Utilities
Утилиты для шифрования и криптографии
"""

import os
import base64
import hashlib
import secrets
from typing import Optional, Tuple, Dict, Any, Union, List
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import structlog

from ..config.settings import settings

logger = structlog.get_logger(__name__)

class EncryptionError(Exception):
    """Базовое исключение для ошибок шифрования"""
    pass

class DecryptionError(EncryptionError):
    """Исключение для ошибок расшифровки"""
    pass

class AESCipher:
    """Класс для AES шифрования"""
    
    def __init__(self, key: Optional[bytes] = None):
        """
        Инициализация AES cipher
        
        Args:
            key: 32-байтный ключ для AES-256. Если не указан, генерируется из настроек
        """
        if key is None:
            key = self._derive_key_from_settings()
        elif len(key) != 32:
            raise EncryptionError("AES key must be exactly 32 bytes")
        
        self.key = key
    
    def _derive_key_from_settings(self) -> bytes:
        """Генерирует ключ из настроек приложения"""
        password = settings.JWT_SECRET.encode()
        salt = b"videobot_salt_2024"  # В продакшене должен быть случайный
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        
        return kdf.derive(password)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Шифрует текст с использованием AES-256-GCM
        
        Args:
            plaintext: Текст для шифрования
            
        Returns:
            Base64-кодированная строка: nonce + ciphertext + tag
        """
        try:
            # Генерируем случайный nonce
            nonce = os.urandom(12)  # 96 бит для GCM
            
            # Создаем cipher
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.GCM(nonce),
                backend=default_backend()
            )
            
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(plaintext.encode('utf-8')) + encryptor.finalize()
            
            # Объединяем nonce + ciphertext + tag
            encrypted_data = nonce + ciphertext + encryptor.tag
            
            return base64.b64encode(encrypted_data).decode('ascii')
            
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Расшифровывает текст
        
        Args:
            encrypted_data: Base64-кодированная зашифрованная строка
            
        Returns:
            Расшифрованный текст
        """
        try:
            # Декодируем из base64
            data = base64.b64decode(encrypted_data.encode('ascii'))
            
            # Извлекаем компоненты
            nonce = data[:12]
            tag = data[-16:]
            ciphertext = data[12:-16]
            
            # Создаем cipher
            cipher = Cipher(
                algorithms.AES(self.key),
                modes.GCM(nonce, tag),
                backend=default_backend()
            )
            
            decryptor = cipher.decryptor()
            plaintext_bytes = decryptor.update(ciphertext) + decryptor.finalize()
            
            return plaintext_bytes.decode('utf-8')
            
        except Exception as e:
            raise DecryptionError(f"Decryption failed: {e}")
    
    def encrypt_dict(self, data: Dict[str, Any]) -> str:
        """Шифрует словарь как JSON"""
        import json
        json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        return self.encrypt(json_str)
    
    def decrypt_dict(self, encrypted_data: str) -> Dict[str, Any]:
        """Расшифровывает словарь из JSON"""
        import json
        json_str = self.decrypt(encrypted_data)
        return json.loads(json_str)

class RSAKeyManager:
    """Менеджер RSA ключей"""
    
    def __init__(self, key_size: int = 2048):
        """
        Инициализация менеджера RSA ключей
        
        Args:
            key_size: Размер ключа в битах
        """
        self.key_size = key_size
        self._private_key = None
        self._public_key = None
    
    def generate_key_pair(self) -> Tuple[bytes, bytes]:
        """
        Генерирует пару RSA ключей
        
        Returns:
            Tuple (приватный ключ PEM, публичный ключ PEM)
        """
        try:
            # Генерируем приватный ключ
            self._private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=self.key_size,
                backend=default_backend()
            )
            
            self._public_key = self._private_key.public_key()
            
            # Сериализуем ключи
            private_pem = self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            
            public_pem = self._public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            return private_pem, public_pem
            
        except Exception as e:
            raise EncryptionError(f"RSA key generation failed: {e}")
    
    def load_private_key(self, private_key_pem: bytes, password: Optional[bytes] = None):
        """Загружает приватный ключ из PEM"""
        try:
            self._private_key = serialization.load_pem_private_key(
                private_key_pem,
                password=password,
                backend=default_backend()
            )
            self._public_key = self._private_key.public_key()
        except Exception as e:
            raise EncryptionError(f"Failed to load private key: {e}")
    
    def load_public_key(self, public_key_pem: bytes):
        """Загружает публичный ключ из PEM"""
        try:
            self._public_key = serialization.load_pem_public_key(
                public_key_pem,
                backend=default_backend()
            )
        except Exception as e:
            raise EncryptionError(f"Failed to load public key: {e}")
    
    def encrypt(self, plaintext: str) -> str:
        """
        Шифрует текст публичным ключом
        
        Args:
            plaintext: Текст для шифрования
            
        Returns:
            Base64-кодированный зашифрованный текст
        """
        if not self._public_key:
            raise EncryptionError("Public key not loaded")
        
        try:
            plaintext_bytes = plaintext.encode('utf-8')
            
            # RSA может шифровать ограниченное количество данных
            max_chunk_size = (self.key_size // 8) - 2 * 32 - 2  # OAEP padding
            
            if len(plaintext_bytes) > max_chunk_size:
                # Для больших данных используем гибридное шифрование
                return self._hybrid_encrypt(plaintext_bytes)
            
            ciphertext = self._public_key.encrypt(
                plaintext_bytes,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            return base64.b64encode(ciphertext).decode('ascii')
            
        except Exception as e:
            raise EncryptionError(f"RSA encryption failed: {e}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Расшифровывает текст приватным ключом
        
        Args:
            encrypted_data: Base64-кодированный зашифрованный текст
            
        Returns:
            Расшифрованный текст
        """
        if not self._private_key:
            raise DecryptionError("Private key not loaded")
        
        try:
            ciphertext = base64.b64decode(encrypted_data.encode('ascii'))
            
            # Проверяем, не гибридное ли это шифрование
            if len(ciphertext) > (self.key_size // 8):
                return self._hybrid_decrypt(ciphertext)
            
            plaintext_bytes = self._private_key.decrypt(
                ciphertext,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            return plaintext_bytes.decode('utf-8')
            
        except Exception as e:
            raise DecryptionError(f"RSA decryption failed: {e}")
    
    def _hybrid_encrypt(self, data: bytes) -> str:
        """Гибридное шифрование для больших данных"""
        # Генерируем случайный AES ключ
        aes_key = os.urandom(32)
        
        # Шифруем данные AES ключом
        aes_cipher = AESCipher(aes_key)
        encrypted_data = aes_cipher.encrypt(data.decode('utf-8'))
        
        # Шифруем AES ключ RSA
        encrypted_key = self._public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # Объединяем зашифрованный ключ и данные
        result = encrypted_key + base64.b64decode(encrypted_data)
        return base64.b64encode(result).decode('ascii')
    
    def _hybrid_decrypt(self, ciphertext: bytes) -> str:
        """Гибридная расшифровка"""
        # Размер зашифрованного RSA ключа
        rsa_key_size = self.key_size // 8
        
        # Извлекаем зашифрованный AES ключ
        encrypted_aes_key = ciphertext[:rsa_key_size]
        encrypted_data = ciphertext[rsa_key_size:]
        
        # Расшифровываем AES ключ
        aes_key = self._private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # Расшифровываем данные
        aes_cipher = AESCipher(aes_key)
        encrypted_data_b64 = base64.b64encode(encrypted_data).decode('ascii')
        return aes_cipher.decrypt(encrypted_data_b64)
    
    def sign(self, message: str) -> str:
        """Создает цифровую подпись"""
        if not self._private_key:
            raise EncryptionError("Private key not loaded for signing")
        
        try:
            signature = self._private_key.sign(
                message.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return base64.b64encode(signature).decode('ascii')
            
        except Exception as e:
            raise EncryptionError(f"Signing failed: {e}")
    
    def verify_signature(self, message: str, signature: str) -> bool:
        """Проверяет цифровую подпись"""
        if not self._public_key:
            raise EncryptionError("Public key not loaded for verification")
        
        try:
            signature_bytes = base64.b64decode(signature.encode('ascii'))
            
            self._public_key.verify(
                signature_bytes,
                message.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
            
        except Exception:
            return False

class PasswordHasher:
    """Класс для хеширования паролей"""
    
    @staticmethod
    def hash_password(password: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
        """
        Хеширует пароль с использованием Scrypt
        
        Args:
            password: Пароль для хеширования
            salt: Соль (если не указана, генерируется случайная)
            
        Returns:
            Tuple (хеш в base64, соль в base64)
        """
        if salt is None:
            salt = os.urandom(16)
        
        try:
            kdf = Scrypt(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend()
            )
            
            key = kdf.derive(password.encode('utf-8'))
            
            return (
                base64.b64encode(key).decode('ascii'),
                base64.b64encode(salt).decode('ascii')
            )
            
        except Exception as e:
            raise EncryptionError(f"Password hashing failed: {e}")
    
    @staticmethod
    def verify_password(password: str, hashed: str, salt: str) -> bool:
        """
        Проверяет пароль против хеша
        
        Args:
            password: Исходный пароль
            hashed: Хеш пароля в base64
            salt: Соль в base64
            
        Returns:
            True если пароль правильный
        """
        try:
            salt_bytes = base64.b64decode(salt.encode('ascii'))
            expected_key = base64.b64decode(hashed.encode('ascii'))
            
            kdf = Scrypt(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt_bytes,
                iterations=100000,
                backend=default_backend()
            )
            
            kdf.verify(password.encode('utf-8'), expected_key)
            return True
            
        except Exception:
            return False

def generate_key_pair() -> Dict[str, str]:
    """
    Генерирует пару RSA ключей
    
    Returns:
        Словарь с приватным и публичным ключами в PEM формате
    """
    key_manager = RSAKeyManager()
    private_pem, public_pem = key_manager.generate_key_pair()
    
    return {
        'private_key': private_pem.decode('utf-8'),
        'public_key': public_pem.decode('utf-8')
    }

def encrypt_sensitive_data(data: Union[str, Dict[str, Any]], 
                          encryption_key: Optional[str] = None) -> str:
    """
    Шифрует чувствительные данные
    
    Args:
        data: Данные для шифрования (строка или словарь)
        encryption_key: Ключ шифрования (если не указан, используется из настроек)
        
    Returns:
        Зашифрованная строка в base64
    """
    try:
        cipher = AESCipher()
        
        if isinstance(data, dict):
            return cipher.encrypt_dict(data)
        else:
            return cipher.encrypt(str(data))
            
    except Exception as e:
        logger.error(f"Failed to encrypt sensitive data: {e}")
        raise EncryptionError(f"Encryption failed: {e}")

def decrypt_sensitive_data(encrypted_data: str, 
                          encryption_key: Optional[str] = None,
                          return_dict: bool = False) -> Union[str, Dict[str, Any]]:
    """
    Расшифровывает чувствительные данные
    
    Args:
        encrypted_data: Зашифрованная строка
        encryption_key: Ключ расшифровки
        return_dict: Возвращать как словарь
        
    Returns:
        Расшифрованные данные
    """
    try:
        cipher = AESCipher()
        
        if return_dict:
            return cipher.decrypt_dict(encrypted_data)
        else:
            return cipher.decrypt(encrypted_data)
            
    except Exception as e:
        logger.error(f"Failed to decrypt sensitive data: {e}")
        raise DecryptionError(f"Decryption failed: {e}")

class SecureStorage:
    """Класс для безопасного хранения данных"""
    
    def __init__(self, master_key: Optional[bytes] = None):
        """
        Инициализация безопасного хранилища
        
        Args:
            master_key: Мастер-ключ для шифрования
        """
        self.cipher = AESCipher(master_key)
        self._storage: Dict[str, str] = {}
    
    def store(self, key: str, value: Any) -> None:
        """Сохраняет значение с шифрованием"""
        if isinstance(value, (dict, list)):
            import json
            value_str = json.dumps(value, ensure_ascii=False)
        else:
            value_str = str(value)
        
        encrypted_value = self.cipher.encrypt(value_str)
        self._storage[key] = encrypted_value
    
    def retrieve(self, key: str, default: Any = None, 
                as_json: bool = False) -> Any:
        """Получает и расшифровывает значение"""
        encrypted_value = self._storage.get(key)
        
        if encrypted_value is None:
            return default
        
        try:
            decrypted_value = self.cipher.decrypt(encrypted_value)
            
            if as_json:
                import json
                return json.loads(decrypted_value)
            
            return decrypted_value
            
        except DecryptionError:
            logger.error(f"Failed to decrypt value for key: {key}")
            return default
    
    def delete(self, key: str) -> bool:
        """Удаляет значение"""
        if key in self._storage:
            del self._storage[key]
            return True
        return False
    
    def list_keys(self) -> list:
        """Возвращает список ключей"""
        return list(self._storage.keys())
    
    def clear(self) -> None:
        """Очищает все данные"""
        self._storage.clear()
    
    def export_encrypted(self) -> str:
        """Экспортирует все данные в зашифрованном виде"""
        import json
        return base64.b64encode(
            json.dumps(self._storage).encode('utf-8')
        ).decode('ascii')
    
    def import_encrypted(self, data: str) -> None:
        """Импортирует зашифрованные данные"""
        import json
        try:
            decoded = base64.b64decode(data.encode('ascii'))
            self._storage = json.loads(decoded.decode('utf-8'))
        except Exception as e:
            raise EncryptionError(f"Failed to import data: {e}")

class TokenGenerator:
    """Генератор криптографически стойких токенов"""
    
    @staticmethod
    def generate_api_token(length: int = 32) -> str:
        """Генерирует API токен"""
        token_bytes = secrets.token_bytes(length)
        return base64.urlsafe_b64encode(token_bytes).decode('ascii').rstrip('=')
    
    @staticmethod
    def generate_session_id() -> str:
        """Генерирует ID сессии"""
        return TokenGenerator.generate_api_token(24)
    
    @staticmethod
    def generate_csrf_token() -> str:
        """Генерирует CSRF токен"""
        return TokenGenerator.generate_api_token(16)
    
    @staticmethod
    def generate_verification_code(length: int = 6, 
                                 digits_only: bool = True) -> str:
        """
        Генерирует код верификации
        
        Args:
            length: Длина кода
            digits_only: Только цифры
            
        Returns:
            Код верификации
        """
        if digits_only:
            return ''.join(secrets.choice('0123456789') for _ in range(length))
        else:
            alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def generate_recovery_codes(count: int = 8, length: int = 8) -> List[str]:
        """Генерирует коды восстановления"""
        codes = []
        for _ in range(count):
            code = TokenGenerator.generate_verification_code(length, digits_only=False)
            # Форматируем как XXXX-XXXX
            if length == 8:
                code = f"{code[:4]}-{code[4:]}"
            codes.append(code)
        return codes

def secure_compare(a: str, b: str) -> bool:
    """
    Безопасное сравнение строк (защита от timing attacks)
    
    Args:
        a: Первая строка
        b: Вторая строка
        
    Returns:
        True если строки равны
    """
    import hmac
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))

def generate_file_checksum(file_path: str, algorithm: str = 'sha256') -> str:
    """
    Генерирует контрольную сумму файла
    
    Args:
        file_path: Путь к файлу
        algorithm: Алгоритм хеширования
        
    Returns:
        Hex-строка контрольной суммы
    """
    hash_func = hashlib.new(algorithm)
    
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
        
    except Exception as e:
        raise EncryptionError(f"Failed to calculate checksum: {e}")

# Глобальные экземпляры для удобства использования
_global_cipher = None

def get_global_cipher() -> AESCipher:
    """Получает глобальный экземпляр AESCipher"""
    global _global_cipher
    if _global_cipher is None:
        _global_cipher = AESCipher()
    return _global_cipher