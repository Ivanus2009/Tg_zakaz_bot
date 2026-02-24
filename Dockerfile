# Multi-stage: сначала сборка фронта, затем образ с Python (web + bot).
# Используется один образ для сервисов web и bot; команда запуска разная.

# --- Stage 1: сборка React ---
FROM node:20-alpine AS frontend-build
WORKDIR /build

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --omit=dev || npm install --omit=dev

COPY frontend/ ./
RUN npm run build

# --- Stage 2: приложение (FastAPI + бот) ---
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Зависимости Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Исходники и статика
COPY src/ ./src/
COPY templates/ ./templates/
COPY --from=frontend-build /build/dist ./frontend/dist

# Каталог для SQLite (бот); при запуске монтируется volume или создаётся
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# По умолчанию — web. Для бота в docker-compose задаётся command.
CMD ["uvicorn", "src.webapp.app:app", "--host", "0.0.0.0", "--port", "8000"]
