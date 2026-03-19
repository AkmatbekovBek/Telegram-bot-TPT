import random
import logging
from typing import List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SlotSymbol(Enum):
    """Символы слота"""
    CHERRY = "🍒"
    LEMON = "🍋"
    WATERMELON = "🍉"
    GRAPE = "🍇"
    ORANGE = "🍊"
    APPLE = "🍎"
    STRAWBERRY = "🍓"
    DIAMOND = "💎"
    BELL = "🔔"
    SEVEN = "7️⃣"


@dataclass
class SlotConfig:
    """Конфигурация игры"""
    # Барабаны и ячейки
    DRUMS_COUNT = 3
    CELLS_PER_DRUM = 3

    # Символы для игры
    SYMBOLS = [
        SlotSymbol.CHERRY,
        SlotSymbol.LEMON,
        SlotSymbol.WATERMELON,
        SlotSymbol.GRAPE,
        SlotSymbol.ORANGE,
        SlotSymbol.APPLE,
        SlotSymbol.STRAWBERRY,
        SlotSymbol.DIAMOND,
        SlotSymbol.BELL,
        SlotSymbol.SEVEN
    ]

    # Множители выигрыша
    WIN_MULTIPLIERS = {
        "single_drum": 2,
        "two_drums": 6,
        "three_drums": 9,
        "three_sevens": 12
    }

    # Минимальная и максимальная ставка
    MIN_BET = 5000
    MAX_BET = 100_000_000


class SlotResult:
    """Результат игры в слот"""

    def __init__(self, reels: List[List[SlotSymbol]], bet: int, user_id: int):
        self.reels = reels
        self.bet = bet
        self.user_id = user_id
        self.win_amount = 0
        self.win_type = None
        self.win_multiplier = 0

    def calculate_win(self) -> int:
        """Рассчитывает выигрыш"""
        if self._check_three_sevens():
            self.win_type = "three_sevens"
            self.win_multiplier = SlotConfig.WIN_MULTIPLIERS["three_sevens"]
            self.win_amount = self.bet * self.win_multiplier
            return self.win_amount

        if self._check_three_drums():
            self.win_type = "three_drums"
            self.win_multiplier = SlotConfig.WIN_MULTIPLIERS["three_drums"]
            self.win_amount = self.bet * self.win_multiplier
            return self.win_amount

        if self._check_two_drums():
            self.win_type = "two_drums"
            self.win_multiplier = SlotConfig.WIN_MULTIPLIERS["two_drums"]
            self.win_amount = self.bet * self.win_multiplier
            return self.win_amount

        if self._check_single_drum():
            self.win_type = "single_drum"
            self.win_multiplier = SlotConfig.WIN_MULTIPLIERS["single_drum"]
            self.win_amount = self.bet * self.win_multiplier
            return self.win_amount

        self.win_type = "lose"
        self.win_multiplier = 0
        self.win_amount = 0
        return 0

    def _check_single_drum(self) -> bool:
        for drum in self.reels:
            if len(set(drum)) == 1:
                return True
        return False

    def _check_two_drums(self) -> bool:
        for i in range(len(self.reels) - 1):
            if self.reels[i] == self.reels[i + 1]:
                return True
        return False

    def _check_three_drums(self) -> bool:
        return len(set(tuple(drum) for drum in self.reels)) == 1

    def _check_three_sevens(self) -> bool:
        for drum in self.reels:
            if not all(symbol == SlotSymbol.SEVEN for symbol in drum):
                return False
        return True

    def get_reels_display(self) -> str:
        """Форматирует барабаны для отображения"""
        lines = []
        for i in range(SlotConfig.CELLS_PER_DRUM):
            row = []
            for drum in self.reels:
                row.append(drum[i].value)
            lines.append(f"|{'|'.join(row)}|")
        return "\n".join(lines)

    def get_win_message(self) -> str:
        if self.win_type == "lose":
            return " Проигрыш"

        win_types = {
            "single_drum": "🎰 3 одинаковых на одном барабане",
            "two_drums": "🎰🎰 2 барабана подряд с одинаковыми",
            "three_drums": "🎰🎰🎰 3 барабана с одинаковыми",
            "three_sevens": "🎰 777 JACKPOT! 🎰"
        }

        return f"🎉 {win_types[self.win_type]} ×{self.win_multiplier}"


