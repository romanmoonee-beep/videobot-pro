"""
VideoBot Pro - Payment Model
Модель для обработки платежей и Premium подписок
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    BigInteger, String, Integer, Boolean, DateTime, 
    Text, JSON, ForeignKey, Index, CheckConstraint, 
    Numeric, DECIMAL
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import BaseModel


class PaymentStatus:
    """Статусы платежей"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    EXPIRED = "expired"
    
    ALL = [PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED, REFUNDED, PARTIALLY_REFUNDED, EXPIRED]


class PaymentMethod:
    """Методы платежа"""
    STRIPE = "stripe"
    PAYPAL = "paypal"
    TELEGRAM_PAYMENTS = "telegram_payments"
    CRYPTO = "crypto"
    BANK_TRANSFER = "bank_transfer"
    GIFT_CODE = "gift_code"
    ADMIN_GRANT = "admin_grant"
    
    ALL = [STRIPE, PAYPAL, TELEGRAM_PAYMENTS, CRYPTO, BANK_TRANSFER, GIFT_CODE, ADMIN_GRANT]


class SubscriptionPlan:
    """Планы подписок"""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"
    
    ALL = [MONTHLY, QUARTERLY, YEARLY, LIFETIME]
    
    # Длительность в днях
    DURATIONS = {
        MONTHLY: 30,
        QUARTERLY: 90,
        YEARLY: 365,
        LIFETIME: 36500  # 100 лет
    }


class Currency:
    """Поддерживаемые валюты"""
    USD = "USD"
    EUR = "EUR"
    RUB = "RUB"
    BTC = "BTC"
    ETH = "ETH"
    
    ALL = [USD, EUR, RUB, BTC, ETH]


