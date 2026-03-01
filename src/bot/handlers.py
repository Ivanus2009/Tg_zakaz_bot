"""Обработчики команд и сообщений Telegram-бота.

Раньше здесь была логика Mini App: кнопка с WebAppInfo(url=WEBAPP_URL) открывала
мини-приложение в Telegram; sendData отправлял данные боту (order_created, request_payment).
Сейчас флоу только на сайте: бот лишь отдаёт ссылку на сайт заказов.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx
from aiogram import Router, F
from aiogram.filters import Command, CommandStart, Filter
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
)

if TYPE_CHECKING:
    pass

from database import get_user, create_user
from database.models import User

router = Router()

# URL сайта заказов (бот только редиректит по ссылке)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com").strip().rstrip("/")

# URL backend для вызовов API (payment pending, order-from-payment)
def _backend_url() -> str:
    url = os.getenv("BACKEND_URL", "").strip()
    if url:
        return url.rstrip("/")
    # Fallback: тот же хост, что и WEBAPP_URL
    base = os.getenv("WEBAPP_URL", "http://localhost:8000").strip().rstrip("/")
    return base


def _bot_secret() -> str:
    return os.getenv("BOT_INTERNAL_SECRET", "").strip()


class SuccessfulPaymentFilter(Filter):
    """Фильтр только для сообщений с successful_payment."""

    async def __call__(self, message: Message) -> bool:
        return bool(getattr(message, "successful_payment", None))


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start."""
    user = message.from_user
    if not user:
        return

    # Регистрируем или обновляем пользователя
    db_user = await get_user(user.id)
    if not db_user:
        new_user = User(
            telegram_id=user.id,
            first_name=user.first_name or "Пользователь",
            last_name=user.last_name,
            username=user.username,
        )
        await create_user(new_user)
        welcome_text = (
            f"Привет, {user.first_name}! 👋\n\n"
            "Добро пожаловать! Заказывайте на нашем сайте — нажмите кнопку ниже."
        )
    else:
        welcome_text = (
            f"С возвращением, {user.first_name}! 👋\n\n"
            "Заказывайте на нашем сайте. Нажмите кнопку ниже."
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть сайт заказов", url=WEBAPP_URL)]
        ]
    )
    await message.answer(welcome_text, reply_markup=keyboard)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """Ссылка на сайт заказов."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть сайт заказов", url=WEBAPP_URL)]
        ]
    )
    await message.answer("Заказывайте на нашем сайте. Нажмите кнопку ниже:", reply_markup=keyboard)


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message) -> None:
    """Совместимость со старым Mini App: если кто-то отправит web_app_data — направляем на сайт."""
    await message.answer(f"Оформите заказ на сайте: {WEBAPP_URL}")


@router.pre_checkout_query()
async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    """Подтверждение оплаты перед списанием."""
    await pre_checkout_query.answer(ok=True)


@router.message(SuccessfulPaymentFilter())
async def handle_successful_payment(message: Message) -> None:
    """После успешной оплаты: создать заказ на backend и уведомить пользователя."""
    payload = message.successful_payment.invoice_payload
    total = message.successful_payment.total_amount / 100  # копейки -> рубли
    secret = _bot_secret()
    if not secret:
        await message.answer("❌ Ошибка настройки. Заказ не создан. Обратитесь в поддержку.")
        return
    base = _backend_url()
    chat_id = message.chat.id
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{base}/api/order-from-payment",
            headers={"X-Bot-Secret": secret, "Content-Type": "application/json"},
            json={"payment_token": payload, "telegram_id": chat_id},
        )
    if r.status_code != 200:
        await message.answer(
            "❌ Оплата прошла, но не удалось создать заказ. Деньги не списаны. Обратитесь в поддержку."
        )
        return
    body = r.json()
    if not body.get("success"):
        await message.answer("❌ " + (body.get("error") or "Заказ не создан."))
        return
    order_id = body.get("order_id", "")
    await message.answer(
        f"✅ Заказ успешно оформлен и оплачен онлайн!\n\n"
        f"📋 Номер заказа: {order_id}\n"
        f"💰 Сумма: {total:.2f} ₽\n"
        f"💳 Оплачено онлайн\n\n"
        "Спасибо за заказ!"
    )

