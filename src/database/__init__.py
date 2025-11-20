"""Модуль работы с базой данных."""

from . import db
from .db import get_user, create_user, update_user_phone

__all__ = ["db", "get_user", "create_user", "update_user_phone"]

