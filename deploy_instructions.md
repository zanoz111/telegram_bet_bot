# Инструкции по деплою Telegram Bet Bot

## 1. Push кода на GitHub

После создания репозитория на GitHub выполните:

```bash
# Замените YOUR_USERNAME на ваш GitHub username
git remote add origin https://github.com/YOUR_USERNAME/telegram_bet_bot.git
git branch -M main
git push -u origin main --tags
```

## 2. Подключение к виртуальному серверу

Подключитесь к вашему серверу через SSH:

```bash
ssh user@your_server_ip
```

## 3. Установка необходимых пакетов на сервере

```bash
# Обновление системы (для Ubuntu/Debian)
sudo apt update && sudo apt upgrade -y

# Установка Python и pip
sudo apt install python3 python3-pip python3-venv -y

# Установка git
sudo apt install git -y
```

## 4. Клонирование репозитория на сервер

```bash
# Перейти в домашнюю директорию
cd ~

# Клонировать репозиторий (замените YOUR_USERNAME на свой)
git clone https://github.com/YOUR_USERNAME/telegram_bet_bot.git

# Перейти в папку проекта
cd telegram_bet_bot
```

## 5. Создание виртуального окружения и установка зависимостей

```bash
# Создать виртуальное окружение
python3 -m venv venv

# Активировать виртуальное окружение
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
```

## 6. Настройка переменных окружения

```bash
# Создать файл .env
nano .env
```

Добавьте в файл:
```
BOT_TOKEN=ваш_токен_бота
TEST_MODE=false
```

Сохраните (Ctrl+O, Enter, Ctrl+X)

## 7. Запуск бота

### Вариант A: Простой запуск (для тестирования)

```bash
python bot.py
```

### Вариант B: Запуск в фоне с помощью screen

```bash
# Установить screen
sudo apt install screen -y

# Создать новую screen сессию
screen -S telegram_bot

# Активировать venv и запустить бота
source venv/bin/activate
python bot.py

# Отсоединиться от screen: Ctrl+A, затем D
```

Для возврата к боту:
```bash
screen -r telegram_bot
```

### Вариант C: Запуск как systemd service (рекомендуется для production)

Создайте service файл:
```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

Добавьте:
```ini
[Unit]
Description=Telegram Bet Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/telegram_bet_bot
Environment="PATH=/home/YOUR_USERNAME/telegram_bet_bot/venv/bin"
ExecStart=/home/YOUR_USERNAME/telegram_bet_bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Замените YOUR_USERNAME на ваше имя пользователя на сервере.

Запустите service:
```bash
# Перезагрузить systemd
sudo systemctl daemon-reload

# Включить автозапуск
sudo systemctl enable telegram-bot

# Запустить бота
sudo systemctl start telegram-bot

# Проверить статус
sudo systemctl status telegram-bot

# Посмотреть логи
sudo journalctl -u telegram-bot -f
```

## 8. Обновление бота на сервере

Когда вы внесёте изменения локально и запушите на GitHub:

```bash
# На сервере
cd ~/telegram_bet_bot
git pull origin main
sudo systemctl restart telegram-bot
```

## 9. Полезные команды

```bash
# Остановить бота
sudo systemctl stop telegram-bot

# Перезапустить бота
sudo systemctl restart telegram-bot

# Посмотреть логи
sudo journalctl -u telegram-bot -n 50

# Посмотреть логи в реальном времени
sudo journalctl -u telegram-bot -f
```

## 10. Безопасность

- ✅ Убедитесь, что `.env` файл НЕ попадает в git (уже в .gitignore)
- ✅ Используйте strong passwords для сервера
- ✅ Настройте firewall на сервере
- ✅ Регулярно обновляйте систему

## Troubleshooting

### Бот не запускается
```bash
# Проверить логи
sudo journalctl -u telegram-bot -n 100

# Проверить что venv активирован
source venv/bin/activate
which python  # должно показать путь к python в venv

# Проверить зависимости
pip list
```

### База данных не создаётся
```bash
# Проверить права на папку
ls -la
chmod 755 ~/telegram_bet_bot
```
