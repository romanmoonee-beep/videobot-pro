"""
VideoBot Pro - Authentication Service
Управление аутентификацией и авторизацией
"""

import jwt
import hashlib
import secrets
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from passlib.context import CryptContext

from shared.config.settings import settings
from shared.models import User, AdminUser, AdminRole, AdminPermission

logger = structlog.get_logger(__name__)

class TokenManager:
    """Менеджер JWT токенов"""
    
    def __init__(self):
        self.secret_key = settings.JWT_SECRET
        self.algorithm = settings.JWT_ALGORITHM
        self.expire_minutes = settings.JWT_EXPIRE_MINUTES
        
    def create_token(self, user_data: Dict[str, Any], token_type: str = "access", 
                    expire_minutes: Optional[int] = None) -> str:
        """Создать JWT токен"""
        try:
            expire_time = expire_minutes or self.expire_minutes
            expire_at = datetime.utcnow() + timedelta(minutes=expire_time)
            
            payload = {
                "sub": str(user_data.get("user_id")),
                "type": token_type,
                "iat": datetime.utcnow(),
                "exp": expire_at,
                "jti": secrets.token_hex(16),  # JWT ID для отзыва
                **user_data
            }
            
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
            
            logger.debug(f"Created {token_type} token", user_id=user_data.get("user_id"))
            return token
            
        except Exception as e:
            logger.error(f"Token creation failed: {e}")
            raise
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Проверить и декодировать токен"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Проверяем срок действия
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp) < datetime.utcnow():
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.debug("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return None
    
    def create_user_token(self, user: User) -> Dict[str, str]:
        """Создать токены для обычного пользователя"""
        user_data = {
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "user_type": user.current_user_type,
            "username": user.username
        }
        
        access_token = self.create_token(user_data, "access", 60)  # 1 час
        refresh_token = self.create_token(user_data, "refresh", 10080)  # 7 дней
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 3600
        }
    
    def create_admin_token(self, admin: AdminUser) -> Dict[str, str]:
        """Создать токены для администратора"""
        admin_data = {
            "admin_id": admin.id,
            "username": admin.username,
            "role": admin.role,
            "permissions": admin._get_role_permissions() + (admin.permissions or []),
            "telegram_id": admin.telegram_id
        }
        
        access_token = self.create_token(admin_data, "admin_access", 240)  # 4 часа
        refresh_token = self.create_token(admin_data, "admin_refresh", 10080)  # 7 дней
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 14400
        }
    
    def refresh_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Обновить access токен используя refresh токен"""
        payload = self.verify_token(refresh_token)
        
        if not payload or payload.get("type") != "refresh":
            return None
        
        # Создаем новый access токен с теми же данными
        token_type = "admin_access" if "admin_id" in payload else "access"
        expire_minutes = 240 if "admin_id" in payload else 60
        
        new_access_token = self.create_token(
            {k: v for k, v in payload.items() if k not in ["exp", "iat", "jti", "type"]},
            token_type,
            expire_minutes
        )
        
        return {
            "access_token": new_access_token,
            "refresh_token": refresh_token,  # Refresh токен остается тот же
            "token_type": "bearer",
            "expires_in": expire_minutes * 60
        }

class PasswordManager:
    """Менеджер паролей"""
    
    def __init__(self):
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    def hash_password(self, password: str) -> str:
        """Хешировать пароль"""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Проверить пароль"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def generate_password(self, length: int = 12) -> str:
        """Сгенерировать случайный пароль"""
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def validate_password_strength(self, password: str) -> Dict[str, Any]:
        """Проверить силу пароля"""
        result = {
            "valid": True,
            "score": 0,
            "issues": []
        }
        
        # Минимальная длина
        if len(password) < 8:
            result["issues"].append("Пароль должен содержать минимум 8 символов")
            result["valid"] = False
        else:
            result["score"] += 1
        
        # Наличие цифр
        if not any(c.isdigit() for c in password):
            result["issues"].append("Пароль должен содержать цифры")
            result["valid"] = False
        else:
            result["score"] += 1
        
        # Наличие прописных букв
        if not any(c.isupper() for c in password):
            result["issues"].append("Пароль должен содержать заглавные буквы")
        else:
            result["score"] += 1
        
        # Наличие строчных букв
        if not any(c.islower() for c in password):
            result["issues"].append("Пароль должен содержать строчные буквы")
        else:
            result["score"] += 1
        
        # Наличие специальных символов
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            result["issues"].append("Рекомендуется использовать специальные символы")
        else:
            result["score"] += 1
        
        return result

class AuthService:
    """Основной сервис аутентификации"""
    
    def __init__(self):
        self.token_manager = TokenManager()
        self.password_manager = PasswordManager()
        self._initialized = False
        
        # Кэш для отозванных токенов (в продакшене лучше использовать Redis)
        self.revoked_tokens = set()
        
    def is_initialized(self) -> bool:
        """Проверить инициализацию сервиса"""
        return self._initialized
    
    async def initialize(self):
        """Инициализация сервиса"""
        if self._initialized:
            return
            
        logger.info("Initializing auth service...")
        self._initialized = True
        logger.info("Auth service initialized")
    
    def create_api_key(self, user_id: int, name: str = None) -> str:
        """Создать API ключ"""
        timestamp = int(datetime.utcnow().timestamp())
        data = f"{user_id}:{timestamp}:{name or 'api_key'}"
        
        # Создаем подпись
        signature = hashlib.sha256(
            f"{data}:{self.token_manager.secret_key}".encode()
        ).hexdigest()
        
        api_key = f"vb_{secrets.token_urlsafe(16)}_{signature[:16]}"
        
        logger.info(f"Created API key for user {user_id}")
        return api_key
    
    def verify_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Проверить API ключ"""
        try:
            if not api_key.startswith("vb_"):
                return None
            
            # В реальном приложении нужно хранить API ключи в БД
            # Здесь упрощенная проверка формата
            parts = api_key.split("_")
            if len(parts) != 3:
                return None
            
            return {"api_key": api_key, "valid": True}
            
        except Exception as e:
            logger.error(f"API key verification failed: {e}")
            return None
    
    def revoke_token(self, token: str) -> bool:
        """Отозвать токен"""
        try:
            payload = self.token_manager.verify_token(token)
            if payload:
                jti = payload.get("jti")
                if jti:
                    self.revoked_tokens.add(jti)
                    logger.info(f"Token revoked", jti=jti)
                    return True
            return False
        except Exception as e:
            logger.error(f"Token revocation failed: {e}")
            return False
    
    def is_token_revoked(self, token: str) -> bool:
        """Проверить, отозван ли токен"""
        try:
            payload = self.token_manager.verify_token(token)
            if payload:
                jti = payload.get("jti")
                return jti in self.revoked_tokens
            return True
        except:
            return True
    
    def create_session_token(self, user_id: int, session_data: Dict[str, Any] = None) -> str:
        """Создать токен сессии"""
        session_data = session_data or {}
        session_data.update({
            "user_id": user_id,
            "session_id": secrets.token_hex(16),
            "created_at": datetime.utcnow().isoformat()
        })
        
        return self.token_manager.create_token(session_data, "session", 60)
    
    def verify_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Проверить токен сессии"""
        payload = self.token_manager.verify_token(token)
        
        if not payload or payload.get("type") != "session":
            return None
            
        if self.is_token_revoked(token):
            return None
            
        return payload
    
    async def authenticate_user(self, telegram_id: int) -> Optional[Dict[str, str]]:
        """Аутентификация пользователя Telegram"""
        from shared.services.database import get_db_session
        
        try:
            async with get_db_session() as session:
                user = await session.query(User).filter(User.telegram_id == telegram_id).first()
                
                if not user:
                    return None
                
                if user.is_banned:
                    logger.warning(f"Banned user tried to authenticate", telegram_id=telegram_id)
                    return None
                
                # Обновляем последнюю активность
                user.update_activity()
                await session.commit()
                
                # Создаем токены
                tokens = self.token_manager.create_user_token(user)
                
                logger.info(f"User authenticated", telegram_id=telegram_id, user_type=user.current_user_type)
                return tokens
                
        except Exception as e:
            logger.error(f"User authentication failed: {e}")
            return None
    
    async def authenticate_admin(self, username: str, password: str, ip_address: str = None) -> Optional[Dict[str, Any]]:
        """Аутентификация администратора"""
        from shared.services.database import get_db_session
        
        try:
            async with get_db_session() as session:
                admin = await session.query(AdminUser).filter(AdminUser.username == username).first()
                
                if not admin:
                    logger.warning(f"Admin login attempt with unknown username", username=username)
                    return None
                
                # Проверяем, не заблокирован ли аккаунт
                if not admin.can_login:
                    logger.warning(f"Blocked admin tried to login", username=username)
                    admin.record_login_attempt(False, ip_address)
                    await session.commit()
                    return None
                
                # Проверяем пароль
                if not admin.check_password(password):
                    logger.warning(f"Admin login attempt with wrong password", username=username)
                    admin.record_login_attempt(False, ip_address)
                    await session.commit()
                    return None
                
                # Успешная аутентификация
                admin.record_login_attempt(True, ip_address)
                await session.commit()
                
                # Создаем токены
                tokens = self.token_manager.create_admin_token(admin)
                
                logger.info(f"Admin authenticated", username=username, role=admin.role)
                
                return {
                    "admin": admin.to_dict_safe(),
                    **tokens
                }
                
        except Exception as e:
            logger.error(f"Admin authentication failed: {e}")
            return None
    
    def check_admin_permission(self, token_payload: Dict[str, Any], required_permission: str) -> bool:
        """Проверить права администратора"""
        if not token_payload or "admin_id" not in token_payload:
            return False
        
        # Суперадмин имеет все права
        if token_payload.get("role") == AdminRole.SUPER_ADMIN:
            return True
        
        permissions = token_payload.get("permissions", [])
        return required_permission in permissions
    
    def check_admin_role_level(self, token_payload: Dict[str, Any], required_level: int) -> bool:
        """Проверить уровень роли администратора"""
        if not token_payload or "admin_id" not in token_payload:
            return False
        
        role = token_payload.get("role")
        current_level = AdminRole.HIERARCHY.get(role, 0)
        
        return current_level >= required_level
    
    async def change_user_password(self, user_id: int, old_password: str, new_password: str) -> Dict[str, Any]:
        """Изменить пароль пользователя"""
        from shared.services.database import get_db_session
        
        # Проверяем силу нового пароля
        strength = self.password_manager.validate_password_strength(new_password)
        if not strength["valid"]:
            return {
                "success": False,
                "error": "Слабый пароль",
                "issues": strength["issues"]
            }
        
        try:
            async with get_db_session() as session:
                # Для администраторов
                if "admin" in locals():  # Проверяем контекст
                    admin = await session.query(AdminUser).filter(AdminUser.id == user_id).first()
                    if not admin:
                        return {"success": False, "error": "Администратор не найден"}
                    
                    if not admin.check_password(old_password):
                        return {"success": False, "error": "Неверный старый пароль"}
                    
                    admin.set_password(new_password)
                else:
                    # Для обычных пользователей (если будет система паролей)
                    pass
                
                await session.commit()
                
                logger.info(f"Password changed", user_id=user_id)
                return {"success": True, "message": "Пароль успешно изменен"}
                
        except Exception as e:
            logger.error(f"Password change failed: {e}")
            return {"success": False, "error": "Ошибка при изменении пароля"}
    
    def generate_reset_token(self, user_id: int) -> str:
        """Сгенерировать токен для сброса пароля"""
        reset_data = {
            "user_id": user_id,
            "purpose": "password_reset",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return self.token_manager.create_token(reset_data, "reset", 60)  # 1 час
    
    def verify_reset_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Проверить токен сброса пароля"""
        payload = self.token_manager.verify_token(token)
        
        if not payload or payload.get("type") != "reset":
            return None
        
        if payload.get("purpose") != "password_reset":
            return None
            
        return payload
    
    async def reset_password(self, reset_token: str, new_password: str) -> Dict[str, Any]:
        """Сбросить пароль используя токен"""
        payload = self.verify_reset_token(reset_token)
        
        if not payload:
            return {"success": False, "error": "Недействительный токен"}
        
        # Проверяем силу пароля
        strength = self.password_manager.validate_password_strength(new_password)
        if not strength["valid"]:
            return {
                "success": False,
                "error": "Слабый пароль",
                "issues": strength["issues"]
            }
        
        try:
            user_id = payload.get("user_id")
            
            from shared.services.database import get_db_session
            async with get_db_session() as session:
                admin = await session.query(AdminUser).filter(AdminUser.id == user_id).first()
                
                if not admin:
                    return {"success": False, "error": "Пользователь не найден"}
                
                admin.set_password(new_password)
                admin.unlock_account()  # Разблокировать если был заблокирован
                await session.commit()
                
                # Отзываем все токены пользователя
                # В продакшене нужно реализовать более продвинутую систему отзыва
                
                logger.info(f"Password reset successful", user_id=user_id)
                return {"success": True, "message": "Пароль успешно сброшен"}
                
        except Exception as e:
            logger.error(f"Password reset failed: {e}")
            return {"success": False, "error": "Ошибка при сбросе пароля"}
    
    def create_invite_token(self, admin_id: int, role: str, email: str = None) -> str:
        """Создать токен приглашения для нового администратора"""
        invite_data = {
            "invited_by": admin_id,
            "role": role,
            "email": email,
            "purpose": "admin_invite",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return self.token_manager.create_token(invite_data, "invite", 10080)  # 7 дней
    
    def verify_invite_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Проверить токен приглашения"""
        payload = self.token_manager.verify_token(token)
        
        if not payload or payload.get("type") != "invite":
            return None
        
        if payload.get("purpose") != "admin_invite":
            return None
            
        return payload
    
    async def accept_invite(self, invite_token: str, username: str, password: str, 
                          full_name: str = None) -> Dict[str, Any]:
        """Принять приглашение и создать аккаунт администратора"""
        payload = self.verify_invite_token(invite_token)
        
        if not payload:
            return {"success": False, "error": "Недействительное приглашение"}
        
        # Проверяем силу пароля
        strength = self.password_manager.validate_password_strength(password)
        if not strength["valid"]:
            return {
                "success": False,
                "error": "Слабый пароль",
                "issues": strength["issues"]
            }
        
        try:
            from shared.services.database import get_db_session
            async with get_db_session() as session:
                # Проверяем, не существует ли уже такой username
                existing_admin = await session.query(AdminUser).filter(AdminUser.username == username).first()
                if existing_admin:
                    return {"success": False, "error": "Имя пользователя уже занято"}
                
                # Создаем нового администратора
                admin = AdminUser.create_admin(
                    username=username,
                    password=password,
                    role=payload.get("role", AdminRole.SUPPORT),
                    email=payload.get("email"),
                    created_by_admin_id=payload.get("invited_by")
                )
                
                if full_name:
                    admin.full_name = full_name
                
                admin.is_verified = True
                
                session.add(admin)
                await session.commit()
                
                logger.info(f"Admin account created via invite", username=username, role=admin.role)
                
                # Создаем токены для нового админа
                tokens = self.token_manager.create_admin_token(admin)
                
                return {
                    "success": True,
                    "message": "Аккаунт администратора создан",
                    "admin": admin.to_dict_safe(),
                    **tokens
                }
                
        except Exception as e:
            logger.error(f"Invite acceptance failed: {e}")
            return {"success": False, "error": "Ошибка при создании аккаунта"}
    
    def cleanup_revoked_tokens(self):
        """Очистить устаревшие отозванные токены"""
        # В продакшене нужна более умная логика с хранением времени отзыва
        if len(self.revoked_tokens) > 10000:
            self.revoked_tokens.clear()
            logger.info("Cleared revoked tokens cache")

# Декораторы для авторизации
def require_auth(func):
    """Декоратор для обязательной аутентификации"""
    async def wrapper(*args, **kwargs):
        # Извлекаем токен из заголовков запроса
        # Реализация зависит от используемого фреймворка
        token = kwargs.get('token') or args[0] if args else None
        
        if not token:
            raise PermissionError("Требуется аутентификация")
        
        auth_service = AuthService()
        payload = auth_service.token_manager.verify_token(token)
        
        if not payload or auth_service.is_token_revoked(token):
            raise PermissionError("Недействительный токен")
        
        # Добавляем информацию о пользователе в kwargs
        kwargs['current_user'] = payload
        
        return await func(*args, **kwargs)
    return wrapper

def require_admin_permission(permission: str):
    """Декоратор для проверки прав администратора"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            
            if not current_user or "admin_id" not in current_user:
                raise PermissionError("Требуются права администратора")
            
            auth_service = AuthService()
            if not auth_service.check_admin_permission(current_user, permission):
                raise PermissionError(f"Недостаточно прав: требуется {permission}")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_admin_role(min_role_level: int):
    """Декоратор для проверки уровня роли администратора"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            
            if not current_user or "admin_id" not in current_user:
                raise PermissionError("Требуются права администратора")
            
            auth_service = AuthService()
            if not auth_service.check_admin_role_level(current_user, min_role_level):
                raise PermissionError("Недостаточный уровень роли")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Утилиты для работы с аутентификацией
class AuthUtils:
    """Утилиты аутентификации"""
    
    @staticmethod
    def generate_telegram_auth_hash(auth_data: Dict[str, Any], bot_token: str) -> str:
        """Генерировать хеш для проверки данных от Telegram"""
        import hmac
        
        # Создаем строку для хеширования из данных
        data_check_arr = []
        for key, value in sorted(auth_data.items()):
            if key != 'hash':
                data_check_arr.append(f"{key}={value}")
        
        data_check_string = '\n'.join(data_check_arr)
        
        # Создаем HMAC
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        auth_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return auth_hash
    
    @staticmethod
    def verify_telegram_auth(auth_data: Dict[str, Any], bot_token: str) -> bool:
        """Проверить аутентификационные данные от Telegram"""
        received_hash = auth_data.get('hash')
        if not received_hash:
            return False
        
        calculated_hash = AuthUtils.generate_telegram_auth_hash(auth_data, bot_token)
        
        return received_hash == calculated_hash
    
    @staticmethod
    def extract_token_from_header(authorization_header: str) -> Optional[str]:
        """Извлечь токен из заголовка Authorization"""
        if not authorization_header:
            return None
        
        if not authorization_header.startswith('Bearer '):
            return None
        
        return authorization_header[7:]  # Убираем 'Bearer '
    
    @staticmethod
    def generate_csrf_token() -> str:
        """Сгенерировать CSRF токен"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_csrf_token(token: str, session_token: str) -> bool:
        """Проверить CSRF токен"""
        # Простая проверка, в продакшене нужна более сложная логика
        return len(token) == 43 and token.isalnum()  # urlsafe токен всегда 43 символа

# Класс для управления сессиями
class SessionManager:
    """Менеджер сессий пользователей"""
    
    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service
        self.active_sessions = {}  # user_id -> список сессий
    
    def create_session(self, user_id: int, device_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """Создать новую сессию"""
        session_id = secrets.token_hex(16)
        
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "device_info": device_info or {},
            "ip_address": device_info.get("ip_address") if device_info else None
        }
        
        # Добавляем сессию к списку активных сессий пользователя
        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = []
        
        self.active_sessions[user_id].append(session_data)
        
        # Ограничиваем количество активных сессий (максимум 5)
        if len(self.active_sessions[user_id]) > 5:
            oldest_session = min(self.active_sessions[user_id], key=lambda x: x["created_at"])
            self.active_sessions[user_id].remove(oldest_session)
        
        return session_data
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получить данные сессии"""
        for user_sessions in self.active_sessions.values():
            for session in user_sessions:
                if session["session_id"] == session_id:
                    return session
        return None
    
    def update_session_activity(self, session_id: str):
        """Обновить время активности сессии"""
        session = self.get_session(session_id)
        if session:
            session["last_activity"] = datetime.utcnow()
    
    def terminate_session(self, session_id: str) -> bool:
        """Завершить конкретную сессию"""
        for user_id, user_sessions in self.active_sessions.items():
            for session in user_sessions:
                if session["session_id"] == session_id:
                    user_sessions.remove(session)
                    return True
        return False
    
    def terminate_all_user_sessions(self, user_id: int) -> int:
        """Завершить все сессии пользователя"""
        if user_id in self.active_sessions:
            count = len(self.active_sessions[user_id])
            self.active_sessions[user_id] = []
            return count
        return 0
    
    def get_user_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Получить все активные сессии пользователя"""
        return self.active_sessions.get(user_id, [])
    
    def cleanup_expired_sessions(self):
        """Очистить истекшие сессии"""
        cutoff_time = datetime.utcnow() - timedelta(hours=24)  # Сессии старше 24 часов
        
        for user_id in list(self.active_sessions.keys()):
            self.active_sessions[user_id] = [
                session for session in self.active_sessions[user_id]
                if session["last_activity"] > cutoff_time
            ]
            
            # Удаляем пустые списки сессий
            if not self.active_sessions[user_id]:
                del self.active_sessions[user_id]