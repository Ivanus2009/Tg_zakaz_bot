# Запуск через Docker (VPS / передача заказчику)

Краткая инструкция по развёртыванию приложения на своём сервере (VPS) или передаче заказчику «под ключ».

## Требования

- На сервере установлены **Docker** и **Docker Compose**.
- Домен направлен на IP сервера (A-запись в DNS).
- HTTPS настраивается на хосте (reverse proxy + Let's Encrypt), трафик проксируется на порт **8000** контейнера `web`.

## Шаги

### 1. Подготовка окружения

Скопируйте репозиторий на сервер. Создайте файл `.env` из примера:

```bash
cp example.env .env
```

Отредактируйте `.env`, заполните:

- `TELEGRAM_BOT_TOKEN` — токен от @BotFather.
- `YT_API_KEY`, `YT_SHOP_GUID` — ключи YTimes.
- `WEBAPP_URL=https://ваш-домен.ru` — **без слэша в конце**. Это адрес, по которому пользователи будут открывать Mini App в Telegram (после настройки SSL).

### 2. Запуск контейнеров

Из корня проекта:

```bash
docker compose up -d
```

Поднимаются два контейнера:

- **web** — FastAPI (SPA + API), порт 8000.
- **bot** — Telegram-бот (long polling). База SQLite хранится в volume `tgzakaz_data`.

Остановка:

```bash
docker compose down
```

### 3. HTTPS и reverse proxy (на хосте)

Telegram открывает Mini App только по **HTTPS**. На сервере нужно:

1. Установить nginx или Caddy.
2. Настроить виртуальный хост для вашего домена с проксированием на `http://127.0.0.1:8000`.
3. Выпустить сертификат (например, Let's Encrypt: `certbot` для nginx или встроенный механизм Caddy).

Пример фрагмента nginx (после получения сертификата):

```nginx
server {
    listen 443 ssl;
    server_name ваш-домен.ru;
    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

После настройки DNS и SSL убедитесь, что `WEBAPP_URL` в `.env` совпадает с этим доменом (например `https://cafe.example.com`). При смене `WEBAPP_URL` перезапустите контейнеры: `docker compose up -d --force-recreate`.

### 4. Передача заказчику

- Передайте заказчику репозиторий (или образ), файл `.env` с заполненными значениями и эту инструкцию.
- Заказчику достаточно: свой домен, DNS на сервер, установленный Docker; затем заполнить `.env`, настроить SSL и выполнить `docker compose up -d`.

Подробнее об общей схеме работы приложения см. [HOW_IT_WORKS.md](HOW_IT_WORKS.md), раздел 9.
