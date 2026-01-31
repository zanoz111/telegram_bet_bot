"""
Основной файл Telegram бота для пари между двумя игроками
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from handlers.start import start_handler
from handlers.bet_handlers import (
    create_bet_handler,
    bet_wizard_handler,
    callback_handler
)
from database.db import init_db

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)


async def post_init(application: Application) -> None:
    """Инициализация после запуска бота"""
    # Устанавливаем команды бота для меню
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("create_match", "Создать пари"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Команды бота установлены")


def main():
    """Главная функция для запуска бота"""
    # Инициализация базы данных
    init_db()
    
    # Получение токена из переменной окружения
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    TOKEN = os.getenv('BOT_TOKEN')
    
    if not TOKEN:
        raise ValueError("BOT_TOKEN не найден! Создайте файл .env с BOT_TOKEN=your_token")
    
    # Создание приложения
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("create_match", create_bet_handler))  # Для совместимости
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bet_wizard_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запуск бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
