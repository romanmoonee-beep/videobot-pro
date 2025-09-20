"""
VideoBot Pro - Admin Authentication API
API endpoints для аутентификации администраторов
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
import structlog

from shared.schemas.admin import (
    AdminLoginSchema, AdminTokenSchema, AdminPasswordChangeSchema,
    AdminUserSchema, AdminRoleChangeSchema
)
from shared.services.auth import AuthService
from shared.services.database import get_db_session
from shared.models import AdminUser, AdminRole
from ..config import admin_settings
from ..dependencies import get_current_admin, get_auth_service, rate_limit
from ..utils.validators import validate_password_strength

logger = structlog.get_logger(__name__)
router = APIRouter()

@router.post("/login", response_model=AdminTokenSchema)
async def admin_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Аутентификация администратора
    
    Принимает username и password, возвращает JWT токены
    """
    try:
        # Получаем IP адрес клиента
        client_ip = getattr(request, 'client', {}).get('host', 'unknown') if request else 'unknown'
        
        # Попытка аутентификации
        result = await auth_service.authenticate_admin(
            username=form_data.username,
            password=form_data.password,
            ip_address=client_ip
        )
        
        if not result:
            logger.warning(
                "Failed admin login attempt",
                username=form_data.username,
                ip=client_ip
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверные учетные данные",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        logger.info(
            "Successful admin login",
            username=form_data.username,
            admin_id=result["admin"]["id"],
            role=result["admin"]["role"]
        )
        
        return AdminTokenSchema(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result["token_type"],
            expires_in=result["expires_in"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при входе в систему"
        )

@router.post("/refresh", response_model=AdminTokenSchema)
async def refresh_token(
    refresh_token: str,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Обновление access токена с помощью refresh токена
    """
    try:
        result = auth_service.token_manager.refresh_token(refresh_token)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительный refresh токен"
            )
        
        return AdminTokenSchema(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result["token_type"],
            expires_in=result["expires_in"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при обновлении токена"
        )

@router.post("/logout")
async def logout(
    token: str,
    current_admin: AdminUser = Depends(get_current_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Выход из системы (отзыв токена)
    """
    try:
        # Отзываем токен
        success = auth_service.revoke_token(token)
        
        if success:
            logger.info(f"Admin logged out", admin_id=current_admin.id)
            return {"message": "Успешный выход из системы"}
        else:
            return {"message": "Токен уже недействителен"}
            
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при выходе из системы"
        )

@router.get("/me", response_model=AdminUserSchema)
async def get_current_admin_info(
    current_admin: AdminUser = Depends(get_current_admin)
):
    """
    Получение информации о текущем администраторе
    """
    try:
        return AdminUserSchema.model_validate(current_admin)
    except Exception as e:
        logger.error(f"Error getting current admin info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении информации о пользователе"
        )

@router.post("/change-password")
async def change_password(
    password_data: AdminPasswordChangeSchema,
    current_admin: AdminUser = Depends(get_current_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Смена пароля администратора
    """
    try:
        # Проверяем текущий пароль
        if not current_admin.check_password(password_data.current_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный текущий пароль"
            )
        
        # Проверяем силу нового пароля
        strength = validate_password_strength(password_data.new_password)
        if not strength["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Слабый пароль",
                    "issues": strength["issues"]
                }
            )
        
        # Меняем пароль
        result = await auth_service.change_user_password(
            user_id=current_admin.id,
            old_password=password_data.current_password,
            new_password=password_data.new_password
        )
        
        if result["success"]:
            logger.info(f"Password changed", admin_id=current_admin.id)
            return {"message": "Пароль успешно изменен"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при смене пароля"
        )

@router.post("/request-password-reset")
async def request_password_reset(
    username: str,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Запрос на сброс пароля
    """
    try:
        async with get_db_session() as session:
            admin = await session.query(AdminUser).filter(
                AdminUser.username == username
            ).first()
            
            if not admin:
                # Не раскрываем информацию о существовании пользователя
                return {"message": "Если пользователь существует, инструкции отправлены"}
            
            # Генерируем токен сброса
            reset_token = auth_service.generate_reset_token(admin.id)
            
            # В реальном приложении здесь отправка email или Telegram сообщения
            # Пока что просто логируем
            logger.info(
                f"Password reset requested",
                admin_id=admin.id,
                username=username,
                reset_token=reset_token  # В продакшене не логировать!
            )
            
            return {"message": "Инструкции по сбросу пароля отправлены"}
            
    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при запросе сброса пароля"
        )

@router.post("/reset-password")
async def reset_password(
    reset_token: str,
    new_password: str,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Сброс пароля по токену
    """
    try:
        # Проверяем силу пароля
        strength = validate_password_strength(new_password)
        if not strength["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Слабый пароль",
                    "issues": strength["issues"]
                }
            )
        
        # Сбрасываем пароль
        result = await auth_service.reset_password(reset_token, new_password)
        
        if result["success"]:
            logger.info("Password reset successful")
            return {"message": "Пароль успешно сброшен"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при сбросе пароля"
        )

@router.post("/create-invite")
async def create_admin_invite(
    role: str,
    email: Optional[str] = None,
    current_admin: AdminUser = Depends(get_current_admin),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Создание приглашения для нового администратора
    Только суперадмин может создавать приглашения
    """
    try:
        # Проверяем права
        if not current_admin.is_super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для создания приглашений"
            )
        
        # Проверяем валидность роли
        if role not in AdminRole.ALL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Недопустимая роль. Доступные: {AdminRole.ALL}"
            )
        
        # Создаем токен приглашения
        invite_token = auth_service.create_invite_token(
            admin_id=current_admin.id,
            role=role,
            email=email
        )
        
        logger.info(
            f"Admin invite created",
            created_by=current_admin.id,
            role=role,
            email=email
        )
        
        # В реальном приложении здесь отправка приглашения по email
        return {
            "message": "Приглашение создано",
            "invite_token": invite_token,  # В продакшене отправлять по email
            "expires_in_days": 7
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin invite creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при создании приглашения"
        )

@router.post("/accept-invite")
async def accept_admin_invite(
    invite_token: str,
    username: str,
    password: str,
    full_name: Optional[str] = None,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Принятие приглашения и создание аккаунта администратора
    """
    try:
        # Проверяем силу пароля
        strength = validate_password_strength(password)
        if not strength["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Слабый пароль",
                    "issues": strength["issues"]
                }
            )
        
        # Принимаем приглашение
        result = await auth_service.accept_invite(
            invite_token=invite_token,
            username=username,
            password=password,
            full_name=full_name
        )
        
        if result["success"]:
            logger.info(f"Admin invite accepted", username=username)
            return {
                "message": "Аккаунт администратора создан",
                "admin": result["admin"],
                "access_token": result["access_token"],
                "refresh_token": result["refresh_token"],
                "token_type": result["token_type"],
                "expires_in": result["expires_in"]
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin invite acceptance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при принятии приглашения"
        )

@router.get("/verify-invite")
async def verify_admin_invite(
    invite_token: str,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Проверка действительности приглашения
    """
    try:
        payload = auth_service.verify_invite_token(invite_token)
        
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Недействительное или истекшее приглашение"
            )
        
        return {
            "valid": True,
            "role": payload.get("role"),
            "email": payload.get("email"),
            "invited_by": payload.get("invited_by")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Invite verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при проверке приглашения"
        )

@router.post("/enable-2fa")
async def enable_two_factor(
    current_admin: AdminUser = Depends(get_current_admin)
):
    """
    Включение двухфакторной аутентификации
    """
    try:
        import pyotp
        import qrcode
        from io import BytesIO
        import base64
        
        # Генерируем секретный ключ
        secret = pyotp.random_base32()
        
        # Создаем TOTP
        totp = pyotp.TOTP(secret)
        
        # Генерируем QR код
        provisioning_uri = totp.provisioning_uri(
            name=current_admin.username,
            issuer_name="VideoBot Pro Admin"
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Конвертируем в base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        # Временно сохраняем секрет (до подтверждения)
        # В реальном приложении лучше использовать временное хранилище
        
        return {
            "secret": secret,
            "qr_code": f"data:image/png;base64,{qr_code_base64}",
            "manual_entry_key": secret,
            "instructions": "Отсканируйте QR код приложением аутентификатора или введите ключ вручную"
        }
        
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="2FA не настроена на сервере"
        )
    except Exception as e:
        logger.error(f"2FA enable error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при настройке 2FA"
        )

@router.post("/confirm-2fa")
async def confirm_two_factor(
    secret: str,
    code: str,
    current_admin: AdminUser = Depends(get_current_admin)
):
    """
    Подтверждение настройки 2FA
    """
    try:
        import pyotp
        
        totp = pyotp.TOTP(secret)
        
        if totp.verify(code):
            # Сохраняем секрет в базе
            async with get_db_session() as session:
                admin = await session.get(AdminUser, current_admin.id)
                admin.enable_2fa(secret)
                await session.commit()
            
            logger.info(f"2FA enabled", admin_id=current_admin.id)
            return {"message": "Двухфакторная аутентификация включена"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный код аутентификации"
            )
            
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="2FA не настроена на сервере"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA confirm error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при подтверждении 2FA"
        )

