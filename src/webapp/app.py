"""FastAPI приложение для Telegram Mini App."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import base64
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
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
    set_pending_yookassa_id,
    update_order_status,
)
from ytimes import YTimesAPIClient, YTimesAPIError

BOT_SECRET_HEADER = "X-Bot-Secret"

# Хранилище меню и добавок — заполняется только фоновой задачей раз в 20 мин (лимит YTimes 10/час)
_MENU_REFRESH_INTERVAL = 20 * 60  # секунд
_stored_menu: dict | None = None
_stored_supplements: list | None = None

app = FastAPI(title="Telegram Mini App - Заказы")

# Статические файлы (legacy)
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Клиент YTimes API
ytimes_client = None


async def _refresh_menu_and_supplements() -> None:
    """Один проход: загрузить меню и добавки из YTimes, сохранить в хранилище."""
    global _stored_menu, _stored_supplements
    if not ytimes_client:
        return
    try:
        loop = asyncio.get_event_loop()
        menu = await loop.run_in_executor(None, ytimes_client.get_menu_items)
        target = None
        for g in menu:
            if g.get("name") == "Меню ( онлайн заказы )":
                target = g
                break
        if target:
            _stored_menu = target
        supps = await loop.run_in_executor(None, ytimes_client.get_supplements)
        _stored_supplements = supps
        print("Меню и добавки обновлены из YTimes.")
    except Exception as e:
        print(f"Фоновое обновление меню: {e}")


async def _menu_refresh_loop() -> None:
    """Фоновая задача: раз в 20 минут обновлять меню и добавки из YTimes."""
    while True:
        await _refresh_menu_and_supplements()
        await asyncio.sleep(_MENU_REFRESH_INTERVAL)


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
    if ytimes_client:
        asyncio.create_task(_menu_refresh_loop())


@app.get("/health")
async def health():
    """Health-check для PaaS (Railway, Render, Fly.io)."""
    return JSONResponse({"status": "ok"})


@app.get("/api/menu")
async def get_menu():
    """Меню отдаётся из хранилища (обновляется фоновой задачей раз в 20 мин)."""
    if _stored_menu is not None:
        return JSONResponse({"success": True, "data": _stored_menu})
    return JSONResponse(
        {"error": "Меню загружается, попробуйте через минуту."},
        status_code=503,
    )


@app.get("/api/supplements")
async def get_supplements():
    """Добавки отдаются из хранилища (обновляется фоновой задачей раз в 20 мин)."""
    if _stored_supplements is not None:
        return JSONResponse({"success": True, "data": _stored_supplements})
    return JSONResponse(
        {"error": "Данные загружаются, попробуйте через минуту."},
        status_code=503,
    )


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


def _yookassa_auth() -> tuple[str, str] | None:
    """Shop ID и secret_key для ЮKassa. Если не заданы — оплата в приложении недоступна."""
    shop_id = os.getenv("YOOKASSA_SHOP_ID", "").strip()
    secret = os.getenv("YOOKASSA_SECRET_KEY", "").strip()
    if not shop_id or not secret:
        return None
    return (shop_id, secret)


async def _yookassa_create_payment(
    amount_rub: float,
    description: str,
    return_url: str,
    metadata: dict,
) -> dict | None:
    """Создать платёж в ЮKassa. Возвращает ответ API или None при ошибке."""
    creds = _yookassa_auth()
    if not creds:
        return None
    shop_id, secret = creds
    auth = base64.b64encode(f"{shop_id}:{secret}".encode()).decode()
    value = f"{amount_rub:.2f}"
    payload = {
        "amount": {"value": value, "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description[:255],
        "capture": True,
        "metadata": metadata,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            "https://api.yookassa.ru/v3/payments",
            headers={
                "Authorization": f"Basic {auth}",
                "Idempotence-Key": str(uuid.uuid4()),
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if r.status_code != 200:
        return None
    return r.json()


async def _yookassa_get_payment(payment_id: str) -> dict | None:
    """Получить платёж из ЮKassa по id."""
    creds = _yookassa_auth()
    if not creds:
        return None
    shop_id, secret = creds
    auth = base64.b64encode(f"{shop_id}:{secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"https://api.yookassa.ru/v3/payments/{payment_id}",
            headers={"Authorization": f"Basic {auth}"},
        )
    if r.status_code != 200:
        return None
    return r.json()


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
        # #region agent log — фиксируем, что фронт дошёл до успешной подготовки платежа (перед вызовом sendData)
        try:
            from pathlib import Path
            _root = Path(__file__).resolve().parents[2]
            _log_path = (_root / "data" / "debug.log") if str(_root) == "/app" else (_root / ".cursor" / "debug.log")
            _log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(_log_path, "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"location": "webapp app.py", "message": "payment_prepare_success", "data": {"telegram_id": telegram_id, "total": total}, "hypothesisId": "H2", "timestamp": int(__import__("time").time() * 1000)}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # #endregion
        return JSONResponse({"success": True, "payment_token": payment_token})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/payment/create-inapp")
async def api_payment_create_inapp(request: Request):
    """Создать платёж ЮKassa для оплаты внутри Mini App. Возвращает confirmation_url для перехода."""
    try:
        data = await request.json()
        items = data.get("items", [])
        if not items:
            return JSONResponse({"success": False, "error": "Пустая корзина"}, status_code=400)
        total = sum(item.get("priceWithDiscount", 0) * item.get("quantity", 1) for item in items)
        if total <= 0:
            return JSONResponse({"success": False, "error": "Некорректная сумма"}, status_code=400)
        if not _yookassa_auth():
            return JSONResponse(
                {"success": False, "error": "Оплата в приложении не настроена (ЮKassa). Выберите «Оплата при получении» или оплату через бота."},
                status_code=503,
            )
        telegram_id = int(data.get("telegramUserId") or 0)
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
        webapp_url = (os.getenv("WEBAPP_URL") or "").rstrip("/")
        if not webapp_url:
            return JSONResponse({"success": False, "error": "WEBAPP_URL не задан"}, status_code=500)
        return_url = f"{webapp_url}/api/payment/return?payment_token={payment_token}"
        yookassa_resp = await _yookassa_create_payment(
            amount_rub=total,
            description=f"Заказ на {total:.2f} ₽",
            return_url=return_url,
            metadata={"payment_token": payment_token},
        )
        if not yookassa_resp or yookassa_resp.get("status") not in ("pending", "waiting_for_capture"):
            return JSONResponse({"success": False, "error": "Не удалось создать платёж. Попробуйте позже."}, status_code=502)
        yookassa_id = yookassa_resp.get("id")
        confirmation = yookassa_resp.get("confirmation") or {}
        confirmation_url = confirmation.get("confirmation_url")
        if not yookassa_id or not confirmation_url:
            return JSONResponse({"success": False, "error": "Ошибка ответа платёжной системы."}, status_code=502)
        await set_pending_yookassa_id(payment_token, yookassa_id)
        return JSONResponse({
            "success": True,
            "payment_token": payment_token,
            "confirmation_url": confirmation_url,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/payment/return")
async def api_payment_return(payment_token: str):
    """Возврат пользователя после оплаты ЮKassa. Проверяем статус, создаём заказ, редирект в приложение."""
    webapp_url = (os.getenv("WEBAPP_URL") or "").rstrip("/")
    fail_url = f"{webapp_url}?payment_failed=1" if webapp_url else "/"
    if not payment_token:
        return RedirectResponse(url=fail_url)
    pending = await get_pending_payment(payment_token)
    if not pending:
        return RedirectResponse(url=fail_url)
    yookassa_id = (pending.get("yookassa_payment_id") or "").strip()
    if not yookassa_id:
        return RedirectResponse(url=fail_url)
    payment = await _yookassa_get_payment(yookassa_id)
    if not payment or payment.get("status") != "succeeded":
        return RedirectResponse(url=fail_url)
    items = json.loads(pending["items_json"])
    total = float(pending["total"])
    client = json.loads(pending["client_json"] or "{}")
    comment = (pending["comment"] or "").strip()
    telegram_id = int(pending.get("telegram_id") or 0)
    if not ytimes_client:
        return RedirectResponse(url=f"{webapp_url}?payment_error=no_ytimes" if webapp_url else fail_url)
    order_guid = str(uuid.uuid4())
    shop_guid = ytimes_client.default_shop_guid
    ytimes_items = _build_ytimes_items(items)
    loop = asyncio.get_event_loop()
    try:
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
    except Exception:
        return RedirectResponse(url=f"{webapp_url}?payment_error=order" if webapp_url else fail_url)
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
    success_url = f"{webapp_url}?payment_success=1&order_id={order_id_return}" if webapp_url else "/"
    return RedirectResponse(url=success_url)


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
        telegram_id = int(data.get("telegram_id") or pending["telegram_id"] or 0)
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

