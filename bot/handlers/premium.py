"""
VideoBot Pro - Premium System Handler
Обработчик Premium подписок и платежей
"""

import structlog
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from shared.config.database import get_async_session
from shared.models import User, Payment, PaymentStatus, PaymentMethod, SubscriptionPlan, Currency, EventType
from shared.models.analytics import track_payment_event
from shared.config.settings import settings
from bot.config import bot_config, get_message, MessageType
from bot.utils.user_manager import get_or_create_user, update_user_activity
from bot.keyboards.inline import create_premium_plans_keyboard, create_payment_methods_keyboard

logger = structlog.get_logger(__name__)

router = Router(name="premium")


class PremiumStates(StatesGroup):
    """Состояния FSM для Premium покупки"""
    choosing_plan = State()
    choosing_payment_method = State()
    processing_payment = State()


# Цены и планы Premium
PREMIUM_PLANS = {
    SubscriptionPlan.MONTHLY: {
        "name": "Месячный Premium",
        "price_usd": Decimal("3.99"),
        "price_rub": Decimal("399"),
        "duration_days": 30,
        "discount": 0,
        "popular": True
    },
    SubscriptionPlan.QUARTERLY: {
        "name": "Квартальный Premium", 
        "price_usd": Decimal("9.99"),
        "price_rub": Decimal("999"),
        "duration_days": 90,
        "discount": 16,  # 16% скидка
        "popular": False
    },
    SubscriptionPlan.YEARLY: {
        "name": "Годовой Premium",
        "price_usd": Decimal("29.99"),
        "price_rub": Decimal("2999"), 
        "duration_days": 365,
        "discount": 37,  # 37% скидка
        "popular": False
    }
}


@router.message(F.text.startswith(("/premium", "💎")))
async def premium_command(message: Message, state: FSMContext):
    """Команда Premium - показать информацию и планы"""
    user_id = message.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await get_or_create_user(
                session=session,
                telegram_id=user_id,
                username=message.from_user.username,
                first_name=message.from_user.first_name
            )
            
            await update_user_activity(session, user, message.message_id)
            await session.commit()
        
        # Проверяем текущий статус Premium
        if user.is_premium_active:
            await show_premium_status(message, user)
        else:
            await show_premium_plans(message, user, state)
    
    except Exception as e:
        logger.error(f"Error in premium command: {e}", user_id=user_id)
        await message.answer("Ошибка при загрузке Premium информации")


