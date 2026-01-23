"""
Модели данных для пари
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# Фиксированные игроки
PLAYER_INZAAA = "Inzaaa"
PLAYER_TROOLZ = "TROOLZ"
PLAYER_INZAAA_USERNAME = "Inzaaa"
PLAYER_TROOLZ_USERNAME = "TROOLZ"

# Статусы пари
STATUS_DRAFT = "DRAFT"
STATUS_OPEN = "OPEN"
STATUS_TAKEN = "TAKEN"
STATUS_FINISHED = "FINISHED"
STATUS_CANCELED = "CANCELED"


@dataclass
class Bet:
    """Модель пари"""
    id: Optional[int]
    maker_user_id: int  # ID создателя (Maker)
    maker_username: str
    taker_user_id: Optional[int]  # ID второго игрока (Taker)
    taker_username: Optional[str]
    playerA_name: str  # Имя первого игрока из матча
    playerB_name: str  # Имя второго игрока из матча
    oddsA: Optional[float]  # Коэффициент для playerA
    oddsB: Optional[float]  # Коэффициент для playerB
    stake: Optional[float]  # Сумма ставки
    status: str  # DRAFT, OPEN, TAKEN, FINISHED, CANCELED
    taker_side: Optional[str]  # 'A' или 'B' - выбранная сторона taker
    result: Optional[str]  # 'A', 'B', 'VOID' - результат матча
    created_at: datetime
    finished_at: Optional[datetime] = None
    maker_win: Optional[float] = 0.0  # Выигрыш maker
    taker_win: Optional[float] = 0.0  # Выигрыш taker
    
    def to_dict(self):
        """Преобразование в словарь для базы данных"""
        return {
            'maker_user_id': self.maker_user_id,
            'maker_username': self.maker_username,
            'taker_user_id': self.taker_user_id,
            'taker_username': self.taker_username,
            'playerA_name': self.playerA_name,
            'playerB_name': self.playerB_name,
            'oddsA': self.oddsA,
            'oddsB': self.oddsB,
            'stake': self.stake,
            'status': self.status,
            'taker_side': self.taker_side,
            'result': self.result,
            'created_at': self.created_at.isoformat(),
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'maker_win': self.maker_win or 0.0,
            'taker_win': self.taker_win or 0.0
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """Создание из словаря базы данных"""
        return cls(
            id=data.get('id'),
            maker_user_id=data['maker_user_id'],
            maker_username=data['maker_username'],
            taker_user_id=data.get('taker_user_id'),
            taker_username=data.get('taker_username'),
            playerA_name=data['playerA_name'],
            playerB_name=data['playerB_name'],
            oddsA=data.get('oddsA'),
            oddsB=data.get('oddsB'),
            stake=data.get('stake'),
            status=data['status'],
            taker_side=data.get('taker_side'),
            result=data.get('result'),
            created_at=datetime.fromisoformat(data['created_at']),
            finished_at=datetime.fromisoformat(data['finished_at']) if data.get('finished_at') else None,
            maker_win=data.get('maker_win', 0.0),
            taker_win=data.get('taker_win', 0.0)
        )
    
    def get_taker_user_id(self) -> int:
        """Определяет ID второго игрока (Taker)"""
        if self.maker_username.lower() == PLAYER_INZAAA_USERNAME.lower():
            # Если maker = Inzaaa, то taker = TROOLZ
            # Нужно вернуть ID TROOLZ (будет установлен при создании)
            return None  # Будет установлен при публикации
        else:
            # Если maker = TROOLZ, то taker = Inzaaa
            return None  # Будет установлен при публикации


@dataclass
class LedgerEntry:
    """Запись в ledger для учета балансов"""
    id: Optional[int]
    bet_id: int
    user_id: int
    username: str
    amount: float  # Может быть положительным (выигрыш) или отрицательным (проигрыш)
    created_at: datetime
    
    def to_dict(self):
        return {
            'bet_id': self.bet_id,
            'user_id': self.user_id,
            'username': self.username,
            'amount': self.amount,
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data.get('id'),
            bet_id=data['bet_id'],
            user_id=data['user_id'],
            username=data['username'],
            amount=data['amount'],
            created_at=datetime.fromisoformat(data['created_at'])
        )
