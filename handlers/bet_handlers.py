"""
Обработчики для работы с пари
"""
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.db import (
    create_bet, update_bet_step2, update_bet_step3, get_bet, 
    get_active_bets, get_bets_last_24h, take_bet, set_bet_result,
    cancel_bet, update_bet_name, change_bet_result
)
from models.bet import Bet, STATUS_DRAFT, STATUS_OPEN, STATUS_TAKEN
from config import is_allowed_player, get_other_player, get_taker_user_id, PLAYER_INZAAA_USERNAME, PLAYER_TROOLZ_USERNAME
from constants import PLAYERS, BET_NAMES
from datetime import datetime


# Хранилище временных данных для визарда
user_states = {}  # {user_id: {'action': 'step0'|'step1'|'step2'|'step3', 'bet_id': int, 'bet_name': str, 'playerA': str, 'playerB': str, 'oddsA': float, 'oddsB': float, 'message_id': int}}


def format_money(amount, signed=False):
    """Форматирование суммы без копеек"""
    if signed:
        return f"{amount:+.0f} ₽"
    return f"{amount:.0f} ₽"


def build_player_keyboard(selected_player=None):
    """Создание клавиатуры выбора игроков с подсветкой выбранного"""
    keyboard = []
    for i in range(0, len(PLAYERS), 2):
        row = []
        name = PLAYERS[i]
        label = f"✅ {name}" if name == selected_player else name
        row.append(InlineKeyboardButton(label, callback_data=f"player_{name}"))
        if i + 1 < len(PLAYERS):
            name2 = PLAYERS[i + 1]
            label2 = f"✅ {name2}" if name2 == selected_player else name2
            row.append(InlineKeyboardButton(label2, callback_data=f"player_{name2}"))
        keyboard.append(row)
    return keyboard


def build_odds_keyboard(bet_id, playerA, playerB, selected_player=None):
    """Клавиатура выбора игрока и процента для шага 2"""
    keyboard = []
    
    # Кнопки выбора игрока
    labelA = f"✅ {playerA}" if selected_player == 'A' else playerA
    labelB = f"✅ {playerB}" if selected_player == 'B' else playerB
    keyboard.append([
        InlineKeyboardButton(labelA, callback_data=f"op_{bet_id}_A"),
        InlineKeyboardButton(labelB, callback_data=f"op_{bet_id}_B")
    ])
    
    # Кнопки процентов (шаг 5)
    percentages = list(range(5, 100, 5))  # 5, 10, 15, ... 95
    for i in range(0, len(percentages), 5):
        row = []
        for pct in percentages[i:i+5]:
            row.append(InlineKeyboardButton(f"{pct}%", callback_data=f"opct_{bet_id}_{pct}"))
        keyboard.append(row)
    
    return keyboard


