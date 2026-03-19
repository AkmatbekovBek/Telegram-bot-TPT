# handlers/roulette/utils.py
import asyncio
from datetime import datetime
from typing import List, Tuple, Optional, Any
from decimal import Decimal, ROUND_DOWN
from aiogram import types
from aiogram.utils.exceptions import BadRequest
from config import bot
import logging

logger = logging.getLogger(__name__)
from .validators import UserFormatter
from .config import CONFIG


def get_display_name(user: types.User) -> str:
    if user.first_name:
        return user.first_name
    elif user.username:
        return f"@{user.username}"
    else:
        return f"Пользователь {user.id}"


def format_username_with_link(user_id: int, username: str) -> str:
    return UserFormatter.get_user_link(user_id, username)


def get_plain_username(username: str) -> str:
    return UserFormatter.get_plain_name(username)


async def delete_bet_messages(chat_id: int, bet_message_ids: List[int]):
    if not bet_message_ids:
        return
    delete_tasks = [
        bot.delete_message(chat_id=chat_id, message_id=msg_id)
        for msg_id in bet_message_ids
    ]
    results = await asyncio.gather(*delete_tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.debug(f"[Utils] Не удалось удалить сообщение: {result}")


async def delete_spin_message(chat_id: int, spin_message_id: Optional[int]):
    if not spin_message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=spin_message_id)
    except Exception as e:
        logger.debug(f"[Utils] Не удалось удалить spin-сообщение: {e}")


def format_wait_time(wait_time: float) -> str:
    if wait_time > 60:
        wait_minutes = int(wait_time // 60)
        wait_seconds = int(wait_time % 60)
        return f"{wait_minutes} мин {wait_seconds} сек"
    return f"{wait_time:.1f} секунд"


def get_bet_display_value(bet_type: str, bet_value: Any) -> str:
    if bet_type == "цвет":
        color_emojis = {"красное": "🔴", "черное": "⚫", "зеленое": "🟢 зеро"}
        return color_emojis.get(bet_value, str(bet_value))
    return str(bet_value)


def calculate_bet_result(game, bet, result: int) -> Tuple[int, int]:
    """
    Рассчитывает результат ставки с учетом ТЗ:
    - При выпадении 0: ставки на цвет (кроме зеленого) и группы возвращаются 50%
    - Ставки на число 0 выигрывают с коэффициентом 12х
    - Ставки на зеленое (как цвет) выигрывают с коэффициентом 12х
    """
    # Проверяем, выпало ли зеро (0)
    is_zero_result = (result == 0)

    # Проверяем, выиграла ли ставка по обычным правилам
    is_win_by_normal_rules = game.check_bet(bet.type, bet.value, result)

    # Если выпало зеро
    if is_zero_result:
        # Ставка на число 0 - полный выигрыш 12х
        if bet.type == "число" and bet.value == 0:
            multiplier = game.get_multiplier(bet.type, bet.value)
            gross_profit = int(bet.amount * multiplier)
            total_payout = gross_profit
            return gross_profit, total_payout

        # Ставка на цвет зеленое - полный выигрыш 12х
        elif bet.type == "цвет" and bet.value == "зеленое":
            multiplier = game.get_multiplier(bet.type, bet.value)
            gross_profit = int(bet.amount * multiplier)
            total_payout = gross_profit
            return gross_profit, total_payout

        # Ставки на другие цвета (красное/черное) - возврат 50%
        elif bet.type == "цвет" and bet.value in ["красное", "черное"]:
            half_bet = bet.amount // 2
            return -half_bet, half_bet  # net_profit = -половина, payout = половина

        # Ставки на группы - проверяем, включает ли группа 0
        elif bet.type == "группа":
            # Если группа включает 0 (например "0-1") — это выигрыш
            if is_win_by_normal_rules:
                multiplier = game.get_multiplier(bet.type, bet.value)
                gross_profit = int(bet.amount * multiplier)
                total_payout = gross_profit
                return gross_profit, total_payout
            # Иначе возврат 50%
            half_bet = bet.amount // 2
            return -half_bet, half_bet

        # Ставки на другие числа - возврат 50%
        elif bet.type == "число":
            half_bet = bet.amount // 2
            return -half_bet, half_bet

    # Если не зеро - стандартный расчет
    if is_win_by_normal_rules:
        multiplier = game.get_multiplier(bet.type, bet.value)
        gross_profit = int(bet.amount * multiplier)
        total_payout = gross_profit
        return gross_profit, total_payout
    else:
        # Полный проигрыш
        return -bet.amount, 0


def parse_vabank_bet(bet_value: str) -> Optional[Tuple[str, Any]]:
    color_map = {
        'к': 'красное', 'кр': 'красное', 'крас': 'красное', 'red': 'красное',
        'ч': 'черное', 'чер': 'черное', 'black': 'черное',
        'з': 'зеленое', 'зел': 'зеленое', 'green': 'зеленое', '0': 'зеленое'
    }
    bet_value = bet_value.lower().strip()

    if bet_value.isdigit() and 0 <= int(bet_value) <= 12:
        return "число", int(bet_value)

    if bet_value in color_map:
        return "цвет", color_map[bet_value]
    if bet_value in ['красное', 'черное', 'зеленое']:
        return "цвет", bet_value

    group_map = {
        '1-3': '1-3', '13': '1-3',
        '4-6': '4-6', '46': '4-6',
        '7-9': '7-9', '79': '7-9',
        '10-12': '10-12', '1012': '10-12'
    }
    if bet_value in group_map:
        return "группа", group_map[bet_value]
    elif '-' in bet_value:
        try:
            start, end = map(int, bet_value.split('-'))
            if 0 <= start <= 12 and 0 <= end <= 12 and start <= end:
                return "группа", f"{start}-{end}"
        except (ValueError, TypeError):
            pass

    return None