async def show_premium_status(message: Message, user: User):
    """Показать статус активного Premium"""
    days_left = (user.premium_expires_at - datetime.utcnow()).days if user.premium_expires_at else 0
    
    status_text = [
        "💎 <b>Premium активен!</b>",
        "",
        f"⏰ Действует до: {user.premium_expires_at.strftime('%d.%m.%Y')}",
        f"📅 Осталось дней: {days_left}",
        f"🔄 Автопродление: {'✅ Включено' if user.premium_auto_renew else '❌ Отключено'}",
        "",
        "🎁 <b>Ваши преимущества:</b>",
        "• ∞ Безлимитные скачивания",
        "• 🎬 4K качество видео",
        "• 📦 Архивы до 2GB",
        "• ☁️ Хранение файлов 30 дней",
        "• 🚀 Приоритетная обработка",
        "• 🔒 Без обязательных подписок"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика использования", callback_data="premium_stats")],
        [InlineKeyboardButton(text="⚙️ Настройки Premium", callback_data="premium_settings")],
        [InlineKeyboardButton(text="🎁 Пригласить друзей", callback_data="premium_referral")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    
    await message.answer("\n".join(status_text), reply_markup=keyboard)


async def show_premium_plans(message: Message, user: User, state: FSMContext):
    """Показать планы Premium для покупки"""
    
    # Проверяем использовал ли пользователь пробный период
    trial_info = ""
    if not user.trial_used and bot_config.trial_enabled:
        trial_info = "\n🎁 <i>Доступен пробный период 60 минут бесплатно!</i>"
    
    plans_text = [
        "💎 <b>Premium подписка VideoBot Pro</b>",
        "",
        "🚀 <b>Что вы получите:</b>",
        "• ∞ Безлимитные скачивания",
        "• 🎬 4K качество (до 2160p)",
        "• 📦 Файлы до 500MB",
        "• ☁️ Хранение файлов 30 дней", 
        "• 🏃 Приоритетная очередь",
        "• 🔒 Без обязательных подписок",
        "• 📊 Расширенная статистика",
        "",
        "💰 <b>Выберите план:</b>",
        trial_info
    ]
    
    keyboard = create_premium_plans_keyboard(PREMIUM_PLANS)
    
    await message.answer("\n".join(plans_text), reply_markup=keyboard)
    await state.set_state(PremiumStates.choosing_plan)


@router.callback_query(F.data.startswith("premium_plan_"))
async def handle_plan_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора плана Premium"""
    plan_key = callback.data.replace("premium_plan_", "")
    user_id = callback.from_user.id
    
    if plan_key not in PREMIUM_PLANS:
        await callback.answer("Неизвестный план", show_alert=True)
        return
    
    plan = PREMIUM_PLANS[plan_key]
    
    # Формируем сообщение о выбранном плане
    plan_text = [
        f"💎 <b>{plan['name']}</b>",
        "",
        f"💰 Цена: ${plan['price_usd']:.2f} ({plan['price_rub']:.0f}₽)",
        f"📅 Длительность: {plan['duration_days']} дней",
    ]
    
    if plan['discount'] > 0:
        plan_text.append(f"🔥 Скидка: {plan['discount']}%")
    
    if plan['popular']:
        plan_text.append("⭐ Самый популярный план")
    
    plan_text.extend([
        "",
        "🎁 <b>Включено в план:</b>",
        "• Безлимитные скачивания",
        "• 4K качество видео",
        "• Файлы до 500MB",
        "• Хранение 30 дней",
        "• Приоритетная поддержка",
        "",
        "💳 Выберите способ оплаты:"
    ])
    
    keyboard = create_payment_methods_keyboard()
    
    await callback.message.edit_text(
        "\n".join(plan_text),
        reply_markup=keyboard
    )
    
    # Сохраняем выбранный план
    await state.update_data(selected_plan=plan_key)
    await state.set_state(PremiumStates.choosing_payment_method)
    await callback.answer()


@router.callback_query(F.data.startswith("payment_"))
async def handle_payment_method(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора способа оплаты"""
    payment_method = callback.data.replace("payment_", "")
    user_id = callback.from_user.id
    
    # Получаем данные плана
    data = await state.get_data()
    plan_key = data.get("selected_plan")
    
    if not plan_key or plan_key not in PREMIUM_PLANS:
        await callback.answer("Ошибка: план не выбран", show_alert=True)
        return
    
    plan = PREMIUM_PLANS[plan_key]
    
    try:
        if payment_method == "telegram":
            await process_telegram_payment(callback, plan_key, plan, state)
        elif payment_method == "stripe":
            await process_stripe_payment(callback, plan_key, plan, state)
        elif payment_method == "crypto":
            await process_crypto_payment(callback, plan_key, plan, state)
        else:
            await callback.answer("Способ оплаты временно недоступен", show_alert=True)
    
    except Exception as e:
        logger.error(f"Error processing payment method: {e}", user_id=user_id)
        await callback.answer("Ошибка при обработке платежа", show_alert=True)


async def process_telegram_payment(callback: CallbackQuery, plan_key: str, plan: Dict, state: FSMContext):
    """Обработка оплаты через Telegram Payments"""
    user_id = callback.from_user.id
    
    # Проверяем настроен ли Telegram Payments
    if not settings.STRIPE_SECRET_KEY:
        await callback.message.edit_text(
            "❌ Telegram платежи временно недоступны.\n"
            "Попробуйте другой способ оплаты."
        )
        return
    
    try:
        # Создаем запись о платеже
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                await callback.answer("Пользователь не найден", show_alert=True)
                return
            
            # Создаем платеж
            payment = Payment.create_payment(
                user_id=user.id,
                telegram_user_id=user.telegram_id,
                amount=plan["price_usd"],
                subscription_plan=plan_key,
                payment_method=PaymentMethod.TELEGRAM_PAYMENTS,
                currency=Currency.USD,
                source="bot"
            )
            
            session.add(payment)
            await session.commit()
            
            # Аналитика
            await track_payment_event(
                event_type=EventType.PAYMENT_INITIATED,
                user_id=user.id,
                payment_amount=float(plan["price_usd"]),
                payment_method="telegram_payments"
            )
        
        # Создаем счет для оплаты
        prices = [LabeledPrice(
            label=plan["name"],
            amount=int(plan["price_usd"] * 100)  # В копейках
        )]
        
        await callback.message.answer_invoice(
            title=f"Premium подписка - {plan['name']}",
            description=(
                f"Premium подписка на {plan['duration_days']} дней\n"
                "• Безлимитные скачивания\n"
                "• 4K качество\n"
                "• Без обязательных подписок"
            ),
            payload=f"premium_{payment.payment_id}_{plan_key}",
            provider_token=settings.STRIPE_SECRET_KEY,
            currency="USD",
            prices=prices,
            start_parameter="premium_payment",
            photo_url="https://cdn.videobot.com/premium-logo.jpg",
            photo_width=512,
            photo_height=512
        )
        
        await state.update_data(payment_id=payment.payment_id)
        await state.set_state(PremiumStates.processing_payment)
        
    except Exception as e:
        logger.error(f"Error creating Telegram payment: {e}", user_id=user_id)
        await callback.message.edit_text("Ошибка при создании платежа. Попробуйте позже.")


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery, state: FSMContext):
    """Обработка pre-checkout запроса"""
    user_id = pre_checkout_query.from_user.id
    payload = pre_checkout_query.invoice_payload
    
    try:
        # Парсим payload
        if not payload.startswith("premium_"):
            await pre_checkout_query.answer(ok=False, error_message="Неверные данные платежа")
            return
        
        parts = payload.split("_")
        if len(parts) < 3:
            await pre_checkout_query.answer(ok=False, error_message="Неверный формат платежа")
            return
        
        payment_id = parts[1]
        plan_key = parts[2]
        
        # Проверяем платеж в базе
        async with get_async_session() as session:
            payment = await session.query(Payment).filter(
                Payment.payment_id == payment_id
            ).first()
            
            if not payment:
                await pre_checkout_query.answer(ok=False, error_message="Платеж не найден")
                return
            
            if payment.status != PaymentStatus.PENDING:
                await pre_checkout_query.answer(ok=False, error_message="Платеж уже обработан")
                return
            
            # Помечаем как обрабатываемый
            payment.mark_as_processing(
                external_payment_id=pre_checkout_query.id,
                provider_response={"pre_checkout_query_id": pre_checkout_query.id}
            )
            await session.commit()
        
        # Подтверждаем платеж
        await pre_checkout_query.answer(ok=True)
        
    except Exception as e:
        logger.error(f"Error in pre-checkout: {e}", user_id=user_id)
        await pre_checkout_query.answer(ok=False, error_message="Ошибка обработки платежа")


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message, state: FSMContext):
    """Обработка успешного платежа"""
    payment_info = message.successful_payment
    user_id = message.from_user.id
    payload = payment_info.invoice_payload
    
    try:
        # Парсим payload
        parts = payload.split("_")
        payment_id = parts[1]
        plan_key = parts[2]
        plan = PREMIUM_PLANS[plan_key]
        
        async with get_async_session() as session:
            # Находим платеж
            payment = await session.query(Payment).filter(
                Payment.payment_id == payment_id
            ).first()
            
            if not payment:
                await message.answer("Ошибка: платеж не найден")
                return
            
            # Получаем пользователя
            user = await session.get(User, payment.user_id)
            if not user:
                await message.answer("Ошибка: пользователь не найден")
                return
            
            # Обновляем платеж
            payment.complete_payment(
                external_payment_id=payment_info.provider_payment_charge_id,
                fee_amount=Decimal(payment_info.provider_payment_charge_id) * Decimal("0.029"),  # 2.9% комиссия Stripe
                provider_response={
                    "telegram_payment_charge_id": payment_info.telegram_payment_charge_id,
                    "provider_payment_charge_id": payment_info.provider_payment_charge_id,
                    "total_amount": payment_info.total_amount,
                    "currency": payment_info.currency
                }
            )
            
            # Активируем Premium
            user.activate_premium(duration_days=plan["duration_days"])
            
            await session.commit()
            
            # Аналитика
            await track_payment_event(
                event_type=EventType.PAYMENT_COMPLETED,
                user_id=user.id,
                payment_amount=float(payment.amount),
                payment_method="telegram_payments"
            )
        
        # Отправляем подтверждение
        success_text = [
            "🎉 <b>Premium успешно активирован!</b>",
            "",
            f"💎 План: {plan['name']}",
            f"📅 Действует до: {user.premium_expires_at.strftime('%d.%m.%Y')}",
            f"💰 Оплачено: ${payment.amount}",
            "",
            "🎁 <b>Ваши новые возможности:</b>",
            "• ∞ Безлимитные скачивания",
            "• 🎬 4K качество видео", 
            "• 📦 Файлы до 500MB",
            "• ☁️ Хранение 30 дней",
            "• 🚀 Приоритетная обработка",
            "",
            "💡 Теперь отправьте ссылку для скачивания!"
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Мой статус", callback_data="status")],
            [InlineKeyboardButton(text="🎁 Пригласить друзей", callback_data="premium_referral")]
        ])
        
        await message.answer(
            "\n".join(success_text),
            reply_markup=keyboard
        )
        
        await state.clear()
        
        logger.info(
            f"Premium activated successfully",
            user_id=user_id,
            payment_id=payment_id,
            plan=plan_key,
            amount=float(payment.amount)
        )
    
    except Exception as e:
        logger.error(f"Error processing successful payment: {e}", user_id=user_id)
        await message.answer(
            "⚠️ Платеж получен, но произошла ошибка при активации Premium. "
            "Обратитесь в поддержку."
        )


