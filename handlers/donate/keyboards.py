from aiogram import types
from database.crud import DonateRepository
from .config import STATUSES, SUPPORT_USERNAME, COIN_PACKAGES


def create_main_donate_keyboard():
    """Создает главную клавиатуру доната"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    # Кнопка для покупки монет
    keyboard.row(
        types.InlineKeyboardButton(
            text="💸 Купить Монеты",
            callback_data="donate_buy_coins"
        )
    )

    # Кнопка для покупки статусов
    keyboard.row(
        types.InlineKeyboardButton(
            text="👑 Купить Статус",
            callback_data="donate_statuses"
        )
    )

    # Кнопка для снятия лимита на передачу (СУЩЕСТВУЮЩЕЕ)
    keyboard.row(
        types.InlineKeyboardButton(
            text="🔓 Снять лимит на передачу монет",
            callback_data="check_type_limit"
        )
    )

    # НОВАЯ КНОПКА: Снятие лимита рулетки
    keyboard.row(
        types.InlineKeyboardButton(
            text="🎰 Снять лимит рулетки в группе - 500₽",
            callback_data="check_type_roulette_limit"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="🎁 Ежедневный бонус",
            callback_data="daily_bonus"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="📊 Мои статусы/чеки",
            callback_data="my_statuses_checks"
        )
    )

    return keyboard


def create_direct_purchase_keyboard():
    """Создает клавиатуру для прямой покупки без /чек"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    # Кнопки для быстрой покупки монет
    keyboard.row(
        types.InlineKeyboardButton(
            text="💰 1.300.000 монет — 400₽",
            callback_data="quick_buy_1300000"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="💰 6.000.000 монет — 1.200₽",
            callback_data="quick_buy_6000000"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="💰 28.000.000 монет — 3.500₽",
            callback_data="quick_buy_28000000"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="📋 Все пакеты монет",
            callback_data="donate_buy_coins"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="🎖️ Показать статусы",
            callback_data="donate_statuses"
        )
    )

    return keyboard


def create_statuses_keyboard(user_id: int = None):
    """Создает клавиатуру статусов"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    # Проверяем активный статус пользователя
    active_status_id = None
    if user_id:
        from .status_repository import StatusRepository
        status_repo = StatusRepository()
        try:
            active_status = status_repo.get_user_active_status(user_id)
            if active_status:
                active_status_id = active_status.get('status_id')
        except Exception:
            active_status_id = None

    for status in STATUSES:
        if status["id"] == 1:  # Обычный статус пропускаем
            continue

        if status["id"] == active_status_id:
            # Уже активен
            emoji = "✅"
            text = f"{emoji} {status['icon']} {status['name'].title()}"
            callback_data = f"status_active_{status['id']}"
        else:
            # Можно купить
            emoji = status['icon']
            text = f"{emoji} {status['name'].title()} - {status['price_rub']:,} руб"
            callback_data = f"status_buy_{status['id']}"

        keyboard.row(
            types.InlineKeyboardButton(
                text=text,
                callback_data=callback_data
            )
        )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_donate"
        )
    )

    return keyboard


def create_send_check_keyboard():
    """Создает клавиатуру для отправки чека"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.row(
        types.InlineKeyboardButton(
            text="💰 Покупка монет",
            callback_data="check_type_coins"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="🎖️ Покупка статуса",
            callback_data="check_type_status"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="🔓 Снятие лимита",
            callback_data="check_type_limit"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад в меню доната",
            callback_data="back_to_donate"
        )
    )

    return keyboard


def create_bonus_keyboard(has_active_status: bool):
    """Создает клавиатуру бонусов"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    if has_active_status:
        keyboard.row(
            types.InlineKeyboardButton(
                text="🎁 Получить бонус",
                callback_data="claim_bonus"
            )
        )

    keyboard.row(
        types.InlineKeyboardButton(
            text="📊 Мои статусы",
            callback_data="my_statuses"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_donate"
        )
    )

    return keyboard


def create_buy_keyboard():
    """Создает клавиатуру для покупки"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.row(
        types.InlineKeyboardButton(
            text="💬 Написать в кассу",
            url=f"https://t.me/{SUPPORT_USERNAME}"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_donate"
        )
    )

    return keyboard


def create_status_purchase_keyboard(status_id: int):
    """Создает клавиатуру для покупки статуса"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.row(
        types.InlineKeyboardButton(
            text="💬 Купить статус",
            url=f"https://t.me/{SUPPORT_USERNAME}"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="📋 Назад к статусам",
            callback_data="donate_statuses"
        )
    )

    return keyboard


def create_back_keyboard():
    """Создает клавиатуру с кнопкой назад"""
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_donate"
        )
    )

    return keyboard


def create_my_status_keyboard():
    """Создает клавиатуру для раздела моих статусов"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    keyboard.row(
        types.InlineKeyboardButton(
            text="🎁 Получить бонус",
            callback_data="claim_bonus"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="💎 Продлить статус",
            callback_data="extend_status"
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="back_to_donate"
        )
    )

    return keyboard