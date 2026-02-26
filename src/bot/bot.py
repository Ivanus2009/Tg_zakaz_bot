"""Инициализация и запуск Telegram-бота."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

# #region agent log
def _debug_log_update(update: Update) -> None:
    try:
        root = Path(__file__).resolve().parents[2]
        log_path = (root / "data" / "debug.log") if (str(root) == "/app") else (root / ".cursor" / "debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        msg = getattr(update, "message", None)
        has_web_app_data = bool(msg and getattr(msg, "web_app_data", None))
        line = (
            json.dumps(
                {
                    "location": "bot.py",
                    "message": "incoming update",
                    "data": {
                        "update_id": update.update_id,
                        "has_message": msg is not None,
                        "has_web_app_data": has_web_app_data,
                    },
                    "hypothesisId": "H1",
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

    # #region agent log — логируем каждый апдейт, чтобы проверить приход web_app_data
    @dp.outer_middleware()
    async def log_updates_middleware(handler, event: Update, data: dict):
        _debug_log_update(event)
        return await handler(event, data)
    # #endregion

    dp.include_router(router)

    # Запуск polling
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

