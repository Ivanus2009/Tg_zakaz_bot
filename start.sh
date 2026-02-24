#!/usr/bin/env bash
# Полная зачистка процессов и портов приложения, затем запуск по одному экземпляру веба и бота.

set -e
cd "$(dirname "$0")"

echo "Зачистка: останавливаю все процессы и порты приложения..."

# Порт веб-сервера
if lsof -ti:8000 >/dev/null 2>&1; then
  echo "  • освобождаю порт 8000..."
  lsof -ti:8000 | xargs kill -9 2>/dev/null || true
fi

# Все экземпляры веба (uvicorn этого приложения)
if pgrep -f "uvicorn.*webapp.app" >/dev/null 2>&1; then
  echo "  • останавливаю uvicorn (web)..."
  pkill -f "uvicorn.*webapp.app" 2>/dev/null || true
fi

# Все экземпляры бота
if pgrep -f "src/bot/bot.py" >/dev/null 2>&1; then
  echo "  • останавливаю бота..."
  pkill -f "src/bot/bot.py" 2>/dev/null || true
fi

echo "  жду 2 сек, чтобы порты и Telegram освободились..."
sleep 2

echo ""
echo "Запускаю по одному экземпляру..."
.venv/bin/uvicorn src.webapp.app:app --reload --host 0.0.0.0 --port 8000 &
WEB_PID=$!
.venv/bin/python src/bot/bot.py &
BOT_PID=$!

echo ""
echo "Готово. Работают:"
echo "  • Веб:  http://localhost:8000  (PID $WEB_PID)"
echo "  • Бот:  в Telegram  (PID $BOT_PID)"
echo ""
echo "Остановка: Ctrl+C"
echo ""

wait