class SlotGame:
    """Основной класс игры"""

    def __init__(self):
        self.config = SlotConfig()

    def spin(self, bet: int, user_id: int) -> SlotResult:
        reels = []
        for _ in range(self.config.DRUMS_COUNT):
            drum = random.choices(
                self.config.SYMBOLS,
                k=self.config.CELLS_PER_DRUM
            )
            reels.append(drum)

        result = SlotResult(reels, bet, user_id)
        result.calculate_win()
        return result

    def is_valid_bet(self, bet: int) -> bool:
        return self.config.MIN_BET <= bet <= self.config.MAX_BET

    def parse_bet(self, bet_str: str) -> int:
        bet_str = bet_str.lower().strip()
        bet_str = bet_str.replace(',', '').replace(' ', '')

        try:
            if bet_str.endswith('m'):
                return int(float(bet_str[:-1]) * 1_000_000)
            elif bet_str.endswith('k'):
                return int(float(bet_str[:-1]) * 1_000)
            else:
                return int(bet_str)
        except ValueError:
            raise ValueError(f"Неверный формат ставки: {bet_str}")


class SlotDatabase:
    """Работа с базой данных для игры — каждая операция создаёт свою сессию,
    чтобы не конфликтовать с параллельными играми (рулетка, баскет и т.д.)"""

    def __init__(self):
        pass  # сессии создаются per-operation

    def update_user_balance(self, user_id: int, amount_change: int, game_result: str = "") -> bool:
        """Обновляет баланс и создает запись в истории"""
        from database import SessionLocal
        db = SessionLocal()
        try:
            from database.crud import UserRepository
            user = UserRepository.get_user_by_telegram_id(db, user_id)

            if not user:
                logger.error(f"User {user_id} not found")
                return False

            if amount_change < 0 and user.coins < abs(amount_change):
                logger.error(f"User {user_id} insufficient funds")
                return False

            user.coins += amount_change

            # Обновляем статистику
            if amount_change > 0:
                user.win_coins = (user.win_coins or 0) + amount_change
                user.max_win_coins = max(user.max_win_coins or 0, amount_change)
            elif amount_change < 0:
                user.defeat_coins = (user.defeat_coins or 0) + abs(amount_change)

            bet_amount = abs(amount_change) if amount_change < 0 else 0
            user.max_bet = max(user.max_bet or 0, bet_amount)

            # Создаем запись в транзакциях для истории
            from database.crud import TransactionRepository

            if amount_change < 0:
                # Ставка или проигрыш
                if "Ставка" in game_result:
                    description = "Слот: Ставка"
                else:
                    description = "Слот: Проигрыш"

                TransactionRepository.create_transaction(
                    db=db,
                    from_user_id=user_id,
                    to_user_id=None,
                    amount=abs(amount_change),
                    description=description
                )
            else:
                # Выигрыш
                description = "Слот: Выигрыш"
                if game_result:
                    # Извлекаем тип выигрыша из game_result
                    if "777" in game_result or "JACKPOT" in game_result:
                        description = "Слот: Джекпот 777"
                    elif "3 барабана" in game_result:
                        description = "Слот: 3 барабана"
                    elif "2 барабана" in game_result:
                        description = "Слот: 2 барабана"
                    elif "3 одинаковых" in game_result:
                        description = "Слот: 1 барабан"

                TransactionRepository.create_transaction(
                    db=db,
                    from_user_id=None,
                    to_user_id=user_id,
                    amount=amount_change,
                    description=description
                )

            db.commit()
            return True

        except Exception as e:
            logger.error(f"Error updating user balance: {e}")
            db.rollback()
            return False
        finally:
            db.close()

    def get_user_balance(self, user_id: int) -> int:
        from database import SessionLocal
        db = SessionLocal()
        try:
            from database.crud import UserRepository
            user = UserRepository.get_user_by_telegram_id(db, user_id)
            return int(user.coins) if user else 0
        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            return 0
        finally:
            db.close()