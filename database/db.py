"""
Модуль для работы с базой данных SQLite
"""
import sqlite3
from typing import List, Optional, Tuple
from models.bet import Bet, LedgerEntry
from datetime import datetime, timedelta


DB_PATH = 'bets.db'


def get_connection():
    """Получение соединения с базой данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализация базы данных"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Таблица пари
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            maker_user_id INTEGER NOT NULL,
            maker_username TEXT NOT NULL,
            taker_user_id INTEGER,
            taker_username TEXT,
            bet_name TEXT,
            playerA_name TEXT NOT NULL,
            playerB_name TEXT NOT NULL,
            oddsA REAL,
            oddsB REAL,
            stake REAL,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            taker_side TEXT,
            result TEXT,
            created_at TEXT NOT NULL,
            finished_at TEXT,
            maker_win REAL DEFAULT 0,
            taker_win REAL DEFAULT 0
        )
    ''')
    
    # Миграция: добавляем колонку bet_name, если она не существует
    cursor.execute("PRAGMA table_info(bets)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'bet_name' not in columns:
        cursor.execute('ALTER TABLE bets ADD COLUMN bet_name TEXT')
        print("Добавлена колонка bet_name в таблицу bets")
    
    # Таблица ledger для учета балансов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bet_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (bet_id) REFERENCES bets(id)
        )
    ''')
    
    # Добавляем индексы для быстрого поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_maker ON bets(maker_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bets_taker ON bets(taker_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ledger_created ON ledger(created_at)')
    
    conn.commit()
    conn.close()
    print("База данных инициализирована")


def create_bet(bet: Bet) -> int:
    """Создание нового пари"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO bets 
        (maker_user_id, maker_username, taker_user_id, taker_username, bet_name, playerA_name, playerB_name,
         oddsA, oddsB, stake, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        bet.maker_user_id, bet.maker_username, bet.taker_user_id, bet.taker_username, bet.bet_name,
        bet.playerA_name, bet.playerB_name, bet.oddsA, bet.oddsB, bet.stake,
        bet.status, bet.created_at.isoformat()
    ))
    
    bet_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return bet_id


def update_bet_step2(bet_id: int, oddsA: float, oddsB: float):
    """Обновление коэффициентов (шаг 2)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE bets SET oddsA = ?, oddsB = ? WHERE id = ?', (oddsA, oddsB, bet_id))
    conn.commit()
    conn.close()


def update_bet_name(bet_id: int, bet_name: str):
    """Обновление названия пари"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE bets SET bet_name = ? WHERE id = ?', (bet_name, bet_id))
    conn.commit()
    conn.close()


def update_bet_step3(bet_id: int, stake: float):
    """Обновление суммы и публикация пари (шаг 3)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Получаем maker username для определения taker
    cursor.execute('SELECT maker_username FROM bets WHERE id = ?', (bet_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    
    maker_username = row[0]
    from config import get_other_player, TEST_MODE
    # В тестовом режиме taker = maker (для тестирования на одном аккаунте)
    if TEST_MODE:
        taker_username = maker_username
    else:
        taker_username = get_other_player(maker_username)
    
    # taker_user_id установится при принятии пари
    
    cursor.execute('''
        UPDATE bets 
        SET stake = ?, status = 'OPEN', taker_username = ?
        WHERE id = ?
    ''', (stake, taker_username, bet_id))
    
    conn.commit()
    conn.close()


def update_taker_user_id(bet_id: int, taker_user_id: int):
    """Обновление taker_user_id (вызывается при принятии пари)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE bets SET taker_user_id = ? WHERE id = ?', (taker_user_id, bet_id))
    conn.commit()
    conn.close()


def get_bet(bet_id: int) -> Optional[Bet]:
    """Получение пари по ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bets WHERE id = ?', (bet_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return Bet.from_dict(dict(row))
    return None


def get_active_bets() -> List[Bet]:
    """Получение активных пари (OPEN и TAKEN)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM bets 
        WHERE status IN ('OPEN', 'TAKEN') 
        ORDER BY created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [Bet.from_dict(dict(row)) for row in rows]


def get_bets_last_24h() -> List[Bet]:
    """Получение завершенных пари за последние 24 часа"""
    conn = get_connection()
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=1)).isoformat()
    cursor.execute('''
        SELECT * FROM bets 
        WHERE status = 'FINISHED' AND finished_at >= ?
        ORDER BY finished_at DESC
    ''', (cutoff,))
    rows = cursor.fetchall()
    conn.close()
    return [Bet.from_dict(dict(row)) for row in rows]


