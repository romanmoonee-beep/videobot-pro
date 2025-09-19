# VideoBot Pro - Инструкция по запуску

## 🚀 Быстрый старт

### 1. Установка зависимостей

Сначала установите Python 3.9+ и PostgreSQL, затем:

```bash
# Клонируем проект
git clone <your-repo>
cd videobot-pro

# Создаем виртуальное окружение
python -m venv venv

# Активируем окружение
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt
```

### 2. Настройка окружения

Создайте файл `.env` из примера:

```bash
cp .env.example .env
```

**Обязательные настройки в .env:**
```env
# Получите токен у @BotFather в Telegram
BOT_TOKEN=your_bot_token_here

# Ваш Telegram ID для админки (узнать у @userinfobot)
ADMIN_IDS=123456789

# База данных (настройте под свои параметры)
DATABASE_URL=postgresql+asyncpg://videobot:password@localhost:5432/videobot

# Redis (если установлен)
REDIS_URL=redis://localhost:6379/0
```

### 3. Настройка базы данных

#### Вариант 1: Автоматическая настройка (рекомендуется)

```bash
# Создание БД и таблиц одной командой
python migrate.py --mode=direct
```

#### Вариант 2: Через миграции Alembic

```bash
# Полная настройка с миграциями
python migrate.py --mode=full
```

#### Вариант 3: Ручная настройка PostgreSQL

```sql
-- Подключитесь к PostgreSQL и выполните:
CREATE DATABASE videobot;
CREATE USER videobot WITH PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE videobot TO videobot;
```

Затем запустите:
```bash
python migrate.py --mode=direct
```

### 4. Запуск бота

```bash
# Запуск в режиме разработки (polling)
python -m bot.main

# Или через точку входа
python bot/main.py
```

### 5. Проверка работы

1. Найдите вашего бота в Telegram
2. Отправьте `/start`
3. Попробуйте скачать видео с YouTube

---

## 🔧 Детальная настройка

### Установка PostgreSQL

#### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Windows:
1. Скачайте с https://www.postgresql.org/download/windows/
2. Установите с настройками по умолчанию
3. Запомните пароль для пользователя `postgres`

#### macOS:
```bash
brew install postgresql
brew services start postgresql
```

### Установка Redis (опционально)

#### Ubuntu/Debian:
```bash
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

#### Windows:
1. Скачайте Redis для Windows
2. Или используйте WSL/Docker

#### macOS:
```bash
brew install redis
brew services start redis
```

### Настройка БД вручную

```bash
# Подключение к PostgreSQL
sudo -u postgres psql

# В консоли PostgreSQL:
CREATE DATABASE videobot;
CREATE USER videobot WITH ENCRYPTED PASSWORD 'password';
GRANT ALL PRIVILEGES ON DATABASE videobot TO videobot;
\q
```

---

## 📁 Структура проекта

```
videobot-pro/
├── shared/                 # Общие модули
│   ├── config/             # Конфигурация
│   ├── models/             # Модели БД
│   └── utils/              # Утилиты
├── bot/                    # Telegram бот
│   ├── handlers/           # Обработчики сообщений
│   ├── middlewares/        # Middleware
│   ├── services/           # Бизнес-логика
│   └── main.py             # Точка входа
├── worker/                 # Celery worker (опционально)
├── migrations/             # Миграции БД
├── migrate.py              # Скрипт миграций
└── .env                    # Настройки окружения
```

---

## 🎯 Возможные проблемы и решения

### Проблема: "ModuleNotFoundError"
**Решение:**
```bash
# Убедитесь что вы в правильной директории и venv активен
pwd
which python
pip list | grep aiogram
```

### Проблема: "Database connection failed"
**Решение:**
1. Проверьте что PostgreSQL запущен: `sudo systemctl status postgresql`
2. Проверьте настройки в `.env`
3. Проверьте что БД существует: `psql -U videobot -d videobot`

### Проблема: "Unauthorized" от Telegram
**Решение:**
1. Проверьте BOT_TOKEN в `.env`
2. Убедитесь что токен получен от @BotFather
3. Проверьте что нет лишних пробелов в токене

### Проблема: Таблицы не создаются
**Решение:**
```bash
# Попробуйте пересоздать таблицы
python migrate.py --mode=direct

# Или проверьте подключение к БД
python -c "
import asyncio
from shared.config.database import init_database
asyncio.run(init_database())
print('Database connection OK')
"
```

---

## 🚀 Производственное развертывание

### 1. Настройки для production

В `.env`:
```env
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# Webhook вместо polling
WEBHOOK_URL=https://yourdomain.com
WEBHOOK_SECRET=your_webhook_secret

# Более безопасные настройки БД
DATABASE_URL=postgresql+asyncpg://videobot:secure_password@localhost:5432/videobot
```

### 2. Systemd сервис (Linux)

Создайте `/etc/systemd/system/videobot.service`:

```ini
[Unit]
Description=VideoBot Pro
After=network.target postgresql.service

[Service]
Type=simple
User=videobot
WorkingDirectory=/path/to/videobot-pro
Environment=PATH=/path/to/videobot-pro/venv/bin
ExecStart=/path/to/videobot-pro/venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запуск:
```bash
sudo systemctl daemon-reload
sudo systemctl enable videobot
sudo systemctl start videobot
sudo systemctl status videobot
```

### 3. Docker (альтернатива)

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "-m", "bot.main"]
```

---

## 📊 Мониторинг и логи

### Просмотр логов
```bash
# В режиме разработки логи выводятся в консоль
python -m bot.main

# В production логи сохраняются в файл
tail -f videobot.log

# Systemd логи
sudo journalctl -u videobot -f
```

### Health check
```bash
# Проверка состояния БД
python -c "
import asyncio
from shared.config.database import DatabaseHealthCheck
async def check():
    result = await DatabaseHealthCheck.check_connection()
    print(result)
asyncio.run(check())
"
```

---

## 🔑 Получение API ключей

### Telegram Bot Token:
1. Найдите @BotFather в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям
4. Получите токен вида: `1234567890:ABCdefGhIJklmNOPqrsTUVwxyz`

### Ваш Telegram ID:
1. Найдите @userinfobot в Telegram
2. Отправьте `/start`
3. Скопируйте ваш ID

### YouTube API (опционально):
1. Перейдите в Google Cloud Console
2. Создайте проект
3. Включите YouTube Data API v3
4. Создайте API ключ

---

## 📞 Поддержка

Если что-то не работает:

1. **Проверьте логи** - они содержат детальную информацию об ошибках
2. **Проверьте .env файл** - убедитесь что все токены правильные  
3. **Проверьте БД** - убедитесь что PostgreSQL запущен
4. **Проверьте сеть** - бот должен иметь доступ к интернету

**Часто помогает:**
```bash
# Полная переустановка зависимостей
pip uninstall -r requirements.txt -y
pip install -r requirements.txt

,

# Пересоздание БД
dropdb videobot && createdb videobot
python migrate.py --mode=direct
```# videobot-pro
# videobot-pro
