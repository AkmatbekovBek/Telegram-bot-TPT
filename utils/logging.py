import logging
import sys
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime
from typing import Dict, Any


def setup_logging():
    """Настройка логирования"""
    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Файловый обработчик
    file_handler = RotatingFileHandler(
        'bot.log',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Отдельный логгер для игр
    game_logger = logging.getLogger('game')
    game_handler = RotatingFileHandler(
        'games.log',
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    game_handler.setFormatter(formatter)
    game_logger.addHandler(game_handler)
    game_logger.setLevel(logging.INFO)

    return root_logger


class GameLogger:
    """Логирование игровых событий"""

    @staticmethod
    def log_roulette_spin(game_data: Dict[str, Any]):
        """Залогировать прокрутку рулетки"""
        logger = logging.getLogger('game')
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "roulette_spin",
            "data": game_data
        }
        logger.info(json.dumps(log_entry, ensure_ascii=False))

    @staticmethod
    def log_big_win(user_id: int, game_type: str, amount: int, details: Dict[str, Any]):
        """Залогировать крупный выигрыш"""
        logger = logging.getLogger('game')
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "big_win",
            "user_id": user_id,
            "game_type": game_type,
            "amount": amount,
            "details": details
        }
        logger.info(json.dumps(log_entry, ensure_ascii=False))

    @staticmethod
    def log_admin_action(admin_id: int, action: str, target_id: int, details: Dict[str, Any]):
        """Залогировать действие администратора"""
        logger = logging.getLogger('game')
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "admin_action",
            "admin_id": admin_id,
            "action": action,
            "target_id": target_id,
            "details": details
        }
        logger.info(json.dumps(log_entry, ensure_ascii=False))


# Инициализация логирования
logger = setup_logging()