def take_bet(bet_id: int, taker_user_id: int, taker_side: str):
    """Принятие пари (выбор стороны)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT taker_username FROM bets WHERE id = ?', (bet_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    
    taker_username = row[0]
    
    cursor.execute('''
        UPDATE bets 
        SET taker_user_id = ?, taker_side = ?, status = 'TAKEN'
        WHERE id = ?
    ''', (taker_user_id, taker_side, bet_id))
    
    conn.commit()
    conn.close()


def set_bet_result(bet_id: int, result: str):
    """Установка результата и расчет выигрышей"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM bets WHERE id = ?', (bet_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    
    bet = Bet.from_dict(dict(row))
    
    if not bet.taker_side or not bet.stake:
        conn.close()
        return
    
    # Формула расчета согласно ТЗ
    S = bet.stake
    O = bet.oddsA if bet.taker_side == 'A' else bet.oddsB
    
    maker_win = 0.0
    taker_win = 0.0
    
    if result == 'VOID':
        maker_win = 0.0
        taker_win = 0.0
    elif result == bet.taker_side:
        # Taker выиграл
        taker_win = S * (O - 1)
        maker_win = -S * (O - 1)
    else:
        # Taker проиграл
        taker_win = -S
        maker_win = S
    
    finished_at = datetime.now()
    
    cursor.execute('''
        UPDATE bets 
        SET result = ?, maker_win = ?, taker_win = ?, status = 'FINISHED', finished_at = ?
        WHERE id = ?
    ''', (result, maker_win, taker_win, finished_at.isoformat(), bet_id))
    
    # Создаем записи в ledger
    cursor.execute('''
        INSERT INTO ledger (bet_id, user_id, username, amount, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (bet_id, bet.maker_user_id, bet.maker_username, maker_win, finished_at.isoformat()))
    
    cursor.execute('''
        INSERT INTO ledger (bet_id, user_id, username, amount, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (bet_id, bet.taker_user_id, bet.taker_username, taker_win, finished_at.isoformat()))
    
    conn.commit()
    conn.close()


def change_bet_result(bet_id: int, new_result: str):
    """Изменение результата пари с пересчетом статистики"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM bets WHERE id = ?', (bet_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    
    bet = Bet.from_dict(dict(row))
    
    if not bet.taker_side or not bet.stake:
        conn.close()
        return
    
    # Удаляем старые ledger записи для этого пари
    cursor.execute('DELETE FROM ledger WHERE bet_id = ?', (bet_id,))
    
    # Пересчитываем выигрыши
    S = bet.stake
    O = bet.oddsA if bet.taker_side == 'A' else bet.oddsB
    
    maker_win = 0.0
    taker_win = 0.0
    
    if new_result == 'VOID':
        maker_win = 0.0
        taker_win = 0.0
    elif new_result == bet.taker_side:
        taker_win = S * (O - 1)
        maker_win = -S * (O - 1)
    else:
        taker_win = -S
        maker_win = S
    
    finished_at = datetime.now()
    
    cursor.execute('''
        UPDATE bets 
        SET result = ?, maker_win = ?, taker_win = ?, finished_at = ?
        WHERE id = ?
    ''', (new_result, maker_win, taker_win, finished_at.isoformat(), bet_id))
    
    # Создаем новые записи в ledger
    cursor.execute('''
        INSERT INTO ledger (bet_id, user_id, username, amount, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (bet_id, bet.maker_user_id, bet.maker_username, maker_win, finished_at.isoformat()))
    
    cursor.execute('''
        INSERT INTO ledger (bet_id, user_id, username, amount, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (bet_id, bet.taker_user_id, bet.taker_username, taker_win, finished_at.isoformat()))
    
    conn.commit()
    conn.close()


def cancel_bet(bet_id: int):
    """Отмена пари"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE bets SET status = 'CANCELED' WHERE id = ?", (bet_id,))
    conn.commit()
    conn.close()


