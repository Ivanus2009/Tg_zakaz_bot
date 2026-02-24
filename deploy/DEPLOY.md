# Деплой на VPS (palm-marten.ru)

Пошаговая настройка продакшена на одном VPS (Ubuntu 24.04). Домен: palm-marten.ru (Reg.ru). Всё в Docker Compose: nginx, certbot, web, bot.

## 1. DNS в Reg.ru

В панели домена palm-marten.ru создать только A-записи на `85.239.38.41`:

- `palm-marten.ru` (или @) → `85.239.38.41`
- `www` → `85.239.38.41`
- `api` → `85.239.38.41`

Удалить или отключить старые A на `31.31.196.75`. AAAA (IPv6) при необходимости отключить.

Проверка (через 5–15 мин):

```bash
nslookup palm-marten.ru
nslookup www.palm-marten.ru
nslookup api.palm-marten.ru
```

Ожидается один и тот же IP: `85.239.38.41`.

---

## 2. Подготовка VPS (Ubuntu 24.04)

Подключение:

```bash
ssh root@85.239.38.41
```

Обновление системы:

```bash
apt update && apt upgrade -y
```

Установка Docker:

```bash
apt install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod 644 /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker && systemctl start docker
```

Проверка: `docker run --rm hello-world`. Если появится ошибка про rate limit Docker Hub — залогиньтесь: `docker login` (аккаунт на hub.docker.com бесплатный).

Файрвол:

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status
```

---

Подробно: готовность проекта, что добавить в .env и как запускать тесты — в [APP_READY_AND_ENV.md](APP_READY_AND_ENV.md).

---

## 3. Размещение проекта на сервере

Вариант A — клонировать репозиторий в `/opt/marten`:

```bash
mkdir -p /opt/marten
cd /opt/marten
git clone https://github.com/Ivanus2009/Tg_zakaz_bot.git .
```

Вариант B — скопировать файлы с локальной машины (scp/rsync). Должна получиться структура:

- `/opt/marten/` — корень репо (Dockerfile, src/, frontend/, requirements.txt, example.env и т.д.)
- `/opt/marten/deploy/docker-compose.yml`
- `/opt/marten/deploy/nginx/conf.d/http.conf`
- `/opt/marten/deploy/nginx/conf.d/https.conf`

Создать каталоги для certbot:

```bash
mkdir -p /opt/marten/deploy/certbot/www /opt/marten/deploy/certbot/conf
```

---

## 4. Файл .env на сервере

Создать `/opt/marten/.env` (не коммитить в git). Скопировать из example.env и подставить реальные значения:

```bash
cd /opt/marten
cp example.env .env
nano .env
```

Обязательные переменные:

- `YT_API_KEY` — ключ интеграции YTimes
- `YT_SHOP_GUID` — GUID торговой точки
- `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather
- `WEBAPP_URL=https://palm-marten.ru` (без слэша в конце)

Для онлайн-оплаты добавить:

- `BOT_INTERNAL_SECRET` — случайная строка для проверки запросов от бота к backend (например `openssl rand -hex 32`)
- `BACKEND_URL` — на VPS в Docker: `http://web:8000` (бот вызывает API по имени сервиса)
- `PAYMENT_PROVIDER_TOKEN` — токен провайдера платежей в BotFather (Payments), если используете «Оплатить онлайн»

---

## 5. Первый запуск (только HTTP)

Чтобы nginx стартовал без ошибок, HTTPS пока не подключаем. Переименовать https.conf:

```bash
cd /opt/marten/deploy
mv nginx/conf.d/https.conf nginx/conf.d/https.conf.bak
```

Сборка и запуск:

```bash
cd /opt/marten
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

Проверить: `curl -I http://85.239.38.41` и при настроенном DNS `curl -I http://palm-marten.ru` — ожидается ответ от приложения.

---

## 6. Получение SSL-сертификатов (certbot)

Один раз получить сертификаты (подставить свой email). Важно: `--entrypoint ""` — иначе контейнер запустит только `certbot renew` и сертификаты не выдадутся.

```bash
cd /opt/marten
docker compose -f deploy/docker-compose.yml run --rm --entrypoint "" certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d palm-marten.ru -d www.palm-marten.ru -d api.palm-marten.ru \
  --email your@email.com \
  --agree-tos --no-eff-email
```

После успеха в `deploy/certbot/conf/live/palm-marten.ru/` появятся `fullchain.pem` и `privkey.pem`.

Включить HTTPS в nginx:

```bash
cd /opt/marten/deploy
mv nginx/conf.d/https.conf.bak nginx/conf.d/https.conf
docker compose -f deploy/docker-compose.yml exec nginx nginx -s reload
```

Опционально: включить редирект HTTP → HTTPS в `deploy/nginx/conf.d/http.conf` — раскомментировать строку с `return 301 https://...` и закомментировать блок `location /` с proxy_pass, затем снова `nginx -s reload`.

---

## 7. Автообновление сертификатов (cron)

На сервере:

```bash
crontab -e
```

Добавить строку (путь к compose — при необходимости поправить):

```bash
0 3 * * * cd /opt/marten && docker compose -f deploy/docker-compose.yml run --rm --entrypoint "" certbot certbot renew && docker compose -f deploy/docker-compose.yml exec nginx nginx -s reload
```

---

## 8. Проверки после деплоя

DNS:

```bash
nslookup palm-marten.ru
nslookup www.palm-marten.ru
nslookup api.palm-marten.ru
```

HTTP (если редирект ещё не включён):

```bash
curl -I http://palm-marten.ru
curl -I http://api.palm-marten.ru/health
```

HTTPS и сертификат:

```bash
curl -I https://palm-marten.ru
openssl s_client -connect palm-marten.ru:443 -servername palm-marten.ru </dev/null 2>/dev/null | openssl x509 -noout -dates
```

Сайт и API:

```bash
curl -s https://palm-marten.ru/ | head -20
curl -s https://palm-marten.ru/health
curl -s https://api.palm-marten.ru/api/menu
```

Ограничение размера тела (ожидается 413 при теле > 2MB):

```bash
curl -X POST https://palm-marten.ru/api/order -H "Content-Type: application/json" -d '{"x":"'$(python3 -c 'print("a"*3000000)')'"}' -w "%{http_code}"
```

---

## 9. Обновление приложения

После изменений в коде на сервере:

```bash
cd /opt/marten
git pull   # или загрузить файлы иначе
docker compose -f deploy/docker-compose.yml build --no-cache
docker compose -f deploy/docker-compose.yml up -d
```

Логи: `docker compose -f deploy/docker-compose.yml logs -f web` или `logs -f bot`.
