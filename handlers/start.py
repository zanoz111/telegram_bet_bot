"""
Обработчик команды /start и главного меню
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import is_allowed_player


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    welcome_text = f"""
Привет, {user.first_name}! 👋

Это бот для пари между Inzaaa и TROOLZ.

📋 *Как это работает:*

1. *Создание пари*: Maker создает линию (матч, коэффициенты, сумма)
2. *Принятие пари*: Taker выбирает сторону
3. *Результат*: Любой из игроков проставляет результат

Используй кнопки ниже для навигации:
    """
    
    keyboard = [
        [
            InlineKeyboardButton("➕ Создать пари", callback_data="menu_create_bet"),
            InlineKeyboardButton("📌 Актуальные пари", callback_data="menu_active_bets")
        ],
        [
            InlineKeyboardButton("🗓 Пари за сутки", callback_data="menu_bets_24h"),
            InlineKeyboardButton("📊 Статистика", callback_data="menu_statistics")
        ],
        [
            InlineKeyboardButton("♻️ Сброс статистики", callback_data="menu_reset_stats")
        ],
        [
            InlineKeyboardButton("🐕 Пнуть пса", callback_data="menu_kick_dog")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
