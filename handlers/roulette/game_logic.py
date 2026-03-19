# handlers/roulette/game_logic.py
import random
import asyncio
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Tuple, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from .config import CONFIG


class RouletteGame:
    def __init__(self):
        self.numbers = list(CONFIG.NUMBERS)
        self._rng = random.Random()
        self.standard_groups = {
            "1-3": {1, 2, 3}, "4-6": {4, 5, 6},
            "7-9": {7, 8, 9}, "10-12": {10, 11, 12}
        }
        self.last_results = []
        self.max_same_color_streak = 4
        self.chat_stats = {}

    def _get_chat_stats(self, chat_id):
        if chat_id not in self.chat_stats:
            self.chat_stats[chat_id] = {
                'last_results': [],
                'color_streak': 0,
                'last_color': None,
                'last_number': None,
                'recent_numbers': [],
                'recent_colors': []
            }
        return self.chat_stats[chat_id]

    def _get_available_numbers(self, exclude_color: str = None, exclude_number: int = None):
        available_numbers = self.numbers.copy()

        if exclude_color == "красное":
            available_numbers = [n for n in available_numbers if n not in CONFIG.RED_NUMBERS]
        elif exclude_color == "черное":
            available_numbers = [n for n in available_numbers if n not in CONFIG.BLACK_NUMBERS]
        elif exclude_color == "зеленое":
            available_numbers = [n for n in available_numbers if n != 0]

        if exclude_number is not None and exclude_number in available_numbers:
            available_numbers.remove(exclude_number)

        return available_numbers

    def spin(self, chat_id: int = 0) -> int:
        stats = self._get_chat_stats(chat_id)

        if stats['color_streak'] >= self.max_same_color_streak and stats['last_color']:
            available_numbers = self._get_available_numbers(exclude_color=stats['last_color'])
            if available_numbers:
                if random.random() < 0.3 and 0 in available_numbers:
                    result = 0
                else:
                    result = random.choice(available_numbers)
            else:
                result = random.choice(self.numbers)
        else:
            result = self._generate_natural_random(stats)

        if result == stats['last_number'] and result != 0:
            all_numbers_except_current = [n for n in self.numbers if n != result]
            result_color = self.get_color(result)
            same_color_numbers = [n for n in all_numbers_except_current if self.get_color(n) == result_color]

            if same_color_numbers:
                result = random.choice(same_color_numbers)
            else:
                result = random.choice(all_numbers_except_current)

        if len(stats['recent_colors']) >= 3:
            last_three = stats['recent_colors'][-3:]
            if len(last_three) == 3:
                pattern1 = ["красное", "черное", "красное"]
                pattern2 = ["черное", "красное", "черное"]
                current_color = self.get_color(result)

                if (last_three == pattern1 and current_color == "черное") or \
                        (last_three == pattern2 and current_color == "красное"):
                    opposite_color = "черное" if current_color == "красное" else "красное"
                    available_numbers = self._get_available_numbers(exclude_color=current_color)

                    if random.random() < 0.2 and 0 in available_numbers:
                        result = 0
                    elif available_numbers:
                        opposite_numbers = [n for n in available_numbers if self.get_color(n) == opposite_color]
                        if opposite_numbers:
                            result = random.choice(opposite_numbers)

        self._update_stats(result, chat_id)
        return result

    def _generate_natural_random(self, stats):
        if random.random() < 0.10:
            return 0

        if stats['color_streak'] >= 3 and stats['last_color'] in ['красное', 'черное']:
            if random.random() < 0.8:
                if stats['last_color'] == 'красное':
                    return random.choice(list(CONFIG.BLACK_NUMBERS))
                else:
                    return random.choice(list(CONFIG.RED_NUMBERS))

        rand_val = random.random()
        if rand_val < 0.48:
            return random.choice(list(CONFIG.RED_NUMBERS))
        else:
            return random.choice(list(CONFIG.BLACK_NUMBERS))

    def _update_stats(self, result: int, chat_id: int):
        stats = self._get_chat_stats(chat_id)
        result_color = self.get_color(result)

        if result_color == stats['last_color']:
            stats['color_streak'] += 1
        else:
            stats['color_streak'] = 1
            stats['last_color'] = result_color

        stats['last_number'] = result
        stats['recent_numbers'].append(result)
        if len(stats['recent_numbers']) > 6:
            stats['recent_numbers'] = stats['recent_numbers'][-6:]

        stats['recent_colors'].append(result_color)
        if len(stats['recent_colors']) > 6:
            stats['recent_colors'] = stats['recent_colors'][-6:]

        stats['last_results'].append(result)
        if len(stats['last_results']) > 20:
            stats['last_results'] = stats['last_results'][-20:]

        self.last_results.append(result)
        if len(self.last_results) > 50:
            self.last_results = self.last_results[-50:]

    def get_color(self, number: int) -> str:
        if number == 0:
            return "зеленое"
        return "красное" if number in CONFIG.RED_NUMBERS else "черное"

    def get_color_emoji(self, number: int) -> str:
        if number == 0:
            return "💚"
        return "🔴" if number in CONFIG.RED_NUMBERS else "⚫"

    def check_bet(self, bet_type: str, bet_value: Any, result: int) -> bool:
        """Проверяет, выиграла ли ставка (без учета особых правил для зеро)"""
        try:
            if bet_type == "число":
                num_value = int(bet_value) if isinstance(bet_value, str) else bet_value
                return num_value == result
            elif bet_type == "цвет":
                return (
                        (bet_value == "красное" and result in CONFIG.RED_NUMBERS) or
                        (bet_value == "черное" and result in CONFIG.BLACK_NUMBERS) or
                        (bet_value == "зеро" and result == 0)
                )
            elif bet_type == "группа":
                if bet_value in self.standard_groups:
                    return result in self.standard_groups[bet_value]
                if isinstance(bet_value, str) and '-' in bet_value:
                    try:
                        start, end = map(int, bet_value.split('-'))
                        if 0 <= start <= 12 and 0 <= end <= 12 and start <= end:
                            return start <= result <= end
                    except (ValueError, TypeError):
                        return False
            return False
        except (ValueError, TypeError):
            return False

    def get_multiplier(self, bet_type: str, bet_value: Any) -> Decimal:
        if bet_type == "число":
            return Decimal('12.0')
        elif bet_type == "цвет":
            if bet_value == "зеленое":
                return Decimal('12.0')
            else:
                return Decimal('2.0')
        elif bet_type == "группа":
            if isinstance(bet_value, str) and '-' in bet_value:
                try:
                    start, end = map(int, bet_value.split('-'))
                    if 0 <= start <= 12 and 0 <= end <= 12 and start <= end:
                        count = end - start + 1
                        return (Decimal('12.0') / Decimal(count)).quantize(
                            Decimal('0.001'), rounding=ROUND_DOWN
                        )
                except (ValueError, TypeError):
                    pass
            return Decimal('4.333')
        return Decimal('1.0')

    def get_color_streak_info(self, chat_id: int = 0) -> str:
        stats = self._get_chat_stats(chat_id)
        if not stats['last_color']:
            return "История цветов пуста"
        return f"Текущая серия: {stats['last_color']} ({stats['color_streak']} раз подряд)"

    def get_recent_history(self, chat_id: int = 0, limit: int = 10) -> list:
        stats = self._get_chat_stats(chat_id)
        return stats['last_results'][-limit:] if stats['last_results'] else []


