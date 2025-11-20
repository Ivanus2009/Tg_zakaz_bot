# Настройка деплоя на Fly.io (БЕСПЛАТНО)

Fly.io - полностью бесплатный вариант с хорошей производительностью.

## Шаг 1: Установка Fly CLI

```bash
# macOS
brew install flyctl

# Или скачайте с https://fly.io/docs/getting-started/installing-flyctl/
```

## Шаг 2: Регистрация

```bash
flyctl auth signup
# Или через браузер:
flyctl auth login
```

## Шаг 3: Создание приложения

```bash
cd /Users/user/Telegramm_cafe_buybot_actual_version+git/Tg_zakaz_bot

# Создать приложение для веб-сервиса
flyctl launch --name tg-cafe-web

# Выберите:
# - Region: ближайший к вам (например, ams для Амстердама)
# - Postgres: No
# - Redis: No
```

## Шаг 4: Настройка fly.toml

Создайте файл `fly.toml`:

```toml
app = "tg-cafe-web"
primary_region = "ams"

[build]

[env]
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1
  processes = ["app"]

[[services]]
  protocol = "tcp"
  internal_port = 8000
  processes = ["app"]

  [[services.ports]]
    port = 80
    handlers = ["http"]
    force_https = true

  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]
```

## Шаг 5: Переменные окружения

```bash
flyctl secrets set YT_API_KEY=ваш_ключ_из_ytimes
flyctl secrets set YT_SHOP_GUID=bdd03b7e-4fd9-4081-bfc0-959229d79044
```

## Шаг 6: Деплой

```bash
flyctl deploy
```

После деплоя получите URL:
```bash
flyctl status
```

## Шаг 7: Создание приложения для бота

```bash
# Создать отдельное приложение для бота
flyctl launch --name tg-cafe-bot --no-deploy

# Настройте fly.toml для бота (измените app name)
```

Создайте `fly-bot.toml`:

```toml
app = "tg-cafe-bot"
primary_region = "ams"

[build]

[env]
  TELEGRAM_BOT_TOKEN = "8357146502:AAF9ZBFC3DUG64bpUNp-YGMg_JlDnXOtDHw"
  YT_API_KEY = "ваш_ключ"
  YT_SHOP_GUID = "bdd03b7e-4fd9-4081-bfc0-959229d79044"
  WEBAPP_URL = "https://tg-cafe-web.fly.dev"

[processes]
  bot = "python src/bot/bot.py"
```

Деплой бота:
```bash
flyctl deploy -c fly-bot.toml
```

## Стоимость

- **Бесплатно**: 3 shared-cpu-1x VMs
- Для этого проекта обычно хватает бесплатного тарифа
- Если превысите лимит, Fly.io уведомит вас

## Обновление

```bash
git push
flyctl deploy
```

