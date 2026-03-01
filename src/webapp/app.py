"""FastAPI приложение для Telegram Mini App."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import base64
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.hash import bcrypt

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
    create_site_user,
    delete_pending_payment,
    get_order_by_ytimes_guid,
    get_pending_payment,
    get_site_user_by_id,
    get_site_user_by_phone,
    init_db,
    set_pending_yookassa_id,
    update_order_status,
    update_site_user_saved_payment_method,
)
from ytimes import YTimesAPIClient, YTimesAPIError

from .payment_log import log as payment_log

BOT_SECRET_HEADER = "X-Bot-Secret"
AUTH_JWT_SECRET = os.getenv("AUTH_JWT_SECRET", os.getenv("BOT_INTERNAL_SECRET", "change-me")).strip()
AUTH_JWT_ALGORITHM = "HS256"
AUTH_JWT_EXP_SECONDS = 30 * 24 * 3600  # 30 дней

# Ограничение запросов к auth (защита от брутфорса): макс. запросов с одного IP в минуту
_AUTH_RATE_LIMIT: dict[str, list[float]] = {}
_AUTH_RATE_LIMIT_MAX = 10
_AUTH_RATE_LIMIT_WINDOW = 60.0  # секунд


def _auth_rate_limit_check(client_host: str) -> bool:
    """True если лимит не превышен, иначе False."""
    now = time.time()
    key = (client_host or "unknown").strip() or "unknown"
    if key not in _AUTH_RATE_LIMIT:
        _AUTH_RATE_LIMIT[key] = []
    times = _AUTH_RATE_LIMIT[key]
    times[:] = [t for t in times if now - t < _AUTH_RATE_LIMIT_WINDOW]
    if len(times) >= _AUTH_RATE_LIMIT_MAX:
        return False
    times.append(now)
    return True


def _normalize_phone(phone: str) -> str:
    """Оставить только цифры от телефона."""
    return re.sub(r"\D", "", phone or "").strip() or ""


async def _get_auth_user(authorization: str | None = Header(None)) -> dict | None:
    """Из заголовка Authorization: Bearer <token> вернуть site_user dict или None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    if not token or not AUTH_JWT_SECRET:
        return None
    try:
        payload = jwt.decode(token, AUTH_JWT_SECRET, algorithms=[AUTH_JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        user = await get_site_user_by_id(int(user_id))
        return user
    except Exception:
        return None


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


@app.post("/api/auth/register")
async def api_auth_register(request: Request):
    """Регистрация: телефон + пароль, опционально имя. Защита: rate limit, пароль не менее 8 символов."""
    if not _auth_rate_limit_check(request.client.host if request.client else ""):
        payment_log("auth_register_rate_limit", host=request.client.host if request.client else "")
        return JSONResponse({"success": False, "error": "Слишком много попыток. Подождите минуту."}, status_code=429)
    try:
        data = await request.json()
        phone = _normalize_phone(data.get("phone") or "")
        password = (data.get("password") or "").strip()
        name = (data.get("name") or "").strip() or None
        if len(phone) < 10:
            return JSONResponse({"success": False, "error": "Введите корректный телефон"}, status_code=400)
        if len(password) < 8:
            return JSONResponse({"success": False, "error": "Пароль не менее 8 символов"}, status_code=400)
        password_hash = bcrypt.hash(password)
        user = await create_site_user(phone=phone, password_hash=password_hash, name=name)
        if not user:
            payment_log("auth_register_fail", reason="phone_taken", phone_len=len(phone))
            return JSONResponse({"success": False, "error": "Этот телефон уже зарегистрирован"}, status_code=409)
        payload = {"sub": user["id"], "exp": int(time.time()) + AUTH_JWT_EXP_SECONDS}
        token = jwt.encode(payload, AUTH_JWT_SECRET, algorithm=AUTH_JWT_ALGORITHM)
        return JSONResponse({
            "success": True,
            "token": token,
            "user": {"id": user["id"], "phone": user["phone"], "name": user.get("name")},
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    """Вход: телефон + пароль, возврат JWT. Защита: rate limit."""
    if not _auth_rate_limit_check(request.client.host if request.client else ""):
        payment_log("auth_login_rate_limit", host=request.client.host if request.client else "")
        return JSONResponse({"success": False, "error": "Слишком много попыток. Подождите минуту."}, status_code=429)
    try:
        data = await request.json()
        phone = _normalize_phone(data.get("phone") or "")
        password = (data.get("password") or "").strip()
        if not phone or not password:
            return JSONResponse({"success": False, "error": "Введите телефон и пароль"}, status_code=400)
        user = await get_site_user_by_phone(phone)
        if not user or not bcrypt.verify(password, user.get("password_hash") or ""):
            payment_log("auth_login_fail", reason="bad_credentials", phone_len=len(phone))
            return JSONResponse({"success": False, "error": "Неверный телефон или пароль"}, status_code=401)
        payload = {"sub": user["id"], "exp": int(time.time()) + AUTH_JWT_EXP_SECONDS}
        token = jwt.encode(payload, AUTH_JWT_SECRET, algorithm=AUTH_JWT_ALGORITHM)
        return JSONResponse({
            "success": True,
            "token": token,
            "user": {"id": user["id"], "phone": user["phone"], "name": user.get("name")},
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/auth/me")
async def api_auth_me(authorization: str | None = Header(None)):
    """Текущий пользователь по JWT (для подстановки в форму заказа)."""
    user = await _get_auth_user(authorization)
    if not user:
        return JSONResponse({"success": False, "error": "Не авторизован"}, status_code=401)
    return JSONResponse({"success": True, "user": user})


@app.post("/api/order")
async def api_create_order(request: Request, authorization: str | None = Header(None)):
    """Создать заказ и отправить на кассу YTimes."""
    try:
        data = await request.json()
        items = data.get("items", [])
        if not items:
            return JSONResponse({"success": False, "error": "Пустой заказ"}, status_code=400)

        total = sum(item.get("priceWithDiscount", 0) * item.get("quantity", 1) for item in items)
        order_guid = str(uuid.uuid4())
        client = data.get("client") or {}
        auth_user = await _get_auth_user(authorization)
        if auth_user:
            client = {
                "name": (client.get("name") or "").strip() or (auth_user.get("name") or auth_user.get("phone") or "Пользователь"),
                "phone": (client.get("phone") or "").strip() or (auth_user.get("phone") or ""),
                "email": (client.get("email") or "").strip(),
            }
        if not (client.get("name") or str(client.get("name", "")).strip()):
            return JSONResponse({"success": False, "error": "Укажите имя"}, status_code=400)
        if not (client.get("phone") or str(client.get("phone", "")).strip()):
            return JSONResponse({"success": False, "error": "Укажите телефон"}, status_code=400)
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
    save_payment_method: bool = False,
) -> dict | None:
    """Создать платёж в ЮKassa. save_payment_method=True — привязка карты для повторных списаний."""
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
    if save_payment_method:
        payload["save_payment_method"] = True
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
        payment_log("payment_prepare_ok", payment_token=payment_token, total=total)
        return JSONResponse({"success": True, "payment_token": payment_token})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/payment/create-inapp")
async def api_payment_create_inapp(request: Request, authorization: str | None = Header(None)):
    """Создать платёж ЮKassa для оплаты внутри Mini App. Возвращает confirmation_url для перехода."""
    payment_token = None
    try:
        data = await request.json()
        items = data.get("items", [])
        if not items:
            payment_log("create_inapp_reject", reason="empty_cart")
            return JSONResponse({"success": False, "error": "Пустая корзина"}, status_code=400)
        total = sum(item.get("priceWithDiscount", 0) * item.get("quantity", 1) for item in items)
        if total <= 0:
            payment_log("create_inapp_reject", reason="invalid_total", total=total)
            return JSONResponse({"success": False, "error": "Некорректная сумма"}, status_code=400)
        client = data.get("client") or {}
        auth_user = await _get_auth_user(authorization)
        if auth_user:
            client = {
                "name": (client.get("name") or "").strip() or (auth_user.get("name") or auth_user.get("phone") or "Пользователь"),
                "phone": (client.get("phone") or "").strip() or (auth_user.get("phone") or ""),
                "email": (client.get("email") or "").strip(),
            }
        if not (client.get("name") or str(client.get("name", "")).strip()):
            payment_log("create_inapp_reject", reason="no_name")
            return JSONResponse({"success": False, "error": "Укажите имя"}, status_code=400)
        if not (client.get("phone") or str(client.get("phone", "")).strip()):
            payment_log("create_inapp_reject", reason="no_phone")
            return JSONResponse({"success": False, "error": "Укажите телефон"}, status_code=400)
        if not _yookassa_auth():
            payment_log("create_inapp_reject", reason="yookassa_not_configured")
            return JSONResponse(
                {"success": False, "error": "Оплата в приложении не настроена (ЮKassa). Выберите «Оплата при получении» или оплату через бота."},
                status_code=503,
            )
        telegram_id = int(data.get("telegramUserId") or 0)
        comment = (data.get("comment") or "").strip()
        payment_token = uuid.uuid4().hex
        site_user_id = auth_user.get("id") if auth_user else None
        await create_pending_payment(
            payment_token=payment_token,
            telegram_id=telegram_id,
            items_json=json.dumps(items),
            total=total,
            client_json=json.dumps(client),
            comment=comment,
            site_user_id=site_user_id,
        )
        payment_log("create_inapp_pending_created", payment_token=payment_token, total=total, site_user_id=site_user_id)
        webapp_url = (os.getenv("WEBAPP_URL") or "").rstrip("/")
        if not webapp_url:
            payment_log("create_inapp_reject", reason="no_webapp_url")
            return JSONResponse({"success": False, "error": "WEBAPP_URL не задан"}, status_code=500)
        return_url = f"{webapp_url}/api/payment/return?payment_token={payment_token}"
        yookassa_resp = await _yookassa_create_payment(
            amount_rub=total,
            description=f"Заказ на {total:.2f} ₽",
            return_url=return_url,
            metadata={"payment_token": payment_token},
        )
        if not yookassa_resp or yookassa_resp.get("status") not in ("pending", "waiting_for_capture"):
            payment_log("create_inapp_yookassa_fail", payment_token=payment_token, yookassa_status=yookassa_resp.get("status") if yookassa_resp else None)
            return JSONResponse({"success": False, "error": "Не удалось создать платёж. Попробуйте позже."}, status_code=502)
        yookassa_id = yookassa_resp.get("id")
        confirmation = yookassa_resp.get("confirmation") or {}
        confirmation_url = confirmation.get("confirmation_url")
        if not yookassa_id or not confirmation_url:
            payment_log("create_inapp_yookassa_no_url", payment_token=payment_token, yookassa_id=yookassa_id)
            return JSONResponse({"success": False, "error": "Ошибка ответа платёжной системы."}, status_code=502)
        await set_pending_yookassa_id(payment_token, yookassa_id)
        payment_log("create_inapp_ok", payment_token=payment_token, yookassa_id=yookassa_id, total=total)
        return JSONResponse({
            "success": True,
            "payment_token": payment_token,
            "confirmation_url": confirmation_url,
        })
    except Exception as e:
        payment_log("create_inapp_error", payment_token=payment_token, error=str(e))
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/payment/return")
async def api_payment_return(payment_token: str):
    """Возврат пользователя после оплаты ЮKassa. Проверяем статус, создаём заказ, редирект в приложение."""
    payment_log("return_start", payment_token=payment_token or "")
    webapp_url = (os.getenv("WEBAPP_URL") or "").rstrip("/")
    fail_url = f"{webapp_url}?payment_failed=1" if webapp_url else "/"
    if not payment_token:
        payment_log("return_fail", reason="no_token")
        return RedirectResponse(url=fail_url)
    pending = await get_pending_payment(payment_token)
    if not pending:
        payment_log("return_fail", payment_token=payment_token, reason="pending_not_found")
        return RedirectResponse(url=fail_url)
    payment_log("return_pending_found", payment_token=payment_token, total=pending.get("total"))
    yookassa_id = (pending.get("yookassa_payment_id") or "").strip()
    if not yookassa_id:
        payment_log("return_fail", payment_token=payment_token, reason="no_yookassa_id")
        return RedirectResponse(url=fail_url)
    payment = await _yookassa_get_payment(yookassa_id)
    if not payment or payment.get("status") != "succeeded":
        payment_log("return_fail", payment_token=payment_token, yookassa_id=yookassa_id, yookassa_status=payment.get("status") if payment else None)
        return RedirectResponse(url=fail_url)
    payment_log("return_yookassa_succeeded", payment_token=payment_token, yookassa_id=yookassa_id)
    link_card_only = pending.get("link_card_only")
    items = json.loads(pending["items_json"])
    total = float(pending["total"])
    client = json.loads(pending["client_json"] or "{}")
    comment = (pending["comment"] or "").strip()
    telegram_id = int(pending.get("telegram_id") or 0)
    site_user_id = pending.get("site_user_id")
    if site_user_id:
        pm = (payment.get("payment_method") or {})
        pm_id = pm.get("id") if isinstance(pm, dict) else None
        if pm_id:
            try:
                await update_site_user_saved_payment_method(int(site_user_id), pm_id)
                payment_log("return_card_saved", payment_token=payment_token, site_user_id=int(site_user_id))
            except Exception as e:
                payment_log("return_card_save_error", payment_token=payment_token, error=str(e))
    if link_card_only:
        await delete_pending_payment(payment_token)
        payment_log("return_link_card_ok", payment_token=payment_token)
        success_url = f"{webapp_url}?card_linked=1" if webapp_url else "/?card_linked=1"
        return RedirectResponse(url=success_url)
    if not ytimes_client:
        payment_log("return_fail", payment_token=payment_token, reason="no_ytimes")
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
    except Exception as e:
        payment_log("return_order_error", payment_token=payment_token, error=str(e))
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
    payment_log("return_success", payment_token=payment_token, order_id=order_id_return, total=total)
    success_url = f"{webapp_url}?payment_success=1&order_id={order_id_return}" if webapp_url else "/"
    return RedirectResponse(url=success_url)


@app.post("/api/payment/link-card")
async def api_payment_link_card(request: Request, authorization: str | None = Header(None)):
    """Привязать карту к аккаунту: платёж 1 ₽, после оплаты карта сохраняется для повторных заказов."""
    auth_user = await _get_auth_user(authorization)
    if not auth_user:
        return JSONResponse({"success": False, "error": "Войдите в аккаунт"}, status_code=401)
    if not _yookassa_auth():
        return JSONResponse({"success": False, "error": "Оплата не настроена"}, status_code=503)
    webapp_url = (os.getenv("WEBAPP_URL") or "").rstrip("/")
    if not webapp_url:
        return JSONResponse({"success": False, "error": "WEBAPP_URL не задан"}, status_code=500)
    payment_token = uuid.uuid4().hex
    client = {"name": auth_user.get("name") or auth_user.get("phone") or "Пользователь", "phone": auth_user.get("phone") or "", "email": ""}
    await create_pending_payment(
        payment_token=payment_token,
        telegram_id=0,
        items_json="[]",
        total=1.0,
        client_json=json.dumps(client),
        comment="Привязка карты",
        site_user_id=auth_user["id"],
        link_card_only=True,
    )
    return_url = f"{webapp_url}/api/payment/return?payment_token={payment_token}"
    yookassa_resp = await _yookassa_create_payment(
        amount_rub=1.0,
        description="Привязка карты к аккаунту (1 ₽)",
        return_url=return_url,
        metadata={"payment_token": payment_token},
        save_payment_method=True,
    )
    if not yookassa_resp or yookassa_resp.get("status") not in ("pending", "waiting_for_capture"):
        payment_log("link_card_yookassa_fail", site_user_id=auth_user["id"])
        return JSONResponse({"success": False, "error": "Не удалось создать платёж"}, status_code=502)
    yookassa_id = yookassa_resp.get("id")
    confirmation = yookassa_resp.get("confirmation") or {}
    confirmation_url = confirmation.get("confirmation_url")
    if not yookassa_id or not confirmation_url:
        return JSONResponse({"success": False, "error": "Ошибка платёжной системы"}, status_code=502)
    await set_pending_yookassa_id(payment_token, yookassa_id)
    payment_log("link_card_created", payment_token=payment_token, site_user_id=auth_user["id"])
    return JSONResponse({"success": True, "confirmation_url": confirmation_url})


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
        payment_log("order_from_payment_reject", reason="bad_secret")
        return JSONResponse({"success": False, "error": str(e)}, status_code=403)
    try:
        data = await request.json()
        payment_token = (data.get("payment_token") or "").strip()
        if not payment_token:
            payment_log("order_from_payment_reject", reason="no_token")
            return JSONResponse({"success": False, "error": "Требуется payment_token"}, status_code=400)
        payment_log("order_from_payment_start", payment_token=payment_token)
        pending = await get_pending_payment(payment_token)
        if not pending:
            payment_log("order_from_payment_fail", payment_token=payment_token, reason="pending_not_found")
            return JSONResponse({"success": False, "error": "Платёж не найден или уже использован"}, status_code=404)
        items = json.loads(pending["items_json"])
        total = float(pending["total"])
        client = json.loads(pending["client_json"] or "{}")
        comment = (pending["comment"] or "").strip()
        telegram_id = int(data.get("telegram_id") or pending["telegram_id"] or 0)
        if not ytimes_client:
            payment_log("order_from_payment_fail", payment_token=payment_token, reason="no_ytimes")
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
        payment_log("order_from_payment_ok", payment_token=payment_token, order_id=order_id_return, total=total)
        return JSONResponse({
            "success": True,
            "order_id": order_id_return,
            "status": status,
            "total": total,
        })
    except YTimesAPIError as e:
        payment_log("order_from_payment_ytimes_error", error=str(e))
        return JSONResponse({"success": False, "error": str(e)}, status_code=502)
    except Exception as e:
        payment_log("order_from_payment_error", error=str(e))
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

