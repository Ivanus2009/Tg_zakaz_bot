"""Модели базы данных."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """Модель пользователя."""

    telegram_id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    is_active: bool = True


@dataclass
class CartItem:
    """Элемент корзины."""

    item_guid: str  # GUID позиции из YTimes
    item_name: str
    type_guid: str  # GUID размера/типа
    type_name: str
    price: float
    quantity: int = 1
    supplements: Optional[list[dict]] = None  # Добавки/модификаторы


@dataclass
class Order:
    """Модель заказа."""

    order_id: Optional[int] = None
    user_telegram_id: int = 0
    items: list[CartItem] = None
    total_price: float = 0.0
    status: str = "pending"  # pending, confirmed, completed, cancelled
    ytimes_order_id: Optional[str] = None  # ID заказа в YTimes
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []

