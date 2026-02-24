"""Инициализация и запуск Telegram-бота."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Добавляем src в путь для импортов
ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Загружаем переменные окружения
load_dotenv(ROOT_DIR / ".env")

from bot.handlers import router
from database import db


def _check_webapp_url() -> None:
    """Предупреждение, если WEBAPP_URL не задан или не подходит для Telegram Mini App."""
    url = os.getenv("WEBAPP_URL", "").strip()
    if not url:
        print("Предупреждение: WEBAPP_URL не задан. Кнопка «Открыть меню» может не работать в Telegram.")
        return
    if not url.startswith("https://"):
        print("Предупреждение: WEBAPP_URL должен начинаться с https:// (Telegram не открывает http). Сейчас:", url)
        return
    if "your-domain.com" in url:
        print("Предупреждение: WEBAPP_URL похож на заглушку (your-domain.com). Задайте реальный URL деплоя в .env")


async def main() -> None:
    """Запуск бота."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в переменных окружения")

    _check_webapp_url()

    # Инициализация базы данных
    await db.init_db()

    # Создание бота и диспетчера
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.include_router(router)

    # Запуск polling
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

