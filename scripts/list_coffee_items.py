#!/usr/bin/env python3
"""Вывести позиции из указанной группы меню торговой точки YTimes."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ytimes import YTimesAPIClient, YTimesAPIError  # noqa: E402


def flatten_groups(groups: List[dict]) -> Iterable[tuple[str, dict]]:
    """Итерируемся по всем группам меню, возвращаем (путь_группы, группа)."""

    def _walk(current_groups: List[dict], prefix: List[str]):
        for group in current_groups:
            group_name = group.get("name") or "Без названия"
            new_prefix = [*prefix, group_name]
            yield (" > ".join(new_prefix), group)
            nested = group.get("categoryList") or group.get("groupList") or []
            yield from _walk(nested, new_prefix)

    yield from _walk(groups, [])


def find_group_by_name(menu: List[dict], target_name: str) -> Optional[dict]:
    """Найти группу меню по названию (с учётом вложенности)."""
    target_lower = target_name.lower().strip()
    for group_path, group in flatten_groups(menu):
        group_name = group.get("name", "").lower().strip()
        if group_name == target_lower or target_lower in group_name or group_name in target_lower:
            return group
    return None


def print_group_items(group: dict, group_path: str = "") -> int:
    """Вывести все позиции из группы (блюда и товары)."""
    count = 0
    
    # Блюда (itemList)
    for item in group.get("itemList") or []:
        count += 1
        item_name = item.get("name") or "Без названия"
        print(f"\n[{count}] {item_name} ({group_path})")
        if item.get("description"):
            print(f"    Описание: {item['description']}")
        if item.get("recipe"):
            print(f"    Рецепт: {item['recipe']}")
        for type_info in item.get("typeList") or []:
            name = type_info.get("name") or "Размер"
            price = type_info.get("price")
            togo = " (с собой)" if type_info.get("isTogo") else ""
            print(f"    - {name}: {price} ₽{togo}")
    
    # Товары (goodsList)
    for good in group.get("goodsList") or []:
        count += 1
        good_name = good.get("name") or "Без названия"
        price = good.get("price")
        print(f"\n[{count}] {good_name} ({group_path}) [Товар]")
        if good.get("description"):
            print(f"    Описание: {good['description']}")
        if good.get("recipe"):
            print(f"    Рецепт: {good['recipe']}")
        print(f"    - Цена: {price} ₽")
    
    # Рекурсивно обрабатываем вложенные группы
    nested = group.get("categoryList") or group.get("groupList") or []
    for nested_group in nested:
        nested_name = nested_group.get("name") or "Без названия"
        nested_path = f"{group_path} > {nested_name}" if group_path else nested_name
        count += print_group_items(nested_group, nested_path)
    
    return count


def print_menu_items(menu: List[dict], group_name: str) -> None:
    """Найти группу и вывести все её позиции."""
    target_group = find_group_by_name(menu, group_name)
    if not target_group:
        print(f"Группа '{group_name}' не найдена в меню.", file=sys.stderr)
        print("\nДоступные группы:", file=sys.stderr)
        for path, _ in flatten_groups(menu):
            print(f"  - {path}", file=sys.stderr)
        raise SystemExit(1)
    
    group_display_name = target_group.get("name") or group_name
    print(f"Позиции из группы: {group_display_name}\n")
    
    count = print_group_items(target_group, group_display_name)
    if count == 0:
        print(f"В группе '{group_display_name}' нет позиций.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Вывести позиции из указанной группы меню YTimes"
    )
    parser.add_argument(
        "-g",
        "--group",
        default="Меню ( онлайн заказы )",
        help='Название группы меню (по умолчанию: "Меню ( онлайн заказы )")',
    )
    args = parser.parse_args()

    load_dotenv(os.path.join(ROOT_DIR, ".env"))
    try:
        client = YTimesAPIClient.from_env()
        menu = client.get_menu_items()
    except YTimesAPIError as exc:
        print(f"Ошибка YTimes API: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(f"Непредвиденная ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print_menu_items(menu, args.group)


if __name__ == "__main__":
    main()

