#!/usr/bin/env python3
"""Скрипт для получения guid торговых точек YTimes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ytimes import YTimesAPIClient, YTimesAPIError  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Получить guid торговой точки YTimes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="shop_name",
        help="Название торговой точки. Если не передано — выводим все точки.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    try:
        client = YTimesAPIClient.from_env()
    except YTimesAPIError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        shops = client.list_shops()
    except YTimesAPIError as exc:
        print(f"Не удалось получить список торговых точек: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not shops:
        print("Торговые точки не найдены.")
        return

    if args.shop_name:
        guid = next((shop.guid for shop in shops if shop.name == args.shop_name), None)
        if guid:
            print(guid)
        else:
            print(f"Точка с названием '{args.shop_name}' не найдена.", file=sys.stderr)
            raise SystemExit(1)
    else:
        for shop in shops:
            print(f"{shop.guid} | {shop.name} | {shop.type}")


if __name__ == "__main__":
    main()

