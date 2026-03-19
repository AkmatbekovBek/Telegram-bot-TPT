import random
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import re


class RouletteHelper:
    """Вспомогательные функции для рулетки"""

    @staticmethod
    def spin_wheel() -> int:
        """Крутить рулетку (возвращает число от 0 до 12)"""
        return random.randint(0, 12)

    @staticmethod
    def get_color(number: int) -> str:
        """Получить цвет числа"""
        if number == 0:
            return "зеленый"
        elif number % 2 == 0:
            return "черный"
        else:
            return "красный"

    @staticmethod
    def parse_bet_text(text: str) -> List[Dict[str, Any]]:
        """Парсить текстовые ставки вида '10 на красное | 5 на 12'"""
        bets = []
        bet_parts = text.split('|')

        for part in bet_parts:
            part = part.strip()
            if not part:
                continue

            # Ищем паттерн: число "на" что-то
            match = re.match(r'(\d+)\s+на\s+(.+)', part, re.IGNORECASE)
            if not match:
                continue

            amount = int(match.group(1))
            target = match.group(2).strip().lower()

            # Определяем тип ставки
            bet_type = None
            bet_value = None

            # Проверяем цвет
            if target in ["красное", "красный", "red"]:
                bet_type = "color"
                bet_value = "red"
            elif target in ["черное", "черный", "black"]:
                bet_type = "color"
                bet_value = "black"
            elif target in ["зеленое", "зеленый", "green", "зеро", "zero", "0"]:
                bet_type = "number"
                bet_value = "0"
            elif target.isdigit() and 0 <= int(target) <= 12:
                bet_type = "number"
                bet_value = target
            elif "-" in target:
                # Диапазон типа "1-3"
                try:
                    start, end = map(int, target.split('-'))
                    if 1 <= start <= end <= 12:
                        bet_type = "range"
                        bet_value = f"{start}-{end}"
                except:
                    continue

            if bet_type and bet_value:
                bets.append({
                    "amount": amount,
                    "type": bet_type,
                    "value": bet_value
                })

        return bets

    @staticmethod
    def format_number(number: int) -> str:
        """Форматировать число с разделителями"""
        return f"{number:,}".replace(",", " ")

    @staticmethod
    def get_roulette_layout() -> List[List[int]]:
        """Получить раскладку рулетки как на фото из ТЗ"""
        return [
            [1, 2, 3, 4, 5, 6],
            [7, 8, 9, 10, 11, 12]
        ]

    @staticmethod
    def get_emoji_for_number(number: int) -> str:
        """Получить эмодзи для числа"""
        if number == 0:
            return "🟢"
        elif number % 2 == 0:
            return "⚫"
        else:
            return "🔴"


class TextHelper:
    """Вспомогательные функции для текста"""

    @staticmethod
    def format_balance(balance: int) -> str:
        """Форматировать баланс"""
        if balance >= 1_000_000_000_000:  # триллионы
            return f"{balance / 1_000_000_000_000:.1f} трлн"
        elif balance >= 1_000_000_000:  # миллиарды
            return f"{balance / 1_000_000_000:.1f} млрд"
        elif balance >= 1_000_000:  # миллионы
            return f"{balance / 1_000_000:.1f} млн"
        elif balance >= 1_000:  # тысячи
            return f"{balance / 1_000:.1f} тыс"
        else:
            return str(balance)

    @staticmethod
    def get_time_ago(timestamp: datetime) -> str:
        """Получить 'сколько времени назад'"""
        now = datetime.utcnow()
        diff = now - timestamp

        if diff.days > 365:
            years = diff.days // 365
            return f"{years} год{'а' if years % 10 in [2, 3, 4] and years % 100 not in [12, 13, 14] else '' if 5 <= years % 10 <= 9 or years % 10 == 0 or years % 100 in [11, 12, 13, 14] else 'ов'}"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} месяц{'а' if months % 10 in [2, 3, 4] and months % 100 not in [12, 13, 14] else 'ев' if months % 10 == 0 or 5 <= months % 10 <= 9 or months % 100 in [11, 12, 13, 14] else ''}"
        elif diff.days > 0:
            return f"{diff.days} день{'дня' if diff.days % 10 in [2, 3, 4] and diff.days % 100 not in [12, 13, 14] else 'дней' if diff.days % 10 == 0 or 5 <= diff.days % 10 <= 9 or diff.days % 100 in [11, 12, 13, 14] else ''}"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} час{'а' if hours % 10 in [2, 3, 4] and hours % 100 not in [12, 13, 14] else 'ов' if hours % 10 == 0 or 5 <= hours % 10 <= 9 or hours % 100 in [11, 12, 13, 14] else ''}"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} минут{'у' if minutes == 1 else 'ы' if 2 <= minutes % 10 <= 4 and minutes % 100 not in [12, 13, 14] else ''}"
        else:
            return "только что"

    @staticmethod
    def escape_markdown(text: str) -> str:
        """Экранировать символы Markdown"""
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text