@router.callback_query(F.data == "premium_stats")
async def show_premium_stats(callback: CallbackQuery):
    """Показать статистику использования Premium"""
    user_id = callback.from_user.id
    
    try:
        async with get_async_session() as session:
            user = await session.get(User, user_id)
            if not user or not user.is_premium_active:
                await callback.answer("Premium не активен", show_alert=True)
                return
            
            # Рассчитываем статистику
            stats = user.stats or {}
            
            stats_text = [
                "📊 <b>Статистика Premium</b>",
                "",
                f"💎 Premium с: {user.premium_started_at.strftime('%d.%m.%Y')}",
                f"⏰ Действует до: {user.premium_expires_at.strftime('%d.%m.%Y')}",
                "",
                "📈 <b>Использование:</b>",
                f"• Скачано всего: {user.downloads_total}",
                f"• За этот месяц: {stats.get('monthly_downloads', 0)}",
                f"• Объем файлов: {stats.get('total_size_mb', 0):.1f} MB",
                "",
                "🎯 <b>По платформам:</b>"
            ]
            
            platforms = stats.get('platforms', {})
            for platform, count in platforms.items():
                emoji = {"youtube": "🔴", "tiktok": "🎵", "instagram": "📸"}.get(platform, "🎬")
                stats_text.append(f"• {emoji} {platform.title()}: {count}")
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_info")]
            ])
            
            await callback.message.edit_text(
                "\n".join(stats_text),
                reply_markup=keyboard
            )
    
    except Exception as e:
        logger.error(f"Error showing premium stats: {e}", user_id=user_id)
        await callback.answer("Ошибка получения статистики", show_alert=True)