@router.post("/disable-2fa")
async def disable_two_factor(
    password: str,
    current_admin: AdminUser = Depends(get_current_admin)
):
    """
    Отключение двухфакторной аутентификации
    """
    try:
        # Проверяем пароль
        if not current_admin.check_password(password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный пароль"
            )
        
        # Отключаем 2FA
        async with get_db_session() as session:
            admin = await session.get(AdminUser, current_admin.id)
            admin.disable_2fa()
            await session.commit()
        
        logger.info(f"2FA disabled", admin_id=current_admin.id)
        return {"message": "Двухфакторная аутентификация отключена"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"2FA disable error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при отключении 2FA"
        )

@router.get("/sessions")
async def get_active_sessions(
    current_admin: AdminUser = Depends(get_current_admin)
):
    """
    Получение списка активных сессий администратора
    """
    try:
        # В реальном приложении здесь получение сессий из Redis или БД
        # Пока что заглушка
        sessions = [
            {
                "id": "session_1",
                "device": "Chrome on Windows",
                "ip": "192.168.1.100",
                "location": "Moscow, Russia",
                "last_activity": datetime.utcnow().isoformat(),
                "is_current": True
            }
        ]
        
        return {"sessions": sessions}
        
    except Exception as e:
        logger.error(f"Get sessions error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при получении сессий"
        )

@router.delete("/sessions/{session_id}")
async def terminate_session(
    session_id: str,
    current_admin: AdminUser = Depends(get_current_admin)
):
    """
    Завершение конкретной сессии
    """
    try:
        # В реальном приложении здесь завершение сессии
        logger.info(f"Session terminated", admin_id=current_admin.id, session_id=session_id)
        return {"message": "Сессия завершена"}
        
    except Exception as e:
        logger.error(f"Terminate session error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при завершении сессии"
        )