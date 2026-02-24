#!/usr/bin/env python3
"""
Проверки приложения «от и до»: health, меню, оплата (опционально).
Запускать при поднятом приложении (локально или на сервере).
Использование:
  python scripts/run_app_tests.py                    # тест http://localhost:8000
  BASE_URL=https://palm-marten.ru python scripts/run_app_tests.py
"""

from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 15.0


def ok(name: str, status: int, detail: str = ""):
    print(f"  ✅ {name}: HTTP {status}" + (f" — {detail}" if detail else ""))


def fail(name: str, msg: str):
    print(f"  ❌ {name}: {msg}")
    return False


def test_health():
    """Проверка /health."""
    print("\n1. Health-check")
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        if r.status_code == 200 and r.json().get("status") == "ok":
            ok("GET /health", r.status_code)
            return True
        return fail("GET /health", f"status={r.status_code} body={r.text[:200]}")
    except Exception as e:
        return fail("GET /health", str(e))


def test_menu():
    """Проверка /api/menu (без авторизации)."""
    print("\n2. API меню")
    try:
        r = httpx.get(f"{BASE_URL}/api/menu", timeout=TIMEOUT)
        if r.status_code != 200:
            return fail("GET /api/menu", f"status={r.status_code} body={r.text[:200]}")
        data = r.json()
        if "error" in data:
            return fail("GET /api/menu", data["error"])
        groups = data.get("menu_groups") or []
        items = data.get("menu_items") or []
        ok("GET /api/menu", r.status_code, f"групп: {len(groups)}, меню: {len(items)}")
        return True
    except Exception as e:
        return fail("GET /api/menu", str(e))


def test_supplements():
    """Проверка /api/supplements."""
    print("\n3. API добавки")
    try:
        r = httpx.get(f"{BASE_URL}/api/supplements", timeout=TIMEOUT)
        if r.status_code != 200:
            return fail("GET /api/supplements", f"status={r.status_code}")
        data = r.json()
        if "error" in data:
            return fail("GET /api/supplements", data["error"])
        count = len(data) if isinstance(data, list) else 0
        ok("GET /api/supplements", r.status_code, f"записей: {count}")
        return True
    except Exception as e:
        return fail("GET /api/supplements", str(e))


def test_root():
    """Проверка главной (SPA или index)."""
    print("\n4. Главная страница")
    try:
        r = httpx.get(f"{BASE_URL}/", timeout=TIMEOUT, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 100:
            ok("GET /", r.status_code, "страница отдаётся")
            return True
        return fail("GET /", f"status={r.status_code} или пустой ответ")
    except Exception as e:
        return fail("GET /", str(e))


def main():
    print(f"BASE_URL = {BASE_URL}")
    results = [test_health(), test_menu(), test_supplements(), test_root()]
    all_ok = all(results)
    print("\n" + ("✅ Все проверки пройдены." if all_ok else "❌ Часть проверок не пройдена."))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
