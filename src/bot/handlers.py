"""Обработчики команд и сообщений Telegram-бота."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup

if TYPE_CHECKING:
    from aiogram import Bot

from database import db, get_user, create_user
from database.models import User

router = Router()

# URL мини-приложения (будет настроен позже)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com/webapp")


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
        elif action == "error":
            error_msg = data.get("message", "Произошла ошибка")
            await message.answer(f"❌ Ошибка: {error_msg}")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка при обработке данных: {e}")

