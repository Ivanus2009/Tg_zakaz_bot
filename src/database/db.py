"""Работа с базой данных SQLite."""

from __future__ import annotations

import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import User, Order, CartItem


DB_PATH = Path(__file__).resolve().parents[3] / "data" / "bot.db"


async def init_db() -> None:
    """Инициализировать базу данных."""
    DB_PATH.parent.mkdir(exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT,
                username TEXT,
                phone TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)

        # Таблица заказов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_telegram_id INTEGER NOT NULL,
                items_json TEXT NOT NULL,
                total_price REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                ytimes_order_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (user_telegram_id) REFERENCES users(telegram_id)
            )
        """)

        await db.commit()


async def get_user(telegram_id: int) -> Optional[User]:
    """Получить пользователя по Telegram ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return User(
                telegram_id=row["telegram_id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                username=row["username"],
                phone=row["phone"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                is_active=bool(row["is_active"]),
            )


async def create_user(user: User) -> User:
    """Создать нового пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.utcnow().isoformat()
        await db.execute(
            """INSERT OR REPLACE INTO users 
               (telegram_id, first_name, last_name, username, phone, created_at, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user.telegram_id,
                user.first_name,
                user.last_name,
                user.username,
                user.phone,
                now,
                1 if user.is_active else 0,
            ),
        )
        await db.commit()
        user.created_at = datetime.fromisoformat(now)
        return user


async def update_user_phone(telegram_id: int, phone: str) -> None:
    """Обновить телефон пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET phone = ? WHERE telegram_id = ?",
            (phone, telegram_id),
        )
        await db.commit()

