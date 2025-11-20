# Настройка GitHub репозитория

## Шаг 1: Создание репозитория на GitHub

1. Откройте [GitHub.com](https://github.com) и войдите в аккаунт
2. Нажмите кнопку **"+"** в правом верхнем углу → **"New repository"**
3. Заполните форму:
   - **Repository name**: `tg-cafe-bot` (или любое другое название)
   - **Description**: "Telegram bot for cafe orders with YTimes integration"
   - **Visibility**:
     - ✅ **Private** (рекомендуется, если код содержит секреты)
     - или **Public** (если хотите открытый репозиторий)
   - ❌ **НЕ** ставьте галочки на "Add a README file", "Add .gitignore", "Choose a license" (у нас уже есть файлы)
4. Нажмите **"Create repository"**

## Шаг 2: Подключение локального репозитория к GitHub

После создания репозитория GitHub покажет инструкции. Выполните команды:

```bash
# Перейдите в папку проекта
cd /Users/user/Telegramm_cafe_buybot_actual_version+git/Tg_zakaz_bot

# Добавьте remote репозиторий (замените YOUR_USERNAME на ваш GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/tg-cafe-bot.git

# Или если используете SSH:
# git remote add origin git@github.com:YOUR_USERNAME/tg-cafe-bot.git

# Переименуйте ветку в main (если нужно)
git branch -M main

# Отправьте код на GitHub
git push -u origin main
```

## Шаг 3: Проверка подключения

Проверить, что репозиторий подключен:

```bash
git remote -v
```

Должно показать:

```
origin  https://github.com/YOUR_USERNAME/tg-cafe-bot.git (fetch)
origin  https://github.com/YOUR_USERNAME/tg-cafe-bot.git (push)
```

## Шаг 4: Подключение к Railway

После того как код будет на GitHub:

1. Откройте [railway.app](https://railway.app)
2. Войдите через GitHub
3. Нажмите **"New Project"**
4. Выберите **"Deploy from GitHub repo"**
5. Выберите ваш репозиторий `tg-cafe-bot`
6. Railway автоматически определит Python проект

## Важно!

⚠️ **НЕ коммитьте файл `.env`** - он уже в `.gitignore`

✅ **Коммитьте `example.env`** - это шаблон для других разработчиков

## Если репозиторий уже существует

Если у вас уже есть репозиторий на GitHub и вы хотите подключить этот проект:

```bash
# Проверьте текущие remote
git remote -v

# Если есть старый origin, удалите его
git remote remove origin

# Добавьте новый
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# Отправьте код
git push -u origin main
```
