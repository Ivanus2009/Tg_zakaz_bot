"""FastAPI приложение для Telegram Mini App."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Добавляем src в путь
ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ytimes import YTimesAPIClient

app = FastAPI(title="Telegram Mini App - Заказы")

# Статические файлы и шаблоны
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
        ytimes_client = YTimesAPIClient.from_env()
    except Exception as e:
        print(f"Ошибка инициализации YTimes клиента: {e}")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница мини-приложения."""
    return templates.TemplateResponse("index.html", {"request": request})


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


@app.post("/api/order")
async def create_order(request: Request):
    """Создать заказ (замоканный - без реального создания в YTimes)."""
    try:
        import uuid
        data = await request.json()
        
        # Извлекаем данные из запроса
        items = data.get("items", [])
        total = sum(item.get("priceWithDiscount", 0) * item.get("quantity", 1) for item in items)
        
        # Генерируем моковый ID заказа
        mock_order_id = str(uuid.uuid4())[:8].upper()
        
        # TODO: В будущем здесь будет реальное создание заказа через YTimes API
        # Пока просто возвращаем успешный ответ
        
        return JSONResponse({
            "success": True,
            "order_id": mock_order_id,
            "status": "CREATED",
            "total": total,
            "message": "Заказ успешно сформирован и отправлен"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

