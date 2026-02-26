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
from aiogram.types import MenuButtonDefault, Update

# #region agent log
def _debug_log_update(event) -> None:
    try:
        root = Path(__file__).resolve().parents[2]
        log_path = (root / "data" / "debug.log") if (str(root) == "/app") else (root / ".cursor" / "debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(event, Update):
            msg = getattr(event, "message", None)
            update_id = getattr(event, "update_id", None)
        else:
            msg = event
            update_id = getattr(event, "message_id", None)
        has_web_app_data = bool(msg and getattr(msg, "web_app_data", None))
        msg_hint = None
        if msg is not None:
            wad = getattr(msg, "web_app_data", None)
            txt = getattr(msg, "text", None)
            msg_hint = {
                "has_text": txt is not None,
                "text_preview": (txt[:80] if txt else None),
                "has_web_app_data_attr": wad is not None,
                "message_content_type": getattr(msg, "content_type", None),
            }
        line = (
            json.dumps(
                {
                    "location": "bot.py",
                    "message": "incoming update",
                    "data": {
                        "update_id": update_id,
                        "has_message": msg is not None,
                        "has_web_app_data": has_web_app_data,
                        "msg_hint": msg_hint,
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
    # Кнопка меню справа от поля ввода = «команды», не Web App (sendData работает только при открытии через KeyboardButton «Открыть меню»)
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception as e:
        print("Предупреждение: не удалось установить кнопку меню по умолчанию:", e)
    dp = Dispatcher()

    # #region agent log — логируем входящие апдейты (H1). Регистрируем middleware только если API есть (aiogram 3.13 может не иметь dp.update)
    try:
        if hasattr(dp, "update") and hasattr(getattr(dp, "update"), "outer_middleware"):
            @dp.update.outer_middleware()
            async def _log_updates_mw(handler, event, data):
                _debug_log_update(event)
                return await handler(event, data)
        else:
            log_path = (ROOT_DIR / "data" / "debug.log") if (str(ROOT_DIR) == "/app") else (ROOT_DIR / ".cursor" / "debug.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"message": "middleware_skipped", "reason": "no dp.update.outer_middleware"}, ensure_ascii=False) + "\n")
    except Exception as e:
        import traceback
        log_path = (ROOT_DIR / "data" / "debug.log") if (str(ROOT_DIR) == "/app") else (ROOT_DIR / ".cursor" / "debug.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"message": "middleware_reg_failed", "error": str(e), "tb": traceback.format_exc()}, ensure_ascii=False) + "\n")
    # #endregion

    dp.include_router(router)

    # #region agent log — запись при старте, чтобы убедиться, что лог-файл используется
    try:
        _start_log_path = (ROOT_DIR / "data" / "debug.log") if (str(ROOT_DIR) == "/app") else (ROOT_DIR / ".cursor" / "debug.log")
        _start_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_start_log_path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"location": "bot.py", "message": "bot_start_polling", "data": {}, "hypothesisId": "H1", "timestamp": int(time.time() * 1000)}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion

    # Запуск polling
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