class GameHelper:
    """Вспомогательные функции для игр"""

    @staticmethod
    def generate_slot_result() -> List[List[str]]:
        """Сгенерировать результат для слотов"""
        symbols = ["🍒", "🍋", "🍉", "🍇", "🍊", "🍎", "🍓", "💎", "🔔", "7️⃣"]

        result = []
        for _ in range(3):  # 3 барабана
            drum = []
            for _ in range(3):  # 3 символа на барабане
                drum.append(random.choice(symbols))
            result.append(drum)

        return result

    @staticmethod
    def calculate_slot_win(result: List[List[str]], bet: int) -> Tuple[int, str]:
        """Рассчитать выигрыш в слотах"""
        # Проверяем комбинации
        win_type = None
        multiplier = 0

        # Все три барабана показывают 7
        if all(all(sym == "7️⃣" for sym in drum) for drum in result):
            win_type = "three_sevens"
            multiplier = 12
        # Все три барабана одинаковые
        elif result[0] == result[1] == result[2]:
            win_type = "three_drums"
            multiplier = 9
        # Первые два барабана одинаковые
        elif result[0] == result[1]:
            win_type = "two_drums"
            multiplier = 6
        # Один барабан показывает три вишни
        elif any(all(sym == "🍒" for sym in drum) for drum in result):
            win_type = "three_cherries"
            multiplier = 2

        win_amount = int(bet * multiplier) if multiplier > 0 else 0
        return win_amount, win_type

    @staticmethod
    async def simulate_spin(duration: int) -> List[int]:
        """Симулировать прокрутку рулетки"""
        numbers = []
        for _ in range(duration):
            numbers.append(random.randint(0, 12))
            await asyncio.sleep(1)
        return numbers


class ValidationHelper:
    """Вспомогательные функции для валидации"""

    @staticmethod
    def validate_bet_amount(amount: int, user_balance: int, min_bet: int) -> Tuple[bool, str]:
        """Проверить сумму ставки"""
        if amount < min_bet:
            return False, f"Минимальная ставка: {min_bet:,}"
        if amount > user_balance:
            return False, f"Недостаточно средств. Ваш баланс: {user_balance:,}"
        return True, ""

    @staticmethod
    def validate_clan_name(name: str) -> Tuple[bool, str]:
        """Проверить имя клана"""
        if len(name) < 3:
            return False, "Имя клана должно быть не менее 3 символов"
        if len(name) > 32:
            return False, "Имя клана должно быть не более 32 символов"
        if not re.match(r'^[a-zA-Zа-яА-Я0-9_\s]+$', name):
            return False, "Имя клана может содержать только буквы, цифры и пробелы"
        return True, ""

    @staticmethod
    def validate_clan_tag(tag: str) -> Tuple[bool, str]:
        """Проверить тег клана"""
        if len(tag) < 2:
            return False, "Тег клана должен быть не менее 2 символов"
        if len(tag) > 8:
            return False, "Тег клана должен быть не более 8 символов"
        if not re.match(r'^[a-zA-Z0-9_]+$', tag):
            return False, "Тег клана может содержать только латинские буквы и цифры"
        return True, ""