class Payment(BaseModel):
    """
    Модель платежа
    
    Отслеживает все платежи пользователей за Premium подписки,
    включая статусы, методы оплаты и возвраты
    """
    
    __tablename__ = "payments"
    
    # Связь с пользователем
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID пользователя"
    )
    
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Telegram ID пользователя"
    )
    
    # Основная информация о платеже
    payment_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Уникальный идентификатор платежа"
    )
    
    external_payment_id: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        index=True,
        comment="ID платежа в внешней системе (Stripe, PayPal, etc.)"
    )
    
    # Статус платежа
    status: Mapped[str] = mapped_column(
        String(30),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
        comment="Статус платежа"
    )
    
    # Метод и детали платежа
    payment_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="Метод платежа"
    )
    
    payment_provider: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Провайдер платежа (stripe, paypal, etc.)"
    )
    
    # Финансовые данные
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False,
        comment="Сумма платежа"
    )
    
    currency: Mapped[str] = mapped_column(
        String(10),
        default=Currency.USD,
        nullable=False,
        comment="Валюта платежа"
    )
    
    amount_usd: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 2),
        nullable=True,
        comment="Сумма в долларах США (для аналитики)"
    )
    
    # Комиссии и сборы
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 2),
        nullable=True,
        comment="Размер комиссии платежной системы"
    )
    
    net_amount: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 2),
        nullable=True,
        comment="Чистая сумма после комиссий"
    )
    
    # Подписка
    subscription_plan: Mapped[str] = mapped_column(
        String(20),
        default=SubscriptionPlan.MONTHLY,
        nullable=False,
        comment="План подписки"
    )
    
    subscription_duration_days: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
        comment="Длительность подписки в днях"
    )
    
    # Временные метки
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Время инициации платежа"
    )
    
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время завершения платежа"
    )
    
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Время истечения платежа (для pending)"
    )
    
    # Возвраты
    refund_amount: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 2),
        nullable=True,
        comment="Сумма возврата"
    )
    
    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Время возврата"
    )
    
    refund_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Причина возврата"
    )
    
    # Дополнительные данные платежа
    payment_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Дополнительные детали платежа"
    )
    
    provider_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        comment="Ответ от платежного провайдера"
    )
    
    # IP и местоположение
    client_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IP адрес клиента"
    )
    
    country_code: Mapped[Optional[str]] = mapped_column(
        String(5),
        nullable=True,
        comment="Код страны клиента"
    )
    
    # Fraud detection
    risk_score: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Оценка риска мошенничества (0-100)"
    )
    
    is_suspicious: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Помечен как подозрительный"
    )
    
    # Уведомления
    notification_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Отправлено ли уведомление пользователю"
    )
    
    admin_notification_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Отправлено ли уведомление админам"
    )
    
    # Промокоды и скидки
    promo_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Использованный промокод"
    )
    
    discount_percent: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Процент скидки"
    )
    
    discount_amount: Mapped[Optional[Decimal]] = mapped_column(
        DECIMAL(10, 2),
        nullable=True,
        comment="Сумма скидки"
    )
    
    # Метаданные
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User agent клиента"
    )
    
    source: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Источник платежа (bot, web, api)"
    )
    
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Заметки о платеже"
    )
    
    # Relationships
    user = relationship("User", back_populates="payments")
    
    # Constraints и индексы
    __table_args__ = (
        CheckConstraint(
            status.in_(PaymentStatus.ALL),
            name='check_payment_status'
        ),
        CheckConstraint(
            payment_method.in_(PaymentMethod.ALL),
            name='check_payment_method'
        ),
        CheckConstraint(
            subscription_plan.in_(SubscriptionPlan.ALL),
            name='check_subscription_plan'
        ),
        CheckConstraint(
            currency.in_(Currency.ALL),
            name='check_currency'
        ),
        CheckConstraint(
            'amount > 0',
            name='check_amount_positive'
        ),
        CheckConstraint(
            'subscription_duration_days > 0',
            name='check_duration_positive'
        ),
        CheckConstraint(
            'risk_score >= 0 AND risk_score <= 100',
            name='check_risk_score_range'
        ),
        # Индексы для оптимизации
        Index('idx_payment_user_status', 'user_id', 'status'),
        Index('idx_payment_status_created', 'status', 'created_at'),
        Index('idx_payment_method_status', 'payment_method', 'status'),
        Index('idx_payment_external_id', 'external_payment_id'),
        Index('idx_payment_expires_at', 'expires_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, payment_id='{self.payment_id}', amount={self.amount}, status='{self.status}')>"
    
    @property
    def is_completed(self) -> bool:
        """Завершен ли платеж успешно"""
        return self.status == PaymentStatus.COMPLETED
    
    @property
    def is_pending(self) -> bool:
        """Ожидает ли платеж обработки"""
        return self.status == PaymentStatus.PENDING
    
    @property
    def is_failed(self) -> bool:
        """Провалился ли платеж"""
        return self.status == PaymentStatus.FAILED
    
    @property
    def is_refunded(self) -> bool:
        """Возвращен ли платеж"""
        return self.status in [PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]
    
    @property
    def is_expired(self) -> bool:
        """Истек ли срок платежа"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    @property
    def processing_time_minutes(self) -> Optional[int]:
        """Время обработки платежа в минутах"""
        if not self.completed_at:
            return None
        delta = self.completed_at - self.initiated_at
        return int(delta.total_seconds() / 60)
    
    @property
    def final_amount(self) -> Decimal:
        """Итоговая сумма после скидки"""
        amount = self.amount
        if self.discount_amount:
            amount -= self.discount_amount
        return max(Decimal('0.00'), amount)
    
    @classmethod
    def generate_payment_id(cls) -> str:
        """Генерирует уникальный ID платежа"""
        import uuid
        return f"pay_{uuid.uuid4().hex[:16]}"
    
    @classmethod
    def create_payment(cls, user_id: int, telegram_user_id: int, amount: Decimal,
                      subscription_plan: str, payment_method: str, currency: str = Currency.USD,
                      **kwargs) -> 'Payment':
        """Создать новый платеж"""
        payment_id = cls.generate_payment_id()
        duration_days = SubscriptionPlan.DURATIONS.get(subscription_plan, 30)
        
        # Устанавливаем срок истечения для pending платежей
        expires_at = datetime.utcnow() + timedelta(hours=1)  # 1 час на оплату
        
        return cls(
            payment_id=payment_id,
            user_id=user_id,
            telegram_user_id=telegram_user_id,
            amount=amount,
            currency=currency,
            subscription_plan=subscription_plan,
            subscription_duration_days=duration_days,
            payment_method=payment_method,
            expires_at=expires_at,
            **kwargs
        )
    
    def mark_as_processing(self, external_payment_id: str = None, provider_response: Dict[str, Any] = None):
        """Пометить платеж как обрабатывающийся"""
        self.status = PaymentStatus.PROCESSING
        if external_payment_id:
            self.external_payment_id = external_payment_id
        if provider_response:
            self.provider_response = provider_response
    
    def complete_payment(self, external_payment_id: str = None, fee_amount: Decimal = None,
                        provider_response: Dict[str, Any] = None):
        """Завершить платеж успешно"""
        self.status = PaymentStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        
        if external_payment_id:
            self.external_payment_id = external_payment_id
        if fee_amount:
            self.fee_amount = fee_amount
            self.net_amount = self.amount - fee_amount
        if provider_response:
            self.provider_response = provider_response
    
    def fail_payment(self, reason: str = None, provider_response: Dict[str, Any] = None):
        """Пометить платеж как неудачный"""
        self.status = PaymentStatus.FAILED
        self.completed_at = datetime.utcnow()
        
        if reason:
            if not self.notes:
                self.notes = ""
            self.notes += f"Failed: {reason}\n"
        
        if provider_response:
            self.provider_response = provider_response
    
    def cancel_payment(self, reason: str = None):
        """Отменить платеж"""
        self.status = PaymentStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        
        if reason:
            if not self.notes:
                self.notes = ""
            self.notes += f"Cancelled: {reason}\n"
    
    def process_refund(self, refund_amount: Decimal, reason: str = None, 
                      external_refund_id: str = None):
        """Обработать возврат"""
        self.refund_amount = refund_amount
        self.refunded_at = datetime.utcnow()
        if reason:
            self.refund_reason = reason
        
        # Определяем статус
        if refund_amount >= self.amount:
            self.status = PaymentStatus.REFUNDED
        else:
            self.status = PaymentStatus.PARTIALLY_REFUNDED
        
        # Сохраняем ID возврата
        if external_refund_id:
            if not self.provider_response:
                self.provider_response = {}
            self.provider_response['refund_id'] = external_refund_id
    
    def apply_discount(self, promo_code: str = None, discount_percent: int = None, 
                      discount_amount: Decimal = None):
        """Применить скидку"""
        if promo_code:
            self.promo_code = promo_code
        
        if discount_percent:
            self.discount_percent = discount_percent
            self.discount_amount = (self.amount * discount_percent) / 100
        elif discount_amount:
            self.discount_amount = discount_amount
            self.discount_percent = int((discount_amount / self.amount) * 100)
    
    def set_risk_assessment(self, risk_score: int, is_suspicious: bool = False):
        """Установить оценку риска"""
        self.risk_score = max(0, min(100, risk_score))
        self.is_suspicious = is_suspicious or risk_score > 70
    
    def add_payment_detail(self, key: str, value: Any):
        """Добавить деталь платежа"""
        if not self.payment_details:
            self.payment_details = {}
        self.payment_details[key] = value
    
    def get_subscription_end_date(self, start_date: datetime = None) -> datetime:
        """Получить дату окончания подписки"""
        if not start_date:
            start_date = self.completed_at or datetime.utcnow()
        return start_date + timedelta(days=self.subscription_duration_days)
    
    def to_dict_safe(self) -> Dict[str, Any]:
        """Безопасное представление для пользователя"""
        return {
            'payment_id': self.payment_id,
            'amount': float(self.amount),
            'currency': self.currency,
            'final_amount': float(self.final_amount),
            'status': self.status,
            'payment_method': self.payment_method,
            'subscription_plan': self.subscription_plan,
            'subscription_duration_days': self.subscription_duration_days,
            'initiated_at': self.initiated_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'promo_code': self.promo_code,
            'discount_percent': self.discount_percent,
            'discount_amount': float(self.discount_amount) if self.discount_amount else None,
            'refund_amount': float(self.refund_amount) if self.refund_amount else None,
            'refunded_at': self.refunded_at.isoformat() if self.refunded_at else None,
            'processing_time_minutes': self.processing_time_minutes
        }
    
    def to_dict_admin(self) -> Dict[str, Any]:
        """Полное представление для администратора"""
        user_dict = self.to_dict_safe()
        user_dict.update({
            'id': self.id,
            'user_id': self.user_id,
            'telegram_user_id': self.telegram_user_id,
            'external_payment_id': self.external_payment_id,
            'payment_provider': self.payment_provider,
            'amount_usd': float(self.amount_usd) if self.amount_usd else None,
            'fee_amount': float(self.fee_amount) if self.fee_amount else None,
            'net_amount': float(self.net_amount) if self.net_amount else None,
            'client_ip': self.client_ip,
            'country_code': self.country_code,
            'risk_score': self.risk_score,
            'is_suspicious': self.is_suspicious,
            'notification_sent': self.notification_sent,
            'admin_notification_sent': self.admin_notification_sent,
            'user_agent': self.user_agent,
            'source': self.source,
            'notes': self.notes,
            'payment_details': self.payment_details,
            'provider_response': self.provider_response,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        })
        return user_dict