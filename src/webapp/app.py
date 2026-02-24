"""FastAPI приложение для Telegram Mini App."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Добавляем src в путь
ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv(ROOT_DIR / ".env")

from database import (
    create_order as db_create_order,
    create_pending_payment,
    delete_pending_payment,
    get_order_by_ytimes_guid,
    get_pending_payment,
    init_db,
    update_order_status,
)
from ytimes import YTimesAPIClient, YTimesAPIError

BOT_SECRET_HEADER = "X-Bot-Secret"

app = FastAPI(title="Telegram Mini App - Заказы")

# Статические файлы (legacy)
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Клиент YTimes API
ytimes_client = None


@app.on_event("startup")
async def startup():
    """Инициализация при запуске."""
    global ytimes_client
    try:
        await init_db()
    except Exception as e:
        print(f"Ошибка инициализации БД: {e}")
    try:
        ytimes_client = YTimesAPIClient.from_env()
    except Exception as e:
        print(f"Ошибка инициализации YTimes клиента: {e}")


@app.get("/health")
async def health():
    """Health-check для PaaS (Railway, Render, Fly.io)."""
    return JSONResponse({"status": "ok"})


@app.get("/api/menu")
async def get_menu():
    """Получить меню для торговой точки."""
    if not ytimes_client:
        return JSONResponse({"error": "YTimes клиент не инициализирован"}, status_code=500)

    try:
        # Вызываем синхронный метод в executor, чтобы не блокировать event loop
        import asyncio
        loop = asyncio.get_event_loop()
        menu = await loop.run_in_executor(None, ytimes_client.get_menu_items)
        
        # Фильтруем только группу "Меню ( онлайн заказы )"
        target_group = None
        for group in menu:
            if group.get("name") == "Меню ( онлайн заказы )":
                target_group = group
                break

        if not target_group:
            return JSONResponse({"error": "Группа меню не найдена"}, status_code=404)

        return JSONResponse({
            "success": True,
            "data": target_group
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/supplements")
async def get_supplements():
    """Получить список добавок/модификаторов."""
    if not ytimes_client:
        return JSONResponse({"error": "YTimes клиент не инициализирован"}, status_code=500)

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        supplements = await loop.run_in_executor(None, ytimes_client.get_supplements)
        return JSONResponse({"success": True, "data": supplements})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _build_ytimes_items(items: list) -> list:
    """Собрать itemList для YTimes: menuTypeGuid только если есть."""
    out = []
    for item in items:
        row = {
            "menuItemGuid": item.get("menuItemGuid"),
            "supplementList": item.get("supplementList") or {},
            "priceWithDiscount": float(item.get("priceWithDiscount", 0)),
            "quantity": int(item.get("quantity", 1)),
        }
        if item.get("menuTypeGuid"):
            row["menuTypeGuid"] = item["menuTypeGuid"]
        out.append(row)
    return out


@app.post("/api/order")
async def api_create_order(request: Request):
    """Создать заказ и отправить на кассу YTimes."""
    try:
        data = await request.json()
        items = data.get("items", [])
        if not items:
            return JSONResponse({"success": False, "error": "Пустой заказ"}, status_code=400)

        total = sum(item.get("priceWithDiscount", 0) * item.get("quantity", 1) for item in items)
        order_guid = str(uuid.uuid4())
        client = data.get("client") or {}
        comment = (data.get("comment") or "").strip()
        paid_value_raw = data.get("paidValue")
        paid_value = None if paid_value_raw is None or paid_value_raw == 0 else float(paid_value_raw)
        telegram_id = int(data.get("telegramUserId") or 0)
        order_type = data.get("type") or "TOGO"

        if not ytimes_client:
            return JSONResponse({"success": False, "error": "YTimes не настроен"}, status_code=500)

        shop_guid = ytimes_client.default_shop_guid
        ytimes_items = _build_ytimes_items(items)

        loop = asyncio.get_event_loop()
        created = await loop.run_in_executor(
            None,
            lambda: ytimes_client.create_order(
                order_guid=order_guid,
                shop_guid=shop_guid,
                order_type=order_type,
                items=ytimes_items,
                client=client,
                comment=comment or None,
                paid_value=paid_value,
            ),
        )

        order_id_return = created.get("guid") or order_guid
        status = created.get("status") or "CREATED"

        await db_create_order(
            user_telegram_id=telegram_id,
            ytimes_order_guid=order_id_return,
            total_price=total,
            status=status,
            items_json=json.dumps(items),
        )

        return JSONResponse({
            "success": True,
            "order_id": order_id_return,
            "status": status,
            "total": total,
            "message": "Заказ успешно сформирован и отправлен на кассу",
        })
    except YTimesAPIError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=502)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


async def _send_telegram_message(chat_id: int, text: str) -> None:
    """Отправить сообщение пользователю через Telegram Bot API."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json={"chat_id": chat_id, "text": text}, timeout=5.0)
        except Exception:
            pass


def _require_bot_secret(x_bot_secret: str | None = Header(None, alias=BOT_SECRET_HEADER)) -> None:
    """Проверка секрета для эндпоинтов, вызываемых только ботом."""
    secret = os.getenv("BOT_INTERNAL_SECRET")
    if not secret:
        raise ValueError("BOT_INTERNAL_SECRET не задан")
    if not x_bot_secret or x_bot_secret != secret:
        raise ValueError("Неверный или отсутствующий X-Bot-Secret")