async def create_bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик создания пари (шаг 0 - название пари)"""
    user = update.effective_user
    
    # Проверка доступа
    if not is_allowed_player(user.username):
        text = "❌ В пари могут играть только @Inzaaa и @TROOLZ"
        if update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
            return
        else:
            await update.message.reply_text(text)
            return
    
    # Удаляем сообщение пользователя, если это команда
    if update.message:
        try:
            await update.message.delete()
        except:
            pass
    
    # Создаем кнопки с готовыми названиями
    keyboard = [[InlineKeyboardButton(name, callback_data=f"betname_{name}")] for name in BET_NAMES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Обрабатываем как callback_query или message
    if update.callback_query:
        # Если это callback_query, редактируем существующее сообщение
        await update.callback_query.edit_message_text(
            "Шаг 0/4 — Название пари\n\n"
            "Введи название пари или выбери из кнопок:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        msg = update.callback_query.message
    else:
        # Если это обычное сообщение
        msg = await update.message.reply_text(
            "Шаг 0/4 — Название пари\n\n"
            "Введи название пари или выбери из кнопок:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    # Сохраняем состояние
    user_states[user.id] = {
        'action': 'step0',
        'message_id': msg.message_id
    }


async def bet_wizard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик визарда создания пари"""
    user = update.effective_user
    text = update.message.text.strip()
    
    if user.id not in user_states:
        try:
            await update.message.delete()
        except:
            pass
        return
    
    state = user_states[user.id]
    
    if state['action'] == 'step0':
        # Шаг 0: Название пари
        bet_name = text
        
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass
        
        # Создаем кнопки с игроками
        keyboard = build_player_keyboard()
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Переходим к шагу 1 - выбор матча
        msg = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=state.get('message_id'),
            text=f"Шаг 1/4 — Матч\n\n"
                 f"Название: {bet_name}\n\n"
                 f"Введи матч в формате:\n"
                 f"`inz vs troolz` или `inz troolz`\n\n"
                 f"Допустимые разделители: `vs`, пробел\n\n"
                 f"Или выбери игроков из кнопок:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        user_states[user.id] = {
            'action': 'step1',
            'bet_name': bet_name,
            'message_id': msg.message_id,
            'selected_playerA': None,  # Для выбора через кнопки
            'selected_playerB': None
        }
    
    elif state['action'] == 'step1':
        # Парсим матч - поддерживаем разделители "vs" и пробел
        match_pattern_vs = r'^(.+?)\s+vs\s+(.+?)$'
        match_pattern_space = r'^(\S+)\s+(\S+)$'
        
        match = re.match(match_pattern_vs, text, re.IGNORECASE)
        if not match:
            match = re.match(match_pattern_space, text, re.IGNORECASE)
        
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass
        
        if not match:
            # Воссоздаем кнопки с игроками
            keyboard = build_player_keyboard()
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=state.get('message_id'),
                text="❌ Неверный формат! Используй формат:\n"
                     "`команда1 vs команда2` или `команда1 команда2`\n\n"
                     "Например: `inz vs troolz` или `inz troolz`\n\n"
                     "Или выбери игроков из кнопок:",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return
        
        playerA = match.group(1).strip()
        playerB = match.group(2).strip()
        
        # Создаем пари в статусе DRAFT
        new_bet = Bet(
            id=None,
            maker_user_id=user.id,
            maker_username=user.username or user.first_name,
            taker_user_id=None,
            taker_username=get_other_player(user.username),
            bet_name=state.get('bet_name'),
            playerA_name=playerA,
            playerB_name=playerB,
            oddsA=None,
            oddsB=None,
            stake=None,
            status=STATUS_DRAFT,
            taker_side=None,
            result=None,
            created_at=datetime.now()
        )
        
        bet_id = create_bet(new_bet)
        
        # Клавиатура выбора игрока + процент
        keyboard = build_odds_keyboard(bet_id, playerA, playerB)
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Обновляем сообщение для шага 2
        msg = await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=state.get('message_id'),
            text=f"Шаг 2/4 — Проценты и коэффициенты\n\n"
                 f"Название: {state.get('bet_name')}\n"
                 f"Матч: {playerA} vs {playerB}\n\n"
                 f"Выбери игрока и его процент на победу:\n"
                 f"Или введи вручную: `{playerA} 60`",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        user_states[user.id] = {
            'action': 'step2',
            'bet_id': bet_id,
            'bet_name': state.get('bet_name'),
            'playerA': playerA,
            'playerB': playerB,
            'message_id': msg.message_id,
            'selected_odds_player': None
        }
    
    elif state['action'] == 'step2' or state['action'] == 'edit_step2':
        # Парсим формат "Имя процент"
        # Заменяем запятые на точки
        text = text.replace(',', '.')
        
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass
        
        # Парсим формат "Имя процент"
        percent_pattern = r'^(.+?)\s+(\d+\.?\d*)$'
        match = re.match(percent_pattern, text.strip())
        
        if not match:
            keyboard = build_odds_keyboard(state['bet_id'], state['playerA'], state['playerB'], state.get('selected_odds_player'))
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=state.get('message_id'),
                text="❌ Неверный формат! Введи имя игрока и процент:\n"
                     f"`{state['playerA']} процент` или `{state['playerB']} процент`\n\n"
                     f"Пример: `{state['playerA']} 60`",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return
        
        player_name = match.group(1).strip()
        try:
            percent = float(match.group(2))
            
            if percent <= 0 or percent >= 100:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=state.get('message_id'),
                    text="❌ Процент должен быть от 0 до 100!"
                )
                return
            
            # Определяем, для какого игрока указан процент
            playerA = state['playerA']
            playerB = state['playerB']
            
            if player_name.lower() == playerA.lower():
                percentA = percent
                percentB = 100 - percent
            elif player_name.lower() == playerB.lower():
                percentB = percent
                percentA = 100 - percent
            else:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=state.get('message_id'),
                    text=f"❌ Неизвестное имя игрока!\n"
                         f"Используй: `{playerA}` или `{playerB}`",
                    parse_mode='Markdown'
                )
                return
            
            # Вычисляем коэффициенты: коэф = 100 / процент
            oddsA = round(100 / percentA, 2)
            oddsB = round(100 / percentB, 2)
            
            # Обновляем коэффициенты
            update_bet_step2(state['bet_id'], oddsA, oddsB)
            
            # Создаем клавиатуру с готовыми суммами
            keyboard = [
                [
                    InlineKeyboardButton("500 ₽", callback_data=f"stake_{state['bet_id']}_500"),
                    InlineKeyboardButton("1000 ₽", callback_data=f"stake_{state['bet_id']}_1000")
                ],
                [
                    InlineKeyboardButton("1500 ₽", callback_data=f"stake_{state['bet_id']}_1500"),
                    InlineKeyboardButton("2000 ₽", callback_data=f"stake_{state['bet_id']}_2000")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение для шага 3
            msg = await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=state.get('message_id'),
                text=f"Шаг 3/4 — Сумма ставки\n\n"
                     f"Название: {state.get('bet_name')}\n"
                     f"Матч: {state['playerA']} vs {state['playerB']}\n\n"
                     f"Проценты и коэффициенты:\n"
                     f"{state['playerA']} — {percentA:.0f}% → `{oddsA:.2f}`\n"
                     f"{state['playerB']} — {percentB:.0f}% → `{oddsB:.2f}`\n\n"
                     f"Введи сумму ставки (₽) или выбери из кнопок:",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            # Определяем следующий шаг - step3 или edit_step3
            next_action = 'edit_step3' if state['action'] == 'edit_step2' else 'step3'
            
            user_states[user.id] = {
                'action': next_action,
                'bet_id': state['bet_id'],
                'bet_name': state.get('bet_name'),
                'playerA': state['playerA'],
                'playerB': state['playerB'],
                'oddsA': oddsA,
                'oddsB': oddsB,
                'percentA': percentA,
                'percentB': percentB,
                'message_id': msg.message_id
            }
            
        except ValueError:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=state.get('message_id'),
                text="❌ Ошибка! Введи корректные числа для коэффициентов."
            )
    
    elif state['action'] == 'step3' or state['action'] == 'edit_step3':
        # Парсим сумму ставки
        try:
            # Заменяем запятые на точки
            text = text.replace(',', '.')
            stake = round(float(text), 2)
            
            # Удаляем сообщение пользователя
            try:
                await update.message.delete()
            except:
                pass
            
            if stake <= 0:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=state.get('message_id'),
                    text="❌ Сумма ставки должна быть положительным числом!"
                )
                return
            
            # Обновляем данные в зависимости от режима
            if state['action'] == 'edit_step3':
                # При редактировании просто обновляем коэффициенты и сумму
                update_bet_step2(state['bet_id'], state['oddsA'], state['oddsB'])
                from database.db import get_connection
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('UPDATE bets SET stake = ? WHERE id = ?', (stake, state['bet_id']))
                conn.commit()
                conn.close()
            else:
                # При создании публикуем пари
                update_bet_step3(state['bet_id'], stake)
            
            # Получаем пари для отображения
            bet = get_bet(state['bet_id'])
            
            # Удаляем состояние пользователя
            del user_states[user.id]
            
            # Формируем карточку пари
            card_text = format_bet_card(bet)
            
            keyboard = [
                [
                    InlineKeyboardButton(f"🟢 За {bet.playerA_name} ({bet.oddsA:.2f})", callback_data=f"side_{bet.id}_A"),
                ],
                [
                    InlineKeyboardButton(f"🔵 За {bet.playerB_name} ({bet.oddsB:.2f})", callback_data=f"side_{bet.id}_B"),
                ],
                [
                    InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{bet.id}"),
                    InlineKeyboardButton("🗑 Отменить", callback_data=f"cancel_{bet.id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=state.get('message_id'),
                text=card_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except ValueError:
            try:
                await update.message.delete()
            except:
                pass
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=state.get('message_id'),
                text="❌ Ошибка! Введи корректное число для суммы ставки."
            )


def format_bet_card(bet: Bet) -> str:
    """Форматирование карточки пари"""
    status_emoji = {
        'DRAFT': '📝',
        'OPEN': '📣',
        'TAKEN': '✅',
        'FINISHED': '🏁',
        'CANCELED': '❌'
    }.get(bet.status, '❓')
    
    # Заголовок с форматом матча
    header = f"{status_emoji} Пари #{bet.id}"
    if bet.bet_name:
        header += f" • {bet.bet_name}"
    text = header + "\n\n"
    
    # Игроки с кэфами и бэкерами
    if bet.oddsA and bet.oddsB:
        if bet.taker_side:
            # Показываем кто на какой стороне прямо на кэфах
            playerA_backer = bet.taker_username if bet.taker_side == 'A' else bet.maker_username
            playerB_backer = bet.taker_username if bet.taker_side == 'B' else bet.maker_username
            text += f"{bet.playerA_name} — `{bet.oddsA:.2f}` ({playerA_backer}) | {bet.playerB_name} — `{bet.oddsB:.2f}` ({playerB_backer})\n"
        else:
            text += f"{bet.playerA_name} — `{bet.oddsA:.2f}` | {bet.playerB_name} — `{bet.oddsB:.2f}`\n"
    else:
        text += f"{bet.playerA_name} vs {bet.playerB_name}\n"
    
    if bet.stake:
        text += f"Сумма: {format_money(bet.stake)}\n"
    
    # Создатель (без тега — тегаем только когда нужно действие)
    text += f"\nСоздал: {bet.maker_username}\n"
    
    if bet.status == 'OPEN':
        # Тегаем только taker — ему нужно действовать
        text += f"\n👉 @{bet.taker_username}, выбери сторону"
    elif bet.status == 'TAKEN':
        text += f"\nОжидает результат"
    elif bet.status == 'FINISHED':
        result_text = bet.playerA_name if bet.result == 'A' else (bet.playerB_name if bet.result == 'B' else 'VOID')
        
        text += f"\n✅ Пари завершено\n"
        text += f"Победил: {result_text}\n\n"
        text += f"Итог:\n"
        text += f"{bet.maker_username} {format_money(bet.maker_win, signed=True)}\n"
        text += f"{bet.taker_username} {format_money(bet.taker_win, signed=True)}\n"
    
    return text


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback-запросов"""
    query = update.callback_query
    user = update.effective_user
    data = query.data
    
    if data.startswith('betname_'):
        # Выбор названия пари через кнопку
        bet_name = data.split('_', 1)[1]
        
        if user.id not in user_states or user_states[user.id]['action'] != 'step0':
            await query.answer("❌ Сессия создания пари истекла. Начните заново.", show_alert=True)
            return
        
        # Создаем кнопки с игроками
        keyboard = build_player_keyboard()
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Переходим к шагу 1
        await query.edit_message_text(
            f"Шаг 1/4 — Матч\n\n"
            f"Название: {bet_name}\n\n"
            f"Введи матч в формате:\n"
            f"`inz vs troolz` или `inz troolz`\n\n"
            f"Допустимые разделители: `vs`, пробел\n\n"
            f"Или выбери игроков из кнопок:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        user_states[user.id] = {
            'action': 'step1',
            'bet_name': bet_name,
            'message_id': query.message.message_id,
            'selected_playerA': None,
            'selected_playerB': None
        }
    
    elif data.startswith('player_'):
        # Выбор игрока через кнопку
        player_name = data.split('_', 1)[1]
        
        if user.id not in user_states or user_states[user.id]['action'] != 'step1':
            await query.answer("❌ Сессия создания пари истекла. Начните заново.", show_alert=True)
            return
        
        state = user_states[user.id]
        
        # Если первый игрок еще не выбран
        if state.get('selected_playerA') is None:
            state['selected_playerA'] = player_name
            await query.answer(f"Выбран первый игрок: {player_name}")
            
            # Обновляем сообщение — подсвечиваем выбранного игрока
            keyboard = build_player_keyboard(selected_player=player_name)
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"Шаг 1/4 — Матч\n\n"
                f"Название: {state['bet_name']}\n\n"
                f"Первый игрок: {player_name}\n"
                f"Выбери второго игрока:",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        # Если первый игрок уже выбран, выбираем второго
        else:
            await query.answer()
            playerA = state['selected_playerA']
            playerB = player_name
            
            # Создаем пари в статусе DRAFT
            new_bet = Bet(
                id=None,
                maker_user_id=user.id,
                maker_username=user.username or user.first_name,
                taker_user_id=None,
                taker_username=get_other_player(user.username),
                bet_name=state.get('bet_name'),
                playerA_name=playerA,
                playerB_name=playerB,
                oddsA=None,
                oddsB=None,
                stake=None,
                status=STATUS_DRAFT,
                taker_side=None,
                result=None,
                created_at=datetime.now()
            )
            
            bet_id = create_bet(new_bet)
            
            # Клавиатура выбора игрока + процент
            keyboard = build_odds_keyboard(bet_id, playerA, playerB)
            reply_markup = InlineKeyboardMarkup(keyboard)
            # Переходим к шагу 2
            msg = await query.edit_message_text(
                f"Шаг 2/4 — Проценты и коэффициенты\n\n"
                f"Название: {state.get('bet_name')}\n"
                f"Матч: {playerA} vs {playerB}\n\n"
                f"Выбери игрока и его процент на победу:\n"
                f"Или введи вручную: `{playerA} 60`",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
            user_states[user.id] = {
                'action': 'step2',
                'bet_id': bet_id,
                'bet_name': state.get('bet_name'),
                'playerA': playerA,
                'playerB': playerB,
                'message_id': msg.message_id,
                'selected_odds_player': None
            }
    
    elif data.startswith('menu_'):
        # Обработка меню
        await query.answer()
        menu_action = data.split('_', 1)[1]
        
        if menu_action == 'create_bet':
            await create_bet_handler(update, context)
        elif menu_action == 'active_bets':
            await view_active_bets_handler(update, context)
        elif menu_action == 'bets_24h':
            await view_bets_24h_handler(update, context)
        elif menu_action == 'statistics':
            await show_statistics_handler(update, context)
        elif menu_action == 'reset_stats':
            await reset_statistics_handler(update, context)
        elif menu_action == 'kick_dog':
            await handle_kick_dog(update, context)
        elif menu_action == 'back':
            from handlers.start import start_handler
            await start_handler(update, context)
    
    elif data.startswith('take_'):
        # Принятие пари
        bet_id = int(data.split('_')[1])
        await handle_take_bet(update, context, bet_id)
    
    elif data.startswith('side_'):
        # Выбор стороны        
        parts = data.split('_')
        
        # Формат: side_{bet_id}_{side}
        if len(parts) >= 3:
            bet_id = int(parts[1])
            side = parts[2]  # 'A' или 'B'
        else:
            await query.answer("❌ Ошибка формата callback", show_alert=True)
            return
        
        try:
            await handle_select_side(update, context, bet_id, side)
        except Exception as e:
            raise
    
    elif data.startswith('result_menu_'):
        # Меню выбора результата
        await query.answer()
        bet_id = int(data.split('_')[2])
        await show_result_menu(update, context, bet_id)
    
    elif data.startswith('result_'):
        # Проставление результата
        await query.answer()
        parts = data.split('_')
        bet_id = int(parts[1])
        result = parts[2]  # 'A', 'B', 'VOID'
        await handle_set_result(update, context, bet_id, result)
    
    elif data.startswith('noop_'):
        # Кнопка-заголовок, ничего не делает
        await query.answer()
        return
    
    elif data == 'reset_confirm':
        # Подтверждение сброса статистики
        await query.answer()
        from database.db import reset_statistics
        reset_statistics()
        await query.edit_message_text(
            "✅ Статистика успешно сброшена!\n\n"
            "Период начинается с текущей даты."
        )
    
    elif data.startswith('stats_'):
        # Фильтр статистики по периоду
        await query.answer()
        period = data.split('_')[1]
        await show_statistics_by_period(update, context, period)
    
    elif data.startswith('cancel_'):
        # Отмена пари
        await query.answer()
        bet_id = int(data.split('_')[1])
        await handle_cancel_bet(update, context, bet_id)
    
    elif data.startswith('stake_'):
        # Выбор готовой суммы ставки
        await query.answer()
        parts = data.split('_')
        bet_id = int(parts[1])
        stake = float(parts[2])
        await handle_stake_selection(update, context, bet_id, stake)
    
    elif data.startswith('op_'):
        # Выбор игрока для процента на шаге 2
        await query.answer()
        parts = data.split('_')
        bet_id = int(parts[1])
        side = parts[2]  # 'A' or 'B'
        
        if user.id not in user_states or user_states[user.id]['action'] not in ('step2', 'edit_step2'):
            await query.answer("❌ Сессия создания пари истекла", show_alert=True)
            return
        
        state = user_states[user.id]
        state['selected_odds_player'] = side
        
        # Перестраиваем клавиатуру с подсветкой выбранного игрока
        keyboard = build_odds_keyboard(bet_id, state['playerA'], state['playerB'], selected_player=side)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        selected_name = state['playerA'] if side == 'A' else state['playerB']
        
        await query.edit_message_text(
            f"Шаг 2/4 — Проценты и коэффициенты\n\n"
            f"Название: {state.get('bet_name')}\n"
            f"Матч: {state['playerA']} vs {state['playerB']}\n\n"
            f"Выбран: *{selected_name}*\n"
            f"Выбери процент на победу или введи вручную: `{selected_name} 60`",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif data.startswith('opct_'):
        # Выбор процента для выбранного игрока на шаге 2
        parts = data.split('_')
        bet_id = int(parts[1])
        pct = int(parts[2])
        
        if user.id not in user_states or user_states[user.id]['action'] not in ('step2', 'edit_step2'):
            await query.answer("❌ Сессия создания пари истекла", show_alert=True)
            return
        
        state = user_states[user.id]
        
        if not state.get('selected_odds_player'):
            await query.answer("⚠️ Сначала выбери игрока!", show_alert=True)
            return
        
        await query.answer()
        
        # Рассчитываем проценты и коэффициенты
        selected_side = state['selected_odds_player']
        if selected_side == 'A':
            percentA = pct
            percentB = 100 - pct
        else:
            percentB = pct
            percentA = 100 - pct
        
        oddsA = round(100 / percentA, 2)
        oddsB = round(100 / percentB, 2)
        
        # Обновляем в БД
        update_bet_step2(state['bet_id'], oddsA, oddsB)
        
        # Клавиатура шага 3
        keyboard = [
            [
                InlineKeyboardButton("500 ₽", callback_data=f"stake_{state['bet_id']}_500"),
                InlineKeyboardButton("1000 ₽", callback_data=f"stake_{state['bet_id']}_1000")
            ],
            [
                InlineKeyboardButton("1500 ₽", callback_data=f"stake_{state['bet_id']}_1500"),
                InlineKeyboardButton("2000 ₽", callback_data=f"stake_{state['bet_id']}_2000")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = await query.edit_message_text(
            f"Шаг 3/4 — Сумма ставки\n\n"
            f"Название: {state.get('bet_name')}\n"
            f"{state['playerA']} — {percentA:.0f}% → `{oddsA:.2f}`\n"
            f"{state['playerB']} — {percentB:.0f}% → `{oddsB:.2f}`\n\n"
            f"Введи сумму ставки (₽) или выбери из кнопок:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        next_action = 'edit_step3' if state['action'] == 'edit_step2' else 'step3'
        
        user_states[user.id] = {
            'action': next_action,
            'bet_id': state['bet_id'],
            'bet_name': state.get('bet_name'),
            'playerA': state['playerA'],
            'playerB': state['playerB'],
            'oddsA': oddsA,
            'oddsB': oddsB,
            'percentA': percentA,
            'percentB': percentB,
            'message_id': msg.message_id
        }
    
    elif data.startswith('chresult_menu_'):
        # Меню изменения результата
        await query.answer()
        bet_id = int(data.split('_')[2])
        await show_change_result_menu(update, context, bet_id)
    
    elif data.startswith('chresult_'):
        # Изменение результата
        await query.answer()
        parts = data.split('_')
        bet_id = int(parts[1])
        new_result = parts[2]
        await handle_change_result(update, context, bet_id, new_result)
    
    elif data.startswith('edit_'):
        # Редактирование пари
        bet_id = int(data.split('_')[1])
        await handle_edit_bet(update, context, bet_id)


async def handle_take_bet(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int):
    """Обработка принятия пари"""
    query = update.callback_query
    user = update.effective_user
    
    bet = get_bet(bet_id)
    if not bet:
        await query.edit_message_text("❌ Пари не найдено!")
        return
    
    # Проверка доступа
    if not is_allowed_player(user.username):
        await query.answer("❌ Выбор стороны доступен только второму игроку", show_alert=True)
        return
    
    # Проверка, что пользователь - taker
    from config import TEST_MODE
    if not TEST_MODE and (not user.username or user.username.lower() != bet.taker_username.lower()):
        await query.answer("❌ Выбор стороны доступен только второму игроку", show_alert=True)
        return
    
    if bet.status != STATUS_OPEN:
        await query.answer("❌ Пари уже принято или отменено", show_alert=True)
        return
    
    # Показываем кнопки выбора стороны
    keyboard = [
        [
            InlineKeyboardButton(
                f"🟢 За {bet.playerA_name} ({bet.oddsA:.2f})",
                callback_data=f"side_{bet_id}_A"
            )
        ],
        [
            InlineKeyboardButton(
                f"🔵 За {bet.playerB_name} ({bet.oddsB:.2f})",
                callback_data=f"side_{bet_id}_B"
            )
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Выбери сторону для ставки:\n\n"
        f"*{bet.playerA_name}* vs *{bet.playerB_name}*\n"
        f"Коэффициенты: `{bet.oddsA:.2f}` / `{bet.oddsB:.2f}`\n"
        f"Сумма: {format_money(bet.stake)}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_select_side(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int, side: str):
    """Обработка выбора стороны"""
    query = update.callback_query
    user = update.effective_user
    
    bet = get_bet(bet_id)
    if not bet:
        await query.edit_message_text("❌ Пари не найдено!")
        return
    
    # Проверка доступа
    # В тестовом режиме разрешаем maker также быть taker
    from config import TEST_MODE
    if not TEST_MODE and (not user.username or user.username.lower() != bet.taker_username.lower()):
        await query.answer("❌ Выбор стороны доступен только второму игроку", show_alert=True)
        return
    
    # Проверка статуса
    if bet.status != STATUS_OPEN:
        await query.answer("❌ Пари уже принято или отменено", show_alert=True)
        return
    
    # Принимаем пари
    from database.db import update_taker_user_id
    update_taker_user_id(bet_id, user.id)
    take_bet(bet_id, user.id, side)
    
    # Обновляем пари
    bet = get_bet(bet_id)
    
    # Формируем карточку
    card_text = format_bet_card(bet)
    
    keyboard = [
        [
            InlineKeyboardButton("🏁 Указать результат", callback_data=f"result_menu_{bet_id}"),
        ],
        [
            InlineKeyboardButton("📌 В актуальные", callback_data="menu_active_bets")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(card_text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        raise


async def show_result_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int):
    """Показ меню выбора результата"""
    query = update.callback_query
    user = update.effective_user
    
    bet = get_bet(bet_id)
    if not bet:
        await query.edit_message_text("❌ Пари не найдено!")
        return
    
    # Проверка доступа
    if not is_allowed_player(user.username):
        await query.answer("❌ Только игроки могут проставлять результат", show_alert=True)
        return
    
    if bet.status != STATUS_TAKEN:
        await query.answer("❌ Пари еще не принято", show_alert=True)
        return
    
    keyboard = [
        [
            InlineKeyboardButton(f"🏆 Победил {bet.playerA_name}", callback_data=f"result_{bet_id}_A")
        ],
        [
            InlineKeyboardButton(f"🏆 Победил {bet.playerB_name}", callback_data=f"result_{bet_id}_B")
        ],
        [
            InlineKeyboardButton("🚫 VOID (отмена матча)", callback_data=f"result_{bet_id}_VOID")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)    
    # Экранируем специальные markdown-символы в именах
    def escape_markdown(text):
        """Экранирует специальные символы для Markdown"""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    playerA_escaped = escape_markdown(bet.playerA_name)
    playerB_escaped = escape_markdown(bet.playerB_name)
    taker_choice_escaped = escape_markdown(bet.playerA_name if bet.taker_side == 'A' else bet.playerB_name)
    
    try:
        await query.edit_message_text(
            f"Выбери результат пари:\n\n"
            f"*{playerA_escaped}* vs *{playerB_escaped}*\n"
            f"Выбрано: {taker_choice_escaped}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        raise


async def handle_set_result(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int, result: str):
    """Обработка проставления результата"""
    query = update.callback_query
    user = update.effective_user
    
    bet = get_bet(bet_id)
    if not bet:
        await query.edit_message_text("❌ Пари не найдено!")
        return
    
    # Проверка доступа
    if not is_allowed_player(user.username):
        await query.answer("❌ Только игроки могут проставлять результат", show_alert=True)
        return
    
    if bet.status != STATUS_TAKEN:
        await query.answer("❌ Пари еще не принято", show_alert=True)
        return
    
    # Устанавливаем результат
    set_bet_result(bet_id, result)
    
    # Обновляем пари
    bet = get_bet(bet_id)
    
    # Формируем карточку
    card_text = format_bet_card(bet)
    
    await query.edit_message_text(card_text, parse_mode='Markdown')


async def show_statistics_by_period(update: Update, context: ContextTypes.DEFAULT_TYPE, period: str):
    """Показ статистики за период"""
    from database.db import get_all_statistics
    from datetime import datetime, timedelta
    
    now = datetime.now()
    start_date = None
    
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_text = "Сегодня"
    elif period == '7d':
        start_date = now - timedelta(days=7)
        period_text = "7 дней"
    elif period == '30d':
        start_date = now - timedelta(days=30)
        period_text = "30 дней"
    else:
        period_text = "Все время"
    
    stats = get_all_statistics(start_date, now)
    
    text = f"📊 *Статистика*\n\n"
    text += f"Период: {period_text}\n\n"
    
    if start_date:
        text += f"С {start_date.strftime('%d.%m.%Y')} по {now.strftime('%d.%m.%Y')}\n\n"
    
    for username, user_stats in stats.items():
        text += f"*{username}*\n"
        text += f"Баланс: {format_money(user_stats['total_balance'], signed=True)}\n"
        text += f"Пари: {user_stats['total_bets']}\n"
        text += f"Победы: {user_stats['wins']} | Поражения: {user_stats['losses']}\n\n"
    
    keyboard = [
        [
            InlineKeyboardButton("Сегодня", callback_data="stats_today"),
            InlineKeyboardButton("7 дней", callback_data="stats_7d")
        ],
        [
            InlineKeyboardButton("30 дней", callback_data="stats_30d"),
            InlineKeyboardButton("Все время", callback_data="stats_all")
        ],
        [
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu_back")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_edit_bet(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int):
    """Обработка редактирования пари"""
    query = update.callback_query
    user = update.effective_user
    
    bet = get_bet(bet_id)
    if not bet:
        await query.edit_message_text("❌ Пари не найдено!")
        return
    
    # Проверка доступа - только maker может редактировать
    if not user.username or user.username.lower() != bet.maker_username.lower():
        await query.answer("❌ Только создатель может редактировать пари", show_alert=True)
        return
    
    # Проверка статуса - можно редактировать только OPEN пари
    if bet.status != STATUS_OPEN:
        await query.answer("❌ Можно редактировать только открытое пари", show_alert=True)
        return
    
    # Начинаем визард редактирования с шага 2 (коэффициенты)
    # Сохраняем состояние для редактирования
    user_states[user.id] = {
        'action': 'edit_step2',
        'bet_id': bet_id,
        'bet_name': bet.bet_name,
        'playerA': bet.playerA_name,
        'playerB': bet.playerB_name,
        'message_id': query.message.message_id,
        'selected_odds_player': None
    }
    
    # Показываем шаг 2 - редактирование коэффициентов
    bet_name_text = f"Название: {bet.bet_name}\n" if bet.bet_name else ""
    
    # Вычисляем текущие проценты из коэффициентов (обратная формула)
    current_percentA = round(100 / bet.oddsA, 1) if bet.oddsA else 50
    current_percentB = round(100 / bet.oddsB, 1) if bet.oddsB else 50
    
    # Кнопки выбора игрока + процент
    keyboard = build_odds_keyboard(bet_id, bet.playerA_name, bet.playerB_name)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✏️ Редактирование пари #{bet_id}\n\n"
        f"{bet_name_text}"
        f"Матч: {bet.playerA_name} vs {bet.playerB_name}\n\n"
        f"Текущие значения:\n"
        f"{bet.playerA_name} — {current_percentA:.0f}% → `{bet.oddsA:.2f}`\n"
        f"{bet.playerB_name} — {current_percentB:.0f}% → `{bet.oddsB:.2f}`\n\n"
        f"Выбери игрока и процент или введи вручную: `{bet.playerA_name} 60`",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def handle_stake_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int, stake: float):
    """Обработка выбора готовой суммы ставки"""
    query = update.callback_query
    user = update.effective_user
    
    # Проверяем, что у пользователя есть активное состояние
    if user.id not in user_states:
        await query.answer("❌ Сессия создания пари истекла. Начните заново.", show_alert=True)
        return
    
    state = user_states[user.id]
    
    # Проверяем, что мы на правильном шаге
    if state['action'] not in ['step3', 'edit_step3']:
        await query.answer("❌ Ошибка: неверный шаг", show_alert=True)
        return
    
    # Проверяем, что bet_id совпадает
    if state['bet_id'] != bet_id:
        await query.answer("❌ Ошибка: несоответствие ID пари", show_alert=True)
        return
    
    # Обновляем данные в зависимости от режима
    if state['action'] == 'edit_step3':
        # При редактировании просто обновляем коэффициенты и сумму
        update_bet_step2(state['bet_id'], state['oddsA'], state['oddsB'])
        from database.db import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE bets SET stake = ? WHERE id = ?', (stake, state['bet_id']))
        conn.commit()
        conn.close()
    else:
        # При создании публикуем пари
        update_bet_step3(state['bet_id'], stake)
    
    # Получаем пари для отображения
    bet = get_bet(state['bet_id'])
    
    # Удаляем состояние пользователя
    del user_states[user.id]
    
    # Формируем карточку пари
    card_text = format_bet_card(bet)
    
    keyboard = [
        [
            InlineKeyboardButton(f"🟢 За {bet.playerA_name} ({bet.oddsA:.2f})", callback_data=f"side_{bet.id}_A"),
        ],
        [
            InlineKeyboardButton(f"🔵 За {bet.playerB_name} ({bet.oddsB:.2f})", callback_data=f"side_{bet.id}_B"),
        ],
        [
            InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{bet.id}"),
            InlineKeyboardButton("🗑 Отменить", callback_data=f"cancel_{bet.id}")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=card_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_cancel_bet(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int):
    """Обработка отмены пари"""
    query = update.callback_query
    user = update.effective_user
    
    bet = get_bet(bet_id)
    if not bet:
        await query.edit_message_text("❌ Пари не найдено!")
        return
    
    # Проверка доступа
    if user.username.lower() != bet.maker_username.lower():
        await query.answer("❌ Только создатель может отменить пари", show_alert=True)
        return
    
    if bet.status != STATUS_OPEN:
        await query.answer("❌ Можно отменить только открытое пари", show_alert=True)
        return
    
    # Отменяем пари
    cancel_bet(bet_id)
    
    bet = get_bet(bet_id)
    card_text = format_bet_card(bet)
    
    await query.edit_message_text(card_text, parse_mode='Markdown')


async def view_active_bets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр активных пари"""
    active_bets = get_active_bets()
    
    if not active_bets:
        text = "📌 *Актуальные пари:*\n\nНет активных пари."
        if update.callback_query:
            keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="menu_back")]]
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    text = "📌 *Актуальные пари:*\n\n"
    
    for bet in active_bets:
        bet_name_text = f" • {bet.bet_name}" if bet.bet_name else ""
        text += f"#{bet.id}{bet_name_text} — {bet.playerA_name} `{bet.oddsA:.2f}` | {bet.playerB_name} `{bet.oddsB:.2f}`\n"
        text += f"Сумма: {format_money(bet.stake)}\n"
        
        # Для TAKEN пари показываем детали
        if bet.status == 'TAKEN':
            taker_choice = bet.playerA_name if bet.taker_side == 'A' else bet.playerB_name
            maker_choice = bet.playerB_name if bet.taker_side == 'A' else bet.playerA_name
            
            text += f"Ставки: {bet.maker_username} → {maker_choice} | {bet.taker_username} → {taker_choice}\n"
            text += f"Ожидает результат\n\n"
        else:
            text += f"Статус: {bet.status}\n\n"
    
    keyboard = []
    user = update.effective_user
    
    for bet in active_bets:
        if bet.status == 'TAKEN':
            bet_name_btn = f" • {bet.bet_name}" if bet.bet_name else ""
            keyboard.append([
                InlineKeyboardButton(f"🏁 Результат #{bet.id}{bet_name_btn}", callback_data=f"result_menu_{bet.id}")
            ])
        elif bet.status == 'OPEN':
            bet_name_lbl = f" • {bet.bet_name}" if bet.bet_name else ""
            # Кнопки выбора стороны для taker
            if user.username and user.username.lower() == bet.taker_username.lower():
                keyboard.append([
                    InlineKeyboardButton(f"── #{bet.id}{bet_name_lbl} выбери сторону ──", callback_data=f"noop_{bet.id}")
                ])
                keyboard.append([
                    InlineKeyboardButton(f"🟢 {bet.playerA_name} ({bet.oddsA:.2f})", callback_data=f"side_{bet.id}_A"),
                    InlineKeyboardButton(f"🔵 {bet.playerB_name} ({bet.oddsB:.2f})", callback_data=f"side_{bet.id}_B")
                ])
            
            # Кнопка отмены для maker
            if user.username and user.username.lower() == bet.maker_username.lower():
                keyboard.append([InlineKeyboardButton(f"🗑 Отменить #{bet.id}{bet_name_lbl}", callback_data=f"cancel_{bet.id}")])
    
    if not keyboard:
        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="menu_back")]]
    else:
        keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="menu_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def view_bets_24h_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр пари за сутки"""    
    bets = get_bets_last_24h()    
    if not bets:
        text = "🗓 *Пари за сутки:*\n\nНет завершенных пари за последние 24 часа."
    else:
        text = "🗓 *Пари за сутки:*\n\n"
        for bet in bets:
            result_text = bet.playerA_name if bet.result == 'A' else (bet.playerB_name if bet.result == 'B' else 'VOID')
            
            taker_choice = bet.playerA_name if bet.taker_side == 'A' else bet.playerB_name
            maker_choice = bet.playerB_name if bet.taker_side == 'A' else bet.playerA_name
            
            bet_name_text = f" • {bet.bet_name}" if bet.bet_name else ""
            text += f"#{bet.id}{bet_name_text} — {bet.playerA_name} `{bet.oddsA:.2f}` | {bet.playerB_name} `{bet.oddsB:.2f}`\n"
            text += f"Результат: {result_text}\n"
            text += f"Ставки: {bet.maker_username} → {maker_choice} | {bet.taker_username} → {taker_choice}\n"
            text += f"{bet.maker_username} {format_money(bet.maker_win, signed=True)} | {bet.taker_username} {format_money(bet.taker_win, signed=True)}\n\n"
    
    keyboard = []
    if bets:
        for bet in bets:
            keyboard.append([
                InlineKeyboardButton(f"🔄 Изменить результат #{bet.id}", callback_data=f"chresult_menu_{bet.id}")
            ])
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="menu_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_statistics_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показ статистики"""
    from database.db import get_all_statistics
    from datetime import datetime, timedelta
    
    # Показываем статистику за все время
    stats = get_all_statistics()
    
    text = "📊 *Статистика*\n\n"
    text += "Период: Все время\n\n"
    
    for username, user_stats in stats.items():
        text += f"*{username}*\n"
        text += f"Баланс: {format_money(user_stats['total_balance'], signed=True)}\n"
        text += f"Пари: {user_stats['total_bets']}\n"
        text += f"Победы: {user_stats['wins']} | Поражения: {user_stats['losses']}\n\n"
    
    keyboard = [
        [
            InlineKeyboardButton("Сегодня", callback_data="stats_today"),
            InlineKeyboardButton("7 дней", callback_data="stats_7d")
        ],
        [
            InlineKeyboardButton("30 дней", callback_data="stats_30d"),
            InlineKeyboardButton("Все время", callback_data="stats_all")
        ],
        [
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu_back")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def reset_statistics_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс статистики"""
    query = update.callback_query
    
    # Показываем подтверждение
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="reset_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="menu_back")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "⚠️ *Подтверждение сброса статистики*\n\n"
        "Вы уверены, что хотите сбросить всю статистику?\n"
        "Это действие нельзя отменить!",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_change_result_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int):
    """Показ меню изменения результата завершенного пари"""
    query = update.callback_query
    
    bet = get_bet(bet_id)
    if not bet:
        await query.edit_message_text("❌ Пари не найдено!")
        return
    
    if bet.status != 'FINISHED':
        await query.answer("❌ Можно изменить результат только завершенного пари", show_alert=True)
        return
    
    current_result = bet.playerA_name if bet.result == 'A' else (bet.playerB_name if bet.result == 'B' else 'VOID')
    
    keyboard = [
        [InlineKeyboardButton(f"🏆 {bet.playerA_name}", callback_data=f"chresult_{bet_id}_A")],
        [InlineKeyboardButton(f"🏆 {bet.playerB_name}", callback_data=f"chresult_{bet_id}_B")],
        [InlineKeyboardButton("🚫 VOID", callback_data=f"chresult_{bet_id}_VOID")],
        [InlineKeyboardButton("🔙 Назад к пари за сутки", callback_data="menu_bets_24h")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🔄 *Изменить результат пари #{bet_id}*\n\n"
        f"{bet.playerA_name} vs {bet.playerB_name}\n"
        f"Текущий результат: *{current_result}*\n\n"
        f"Выбери новый результат:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_change_result(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_id: int, new_result: str):
    """Обработка изменения результата с пересчетом статистики"""
    query = update.callback_query
    user = update.effective_user
    
    # Проверка доступа
    if not is_allowed_player(user.username):
        await query.answer("❌ Только игроки могут изменять результат", show_alert=True)
        return
    
    bet = get_bet(bet_id)
    if not bet:
        await query.edit_message_text("❌ Пари не найдено!")
        return
    
    # Изменяем результат с пересчетом
    change_bet_result(bet_id, new_result)
    
    bet = get_bet(bet_id)
    result_text = bet.playerA_name if bet.result == 'A' else (bet.playerB_name if bet.result == 'B' else 'VOID')
    
    await query.answer(f"✅ Результат изменен: {result_text}", show_alert=True)
    
    # Возвращаемся к списку пари за сутки
    await view_bets_24h_handler(update, context)


KICK_DOG_MESSAGES = [
    "быстро создавай пари, псина шелудивая!!!быстра!!",
    "шевели копытами своими кривыми, лошадь дохлая, пари где, сука?!!ЖИВО блять!!",
    "двигай этими культяпками, бомжара безмозглая, пари создавай или пиздец тебе!!ЖИВО!!",
    "шевели жопой криворукой, создавай пари уже, чмошник!!быстрее!!",
    "ты че уснул, пидор обоссаный? Делай пари СЕЙЧАС, мразь!!",
    "бегом создавай пари, ссыкло вонючее, или пиздец тебе!!го!!",
    "тряси своей лысой башкой и лепи пари, лох ебаный!!быстро бля!!",
    "не трынди, а создавай пари, кусок дерьма ходячий!!шевелись!!",
    "ты че как бабка старая копаешься? Пари давай, уёбище!!ЖИВО!!",
    "создавай пари, пока я тебе яйца не оторвал, чмырь позорный!!го го!!",
    "шевели пальцами, бомжара криворукая, пари где, сука?!!быстрее!!",
    "не беси, мразота шелудивая, лепи пари мгновенно или пиздец тебе!!",
    "давай пари, ты жопа безмозглая, или я тебя здесь же закопаю!!СРОЧНО!!",
    "шевели граблями своими кривыми, лошадь патанская, пари где, лярва позорная?!!Сейчас, тварь!!",
    "шевели копытами лошадь, пари где, гнида вонючая?!!ЖИВО, сука!!",
    "двигай этими клешнями дохлыми, лярва бомжатская, создавай пари, быдло ебаное!!СРОЧНО!!",
    "шевели копытами, лошадь гнилая, пари где, сука?! ЖИВО!",
    "копытами шевели, лярва вонючая, создавай, мразь!! СРОЧНО!",
    "двигай копытами, быдло тупое, пари давай, гнида!! Быстрее!!",
    "шевели клешнями, штемп обосранный, лепи пари, патана!! ЖИВО блять!",
    "копытами шевели, лошадь криворукая, пари или пиздец тебе, тварь!! СЕЙЧАС!",
]


async def handle_kick_dog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пнуть пса — тегнуть противника с рандомным сообщением"""
    import random
    query = update.callback_query
    user = update.effective_user
    
    # Определяем противника
    other = get_other_player(user.username)
    if not other:
        await query.answer("❌ Только игроки могут пинать пса!", show_alert=True)
        return
    
    msg = random.choice(KICK_DOG_MESSAGES)
    
    # Отправляем НОВОЕ сообщение, чтобы тег сработал как уведомление
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🐕 @{other}, {msg}"
    )
