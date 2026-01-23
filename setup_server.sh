#!/bin/bash

# Скрипт для быстрой установки бота на сервере
# Использование: bash setup_server.sh

set -e

echo "🚀 Начало установки Telegram Bet Bot..."

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка что скрипт запущен не от root
if [ "$EUID" -eq 0 ]; then 
   echo "❌ Не запускайте скрипт от root!"
   exit 1
fi

# Обновление системы
echo -e "${YELLOW}📦 Обновление системы...${NC}"
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
echo -e "${YELLOW}📦 Установка Python, pip, git...${NC}"
sudo apt install python3 python3-pip python3-venv git screen -y

# Создание виртуального окружения
echo -e "${YELLOW}🐍 Создание виртуального окружения...${NC}"
python3 -m venv venv

# Активация и установка зависимостей
echo -e "${YELLOW}📚 Установка зависимостей...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Создание .env файла если его нет
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚙️  Создание .env файла...${NC}"
    read -p "Введите BOT_TOKEN: " bot_token
    read -p "Использовать TEST_MODE? (true/false): " test_mode
    
    cat > .env << EOF
BOT_TOKEN=$bot_token
TEST_MODE=$test_mode
EOF
    echo -e "${GREEN}✅ .env файл создан${NC}"
else
    echo -e "${GREEN}✅ .env файл уже существует${NC}"
fi

# Настройка systemd service
echo -e "${YELLOW}🔧 Настройка systemd service...${NC}"
CURRENT_USER=$(whoami)
SERVICE_FILE="/etc/systemd/system/telegram-bot.service"

# Замена YOUR_USERNAME на текущего пользователя в service файле
sed "s/YOUR_USERNAME/$CURRENT_USER/g" telegram-bot.service | sudo tee $SERVICE_FILE > /dev/null

# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable telegram-bot

echo -e "${GREEN}✅ Установка завершена!${NC}"
echo ""
echo "Для запуска бота выполните:"
echo "  sudo systemctl start telegram-bot"
echo ""
echo "Для проверки статуса:"
echo "  sudo systemctl status telegram-bot"
echo ""
echo "Для просмотра логов:"
echo "  sudo journalctl -u telegram-bot -f"
