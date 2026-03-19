from aiogram.dispatcher.filters.state import State, StatesGroup

class RouletteStates(StatesGroup):
    """Состояния для рулетки"""
    waiting_for_bet = State()
    placing_bet = State()
    spinning = State()

class DonationStates(StatesGroup):
    """Состояния для доната"""
    waiting_for_screenshot = State()
    confirming_donation = State()

class ClanStates(StatesGroup):
    """Состояния для кланов"""
    waiting_for_clan_name = State()
    waiting_for_clan_tag = State()
    waiting_for_clan_description = State()
    waiting_for_application_text = State()

class AdminStates(StatesGroup):
    """Состояния для админки"""
    waiting_for_ban_reason = State()
    waiting_for_mute_duration = State()
    waiting_for_reset_confirmation = State()
    waiting_for_coins_amount = State()

class ProfileStates(StatesGroup):
    """Состояния для профиля"""
    editing_status = State()
    editing_bio = State()