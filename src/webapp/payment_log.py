"""Логирование всей логики оплаты: create-inapp, return, order-from-payment, YooKassa."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).resolve().parents[2] / "data"
_LOG_FILE = _LOG_DIR / "payment.log"


def _safe_data(data: dict[str, Any]) -> dict[str, Any]:
    """Убираем чувствительные поля из логов."""
    out = dict(data)
    for key in ("password", "password_hash", "token", "secret", "authorization"):
        if key in out:
            out[key] = "***"
    return out


def log(event: str, **kwargs: Any) -> None:
    """Пишет одну строку JSON в payment.log и в stdout (без паролей)."""
    payload = _safe_data({
        "event": event,
        "ts": round(time.time() * 1000),
        **kwargs,
    })
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(f"[payment] {line.strip()}")
