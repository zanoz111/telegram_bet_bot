"""
Конфигурация бота
"""
from typing import Optional
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Фиксированные игроки
PLAYER_INZAAA_USERNAME = "Inzaaa"
PLAYER_TROOLZ_USERNAME = "TROOLZ"

# Тестовый режим - разрешает одному пользователю быть и maker, и taker
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true'

# Статусы пари
STATUS_DRAFT = "DRAFT"
STATUS_OPEN = "OPEN"
STATUS_TAKEN = "TAKEN"
STATUS_FINISHED = "FINISHED"
STATUS_CANCELED = "CANCELED"


def is_allowed_player(username: str) -> bool:
    """Проверяет, является ли пользователь одним из разрешенных игроков"""
    username_lower = username.lower() if username else ""
    return username_lower in [PLAYER_INZAAA_USERNAME.lower(), PLAYER_TROOLZ_USERNAME.lower()]


def get_other_player(username: str) -> Optional[str]:
    """Возвращает username второго игрока"""
    username_lower = username.lower() if username else ""
    if username_lower == PLAYER_INZAAA_USERNAME.lower():
        return PLAYER_TROOLZ_USERNAME
    elif username_lower == PLAYER_TROOLZ_USERNAME.lower():
        return PLAYER_INZAAA_USERNAME
    return None


def get_taker_user_id(maker_username: str, inzaaa_id: int, troolz_id: int) -> Optional[int]:
    """Определяет ID второго игрока (Taker) по username maker"""
    maker_lower = maker_username.lower() if maker_username else ""
    if maker_lower == PLAYER_INZAAA_USERNAME.lower():
        return troolz_id
    elif maker_lower == PLAYER_TROOLZ_USERNAME.lower():
        return inzaaa_id
    return None
