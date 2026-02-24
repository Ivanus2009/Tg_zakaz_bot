#!/usr/bin/env python3
"""Проверить, что возвращает API YTimes, и сохранить в файл для составления меню."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
OUTPUT_FILE = ROOT_DIR / "api_menu_data.json"

# Только эта группа меню идёт в бота (договорённость)
ONLINE_ORDERS_MENU_NAME = "Меню ( онлайн заказы )"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ytimes import YTimesAPIClient, YTimesAPIError  # noqa: E402


def main() -> None:
    load_dotenv(os.path.join(ROOT_DIR, ".env"))

    try:
        client = YTimesAPIClient.from_env()
    except YTimesAPIError as exc:
        print(f"❌ Ошибка YTimes API: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Непредвиденная ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    result = {
        "shops": [],
        "menu_groups": [],
        "menu_items": [],
        "supplements": [],
        "errors": [],
    }

    # 1. Список торговых точек
    try:
        shops = client.list_shops()
        result["shops"] = [
            {"guid": s.guid, "name": s.name, "type": s.type, "city_name": s.city_name}
            for s in shops
        ]
        print(f"✅ Торговых точек: {len(shops)}")
    except Exception as e:
        result["errors"].append(f"shops: {e}")
        print(f"❌ Торговые точки: {e}")

    # 2. Группы меню (только "Меню ( онлайн заказы )")
    try:
        menu_groups = client.get_menu_groups()
        filtered_groups = [g for g in menu_groups if g.get("name") == ONLINE_ORDERS_MENU_NAME]
        result["menu_groups"] = filtered_groups
        if not filtered_groups:
            print(f"⚠️ Группа {ONLINE_ORDERS_MENU_NAME!r} не найдена среди {len(menu_groups)} групп")
        else:
            print(f"✅ Групп меню: {len(menu_groups)} → оставлена одна: {ONLINE_ORDERS_MENU_NAME!r}")
    except Exception as e:
        result["errors"].append(f"menu_groups: {e}")
        print(f"❌ Группы меню: {e}")

    # 3. Позиции меню (только "Меню ( онлайн заказы )")
    try:
        menu_items = client.get_menu_items()
        filtered_items = [m for m in menu_items if m.get("name") == ONLINE_ORDERS_MENU_NAME]
        result["menu_items"] = filtered_items
        if filtered_items:
            m = filtered_items[0]
            n_positions = len(m.get("itemList", [])) + len(m.get("goodsList", []))
            print(f"✅ Позиций меню: оставлено одно меню {ONLINE_ORDERS_MENU_NAME!r} ({n_positions} позиций)")
        else:
            print(f"⚠️ Меню {ONLINE_ORDERS_MENU_NAME!r} не найдено среди menu_items")
    except Exception as e:
        result["errors"].append(f"menu_items: {e}")
        print(f"❌ Позиции меню: {e}")

    # 4. Добавки/модификаторы
    try:
        supplements = client.get_supplements()
        result["supplements"] = supplements
        print(f"✅ Добавок: {len(supplements)}")
    except Exception as e:
        result["errors"].append(f"supplements: {e}")
        print(f"❌ Добавки: {e}")

    # Сохраняем в файл
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n📄 Результат сохранён в: {OUTPUT_FILE}")
    print("   Открой этот файл — в нём всё, из чего можно составлять меню (menu_items, menu_groups, supplements).")


if __name__ == "__main__":
    main()
