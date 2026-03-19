"""
States для системы чеков
"""
from aiogram.dispatcher.filters.state import State, StatesGroup

class CheckStates(StatesGroup):
    waiting_for_check_type = State()  # Ожидание выбора типа покупки
    waiting_for_check_details = State()  # Ожидание выбора деталей покупки
    waiting_for_check_photo = State()  # Ожидание фото чека
    waiting_for_group_id = State()  # Ожидание ID группы для снятия лимита рулетки