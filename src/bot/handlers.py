"""Обработчики команд и сообщений Telegram-бота."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

# #region agent log
def _debug_log(message: str, data: dict, hypothesis_id: str) -> None:
    try:
        root = Path(__file__).resolve().parents[2]
        log_path = (root / "data" / "debug.log") if (str(root) == "/app") else (root / ".cursor" / "debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = (
            json.dumps(
                {
                    "location": "handlers.py",
                    "message": message,
                    "data": data,
                    "hypothesisId": hypothesis_id,
                    "timestamp": int(time.time() * 1000),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
# #endregion

import httpx
from aiogram import Router, F
from aiogram.filters import Command, CommandStart, Filter
from aiogram.types import (
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

if TYPE_CHECKING:
    pass

from database import db, get_user, create_user
from database.models import User

router = Router()

# URL мини-приложения (будет настроен позже)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com/webapp")

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
            "Добро пожаловать в бот для заказов!\n\n"
            "Для начала работы нужно зарегистрироваться. "
            "Нажмите кнопку ниже, чтобы открыть меню заказов."
        )
    else:
        welcome_text = (
            f"С возвращением, {user.first_name}! 👋\n\n"
            "Готовы сделать заказ? Нажмите кнопку ниже, чтобы открыть меню."
        )

    # Кнопка для открытия мини-приложения
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="🛒 Открыть меню",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )]
        ],
        resize_keyboard=True,
    )

    await message.answer(welcome_text, reply_markup=keyboard)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """Открыть меню заказов."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="🛒 Открыть меню",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )]
        ],
        resize_keyboard=True,
    )
    await message.answer("Нажмите кнопку, чтобы открыть меню заказов:", reply_markup=keyboard)


@router.message(F.web_app_data)
async def handle_webapp_data(message: Message) -> None:
    """Обработка данных из мини-приложения."""
    try:
        data = json.loads(message.web_app_data.data)
        action = data.get("action")
        # #region agent log
        _debug_log(
            "handle_webapp_data received",
            {"action": action, "has_payment_token": bool(data.get("payment_token"))},
            "H1",
        )
        # #endregion

        if action == "order_created":
            order_id = data.get("order_id")
            total = data.get("total", 0)
            is_paid = data.get("paid", False)
            
            payment_status = "✅ Оплачено онлайн" if is_paid else "💵 Оплата при получении"
            
            await message.answer(
                f"✅ Заказ успешно сформирован и отправлен!\n\n"
                f"📋 Номер заказа: {order_id}\n"
                f"💰 Сумма: {total:.2f} ₽\n"
                f"💳 {payment_status}\n\n"
                "Спасибо за заказ! Мы свяжемся с вами для подтверждения."
            )
        elif action == "request_payment":
            payment_token = data.get("payment_token")
            if not payment_token:
                await message.answer("❌ Не передан токен платежа.")
                return
            provider_token = os.getenv("PAYMENT_PROVIDER_TOKEN", "").strip()
            # #region agent log
            _debug_log(
                "request_payment provider_token check",
                {"provider_token_set": bool(provider_token), "token_length": len(provider_token) if provider_token else 0},
                "H5",
            )
            # #endregion
            if not provider_token:
                await message.answer("💳 Оплата онлайн пока не настроена. Выберите «Оплата при получении».")
                return
            secret = _bot_secret()
            if not secret:
                await message.answer("❌ Ошибка настройки бота (секрет).")
                return
            base = _backend_url()
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{base}/api/payment/pending/{payment_token}",
                    headers={"X-Bot-Secret": secret},
                )
            try:
                body = r.json()
            except Exception:
                body = {}
            # #region agent log
            _debug_log(
                "request_payment backend response",
                {"status_code": r.status_code, "body_success": body.get("success"), "body_error": body.get("error")},
                "H2",
            )
            # #endregion
            if r.status_code != 200:
                await message.answer("❌ Не удалось загрузить данные заказа. Попробуйте снова оформить заказ.")
                return
            if not body.get("success"):
                await message.answer("❌ " + (body.get("error") or "Платёж не найден."))
                return
            total = float(body["total"])
            title = "Заказ в кафе"
            description = f"Оплата заказа на сумму {total:.2f} ₽"
            # Сумма в копейках для Telegram (RUB — 2 знака)
            amount_kopecks = int(round(total * 100))
            prices = [LabeledPrice(label="Заказ", amount=amount_kopecks)]
            # #region agent log
            _debug_log("request_payment before send_invoice", {"amount_kopecks": amount_kopecks}, "H3")
            # #endregion
            await message.bot.send_invoice(
                chat_id=message.chat.id,
                title=title,
                description=description,
                payload=payment_token,
                provider_token=provider_token,
                currency="RUB",
                prices=prices,
            )
            # #region agent log
            _debug_log("request_payment send_invoice success", {}, "H3")
            # #endregion
        elif action == "error":
            error_msg = data.get("message", "Произошла ошибка")
            await message.answer(f"❌ Ошибка: {error_msg}")
    except Exception as e:
        # #region agent log
        _debug_log("handle_webapp_data exception", {"error": str(e), "error_type": type(e).__name__}, "H3")
        # #endregion
        await message.answer(f"❌ Произошла ошибка при обработке данных: {e}")


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
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{base}/api/order-from-payment",
            headers={"X-Bot-Secret": secret, "Content-Type": "application/json"},
            json={"payment_token": payload},
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