@app.post("/api/payment/prepare")
async def api_payment_prepare(request: Request):
    """Подготовить платёж: сохранить корзину, вернуть payment_token для инвойса."""
    try:
        data = await request.json()
        items = data.get("items", [])
        if not items:
            return JSONResponse({"success": False, "error": "Пустая корзина"}, status_code=400)
        total = sum(item.get("priceWithDiscount", 0) * item.get("quantity", 1) for item in items)
        telegram_id = int(data.get("telegramUserId") or 0)
        if not telegram_id:
            return JSONResponse({"success": False, "error": "Требуется telegramUserId"}, status_code=400)
        client = data.get("client") or {}
        comment = (data.get("comment") or "").strip()
        payment_token = uuid.uuid4().hex
        await create_pending_payment(
            payment_token=payment_token,
            telegram_id=telegram_id,
            items_json=json.dumps(items),
            total=total,
            client_json=json.dumps(client),
            comment=comment,
        )
        return JSONResponse({"success": True, "payment_token": payment_token})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/payment/pending/{payment_token}")
async def api_payment_pending(
    payment_token: str,
    x_bot_secret: str | None = Header(None, alias=BOT_SECRET_HEADER),
):
    """Получить данные ожидающего платежа (вызывает только бот)."""
    try:
        _require_bot_secret(x_bot_secret)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=403)
    pending = await get_pending_payment(payment_token)
    if not pending:
        return JSONResponse({"success": False, "error": "Платёж не найден или уже использован"}, status_code=404)
    return JSONResponse({
        "success": True,
        "items": json.loads(pending["items_json"]),
        "total": pending["total"],
        "client": json.loads(pending["client_json"] or "{}"),
        "comment": pending["comment"] or "",
        "telegram_id": pending["telegram_id"],
    })


@app.post("/api/order-from-payment")
async def api_order_from_payment(
    request: Request,
    x_bot_secret: str | None = Header(None, alias=BOT_SECRET_HEADER),
):
    """Создать заказ после успешной оплаты (вызывает только бот). paidValue = total."""
    try:
        _require_bot_secret(x_bot_secret)
    except ValueError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=403)
    try:
        data = await request.json()
        payment_token = (data.get("payment_token") or "").strip()
        if not payment_token:
            return JSONResponse({"success": False, "error": "Требуется payment_token"}, status_code=400)
        pending = await get_pending_payment(payment_token)
        if not pending:
            return JSONResponse({"success": False, "error": "Платёж не найден или уже использован"}, status_code=404)
        items = json.loads(pending["items_json"])
        total = float(pending["total"])
        client = json.loads(pending["client_json"] or "{}")
        comment = (pending["comment"] or "").strip()
        telegram_id = int(pending["telegram_id"])
        if not ytimes_client:
            return JSONResponse({"success": False, "error": "YTimes не настроен"}, status_code=500)
        order_guid = str(uuid.uuid4())
        shop_guid = ytimes_client.default_shop_guid
        ytimes_items = _build_ytimes_items(items)
        loop = asyncio.get_event_loop()
        created = await loop.run_in_executor(
            None,
            lambda: ytimes_client.create_order(
                order_guid=order_guid,
                shop_guid=shop_guid,
                order_type="TOGO",
                items=ytimes_items,
                client=client,
                comment=comment or None,
                paid_value=total,
            ),
        )
        order_id_return = created.get("guid") or order_guid
        status = created.get("status") or "CREATED"
        await db_create_order(
            user_telegram_id=telegram_id,
            ytimes_order_guid=order_id_return,
            total_price=total,
            status=status,
            items_json=json.dumps(items),
        )
        await delete_pending_payment(payment_token)
        return JSONResponse({
            "success": True,
            "order_id": order_id_return,
            "status": status,
            "total": total,
        })
    except YTimesAPIError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=502)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/webhook/order-status", response_class=PlainTextResponse)
async def webhook_order_status(request: Request):
    """Приём статуса заказа от YTimes (принят/отклонён кассиром). Ответ: 200 OK."""
    try:
        body = await request.json()
        guid = body.get("guid")
        status = body.get("status")
        if not guid or not status:
            return PlainTextResponse("OK", status_code=200)

        order = await get_order_by_ytimes_guid(guid)
        await update_order_status(guid, status)

        if order:
            telegram_id = order.get("user_telegram_id") or 0
            if telegram_id and status == "ACCEPTED":
                await _send_telegram_message(telegram_id, "✅ Ваш заказ принят. Ожидайте приготовления.")
            elif telegram_id and status == "CANCELLED":
                msg = body.get("statusMessage") or "Причина не указана"
                await _send_telegram_message(telegram_id, f"❌ Заказ отклонён: {msg}")
    except Exception:
        pass
    return PlainTextResponse("OK", status_code=200)


# SPA (React): раздаём frontend/dist после API, чтобы /api имел приоритет
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="spa")
else:
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """Главная страница (fallback: старый шаблон, если React не собран)."""
        return templates.TemplateResponse("index.html", {"request": request})