def get_user_statistics(user_id: int, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> dict:
    """Получение статистики пользователя за период"""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = 'SELECT SUM(amount) as total_balance FROM ledger WHERE user_id = ?'
    params = [user_id]
    
    if start_date:
        query += ' AND created_at >= ?'
        params.append(start_date.isoformat())
    if end_date:
        query += ' AND created_at <= ?'
        params.append(end_date.isoformat())
    
    cursor.execute(query, params)
    row = cursor.fetchone()
    total_balance = row[0] or 0.0
    
    # Подсчет пари (уникальных bet_id)
    query_bets = 'SELECT COUNT(DISTINCT bet_id) FROM ledger WHERE user_id = ?'
    params_bets = [user_id]
    if start_date:
        query_bets += ' AND created_at >= ?'
        params_bets.append(start_date.isoformat())
    if end_date:
        query_bets += ' AND created_at <= ?'
        params_bets.append(end_date.isoformat())
    
    cursor.execute(query_bets, params_bets)
    total_bets = cursor.fetchone()[0] or 0
    
    # Победы (amount > 0)
    query_wins = 'SELECT COUNT(*) FROM ledger WHERE user_id = ? AND amount > 0'
    params_wins = [user_id]
    if start_date:
        query_wins += ' AND created_at >= ?'
        params_wins.append(start_date.isoformat())
    if end_date:
        query_wins += ' AND created_at <= ?'
        params_wins.append(end_date.isoformat())
    
    cursor.execute(query_wins, params_wins)
    wins = cursor.fetchone()[0] or 0
    
    # Поражения (amount < 0)
    query_losses = 'SELECT COUNT(*) FROM ledger WHERE user_id = ? AND amount < 0'
    params_losses = [user_id]
    if start_date:
        query_losses += ' AND created_at >= ?'
        params_losses.append(start_date.isoformat())
    if end_date:
        query_losses += ' AND created_at <= ?'
        params_losses.append(end_date.isoformat())
    
    cursor.execute(query_losses, params_losses)
    losses = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        'total_balance': total_balance,
        'total_bets': total_bets,
        'wins': wins,
        'losses': losses
    }


def get_all_statistics(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> dict:
    """Получение общей статистики для обоих игроков"""
    from config import PLAYER_INZAAA_USERNAME, PLAYER_TROOLZ_USERNAME
    
    # Получаем ID игроков из ledger (более надежный источник)
    conn = get_connection()
    cursor = conn.cursor()
    
    # Получаем уникальные user_id и username из ledger с приоритетом последним записям
    cursor.execute('''
        SELECT user_id, username 
        FROM ledger 
        WHERE username IN (?, ?)
        GROUP BY username
        ORDER BY MAX(created_at) DESC
    ''', (PLAYER_INZAAA_USERNAME, PLAYER_TROOLZ_USERNAME))
    
    users = {}
    for row in cursor.fetchall():
        username = row[1]
        user_id = row[0]
        if username and username not in users:
            users[username] = user_id
    
    # Если не нашли в ledger, ищем в bets
    if len(users) < 2:
        # Сначала ищем как maker
        cursor.execute('''
            SELECT DISTINCT maker_user_id, maker_username 
            FROM bets 
            WHERE maker_username IN (?, ?)
        ''', (PLAYER_INZAAA_USERNAME, PLAYER_TROOLZ_USERNAME))
        
        for row in cursor.fetchall():
            username = row[1]
            user_id = row[0]
            if username and username not in users:
                users[username] = user_id
        
        # Потом ищем как taker
        cursor.execute('''
            SELECT DISTINCT taker_user_id, taker_username 
            FROM bets 
            WHERE taker_username IN (?, ?) AND taker_user_id IS NOT NULL
        ''', (PLAYER_INZAAA_USERNAME, PLAYER_TROOLZ_USERNAME))
        
        for row in cursor.fetchall():
            username = row[1]
            user_id = row[0]
            if username and username not in users:
                users[username] = user_id
    
    conn.close()
    
    stats = {}
    for username, user_id in users.items():
        if user_id:
            stats[username] = get_user_statistics(user_id, start_date, end_date)
        else:
            # Если user_id не найден, возвращаем нулевую статистику
            stats[username] = {
                'total_balance': 0.0,
                'total_bets': 0,
                'wins': 0,
                'losses': 0
            }
    
    # Убеждаемся, что оба игрока присутствуют
    if PLAYER_INZAAA_USERNAME not in stats:
        stats[PLAYER_INZAAA_USERNAME] = {'total_balance': 0.0, 'total_bets': 0, 'wins': 0, 'losses': 0}
    if PLAYER_TROOLZ_USERNAME not in stats:
        stats[PLAYER_TROOLZ_USERNAME] = {'total_balance': 0.0, 'total_bets': 0, 'wins': 0, 'losses': 0}
    
    return stats


def reset_statistics():
    """Сброс статистики (очистка ledger)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ledger')
    conn.commit()
    conn.close()
