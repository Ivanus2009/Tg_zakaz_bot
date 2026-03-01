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
                yookassa_payment_id TEXT,
                site_user_id INTEGER,
                link_card_only INTEGER NOT NULL DEFAULT 0
            )
        """)
        try:
            await db.execute("ALTER TABLE pending_payments ADD COLUMN yookassa_payment_id TEXT")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE pending_payments ADD COLUMN site_user_id INTEGER")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE pending_payments ADD COLUMN link_card_only INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        # Пользователи сайта (телефон + пароль)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS site_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                created_at TEXT NOT NULL,
                saved_payment_method_id TEXT
            )
        """)
        try:
            await db.execute("ALTER TABLE site_users ADD COLUMN saved_payment_method_id TEXT")
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
    site_user_id: int | None = None,
    link_card_only: bool = False,
) -> None:
    """Сохранить ожидающий платёж (корзина для ЮKassa / Telegram Invoice). link_card_only=True — только привязка карты, заказ не создаём."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO pending_payments
               (payment_token, telegram_id, items_json, total, client_json, comment, created_at, site_user_id, link_card_only)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payment_token, telegram_id, items_json, total, client_json, comment or "", now, site_user_id, 1 if link_card_only else 0),
        )
        await conn.commit()


async def get_pending_payment(payment_token: str) -> Optional[dict]:
    """Получить ожидающий платёж по токену. Для вызова из бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT payment_token, telegram_id, items_json, total, client_json, comment, yookassa_payment_id, site_user_id, link_card_only FROM pending_payments WHERE payment_token = ?",
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


async def create_site_user(phone: str, password_hash: str, name: str | None = None) -> dict | None:
    """Создать пользователя сайта. Возвращает dict с id, phone, name, created_at или None если телефон занят."""
    now = datetime.utcnow().isoformat()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """INSERT INTO site_users (phone, password_hash, name, created_at)
                   VALUES (?, ?, ?, ?)""",
                (phone.strip(), password_hash, (name or "").strip() or None, now),
            )
            await db.commit()
            return {"id": cursor.lastrowid, "phone": phone.strip(), "name": (name or "").strip() or None, "created_at": now}
    except aiosqlite.IntegrityError:
        return None


async def get_site_user_by_phone(phone: str) -> dict | None:
    """Получить пользователя сайта по телефону (включая password_hash для проверки)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, phone, password_hash, name, created_at FROM site_users WHERE phone = ?",
            (phone.strip(),),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_site_user_by_id(user_id: int) -> dict | None:
    """Получить пользователя сайта по id (без password_hash для ответов API)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, phone, name, created_at, saved_payment_method_id FROM site_users WHERE id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_site_user_saved_payment_method(site_user_id: int, payment_method_id: str) -> None:
    """Привязать сохранённый способ оплаты ЮKassa к аккаунту пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE site_users SET saved_payment_method_id = ? WHERE id = ?",
            (payment_method_id.strip(), site_user_id),
        )
        await db.commit()