class RouletteKeyboard:
    @staticmethod
    def create_roulette_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(row_width=4).row(
            InlineKeyboardButton("1-3", callback_data="bet:1-3"),
            InlineKeyboardButton("4-6", callback_data="bet:4-6"),
            InlineKeyboardButton("7-9", callback_data="bet:7-9"),
            InlineKeyboardButton("10-12", callback_data="bet:10-12"),
        ).row(
            InlineKeyboardButton("5тыс 🔴", callback_data="quick:5000_red"),
            InlineKeyboardButton("5тыс ⚫", callback_data="quick:5000_black"),
            InlineKeyboardButton("5тыс 💚", callback_data="quick:5000_green"),
        ).row(
            InlineKeyboardButton("Повторить", callback_data="action:repeat"),
            InlineKeyboardButton("Удвоить", callback_data="action:double"),
            InlineKeyboardButton("Крутить", callback_data="action:spin"),
        )


class AntiFloodManager:
    __slots__ = ('user_last_spin', 'user_spin_count', 'user_spin_reset_time')

    def __init__(self):
        self.user_last_spin: Dict[Tuple[int, int], float] = {}
        self.user_spin_count: Dict[Tuple[int, int], int] = {}
        self.user_spin_reset_time: Dict[Tuple[int, int], float] = {}

    def can_spin(self, user_id: int, chat_id: int) -> Tuple[bool, float]:
        key = (user_id, chat_id)
        current_time = asyncio.get_event_loop().time()
        if key in self.user_last_spin:
            last_spin_time = self.user_last_spin[key]
            elapsed = current_time - last_spin_time
            if elapsed < CONFIG.MIN_SPIN_INTERVAL:
                return False, CONFIG.MIN_SPIN_INTERVAL - elapsed
        if key not in self.user_spin_count:
            self.user_spin_count[key] = 0
            self.user_spin_reset_time[key] = current_time
        if current_time - self.user_spin_reset_time[key] > CONFIG.RESET_INTERVAL:
            self.user_spin_count[key] = 0
            self.user_spin_reset_time[key] = current_time
        if self.user_spin_count[key] >= CONFIG.MAX_SPINS_PER_MINUTE:
            time_until_reset = CONFIG.RESET_INTERVAL - (current_time - self.user_spin_reset_time[key])
            return False, time_until_reset
        self.user_last_spin[key] = current_time
        self.user_spin_count[key] += 1
        return True, 0

    def cleanup_old_entries(self):
        current_time = asyncio.get_event_loop().time()
        old_keys = [
            key for key, timestamp in self.user_last_spin.items()
            if current_time - timestamp > CONFIG.CLEANUP_INTERVAL
        ]
        for key in old_keys:
            self.user_last_spin.pop(key, None)
            self.user_spin_count.pop(key, None)
            self.user_spin_reset_time.pop(key, None)