@router.callback_query(F.data == "premium_referral")
async def show_premium_referral(callback: CallbackQuery):
    """Показать реферальную программу"""
    user_id = callback.from_user.id
    
    referral_link = f"https://t.me/{callback.bot.username}?start=ref_{user_id}"
    
    referral_text = [
        "🎁 <b>Пригласите друзей!</b>",
        "",
        "💰 <b>Получайте награды:</b>",
        "• 7 дней Premium за каждого друга",
        "• Бонусы при покупке Premium другом",
        "• Специальные акции для активных",
        "",
        f"🔗 <b>Ваша ссылка:</b>",
        f"<code>{referral_link}</code>",
        "",
        f"👥 Приглашено: {user.referrals_count if hasattr(user, 'referrals_count') else 0}"
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={referral_link}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="premium_info")]
    ])
    
    await callback.message.edit_text(
        "\n".join(referral_text),
        reply_markup=keyboard
    )
    await callback.answer()


# Дополнительные утилиты

async def check_premium_expiry():
    """Проверка истекших Premium подписок (запускается периодически)"""
    try:
        async with get_async_session() as session:
            expired_users = await session.query(User).filter(
                User.is_premium == True,
                User.premium_expires_at < datetime.utcnow()
            ).all()
            
            for user in expired_users:
                user.deactivate_premium()
                
                # Уведомление пользователя об истечении
                try:
                    from aiogram import Bot
                    bot = Bot.get_current()
                    await bot.send_message(
                        user.telegram_id,
                        "⏰ Ваша Premium подписка истекла.\n\n"
                        "💎 Продлить Premium можно командой /premium"
                    )
                except Exception:
                    pass  # Пользователь заблокировал бота
            
            await session.commit()
            
            if expired_users:
                logger.info(f"Deactivated {len(expired_users)} expired Premium subscriptions")
    
    except Exception as e:
        logger.error(f"Error checking premium expiry: {e}")


async def process_stripe_payment(callback: CallbackQuery, plan_key: str, plan: Dict, state: FSMContext):
    """Заглушка для Stripe платежей"""
    await callback.message.edit_text(
        "💳 <b>Stripe платежи</b>\n\n"
        "Функция в разработке.\n"
        "Попробуйте Telegram платежи."
    )


async def process_crypto_payment(callback: CallbackQuery, plan_key: str, plan: Dict, state: FSMContext):
    """Заглушка для крипто платежей"""
    await callback.message.edit_text(
        "₿ <b>Криптовалютные платежи</b>\n\n"
        "Функция в разработке.\n"
        "Попробуйте Telegram платежи."
    )