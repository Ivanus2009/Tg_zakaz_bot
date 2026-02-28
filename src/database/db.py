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

        # Ожидающие онлайн-оплаты (корзина до отправки инвойса / ЮKassa)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_payments (
                payment_token TEXT PRIMARY KEY,
                telegram_id INTEGER NOT NULL,
                items_json TEXT NOT NULL,
                total REAL NOT NULL,
                client_json TEXT,
                comment TEXT,
                created_at TEXT NOT NULL,
                yookassa_payment_id TEXT
            )
        """)
        try:
            await db.execute("ALTER TABLE pending_payments ADD COLUMN yookassa_payment_id TEXT")
        except Exception:
            pass
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


async def create_order(
    user_telegram_id: int,
    ytimes_order_guid: str,
    total_price: float,
    status: str = "CREATED",
    items_json: str = "[]",
) -> None:
    """Сохранить заказ после создания в YTimes."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO orders
               (user_telegram_id, items_json, total_price, status, ytimes_order_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_telegram_id, items_json, total_price, status, ytimes_order_guid, now),
        )
        await db.commit()


async def get_order_by_ytimes_guid(ytimes_guid: str) -> Optional[dict]:
    """Найти заказ по YTimes guid (для вебхука). Возвращает dict с user_telegram_id, status и др."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT order_id, user_telegram_id, total_price, status, ytimes_order_id, created_at FROM orders WHERE ytimes_order_id = ?",
            (ytimes_guid,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)


async def update_order_status(ytimes_guid: str, status: str) -> None:
    """Обновить статус заказа (ACCEPTED/CANCELLED) после вебхука."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE ytimes_order_id = ?",
            (status, now, ytimes_guid),
        )
        await db.commit()


async def create_pending_payment(
    payment_token: str,
    telegram_id: int,
    items_json: str,
    total: float,
    client_json: str = "{}",
    comment: str = "",
) -> None:
    """Сохранить ожидающий платёж (корзина для Telegram Invoice)."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO pending_payments
               (payment_token, telegram_id, items_json, total, client_json, comment, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (payment_token, telegram_id, items_json, total, client_json, comment or "", now),
        )
        await conn.commit()


async def get_pending_payment(payment_token: str) -> Optional[dict]:
    """Получить ожидающий платёж по токену. Для вызова из бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT payment_token, telegram_id, items_json, total, client_json, comment, yookassa_payment_id FROM pending_payments WHERE payment_token = ?",
            (payment_token,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)


async def set_pending_yookassa_id(payment_token: str, yookassa_payment_id: str) -> None:
    """Сохранить id платежа ЮKassa для ожидающего платежа."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pending_payments SET yookassa_payment_id = ? WHERE payment_token = ?",
            (yookassa_payment_id, payment_token),
        )
        await db.commit()


async def delete_pending_payment(payment_token: str) -> None:
    """Удалить ожидающий платёж после создания заказа."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pending_payments WHERE payment_token = ?", (payment_token,))
        await db.commit()

